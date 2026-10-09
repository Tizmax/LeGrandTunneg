export type Theme = {
  label: string
  progressValue: number // 0-10
  validatedSquares: number // 0-10
  discovered: boolean
  completed: boolean
  nullified: number[] // list of square numbers (1-10) permanently nullified
}

export type Player = {
  name: string
  points: number
}

export type GamePhase =
  | 'menu' // player entry
  | 'themes' // theme entry (blind)
  | 'selection' // theme selection board
  | 'tunnel' // in-game tunnel for a theme
  | 'end' // end-game podium

export type TunnelSubPhase =
  | 'question' // a question was just asked, awaiting outcome
  | 'after-success' // good answer just given, risk/reward choice

export type SquareColor = 'black' | 'gray' | 'green' | 'yellow' | 'empty'

export type HistoryEntry = {
  themeLabel: string
  playerName: string
  pointsGained: number
}

export type GameState = {
  phase: GamePhase
  players: Player[]
  themes: Theme[]
  currentPlayerIndex: number
  activeThemeIndex: number | null
  tunnelSubPhase: TunnelSubPhase | null
  history: HistoryEntry[]
}
