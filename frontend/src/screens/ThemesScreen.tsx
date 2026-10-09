import { useState } from 'react'
import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'

type ThemesScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
}

export function ThemesScreen({ state, dispatch }: ThemesScreenProps) {
  const [label, setLabel] = useState('')

  function handleAdd() {
    if (!label.trim()) return
    dispatch({ type: 'ADD_THEME', label })
    setLabel('')
  }

  const canStart = state.themes.length >= 1

  return (
    <ScreenShell spotlight>
      <div className="flex flex-1 flex-col items-center justify-center gap-10">
        <div className="animate-rise-up text-center">
          <h1 className="font-display text-4xl font-bold text-amber-glow sm:text-5xl">
            Les thèmes secrets
          </h1>
          <p className="mt-3 text-sm tracking-[0.3em] text-[#9a8d7d] uppercase">
            Saisie à l'aveugle — personne ne doit voir l'écran
          </p>
        </div>

        <div className="animate-rise-up w-full max-w-md rounded-2xl border border-brass-600/30 bg-charcoal-900 p-6 shadow-stage">
          <div className="flex gap-2">
            <input
              type="password"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAdd()
              }}
              placeholder="Thème secret"
              maxLength={30}
              className="flex-1 rounded-lg border border-brass-600/30 bg-charcoal-800 px-4 py-2.5 text-[#f1e6d8] placeholder-[#6b625b] outline-none focus:border-amber-glow"
            />
            <Button variant="primary" onClick={handleAdd} disabled={!label.trim()}>
              Ajouter
            </Button>
          </div>

          {state.themes.length > 0 && (
            <ul className="mt-5 flex flex-col gap-2">
              {state.themes.map((theme, i) => (
                <li
                  key={i}
                  className="flex items-center justify-between rounded-lg bg-charcoal-800/70 px-4 py-2"
                >
                  <span className="font-display text-lg tracking-[0.3em] text-[#f1e6d8]">
                    {'●'.repeat(Math.min(theme.label.length, 12))}
                  </span>
                  <button
                    onClick={() => dispatch({ type: 'REMOVE_THEME', index: i })}
                    className="cursor-pointer text-xs tracking-wide text-burgundy-500 uppercase hover:text-burgundy-500/70"
                  >
                    Retirer
                  </button>
                </li>
              ))}
            </ul>
          )}

          {state.themes.length < 1 && (
            <p className="mt-4 text-center text-xs text-[#7a6f63]">
              Minimum 1 thème requis pour lancer la partie.
            </p>
          )}
        </div>

        <Button
          variant="gold"
          className="animate-rise-up px-10 py-3 text-base"
          disabled={!canStart}
          onClick={() => dispatch({ type: 'START_GAME' })}
        >
          Lancer la partie
        </Button>
      </div>
    </ScreenShell>
  )
}
