import { useEffect } from 'react'
import { motion } from 'framer-motion'
import { createPortal } from 'react-dom'

type CurtainCloseProps = {
  /** Appelé une fois l'animation de fermeture terminée (et le court temps
   * d'obscurité passé) — le parent peut alors démonter cet overlay. */
  onDone: () => void
}

const CLOSE_DURATION = 0.7
const HOLD_MS = 250

/**
 * Rideaux de velours qui se FERMENT en sortie du tunnel (toute cause :
 * mauvaise réponse, Passer, Descendre, ou coffrage automatique case 10) —
 * symétrique de `CurtainReveal` qui gère l'ouverture réservée à l'entrée
 * (sélection de thème). Rendu en overlay plein écran via portail, au-dessus
 * de la transition de scène (voir App.tsx), puis se retire après un bref
 * temps d'obscurité pour révéler l'écran Sélection déjà monté dessous.
 */
export function CurtainClose({ onDone }: CurtainCloseProps) {
  useEffect(() => {
    const timer = setTimeout(onDone, CLOSE_DURATION * 1000 + HOLD_MS)
    return () => clearTimeout(timer)
  }, [onDone])

  return createPortal(
    <div className="pointer-events-none fixed inset-0 z-50">
      <motion.div
        className="curtain-panel absolute inset-y-0 left-0 w-1/2"
        initial={{ x: '-100%' }}
        animate={{ x: '0%' }}
        transition={{ duration: CLOSE_DURATION, ease: [0.76, 0, 0.24, 1] }}
      />
      <motion.div
        className="curtain-panel-right absolute inset-y-0 right-0 w-1/2"
        initial={{ x: '100%' }}
        animate={{ x: '0%' }}
        transition={{ duration: CLOSE_DURATION, ease: [0.76, 0, 0.24, 1] }}
      />
    </div>,
    document.body,
  )
}
