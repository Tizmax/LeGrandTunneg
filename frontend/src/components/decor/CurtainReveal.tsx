import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'

type CurtainRevealProps = {
  children: ReactNode
}

/**
 * Rideaux de velours qui s'ouvrent à l'entrée dans le tunnel — entrée
 * théâtrale façon lever de rideau de spectacle. Joue une seule fois au
 * montage grâce à la `key` posée par le parent (remonte à chaque nouveau
 * thème/question).
 *
 * Les panneaux sont rendus via un portail directement dans `document.body`.
 * Nécessaire car l'écran parent est enveloppé dans un `motion.div` animé
 * (transition de scène dans App.tsx) : tout ancêtre avec une transform CSS
 * active crée un nouveau "containing block" pour ses descendants en
 * `position: fixed`, qui ne se positionnent alors plus par rapport au
 * viewport mais par rapport à cet ancêtre (large de ~1024px au lieu de la
 * largeur réelle de l'écran) — d'où un rideau qui semblait "bloqué" alors
 * qu'il s'animait bien, mais dans un cadre trop étroit. Le portail sort les
 * panneaux de cet arbre transformé pour qu'ils couvrent le vrai viewport.
 *
 * Le panneau droit utilise `.curtain-panel-right` (dégradé en miroir) au
 * lieu d'un `scale-x-[-1]` Tailwind : framer-motion pose sa propre valeur
 * `transform` en style inline pour animer `x`, ce qui écrase toute classe
 * Tailwind définissant aussi `transform` sur le même élément — le flip
 * serait perdu et la translation finale faussée dès le démarrage de
 * l'animation.
 */
export function CurtainReveal({ children }: CurtainRevealProps) {
  return (
    <div className="relative">
      {children}
      {createPortal(
        <>
          <motion.div
            className="curtain-panel pointer-events-none fixed inset-y-0 left-0 z-40 w-1/2"
            initial={{ x: '0%' }}
            animate={{ x: '-100%' }}
            transition={{ duration: 0.8, ease: [0.76, 0, 0.24, 1], delay: 0.1 }}
          />
          <motion.div
            className="curtain-panel-right pointer-events-none fixed inset-y-0 right-0 z-40 w-1/2"
            initial={{ x: '0%' }}
            animate={{ x: '100%' }}
            transition={{ duration: 0.8, ease: [0.76, 0, 0.24, 1], delay: 0.1 }}
          />
        </>,
        document.body,
      )}
    </div>
  )
}
