import { afterEach, expect, it, vi } from 'vitest'
import { createRoom, joinRoom } from './roomApi'

afterEach(() => vi.unstubAllGlobals())

it('creates new membership using only the name, without identity in the URL', async () => {
  const response = { code: 'ABCD', localPlayerId: 'public-id', role: 'presentateur', sessionToken: 'proof' }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(response)))
  vi.stubGlobal('fetch', fetchMock)
  expect(await createRoom('Alice')).toEqual(response)
  const [url, init] = fetchMock.mock.calls[0]
  expect(url).toMatch(/\/api\/rooms$/)
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body)).toEqual({ pseudo: 'Alice' })
})

it('normalizes join codes and sends only new-membership fields', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetchMock)
  await joinRoom('abcd', 'Alice', 'ecran-principal')
  const [url, init] = fetchMock.mock.calls[0]
  expect(url).toMatch(/\/api\/rooms\/ABCD\/join$/)
  expect(JSON.parse(init.body)).toEqual({ pseudo: 'Alice', role: 'ecran-principal' })
})

it.each([
  [{ detail: { code: 'session_revoked', message: 'Session unavailable.' } }, 'Session unavailable.'],
  [{ detail: 'Room unavailable.' }, 'Room unavailable.'],
])('preserves structured or legacy HTTP error explanations', async (body, message) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 401 })))
  await expect(createRoom('Alice')).rejects.toThrow(message)
})
