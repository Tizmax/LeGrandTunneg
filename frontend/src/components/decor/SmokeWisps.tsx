import { motion } from 'framer-motion'

/**
 * Volutes de fumée discrètes qui dérivent lentement vers le haut —
 * référence directe aux scènes de club enfumé de "Soul". Rendu en SVG +
 * framer-motion (transform/opacity only) pour rester performant.
 */
const WISPS = [
  { left: '15%', width: 220, duration: 14, delay: 0 },
  { left: '68%', width: 280, duration: 18, delay: 3 },
  { left: '40%', width: 180, duration: 16, delay: 6 },
]

export function SmokeWisps() {
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-0 h-full overflow-hidden" aria-hidden="true">
      {WISPS.map((w, i) => (
        <motion.svg
          key={i}
          viewBox="0 0 200 400"
          className="absolute bottom-0 opacity-0"
          style={{ left: w.left, width: w.width }}
          initial={{ y: 40, opacity: 0 }}
          animate={{ y: [40, -200, -420], opacity: [0, 0.12, 0] }}
          transition={{
            duration: w.duration,
            delay: w.delay,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        >
          <path
            d="M100 400 C 60 340, 140 300, 100 250 C 60 200, 140 160, 100 110 C 70 70, 120 40, 90 0"
            fill="none"
            stroke="rgba(230,215,200,0.9)"
            strokeWidth="26"
            strokeLinecap="round"
          />
        </motion.svg>
      ))}
    </div>
  )
}
