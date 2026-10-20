import { useCallback, useEffect, useRef, useState } from 'react'
import type { GameState } from '../game/types'
import { initialState } from '../game/gameReducer'
import type { ErrorPayload, Identity, Role } from './types'
import { wsBaseUrl } from './config'
import { clearStoredIdentity, loadStoredIdentity, storeIdentity } from './identity'
export { clearStoredIdentity, loadStoredIdentity, storeIdentity, hasLegacyIdentity } from './identity'

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

export type ConnectionStatus = 'idle' | 'connecting' | 'reconnecting' | 'open' | 'disconnected'
  | 'closed' | 'kicked' | 'revoked' | 'replaced' | 'policy-error'

export type RoomConnection = {
  status: ConnectionStatus
  state: GameState
  role: Role | null
  localPlayerId: string | null
  lastError: ErrorPayload | null
  send: (message: OutgoingMessage) => void
  disconnect: () => void
  resume: () => void
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
  const authenticatedRef = useRef(false)
  const disconnectRef = useRef<() => void>(() => {})
  const resumeRef = useRef<() => void>(() => {})

  useEffect(() => {
    let cancelled = false
    let stopped = false
    let attempt = 0
    let retry: ReturnType<typeof setTimeout> | undefined
    let currentIdentity = identity
    setState(initialState)
    setRole(null)
    setLocalPlayerId(null)
    setLastError(null)
    authenticatedRef.current = false

    function detach() {
      clearTimeout(retry)
      retry = undefined
      const socket = socketRef.current
      socketRef.current = null
      authenticatedRef.current = false
      socket?.close()
    }
    function persist(autoResume: boolean) {
      if (!currentIdentity) return
      const ownsStorage = ownsStoredIdentity()
      currentIdentity = { ...currentIdentity, autoResume }
      if (ownsStorage) storeIdentity(currentIdentity)
    }
    function ownsStoredIdentity() {
      const stored = loadStoredIdentity()
      return stored !== null && stored.code === currentIdentity?.code
        && stored.localPlayerId === currentIdentity.localPlayerId && stored.sessionToken === currentIdentity.sessionToken
    }
    function terminal(code: string) {
      const endings: Record<string, [ConnectionStatus, string]> = {
        session_revoked: ['revoked', 'Session indisponible. Rejoignez explicitement une room.'],
        player_kicked: ['kicked', 'Vous avez été retiré de la room.'],
        room_closed: ['closed', 'Room fermée ou indisponible. Les sessions ne survivent pas au redémarrage du serveur.'],
        session_replaced: ['replaced', 'Session ouverte ailleurs. Reprendre ici remplacera cette autre connexion.'],
      }
      const ending = endings[code]
      stopped = true
      detach()
      if (code === 'session_replaced') persist(false)
      else if (ending) {
        if (ownsStoredIdentity()) clearStoredIdentity()
        currentIdentity = null
      } else persist(false)
      setStatus(ending?.[0] ?? 'policy-error')
      setLastError({ code, message: ending?.[1] ?? 'Connexion refusée par la politique du serveur. Reprise explicite nécessaire.' })
    }
    function reconnect() {
      if (cancelled || stopped || retry !== undefined) return
      detach()
      setStatus('reconnecting')
      const cap = Math.min(30000, 500 * 2 ** Math.min(attempt, 6))
      attempt += 1
      retry = setTimeout(() => {
        retry = undefined
        connect()
      }, cap * (0.5 + Math.random() * 0.5))
    }
    function connect() {
      if (cancelled || stopped || !currentIdentity) return
      setStatus('connecting')
      let socket: WebSocket
      try { socket = new WebSocket(`${wsBaseUrl()}/ws/${currentIdentity.code}`) }
      catch { reconnect(); return }
      socketRef.current = socket
      const isCurrent = () => !cancelled && !stopped && socketRef.current === socket
      socket.onopen = () => {
        if (!isCurrent()) return
        try {
          socket.send(JSON.stringify({ type: 'session:auth', payload: {
            localPlayerId: currentIdentity!.localPlayerId, sessionToken: currentIdentity!.sessionToken,
          } }))
        } catch { reconnect() }
      }
      socket.onmessage = (event) => {
        if (!isCurrent()) return
        let message
        try { message = JSON.parse(event.data) } catch { return }
        if (!message || typeof message !== 'object') return
        if (message.type === 'session:ended') terminal(message.payload?.code)
        else if (message.type === 'room:closed') terminal('room_closed')
        else if (message.type === 'player:kicked') terminal('player_kicked')
        else if (message.type === 'room:state_sync') {
          const payload = message.payload
          if (!payload || !currentIdentity || payload.code !== currentIdentity.code || payload.localPlayerId !== currentIdentity.localPlayerId
            || !['presentateur', 'joueur', 'ecran-principal'].includes(payload.role) || !payload.state) return
          authenticatedRef.current = true
          attempt = 0
          setStatus('open')
          setRole(payload.role)
          setLocalPlayerId(payload.localPlayerId)
          setState(payload.state)
          setLastError(null)
        } else if (message.type === 'error' && authenticatedRef.current) {
          setLastError(message.payload as ErrorPayload)
        }
      }
      // Browsers emit close after error; wait for its authoritative terminal code.
      socket.onerror = () => { if (isCurrent()) authenticatedRef.current = false }
      socket.onclose = (event) => {
        if (!isCurrent()) return
        const endings: Record<number, string> = { 4401: 'session_revoked', 4403: 'player_kicked', 4404: 'room_closed', 4409: 'session_replaced' }
        if (endings[event.code]) terminal(endings[event.code])
        else if ([1008, 1009, 4429].includes(event.code)) terminal(`policy_${event.code}`)
        else reconnect()
      }
    }
    disconnectRef.current = () => {
      stopped = true
      persist(false)
      detach()
      setStatus('disconnected')
      setLastError({ code: 'voluntary_disconnect', message: 'Déconnecté volontairement. Reprenez explicitement votre session.' })
    }
    resumeRef.current = () => {
      if (!currentIdentity || cancelled) return
      detach()
      stopped = false
      persist(true)
      setLastError(null)
      connect()
    }
    if (!identity) setStatus('idle')
    else if (identity.autoResume) connect()
    else {
      setStatus('disconnected')
      setLastError({ code: 'resume_required', message: 'Session conservée. Reprise explicite nécessaire.' })
    }
    return () => {
      cancelled = true
      detach()
      disconnectRef.current = () => {}
      resumeRef.current = () => {}
    }
  }, [identity])

  const send = useCallback((message: OutgoingMessage) => {
    const socket = socketRef.current
    if (!authenticatedRef.current || !socket || socket.readyState !== WebSocket.OPEN) return
    try { socket.send(JSON.stringify(message)) } catch { /* Never queue or replay an action. */ }
  }, [])

  const disconnect = useCallback(() => {
    disconnectRef.current()
  }, [])
  const resume = useCallback(() => resumeRef.current(), [])

  return { status, state, role, localPlayerId, lastError, send, disconnect, resume }
}
