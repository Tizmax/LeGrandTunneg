import type { GameState, HistoryEntry, Player, Theme } from './types'
import { coffrer, createTheme, poursuivre, resetTheme } from './rules'

export type GameAction =
  | { type: 'ADD_PLAYER'; name: string }
  | { type: 'REMOVE_PLAYER'; index: number }
  | { type: 'GO_TO_THEMES' }
  | { type: 'ADD_THEME'; label: string }
  | { type: 'REMOVE_THEME'; index: number }
  | { type: 'START_GAME' }
  | { type: 'SELECT_THEME'; index: number }
  // Couche show : le Présentateur a fini de poser sa question à l'oral et
  // déclenche manuellement le chrono (question-pending -> question).
  | { type: 'START_TIMER' }
  | { type: 'GOOD_ANSWER' }
  | { type: 'BAD_ANSWER' }
  | { type: 'PASS' }
  | { type: 'CONTINUE' }
  | { type: 'COFFRER' }
  | { type: 'RESET_GAME' }
  | { type: 'QUIT_TO_MENU' }
  // Couche show : fait passer un choix joueur de choice_pending à choice_open.
  // Déclenchée par le Présentateur (bouton "Lancer le choix"). S'applique au
  // choix de thème (phase 'selection-pending' -> 'selection') et au choix
  // Continuer/Coffrer (tunnelSubPhase 'after-success-pending' -> 'after-success-open').
  | { type: 'REVEAL_CHOICE' }

export const initialState: GameState = {
  phase: 'menu',
  players: [],
  themes: [],
  currentPlayerIndex: 0,
  activeThemeIndex: null,
  tunnelSubPhase: null,
  history: [],
}

function nextPlayerIndex(current: number, count: number): number {
  if (count === 0) return 0
  return (current + 1) % count
}

function creditPoints(players: Player[], index: number, amount: number): Player[] {
  if (amount <= 0) return players
  return players.map((p, i) => (i === index ? { ...p, points: p.points + amount } : p))
}

function allThemesCompleted(themes: Theme[]): boolean {
  return themes.length > 0 && themes.every((t) => t.completed)
}

export function gameReducer(state: GameState, action: GameAction): GameState {
  switch (action.type) {
    case 'ADD_PLAYER': {
      const name = action.name.trim()
      if (!name) return state
      // Reducer local conservé pour StyleguideScreen (Bloc 6) et un futur mode
      // solo hotseat (Bloc 7bis) ; id généré localement car il n'y a pas de
      // serveur de room dans ce chemin (contrairement au mode multi réseau,
      // voir net/useRoomConnection.ts où `id` vient du serveur).
      const id = typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `local-${Date.now()}-${Math.random().toString(36).slice(2)}`
      return { ...state, players: [...state.players, { id, name, points: 0 }] }
    }

    case 'REMOVE_PLAYER': {
      return {
        ...state,
        players: state.players.filter((_, i) => i !== action.index),
      }
    }

    case 'GO_TO_THEMES': {
      if (state.players.length < 2) return state
      return { ...state, phase: 'themes' }
    }

    case 'ADD_THEME': {
      const label = action.label.trim()
      if (!label) return state
      return { ...state, themes: [...state.themes, createTheme(label)] }
    }

    case 'REMOVE_THEME': {
      return {
        ...state,
        themes: state.themes.filter((_, i) => i !== action.index),
      }
    }

    case 'START_GAME': {
      if (state.themes.length < 1) return state
      const startIndex = Math.floor(Math.random() * state.players.length)
      return {
        ...state,
        // Couche show : le choix de thème du premier tour est éligible mais
        // reste caché tant que le Présentateur n'a pas lancé le choix.
        phase: 'selection-pending',
        currentPlayerIndex: startIndex,
        activeThemeIndex: null,
        tunnelSubPhase: null,
        history: [],
      }
    }

    case 'SELECT_THEME': {
      // Le choix ne peut être tranché que lorsqu'il a été révélé (choice_open).
      if (state.phase !== 'selection') return state
      const theme = state.themes[action.index]
      if (!theme || theme.completed) return state
      const updatedThemes = state.themes.map((t, i) =>
        i === action.index ? { ...t, discovered: true } : t,
      )
      return {
        ...state,
        phase: 'tunnel',
        themes: updatedThemes,
        activeThemeIndex: action.index,
        // Couche show : le Présentateur doit poser sa question avant de
        // lancer le chrono (voir action START_TIMER).
        tunnelSubPhase: 'question-pending',
      }
    }

    case 'START_TIMER': {
      if (state.tunnelSubPhase !== 'question-pending') return state
      return { ...state, tunnelSubPhase: 'question' }
    }

    case 'GOOD_ANSWER': {
      if (state.activeThemeIndex === null) return state
      const idx = state.activeThemeIndex
      const theme = state.themes[idx]
      const discoveredFalse: Theme = { ...theme, discovered: false }
      const { theme: advancedTheme, autoCoffrage, pointsGained } = poursuivre(discoveredFalse)
      const updatedThemes = state.themes.map((t, i) => (i === idx ? advancedTheme : t))

      if (autoCoffrage) {
        const players = creditPoints(state.players, state.currentPlayerIndex, pointsGained)
        const history: HistoryEntry[] =
          pointsGained > 0
            ? [
                ...state.history,
                {
                  themeLabel: theme.label,
                  playerName: state.players[state.currentPlayerIndex].name,
                  pointsGained,
                },
              ]
            : state.history
        const completed = allThemesCompleted(updatedThemes)
        return {
          ...state,
          themes: updatedThemes,
          players,
          history,
          currentPlayerIndex: nextPlayerIndex(state.currentPlayerIndex, state.players.length),
          // Coffrage automatique case 10 : AUCUN choix humain à révéler, pas
          // concerné par la couche show, on repasse directement par le
          // choice_pending du prochain tour de sélection de thème.
          phase: completed ? 'end' : 'selection-pending',
          activeThemeIndex: null,
          tunnelSubPhase: null,
        }
      }

      return {
        ...state,
        themes: updatedThemes,
        // Couche show : le choix Continuer/Coffrer est éligible mais reste
        // caché tant que le Présentateur n'a pas lancé le choix.
        tunnelSubPhase: 'after-success-pending',
      }
    }

    case 'BAD_ANSWER': {
      return {
        ...state,
        phase: 'selection-pending',
        activeThemeIndex: null,
        tunnelSubPhase: null,
        currentPlayerIndex: nextPlayerIndex(state.currentPlayerIndex, state.players.length),
      }
    }

    case 'PASS': {
      if (state.activeThemeIndex === null) return state
      const idx = state.activeThemeIndex
      const theme = state.themes[idx]
      const nullifiedSquare = theme.progressValue + 1
      const themeWithNullified: Theme = {
        ...theme,
        nullified: [...theme.nullified, nullifiedSquare],
      }
      const { theme: advancedTheme, autoCoffrage, pointsGained } = poursuivre(themeWithNullified)
      const updatedThemes = state.themes.map((t, i) => (i === idx ? advancedTheme : t))

      if (autoCoffrage) {
        const players = creditPoints(state.players, state.currentPlayerIndex, pointsGained)
        const history: HistoryEntry[] =
          pointsGained > 0
            ? [
                ...state.history,
                {
                  themeLabel: theme.label,
                  playerName: state.players[state.currentPlayerIndex].name,
                  pointsGained,
                },
              ]
            : state.history
        const completed = allThemesCompleted(updatedThemes)
        return {
          ...state,
          themes: updatedThemes,
          players,
          history,
          // Passer : le joueur courant ne change PAS, mais le thème est
          // terminé automatiquement donc on revient à la sélection (couche
          // show : coffrage auto, pas de choix humain à révéler ici, mais le
          // prochain tour de sélection de thème repasse par choice_pending).
          phase: completed ? 'end' : 'selection-pending',
          activeThemeIndex: null,
          tunnelSubPhase: null,
        }
      }

      return {
        ...state,
        phase: 'selection-pending',
        themes: updatedThemes,
        activeThemeIndex: null,
        tunnelSubPhase: null,
        // currentPlayerIndex inchangé : le joueur reste actif.
      }
    }

    case 'CONTINUE': {
      // Action du joueur une fois le choix Continuer/Coffrer révélé et tranché.
      if (state.activeThemeIndex === null || state.tunnelSubPhase !== 'after-success-open') {
        return state
      }
      const idx = state.activeThemeIndex
      const updatedThemes = state.themes.map((t, i) =>
        i === idx ? { ...t, discovered: true } : t,
      )
      return {
        ...state,
        themes: updatedThemes,
        // Couche show : repasse par question-pending, le Présentateur doit
        // reposer sa question avant de relancer le chrono.
        tunnelSubPhase: 'question-pending',
      }
    }

    case 'COFFRER': {
      // Action du joueur une fois le choix Continuer/Coffrer révélé et tranché.
      if (state.activeThemeIndex === null || state.tunnelSubPhase !== 'after-success-open') {
        return state
      }
      const idx = state.activeThemeIndex
      const theme = state.themes[idx]
      const { theme: coffredTheme, pointsGained } = coffrer(theme)
      const updatedThemes = state.themes.map((t, i) => (i === idx ? coffredTheme : t))
      const players = creditPoints(state.players, state.currentPlayerIndex, pointsGained)
      const history: HistoryEntry[] =
        pointsGained > 0
          ? [
              ...state.history,
              {
                themeLabel: theme.label,
                playerName: state.players[state.currentPlayerIndex].name,
                pointsGained,
              },
            ]
          : state.history
      const completed = allThemesCompleted(updatedThemes)
      return {
        ...state,
        themes: updatedThemes,
        players,
        history,
        phase: completed ? 'end' : 'selection-pending',
        activeThemeIndex: null,
        tunnelSubPhase: null,
        currentPlayerIndex: nextPlayerIndex(state.currentPlayerIndex, state.players.length),
      }
    }

    case 'RESET_GAME': {
      return {
        ...state,
        players: state.players.map((p) => ({ ...p, points: 0 })),
        themes: state.themes.map(resetTheme),
        currentPlayerIndex: 0,
        activeThemeIndex: null,
        tunnelSubPhase: null,
        history: [],
        phase: 'selection-pending',
      }
    }

    case 'QUIT_TO_MENU': {
      return initialState
    }

    case 'REVEAL_CHOICE': {
      // Couche show, actionnée par le Présentateur : fait passer le choix
      // joueur actuellement en attente (choice_pending) à l'état révélé
      // (choice_open), sans toucher au reste de l'état.
      if (state.phase === 'selection-pending') {
        return { ...state, phase: 'selection' }
      }
      if (state.tunnelSubPhase === 'after-success-pending') {
        return { ...state, tunnelSubPhase: 'after-success-open' }
      }
      return state
    }

    default:
      return state
  }
}
