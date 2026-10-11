import { useState } from 'react'
import { ScreenShell } from '../components/ScreenShell'
import { Button } from '../components/Button'
import { ArtDecoCorner } from '../components/decor/ArtDecoCorner'
import { createRoom, joinRoom } from '../net/roomApi'
import type { Identity } from '../net/types'

type AccueilScreenProps = {
  onConnected: (identity: Identity) => void
  /** Message d'erreur à afficher si une tentative de reconnexion a échoué
   * (room introuvable/expirée) — voir App.tsx. */
  initialError?: string | null
}

type Mode = 'create' | 'join'

/**
 * Écran d'accueil du mode room multi (Bloc 7, scope de cette session) :
 * création d'une room (le créateur devient Présentateur) ou jointure d'une
 * room existante via son code (en tant que Joueur ou Écran principal).
 *
 * Le mode "Créer une room solo" (hotseat mono-écran, Bloc 7bis) n'est pas
 * implémenté dans cette passe — hors scope de la session en cours, voir
 * docs/exec-plans/reconstruction-le-grand-tunneg.md.
 */
export function AccueilScreen({ onConnected, initialError = null }: AccueilScreenProps) {
  const [mode, setMode] = useState<Mode>('create')
  const [pseudo, setPseudo] = useState('')
  const [code, setCode] = useState('')
  const [joinRole, setJoinRole] = useState<'joueur' | 'ecran-principal'>('joueur')
  const [error, setError] = useState<string | null>(initialError)
  const [busy, setBusy] = useState(false)

  async function handleCreate() {
    if (!pseudo.trim()) return
    setBusy(true)
    setError(null)
    try {
      const result = await createRoom(pseudo.trim())
      onConnected({ code: result.code, localPlayerId: result.localPlayerId })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur inconnue.')
    } finally {
      setBusy(false)
    }
  }

  async function handleJoin() {
    if (!pseudo.trim() || !code.trim()) return
    setBusy(true)
    setError(null)
    try {
      const result = await joinRoom(code.trim(), pseudo.trim(), joinRole)
      onConnected({ code: result.code, localPlayerId: result.localPlayerId })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur inconnue.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <ScreenShell spotlight smoke>
      <div className="flex flex-1 flex-col items-center justify-center gap-10">
        <div className="animate-rise-up text-center">
          <p className="mb-2 text-xs tracking-[0.5em] text-brass-400/80 uppercase">
            ★ Ce soir, sur scène ★
          </p>
          <h1 className="marquee-text font-display text-5xl font-black tracking-wide sm:text-7xl">
            Le Grand Tunneg
          </h1>
          <p className="mt-3 text-sm tracking-[0.3em] text-[#9a8d7d] uppercase">
            Créez une room ou rejoignez-en une
          </p>
        </div>

        <div className="string-lights animate-rise-up relative w-full max-w-md rounded-2xl border border-brass-600/30 bg-gradient-to-b from-charcoal-800 to-charcoal-900 p-6 shadow-stage-lg">
          <ArtDecoCorner position="top-left" />
          <ArtDecoCorner position="top-right" />
          <ArtDecoCorner position="bottom-left" />
          <ArtDecoCorner position="bottom-right" />

          <div className="mb-5 flex justify-center gap-1 rounded-full border border-brass-600/30 bg-charcoal-950/60 p-1 text-xs">
            <button
              onClick={() => setMode('create')}
              className={`flex-1 rounded-full px-4 py-2 font-medium tracking-wide uppercase transition-all ${
                mode === 'create'
                  ? 'bg-gradient-to-b from-amber-glow to-amber-ember text-charcoal-950'
                  : 'text-[#d8c9b0] hover:bg-white/5'
              }`}
            >
              Créer une room
            </button>
            <button
              onClick={() => setMode('join')}
              className={`flex-1 rounded-full px-4 py-2 font-medium tracking-wide uppercase transition-all ${
                mode === 'join'
                  ? 'bg-gradient-to-b from-amber-glow to-amber-ember text-charcoal-950'
                  : 'text-[#d8c9b0] hover:bg-white/5'
              }`}
            >
              Rejoindre
            </button>
          </div>

          <div className="flex flex-col gap-3">
            <input
              type="text"
              value={pseudo}
              onChange={(e) => setPseudo(e.target.value)}
              placeholder="Votre pseudo"
              maxLength={24}
              className="rounded-lg border border-brass-600/30 bg-charcoal-900/80 px-4 py-2.5 text-[#f1e6d8] placeholder-[#6b625b] shadow-[inset_0_2px_6px_rgba(0,0,0,0.4)] outline-none focus:border-amber-glow focus:shadow-[inset_0_2px_6px_rgba(0,0,0,0.4),0_0_0_3px_rgba(232,163,61,0.2)]"
            />

            {mode === 'join' && (
              <>
                <input
                  type="text"
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  placeholder="Code de la room"
                  maxLength={4}
                  className="rounded-lg border border-brass-600/30 bg-charcoal-900/80 px-4 py-2.5 text-center font-display text-lg tracking-[0.3em] text-[#f1e6d8] placeholder-[#6b625b] placeholder:tracking-normal shadow-[inset_0_2px_6px_rgba(0,0,0,0.4)] outline-none focus:border-amber-glow focus:shadow-[inset_0_2px_6px_rgba(0,0,0,0.4),0_0_0_3px_rgba(232,163,61,0.2)]"
                />
                <div className="flex justify-center gap-1 rounded-full border border-brass-600/20 bg-charcoal-950/40 p-1 text-xs">
                  <button
                    onClick={() => setJoinRole('joueur')}
                    className={`flex-1 rounded-full px-3 py-1.5 font-medium tracking-wide transition-all ${
                      joinRole === 'joueur'
                        ? 'bg-brass-600/60 text-[#f1e6d8]'
                        : 'text-[#9a8d7d] hover:bg-white/5'
                    }`}
                  >
                    Joueur
                  </button>
                  <button
                    onClick={() => setJoinRole('ecran-principal')}
                    className={`flex-1 rounded-full px-3 py-1.5 font-medium tracking-wide transition-all ${
                      joinRole === 'ecran-principal'
                        ? 'bg-brass-600/60 text-[#f1e6d8]'
                        : 'text-[#9a8d7d] hover:bg-white/5'
                    }`}
                  >
                    Écran principal
                  </button>
                </div>
              </>
            )}
          </div>

          {error && (
            <p className="mt-4 text-center text-xs text-burgundy-500">{error}</p>
          )}
        </div>

        <Button
          variant="gold"
          className="animate-rise-up px-10 py-3 text-base"
          disabled={busy || !pseudo.trim() || (mode === 'join' && !code.trim())}
          onClick={mode === 'create' ? handleCreate : handleJoin}
        >
          {busy ? 'Connexion…' : mode === 'create' ? 'Créer la room' : 'Rejoindre la room'}
        </Button>
      </div>
    </ScreenShell>
  )
}
