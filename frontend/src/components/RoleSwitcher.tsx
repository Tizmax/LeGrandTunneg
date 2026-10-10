import type { ViewRole } from '../viewRole'

type RoleSwitcherProps = {
  role: ViewRole
  onChange: (role: ViewRole) => void
}

const labels: Record<ViewRole, string> = {
  presentateur: 'Vue Présentateur',
  joueur: 'Vue Joueur',
  'ecran-principal': 'Vue Écran principal',
}

/**
 * Sélecteur de vue LOCAL (voir src/viewRole.ts) : permet de prévisualiser les
 * 3 vues de rôle sur un seul poste, sans réseau. Barre discrète en haut de
 * l'écran, pensée pour la mise au point/démo, pas pour le joueur final.
 *
 * TEMPORAIRE : à supprimer au Bloc 7 réel au profit d'un routage réseau par
 * rôle (chaque device recevra directement le bon écran depuis le serveur).
 */
export function RoleSwitcher({ role, onChange }: RoleSwitcherProps) {
  return (
    <div className="fixed top-2 left-1/2 z-50 flex -translate-x-1/2 gap-1 rounded-full border border-brass-600/40 bg-charcoal-950/90 p-1 text-xs shadow-stage backdrop-blur-sm">
      {(Object.keys(labels) as ViewRole[]).map((r) => (
        <button
          key={r}
          onClick={() => onChange(r)}
          className={`rounded-full px-3 py-1.5 font-medium tracking-wide transition-all duration-200 ${
            role === r
              ? 'bg-gradient-to-b from-amber-glow to-amber-ember text-charcoal-950'
              : 'text-[#d8c9b0] hover:bg-white/5'
          }`}
        >
          {labels[r]}
        </button>
      ))}
    </div>
  )
}
