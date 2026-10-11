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
 * Écran de suspense réduit affiché pendant choice_pending du cycle
 * Rester sur scène / Descendre : un Présentateur humain parle déjà à l'oral,
 * donc pas de texte explicatif superflu ici — juste le nom du joueur
 * concerné, un signe d'attente discret, et le contrôle du Présentateur.
 * (La sélection de thème, elle, reste visible en permanence sur
 * SelectionScreen — voir ce fichier pour le choix de design équivalent.)
 */
export function ChoicePendingScreen({ state, dispatch, isPresenterView }: ChoicePendingScreenProps) {
  const currentPlayer = state.players[state.currentPlayerIndex]

  return (
    <ScreenShell spotlight smoke>
      <div className="flex flex-1 flex-col items-center justify-center gap-10 py-4 text-center">
        <div className="animate-rise-up relative flex flex-col items-center gap-4 rounded-2xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800/80 to-charcoal-900/80 px-8 py-10 shadow-stage-lg sm:px-14">
          <ArtDecoCorner position="top-left" className="opacity-40" />
          <ArtDecoCorner position="top-right" className="opacity-40" />
          <ArtDecoCorner position="bottom-left" className="opacity-40" />
          <ArtDecoCorner position="bottom-right" className="opacity-40" />

          <h2 className="marquee-text font-display text-2xl font-bold sm:text-3xl">
            {currentPlayer?.name} va décider…
          </h2>

          <div className="mt-2 flex gap-2" aria-hidden="true">
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
