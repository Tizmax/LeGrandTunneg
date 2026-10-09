import { useState } from 'react'
import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'

type MenuScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
}

export function MenuScreen({ state, dispatch }: MenuScreenProps) {
  const [name, setName] = useState('')

  function handleAdd() {
    if (!name.trim()) return
    dispatch({ type: 'ADD_PLAYER', name })
    setName('')
  }

  const canContinue = state.players.length >= 2

  return (
    <ScreenShell spotlight>
      <div className="flex flex-1 flex-col items-center justify-center gap-10">
        <div className="animate-rise-up text-center">
          <h1 className="font-display text-5xl font-bold tracking-wide text-amber-glow drop-shadow-[0_0_30px_rgba(232,163,61,0.3)] sm:text-6xl">
            Le Grand Tunneg
          </h1>
          <p className="mt-3 text-sm tracking-[0.3em] text-[#9a8d7d] uppercase">
            Ajoutez les joueurs pour commencer
          </p>
        </div>

        <div className="animate-rise-up w-full max-w-md rounded-2xl border border-brass-600/30 bg-charcoal-900 p-6 shadow-stage">
          <div className="flex gap-2">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAdd()
              }}
              placeholder="Nom du joueur"
              maxLength={24}
              className="flex-1 rounded-lg border border-brass-600/30 bg-charcoal-800 px-4 py-2.5 text-[#f1e6d8] placeholder-[#6b625b] outline-none focus:border-amber-glow"
            />
            <Button variant="primary" onClick={handleAdd} disabled={!name.trim()}>
              Ajouter
            </Button>
          </div>

          {state.players.length > 0 && (
            <ul className="mt-5 flex flex-col gap-2">
              {state.players.map((player, i) => (
                <li
                  key={player.name + i}
                  className="flex items-center justify-between rounded-lg bg-charcoal-800/70 px-4 py-2"
                >
                  <span className="font-display text-lg text-[#f1e6d8]">{player.name}</span>
                  <button
                    onClick={() => dispatch({ type: 'REMOVE_PLAYER', index: i })}
                    className="cursor-pointer text-xs tracking-wide text-burgundy-500 uppercase hover:text-burgundy-500/70"
                  >
                    Retirer
                  </button>
                </li>
              ))}
            </ul>
          )}

          {state.players.length < 2 && (
            <p className="mt-4 text-center text-xs text-[#7a6f63]">
              Minimum 2 joueurs requis pour continuer.
            </p>
          )}
        </div>

        <Button
          variant="gold"
          className="animate-rise-up px-10 py-3 text-base"
          disabled={!canContinue}
          onClick={() => dispatch({ type: 'GO_TO_THEMES' })}
        >
          Continuer
        </Button>
      </div>
    </ScreenShell>
  )
}
