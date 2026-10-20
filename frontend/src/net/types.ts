/**
 * Rôle réseau assigné par le serveur de room à la connexion WebSocket (voir
 * docs/websocket-protocol.md). Remplace l'ancien `ViewRole` local de
 * src/viewRole.ts qui ne servait qu'à prévisualiser les vues sans réseau.
 */
export type Role = 'presentateur' | 'joueur' | 'ecran-principal'

/** Identité de connexion à une room, persistée en localStorage pour permettre
 * la reconnexion (voir docs/websocket-protocol.md, section "Reconnexion"). */
export type Identity = {
  version: 2
  code: string
  localPlayerId: string
  sessionToken: string
  autoResume: boolean
}

export type ErrorPayload = {
  code: string
  message: string
}
