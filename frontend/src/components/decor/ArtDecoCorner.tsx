type ArtDecoCornerProps = {
  position: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'
  className?: string
}

const rotations: Record<ArtDecoCornerProps['position'], string> = {
  'top-left': 'top-2 left-2 rotate-0',
  'top-right': 'top-2 right-2 rotate-90',
  'bottom-left': 'bottom-2 left-2 -rotate-90',
  'bottom-right': 'bottom-2 right-2 rotate-180',
}

/** Ornement Art Déco discret pour les coins de panneaux (esthétique années 1920-30). */
export function ArtDecoCorner({ position, className = '' }: ArtDecoCornerProps) {
  return (
    <svg
      viewBox="0 0 40 40"
      fill="none"
      className={`art-deco-corner ${rotations[position]} ${className}`}
      aria-hidden="true"
    >
      <path d="M2 2 L2 14 M2 2 L14 2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M2 2 L22 2" stroke="currentColor" strokeWidth="1" opacity="0.5" />
      <path d="M2 2 L2 22" stroke="currentColor" strokeWidth="1" opacity="0.5" />
      <circle cx="9" cy="9" r="2" stroke="currentColor" strokeWidth="1" />
      <path d="M2 18 L6 18 M18 2 L18 6" stroke="currentColor" strokeWidth="1" opacity="0.6" />
    </svg>
  )
}
