/**
 * Bloc 8 — Intégration audio
 *
 * Tous les sons sont générés synthétiquement via la Web Audio API :
 * aucun fichier asset externe requis. Les sons s'inspirent de l'univers
 * jazz-théâtral du jeu (cuivres, percussions légères).
 */

/** Résout l'AudioContext global en le créant paresseusement (user gesture first). */
let _ctx: AudioContext | null = null
export function getAudioContext(): AudioContext {
  if (!_ctx) {
    _ctx = new AudioContext()
  }
  return _ctx
}

/** Reprend le contexte audio si suspendu par le navigateur (autoplay policy). */
export function resumeAudioContext(): Promise<void> {
  const ctx = getAudioContext()
  if (ctx.state === 'suspended') return ctx.resume()
  return Promise.resolve()
}

// ─── Utilitaires de construction ─────────────────────────────────────────────

function masterGain(ctx: AudioContext, volume: number): GainNode {
  const g = ctx.createGain()
  g.gain.setValueAtTime(volume, ctx.currentTime)
  g.connect(ctx.destination)
  return g
}

function envelope(
  gain: AudioParam,
  _ctx: AudioContext,
  attack: number,
  decay: number,
  sustain: number,
  release: number,
  peak: number,
  startTime: number,
): void {
  gain.setValueAtTime(0, startTime)
  gain.linearRampToValueAtTime(peak, startTime + attack)
  gain.linearRampToValueAtTime(peak * sustain, startTime + attack + decay)
  gain.setValueAtTime(peak * sustain, startTime + attack + decay + release * 0.01)
  gain.linearRampToValueAtTime(0, startTime + attack + decay + release)
}

// ─── Effets sonores ───────────────────────────────────────────────────────────

/**
 * Tic-tac du chronomètre.
 * Son court et sec, type horloge mécanique. Rendu plus tendu à mesure que
 * le temps diminue (pitch monte légèrement).
 *
 * @param urgency 0 = normal, 1 = très urgent (palier rouge)
 */
export function playTick(volume: number, urgency: number = 0): void {
  const ctx = getAudioContext()
  const t = ctx.currentTime

  const master = masterGain(ctx, volume * 0.35)

  // Oscillateur principal — pitch monte avec l'urgence
  const osc = ctx.createOscillator()
  const gainNode = ctx.createGain()
  osc.type = 'square'
  osc.frequency.setValueAtTime(800 + urgency * 400, t)
  osc.frequency.exponentialRampToValueAtTime(400 + urgency * 200, t + 0.04)
  gainNode.gain.setValueAtTime(1, t)
  gainNode.gain.exponentialRampToValueAtTime(0.001, t + 0.06)
  osc.connect(gainNode)
  gainNode.connect(master)
  osc.start(t)
  osc.stop(t + 0.07)

  // Click métallique (noise burst très court)
  const bufferSize = Math.ceil(ctx.sampleRate * 0.01)
  const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < bufferSize; i++) data[i] = (Math.random() * 2 - 1) * 0.6
  const noise = ctx.createBufferSource()
  noise.buffer = buffer
  const noiseGain = ctx.createGain()
  noiseGain.gain.setValueAtTime(0.8, t)
  noiseGain.gain.exponentialRampToValueAtTime(0.001, t + 0.012)
  noise.connect(noiseGain)
  noiseGain.connect(master)
  noise.start(t)
  noise.stop(t + 0.015)
}

/**
 * Bonne réponse — fanfare cuivrée ascendante, joyeuse.
 * Deux notes : si4 (493 Hz) → ré5 (587 Hz), courte reverb synthétique.
 */
export function playGoodAnswer(volume: number): void {
  const ctx = getAudioContext()
  const t = ctx.currentTime
  const master = masterGain(ctx, volume * 0.6)

  // Filtre léger pour chaleur cuivrée
  const filter = ctx.createBiquadFilter()
  filter.type = 'bandpass'
  filter.frequency.value = 900
  filter.Q.value = 1.2
  filter.connect(master)

  const notes = [
    { freq: 493.88, delay: 0 },      // si4
    { freq: 587.33, delay: 0.12 },    // ré5
    { freq: 739.99, delay: 0.24 },    // fa#5
  ]

  notes.forEach(({ freq, delay }) => {
    const osc = ctx.createOscillator()
    const g = ctx.createGain()
    osc.type = 'sawtooth'
    osc.frequency.setValueAtTime(freq, t + delay)
    envelope(g.gain, ctx, 0.01, 0.05, 0.7, 0.25, 1, t + delay)
    osc.connect(g)
    g.connect(filter)
    osc.start(t + delay)
    osc.stop(t + delay + 0.4)
  })
}

/**
 * Mauvaise réponse — descente chromatique sombre, brève.
 * Sol4 → Mi4 (type "wah-wah" de show télévisé).
 */
export function playBadAnswer(volume: number): void {
  const ctx = getAudioContext()
  const t = ctx.currentTime
  const master = masterGain(ctx, volume * 0.5)

  const osc = ctx.createOscillator()
  const g = ctx.createGain()
  osc.type = 'sawtooth'
  osc.frequency.setValueAtTime(392, t)            // sol4
  osc.frequency.exponentialRampToValueAtTime(220, t + 0.45)  // la3
  envelope(g.gain, ctx, 0.01, 0.1, 0.6, 0.35, 0.8, t)
  osc.connect(g)
  g.connect(master)
  osc.start(t)
  osc.stop(t + 0.55)

  // Second oscillateur légèrement désaccordé pour effet "wah"
  const osc2 = ctx.createOscillator()
  const g2 = ctx.createGain()
  osc2.type = 'sawtooth'
  osc2.frequency.setValueAtTime(388, t)
  osc2.frequency.exponentialRampToValueAtTime(218, t + 0.45)
  envelope(g2.gain, ctx, 0.01, 0.1, 0.5, 0.35, 0.5, t)
  osc2.connect(g2)
  g2.connect(master)
  osc2.start(t)
  osc2.stop(t + 0.55)
}

/**
 * Coffrage (victoire) — accord cuivré plein, solennel et satisfaisant.
 * Accord de ré majeur avec résonance finale.
 */
export function playCoffrage(volume: number): void {
  const ctx = getAudioContext()
  const t = ctx.currentTime
  const master = masterGain(ctx, volume * 0.55)

  const filter = ctx.createBiquadFilter()
  filter.type = 'bandpass'
  filter.frequency.value = 700
  filter.Q.value = 0.8
  filter.connect(master)

  // Accord ré majeur : ré4, fa#4, la4 + octave ré5
  const chord = [293.66, 369.99, 440, 587.33]
  chord.forEach((freq, i) => {
    const osc = ctx.createOscillator()
    const g = ctx.createGain()
    osc.type = 'sawtooth'
    osc.frequency.setValueAtTime(freq, t + i * 0.02)
    const dur = 0.7
    envelope(g.gain, ctx, 0.015, 0.1, 0.65, dur, 0.9 - i * 0.05, t + i * 0.02)
    osc.connect(g)
    g.connect(filter)
    osc.start(t + i * 0.02)
    osc.stop(t + i * 0.02 + dur + 0.15)
  })

  // Shimmer haute fréquence (clochette)
  const bell = ctx.createOscillator()
  const bellGain = ctx.createGain()
  bell.type = 'sine'
  bell.frequency.setValueAtTime(1760, t + 0.05) // la6
  envelope(bellGain.gain, ctx, 0.002, 0.02, 0.0, 0.5, 0.4, t + 0.05)
  bell.connect(bellGain)
  bellGain.connect(master)
  bell.start(t + 0.05)
  bell.stop(t + 0.65)
}

/**
 * Passer — courte note neutre, glissement vers le bas.
 */
export function playPass(volume: number): void {
  const ctx = getAudioContext()
  const t = ctx.currentTime
  const master = masterGain(ctx, volume * 0.4)

  const osc = ctx.createOscillator()
  const g = ctx.createGain()
  osc.type = 'triangle'
  osc.frequency.setValueAtTime(440, t)
  osc.frequency.exponentialRampToValueAtTime(310, t + 0.3)
  envelope(g.gain, ctx, 0.01, 0.05, 0.5, 0.25, 0.7, t)
  osc.connect(g)
  g.connect(master)
  osc.start(t)
  osc.stop(t + 0.4)
}

/**
 * Début de chrono (START_TIMER) — petit "ding" d'alerte.
 */
export function playTimerStart(volume: number): void {
  const ctx = getAudioContext()
  const t = ctx.currentTime
  const master = masterGain(ctx, volume * 0.45)

  const osc = ctx.createOscillator()
  const g = ctx.createGain()
  osc.type = 'sine'
  osc.frequency.setValueAtTime(880, t)  // la5
  envelope(g.gain, ctx, 0.005, 0.02, 0, 0.3, 0.6, t)
  osc.connect(g)
  g.connect(master)
  osc.start(t)
  osc.stop(t + 0.35)
}

/**
 * Révélation de choix (REVEAL_CHOICE) — roulement de caisse claire court.
 * Donne l'impression de suspense théâtral.
 */
export function playReveal(volume: number): void {
  const ctx = getAudioContext()
  const t = ctx.currentTime
  const master = masterGain(ctx, volume * 0.35)

  // Roulement de noise bref
  const bufferSize = Math.ceil(ctx.sampleRate * 0.18)
  const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < bufferSize; i++) {
    // Roulement : amplitude oscille rapidement
    const roll = Math.sin(i * 0.08) * 0.5 + 0.5
    data[i] = (Math.random() * 2 - 1) * roll
  }
  const noise = ctx.createBufferSource()
  noise.buffer = buffer
  const filter = ctx.createBiquadFilter()
  filter.type = 'bandpass'
  filter.frequency.value = 2500
  filter.Q.value = 1.5
  const g = ctx.createGain()
  g.gain.setValueAtTime(0, t)
  g.gain.linearRampToValueAtTime(1, t + 0.05)
  g.gain.linearRampToValueAtTime(0.7, t + 0.1)
  g.gain.linearRampToValueAtTime(0, t + 0.18)
  noise.connect(filter)
  filter.connect(g)
  g.connect(master)
  noise.start(t)
  noise.stop(t + 0.2)
}

/**
 * Début de partie ou entrée dans le tunnel — accent dramatique.
 * Hit de tom grave + shimmer cuivré.
 */
export function playThemeStart(volume: number): void {
  const ctx = getAudioContext()
  const t = ctx.currentTime
  const master = masterGain(ctx, volume * 0.5)

  // Tom grave
  const osc = ctx.createOscillator()
  const g = ctx.createGain()
  osc.type = 'sine'
  osc.frequency.setValueAtTime(120, t)
  osc.frequency.exponentialRampToValueAtTime(60, t + 0.2)
  envelope(g.gain, ctx, 0.003, 0.05, 0.3, 0.2, 1, t)
  osc.connect(g)
  g.connect(master)
  osc.start(t)
  osc.stop(t + 0.3)

  // Accent cuivré (fa#5)
  const osc2 = ctx.createOscillator()
  const g2 = ctx.createGain()
  osc2.type = 'sawtooth'
  osc2.frequency.setValueAtTime(739.99, t + 0.05)
  envelope(g2.gain, ctx, 0.01, 0.08, 0.4, 0.3, 0.7, t + 0.05)
  osc2.connect(g2)
  g2.connect(master)
  osc2.start(t + 0.05)
  osc2.stop(t + 0.45)
}

// ─── Musique d'ambiance jazz ──────────────────────────────────────────────────

/**
 * Ligne de basse jazzy minimale en boucle (walking bass simplifiée).
 * Retourne une fonction stop() pour arrêter proprement.
 */
export function startAmbientJazz(volume: number): () => void {
  const ctx = getAudioContext()

  // Notes de basse : ré2, fa2, la2, do3, la2, fa2 (progression jazz ii-V-I)
  const bassNotes = [73.42, 87.31, 110, 130.81, 110, 87.31, 98, 73.42] // Hz
  const noteDuration = 0.45 // secondes par note
  const gapBetweenNotes = 0.05

  let stopped = false
  let currentGain: GainNode | null = null
  let loopTimeout: ReturnType<typeof setTimeout> | null = null

  const masterGainNode = ctx.createGain()
  masterGainNode.gain.setValueAtTime(volume * 0.25, ctx.currentTime)
  masterGainNode.connect(ctx.destination)

  // Filtre chaud pour la basse
  const filter = ctx.createBiquadFilter()
  filter.type = 'lowpass'
  filter.frequency.value = 400
  filter.Q.value = 0.7
  filter.connect(masterGainNode)

  let noteIndex = 0

  function scheduleNote() {
    if (stopped) return
    const t = ctx.currentTime
    const freq = bassNotes[noteIndex % bassNotes.length]
    noteIndex++

    const osc = ctx.createOscillator()
    const g = ctx.createGain()
    osc.type = 'triangle'
    osc.frequency.setValueAtTime(freq, t)
    g.gain.setValueAtTime(0, t)
    g.gain.linearRampToValueAtTime(0.8, t + 0.02)
    g.gain.setValueAtTime(0.8, t + noteDuration - 0.06)
    g.gain.linearRampToValueAtTime(0, t + noteDuration)

    osc.connect(g)
    g.connect(filter)
    osc.start(t)
    osc.stop(t + noteDuration)

    currentGain = g

    // Cymbale hi-hat légère sur temps forts (toutes les 2 notes)
    if (noteIndex % 2 === 0) {
      scheduleHihat(t, volume)
    }

    loopTimeout = setTimeout(scheduleNote, (noteDuration + gapBetweenNotes) * 1000)
  }

  function scheduleHihat(startTime: number, vol: number) {
    const bufSize = Math.ceil(ctx.sampleRate * 0.04)
    const buf = ctx.createBuffer(1, bufSize, ctx.sampleRate)
    const data = buf.getChannelData(0)
    for (let i = 0; i < bufSize; i++) data[i] = Math.random() * 2 - 1

    const noise = ctx.createBufferSource()
    noise.buffer = buf
    const hiFilter = ctx.createBiquadFilter()
    hiFilter.type = 'highpass'
    hiFilter.frequency.value = 8000
    const hiGain = ctx.createGain()
    hiGain.gain.setValueAtTime(vol * 0.12, startTime)
    hiGain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.04)
    noise.connect(hiFilter)
    hiFilter.connect(hiGain)
    hiGain.connect(ctx.destination)
    noise.start(startTime)
    noise.stop(startTime + 0.045)
  }

  // Fondu d'entrée
  masterGainNode.gain.setValueAtTime(0, ctx.currentTime)
  masterGainNode.gain.linearRampToValueAtTime(volume * 0.25, ctx.currentTime + 1.5)

  scheduleNote()

  return function stop() {
    stopped = true
    if (loopTimeout) clearTimeout(loopTimeout)
    // Fondu de sortie
    masterGainNode.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.8)
    if (currentGain) {
      try { currentGain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.3) } catch (_) {}
    }
    setTimeout(() => {
      try { masterGainNode.disconnect() } catch (_) {}
      try { filter.disconnect() } catch (_) {}
    }, 900)
  }
}
