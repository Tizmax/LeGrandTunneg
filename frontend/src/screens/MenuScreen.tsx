import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import type { Role } from '../net/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'
import { ArtDecoCorner } from '../components/decor/ArtDecoCorner'

type MenuScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
  role: Role
  roomCode: string
}

/**
 * Lobby de la room multi (Bloc 7) : les joueurs rejoignent eux-mêmes la room
 * via l'écran d'accueil (POST /api/rooms/{code}/join), ils n'apparaissent
 * donc plus ici via une saisie locale (contrairement à l'ancien POC hotseat
 * — voir game/gameReducer.ts, action ADD_PLAYER désormais sans effet réseau,
 * voir net/dispatchAdapter.ts). Seul le Présentateur peut retirer un
 * participant ou lancer la suite (`lobby:go_to_themes`).
 */
export function MenuScreen({ state, dispatch, role, roomCode }: MenuScreenProps) {
  const canContinue = state.players.length >= 2
  const isPresenter = role === 'presentateur'

  return (
    <ScreenShell spotlight smoke>
      <div className="flex flex-1 flex-col items-center justify-center gap-10">
        <div className="animate-rise-up text-center">
          <p className="mb-2 text-xs tracking-[0.5em] text-brass-400/80 uppercase">
            ★ Ce soir, sur scène ★
          </p>
          <h1 className="marquee-text font-display text-5xl font-black tracking-wide sm:text-7xl">
            Le Grand Tunneg
          </h1>
          <p className="mt-3 text-sm tracking-[0.3em] text-[#9a8d7d] uppercase">
            {isPresenter
              ? 'Partagez le code pour que les joueurs rejoignent'
              : 'En attente du lancement de la partie…'}
          </p>
        </div>

        <div className="string-lights animate-rise-up relative w-full max-w-md rounded-2xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800 to-charcoal-900 p-6 shadow-stage-lg">
          <ArtDecoCorner position="top-left" />
          <ArtDecoCorner position="top-right" />
          <ArtDecoCorner position="bottom-left" />
          <ArtDecoCorner position="bottom-right" />

          <div className="mb-5 flex flex-col items-center gap-1">
            <span className="text-xs tracking-[0.3em] text-[#9a8d7d] uppercase">
              Code de la room
            </span>
            <span className="font-display text-3xl font-black tracking-[0.3em] text-amber-glow">
              {roomCode}
            </span>
          </div>

          {state.players.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {state.players.map((player, i) => (
                <li
                  key={player.id}
                  className="flex items-center justify-between rounded-lg border border-white/5 bg-charcoal-900/60 px-4 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                >
                  <span className="font-display text-lg text-[#f1e6d8]">{player.name}</span>
                  {isPresenter && (
                    <button
                      onClick={() => dispatch({ type: 'REMOVE_PLAYER', index: i })}
                      className="cursor-pointer text-xs tracking-wide text-burgundy-500 uppercase transition-colors hover:text-burgundy-500/70"
                    >
                      Retirer
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-center text-xs text-[#7a6f63]">
              Aucun joueur n'a encore rejoint la room.
            </p>
          )}

          {state.players.length < 2 && (
            <p className="mt-4 text-center text-xs text-[#7a6f63]">
              Minimum 2 joueurs requis pour continuer.
            </p>
          )}
        </div>

        {isPresenter && (
          <Button
            variant="gold"
            className="animate-rise-up px-10 py-3 text-base"
            disabled={!canContinue}
            onClick={() => dispatch({ type: 'GO_TO_THEMES' })}
          >
            Continuer
          </Button>
        )}
      </div>
    </ScreenShell>
  )
}
