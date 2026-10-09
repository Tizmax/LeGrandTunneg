import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'

type EndScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
}

const PODIUM_HEIGHTS = ['h-36', 'h-28', 'h-20'] as const
const PODIUM_LABELS = ['1er', '2e', '3e'] as const

function biggestSingleCoffrage(state: GameState) {
  if (state.history.length === 0) return null
  return state.history.reduce((best, entry) =>
    entry.pointsGained > best.pointsGained ? entry : best,
  )
}

export function EndScreen({ state, dispatch }: EndScreenProps) {
  const ranked = [...state.players].sort((a, b) => b.points - a.points)
  const podium = ranked.slice(0, 3)
  // Reorder visually: 2nd, 1st, 3rd for classic podium look
  const visualOrder =
    podium.length === 3
      ? [podium[1], podium[0], podium[2]]
      : podium.length === 2
        ? [podium[1], podium[0]]
        : podium

  const bigCoffrage = biggestSingleCoffrage(state)

  return (
    <ScreenShell spotlight>
      <div className="flex flex-1 flex-col items-center justify-center gap-10 py-8">
        <div className="animate-rise-up text-center">
          <h1 className="font-display text-5xl font-bold text-amber-glow drop-shadow-[0_0_30px_rgba(232,163,61,0.3)]">
            Partie terminée
          </h1>
          <p className="mt-3 text-sm tracking-[0.3em] text-[#9a8d7d] uppercase">
            Tous les thèmes ont été coffrés
          </p>
        </div>

        <div className="flex items-end justify-center gap-4 sm:gap-8">
          {visualOrder.map((player, i) => {
            const rankIndex = podium.indexOf(player)
            return (
              <div
                key={player.name}
                className="animate-rise-up flex flex-col items-center gap-2"
                style={{ animationDelay: `${i * 150}ms` }}
              >
                <span className="font-display text-lg font-semibold text-[#f1e6d8]">
                  {player.name}
                </span>
                <span className="text-xs text-[#9a8d7d]">{player.points} pts</span>
                <div
                  className={`flex w-24 items-start justify-center rounded-t-lg border border-brass-600/40 bg-gradient-to-b from-amber-glow/20 to-charcoal-800 pt-2 shadow-stage sm:w-32 ${PODIUM_HEIGHTS[rankIndex]}`}
                >
                  <span className="font-display text-2xl font-bold text-amber-glow">
                    {PODIUM_LABELS[rankIndex]}
                  </span>
                </div>
              </div>
            )
          })}
        </div>

        {bigCoffrage && (
          <div className="animate-rise-up rounded-xl border border-brass-600/30 bg-charcoal-900 px-6 py-4 text-center shadow-stage">
            <p className="text-xs tracking-[0.25em] text-[#9a8d7d] uppercase">
              Plus gros coffrage de la partie
            </p>
            <p className="font-display mt-1 text-xl text-[#f1e6d8]">
              {bigCoffrage.playerName} — {bigCoffrage.pointsGained} pts sur « {bigCoffrage.themeLabel} »
            </p>
          </div>
        )}

        <div className="animate-rise-up flex gap-4">
          <Button variant="secondary" onClick={() => dispatch({ type: 'RESET_GAME' })}>
            Rejouer
          </Button>
          <Button variant="ghost" onClick={() => dispatch({ type: 'QUIT_TO_MENU' })}>
            Retour au menu
          </Button>
        </div>
      </div>
    </ScreenShell>
  )
}
