import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'
import { ScoreBoard } from '../components/ScoreBoard'
import { MiniProgressBar } from '../components/MiniProgressBar'

type SelectionScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
}

export function SelectionScreen({ state, dispatch }: SelectionScreenProps) {
  const currentPlayer = state.players[state.currentPlayerIndex]

  return (
    <ScreenShell>
      <div className="flex flex-1 flex-col gap-8 py-4">
        <div className="animate-rise-up flex flex-col items-center gap-4 text-center">
          <h2 className="font-display text-3xl font-bold text-amber-glow sm:text-4xl">
            Tour de {currentPlayer?.name}
          </h2>
          <ScoreBoard players={state.players} currentPlayerIndex={state.currentPlayerIndex} />
        </div>

        <div className="animate-rise-up grid flex-1 grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {state.themes.map((theme, i) => (
            <button
              key={i}
              disabled={theme.completed}
              onClick={() => dispatch({ type: 'SELECT_THEME', index: i })}
              className={`group flex flex-col gap-4 rounded-xl border p-5 text-left transition-all duration-300 ${
                theme.completed
                  ? 'cursor-not-allowed border-charcoal-700 bg-charcoal-900/50 opacity-40 grayscale'
                  : 'cursor-pointer border-brass-600/30 bg-charcoal-900 shadow-stage hover:-translate-y-1 hover:border-amber-glow hover:shadow-[0_10px_30px_-5px_rgba(232,163,61,0.3)]'
              }`}
            >
              <span className="font-display text-xl font-semibold text-[#f1e6d8]">
                {theme.label}
                {theme.completed && (
                  <span className="ml-2 text-xs font-normal text-[#7a6f63] uppercase">
                    (terminé)
                  </span>
                )}
              </span>
              <MiniProgressBar theme={theme} />
            </button>
          ))}
        </div>

        <div className="animate-rise-up flex justify-center gap-4 pt-4">
          <Button variant="secondary" onClick={() => dispatch({ type: 'RESET_GAME' })}>
            Réinitialiser la partie
          </Button>
          <Button variant="ghost" onClick={() => dispatch({ type: 'QUIT_TO_MENU' })}>
            Retour au menu
          </Button>
        </div>
      </div>
    </ScreenShell>
  )
}
