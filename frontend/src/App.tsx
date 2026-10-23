import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { GameState } from './game/types'
import type { Identity, Role } from './net/types'
import {
  clearStoredIdentity,
  loadStoredIdentity,
  storeIdentity,
  hasLegacyIdentity,
  useRoomConnection,
} from './net/useRoomConnection'
import { createNetworkDispatch } from './net/dispatchAdapter'
import { AccueilScreen } from './screens/AccueilScreen'
import { LobbyScreen } from './screens/LobbyScreen'
import { SelectionScreen } from './screens/SelectionScreen'
import { TunnelScreen } from './screens/TunnelScreen'
import { EndScreen } from './screens/EndScreen'
import { StyleguideScreen } from './screens/StyleguideScreen'
import { ScreenShell } from './components/ScreenShell'
import { GameControls } from './components/GameControls'
import { CurtainClose } from './components/decor/CurtainClose'
import { MuteButton } from './components/MuteButton'
import { Button } from './components/Button'
import { useAudio } from './audio/AudioContext'

function renderScreen(
  phase: string,
  state: GameState,
  dispatch: ReturnType<typeof createNetworkDispatch>,
  role: Role,
  localPlayerId: string | null,
  roomCode: string,
  onTransferPresenter: (targetPlayerId: string) => void,
) {
  switch (phase) {
    case 'lobby':
      return (
        <LobbyScreen
          state={state}
          dispatch={dispatch}
          role={role}
          localPlayerId={localPlayerId}
          roomCode={roomCode}
          onTransferPresenter={onTransferPresenter}
        />
      )
    // Couche show : choix de thème pas encore révélé par le Présentateur.
    // Contrairement à Continuer/Coffrer, la grille de thèmes reste visible
    // (juste non cliquable) — c'est SelectionScreen qui gère les deux
    // phases selection-pending/selection pour ne jamais démonter/remonter
    // la grille entre les deux (voir SelectionScreen.tsx).
    case 'selection-pending':
    case 'selection':
      return <SelectionScreen state={state} dispatch={dispatch} role={role} localPlayerId={localPlayerId} />
    case 'tunnel':
      return (
        <TunnelScreen state={state} dispatch={dispatch} role={role} localPlayerId={localPlayerId} />
      )
    case 'end':
      return <EndScreen state={state} dispatch={dispatch} role={role} />
    default:
      return (
        <LobbyScreen
          state={state}
          dispatch={dispatch}
          role={role}
          localPlayerId={localPlayerId}
          roomCode={roomCode}
          onTransferPresenter={onTransferPresenter}
        />
      )
  }
}

/** La barre de contrôle (Terminer la partie / Quitter la partie) n'a pas de
 * sens tant qu'on est encore au lobby (pas de partie en cours à quitter). */
function shouldShowControls(phase: string): boolean {
  return phase !== 'lobby'
}

/** Écran neutre pendant la connexion/reconnexion WebSocket. */
function ConnectingScreen({ error, resume }: { error?: string; resume: () => void }) {
  return (
    <ScreenShell spotlight smoke>
      <div className="flex flex-1 flex-col items-center justify-center gap-4">
        <p className="text-xs tracking-[0.3em] text-[#9a8d7d] uppercase">Connexion à la room…</p>
        {error && <p role="status" className="max-w-lg px-4 text-center text-sm text-amber-glow">{error}</p>}
        {error && <Button variant="gold" onClick={resume}>Reprendre la session</Button>}
      </div>
    </ScreenShell>
  )
}

function App() {
  // Route de démonstration interne du design system (Bloc 6), atteignable
  // via ?debug=styleguide — jamais exposée dans le flux de jeu normal, et
  // totalement indépendante du réseau (pas de room, pas de WebSocket).
  const isStyleguide =
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).get('debug') === 'styleguide'

  if (isStyleguide) {
    return (
      <StyleguideScreen
        dispatch={(action) => {
          if (action.type === 'QUIT_TO_MENU') {
            window.location.href = window.location.pathname
          }
        }}
      />
    )
  }

  return <AppConnected />
}

/**
 * Sous-composant monté uniquement hors mode styleguide.
 * Tous les hooks (useRoomConnection, useAudio, useEffect…) sont appelés de
 * façon inconditionnelle ici — React error #310 corrigé (les hooks étaient
 * auparavant appelés après des `return` conditionnels dans App).
 */
function AppConnected() {
  // Keep the private identity stable during transport recovery; only explicit
  // create/join or forgetting a session replaces this controller's identity.
  const [session, setSession] = useState<{ identity: Identity | null; connectError: string | null; persistenceUnavailable?: boolean }>(
    () => ({ identity: loadStoredIdentity(), connectError: hasLegacyIdentity()
      ? 'Ancienne session sans preuve privée. Rejoignez explicitement une room pour continuer.' : null }),
  )
  const { identity, connectError } = session

  const connection = useRoomConnection(identity, session.persistenceUnavailable)

  const handleConnected = useCallback((newIdentity: Identity, persistenceUnavailable = false) => {
    storeIdentity(newIdentity)
    setSession({ identity: newIdentity, connectError: null, persistenceUnavailable })
  }, [])

  // ── Ambiance jazz : gérée au niveau de l'App pour persister entre phases ──
  // Jazz démarre dès selection-pending et tourne en continu (tunnel inclus).
  // S'arrête uniquement quand on revient au lobby ou à l'écran de fin.
  // Tous les hooks sont appelés inconditionnellement (règle des hooks React).
  const { startAmbient, stopAmbient } = useAudio()
  const phase = connection.state.phase
  useEffect(() => {
    if (connection.status !== 'open' || phase === 'lobby') {
      stopAmbient()
    } else if (phase === 'selection-pending' || phase === 'selection' || phase === 'tunnel') {
      startAmbient('jazz')
    } else if (phase === 'end') {
      stopAmbient()
    }
   // Presence-only snapshots must not restart the ambience.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, connection.status])

  // Aucune identité connue (ni fournie, ni retrouvée en localStorage) ->
  // écran d'accueil pour créer/rejoindre une room.
  if (!identity) {
    return <AccueilScreen onConnected={handleConnected} initialError={connectError} />
  }

  if (['closed', 'kicked', 'revoked'].includes(connection.status)) {
    return <AccueilScreen onConnected={handleConnected} initialError={connection.lastError?.message} />
  }

  if (['disconnected', 'replaced', 'policy-error'].includes(connection.status)) {
    return (
      <ScreenShell spotlight smoke>
        <div className="flex flex-1 flex-col items-center justify-center gap-6 px-4 text-center">
          <p role="status" className="max-w-lg text-sm text-amber-glow">{connection.lastError?.message}</p>
          <Button variant="gold" onClick={connection.resume}>Reprendre la session</Button>
          <Button variant="secondary" onClick={() => {
            const stored = loadStoredIdentity()
            if (stored?.code === identity.code && stored.localPlayerId === identity.localPlayerId
              && stored.sessionToken === identity.sessionToken) clearStoredIdentity()
            setSession({ identity: null, connectError: null })
          }}>Oublier cette session</Button>
        </div>
      </ScreenShell>
    )
  }

  if (connection.status !== 'open' || !connection.role) {
    return (
      <div>
        <ConnectingScreen error={connection.lastError?.message} resume={connection.resume} />
        <button className="fixed bottom-6 left-1/2 -translate-x-1/2 text-sm text-amber-glow" onClick={connection.disconnect}>
          Arrêter la reconnexion
        </button>
      </div>
    )
  }

  const dispatch = createNetworkDispatch(connection.send)
  const { state, role, localPlayerId } = connection

  function handleLeave() {
    connection.disconnect()
  }

  function handleTransferPresenter(targetPlayerId: string) {
    connection.send({ type: 'presenter:transfer', payload: { targetPlayerId } })
  }

  return (
    <>
      {shouldShowControls(state.phase) && (
        <GameControls dispatch={dispatch} role={role} onLeave={handleLeave}
          canReset={state.themes.length > 0 && state.players.some((p) => !p.isPresenter && p.connected)} />
      )}
      <button className="fixed top-3 left-3 z-30 rounded-full border border-white/15 bg-charcoal-900/90 px-3 py-2 text-xs text-[#d8c9b0]"
        onClick={handleLeave}>Se déconnecter</button>
      {connection.lastError && <p role="alert" className="fixed bottom-4 left-1/2 z-40 max-w-lg -translate-x-1/2 rounded-xl bg-charcoal-900 p-3 text-center text-sm text-amber-glow">{connection.lastError.message}</p>}
      <TunnelExitCurtain phase={state.phase} />
      {/* Bouton mute flottant — visible sur tous les écrans de jeu */}
      <MuteButton />
      {/* Balayage lumineux théâtral à chaque changement d'écran, façon rideau qui se lève */}
      <AnimatePresence mode="wait">
        <motion.div
          key={state.phase}
          initial={{ opacity: 0, scale: 0.985 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 1.01 }}
          transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
        >
          <div key={`sweep-${state.phase}`} className="light-sweep" aria-hidden="true" />
          {renderScreen(state.phase, state, dispatch, role, localPlayerId, identity.code, handleTransferPresenter)}
        </motion.div>
      </AnimatePresence>
    </>
  )
}

/**
 * Rideau de FERMETURE joué à chaque sortie du tunnel vers l'écran Sélection
 * (mauvaise réponse, Passer, Descendre, ou coffrage automatique case 10 —
 * peu importe la cause exacte, seule la transition de phase compte). Le
 * rideau d'ouverture, lui, reste réservé à l'entrée dans le tunnel (géré
 * séparément par CurtainReveal dans TunnelScreen.tsx via key=activeThemeIndex).
 * Ce composant ne fait que détecter la transition tunnel -> !tunnel et
 * monter l'overlay CurtainClose par-dessus l'écran déjà affiché dessous.
 */
function TunnelExitCurtain({ phase }: { phase: string }) {
  const prevPhaseRef = useRef(phase)
  const [closing, setClosing] = useState(false)

  useEffect(() => {
    if (prevPhaseRef.current === 'tunnel' && phase !== 'tunnel' && phase !== 'end') {
      setClosing(true)
    }
    prevPhaseRef.current = phase
  }, [phase])

  if (!closing) return null
  return <CurtainClose onDone={() => setClosing(false)} />
}

export default App
