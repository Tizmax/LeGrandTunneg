import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import { ScreenShell } from '../components/ScreenShell'
import { ScoreBoard } from '../components/ScoreBoard'
import { Button } from '../components/Button'
import { ArtDecoCorner } from '../components/decor/ArtDecoCorner'

type ChoicePendingScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
  /** Vue courante : seule la vue Présentateur peut déclencher la révélation. */
  isPresenterView: boolean
}

/**
 * Écran de suspense neutre affiché pendant choice_pending : un choix joueur
 * (sélection de thème, ou Continuer/Coffrer) est éligible mais pas encore
 * révélé. Aucune option, aucun bouton désactivé/grisé — uniquement une
 * attente théâtrale, le temps que le Présentateur lance le choix.
 */
export function ChoicePendingScreen({ state, dispatch, isPresenterView }: ChoicePendingScreenProps) {
  const currentPlayer = state.players[state.currentPlayerIndex]
  const isThemeChoice = state.phase === 'selection-pending'

  return (
    <ScreenShell spotlight smoke>
      <div className="flex flex-1 flex-col items-center justify-center gap-10 py-4 text-center">
        <div className="animate-rise-up relative flex flex-col items-center gap-4 rounded-2xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800/80 to-charcoal-900/80 px-8 py-10 shadow-stage-lg sm:px-14">
          <ArtDecoCorner position="top-left" className="opacity-40" />
          <ArtDecoCorner position="top-right" className="opacity-40" />
          <ArtDecoCorner position="bottom-left" className="opacity-40" />
          <ArtDecoCorner position="bottom-right" className="opacity-40" />

          <span className="text-xs tracking-[0.35em] text-[#9a8d7d] uppercase">
            Suspense en régie
          </span>
          <h2 className="marquee-text font-display text-2xl font-bold sm:text-3xl">
            {isThemeChoice
              ? `${currentPlayer?.name}, votre thème vous attend…`
              : `${currentPlayer?.name}, un choix décisif approche…`}
          </h2>
          <p className="max-w-md text-sm text-[#d8c9b0]">
            Le Présentateur va bientôt vous donner la parole. Patientez, les
            projecteurs se préparent.
          </p>

          <div className="mt-4 flex gap-2" aria-hidden="true">
            <span className="h-2 w-2 animate-pulse rounded-full bg-amber-glow" />
            <span className="h-2 w-2 animate-pulse rounded-full bg-amber-glow [animation-delay:150ms]" />
            <span className="h-2 w-2 animate-pulse rounded-full bg-amber-glow [animation-delay:300ms]" />
          </div>
        </div>

        <div className="animate-rise-up">
          <ScoreBoard players={state.players} currentPlayerIndex={state.currentPlayerIndex} />
        </div>

        {isPresenterView && (
          <div className="animate-rise-up">
            <Button variant="gold" onClick={() => dispatch({ type: 'REVEAL_CHOICE' })}>
              Lancer le choix
            </Button>
          </div>
        )}
      </div>
    </ScreenShell>
  )
}
