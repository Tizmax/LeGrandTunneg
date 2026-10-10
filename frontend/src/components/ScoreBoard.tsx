import type { Player } from '../game/types'

type ScoreBoardProps = {
  players: Player[]
  currentPlayerIndex: number
}

/** Tableau de scores façon ardoise de club vintage, avec pion lumineux sur le joueur actif. */
export function ScoreBoard({ players, currentPlayerIndex }: ScoreBoardProps) {
  return (
    <div className="flex flex-wrap justify-center gap-3">
      {players.map((player, i) => {
        const isCurrent = i === currentPlayerIndex
        return (
          <div
            key={player.name + i}
            className={`relative rounded-lg border px-4 py-2 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_3px_10px_-4px_rgba(0,0,0,0.6)] transition-all duration-300 ${
              isCurrent
                ? 'border-amber-glow bg-gradient-to-b from-amber-glow/15 to-charcoal-900 shadow-[0_0_20px_-2px_rgba(232,163,61,0.6),inset_0_1px_0_rgba(255,255,255,0.1)]'
                : 'border-brass-600/25 bg-gradient-to-b from-charcoal-800/80 to-charcoal-900/60'
            }`}
          >
            {isCurrent && (
              <span className="animate-glow-pulse absolute -top-1.5 -right-1.5 h-3 w-3 rounded-full bg-amber-glow" />
            )}
            <div
              className={`font-display text-base font-semibold ${isCurrent ? 'text-amber-glow drop-shadow-[0_0_6px_rgba(232,163,61,0.5)]' : 'text-[#d8c9b0]'}`}
            >
              {player.name}
            </div>
            <div className="text-xs tracking-wide text-[#9a8d7d] tabular-nums">
              {player.points} pts
            </div>
          </div>
        )
      })}
    </div>
  )
}
