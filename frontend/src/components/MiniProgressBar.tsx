import type { Theme } from '../game/types'
import { squareColor } from '../game/rules'
import { squareMiniClasses } from './SquareColors'

type MiniProgressBarProps = {
  theme: Theme
}

export function MiniProgressBar({ theme }: MiniProgressBarProps) {
  const squares = Array.from({ length: 10 }, (_, i) => i + 1)
  return (
    <div className="flex gap-0.5">
      {squares.map((k) => (
        <div
          key={k}
          className={`h-2 flex-1 rounded-[2px] transition-colors duration-500 ${squareMiniClasses[squareColor(theme, k)]} ${k === 3 || k === 6 || k === 9 ? 'mr-1' : ''}`}
        />
      ))}
    </div>
  )
}
