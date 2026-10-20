import { beforeEach, describe, expect, it, vi } from 'vitest'
import { clearStoredIdentity, hasLegacyIdentity, isIdentity, loadStoredIdentity, storeIdentity } from './identity'

const key = 'legrandtunneg:identity:v2'
const legacy = 'legrandtunneg:identity'
const valid = {
  version: 2 as const,
  code: 'ABCD',
  localPlayerId: 'ecaa8b4a-762f-4dc2-8b3c-f270f512a45f',
  sessionToken: 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8',
  autoResume: true,
}

beforeEach(() => localStorage.clear())

describe('strict versioned session storage', () => {
  it('accepts server-generated room codes containing digits', () => {
    const identity = { ...valid, code: 'AB23' }
    storeIdentity(identity)
    expect(loadStoredIdentity()).toEqual(identity)
  })
  it('round trips both autoResume choices without storing a trusted role', () => {
    for (const autoResume of [true, false]) {
      const identity = { ...valid, autoResume }
      storeIdentity(identity)
      expect(loadStoredIdentity()).toEqual(identity)
      expect(Object.keys(JSON.parse(localStorage.getItem(key)!)).sort()).toEqual(Object.keys(valid).sort())
    }
    clearStoredIdentity()
    expect(loadStoredIdentity()).toBeNull()
  })

  it.each([
    null, [], 'identity', 2, {},
    { ...valid, version: 1 }, { ...valid, version: '2' },
    { ...valid, code: 'abcd' }, { ...valid, code: 'ABCDE' }, { ...valid, code: 'AB1D' },
    { ...valid, localPlayerId: valid.localPlayerId.toUpperCase() },
    { ...valid, localPlayerId: 'not-a-uuid' },
    { ...valid, sessionToken: 'x'.repeat(42) }, { ...valid, sessionToken: 'x'.repeat(44) },
    { ...valid, sessionToken: 'A'.repeat(42) + 'B' },
    { ...valid, sessionToken: '+'.repeat(42) + 'A' },
    { ...valid, autoResume: 'true' }, { ...valid, autoResume: 1 },
    { ...valid, role: 'presentateur' },
    { version: 2, code: valid.code, localPlayerId: valid.localPlayerId, autoResume: true },
  ])('rejects invalid persisted shape %#', (value) => {
    localStorage.setItem(key, JSON.stringify(value))
    expect(isIdentity(value)).toBe(false)
    expect(loadStoredIdentity()).toBeNull()
  })

  it('rejects malformed JSON and never uses the legacy identity as proof', () => {
    localStorage.setItem(key, '{invalid')
    localStorage.setItem(legacy, JSON.stringify(valid))
    expect(loadStoredIdentity()).toBeNull()
    expect(hasLegacyIdentity()).toBe(true)
    localStorage.removeItem(key)
    expect(loadStoredIdentity()).toBeNull()
    storeIdentity(valid)
    expect(hasLegacyIdentity()).toBe(false)
    expect(loadStoredIdentity()).toEqual(valid)
  })

  it.each(['code', 'localPlayerId', 'sessionToken'] as const)('rejects trailing line endings in %s rather than accepting a regex end anchor', (field) => {
    for (const suffix of ['\n', '\r', '\r\n']) {
      const value = { ...valid, [field]: valid[field] + suffix }
      localStorage.setItem(key, JSON.stringify(value))
      expect(isIdentity(value)).toBe(false)
      expect(loadStoredIdentity()).toBeNull()
      expect(() => storeIdentity(value)).toThrow('Identité de session invalide.')
    }
  })

  it('survives unavailable browser storage without preventing a live session', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('disabled') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('disabled') })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('disabled') })
    expect(loadStoredIdentity()).toBeNull()
    expect(hasLegacyIdentity()).toBe(false)
    expect(() => storeIdentity(valid)).not.toThrow()
    expect(() => clearStoredIdentity()).not.toThrow()
  })
})
