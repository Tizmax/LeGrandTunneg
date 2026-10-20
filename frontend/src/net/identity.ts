import type { Identity } from './types'

const STORAGE_KEY = 'legrandtunneg:identity:v2'
const LEGACY_KEY = 'legrandtunneg:identity'

export function isIdentity(value: unknown): value is Identity {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const data = value as Record<string, unknown>
  return Object.keys(data).sort().join(',') === 'autoResume,code,localPlayerId,sessionToken,version'
    && data.version === 2
    && typeof data.code === 'string' && data.code.length === 4 && /^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{4}$/.test(data.code)
    && typeof data.localPlayerId === 'string' && data.localPlayerId.length === 36
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(data.localPlayerId)
    && typeof data.sessionToken === 'string' && data.sessionToken.length === 43
    && /^[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]$/.test(data.sessionToken)
    && typeof data.autoResume === 'boolean'
}

export function loadStoredIdentity(): Identity | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const value: unknown = raw ? JSON.parse(raw) : null
    return isIdentity(value) ? value : null
  } catch { return null }
}

export function hasLegacyIdentity(): boolean {
  try { return localStorage.getItem(LEGACY_KEY) !== null } catch { return false }
}

export function storeIdentity(identity: Identity): void {
  if (!isIdentity(identity)) throw new Error('Identité de session invalide.')
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(identity))
    localStorage.removeItem(LEGACY_KEY)
  } catch { /* Storage may be disabled; the live session remains usable. */ }
}

export function clearStoredIdentity(): void {
  try { localStorage.removeItem(STORAGE_KEY) } catch { /* Storage unavailable. */ }
}
