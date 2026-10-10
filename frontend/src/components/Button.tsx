import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'gold'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  children: ReactNode
}

const variantClasses: Record<Variant, string> = {
  primary:
    'bg-gradient-to-b from-amber-glow via-amber-dim to-amber-ember text-charcoal-950 font-semibold border border-amber-glow/40 shadow-[0_8px_22px_-4px_rgba(232,163,61,0.6),inset_0_1px_0_rgba(255,255,255,0.35)] hover:brightness-110 hover:shadow-[0_10px_30px_-4px_rgba(232,163,61,0.85),0_0_26px_4px_rgba(255,180,90,0.45),inset_0_1px_0_rgba(255,255,255,0.4)] active:translate-y-0.5 active:shadow-[0_3px_10px_-2px_rgba(232,163,61,0.5),inset_0_2px_4px_rgba(0,0,0,0.3)]',
  secondary:
    'bg-gradient-to-b from-charcoal-700 to-charcoal-900 text-brass-400 border border-brass-600/50 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] hover:border-brass-400 hover:shadow-[0_0_18px_-4px_rgba(212,175,106,0.5),inset_0_1px_0_rgba(255,255,255,0.1)] active:translate-y-0.5',
  danger:
    'bg-gradient-to-b from-burgundy-500 to-burgundy-900 text-[#f8ece0] border border-burgundy-500/70 shadow-[0_6px_18px_-4px_rgba(138,34,50,0.6),inset_0_1px_0_rgba(255,255,255,0.15)] hover:brightness-110 hover:shadow-[0_8px_24px_-4px_rgba(138,34,50,0.85),0_0_20px_2px_rgba(138,34,50,0.4)] active:translate-y-0.5',
  ghost:
    'bg-transparent text-[#d8c9b0] border border-[#d8c9b0]/25 hover:border-[#d8c9b0]/70 hover:bg-white/5 hover:shadow-[0_0_14px_-4px_rgba(216,201,176,0.4)] active:translate-y-0.5',
  gold: 'bg-gradient-to-b from-sunset-gold via-brass-400 to-brass-600 text-charcoal-950 font-semibold border border-brass-400/50 shadow-[0_8px_22px_-4px_rgba(212,175,106,0.6),inset_0_1px_0_rgba(255,255,255,0.4)] hover:brightness-110 hover:shadow-[0_10px_28px_-4px_rgba(255,215,122,0.8),0_0_26px_4px_rgba(255,215,122,0.4)] active:translate-y-0.5',
}

export function Button({ variant = 'primary', className = '', children, ...rest }: ButtonProps) {
  return (
    <button
      className={`relative inline-flex cursor-pointer items-center justify-center rounded-lg px-5 py-2.5 text-sm font-medium tracking-wide transition-all duration-200 ease-out disabled:cursor-not-allowed disabled:opacity-35 disabled:grayscale disabled:shadow-none disabled:hover:brightness-100 ${variantClasses[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
