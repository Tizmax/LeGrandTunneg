import type { SquareColor } from '../game/types'

/** Classes Tailwind associées à chaque couleur de case, version "pleine" (tunnel). */
export const squareFullClasses: Record<SquareColor, string> = {
  black:
    'bg-gradient-to-b from-[#1a1716] to-[#050403] border-black text-[#4a433c] shadow-[inset_0_2px_6px_rgba(0,0,0,0.8)]',
  gray: 'bg-gradient-to-b from-[#5a534c] to-[#413b35] border-[#6b625b] text-[#e8dcc8] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]',
  green:
    'bg-gradient-to-b from-emerald-400 to-emerald-700 border-emerald-800 text-[#f1e6d8] shadow-[0_0_10px_1px_rgba(16,185,129,0.65),0_0_26px_4px_rgba(16,185,129,0.35),inset_0_1px_0_rgba(255,255,255,0.3)]',
  yellow:
    'bg-gradient-to-b from-sunset-gold via-amber-glow to-amber-ember border-amber-ember text-charcoal-950 shadow-[0_0_14px_2px_rgba(255,215,122,0.8),0_0_34px_8px_rgba(232,163,61,0.5),inset_0_1px_0_rgba(255,255,255,0.5)]',
  empty:
    'bg-gradient-to-b from-charcoal-700 to-charcoal-800 border-charcoal-700 text-[#7a6f63] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
}

/** Classes Tailwind associées à chaque couleur de case, version "mini" (carte thème). */
export const squareMiniClasses: Record<SquareColor, string> = {
  black: 'bg-black',
  gray: 'bg-[#6b625b]',
  green: 'bg-emerald-500 shadow-[0_0_6px_0_rgba(16,185,129,0.6)]',
  yellow: 'bg-amber-glow shadow-[0_0_6px_0_rgba(232,163,61,0.7)]',
  empty: 'bg-charcoal-700',
}
