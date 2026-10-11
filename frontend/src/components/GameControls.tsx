import type { GameAction } from '../game/gameReducer'
import type { Role } from '../net/types'

type GameControlsProps = {
  dispatch: React.Dispatch<GameAction>
  role: Role
  /** Quitte la room individuellement (ferme la connexion réseau, revient à
   * l'accueil) — réservé au Joueur. Le Présentateur dispose de "Terminer la
   * partie" à la place (ramène tout le monde au lobby, ne ferme rien). */
  onLeave: () => void
}

/**
 * Barre de contrôle discrète, superposée en permanence sur tous les écrans
 * de jeu (hors lobby) :
 * - Présentateur : "Terminer la partie" — met fin à la partie en cours à
 *   tout moment et ramène tout le monde au lobby (joueurs/thèmes conservés).
 * - Joueur : "Quitter la partie" — se déconnecte individuellement vers
 *   l'accueil ; les autres le voient marqué absent (son tour est sauté) et
 *   il peut rejoindre la room à nouveau plus tard pour reprendre sa place.
 * L'Écran principal n'a aucun contrôle ici.
 */
export function GameControls({ dispatch, role, onLeave }: GameControlsProps) {
  if (role === 'ecran-principal') return null

  return (
    <div className="fixed top-3 right-3 z-30 flex gap-2">
      {role === 'presentateur' && (
        <button
          onClick={() => {
            if (window.confirm('Terminer la partie et ramener tout le monde au lobby ?')) {
              dispatch({ type: 'END_GAME_EARLY' })
            }
          }}
          className="cursor-pointer rounded-full border border-burgundy-500/40 bg-charcoal-900/80 px-3 py-1.5 text-[0.65rem] tracking-wide text-burgundy-500 uppercase backdrop-blur-sm transition-colors hover:border-burgundy-500/80 hover:bg-charcoal-900"
        >
          Terminer la partie
        </button>
      )}
      {role === 'joueur' && (
        <button
          onClick={() => {
            if (window.confirm('Quitter la partie ? Vous pourrez rejoindre à nouveau avec le même code.')) {
              onLeave()
            }
          }}
          className="cursor-pointer rounded-full border border-[#d8c9b0]/25 bg-charcoal-900/80 px-3 py-1.5 text-[0.65rem] tracking-wide text-[#d8c9b0] uppercase backdrop-blur-sm transition-colors hover:border-[#d8c9b0]/60 hover:bg-charcoal-900"
        >
          Quitter la partie
        </button>
      )}
    </div>
  )
}
