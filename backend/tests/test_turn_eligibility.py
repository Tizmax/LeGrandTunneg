"""Presence, nullable turn DTOs and conservative multiplayer rotation."""

import random
from dataclasses import replace

import pytest

from app.core.settings import settings
from app.game import engine
from app.game.serialize import serialize_state
from app.game.types import GameState


def lobby() -> GameState:
    state = engine.add_player(GameState(), "host", "Host", is_presenter=True)
    for pid in ("alice", "bob", "carol"):
        state = engine.add_player(state, pid, pid)
    return engine.add_theme(state, "Theme", "presentateur")


def started() -> GameState:
    state = lobby()
    state = engine.set_player_connected(state, "host", True)
    state = engine.set_player_connected(state, "bob", True)
    return engine.start_game(state, "presentateur", rng=random.Random(0))


def at_subphase(subphase: str) -> GameState:
    state = started()
    if subphase == "selection-pending":
        return state
    state = engine.reveal_choice(state, "presentateur")
    if subphase == "selection":
        return state
    state = engine.select_theme(state, 0, "joueur", "bob")
    if subphase == "question-pending":
        return state
    state = engine.start_timer(state, "presentateur")
    if subphase == "question":
        return state
    state = engine.good_answer(state, "presentateur")
    if subphase == "after-success-pending":
        return state
    return engine.reveal_choice(state, "presentateur")


def assert_rejected(code: str, action, *args) -> None:
    state = args[0]
    before = serialize_state(state)
    with pytest.raises(engine.GameError) as caught:
        action(*args)
    assert caught.value.code == code
    assert serialize_state(state) == before


def test_rest_membership_is_absent_and_lobby_dto_is_idle() -> None:
    state = lobby()
    assert all(not p.connected for p in state.players)
    dto = serialize_state(state)
    assert dto["currentPlayerIndex"] is None
    assert dto["rotationAnchorIndex"] is None
    assert dto["turnStatus"] == "idle"


@pytest.mark.parametrize("seed", range(10))
def test_start_draw_only_includes_connected_nonpresenters(seed: int) -> None:
    state = engine.set_player_connected(lobby(), "host", True)
    assert_rejected("invalid_phase", engine.start_game, state, "presentateur")
    state = engine.set_player_connected(state, "bob", True)
    state = engine.start_game(state, "presentateur", rng=random.Random(seed))
    assert state.current_player_index == 2
    assert state.turn_status == "ready"
    assert state.rotation_anchor_index is None


@pytest.mark.parametrize("subphase", [
    "selection-pending", "selection", "question-pending", "question",
    "after-success-pending", "after-success-open",
])
def test_active_loss_and_return_preserve_exact_turn(subphase: str) -> None:
    state = at_subphase(subphase)
    absent = engine.set_player_connected(state, "bob", False)
    assert absent == replace(
        state, players=tuple(replace(p, connected=False) if p.id == "bob" else p
                             for p in state.players), turn_status="active-absent",
    )
    assert serialize_state(absent)["turnStatus"] == "active-absent"
    assert absent.current_player_index == 2
    assert absent.rotation_anchor_index is None
    for action in (engine.reveal_choice, engine.start_timer, engine.good_answer,
                   engine.bad_answer, engine.pass_question):
        assert_rejected("game_suspended", action, absent, "presentateur")
    assert_rejected("game_suspended", engine.select_theme, absent, 0, "joueur", "bob")
    for action in (engine.continue_tunnel, engine.vault):
        assert_rejected("game_suspended", action, absent, "joueur", "bob")
    other_returned = engine.set_player_connected(absent, "alice", True)
    assert other_returned.turn_status == "active-absent"
    assert other_returned.current_player_index == 2
    assert engine.set_player_connected(absent, "bob", True) == state
    resumed = engine.set_player_connected(other_returned, "bob", True)
    assert resumed.turn_status == "ready"
    assert resumed.themes == state.themes
    assert resumed.history == state.history
    assert resumed.tunnel_sub_phase == state.tunnel_sub_phase


def test_nonactive_and_presenter_presence_do_not_suspend_actor() -> None:
    state = started()
    state = engine.set_player_connected(state, "host", False)
    state = engine.set_player_connected(state, "alice", True)
    state = engine.set_player_connected(state, "alice", False)
    assert state.turn_status == "ready"
    assert state.current_player_index == 2


def test_rotation_wraps_to_only_eligible_actor() -> None:
    state = engine.bad_answer(at_subphase("question"), "presentateur")
    assert state.current_player_index == 2
    assert state.turn_status == "ready"
    state = engine.set_player_connected(state, "alice", True)
    state = engine.reveal_choice(state, "presentateur")
    state = engine.select_theme(state, 0, "joueur", "bob")
    state = engine.start_timer(state, "presentateur")
    state = engine.bad_answer(state, "presentateur")
    assert state.current_player_index == 1


@pytest.mark.parametrize("action", ["bad_answer", "vault", "good_answer"])
def test_noeligible_transition_and_anchor_recovery(action: str) -> None:
    # Serialized command/presence handling normally keeps the active actor
    # eligible until completion; inject the boundary to exercise total rotation.
    state = at_subphase("after-success-open" if action == "vault" else "question")
    if action == "good_answer":
        state = replace(state, themes=(replace(state.themes[0], progress_value=9),))
        state = replace(state, themes=state.themes + (replace(state.themes[0],
                        label="Other", progress_value=0),))
    state = replace(state, players=tuple(replace(p, connected=False) for p in state.players))
    state = (engine.vault(state, "joueur", "bob") if action == "vault"
             else getattr(engine, action)(state, "presentateur"))
    assert state.phase == "selection-pending"
    assert state.current_player_index is None
    assert state.turn_status == "waiting-eligible"
    assert state.rotation_anchor_index == 2
    dto = serialize_state(state)
    assert dto["currentPlayerIndex"] is None
    assert dto["rotationAnchorIndex"] == 2
    assert dto["turnStatus"] == "waiting-eligible"
    if action != "bad_answer":
        assert state.history and sum(p.points for p in state.players) > 0
    for fn in (engine.reveal_choice, engine.start_timer, engine.good_answer,
               engine.bad_answer, engine.pass_question):
        assert_rejected("game_suspended", fn, state, "presentateur")
    assert_rejected("game_suspended", engine.select_theme, state, 0, "joueur", "bob")
    for fn in (engine.continue_tunnel, engine.vault):
        assert_rejected("game_suspended", fn, state, "joueur", "bob")
    assert_rejected("invalid_phase", engine.reset_game, state, "presentateur")
    host_returned = engine.set_player_connected(state, "host", True)
    assert host_returned.turn_status == "waiting-eligible"
    recovered = engine.set_player_connected(host_returned, "carol", True)
    assert recovered.current_player_index == 3
    assert recovered.turn_status == "ready"
    assert recovered.rotation_anchor_index is None
    assert recovered.themes == state.themes
    assert recovered.history == state.history
    assert recovered.players[0].points == 0
    # Recovery searches cyclically after the anchor, not from array index zero.
    boundary = replace(state, players=tuple(
        replace(p, connected=p.id in {"alice", "carol"}) for p in state.players
    ))
    recovered = engine.set_player_connected(boundary, "host", True)
    assert recovered.current_player_index == 3
    for pid, expected_index in (("alice", 1), ("bob", 2)):
        recovered = engine.set_player_connected(state, pid, True)
        assert recovered.current_player_index == expected_index
        assert recovered.turn_status == "ready"
        assert recovered.rotation_anchor_index is None
    assert engine.end_game_early(state, "presentateur").turn_status == "idle"
    assert engine.quit_to_menu(state, "presentateur") == GameState()


@pytest.mark.parametrize("progress", [0, 9])
def test_pass_retains_actor_including_automatic_coffrage(progress: int) -> None:
    state = at_subphase("question")
    state = engine.set_player_connected(state, "carol", True)
    state = replace(state, themes=(replace(state.themes[0], progress_value=progress),
                                  replace(state.themes[0], label="Other")))
    result = engine.pass_question(state, "presentateur")
    assert result.phase == "selection-pending"
    assert result.current_player_index == 2
    assert result.turn_status == "ready"
    assert result.rotation_anchor_index is None
    assert progress + 1 in result.themes[0].nullified
    assert result.themes[0].completed == (progress == 9)
    assert result.players[0].points == 0
    assert result.players[2].points == (18 if progress == 9 else 0)
    assert [h.points_gained for h in result.history] == ([18] if progress == 9 else [])


@pytest.mark.parametrize("action", [engine.good_answer, engine.pass_question])
def test_terminal_case10_clears_turn_metadata_before_rotation(action) -> None:
    state = at_subphase("question")
    state = replace(state, themes=(replace(state.themes[0], progress_value=9),))
    # Even the no-eligible boundary ends rather than entering a waiting turn.
    state = replace(state, players=tuple(replace(p, connected=False) for p in state.players))
    state = action(state, "presentateur")
    assert state.phase == "end"
    assert state.turn_status == "idle"
    assert state.current_player_index is None
    assert state.rotation_anchor_index is None
    assert state.tunnel_sub_phase is None
    assert state.active_theme_index is None
    state = engine.set_player_connected(state, "alice", True)
    assert state.turn_status == "idle"
    assert state.current_player_index is None


def test_reset_eligibility_and_suspended_escape_controls() -> None:
    assert_rejected("invalid_phase", engine.reset_game, lobby(), "presentateur")
    state = at_subphase("after-success-open")
    state = engine.vault(state, "joueur", "bob")
    state = engine.set_player_connected(state, "bob", False)
    assert_rejected("invalid_phase", engine.reset_game, state, "presentateur")
    state = engine.set_player_connected(state, "carol", True)
    assert_rejected("invalid_phase", engine.reset_game, replace(state, themes=()), "presentateur")
    state = engine.set_player_connected(state, "alice", True)
    reset = engine.reset_game(state, "presentateur")
    assert reset.current_player_index == 1
    assert reset.turn_status == "ready"
    assert reset.phase == "selection-pending"
    assert reset.rotation_anchor_index is None
    assert reset.history == ()
    assert all(p.points == 0 for p in reset.players)
    assert reset.themes[0].progress_value == 0
    ended = engine.end_game_early(state, "presentateur")
    assert ended.current_player_index is None
    assert ended.rotation_anchor_index is None
    assert ended.turn_status == "idle"
    assert ended.phase == "lobby"
    assert [p.connected for p in ended.players] == [p.connected for p in state.players]
    assert engine.quit_to_menu(state, "presentateur") == GameState()


def test_complete_game_scores_one_then_twenty_two_presenter_zero() -> None:
    state = engine.set_player_connected(started(), "carol", True)
    state = engine.reveal_choice(state, "presentateur")
    state = engine.select_theme(state, 0, "joueur", "bob")
    state = engine.start_timer(state, "presentateur")
    state = engine.good_answer(state, "presentateur")
    state = engine.reveal_choice(state, "presentateur")
    state = engine.vault(state, "joueur", "bob")
    assert state.players[2].points == 1
    assert state.themes[0].completed is False
    assert state.current_player_index == 3
    state = engine.reveal_choice(state, "presentateur")
    state = engine.select_theme(state, 0, "joueur", "carol")
    for square in range(2, 11):
        state = engine.start_timer(state, "presentateur")
        state = engine.good_answer(state, "presentateur")
        if square < 10:
            state = engine.reveal_choice(state, "presentateur")
            state = engine.continue_tunnel(state, "joueur", "carol")
    assert state.phase == "end"
    assert [p.points for p in state.players] == [0, 0, 1, 22]
    assert [h.points_gained for h in state.history] == [1, 22]
    assert state.turn_status == "idle"
    assert state.current_player_index is None
    reset = engine.reset_game(state, "presentateur")
    assert reset.current_player_index == 2
    assert reset.turn_status == "ready"


def test_engine_limits_use_configured_values_after_trimming(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_players", 2)
    monkeypatch.setattr(settings, "max_themes", 1)
    monkeypatch.setattr(settings, "max_name_chars", 3)
    monkeypatch.setattr(settings, "max_theme_label_chars", 4)
    state = engine.add_player(GameState(), "host", " Abc ", is_presenter=True)
    assert state.players[0].name == "Abc"
    assert_rejected("invalid_payload", engine.add_player, state, "p1", "long")
    state = engine.add_player(state, "p1", " Bob ")
    assert_rejected("capacity_exceeded", engine.add_player, state, "p2", "Cat")
    assert_rejected("invalid_payload", engine.rename_player, state, "joueur", "p1", "long")
    assert_rejected("invalid_payload", engine.add_theme, state, "longer", "presentateur")
    state = engine.add_theme(state, " Test ", "presentateur")
    assert state.themes[0].label == "Test"
    assert_rejected("capacity_exceeded", engine.add_theme, state, "Next", "presentateur")


@pytest.mark.parametrize("index", [True, False, 0.0, -1, 99, "0", None])
def test_indices_reject_coercions_and_out_of_range_values(index) -> None:
    state = lobby()
    assert_rejected("invalid_payload", engine.remove_player, state, index, "presentateur")
    assert_rejected("invalid_payload", engine.remove_theme, state, index, "presentateur")
    state = at_subphase("selection")
    assert_rejected("invalid_payload", engine.select_theme, state, index, "joueur", "bob")


def test_screen_identity_cannot_change_avatar() -> None:
    assert_rejected("forbidden_role", engine.set_player_avatar, lobby(), "screen", "alice")
