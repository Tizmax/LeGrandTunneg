import type { SquareColor } from '../game/types'

/** Classes Tailwind associées à chaque couleur de case, version "pleine" (tunnel). */
export const squareFullClasses: Record<SquareColor, string> = {
  black: 'bg-[#0a0908] border-[#000] text-[#555]',
  gray: 'bg-[#4a4440] border-[#6b625b] text-[#d8c9b0]',
  green: 'bg-gradient-to-b from-emerald-500 to-emerald-700 border-emerald-800 text-[#f1e6d8] shadow-[0_0_18px_-2px_rgba(16,185,129,0.6)]',
  yellow:
    'bg-gradient-to-b from-amber-glow to-amber-dim border-amber-ember text-charcoal-950 shadow-[0_0_24px_0px_rgba(232,163,61,0.75)]',
  empty: 'bg-charcoal-800 border-charcoal-700 text-[#7a6f63]',
}

/** Classes Tailwind associées à chaque couleur de case, version "mini" (carte thème). */
export const squareMiniClasses: Record<SquareColor, string> = {
  black: 'bg-black',
  gray: 'bg-[#6b625b]',
  green: 'bg-emerald-600',
  yellow: 'bg-amber-glow',
  empty: 'bg-charcoal-700',
}
