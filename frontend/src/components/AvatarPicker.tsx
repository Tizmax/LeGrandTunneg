/** Liste des avatars disponibles — synchronisée avec engine._ALLOWED_AVATARS (backend). */
export const AVATARS = [
  '🎭', '🦊', '🐸', '🦁', '🐧', '🦄',
  '🐺', '🦋', '🐲', '👻', '🤖', '🎩',
  '🧙', '🎪', '🥷', '🦅',
]

type AvatarPickerProps = {
  selected: string
  onSelect: (avatar: string) => void
}

/**
 * Grille de sélection d'icône de personnage pour le lobby.
 * Affichée dans le lobby pour chaque participant (joueur et Présentateur).
 */
export function AvatarPicker({ selected, onSelect }: AvatarPickerProps) {
  return (
    <div className="grid grid-cols-8 gap-1.5">
      {AVATARS.map((avatar) => (
        <button
          key={avatar}
          onClick={() => onSelect(avatar)}
          title={avatar}
          className={[
            'flex h-9 w-9 items-center justify-center rounded-lg text-xl transition-all',
            selected === avatar
              ? 'bg-amber-glow/20 ring-2 ring-amber-glow scale-110'
              : 'bg-charcoal-900/60 hover:bg-charcoal-800 hover:scale-105',
          ].join(' ')}
        >
          {avatar}
        </button>
      ))}
    </div>
  )
}
