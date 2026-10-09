import type { ReactNode } from 'react'

type ScreenShellProps = {
  children: ReactNode
  spotlight?: boolean
  className?: string
}

/**
 * Enveloppe commune à tous les écrans : fond charbon, vignettage, grain
 * subtil, et animation d'apparition théâtrale.
 */
export function ScreenShell({ children, spotlight = false, className = '' }: ScreenShellProps) {
  return (
    <div
      className={`vignette grain-overlay relative min-h-screen w-full overflow-x-hidden bg-charcoal-950 ${spotlight ? 'spotlight' : ''} ${className}`}
    >
      <div className="animate-screen-fade relative z-10 mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-8 sm:px-8">
        {children}
      </div>
    </div>
  )
}
