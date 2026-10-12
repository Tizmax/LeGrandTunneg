/**
 * Liste des IDs d'avatars — synchronisée avec engine._ALLOWED_AVATARS (backend).
 * Chaque ID correspond à un SVG dans /public/avatars/{id}.svg
 * (DiceBear Lorelei, seeds fixes, licence CC0).
 */
export const AVATARS = [
  'alice', 'bob', 'charlie', 'diana', 'edgar', 'flora',
  'gareth', 'hannah', 'ivan', 'julia', 'kevin', 'luna',
  'marco', 'nina', 'oscar', 'petra',
]

/** Retourne l'URL publique du SVG pour un ID d'avatar. */
export function avatarUrl(id: string): string {
  return `/avatars/${id}.svg`
}

type AvatarPickerProps = {
  selected: string
  onSelect: (avatar: string) => void
}

/**
 * Grille de sélection d'avatar pour le lobby.
 * Affichée dans le lobby pour chaque participant (joueur et Présentateur).
 */
export function AvatarPicker({ selected, onSelect }: AvatarPickerProps) {
  return (
    <div className="grid grid-cols-8 gap-1.5">
      {AVATARS.map((id) => (
        <button
          key={id}
          onClick={() => onSelect(id)}
          title={id}
          className={[
            'flex h-10 w-10 items-center justify-center rounded-lg overflow-hidden transition-all',
            selected === id
              ? 'ring-2 ring-amber-glow scale-110 bg-amber-glow/10'
              : 'bg-charcoal-900/60 hover:bg-charcoal-800 hover:scale-105',
          ].join(' ')}
        >
          <img
            src={avatarUrl(id)}
            alt={id}
            className="h-full w-full object-cover"
            draggable={false}
          />
        </button>
      ))}
    </div>
  )
}
