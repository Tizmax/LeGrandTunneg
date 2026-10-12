import { useCallback, useEffect, useRef, useState } from 'react'
import type { GameState } from '../game/types'
import { initialState } from '../game/gameReducer'
import type { ErrorPayload, Identity, Role } from './types'
import { wsBaseUrl } from './config'

const STORAGE_KEY = 'legrandtunneg:identity'

export function loadStoredIdentity(): Identity | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (typeof parsed?.code === 'string' && typeof parsed?.localPlayerId === 'string') {
      return parsed as Identity
    }
    return null
  } catch {
    return null
  }
}

export function storeIdentity(identity: Identity): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(identity))
}

export function clearStoredIdentity(): void {
  localStorage.removeItem(STORAGE_KEY)
}

/** Message client -> serveur du protocole (voir docs/websocket-protocol.md). */
export type OutgoingMessage =
  | { type: 'theme:add'; payload: { label: string } }
  | { type: 'theme:remove'; payload: { index: number } }
  | { type: 'player:remove'; payload: { index: number } }
  | { type: 'player:rename'; payload: { name: string } }
  | { type: 'player:set_avatar'; payload: { avatar: string } }
  | { type: 'game:start'; payload: Record<string, never> }
  | { type: 'choice:reveal'; payload: Record<string, never> }
  | { type: 'theme:select'; payload: { index: number } }
  | { type: 'timer:start'; payload: Record<string, never> }
  | { type: 'answer:good'; payload: Record<string, never> }
  | { type: 'answer:bad'; payload: Record<string, never> }
  | { type: 'answer:pass'; payload: Record<string, never> }
  | { type: 'answer:continue'; payload: Record<string, never> }
  | { type: 'answer:vault'; payload: Record<string, never> }
  | { type: 'game:reset'; payload: Record<string, never> }
  | { type: 'game:end_early'; payload: Record<string, never> }
  | { type: 'room:quit'; payload: Record<string, never> }
  | { type: 'presenter:transfer'; payload: { targetPlayerId: string } }

export type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'kicked' | 'error'

export type RoomConnection = {
  status: ConnectionStatus
  state: GameState
  role: Role | null
  localPlayerId: string | null
  lastError: ErrorPayload | null
  send: (message: OutgoingMessage) => void
  disconnect: () => void
}

/**
 * Hook de connexion WebSocket à une room (remplace l'ancien useGame local à
 * base de useReducer). `identity` doit rester stable (même référence tant que
 * code/localPlayerId ne changent pas) pour éviter de recréer le socket.
 */
export function useRoomConnection(identity: Identity | null): RoomConnection {
  const [status, setStatus] = useState<ConnectionStatus>('idle')
  const [state, setState] = useState<GameState>(initialState)
  const [role, setRole] = useState<Role | null>(null)
  const [localPlayerId, setLocalPlayerId] = useState<string | null>(null)
  const [lastError, setLastError] = useState<ErrorPayload | null>(null)
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!identity) {
      setStatus('idle')
      return
    }

    let cancelled = false
    setStatus('connecting')
    setLastError(null)

    const url = `${wsBaseUrl()}/ws/${identity.code.toUpperCase()}?local_player_id=${encodeURIComponent(identity.localPlayerId)}`
    const socket = new WebSocket(url)
    socketRef.current = socket

    socket.onopen = () => {
      if (cancelled) return
      setStatus('open')
    }

    socket.onmessage = (event) => {
      if (cancelled) return
      let message: { type: string; payload: unknown }
      try {
        message = JSON.parse(event.data)
      } catch {
        return
      }
      if (message.type === 'room:state_sync') {
        const payload = message.payload as {
          role: Role
          localPlayerId: string
          state: GameState
        }
        setRole(payload.role)
        setLocalPlayerId(payload.localPlayerId)
        setState(payload.state)
        setLastError(null)
      } else if (message.type === 'error') {
        setLastError(message.payload as ErrorPayload)
      } else if (message.type === 'room:closed') {
        clearStoredIdentity()
        setStatus('closed')
      } else if (message.type === 'player:kicked') {
        clearStoredIdentity()
        setStatus('kicked')
      }
    }

    socket.onerror = () => {
      if (cancelled) return
      setStatus('error')
    }

    socket.onclose = () => {
      if (cancelled) return
      setStatus((prev) => (prev === 'error' ? prev : 'closed'))
    }

    return () => {
      cancelled = true
      socket.close()
      if (socketRef.current === socket) socketRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identity?.code, identity?.localPlayerId])

  const send = useCallback((message: OutgoingMessage) => {
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) return
    socket.send(JSON.stringify(message))
  }, [])

  const disconnect = useCallback(() => {
    socketRef.current?.close()
  }, [])

  return { status, state, role, localPlayerId, lastError, send, disconnect }
}
