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
  /** ID de l'avatar actuellement sélectionné par ce participant. */
  selected: string
  /** Appelé quand l'utilisateur choisit un avatar. */
  onSelect: (avatar: string) => void
  /** Avatars déjà pris par d'autres participants (grisés, non sélectionnables). */
  takenBy?: Record<string, string> // avatarId -> nom du joueur qui le possède
}

/**
 * Grille de sélection d'avatar pour le lobby.
 * Affichée dans le lobby en colonne gauche. Les avatars déjà pris par
 * d'autres participants sont grisés (1 avatar = 1 joueur).
 */
export function AvatarPicker({ selected, onSelect, takenBy = {} }: AvatarPickerProps) {
  return (
    <div className="grid grid-cols-4 gap-2">
      {AVATARS.map((id) => {
        const isMine = selected === id
        const takenByName = takenBy[id]
        const isTakenByOther = Boolean(takenByName) && !isMine

        return (
          <button
            key={id}
            onClick={() => !isTakenByOther && onSelect(id)}
            title={isTakenByOther ? `Pris par ${takenByName}` : id}
            disabled={isTakenByOther}
            className={[
              'relative flex h-12 w-12 items-center justify-center rounded-xl overflow-hidden transition-all',
              isMine
                ? 'ring-2 ring-amber-glow scale-110 bg-amber-glow/10 shadow-[0_0_10px_rgba(232,163,61,0.3)]'
                : isTakenByOther
                  ? 'opacity-30 cursor-not-allowed grayscale'
                  : 'bg-charcoal-900/60 hover:bg-charcoal-800 hover:scale-105 cursor-pointer',
            ].join(' ')}
          >
            <img
              src={avatarUrl(id)}
              alt={id}
              className="h-full w-full object-cover"
              draggable={false}
            />
          </button>
        )
      })}
    </div>
  )
}
