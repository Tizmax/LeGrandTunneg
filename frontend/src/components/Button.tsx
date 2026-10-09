import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'gold'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  children: ReactNode
}

const variantClasses: Record<Variant, string> = {
  primary:
    'bg-gradient-to-b from-amber-glow to-amber-ember text-charcoal-950 font-semibold shadow-[0_6px_18px_-4px_rgba(232,163,61,0.55)] hover:brightness-110 active:brightness-95',
  secondary:
    'bg-charcoal-800 text-brass-400 border border-brass-600/50 hover:bg-charcoal-700 hover:border-brass-400',
  danger:
    'bg-burgundy-700 text-[#f1e6d8] border border-burgundy-500/60 hover:bg-burgundy-500',
  ghost: 'bg-transparent text-[#d8c9b0] border border-[#d8c9b0]/25 hover:border-[#d8c9b0]/60',
  gold: 'bg-gradient-to-b from-brass-400 to-brass-600 text-charcoal-950 font-semibold hover:brightness-110',
}

export function Button({ variant = 'primary', className = '', children, ...rest }: ButtonProps) {
  return (
    <button
      className={`cursor-pointer rounded-lg px-5 py-2.5 text-sm tracking-wide transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-35 disabled:grayscale ${variantClasses[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
