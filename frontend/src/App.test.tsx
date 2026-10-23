import type { ReactNode } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { initialState } from './game/gameReducer'
import type { GameState } from './game/types'
import { loadStoredIdentity, storeIdentity } from './net/identity'
import type { Identity } from './net/types'

const audio = vi.hoisted(() => ({ startAmbient: vi.fn(), stopAmbient: vi.fn() }))
vi.mock('./audio/AudioContext', () => ({ useAudio: () => audio }))
vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  motion: { div: ({ children }: { children: ReactNode }) => <div>{children}</div> },
}))
vi.mock('./components/ScreenShell', () => ({ ScreenShell: ({ children }: { children: ReactNode }) => <main>{children}</main> }))
vi.mock('./components/MuteButton', () => ({ MuteButton: () => null }))
vi.mock('./components/decor/CurtainClose', () => ({ CurtainClose: () => null }))
vi.mock('./screens/LobbyScreen', () => ({ LobbyScreen: () => <p>Connected lobby</p> }))
vi.mock('./screens/SelectionScreen', () => ({ SelectionScreen: () => <p>Connected selection</p> }))
vi.mock('./screens/TunnelScreen', () => ({ TunnelScreen: () => <p>Connected tunnel</p> }))
vi.mock('./screens/EndScreen', () => ({ EndScreen: () => <p>Connected end</p> }))
vi.mock('./screens/StyleguideScreen', () => ({ StyleguideScreen: () => null }))

const identity: Identity = {
  version: 2, code: 'ABCD', localPlayerId: 'ecaa8b4a-762f-4dc2-8b3c-f270f512a45f',
  sessionToken: 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8', autoResume: true,
}
const state: GameState = {
  ...initialState, phase: 'tunnel', turnStatus: 'active-absent',
  players: [{ id: 'alice', name: 'Alice', points: 0, connected: false, avatar: '', isPresenter: false }],
  themes: [{ label: 'Cinema', progressValue: 0, validatedSquares: 0, discovered: true, completed: false, nullified: [] }],
}

class FakeWebSocket {
  static OPEN = 1
  static instances: FakeWebSocket[] = []
  readyState = 0
  url: string
  sent: unknown[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  constructor(url: string) { this.url = url; FakeWebSocket.instances.push(this) }
  close() { this.readyState = 3 }
  send(data: string) { this.sent.push(JSON.parse(data)) }
  message(type: string, payload: unknown) { this.onmessage?.({ data: JSON.stringify({ type, payload }) }) }
  sync(snapshot = state) {
    this.readyState = 1
    this.onopen?.()
    this.message('room:state_sync', { code: identity.code, localPlayerId: identity.localPlayerId, role: 'presentateur', state: snapshot })
  }
  fail(code = 1006) { this.readyState = 3; this.onclose?.({ code }) }
}

function latest() { return FakeWebSocket.instances.at(-1)! }
function advance(ms: number) { act(() => { vi.advanceTimersByTime(ms) }) }
function connect() {
  const view = render(<App />)
  act(() => latest().sync())
  expect(screen.getByText('Connected tunnel')).toBeTruthy()
  return view
}
function openSettings() { fireEvent.click(screen.getByTitle('Paramètres de la partie')) }

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
  vi.spyOn(Math, 'random').mockReturnValue(0)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  vi.stubGlobal('WebSocket', FakeWebSocket)
  vi.stubGlobal('fetch', vi.fn())
  FakeWebSocket.instances = []
  localStorage.clear()
  storeIdentity(identity)
  vi.advanceTimersByTime(0)
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('App session lifecycle with real room connection', () => {
  it('keeps a degraded join receipt through preauth failure, reload and recovery without rejoining', async () => {
    localStorage.clear()
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({
      code: identity.code, localPlayerId: identity.localPlayerId, role: 'joueur',
      sessionToken: identity.sessionToken, state: null, persistenceUnavailable: true,
    }), { status: 200 }))
    const view = render(<App />)
    fireEvent.click(screen.getByRole('button', { name: /^Rejoindre$/ }))
    fireEvent.change(screen.getByPlaceholderText('Votre pseudo'), { target: { value: 'Alice' } })
    fireEvent.change(screen.getByPlaceholderText('Code de la room'), { target: { value: identity.code } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Rejoindre la room' })) })
    expect(loadStoredIdentity()).toEqual(identity)
    expect(screen.getByRole('status').textContent).toContain('temporairement indisponible')
    expect(screen.queryByText('Connected lobby')).toBeNull()
    act(() => {
      latest().readyState = 1
      latest().onopen?.()
      latest().message('error', { code: 'persistence_unavailable', message: `unsafe ${identity.sessionToken}` })
      latest().fail(1013)
    })
    expect(screen.getByRole('status').textContent).toContain('session est conservée')
    expect(document.body.textContent).not.toContain(identity.sessionToken)
    expect(loadStoredIdentity()).toEqual(identity)
    fireEvent.click(screen.getByRole('button', { name: 'Reprendre la session' }))
    expect(screen.queryByText('Connected lobby')).toBeNull()
    view.unmount()
    render(<App />)
    act(() => {
      latest().readyState = 1
      latest().onopen?.()
      latest().message('error', { code: 'persistence_unavailable', message: 'Room persistence unavailable.' })
      latest().fail(1013)
    })
    expect(screen.getByRole('status').textContent).toContain('temporairement indisponible')
    advance(250)
    act(() => latest().sync(initialState))
    expect(screen.getByText('Connected lobby')).toBeTruthy()
    expect(screen.queryByRole('status')).toBeNull()
    expect(loadStoredIdentity()).toEqual(identity)
    expect(latest().sent).toEqual([{ type: 'session:auth', payload: {
      localPlayerId: identity.localPlayerId, sessionToken: identity.sessionToken,
    } }])
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string)).toEqual({ pseudo: 'Alice', role: 'joueur' })
  })

  it.each([1006, 4408])('retains identity and automatically retries transient close %s without rejoining', (code) => {
    connect()
    expect(audio.startAmbient).toHaveBeenCalledWith('jazz')
    audio.stopAmbient.mockClear()
    act(() => latest().fail(code))
    expect(screen.getByText('Connexion à la room…')).toBeTruthy()
    expect(screen.queryByPlaceholderText('Votre pseudo')).toBeNull()
    expect(loadStoredIdentity()).toEqual(identity)
    expect(audio.stopAmbient).toHaveBeenCalledTimes(1)
    advance(249)
    expect(FakeWebSocket.instances).toHaveLength(1)
    advance(1)
    expect(FakeWebSocket.instances).toHaveLength(2)
    act(() => latest().sync())
    expect(screen.getByText('Connected tunnel')).toBeTruthy()
    expect(latest().sent).toEqual([{ type: 'session:auth', payload: {
      localPlayerId: identity.localPlayerId, sessionToken: identity.sessionToken,
    } }])
    expect(fetch).not.toHaveBeenCalled()
  })

  it('stops ambience on voluntary disconnect and requires explicit resume even after remount', () => {
    const view = connect()
    audio.stopAmbient.mockClear()
    fireEvent.click(screen.getByRole('button', { name: 'Se déconnecter' }))
    expect(screen.getByRole('status').textContent).toContain('Déconnecté volontairement')
    expect(audio.stopAmbient).toHaveBeenCalledTimes(1)
    expect(loadStoredIdentity()).toEqual({ ...identity, autoResume: false })
    advance(120000)
    expect(FakeWebSocket.instances).toHaveLength(1)
    view.unmount()
    render(<App />)
    expect(screen.getByRole('status').textContent).toContain('Reprise explicite')
    advance(120000)
    expect(FakeWebSocket.instances).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Reprendre la session' }))
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(loadStoredIdentity()?.autoResume).toBe(true)
    act(() => latest().sync())
    expect(screen.getByText('Connected tunnel')).toBeTruthy()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('forgets the disconnected tab locally without erasing a newer stored session', () => {
    connect()
    fireEvent.click(screen.getByRole('button', { name: 'Se déconnecter' }))
    const newer: Identity = { ...identity, sessionToken: 'A'.repeat(43) }
    storeIdentity(newer)
    const stored = localStorage.getItem('legrandtunneg:identity:v2')
    fireEvent.click(screen.getByRole('button', { name: 'Oublier cette session' }))
    expect(screen.getByPlaceholderText('Votre pseudo')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Reprendre la session' })).toBeNull()
    expect(localStorage.getItem('legrandtunneg:identity:v2')).toBe(stored)
    expect(loadStoredIdentity()).toEqual(newer)
    advance(120000)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each([
    ['session_revoked', 4401, 'Session indisponible.'],
    ['player_kicked', 4403, 'Vous avez été retiré'],
    ['room_closed', 4404, 'Room fermée ou indisponible.'],
    ['session_replaced', 4409, 'Session ouverte ailleurs.'],
  ] as const)('keeps the %s explanation visible after late callbacks without retry or ambient restart', (code, closeCode, text) => {
    connect()
    const socket = latest()
    const { onmessage, onclose, onerror } = socket
    audio.stopAmbient.mockClear()
    audio.startAmbient.mockClear()
    act(() => socket.message('session:ended', { code }))
    const explanation = screen.getByText((content) => content.startsWith(text)).textContent
    expect(audio.stopAmbient).toHaveBeenCalledTimes(1)
    act(() => {
      onerror?.()
      onclose?.({ code: closeCode })
      onclose?.({ code: 1006 })
      onmessage?.({ data: JSON.stringify({ type: 'room:state_sync', payload: {
        code: identity.code, localPlayerId: identity.localPlayerId, role: 'presentateur', state,
      } }) })
    })
    advance(120000)
    expect(screen.getByText(explanation!)).toBeTruthy()
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(audio.startAmbient).not.toHaveBeenCalled()
    expect(loadStoredIdentity()).toEqual(code === 'session_replaced' ? { ...identity, autoResume: false } : null)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('never opens a socket or creates membership from legacy storage', () => {
    localStorage.clear()
    localStorage.setItem('legrandtunneg:identity', JSON.stringify({ code: identity.code, localPlayerId: identity.localPlayerId, role: 'presentateur' }))
    render(<App />)
    expect(screen.getByText(/Ancienne session sans preuve privée/)).toBeTruthy()
    expect(screen.getByPlaceholderText('Votre pseudo')).toBeTruthy()
    advance(120000)
    expect(FakeWebSocket.instances).toHaveLength(0)
    expect(fetch).not.toHaveBeenCalled()
    expect(audio.startAmbient).not.toHaveBeenCalled()
  })

  it('does not restart ambience for presence-only or equal snapshots', () => {
    connect()
    audio.startAmbient.mockClear()
    act(() => latest().message('room:state_sync', {
      code: identity.code, localPlayerId: identity.localPlayerId, role: 'presentateur',
      state: { ...state, turnStatus: 'ready', players: state.players.map((p) => ({ ...p, connected: true })) },
    }))
    act(() => latest().message('room:state_sync', {
      code: identity.code, localPlayerId: identity.localPlayerId, role: 'presentateur', state: JSON.parse(JSON.stringify(state)),
    }))
    expect(audio.startAmbient).not.toHaveBeenCalled()
  })

  it.each([false, true])('allows suspended presenter end/quit but reset only with a connected eligible player (%s)', (eligible) => {
    connect()
    if (eligible) act(() => latest().message('room:state_sync', {
      code: identity.code, localPlayerId: identity.localPlayerId, role: 'presentateur',
      state: { ...state, players: [...state.players, { ...state.players[0], id: 'bob', name: 'Bob', connected: true }] },
    }))
    openSettings()
    const reset = screen.getByRole('button', { name: /Réinitialiser/ }) as HTMLButtonElement
    expect(reset.disabled).toBe(!eligible)
    fireEvent.click(reset)
    expect(latest().sent).toHaveLength(eligible ? 2 : 1)
    if (eligible) {
      expect(latest().sent.at(-1)).toEqual({ type: 'game:reset', payload: {} })
      openSettings()
    }
    fireEvent.click(screen.getByRole('button', { name: /Terminer la partie/ }))
    expect(latest().sent.at(-1)).toEqual({ type: 'game:end_early', payload: {} })
    openSettings()
    fireEvent.click(screen.getByRole('button', { name: /Retour au menu/ }))
    expect(latest().sent.at(-1)).toEqual({ type: 'room:quit', payload: {} })
  })
})
