/**
 * URL de base du backend.
 *
 * - En production (Bloc 9, service unique) : le frontend est servi par le
 *   même process FastAPI que l'API/WS, donc l'URL de base doit être une
 *   chaîne vide (chemins relatifs, même origine que la page). Utiliser une
 *   URL absolue en dur ici (ex. http://127.0.0.1:8000) serait FAUX en
 *   production — ça pointerait vers la machine du visiteur, pas vers le
 *   serveur, et déclenche en plus la demande "Private Network Access" du
 *   navigateur quand une page publique tente de joindre une IP privée.
 * - En dev (`npm run dev`), Vite et uvicorn tournent sur deux ports
 *   distincts : on utilise alors http://127.0.0.1:8000 par défaut.
 *
 * Surchargeable dans tous les cas via la variable d'environnement Vite
 * VITE_API_BASE_URL (utile par ex. pour tester depuis un autre appareil du
 * réseau local en pointant vers l'IP de la machine de dev).
 */
const DEFAULT_API_BASE_URL = import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? DEFAULT_API_BASE_URL

export function wsBaseUrl(): string {
  if (API_BASE_URL) {
    return API_BASE_URL.replace(/^http/, 'ws')
  }
  // Même origine que la page : dérive ws(s):// à partir de la protocole
  // actuelle (http -> ws, https -> wss), nécessaire car les WebSocket
  // n'acceptent pas d'URL relative sans scheme explicite.
  const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${wsProtocol}://${window.location.host}`
}
