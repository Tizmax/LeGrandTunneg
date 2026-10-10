import type { ReactNode } from 'react'
import { BokehField } from './decor/BokehField'
import { SmokeWisps } from './decor/SmokeWisps'

type ScreenShellProps = {
  children: ReactNode
  spotlight?: boolean
  smoke?: boolean
  className?: string
}

/**
 * Enveloppe commune à tous les écrans : aurore chaude animée en fond,
 * bokeh de lumières floutées, grain pelliculaire, vignettage profond et
 * animation d'apparition théâtrale. Référence "Soul" / "La La Land".
 */
export function ScreenShell({
  children,
  spotlight = false,
  smoke = false,
  className = '',
}: ScreenShellProps) {
  return (
    <div
      className={`bg-aurora vignette grain-overlay relative min-h-screen w-full overflow-x-hidden bg-charcoal-950 ${spotlight ? 'spotlight' : ''} ${className}`}
    >
      <BokehField />
      {smoke && <SmokeWisps />}
      <div className="animate-screen-fade relative z-10 mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-8 sm:px-8">
        {children}
      </div>
    </div>
  )
}
