import { useReducer } from 'react'
import { gameReducer, initialState } from './gameReducer'

export function useGame() {
  const [state, dispatch] = useReducer(gameReducer, initialState)
  return { state, dispatch }
}

export type UseGameReturn = ReturnType<typeof useGame>
