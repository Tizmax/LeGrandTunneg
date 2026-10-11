export type Theme = {
  label: string
  progressValue: number // 0-10
  validatedSquares: number // 0-10
  discovered: boolean
  completed: boolean
  nullified: number[] // list of square numbers (1-10) permanently nullified
}

export type Player = {
  // localPlayerId d'origine, assigné par le serveur de room — voir
  // docs/websocket-protocol.md. Absent dans l'ancien POC hotseat local,
  // généré uniquement côté client factice pour le mode styleguide/debug.
  id: string
  name: string
  points: number
}

export type GamePhase =
  | 'menu' // player entry
  | 'themes' // theme entry (blind)
  | 'selection-pending' // choice_pending : le choix de thème est éligible mais pas encore révélé par le Présentateur
  | 'selection' // choice_open : la grille de sélection du thème est révélée, visible/cliquable
  | 'tunnel' // in-game tunnel for a theme
  | 'end' // end-game podium

export type TunnelSubPhase =
  | 'question' // a question was just asked, awaiting outcome (pas concerné par la couche show)
  | 'after-success-pending' // choice_pending : bonne réponse non terminale, Continuer/Coffrer éligible mais pas encore révélé
  | 'after-success-open' // choice_open : Continuer/Coffrer révélés, visibles/cliquables par le joueur

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
