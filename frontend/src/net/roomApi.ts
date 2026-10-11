import type { Role } from './types'
import { API_BASE_URL } from './config'

export type CreateRoomResult = {
  code: string
  localPlayerId: string
  role: 'presentateur'
}

export type JoinRoomResult = {
  code: string
  localPlayerId: string
  role: Role
  // L'état complet n'est pas utilisé directement (le client WS réémet un
  // room:state_sync juste après l'ouverture du socket), mais renvoyé par
  // l'API pour permettre un affichage immédiat avant connexion WS si besoin.
  state: unknown
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // ignore, on garde statusText
    }
    throw new Error(detail || `Erreur HTTP ${response.status}`)
  }
  return (await response.json()) as T
}

export async function createRoom(pseudo: string): Promise<CreateRoomResult> {
  const response = await fetch(`${API_BASE_URL}/api/rooms`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pseudo }),
  })
  return parseJsonOrThrow<CreateRoomResult>(response)
}

export async function joinRoom(
  code: string,
  pseudo: string,
  role: 'joueur' | 'ecran-principal' = 'joueur',
  localPlayerId?: string,
): Promise<JoinRoomResult> {
  const response = await fetch(`${API_BASE_URL}/api/rooms/${code.toUpperCase()}/join`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pseudo, role, localPlayerId }),
  })
  return parseJsonOrThrow<JoinRoomResult>(response)
}
