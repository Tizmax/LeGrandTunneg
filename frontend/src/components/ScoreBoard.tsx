import type { Player } from '../game/types'

type ScoreBoardProps = {
  players: Player[]
  currentPlayerIndex: number
}

export function ScoreBoard({ players, currentPlayerIndex }: ScoreBoardProps) {
  return (
    <div className="flex flex-wrap justify-center gap-3">
      {players.map((player, i) => {
        const isCurrent = i === currentPlayerIndex
        return (
          <div
            key={player.name + i}
            className={`rounded-lg border px-4 py-2 text-center transition-all duration-300 ${
              isCurrent
                ? 'border-amber-glow bg-amber-glow/10 shadow-[0_0_16px_-2px_rgba(232,163,61,0.5)]'
                : 'border-brass-600/20 bg-charcoal-800/60'
            }`}
          >
            <div
              className={`font-display text-base font-semibold ${isCurrent ? 'text-amber-glow' : 'text-[#d8c9b0]'}`}
            >
              {player.name}
            </div>
            <div className="text-xs text-[#9a8d7d]">{player.points} pts</div>
          </div>
        )
      })}
    </div>
  )
}
