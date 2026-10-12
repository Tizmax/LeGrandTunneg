import { useEffect, useState } from 'react'
import { useAudio } from '../audio/AudioContext'

type CountdownTimerProps = {
  durationSeconds?: number
}

function tierClasses(seconds: number): string {
  if (seconds <= 10) return 'text-burgundy-500 animate-blink-red drop-shadow-[0_0_14px_rgba(138,34,50,0.7)]'
  if (seconds <= 20) return 'text-orange-500 drop-shadow-[0_0_10px_rgba(249,115,22,0.5)]'
  if (seconds <= 30) return 'text-amber-glow drop-shadow-[0_0_10px_rgba(232,163,61,0.5)]'
  return 'text-[#d8c9b0]'
}

/** Urgence audio : 0 = normal, 1 = très urgent (palier rouge ≤10 s). */
function tickUrgency(seconds: number): 0 | 1 {
  return seconds <= 10 ? 1 : 0
}

/**
 * Chrono visuel avec tic-tac audio.
 * Pour le redémarrer (ex. nouvelle question), montez ce composant avec une
 * prop `key` différente depuis le parent — cela force React à réinitialiser
 * son état interne sans setState-in-effect.
 *
 * Le tic-tac est joué à chaque seconde via useAudio().playEffect. Il est
 * silencieux si l'utilisateur a coupé le son.
 * Paliers audio :
 *   > 10 s  → 'tick'         (tic normal)
 *   ≤ 10 s  → 'tick_urgent'  (tic plus aigu, plus présent)
 */
export function CountdownTimer({ durationSeconds = 60 }: CountdownTimerProps) {
  const [seconds, setSeconds] = useState(durationSeconds)
  const { playEffect } = useAudio()

  useEffect(() => {
    if (seconds <= 0) return
    const id = setTimeout(() => {
      setSeconds((s) => s - 1)
    }, 1000)
    return () => clearTimeout(id)
  }, [seconds])

  // Tic-tac : joué à chaque décrément (sauf à 0)
  useEffect(() => {
    if (seconds <= 0 || seconds === durationSeconds) return
    const urgency = tickUrgency(seconds)
    playEffect(urgency === 1 ? 'tick_urgent' : 'tick')
  // On veut jouer le son à chaque changement de `seconds` uniquement.
  // playEffect est stable (useCallback), durationSeconds ne change pas.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seconds])

  return (
    <div className="relative flex flex-col items-center gap-1 rounded-full border border-brass-600/30 bg-gradient-to-b from-charcoal-900 to-charcoal-950 px-6 py-3 shadow-[inset_0_2px_6px_rgba(0,0,0,0.5),0_4px_16px_-4px_rgba(0,0,0,0.6)]">
      <span className={`font-display text-4xl font-bold tabular-nums ${tierClasses(seconds)}`}>
        {String(Math.max(seconds, 0)).padStart(2, '0')}
      </span>
      <span className="text-xs tracking-widest text-[#7a6f63] uppercase">Temps</span>
    </div>
  )
}
