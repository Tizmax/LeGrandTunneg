import type { ReactNode } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { initialState } from '../game/gameReducer'
import type { GameState, TunnelSubPhase } from '../game/types'
import type { Role } from '../net/types'
import { TunnelScreen } from './TunnelScreen'

vi.mock('../audio/AudioContext', () => ({ useAudio: () => ({ playEffect: vi.fn() }) }))
vi.mock('../components/ScreenShell', () => ({ ScreenShell: ({ children }: { children: ReactNode }) => <main>{children}</main> }))
vi.mock('../components/decor/CurtainReveal', () => ({ CurtainReveal: ({ children }: { children: ReactNode }) => <>{children}</> }))
vi.mock('../components/Tunnel', () => ({ Tunnel: () => null }))
vi.mock('../components/ScoreBoard', () => ({ ScoreBoard: () => null }))
vi.mock('../components/RoomOverview', () => ({ RoomOverview: () => null }))

function game(subphase: TunnelSubPhase = 'question'): GameState {
  return {
    ...initialState,
    phase: 'tunnel',
    players: [{ id: 'alice', name: 'Alice', points: 0, connected: true, avatar: '', isPresenter: false }],
    currentPlayerIndex: 0,
    activeThemeIndex: 0,
    turnStatus: 'ready',
    tunnelSubPhase: subphase,
    themes: [{ label: 'Cinema', progressValue: 0, validatedSquares: 0, discovered: true, completed: false, nullified: [] }],
  }
}

// Advance one tick per React flush: the indicative clock schedules each next tick in an effect.
function tick(seconds: number) {
  for (let i = 0; i < seconds; i += 1) act(() => { vi.advanceTimersByTime(1000) })
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => { cleanup(); vi.useRealTimers() })

describe('local question timer integration', () => {
  it('survives equal sync and presence suspension without reset, freeze, unmount or dispatch at zero', () => {
    const dispatch = vi.fn()
    let state = game()
    const view = render(<TunnelScreen state={state} dispatch={dispatch} role="presentateur" localPlayerId="host" />)
    const timer = screen.getByText('60')
    tick(7)
    expect(timer.textContent).toBe('53')
    state = JSON.parse(JSON.stringify(state)) as GameState
    view.rerender(<TunnelScreen state={state} dispatch={dispatch} role="presentateur" localPlayerId="host" />)
    expect(screen.getByText('53')).toBe(timer)
    state = { ...state, turnStatus: 'active-absent', players: state.players.map((p) => ({ ...p, connected: false })) }
    view.rerender(<TunnelScreen state={state} dispatch={dispatch} role="presentateur" localPlayerId="host" />)
    expect(screen.getByRole('status').textContent).toContain('suspendue')
    expect(screen.getByText('53')).toBe(timer)
    tick(12)
    expect(timer.textContent).toBe('41')
    for (const button of screen.getAllByRole('button')) {
      expect((button as HTMLButtonElement).disabled).toBe(true)
      fireEvent.click(button)
    }
    tick(41)
    expect(screen.getByText('00')).toBe(timer)
    tick(5)
    expect(timer.textContent).toBe('00')
    expect(dispatch).not.toHaveBeenCalled()
    state = { ...state, turnStatus: 'ready', players: state.players.map((p) => ({ ...p, connected: true })) }
    view.rerender(<TunnelScreen state={state} dispatch={dispatch} role="presentateur" localPlayerId="host" />)
    expect(screen.getByText('00')).toBe(timer)
    expect((screen.getByRole('button', { name: 'Bonne réponse' }) as HTMLButtonElement).disabled).toBe(false)
    expect(dispatch).not.toHaveBeenCalled()
  })

  it('starts fresh after a remount or new question but only mounts in question subphase', () => {
    const dispatch = vi.fn()
    const state = game()
    const view = render(<TunnelScreen state={state} dispatch={dispatch} role="presentateur" localPlayerId="host" />)
    tick(4)
    expect(screen.getByText('56')).toBeTruthy()
    view.unmount()
    const remount = render(<TunnelScreen state={state} dispatch={dispatch} role="presentateur" localPlayerId="host" />)
    expect(screen.getByText('60')).toBeTruthy()
    tick(2)
    remount.rerender(<TunnelScreen state={{ ...state, themes: [{ ...state.themes[0], progressValue: 1 }] }} dispatch={dispatch} role="presentateur" localPlayerId="host" />)
    expect(screen.getByText('60')).toBeTruthy()
    for (const tunnelSubPhase of ['question-pending', 'after-success-pending', 'after-success-open'] as const) {
      remount.rerender(<TunnelScreen state={{ ...state, tunnelSubPhase }} dispatch={dispatch} role="presentateur" localPlayerId="host" />)
      expect(screen.queryByText('Temps')).toBeNull()
    }
    expect(dispatch).not.toHaveBeenCalled()
  })

  it.each([
    ['question-pending', 'presentateur', ['Lancer le chrono']],
    ['question', 'presentateur', ['Bonne réponse', 'Mauvaise réponse', 'Passer']],
    ['after-success-pending', 'presentateur', ['Lancer le choix']],
    ['after-success-open', 'joueur', ['Rester sur scène', 'Descendre']],
  ] as const)('disables %s controls for %s while suspended', (tunnelSubPhase, role, names) => {
    const dispatch = vi.fn()
    const state = { ...game(tunnelSubPhase), turnStatus: 'active-absent' as const }
    const view = render(<TunnelScreen state={state} dispatch={dispatch} role={role} localPlayerId="alice" />)
    for (const name of names) {
      const button = screen.getByRole('button', { name }) as HTMLButtonElement
      expect(button.disabled).toBe(true)
      fireEvent.click(button)
    }
    expect(dispatch).not.toHaveBeenCalled()
    view.rerender(<TunnelScreen state={{ ...state, turnStatus: 'ready' }} dispatch={dispatch} role={role} localPlayerId="alice" />)
    for (const name of names) expect((screen.getByRole('button', { name }) as HTMLButtonElement).disabled).toBe(false)
  })

  it.each(['presentateur', 'joueur', 'ecran-principal'] satisfies Role[])('exposes no actionable controls while waiting for an eligible player (%s)', (role) => {
    const dispatch = vi.fn()
    const state = { ...game('after-success-open'), currentPlayerIndex: null, turnStatus: 'waiting-eligible' as const }
    render(<TunnelScreen state={state} dispatch={dispatch} role={role} localPlayerId="alice" />)
    expect(screen.getByRole('status').textContent).toContain('aucun joueur connecté')
    expect(screen.queryAllByRole('button').every((button) => (button as HTMLButtonElement).disabled)).toBe(true)
    expect(dispatch).not.toHaveBeenCalled()
  })
})
