/**
 * Rôle réseau assigné par le serveur de room à la connexion WebSocket (voir
 * docs/websocket-protocol.md). Remplace l'ancien `ViewRole` local de
 * src/viewRole.ts qui ne servait qu'à prévisualiser les vues sans réseau.
 */
export type Role = 'presentateur' | 'joueur' | 'ecran-principal'

/** Identité de connexion à une room, persistée en localStorage pour permettre
 * la reconnexion (voir docs/websocket-protocol.md, section "Reconnexion"). */
export type Identity = {
  code: string
  localPlayerId: string
}

export type ErrorPayload = {
  code: 'forbidden_role' | 'not_your_turn' | 'invalid_phase' | 'invalid_payload' | 'room_not_found'
  message: string
}
