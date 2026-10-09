import type { SquareColor, Theme } from './types'

/** Barème de points par case (k 1-indexé). */
export function pointsForSquare(k: number): number {
  if (k >= 1 && k <= 3) return 1
  if (k >= 4 && k <= 6) return 2
  if (k >= 7 && k <= 9) return 3
  if (k === 10) return 5
  return 0
}

/** Couleur d'une case k pour un thème donné, selon l'ordre de priorité strict. */
export function squareColor(theme: Theme, k: number): SquareColor {
  if (theme.nullified.includes(k)) return 'black'
  if (k <= theme.validatedSquares) return 'gray'
  if (k <= theme.progressValue) return 'green'
  if (k - 1 === theme.progressValue && theme.discovered) return 'yellow'
  return 'empty'
}

export function createTheme(label: string): Theme {
  return {
    label,
    progressValue: 0,
    validatedSquares: 0,
    discovered: false,
    completed: false,
    nullified: [],
  }
}

export function resetTheme(theme: Theme): Theme {
  return createTheme(theme.label)
}

/**
 * Coffrage : crédite les points de toutes les cases entre validatedSquares+1
 * et progressValue (incluses), sauf celles nullifiées, puis marque ces cases
 * comme validées. Retourne le thème mis à jour et le total de points gagnés.
 */
export function coffrer(theme: Theme): { theme: Theme; pointsGained: number } {
  let pointsGained = 0
  let validatedSquares = theme.validatedSquares
  for (let i = theme.validatedSquares + 1; i <= theme.progressValue; i++) {
    validatedSquares = i
    if (!theme.nullified.includes(i)) {
      pointsGained += pointsForSquare(i)
    }
  }
  return {
    theme: { ...theme, validatedSquares },
    pointsGained,
  }
}

/** Avance la progression suite à une bonne réponse ou un passage. */
export function poursuivre(
  theme: Theme,
): { theme: Theme; autoCoffrage: boolean; pointsGained: number } {
  if (theme.progressValue === 9) {
    const advanced = { ...theme, progressValue: 10 }
    const { theme: coffredTheme, pointsGained } = coffrer(advanced)
    return {
      theme: { ...coffredTheme, completed: true },
      autoCoffrage: true,
      pointsGained,
    }
  }
  return {
    theme: { ...theme, progressValue: theme.progressValue + 1 },
    autoCoffrage: false,
    pointsGained: 0,
  }
}
