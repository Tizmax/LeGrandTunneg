import { useState } from 'react'
import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'
import { ArtDecoCorner } from '../components/decor/ArtDecoCorner'

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
    <ScreenShell spotlight smoke>
      <div className="flex flex-1 flex-col items-center justify-center gap-10">
        <div className="animate-rise-up text-center">
          <p className="mb-2 text-xs tracking-[0.5em] text-brass-400/80 uppercase">
            ★ Entracte confidentiel ★
          </p>
          <h1 className="marquee-text font-display text-4xl font-black sm:text-6xl">
            Les thèmes secrets
          </h1>
          <p className="mt-3 text-sm tracking-[0.3em] text-[#9a8d7d] uppercase">
            Saisie à l'aveugle — personne ne doit voir l'écran
          </p>
        </div>

        <div className="string-lights animate-rise-up relative w-full max-w-md rounded-2xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800 to-charcoal-900 p-6 shadow-stage-lg">
          <ArtDecoCorner position="top-left" />
          <ArtDecoCorner position="top-right" />
          <ArtDecoCorner position="bottom-left" />
          <ArtDecoCorner position="bottom-right" />
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
              className="flex-1 rounded-lg border border-brass-600/30 bg-charcoal-900/80 px-4 py-2.5 text-[#f1e6d8] placeholder-[#6b625b] shadow-[inset_0_2px_6px_rgba(0,0,0,0.4)] outline-none focus:border-amber-glow focus:shadow-[inset_0_2px_6px_rgba(0,0,0,0.4),0_0_0_3px_rgba(232,163,61,0.2)]"
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
                  className="flex items-center justify-between rounded-lg border border-white/5 bg-charcoal-900/60 px-4 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                >
                  <span className="font-display text-lg tracking-[0.3em] text-[#f1e6d8]">
                    {'●'.repeat(Math.min(theme.label.length, 12))}
                  </span>
                  <button
                    onClick={() => dispatch({ type: 'REMOVE_THEME', index: i })}
                    className="cursor-pointer text-xs tracking-wide text-burgundy-500 uppercase transition-colors hover:text-burgundy-500/70"
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
