import { useEffect } from 'react'
import { motion } from 'framer-motion'
import type { GameAction } from '../game/gameReducer'
import type { GameState } from '../game/types'
import { joueurs } from '../game/types'
import type { Role } from '../net/types'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'
import { ArtDecoCorner } from '../components/decor/ArtDecoCorner'
import { useAudio } from '../audio/AudioContext'

type EndScreenProps = {
  state: GameState
  dispatch: React.Dispatch<GameAction>
  role: Role
}

const PODIUM_HEIGHTS = ['h-36', 'h-28', 'h-20'] as const
const PODIUM_LABELS = ['1er', '2e', '3e'] as const
const PODIUM_GLOW = [
  'shadow-[0_0_40px_-6px_rgba(255,215,122,0.7)] border-sunset-gold/70',
  'shadow-[0_0_24px_-6px_rgba(212,175,106,0.5)] border-brass-400/60',
  'shadow-[0_0_16px_-6px_rgba(169,128,63,0.4)] border-brass-600/50',
] as const

function biggestSingleCoffrage(state: GameState) {
  if (state.history.length === 0) return null
  return state.history.reduce((best, entry) =>
    entry.pointsGained > best.pointsGained ? entry : best,
  )
}

export function EndScreen({ state, dispatch, role }: EndScreenProps) {
  const ranked = [...joueurs(state)].sort((a, b) => b.points - a.points)
  const { playEffect } = useAudio()

  // Fanfare de victoire au montage de l'écran final
  useEffect(() => {
    playEffect('coffrage')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const podium = ranked.slice(0, 3)
  // Reorder visually: 2nd, 1st, 3rd for classic podium look
  const visualOrder =
    podium.length === 3
      ? [podium[1], podium[0], podium[2]]
      : podium.length === 2
        ? [podium[1], podium[0]]
        : podium

  const bigCoffrage = biggestSingleCoffrage(state)

  return (
    <ScreenShell spotlight smoke>
      <div className="flex flex-1 flex-col items-center justify-center gap-10 py-8">
        <div className="animate-rise-up text-center">
          <p className="mb-2 text-xs tracking-[0.5em] text-brass-400/80 uppercase">
            ★ Rideau final ★
          </p>
          <h1 className="marquee-text font-display text-5xl font-black sm:text-6xl">
            Partie terminée
          </h1>
          <p className="mt-3 text-sm tracking-[0.3em] text-[#9a8d7d] uppercase">
            Tous les thèmes ont été coffrés
          </p>
        </div>

        <div className="flex items-end justify-center gap-4 sm:gap-8">
          {visualOrder.map((player, i) => {
            const rankIndex = podium.indexOf(player)
            return (
              <motion.div
                key={player.name}
                className="flex flex-col items-center gap-2"
                initial={{ opacity: 0, y: 40 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  duration: 0.6,
                  delay: 0.3 + i * 0.2,
                  ease: [0.16, 1, 0.3, 1],
                }}
              >
                <span className="font-display text-lg font-semibold text-[#f1e6d8]">
                  {player.name}
                </span>
                <span className="text-xs tracking-wide text-[#9a8d7d] tabular-nums">
                  {player.points} pts
                </span>
                <div
                  className={`relative flex w-24 items-start justify-center overflow-hidden rounded-t-lg border bg-gradient-to-b from-amber-glow/25 via-charcoal-800 to-charcoal-900 pt-2 shadow-stage-lg sm:w-32 ${PODIUM_HEIGHTS[rankIndex]} ${PODIUM_GLOW[rankIndex]}`}
                >
                  <div className="pointer-events-none absolute inset-x-0 top-0 h-6 bg-gradient-to-b from-white/15 to-transparent" />
                  <span className="marquee-text font-display text-2xl font-black">
                    {PODIUM_LABELS[rankIndex]}
                  </span>
                </div>
              </motion.div>
            )
          })}
        </div>

        {bigCoffrage && (
          <div className="string-lights animate-rise-up relative rounded-xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800 to-charcoal-900 px-6 py-4 text-center shadow-stage">
            <ArtDecoCorner position="top-left" />
            <ArtDecoCorner position="top-right" />
            <p className="text-xs tracking-[0.25em] text-[#9a8d7d] uppercase">
              Plus gros coffrage de la partie
            </p>
            <p className="font-display mt-1 text-xl text-[#f1e6d8]">
              {bigCoffrage.playerName} — {bigCoffrage.pointsGained} pts sur « {bigCoffrage.themeLabel}{' '}
              »
            </p>
          </div>
        )}

        {/* Rejouer / Retour au menu : réservés au Présentateur (le serveur
            rejetterait de toute façon avec `forbidden_role` sinon). */}
        {role === 'presentateur' && (
          <div className="animate-rise-up flex gap-4">
            <Button variant="secondary" onClick={() => dispatch({ type: 'RESET_GAME' })}>
              Rejouer
            </Button>
            <Button variant="ghost" onClick={() => dispatch({ type: 'QUIT_TO_MENU' })}>
              Retour au menu
            </Button>
          </div>
        )}
      </div>
    </ScreenShell>
  )
}
