import { useEffect, useRef, useState } from 'react'
import type { Theme } from '../game/types'
import { squareColor } from '../game/rules'
import { squareFullClasses } from './SquareColors'
import { ArtDecoCorner } from './decor/ArtDecoCorner'

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
    <div className="spotlight relative mx-auto w-full max-w-3xl overflow-hidden rounded-2xl border border-brass-600/40 bg-gradient-to-b from-charcoal-900 to-charcoal-950 p-6 shadow-stage-lg sm:p-10">
      <ArtDecoCorner position="top-left" />
      <ArtDecoCorner position="top-right" />
      <ArtDecoCorner position="bottom-left" />
      <ArtDecoCorner position="bottom-right" />

      {/* Spot de scène qui balaie doucement le plafond du tunnel */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-24 overflow-hidden opacity-70">
        <div className="animate-spot-sweep absolute top-0 h-full w-1/3 bg-[radial-gradient(ellipse_60%_100%_at_50%_0%,rgba(255,215,122,0.35),transparent_70%)]" />
      </div>

      <div className="relative z-10 flex items-end justify-center gap-1 sm:gap-2">
        {squares.map((k) => {
          const color = squareColor(theme, k)
          const isSeparator = k === 3 || k === 6 || k === 9
          return (
            <div key={k} className="flex items-center">
              <div className="flex flex-col items-center">
                <div
                  className={`flex h-20 w-12 flex-col items-center justify-end rounded-md border-2 pb-1.5 text-base font-bold transition-all duration-500 sm:h-32 sm:w-20 sm:text-xl ${squareFullClasses[color]} ${ignited[k] ? 'animate-square-ignite' : ''}`}
                >
                  {k}
                </div>
                {/* Reflet au sol, façon scène éclairée */}
                <div
                  className="mt-1 h-1.5 w-10 rounded-full opacity-40 blur-[3px] transition-opacity duration-500 sm:w-16"
                  style={{
                    background:
                      color === 'yellow'
                        ? 'radial-gradient(ellipse, rgba(255,215,122,0.9), transparent 75%)'
                        : color === 'green'
                          ? 'radial-gradient(ellipse, rgba(16,185,129,0.7), transparent 75%)'
                          : 'transparent',
                  }}
                />
              </div>
              {isSeparator && (
                <div className="mx-2 h-20 w-px bg-gradient-to-b from-transparent via-brass-600/40 to-transparent sm:mx-4 sm:h-28" />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
