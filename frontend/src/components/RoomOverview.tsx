import type { Theme } from '../game/types'
import { MiniProgressBar } from './MiniProgressBar'

type RoomOverviewProps = {
  themes: Theme[]
}

/**
 * Vue d'ensemble compacte de tous les thèmes de la room (utilisée par la vue
 * Présentateur/régie) : permet de suivre l'état de chaque tunnel sans y être
 * actuellement engagé.
 */
export function RoomOverview({ themes }: RoomOverviewProps) {
  return (
    <div className="animate-rise-up w-full max-w-2xl rounded-xl border border-brass-600/25 bg-charcoal-900/60 p-4">
      <span className="mb-3 block text-center text-xs tracking-[0.3em] text-[#9a8d7d] uppercase">
        Vue d'ensemble de la room
      </span>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {themes.map((theme, i) => (
          <div key={i} className="flex flex-col gap-1.5">
            <span className="truncate text-xs font-medium text-[#d8c9b0]">
              {theme.label}
              {theme.completed && <span className="ml-1 text-[#7a6f63]">(terminé)</span>}
            </span>
            <MiniProgressBar theme={theme} />
          </div>
        ))}
      </div>
    </div>
  )
}
