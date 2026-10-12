/**
 * Bloc 8 — Bouton mute flottant
 *
 * Affiché en overlay sur tous les écrans de jeu (positionné fixed en bas à
 * droite). Bascule le son global on/off et mémorise la préférence.
 */
import { useAudio } from '../audio/AudioContext'

export function MuteButton() {
  const { muted, setMuted } = useAudio()

  return (
    <button
      onClick={() => setMuted(!muted)}
      title={muted ? 'Activer le son' : 'Couper le son'}
      aria-label={muted ? 'Activer le son' : 'Couper le son'}
      className="fixed bottom-4 right-4 z-50 flex h-9 w-9 items-center justify-center rounded-full border border-brass-600/30 bg-charcoal-900/80 text-[#9a8d7d] shadow-stage backdrop-blur-sm transition-all duration-200 hover:border-amber-glow/50 hover:text-amber-glow focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-glow/50"
    >
      {muted ? (
        // Icône son coupé — haut-parleur barré (SVG minimal)
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
          <path d="M9.547 3.062A.75.75 0 0 1 10 3.75v12.5a.75.75 0 0 1-1.264.546L4.703 13H3.167a.75.75 0 0 1-.75-.75v-4.5a.75.75 0 0 1 .75-.75h1.536l4.033-3.796a.75.75 0 0 1 .811-.142ZM13.78 7.22a.75.75 0 1 0-1.06 1.06L13.94 9.5l-1.22 1.22a.75.75 0 1 0 1.06 1.06L15 10.56l1.22 1.22a.75.75 0 1 0 1.06-1.06L16.06 9.5l1.22-1.22a.75.75 0 1 0-1.06-1.06L15 8.44l-1.22-1.22Z" />
        </svg>
      ) : (
        // Icône son actif — haut-parleur avec ondes
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
          <path d="M9.547 3.062A.75.75 0 0 1 10 3.75v12.5a.75.75 0 0 1-1.264.546L4.703 13H3.167a.75.75 0 0 1-.75-.75v-4.5a.75.75 0 0 1 .75-.75h1.536l4.033-3.796a.75.75 0 0 1 .811-.142Z" />
          <path d="M12.78 7.595a.75.75 0 0 1 1.06-.005 4.5 4.5 0 0 1 0 5.82.75.75 0 0 1-1.066-1.056 3 3 0 0 0 0-3.71.75.75 0 0 1 .005-1.049ZM14.312 5.065a.75.75 0 0 1 1.061 0 7.5 7.5 0 0 1 0 9.87.75.75 0 1 1-1.072-1.05 6 6 0 0 0 0-7.77.75.75 0 0 1 .01-1.05Z" />
        </svg>
      )}
    </button>
  )
}
