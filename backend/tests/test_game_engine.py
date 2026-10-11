"""Tests du moteur de règles (Bloc 4) — couvre les critères "Done when" du
Bloc 4 de docs/exec-plans/reconstruction-le-grand-tunneg.md :
- barème de points par palier (1/2/3/5)
- coffrage automatique en case 10 (sans passage par choice_pending)
- non-perte de progression sur mauvaise réponse
- non-gain définitif sur case passée même après coffrage ultérieur
- vol de progression par un autre joueur
- rejet de sélection d'un thème `completed`
- comportement distinct reset-partie vs quitter-partie
- transition choice_pending -> choice_open déclenchable uniquement par le
  Présentateur, et rejet d'un choix joueur tant que l'état est choice_pending
"""

from __future__ import annotations

import random

import pytest

from app.game import engine, rules
from app.game.types import GameState, Player, Theme


# --- Fixtures / helpers ------------------------------------------------------


def two_player_lobby() -> GameState:
    state = GameState()
    state = engine.add_player(state, "p1", "Alice")
    state = engine.add_player(state, "p2", "Bob")
    return state


def started_selection_open(seed: int = 0) -> GameState:
    """Lobby -> thèmes -> partie démarrée -> choice ouvert sur la sélection."""
    state = two_player_lobby()
    state = engine.go_to_themes(state, "presentateur")
    state = engine.add_theme(state, "Cinéma", "presentateur")
    state = engine.start_game(state, "presentateur", rng=random.Random(seed))
    state = engine.reveal_choice(state, "presentateur")
    assert state.phase == "selection"
    return state


def current_player_id(state: GameState) -> str:
    return state.players[state.current_player_index].id


def select_and_start(state: GameState, index: int, pid: str) -> GameState:
    """Sélectionne un thème puis lance immédiatement le chrono (le
    Présentateur a fini de poser sa question) — raccourci pour les tests qui
    ne portent pas sur le nouveau sous-état question-pending lui-même."""
    state = engine.select_theme(state, index, "joueur", pid)
    return engine.start_timer(state, "presentateur")


def continue_and_start(state: GameState, pid: str) -> GameState:
    state = engine.continue_tunnel(state, "joueur", pid)
    return engine.start_timer(state, "presentateur")


# --- Barème de points --------------------------------------------------------


@pytest.mark.parametrize(
    "square,expected",
    [(1, 1), (2, 1), (3, 1), (4, 2), (5, 2), (6, 2), (7, 3), (8, 3), (9, 3), (10, 5)],
)
def test_points_for_square(square: int, expected: int) -> None:
    assert rules.points_for_square(square) == expected


# --- Coloration des cases -----------------------------------------------------


def test_square_color_priority_nullified_over_everything() -> None:
    theme = Theme(
        label="x", progress_value=5, validated_squares=5, discovered=True, nullified=(3,)
    )
    assert rules.square_color(theme, 3) == "black"


def test_square_color_gray_green_yellow_empty() -> None:
    theme = Theme(label="x", progress_value=3, validated_squares=2, discovered=True)
    assert rules.square_color(theme, 1) == "gray"
    assert rules.square_color(theme, 2) == "gray"
    assert rules.square_color(theme, 3) == "green"
    assert rules.square_color(theme, 4) == "yellow"  # k-1 == progress_value, discovered
    assert rules.square_color(theme, 5) == "empty"


# --- Coffrage automatique en case 10 -----------------------------------------


def test_auto_coffrage_at_square_10_skips_choice_pending() -> None:
    # Deux thèmes pour que la partie ne se termine pas après le coffrage auto
    # du premier (sinon phase passerait à 'end', ce qui est testé ailleurs).
    state = two_player_lobby()
    state = engine.go_to_themes(state, "presentateur")
    state = engine.add_theme(state, "Cinéma", "presentateur")
    state = engine.add_theme(state, "Musique", "presentateur")
    state = engine.start_game(state, "presentateur", rng=random.Random(0))
    state = engine.reveal_choice(state, "presentateur")
    pid = current_player_id(state)
    state = select_and_start(state, 0, pid)
    assert state.phase == "tunnel"

    # 10 bonnes réponses : les 9 premières font progress_value 0->9 (en
    # repassant par Continuer à chaque fois), la 10e détecte progress_value==9
    # et déclenche l'auto-coffrage (0->10) directement depuis "Bonne réponse".
    for i in range(10):
        state = engine.good_answer(state, "presentateur")
        if i < 9:
            # Pas encore à progress_value=9 -> cycle after-success choisi par
            # le joueur : on choisit Continuer pour relancer une question.
            assert state.tunnel_sub_phase == "after-success-pending"
            state = engine.reveal_choice(state, "presentateur")
            pid = current_player_id(state)
            state = continue_and_start(state, pid)
            assert state.tunnel_sub_phase == "question"

    # Après la 9e bonne réponse, progress_value doit être passé de 9 à 10 et
    # l'auto-coffrage doit avoir eu lieu sans passer par choice_pending.
    theme = state.themes[0]
    assert theme.progress_value == 10
    assert theme.validated_squares == 10
    assert theme.completed is True
    # Aucun sous-état after-success-* : retour direct à selection-pending.
    assert state.tunnel_sub_phase is None
    assert state.phase == "selection-pending"
    # Points crédités : somme des barèmes 1..10 = 1*3+2*3+3*3+5 = 3+6+9+5=23
    assert sum(p.points for p in state.players) == 23


# --- Non-perte de progression sur mauvaise réponse --------------------------


def test_bad_answer_does_not_lose_progress() -> None:
    state = started_selection_open()
    starting_index = state.current_player_index
    pid = current_player_id(state)
    state = select_and_start(state, 0, pid)
    state = engine.good_answer(state, "presentateur")  # progress_value -> 1
    theme_before = state.themes[0]
    assert theme_before.progress_value == 1

    state = engine.reveal_choice(state, "presentateur")
    pid = current_player_id(state)
    state = continue_and_start(state, pid)
    state = engine.bad_answer(state, "presentateur")

    theme_after = state.themes[0]
    assert theme_after.progress_value == 1  # inchangé
    assert theme_after.validated_squares == 0
    assert theme_after.nullified == ()
    assert state.phase == "selection-pending"
    # Le tour passe au joueur suivant.
    assert state.current_player_index == (starting_index + 1) % len(state.players)


# --- Non-gain définitif sur case passée même après coffrage ultérieur -------


def test_pass_nullifies_square_permanently_even_after_vault() -> None:
    state = started_selection_open()
    starting_index = state.current_player_index
    pid = current_player_id(state)
    state = select_and_start(state, 0, pid)

    # Passer sur la case 1 : nullified=[1], progress_value=1, joueur reste actif.
    state = engine.pass_question(state, "presentateur")
    theme = state.themes[0]
    assert theme.nullified == (1,)
    assert theme.progress_value == 1
    assert state.phase == "selection-pending"
    # current_player_index inchangé (le joueur reste actif après un Passer).
    assert state.current_player_index == starting_index

    # Reprendre le même thème et avancer jusqu'à coffrer : la case 1 ne doit
    # jamais rapporter de points, même si validated_squares la dépasse.
    state = engine.reveal_choice(state, "presentateur")
    pid = current_player_id(state)
    state = select_and_start(state, 0, pid)
    state = engine.good_answer(state, "presentateur")  # progress_value -> 2
    state = engine.reveal_choice(state, "presentateur")
    pid = current_player_id(state)
    state = engine.vault(state, "joueur", pid)  # coffrer manuellement

    theme = state.themes[0]
    assert theme.validated_squares == 2
    assert 1 in theme.nullified
    # Seule la case 2 (1 point) doit avoir été créditée, pas la case 1.
    assert state.players[0].points == 1 or state.players[1].points == 1
    assert sum(p.points for p in state.players) == 1


# --- Vol de progression par un autre joueur ---------------------------------


def test_progress_can_be_stolen_by_another_player() -> None:
    state = started_selection_open()
    starting_index = state.current_player_index
    first_player = current_player_id(state)
    state = select_and_start(state, 0, first_player)
    state = engine.good_answer(state, "presentateur")  # progress_value -> 1 (vert)
    assert state.tunnel_sub_phase == "after-success-pending"
    state = engine.reveal_choice(state, "presentateur")
    state = continue_and_start(state, first_player)
    state = engine.bad_answer(state, "presentateur")  # tour passe, case verte reste
    assert state.current_player_index == (starting_index + 1) % len(state.players)
    second_player = current_player_id(state)
    assert second_player != first_player

    # Le 2e joueur reprend le même thème (toujours vert, progress_value=1) et coffre.
    state = engine.reveal_choice(state, "presentateur")  # selection-pending -> selection
    state = select_and_start(state, 0, second_player)
    state = engine.good_answer(state, "presentateur")  # progress_value -> 2
    state = engine.reveal_choice(state, "presentateur")  # after-success-pending -> open
    state = engine.vault(state, "joueur", second_player)

    # Les points de la case 1 doivent revenir au 2e joueur (le voleur), pas au 1er.
    second_idx = state.players.index(
        next(p for p in state.players if p.id == second_player)
    )
    first_idx = state.players.index(
        next(p for p in state.players if p.id == first_player)
    )
    # Coffrage couvre les cases 1 et 2 (1pt chacune) = 2 points, tous pour le
    # 2e joueur ; le 1er joueur (qui avait eu la bonne réponse sur la case 1
    # mais n'a jamais coffré) ne touche rien.
    assert state.players[second_idx].points == 2
    assert state.players[first_idx].points == 0


# --- Rejet de sélection d'un thème completed ---------------------------------


def test_select_completed_theme_is_rejected() -> None:
    state = two_player_lobby()
    state = engine.go_to_themes(state, "presentateur")
    state = engine.add_theme(state, "Seul thème", "presentateur")
    state = engine.start_game(state, "presentateur", rng=random.Random(1))
    state = engine.reveal_choice(state, "presentateur")
    pid = current_player_id(state)
    state = engine.select_theme(state, 0, "joueur", pid)

    # Force le thème à completed=True directement pour tester le garde-fou
    # indépendamment du chemin d'auto-coffrage (déjà testé ailleurs).
    from dataclasses import replace

    state = replace(
        state,
        themes=(replace(state.themes[0], completed=True),),
        phase="selection-pending",
        active_theme_index=None,
        tunnel_sub_phase=None,
    )
    state = engine.reveal_choice(state, "presentateur")
    with pytest.raises(engine.GameError) as exc_info:
        engine.select_theme(state, 0, "joueur", current_player_id(state))
    assert exc_info.value.code == "invalid_payload"


# --- Reset vs quitter ---------------------------------------------------------


def test_reset_game_keeps_players_and_themes_zeroes_progress() -> None:
    state = started_selection_open()
    pid = current_player_id(state)
    state = select_and_start(state, 0, pid)
    state = engine.good_answer(state, "presentateur")

    state = engine.reset_game(state, "presentateur")
    assert len(state.players) == 2
    assert all(p.points == 0 for p in state.players)
    assert len(state.themes) == 1
    theme = state.themes[0]
    assert theme.progress_value == 0 and theme.validated_squares == 0
    assert theme.discovered is False and theme.completed is False
    assert theme.nullified == ()
    assert state.phase == "selection-pending"


def test_quit_to_menu_wipes_everything() -> None:
    state = started_selection_open()
    state = engine.quit_to_menu(state, "presentateur")
    assert state == GameState()
    assert state.players == ()
    assert state.themes == ()
    assert state.phase == "menu"


def test_reset_game_rejected_for_non_presentateur() -> None:
    state = started_selection_open()
    with pytest.raises(engine.GameError) as exc_info:
        engine.reset_game(state, "joueur")
    assert exc_info.value.code == "forbidden_role"


# --- choice_pending -> choice_open : enforcement de rôle et de phase --------


def test_reveal_choice_only_by_presentateur() -> None:
    state = two_player_lobby()
    state = engine.go_to_themes(state, "presentateur")
    state = engine.add_theme(state, "Thème", "presentateur")
    state = engine.start_game(state, "presentateur", rng=random.Random(0))
    assert state.phase == "selection-pending"

    with pytest.raises(engine.GameError) as exc_info:
        engine.reveal_choice(state, "joueur")
    assert exc_info.value.code == "forbidden_role"

    state = engine.reveal_choice(state, "presentateur")
    assert state.phase == "selection"


def test_select_theme_rejected_while_choice_pending() -> None:
    state = two_player_lobby()
    state = engine.go_to_themes(state, "presentateur")
    state = engine.add_theme(state, "Thème", "presentateur")
    state = engine.start_game(state, "presentateur", rng=random.Random(0))
    assert state.phase == "selection-pending"
    pid = current_player_id(state)

    with pytest.raises(engine.GameError) as exc_info:
        engine.select_theme(state, 0, "joueur", pid)
    assert exc_info.value.code == "invalid_phase"


def test_continue_or_vault_rejected_while_after_success_pending() -> None:
    state = started_selection_open()
    pid = current_player_id(state)
    state = select_and_start(state, 0, pid)
    state = engine.good_answer(state, "presentateur")
    assert state.tunnel_sub_phase == "after-success-pending"

    with pytest.raises(engine.GameError) as exc_info:
        engine.continue_tunnel(state, "joueur", pid)
    assert exc_info.value.code == "invalid_phase"

    with pytest.raises(engine.GameError) as exc_info:
        engine.vault(state, "joueur", pid)
    assert exc_info.value.code == "invalid_phase"


def test_wrong_player_cannot_act_on_behalf_of_current_player() -> None:
    state = started_selection_open()
    pid = current_player_id(state)
    other_pid = next(p.id for p in state.players if p.id != pid)
    with pytest.raises(engine.GameError) as exc_info:
        engine.select_theme(state, 0, "joueur", other_pid)
    assert exc_info.value.code == "not_your_turn"


def test_presentateur_cannot_select_theme_on_behalf_of_player() -> None:
    state = started_selection_open()
    with pytest.raises(engine.GameError) as exc_info:
        engine.select_theme(state, 0, "presentateur", "whatever")
    assert exc_info.value.code == "forbidden_role"


# --- Jugement de réponse réservé au Présentateur -----------------------------


@pytest.mark.parametrize("action", ["good_answer", "bad_answer", "pass_question"])
def test_answer_judgement_rejected_for_non_presentateur(action: str) -> None:
    state = started_selection_open()
    pid = current_player_id(state)
    state = engine.select_theme(state, 0, "joueur", pid)
    fn = getattr(engine, action)
    with pytest.raises(engine.GameError) as exc_info:
        fn(state, "joueur")
    assert exc_info.value.code == "forbidden_role"


# --- Couche show : délai de lancement du chrono (question-pending) ----------


def test_select_theme_enters_question_pending_not_question() -> None:
    state = started_selection_open()
    pid = current_player_id(state)
    state = engine.select_theme(state, 0, "joueur", pid)
    assert state.phase == "tunnel"
    assert state.tunnel_sub_phase == "question-pending"


def test_judgement_rejected_while_question_pending() -> None:
    state = started_selection_open()
    pid = current_player_id(state)
    state = engine.select_theme(state, 0, "joueur", pid)
    assert state.tunnel_sub_phase == "question-pending"

    for action in ("good_answer", "bad_answer", "pass_question"):
        with pytest.raises(engine.GameError) as exc_info:
            getattr(engine, action)(state, "presentateur")
        assert exc_info.value.code == "invalid_phase"


def test_start_timer_transitions_question_pending_to_question() -> None:
    state = started_selection_open()
    pid = current_player_id(state)
    state = engine.select_theme(state, 0, "joueur", pid)
    state = engine.start_timer(state, "presentateur")
    assert state.tunnel_sub_phase == "question"
    # Une fois le chrono lancé, le jugement devient possible.
    state = engine.good_answer(state, "presentateur")
    assert state.themes[0].progress_value == 1


def test_start_timer_rejected_for_non_presentateur() -> None:
    state = started_selection_open()
    pid = current_player_id(state)
    state = engine.select_theme(state, 0, "joueur", pid)
    with pytest.raises(engine.GameError) as exc_info:
        engine.start_timer(state, "joueur")
    assert exc_info.value.code == "forbidden_role"


def test_start_timer_rejected_outside_question_pending() -> None:
    state = started_selection_open()
    with pytest.raises(engine.GameError) as exc_info:
        engine.start_timer(state, "presentateur")
    assert exc_info.value.code == "invalid_phase"


def test_continue_tunnel_re_enters_question_pending() -> None:
    state = started_selection_open()
    pid = current_player_id(state)
    state = select_and_start(state, 0, pid)
    state = engine.good_answer(state, "presentateur")  # progress_value -> 1
    assert state.tunnel_sub_phase == "after-success-pending"
    state = engine.reveal_choice(state, "presentateur")
    state = engine.continue_tunnel(state, "joueur", pid)
    # Continuer repasse par question-pending, PAS directement question : le
    # Présentateur doit reposer sa question avant de relancer le chrono.
    assert state.tunnel_sub_phase == "question-pending"
    with pytest.raises(engine.GameError) as exc_info:
        engine.good_answer(state, "presentateur")
    assert exc_info.value.code == "invalid_phase"
