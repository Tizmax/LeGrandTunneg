import { Sparkles, RotateCcw, Home } from 'lucide-react'
import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import { joueurs, currentJoueur, currentJoueurIndex } from '../game/types'
import type { Role } from '../net/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'
import { ScoreBoard } from '../components/ScoreBoard'
import { MiniProgressBar } from '../components/MiniProgressBar'
import { ArtDecoCorner } from '../components/decor/ArtDecoCorner'
import { useAudio } from '../audio/AudioContext'

type SelectionScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
  role: Role
  localPlayerId: string | null
}

/**
 * Choix du thème. Deux temps, tous deux rendus par cet écran pour que la
 * grille de thèmes (contenu informatif) reste visible en permanence — seule
 * l'interactivité change :
 * - `selection-pending` (choice_pending) : le choix n'est pas encore révélé.
 *   La grille est visible pour tout le monde mais non cliquable, même pour
 *   le joueur concerné — seul le Présentateur a un contrôle ("Lancer le
 *   choix"). Contrairement au cycle Continuer/Coffrer (voir
 *   ChoicePendingScreen), on choisit ici de montrer le contenu (les thèmes)
 *   à l'avance : ce n'est pas un suspense sur le CONTENU mais sur le DROIT
 *   d'agir, donc cacher la grille n'apporterait rien et frustrerait les
 *   joueurs qui veulent réfléchir à leur choix pendant que le Présentateur
 *   parle.
 * - `selection` (choice_open) : la sélection appartient au Joueur dont
 *   c'est le tour, pas au Présentateur ni aux autres joueurs.
 *   - Joueur concerné (players[currentPlayerIndex].id === localPlayerId) :
 *     grille cliquable (c'est son choix) — tout autre joueur la voit en
 *     lecture seule, le serveur rejetterait de toute façon avec
 *     `not_your_turn` (voir docs/websocket-protocol.md).
 *   - Présentateur : grille en lecture seule + vue d'ensemble room +
 *     actions réservées (Réinitialiser/Retour menu).
 *   - Écran principal : grille en lecture seule, aucun contrôle.
 */
export function SelectionScreen({ state, dispatch, role, localPlayerId }: SelectionScreenProps) {
  const currentPlayer = currentJoueur(state)
  const revealed = state.phase === 'selection'
  const isInteractive = revealed && role === 'joueur' && currentPlayer?.id === localPlayerId
  const { playEffect } = useAudio()

  return (
    <ScreenShell>
      <div className="flex flex-1 flex-col gap-8 py-4">
        <div className="animate-rise-up flex flex-col items-center gap-4 text-center">
          <h2 className="marquee-text font-display text-3xl font-bold sm:text-4xl">
            {currentPlayer?.name} monte sur scène
          </h2>
          <ScoreBoard players={joueurs(state)} currentPlayerIndex={currentJoueurIndex(state)} />
          {!revealed && role === 'presentateur' && (
            <Button variant="gold" onClick={() => { playEffect('reveal'); dispatch({ type: 'REVEAL_CHOICE' }) }}>
              <span className="flex items-center gap-2"><Sparkles size={16} /> Lancer le choix</span>
            </Button>
          )}
          {!revealed && role !== 'presentateur' && (
            <p className="text-xs tracking-wide text-[#9a8d7d] uppercase">
              Le Présentateur va bientôt lancer le choix…
            </p>
          )}
          {revealed && role === 'presentateur' && (
            <p className="text-xs tracking-wide text-[#9a8d7d] uppercase">
              En attente du choix du joueur
            </p>
          )}
        </div>

        <div className="animate-rise-up grid flex-1 grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {state.themes.map((theme, i) => {
            const disabled = theme.completed || !isInteractive
            const content = (
              <>
                {!theme.completed && (
                  <>
                    <ArtDecoCorner
                      position="top-left"
                      className="opacity-30 group-hover:opacity-60"
                    />
                    <ArtDecoCorner
                      position="bottom-right"
                      className="opacity-30 group-hover:opacity-60"
                    />
                  </>
                )}
                <span className="font-display text-sm font-semibold text-[#f1e6d8]">
                  {theme.label}
                  {theme.completed && (
                    <span className="ml-1 text-[0.6rem] font-normal text-[#7a6f63] uppercase">
                      (terminé)
                    </span>
                  )}
                </span>
                <MiniProgressBar theme={theme} />
              </>
            )
            const className = `group relative flex flex-col gap-2 overflow-hidden rounded-xl border p-3 text-left transition-all duration-300 ${
              theme.completed
                ? 'cursor-not-allowed border-charcoal-700 bg-charcoal-900/50 opacity-40 grayscale'
                : isInteractive
                  ? 'cursor-pointer border-brass-600/30 bg-gradient-to-b from-charcoal-800 to-charcoal-900 shadow-stage hover:-translate-y-1 hover:border-amber-glow hover:shadow-[0_14px_34px_-6px_rgba(232,163,61,0.4),0_0_30px_-8px_rgba(232,163,61,0.3)]'
                  : 'border-brass-600/20 bg-gradient-to-b from-charcoal-800/70 to-charcoal-900/70'
            }`
            return isInteractive ? (
              <button
                key={i}
                disabled={disabled}
                onClick={() => { playEffect('theme_start'); dispatch({ type: 'SELECT_THEME', index: i }) }}
                className={className}
              >
                {content}
              </button>
            ) : (
              <div key={i} className={className}>
                {content}
              </div>
            )
          })}
        </div>

        {role === 'presentateur' && (
          <div className="animate-rise-up flex justify-center gap-4 pt-4">
            <Button variant="secondary" onClick={() => dispatch({ type: 'RESET_GAME' })}>
              <span className="flex items-center gap-2"><RotateCcw size={15} /> Réinitialiser</span>
            </Button>
            <Button variant="ghost" onClick={() => dispatch({ type: 'QUIT_TO_MENU' })}>
              <span className="flex items-center gap-2"><Home size={15} /> Menu</span>
            </Button>
          </div>
        )}
      </div>
    </ScreenShell>
  )
}
