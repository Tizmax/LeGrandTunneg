import { useState, useRef, useEffect } from 'react'
import { Settings, RotateCcw, Home, Flag, LogOut } from 'lucide-react'
import type { GameAction } from '../game/gameReducer'
import type { Role } from '../net/types'

type GameControlsProps = {
  dispatch: React.Dispatch<GameAction>
  role: Role
  /** Quitte la room individuellement (ferme la connexion réseau, revient à
   * l'accueil) — réservé au Joueur. Le Présentateur dispose du menu settings
   * à la place (ramène tout le monde au lobby, ne ferme rien). */
  onLeave: () => void
}

/**
 * Barre de contrôle discrète, superposée en permanence sur tous les écrans
 * de jeu (hors lobby) :
 * - Présentateur : icône ⚙ ouvre un menu déroulant avec Réinitialiser /
 *   Retour menu / Terminer la partie.
 * - Joueur : icône porte (quitter individuellement).
 * L'Écran principal n'a aucun contrôle ici.
 */
export function GameControls({ dispatch, role, onLeave }: GameControlsProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Fermer le menu si clic extérieur
  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  if (role === 'ecran-principal') return null

  return (
    <div ref={ref} className="fixed top-3 right-3 z-30">
      {/* ── Présentateur : bouton settings → menu déroulant ───────────── */}
      {role === 'presentateur' && (
        <>
          <button
            title="Paramètres de la partie"
            onClick={() => setOpen((v) => !v)}
            className={[
              'flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border backdrop-blur-sm transition-all',
              open
                ? 'border-amber-glow/60 bg-charcoal-900 text-amber-glow'
                : 'border-white/15 bg-charcoal-900/70 text-[#9a8d7d] hover:border-white/35 hover:text-[#d8c9b0]',
            ].join(' ')}
          >
            <Settings size={16} />
          </button>

          {open && (
            <div className="absolute right-0 mt-2 w-52 overflow-hidden rounded-xl border border-white/10 bg-charcoal-900/95 shadow-stage-lg backdrop-blur-sm">
              <div className="px-3 py-2">
                <p className="text-[10px] tracking-[0.25em] text-[#7a6f63] uppercase">Partie en cours</p>
              </div>
              <div className="flex flex-col">
                <MenuAction
                  icon={<RotateCcw size={14} />}
                  label="Réinitialiser"
                  description="Remet tous les scores à zéro"
                  color="text-[#d8c9b0]"
                  onClick={() => {
                    setOpen(false)
                    if (window.confirm('Réinitialiser la partie ? Les scores seront remis à zéro.')) {
                      dispatch({ type: 'RESET_GAME' })
                    }
                  }}
                />
                <MenuAction
                  icon={<Home size={14} />}
                  label="Retour au menu"
                  description="Revenir à l'accueil"
                  color="text-[#d8c9b0]"
                  onClick={() => {
                    setOpen(false)
                    if (window.confirm('Retourner au menu principal ?')) {
                      dispatch({ type: 'QUIT_TO_MENU' })
                    }
                  }}
                />
                <div className="mx-3 my-1 border-t border-white/8" />
                <MenuAction
                  icon={<Flag size={14} />}
                  label="Terminer la partie"
                  description="Ramène tout le monde au lobby"
                  color="text-burgundy-400"
                  onClick={() => {
                    setOpen(false)
                    if (window.confirm('Terminer la partie et ramener tout le monde au lobby ?')) {
                      dispatch({ type: 'END_GAME_EARLY' })
                    }
                  }}
                />
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Joueur : icône quitter ─────────────────────────────────────── */}
      {role === 'joueur' && (
        <button
          title="Quitter la partie"
          onClick={() => {
            if (window.confirm('Quitter la partie ? Vous pourrez rejoindre à nouveau avec le même code.')) {
              onLeave()
            }
          }}
          className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border border-white/15 bg-charcoal-900/70 text-[#9a8d7d] backdrop-blur-sm transition-all hover:border-white/35 hover:text-[#d8c9b0]"
        >
          <LogOut size={16} />
        </button>
      )}
    </div>
  )
}

// ─── Item du menu déroulant ────────────────────────────────────────────────────

type MenuActionProps = {
  icon: React.ReactNode
  label: string
  description: string
  color: string
  onClick: () => void
}

function MenuAction({ icon, label, description, color, onClick }: MenuActionProps) {
  return (
    <button
      onClick={onClick}
      className={[
        'flex w-full cursor-pointer items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-white/5',
        color,
      ].join(' ')}
    >
      <span className="shrink-0 opacity-70">{icon}</span>
      <div className="min-w-0">
        <p className="text-sm font-medium leading-tight">{label}</p>
        <p className="text-[10px] text-[#7a6f63]">{description}</p>
      </div>
    </button>
  )
}
