import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { GameState } from './game/types'
import type { Identity, Role } from './net/types'
import {
  clearStoredIdentity,
  loadStoredIdentity,
  storeIdentity,
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
import { useAudio } from './audio/AudioContext'

function renderScreen(
  phase: string,
  state: GameState,
  dispatch: ReturnType<typeof createNetworkDispatch>,
  role: Role,
  localPlayerId: string | null,
  roomCode: string,
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
function ConnectingScreen() {
  return (
    <ScreenShell spotlight smoke>
      <div className="flex flex-1 flex-col items-center justify-center gap-4">
        <p className="text-xs tracking-[0.3em] text-[#9a8d7d] uppercase">Connexion à la room…</p>
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
  // Identité de connexion (code de room + local_player_id) + message
  // d'erreur éventuel à afficher sur l'accueil, regroupés dans un seul état
  // pour n'avoir qu'une seule mutation par transition. null tant que
  // l'utilisateur n'a pas créé/rejoint de room via AccueilScreen, ou après un
  // room:closed / reconnexion impossible.
  const [session, setSession] = useState<{ identity: Identity | null; connectError: string | null }>(
    () => ({ identity: loadStoredIdentity(), connectError: null }),
  )
  const { identity, connectError } = session

  const connection = useRoomConnection(identity)

  const handleConnected = useCallback((newIdentity: Identity) => {
    storeIdentity(newIdentity)
    setSession({ identity: newIdentity, connectError: null })
  }, [])

  // Synchronise l'état local avec le cycle de vie externe de la connexion
  // WebSocket (voir net/useRoomConnection.ts) : si la room a été fermée côté
  // serveur (quit du Présentateur) ou si la connexion a définitivement
  // échoué (room introuvable/expirée après un redémarrage serveur, la
  // persistance étant en mémoire uniquement — voir
  // docs/websocket-protocol.md, section Limitations connues), on efface
  // l'identité et on repart sur l'accueil avec un message clair.
  useEffect(() => {
    if (!identity) return
    if (connection.status === 'closed') {
      clearStoredIdentity()
      setSession({ identity: null, connectError: 'La room a été fermée par le Présentateur.' })
    } else if (connection.status === 'error') {
      clearStoredIdentity()
      setSession({
        identity: null,
        connectError: 'Connexion perdue. La room est peut-être introuvable ou le serveur a redémarré.',
      })
    }
  }, [connection.status, identity])

  // ── Ambiance jazz : gérée au niveau de l'App pour persister entre phases ──
  // Jazz démarre dès selection-pending et tourne en continu (tunnel inclus).
  // S'arrête uniquement quand on revient au lobby ou à l'écran de fin.
  // Tous les hooks sont appelés inconditionnellement (règle des hooks React).
  const { startAmbient, stopAmbient } = useAudio()
  const phase = connection.state.phase
  useEffect(() => {
    if (phase === 'lobby') {
      stopAmbient()
    } else if (phase === 'selection-pending' || phase === 'selection' || phase === 'tunnel') {
      startAmbient('jazz')
    } else if (phase === 'end') {
      stopAmbient()
    }
  // On ne veut relancer l'ambiance QUE sur les changements de phase clés,
  // pas à chaque re-render. startAmbient/stopAmbient sont stables (useCallback).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase])

  // Aucune identité connue (ni fournie, ni retrouvée en localStorage) ->
  // écran d'accueil pour créer/rejoindre une room.
  if (!identity) {
    return <AccueilScreen onConnected={handleConnected} initialError={connectError} />
  }

  // Le useEffect ci-dessus efface l'identité de façon asynchrone sur
  // closed/error ; en attendant le prochain rendu (identity encore non-null
  // le temps du cycle courant), on affiche un écran de connexion neutre
  // plutôt que de muter l'état pendant le rendu.
  if (connection.status === 'idle' || connection.status === 'connecting' || !connection.role) {
    return <ConnectingScreen />
  }

  const dispatch = createNetworkDispatch(connection.send)
  const { state, role, localPlayerId } = connection

  // Un Joueur quitte SA partie individuellement : ferme sa propre connexion
  // et efface son identité locale pour revenir à l'accueil (il peut
  // rejoindre à nouveau la même room plus tard avec le code). Les autres
  // participants le voient simplement marqués absents côté serveur — contraste
  // avec "Terminer la partie" (END_GAME_EARLY) qui est une action du
  // Présentateur affectant toute la room sans déconnecter personne.
  function handleLeave() {
    connection.disconnect()
    clearStoredIdentity()
    setSession({ identity: null, connectError: null })
  }

  return (
    <>
      {shouldShowControls(state.phase) && (
        <GameControls dispatch={dispatch} role={role} onLeave={handleLeave} />
      )}
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
          {renderScreen(state.phase, state, dispatch, role, localPlayerId, identity.code)}
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
