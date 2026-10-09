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
  | { type: 'GOOD_ANSWER' }
  | { type: 'BAD_ANSWER' }
  | { type: 'PASS' }
  | { type: 'CONTINUE' }
  | { type: 'COFFRER' }
  | { type: 'RESET_GAME' }
  | { type: 'QUIT_TO_MENU' }

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
      return { ...state, players: [...state.players, { name, points: 0 }] }
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
        phase: 'selection',
        currentPlayerIndex: startIndex,
        activeThemeIndex: null,
        tunnelSubPhase: null,
        history: [],
      }
    }

    case 'SELECT_THEME': {
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
        tunnelSubPhase: 'question',
      }
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
          phase: completed ? 'end' : 'selection',
          activeThemeIndex: null,
          tunnelSubPhase: null,
        }
      }

      return {
        ...state,
        themes: updatedThemes,
        tunnelSubPhase: 'after-success',
      }
    }

    case 'BAD_ANSWER': {
      return {
        ...state,
        phase: 'selection',
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
          // terminé automatiquement donc on revient à la sélection.
          phase: completed ? 'end' : 'selection',
          activeThemeIndex: null,
          tunnelSubPhase: null,
        }
      }

      return {
        ...state,
        phase: 'selection',
        themes: updatedThemes,
        activeThemeIndex: null,
        tunnelSubPhase: null,
        // currentPlayerIndex inchangé : le joueur reste actif.
      }
    }

    case 'CONTINUE': {
      if (state.activeThemeIndex === null) return state
      const idx = state.activeThemeIndex
      const updatedThemes = state.themes.map((t, i) =>
        i === idx ? { ...t, discovered: true } : t,
      )
      return {
        ...state,
        themes: updatedThemes,
        tunnelSubPhase: 'question',
      }
    }

    case 'COFFRER': {
      if (state.activeThemeIndex === null) return state
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
        phase: completed ? 'end' : 'selection',
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
        phase: 'selection',
      }
    }

    case 'QUIT_TO_MENU': {
      return initialState
    }

    default:
      return state
  }
}
