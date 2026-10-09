import { useEffect, useRef, useState } from 'react'
import type { Theme } from '../game/types'
import { squareColor } from '../game/rules'
import { squareFullClasses } from './SquareColors'

type TunnelProps = {
  theme: Theme
}

export function Tunnel({ theme }: TunnelProps) {
  const squares = Array.from({ length: 10 }, (_, i) => i + 1)
  const prevColors = useRef<Record<number, string>>({})
  const [ignited, setIgnited] = useState<Record<number, boolean>>({})

  useEffect(() => {
    const changed: Record<number, boolean> = {}
    for (const k of squares) {
      const color = squareColor(theme, k)
      if (prevColors.current[k] !== undefined && prevColors.current[k] !== color) {
        changed[k] = true
      }
      prevColors.current[k] = color
    }
    if (Object.keys(changed).length > 0) {
      setIgnited(changed)
      const t = setTimeout(() => setIgnited({}), 650)
      return () => clearTimeout(t)
    }
    // squares is a stable constant array, safe to omit from deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme.progressValue, theme.validatedSquares, theme.discovered, theme.nullified.length])

  return (
    <div className="spotlight relative mx-auto w-full max-w-3xl rounded-2xl border border-brass-600/30 bg-charcoal-900 p-6 shadow-stage sm:p-10">
      <div className="relative z-10 flex items-end justify-center gap-1 sm:gap-2">
        {squares.map((k) => {
          const color = squareColor(theme, k)
          const isSeparator = k === 3 || k === 6 || k === 9
          return (
            <div key={k} className="flex items-center">
              <div
                className={`flex h-16 w-10 flex-col items-center justify-end rounded-md border-2 pb-1.5 text-sm font-bold transition-all duration-500 sm:h-24 sm:w-14 sm:text-base ${squareFullClasses[color]} ${ignited[k] ? 'animate-square-ignite' : ''}`}
              >
                {k}
              </div>
              {isSeparator && <div className="mx-2 h-20 w-px bg-brass-600/30 sm:mx-4 sm:h-28" />}
            </div>
          )
        })}
      </div>
    </div>
  )
}
