import type { Player } from '../game/types'

type ScoreBoardProps = {
  players: Player[]
  currentPlayerIndex: number
}

/**
 * Tableau de scores façon scénographie de cabaret : le joueur « sur scène »
 * (actif) est mis en avant au centre, flanqué de deux groupes selon le sens
 * de circulation du public dans une salle de théâtre :
 * - Côté COUR (gauche) : les joueurs déjà passés ce tour-ci, du plus ancien
 *   (à l'extrémité gauche) au plus récent (juste avant la scène).
 * - Côté JARDIN (droite) : les prochains joueurs, du plus proche (juste
 *   après la scène) au plus lointain (à l'extrémité droite).
 * L'ordre de jeu réel (`currentPlayerIndex`) n'est jamais modifié par
 * l'affichage — un joueur absent (`connected: false`, déconnecté mais pas
 * retiré de la partie) garde sa place dans la rotation, simplement estompé.
 */
export function ScoreBoard({ players, currentPlayerIndex }: ScoreBoardProps) {
  const count = players.length
  if (count === 0) return null

  // Reconstruit l'ordre de passage à partir du joueur actif, en partageant
  // les `count - 1` autres joueurs en deux moitiés DISJOINTES (pas de
  // duplication si le nombre de joueurs est impair). Si le nombre de
  // joueurs est pair, le joueur diamétralement opposé au joueur actif est
  // équidistant dans les deux sens : il apparaît alors une fois à chaque
  // extrémité pour équilibrer visuellement l'affichage (comportement
  // explicitement voulu, pas un bug).
  const otherCount = count - 1
  const half = Math.ceil(otherCount / 2)
  const before: number[] = []
  const after: number[] = []
  for (let step = 1; step <= half; step++) {
    before.push((currentPlayerIndex - step + count) % count)
    after.push((currentPlayerIndex + step) % count)
  }
  // Affichage gauche->droite : le plus ancien passage à l'extrémité gauche,
  // le plus récent juste avant la scène.
  const cour = [...before].reverse()
  const jardin = after

  function renderCard(index: number, variant: 'active' | 'muted', slot: string) {
    const player = players[index]
    const isActive = variant === 'active'
    return (
      <div
        key={`${player.id}-${slot}`}
        className={`relative rounded-lg border text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_3px_10px_-4px_rgba(0,0,0,0.6)] transition-all duration-300 ${
          isActive
            ? 'border-amber-glow bg-gradient-to-b from-amber-glow/15 to-charcoal-900 px-5 py-3 shadow-[0_0_20px_-2px_rgba(232,163,61,0.6),inset_0_1px_0_rgba(255,255,255,0.1)]'
            : 'border-brass-600/25 bg-gradient-to-b from-charcoal-800/80 to-charcoal-900/60 px-3 py-1.5'
        } ${!player.connected ? 'opacity-40 grayscale' : ''}`}
      >
        {isActive && (
          <span className="animate-glow-pulse absolute -top-1.5 -right-1.5 h-3 w-3 rounded-full bg-amber-glow" />
        )}
        <div
          className={`font-display font-semibold ${
            isActive
              ? 'text-base text-amber-glow drop-shadow-[0_0_6px_rgba(232,163,61,0.5)]'
              : 'text-sm text-[#d8c9b0]'
          }`}
        >
          {player.name}
          {!player.connected && (
            <span className="ml-1.5 text-[0.6rem] font-normal tracking-wide text-[#7a6f63] uppercase">
              (parti)
            </span>
          )}
        </div>
        <div className="text-xs tracking-wide text-[#9a8d7d] tabular-nums">
          {player.points} pts
        </div>
      </div>
    )
  }

  return (
    <div className="flex w-full flex-wrap items-center justify-center gap-5">
      {cour.length > 0 && (
        <div className="flex flex-col items-center gap-1.5">
          <span className="text-[0.6rem] tracking-[0.3em] text-[#7a6f63] uppercase">Cour</span>
          <div className="flex flex-wrap justify-end gap-2">
            {cour.map((i, idx) => renderCard(i, 'muted', `cour-${idx}`))}
          </div>
        </div>
      )}

      <div className="flex flex-col items-center gap-1.5">
        <span className="text-[0.6rem] tracking-[0.3em] text-amber-glow/80 uppercase">
          Sur scène
        </span>
        {renderCard(currentPlayerIndex, 'active', 'scene')}
      </div>

      {jardin.length > 0 && (
        <div className="flex flex-col items-center gap-1.5">
          <span className="text-[0.6rem] tracking-[0.3em] text-[#7a6f63] uppercase">Jardin</span>
          <div className="flex flex-wrap justify-start gap-2">
            {jardin.map((i, idx) => renderCard(i, 'muted', `jardin-${idx}`))}
          </div>
        </div>
      )}
    </div>
  )
}
