/**
 * Bloc 8 — Contexte React audio global
 *
 * Fournit l'état mute/volume à toute l'application et expose les fonctions
 * utilitaires (playEffect, startAmbient, stopAmbient). Les préférences sont
 * persistées dans localStorage.
 *
 * Usage :
 *   // Dans App.tsx (wrapping) :
 *   <AudioProvider><App /></AudioProvider>
 *
 *   // Dans un composant :
 *   const { playEffect, muted, setMuted } = useAudio()
 *   playEffect('good_answer')
 */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import {
  resumeAudioContext,
  playGoodAnswer,
  playBadAnswer,
  playCoffrage,
  playPass,
  playTick,
  playTimerStart,
  playReveal,
  playThemeStart,
  startAmbientJazz,
} from './sounds'

// ─── Types ────────────────────────────────────────────────────────────────────

export type SoundEffect =
  | 'good_answer'
  | 'bad_answer'
  | 'coffrage'
  | 'pass'
  | 'tick'
  | 'tick_urgent'
  | 'timer_start'
  | 'reveal'
  | 'theme_start'

export type AmbientScene = 'jazz' | 'none'

interface AudioContextValue {
  /** Joue un effet sonore ponctuel. Silencieux si muted. */
  playEffect: (effect: SoundEffect) => void
  /** Lance la musique d'ambiance pour la scène donnée. */
  startAmbient: (scene: AmbientScene) => void
  /** Arrête la musique d'ambiance en cours (fondu). */
  stopAmbient: () => void
  /** Volume global (0–1). */
  volume: number
  setVolume: (v: number) => void
  /** Coupe/rétablit tous les sons. */
  muted: boolean
  setMuted: (m: boolean) => void
  /** Scène d'ambiance active. */
  ambientScene: AmbientScene
}

// ─── Clés localStorage ────────────────────────────────────────────────────────

const LS_MUTED = 'tunneg_audio_muted'
const LS_VOLUME = 'tunneg_audio_volume'

function loadMuted(): boolean {
  try {
    const v = localStorage.getItem(LS_MUTED)
    return v === 'true'
  } catch {
    return false
  }
}

function loadVolume(): number {
  try {
    const v = parseFloat(localStorage.getItem(LS_VOLUME) ?? '')
    return isNaN(v) ? 0.7 : Math.max(0, Math.min(1, v))
  } catch {
    return 0.7
  }
}

// ─── Contexte ─────────────────────────────────────────────────────────────────

const AudioCtx = createContext<AudioContextValue | null>(null)

export function AudioProvider({ children }: { children: React.ReactNode }) {
  const [muted, _setMuted] = useState<boolean>(loadMuted)
  const [volume, _setVolume] = useState<number>(loadVolume)
  const [ambientScene, setAmbientScene] = useState<AmbientScene>('none')

  // Référence vers la fonction stop() de la musique d'ambiance en cours
  const ambientStopRef = useRef<(() => void) | null>(null)

  // ── Persistance ──────────────────────────────────────────────────────────
  const setMuted = useCallback((m: boolean) => {
    _setMuted(m)
    try { localStorage.setItem(LS_MUTED, String(m)) } catch {}
  }, [])

  const setVolume = useCallback((v: number) => {
    const clamped = Math.max(0, Math.min(1, v))
    _setVolume(clamped)
    try { localStorage.setItem(LS_VOLUME, String(clamped)) } catch {}
  }, [])

  // ── Effets sonores ────────────────────────────────────────────────────────
  const playEffect = useCallback((effect: SoundEffect) => {
    if (muted) return
    void resumeAudioContext()
    const vol = volume
    switch (effect) {
      case 'good_answer': playGoodAnswer(vol); break
      case 'bad_answer': playBadAnswer(vol); break
      case 'coffrage': playCoffrage(vol); break
      case 'pass': playPass(vol); break
      case 'tick': playTick(vol, 0); break
      case 'tick_urgent': playTick(vol, 1); break
      case 'timer_start': playTimerStart(vol); break
      case 'reveal': playReveal(vol); break
      case 'theme_start': playThemeStart(vol); break
    }
  }, [muted, volume])

  // ── Ambiance ──────────────────────────────────────────────────────────────
  const stopAmbient = useCallback(() => {
    if (ambientStopRef.current) {
      ambientStopRef.current()
      ambientStopRef.current = null
    }
    setAmbientScene('none')
  }, [])

  const startAmbient = useCallback((scene: AmbientScene) => {
    // Arrête l'ambiance précédente proprement
    if (ambientStopRef.current) {
      ambientStopRef.current()
      ambientStopRef.current = null
    }
    setAmbientScene(scene)
    if (scene === 'none' || muted) return
    void resumeAudioContext()
    if (scene === 'jazz') {
      ambientStopRef.current = startAmbientJazz(volume)
    }
  }, [muted, volume])

  // Quand on démute, relance l'ambiance si une scène était active
  useEffect(() => {
    if (!muted && ambientScene !== 'none') {
      void resumeAudioContext()
      if (ambientScene === 'jazz') {
        if (ambientStopRef.current) ambientStopRef.current()
        ambientStopRef.current = startAmbientJazz(volume)
      }
    } else if (muted && ambientStopRef.current) {
      ambientStopRef.current()
      ambientStopRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [muted])

  // Cleanup au démontage
  useEffect(() => {
    return () => {
      if (ambientStopRef.current) ambientStopRef.current()
    }
  }, [])

  return (
    <AudioCtx.Provider value={{ playEffect, startAmbient, stopAmbient, volume, setVolume, muted, setMuted, ambientScene }}>
      {children}
    </AudioCtx.Provider>
  )
}

/** Hook à utiliser dans n'importe quel composant enfant d'AudioProvider. */
export function useAudio(): AudioContextValue {
  const ctx = useContext(AudioCtx)
  if (!ctx) throw new Error('useAudio must be used within AudioProvider')
  return ctx
}
