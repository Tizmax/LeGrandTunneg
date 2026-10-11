import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import type { Role } from '../net/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'
import { ScoreBoard } from '../components/ScoreBoard'
import { Tunnel } from '../components/Tunnel'
import { CountdownTimer } from '../components/CountdownTimer'
import { CurtainReveal } from '../components/decor/CurtainReveal'
import { RoomOverview } from '../components/RoomOverview'
import { ChoicePendingScreen } from './ChoicePendingScreen'

type TunnelScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
  role: Role
  localPlayerId: string | null
}

export function TunnelScreen({ state, dispatch, role, localPlayerId }: TunnelScreenProps) {
  const theme = state.activeThemeIndex !== null ? state.themes[state.activeThemeIndex] : null
  const currentPlayer = state.players[state.currentPlayerIndex]

  if (!theme) return null

  // Couche show : choix Continuer/Coffrer pas encore révélé par le
  // Présentateur -> écran d'attente neutre, aucune option visible.
  if (state.tunnelSubPhase === 'after-success-pending') {
    return (
      <ChoicePendingScreen state={state} dispatch={dispatch} isPresenterView={role === 'presentateur'} />
    )
  }

  const isPresenter = role === 'presentateur'
  // Seul le joueur dont c'est le tour peut voir Continuer/Coffrer — un autre
  // joueur ne reçoit que le message d'attente ci-dessous (le serveur
  // rejetterait de toute façon avec `not_your_turn`).
  const isCurrentPlayer = role === 'joueur' && currentPlayer?.id === localPlayerId

  return (
    <ScreenShell spotlight smoke>
      {/* key=activeThemeIndex : le rideau ne se lève qu'à l'entrée sur un nouveau thème */}
      <CurtainReveal key={state.activeThemeIndex}>
        <div className="flex flex-1 flex-col items-center gap-8 py-4">
          <div className="animate-rise-up flex flex-col items-center gap-3 text-center">
            <span className="text-xs tracking-[0.3em] text-[#9a8d7d] uppercase">
              {currentPlayer?.name} joue
            </span>
            <h2 className="marquee-text font-display text-3xl font-bold sm:text-4xl">
              {theme.label}
            </h2>
            <ScoreBoard players={state.players} currentPlayerIndex={state.currentPlayerIndex} />
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
              <Button variant="gold" onClick={() => dispatch({ type: 'START_TIMER' })}>
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
                <Button variant="primary" onClick={() => dispatch({ type: 'GOOD_ANSWER' })}>
                  Bonne réponse
                </Button>
                <Button variant="danger" onClick={() => dispatch({ type: 'BAD_ANSWER' })}>
                  Mauvaise réponse
                </Button>
                <Button variant="secondary" onClick={() => dispatch({ type: 'PASS' })}>
                  Passer
                </Button>
              </>
            )}

            {role === 'joueur' && state.tunnelSubPhase === 'question' && (
              <p className="text-xs tracking-wide text-[#9a8d7d] uppercase">
                Le Présentateur juge la réponse…
              </p>
            )}

            {/* Continuer / Coffrer : choix révélé (choice_open), appartient
                au seul Joueur dont c'est le tour — jamais au Présentateur ni
                aux autres joueurs. */}
            {isCurrentPlayer && state.tunnelSubPhase === 'after-success-open' && (
              <>
                <Button variant="primary" onClick={() => dispatch({ type: 'CONTINUE' })}>
                  Continuer
                </Button>
                <Button variant="gold" onClick={() => dispatch({ type: 'COFFRER' })}>
                  Coffrer
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
