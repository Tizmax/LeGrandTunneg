import { useEffect, useState } from 'react'

type CountdownTimerProps = {
  durationSeconds?: number
}

function tierClasses(seconds: number): string {
  if (seconds <= 10) return 'text-burgundy-500 animate-blink-red'
  if (seconds <= 20) return 'text-orange-500'
  if (seconds <= 30) return 'text-amber-glow'
  return 'text-[#d8c9b0]'
}

/**
 * Chrono visuel. Pour le redémarrer (ex. nouvelle question), montez ce
 * composant avec une prop `key` différente depuis le parent — cela force
 * React à réinitialiser son état interne sans setState-in-effect.
 */
export function CountdownTimer({ durationSeconds = 60 }: CountdownTimerProps) {
  const [seconds, setSeconds] = useState(durationSeconds)

  useEffect(() => {
    if (seconds <= 0) return
    const id = setTimeout(() => setSeconds((s) => s - 1), 1000)
    return () => clearTimeout(id)
  }, [seconds])

  return (
    <div className="flex flex-col items-center gap-1">
      <span className={`font-display text-4xl font-bold tabular-nums ${tierClasses(seconds)}`}>
        {String(Math.max(seconds, 0)).padStart(2, '0')}
      </span>
      <span className="text-xs tracking-widest text-[#7a6f63] uppercase">Temps</span>
    </div>
  )
}
