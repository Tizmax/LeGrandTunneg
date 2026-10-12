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
  // Présence réseau : un joueur déconnecté reste affiché (classement final)
  // mais son tour est sauté côté serveur (voir docs/websocket-protocol.md).
  connected: boolean
  // Emoji personnage choisi dans le lobby (ex. "🎭", "🦊") — chaîne vide si pas encore choisi.
  avatar: string
}

export type GamePhase =
  // Fusion 2026-10-11 : lobby unique (attente joueurs + saisie thèmes +
  // renommage de soi), remplace les anciennes phases 'menu'/'themes'.
  | 'lobby'
  | 'selection-pending' // choice_pending : le choix de thème est éligible mais pas encore révélé par le Présentateur
  | 'selection' // choice_open : la grille de sélection du thème est révélée, visible/cliquable
  | 'tunnel' // in-game tunnel for a theme
  | 'end' // end-game podium

export type TunnelSubPhase =
  | 'question-pending' // couche show : le Présentateur pose sa question à l'oral, chrono pas encore lancé
  | 'question' // chrono lancé, question en cours, en attente du jugement du Présentateur
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
  // Nom d'affichage du Présentateur (n'apparaît jamais dans `players`, voir
  // docs/websocket-protocol.md) — null en mode styleguide/debug sans réseau.
  presentateurName: string | null
  // Avatar emoji du Présentateur (géré dans Room.avatars côté serveur, pas dans players).
  presentateurAvatar: string
  players: Player[]
  themes: Theme[]
  currentPlayerIndex: number
  activeThemeIndex: number | null
  tunnelSubPhase: TunnelSubPhase | null
  history: HistoryEntry[]
}
