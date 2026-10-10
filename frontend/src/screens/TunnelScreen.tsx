import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'
import { ScoreBoard } from '../components/ScoreBoard'
import { Tunnel } from '../components/Tunnel'
import { CountdownTimer } from '../components/CountdownTimer'
import { CurtainReveal } from '../components/decor/CurtainReveal'

type TunnelScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
}

export function TunnelScreen({ state, dispatch }: TunnelScreenProps) {
  const theme = state.activeThemeIndex !== null ? state.themes[state.activeThemeIndex] : null
  const currentPlayer = state.players[state.currentPlayerIndex]

  if (!theme) return null

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

          <div className="animate-rise-up">
            <CountdownTimer
              key={`${state.activeThemeIndex}-${theme.progressValue}-${state.tunnelSubPhase}`}
            />
          </div>

          <div className="animate-rise-up flex flex-wrap justify-center gap-4 pt-2">
            {state.tunnelSubPhase === 'question' && (
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

            {state.tunnelSubPhase === 'after-success' && (
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
        </div>
      </CurtainReveal>
    </ScreenShell>
  )
}
