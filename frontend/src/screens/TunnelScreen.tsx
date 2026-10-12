import { useEffect } from 'react'
import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import { joueurs, currentJoueur, currentJoueurIndex } from '../game/types'
import type { Role } from '../net/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'
import { ScoreBoard } from '../components/ScoreBoard'
import { Tunnel } from '../components/Tunnel'
import { CountdownTimer } from '../components/CountdownTimer'
import { CurtainReveal } from '../components/decor/CurtainReveal'
import { RoomOverview } from '../components/RoomOverview'
import { useAudio } from '../audio/AudioContext'

type TunnelScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
  role: Role
  localPlayerId: string | null
}

export function TunnelScreen({ state, dispatch, role, localPlayerId }: TunnelScreenProps) {
  const theme = state.activeThemeIndex !== null ? state.themes[state.activeThemeIndex] : null
  const currentPlayer = currentJoueur(state)
  const { playEffect } = useAudio()

  if (!theme) return null

  const isPresenter = role === 'presentateur'
  // Seul le joueur dont c'est le tour peut voir Continuer/Coffrer — un autre
  // joueur ne reçoit que le message d'attente ci-dessous (le serveur
  // rejetterait de toute façon avec `not_your_turn`).
  const isCurrentPlayer = role === 'joueur' && currentPlayer?.id === localPlayerId

  // ── Son d'entrée dans le tunnel (accent dramatique) ───────────────────────
  // eslint-disable-next-line react-hooks/rules-of-hooks
  useEffect(() => {
    playEffect('theme_start')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.activeThemeIndex])

  // ─── Wrappers dispatch avec effets sonores ─────────────────────────────────

  function handleStartTimer() {
    playEffect('timer_start')
    dispatch({ type: 'START_TIMER' })
  }

  function handleGoodAnswer() {
    playEffect('good_answer')
    dispatch({ type: 'GOOD_ANSWER' })
  }

  function handleBadAnswer() {
    playEffect('bad_answer')
    dispatch({ type: 'BAD_ANSWER' })
  }

  function handlePass() {
    playEffect('pass')
    dispatch({ type: 'PASS' })
  }

  function handleRevealChoice() {
    playEffect('reveal')
    dispatch({ type: 'REVEAL_CHOICE' })
  }

  function handleCoffrer() {
    playEffect('coffrage')
    dispatch({ type: 'COFFRER' })
  }

  return (
    <ScreenShell spotlight smoke>
      {/* key=activeThemeIndex : le rideau ne se lève qu'à l'entrée sur un nouveau thème */}
      <CurtainReveal key={state.activeThemeIndex}>
        <div className="flex flex-1 flex-col items-center gap-8 py-4">
          <div className="animate-rise-up flex flex-col items-center gap-3 text-center">
            <span className="text-xs tracking-[0.3em] text-[#9a8d7d] uppercase">
              {currentPlayer?.name} est sur scène
            </span>
            <h2 className="marquee-text font-display text-3xl font-bold sm:text-4xl">
              {theme.label}
            </h2>
            <ScoreBoard players={joueurs(state)} currentPlayerIndex={currentJoueurIndex(state)} />
          </div>

          <div className="animate-rise-up w-full">
            <Tunnel theme={theme} />
          </div>

          {/* Couche show : le chrono ne s'affiche/démarre qu'une fois que le
              Présentateur a fini de poser sa question (tunnelSubPhase
              'question', pas encore 'question-pending'). */}
          {state.tunnelSubPhase === 'question' && (
            <div className="animate-rise-up">
              <CountdownTimer
                key={`${state.activeThemeIndex}-${theme.progressValue}-${state.tunnelSubPhase}`}
              />
            </div>
          )}

          <div className="animate-rise-up flex flex-wrap justify-center gap-4 pt-2">
            {/* Couche show : question-pending — le Présentateur pose sa
                question à l'oral puis déclenche lui-même le chrono. */}
            {isPresenter && state.tunnelSubPhase === 'question-pending' && (
              <Button variant="gold" onClick={handleStartTimer}>
                Lancer le chrono
              </Button>
            )}

            {role === 'joueur' && state.tunnelSubPhase === 'question-pending' && (
              <p className="text-xs tracking-wide text-[#9a8d7d] uppercase">
                Écoutez la question…
              </p>
            )}

            {/* Bonne réponse / Mauvaise réponse / Passer : jugement de la
                réponse, réservé au Présentateur (lui seul connaît la bonne
                réponse) — jamais visible côté Joueur ni Écran principal. */}
            {isPresenter && state.tunnelSubPhase === 'question' && (
              <>
                <Button variant="primary" onClick={handleGoodAnswer}>
                  Bonne réponse
                </Button>
                <Button variant="danger" onClick={handleBadAnswer}>
                  Mauvaise réponse
                </Button>
                <Button variant="secondary" onClick={handlePass}>
                  Passer
                </Button>
              </>
            )}

            {role === 'joueur' && state.tunnelSubPhase === 'question' && (
              <p className="text-xs tracking-wide text-[#9a8d7d] uppercase">
                Le Présentateur juge la réponse…
              </p>
            )}

            {/* Couche show : after-success-pending — le thème/tunnel reste
                entièrement visible (principe : le temps d'attente du
                Présentateur ne doit pas changer drastiquement ce que voit
                le joueur, pour qu'il puisse faire un choix éclairé). Seul
                le bouton de révélation du Présentateur est ajouté ; les
                boutons Rester sur scène/Descendre restent masqués tant que
                le choix n'est pas ouvert. */}
            {isPresenter && state.tunnelSubPhase === 'after-success-pending' && (
              <Button variant="gold" onClick={handleRevealChoice}>
                Lancer le choix
              </Button>
            )}

            {role === 'joueur' && state.tunnelSubPhase === 'after-success-pending' && (
              <p className="text-xs tracking-wide text-[#9a8d7d] uppercase">
                {currentPlayer?.name} va décider…
              </p>
            )}

            {/* Continuer / Coffrer : choix révélé (choice_open), appartient
                au seul Joueur dont c'est le tour — jamais au Présentateur ni
                aux autres joueurs. */}
            {isCurrentPlayer && state.tunnelSubPhase === 'after-success-open' && (
              <>
                <Button variant="primary" onClick={() => dispatch({ type: 'CONTINUE' })}>
                  Rester sur scène
                </Button>
                <Button variant="gold" onClick={handleCoffrer}>
                  Descendre
                </Button>
              </>
            )}
          </div>

          {isPresenter && (
            <div className="animate-rise-up w-full">
              <RoomOverview themes={state.themes} />
            </div>
          )}
        </div>
      </CurtainReveal>
    </ScreenShell>
  )
}
