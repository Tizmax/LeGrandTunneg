/**
 * URLs du backend. En dev, le frontend Vite (http://localhost:5173) et le
 * backend FastAPI (http://127.0.0.1:8000) tournent sur deux ports distincts
 * (voir backend/app/main.py, CORS ouvert en dev) tant que le Bloc 9
 * (packaging Railway en service unique) n'est pas en place.
 *
 * Surchargeable via la variable d'environnement Vite VITE_API_BASE_URL.
 */
const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000'

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? DEFAULT_API_BASE_URL

export function wsBaseUrl(): string {
  return API_BASE_URL.replace(/^http/, 'ws')
}
