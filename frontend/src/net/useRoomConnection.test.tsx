import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { initialState } from '../game/gameReducer'
import { loadStoredIdentity, storeIdentity } from './identity'
import type { Identity } from './types'
import { useRoomConnection } from './useRoomConnection'

const identity: Identity = {
  version: 2,
  code: 'ABCD',
  localPlayerId: 'ecaa8b4a-762f-4dc2-8b3c-f270f512a45f',
  sessionToken: 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8',
  autoResume: true,
}
const action = { type: 'game:start', payload: {} } as const

class FakeWebSocket {
  static OPEN = 1
  static instances: FakeWebSocket[] = []
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  sent: unknown[] = []
  url: string
  close = vi.fn(() => { this.readyState = 3 })

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(data: string) { this.sent.push(JSON.parse(data)) }
  open() { this.readyState = 1; this.onopen?.() }
  message(type: string, payload: unknown) {
    this.onmessage?.({ data: JSON.stringify({ type, payload }) })
  }
  sync(who = identity) {
    this.message('room:state_sync', {
      code: who.code, localPlayerId: who.localPlayerId, role: 'joueur', state: initialState,
    })
  }
  fail(code = 1006) { this.readyState = 3; this.onclose?.({ code }) }
}

function latest() { return FakeWebSocket.instances.at(-1)! }
function advance(ms: number) { act(() => { vi.advanceTimersByTime(ms) }) }
function queuedCallbacks(socket: FakeWebSocket) {
  const { onopen, onmessage, onclose, onerror } = socket
  return () => {
    onopen?.()
    onmessage?.({ data: JSON.stringify({ type: 'room:state_sync', payload: {
      code: identity.code, localPlayerId: identity.localPlayerId, role: 'joueur', state: initialState,
    } }) })
    onmessage?.({ data: JSON.stringify({ type: 'session:ended', payload: { code: 'session_revoked' } }) })
    onerror?.()
    onclose?.({ code: 4409 })
    onclose?.({ code: 1006 })
  }
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] })
  vi.spyOn(Math, 'random').mockReturnValue(0)
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
  localStorage.clear()
  storeIdentity(identity)
  // jsdom queues storage events with zero-delay timers; exclude those from retry counts.
  vi.advanceTimersByTime(0)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('authenticated transport and retry backoff', () => {
  it('authenticates in the first frame, never in the URL, and drops unacknowledged actions without replay', () => {
    const { result } = renderHook(() => useRoomConnection(identity))
    const socket = latest()
    const url = new URL(socket.url)
    expect(url.pathname).toBe('/ws/ABCD')
    expect(url.search).toBe('')
    expect(socket.url).not.toContain(identity.sessionToken)
    act(() => { result.current.send(action); socket.open(); result.current.send(action) })
    expect(socket.sent).toEqual([{ type: 'session:auth', payload: {
      localPlayerId: identity.localPlayerId, sessionToken: identity.sessionToken,
    } }])
    expect(result.current.status).toBe('connecting')
    act(() => socket.sync())
    expect(result.current.status).toBe('open')
    act(() => result.current.send(action))
    expect(socket.sent.at(-1)).toEqual(action)
    act(() => { socket.fail(); result.current.send(action) })
    advance(250)
    const replacement = latest()
    act(() => { replacement.open(); result.current.send(action); replacement.sync() })
    expect(replacement.sent).toHaveLength(1)
    expect(replacement.sent[0]).toMatchObject({ type: 'session:auth' })
  })

  it.each([0, 0.5, 0.999999])('uses exact capped exponential jitter for random=%s, resetting only on valid sync', (random) => {
    vi.mocked(Math.random).mockReturnValue(random)
    const { result } = renderHook(() => useRoomConnection(identity))
    const caps = [500, 1000, 2000, 4000, 8000, 16000, 30000, 30000]
    for (const cap of caps) {
      const socket = latest()
      act(() => {
        socket.open()
        socket.message('room:state_sync', { code: 'WXYZ', localPlayerId: identity.localPlayerId,
          role: 'joueur', state: initialState })
        socket.onerror?.()
        socket.fail(4408)
        socket.fail(1006)
      })
      expect(result.current.status).toBe('reconnecting')
      expect(vi.getTimerCount()).toBe(1)
      const count = FakeWebSocket.instances.length
      const delay = Math.floor(cap * (0.5 + random * 0.5))
      advance(delay - 1)
      expect(FakeWebSocket.instances).toHaveLength(count)
      advance(1)
      expect(FakeWebSocket.instances).toHaveLength(count + 1)
    }
    act(() => { latest().open(); latest().sync(); latest().fail() })
    const count = FakeWebSocket.instances.length
    const delay = Math.floor(500 * (0.5 + random * 0.5))
    advance(delay - 1)
    expect(FakeWebSocket.instances).toHaveLength(count)
    advance(1)
    expect(FakeWebSocket.instances).toHaveLength(count + 1)
  })

  it.each([4408, 1006, 1011, 1012, 1013])('treats close %s as transient and retains the proof', (code) => {
    const { result } = renderHook(() => useRoomConnection(identity))
    act(() => { latest().open(); latest().sync(); latest().onerror?.(); latest().fail(code) })
    expect(result.current.status).toBe('reconnecting')
    expect(loadStoredIdentity()).toEqual(identity)
    advance(250)
    expect(FakeWebSocket.instances).toHaveLength(2)
  })
})

describe('terminal outcomes', () => {
  const endings = [
    ['session_revoked', 4401, 'revoked', false],
    ['player_kicked', 4403, 'kicked', false],
    ['room_closed', 4404, 'closed', false],
    ['session_replaced', 4409, 'replaced', true],
  ] as const

  it.each(endings)('%s frame preserves its explanation and storage decision after late close/error', (code, closeCode, status, retain) => {
    const { result } = renderHook(() => useRoomConnection(identity))
    const socket = latest()
    act(() => {
      socket.open(); socket.sync()
      socket.message('session:ended', { code, message: 'Server terminal explanation.' })
    })
    expect(result.current.status).toBe(status)
    expect(result.current.lastError?.code).toBe(code)
    expect(result.current.lastError?.message).toBeTruthy()
    const explanation = result.current.lastError
    act(() => { socket.onerror?.(); socket.fail(closeCode); socket.fail(1006); socket.sync() })
    advance(120000)
    expect(result.current.lastError).toEqual(explanation)
    expect(result.current.status).toBe(status)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(loadStoredIdentity()).toEqual(retain ? { ...identity, autoResume: false } : null)
    act(() => result.current.resume())
    expect(FakeWebSocket.instances).toHaveLength(retain ? 2 : 1)
    if (retain) expect(loadStoredIdentity()?.autoResume).toBe(true)
  })

  it.each(endings)('close-only %s is authoritative even after error', (code, closeCode, status, retain) => {
    const { result } = renderHook(() => useRoomConnection(identity))
    act(() => { latest().onerror?.(); latest().fail(closeCode) })
    expect(result.current.status).toBe(status)
    expect(result.current.lastError?.code).toBe(code)
    expect(loadStoredIdentity()).toEqual(retain ? { ...identity, autoResume: false } : null)
    advance(120000)
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it.each([['player:kicked', 'kicked'], ['room:closed', 'closed']])('supports terminal alias %s', (event, status) => {
    const { result } = renderHook(() => useRoomConnection(identity))
    act(() => latest().message(event, {}))
    const explanation = result.current.lastError
    act(() => { latest().fail(1006); latest().onerror?.() })
    advance(120000)
    expect(result.current.status).toBe(status)
    expect(result.current.lastError).toEqual(explanation)
    expect(loadStoredIdentity()).toBeNull()
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it.each([1008, 1009, 4429])('never retries policy close %s without explicit action', (code) => {
    const { result } = renderHook(() => useRoomConnection(identity))
    act(() => latest().fail(code))
    expect(result.current.status).toBe('policy-error')
    expect(result.current.lastError?.message).toBeTruthy()
    expect(loadStoredIdentity()).toEqual({ ...identity, autoResume: false })
    advance(120000)
    expect(FakeWebSocket.instances).toHaveLength(1)
    act(() => result.current.resume())
    expect(FakeWebSocket.instances).toHaveLength(2)
  })
})

describe('obsolete controllers and explicit resume', () => {
  describe.each([
    { code: 'WXYZ' },
    { localPlayerId: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa' },
    { sessionToken: 'A'.repeat(43) },
  ])('storage replaced by a newer controller: %j', (replacement) => {
    it.each(['disconnect', 'session_revoked', 'player_kicked', 'room_closed', 'session_replaced', 'policy'])(
      'does not overwrite or delete the newer proof during %s or subsequent resume', (outcome) => {
        const { result } = renderHook(() => useRoomConnection(identity))
        const old = latest()
        act(() => { old.open(); old.sync() })
        const newer = { ...identity, ...replacement }
        storeIdentity(newer)
        const raw = localStorage.getItem('legrandtunneg:identity:v2')
        act(() => {
          if (outcome === 'disconnect') result.current.disconnect()
          else if (outcome === 'policy') old.fail(1008)
          else old.message('session:ended', { code: outcome })
        })
        expect(localStorage.getItem('legrandtunneg:identity:v2')).toBe(raw)
        const pausedNewer = { ...newer, autoResume: false }
        storeIdentity(pausedNewer)
        act(() => result.current.resume())
        expect(loadStoredIdentity()).toEqual(pausedNewer)
        advance(120000)
        expect(loadStoredIdentity()).toEqual(pausedNewer)
      },
    )
  })

  it('ignores every callback from a replaced socket', () => {
    const { result } = renderHook(() => useRoomConnection(identity))
    const stale = latest()
    const flushStale = queuedCallbacks(stale)
    act(() => { stale.open(); stale.sync(); stale.fail() })
    advance(250)
    const active = latest()
    act(() => { active.open(); active.sync() })
    act(flushStale)
    expect(result.current.status).toBe('open')
    expect(loadStoredIdentity()).toEqual(identity)
    expect(stale.sent).toHaveLength(1)
    expect(vi.getTimerCount()).toBe(0)
    act(() => result.current.send(action))
    expect(active.sent.at(-1)).toEqual(action)
  })

  it('cancels pending retries and ignores stale callbacks after identity changes', () => {
    const { result, rerender } = renderHook(({ who }) => useRoomConnection(who), { initialProps: { who: identity } })
    const stale = latest()
    const flushStale = queuedCallbacks(stale)
    act(() => stale.fail())
    const other = { ...identity, code: 'WXYZ', localPlayerId: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa' }
    storeIdentity(other)
    rerender({ who: other })
    const active = latest()
    act(() => { active.open(); active.sync(other) })
    act(flushStale)
    advance(120000)
    expect(result.current.status).toBe('open')
    expect(result.current.localPlayerId).toBe(other.localPlayerId)
    expect(loadStoredIdentity()).toEqual(other)
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(stale.sent).toHaveLength(0)
  })

  it('voluntary disconnect cancels retry, persists across reload, and requires explicit resume', () => {
    const first = renderHook(() => useRoomConnection(identity))
    const stale = latest()
    const flushStale = queuedCallbacks(stale)
    act(() => { stale.fail(); first.result.current.disconnect() })
    const explanation = first.result.current.lastError
    act(flushStale)
    advance(120000)
    expect(first.result.current.status).toBe('disconnected')
    expect(first.result.current.lastError).toEqual(explanation)
    expect(loadStoredIdentity()).toEqual({ ...identity, autoResume: false })
    first.unmount()
    const restored = loadStoredIdentity()
    const second = renderHook(() => useRoomConnection(restored))
    expect(second.result.current.status).toBe('disconnected')
    expect(FakeWebSocket.instances).toHaveLength(1)
    act(() => second.result.current.resume())
    expect(loadStoredIdentity()?.autoResume).toBe(true)
    expect(FakeWebSocket.instances).toHaveLength(2)
    act(() => { latest().open(); latest().sync() })
    expect(second.result.current.status).toBe('open')
  })

  it('unmount cancels retry and makes queued callbacks and retained controls inert', () => {
    const { result, unmount } = renderHook(() => useRoomConnection(identity))
    const stale = latest()
    const flushStale = queuedCallbacks(stale)
    const controls = result.current
    act(() => stale.fail())
    unmount()
    act(() => {
      flushStale()
      controls.resume(); controls.disconnect(); controls.send(action)
    })
    advance(120000)
    expect(vi.getTimerCount()).toBe(0)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(stale.sent).toEqual([])
    expect(loadStoredIdentity()).toEqual(identity)
  })
})
