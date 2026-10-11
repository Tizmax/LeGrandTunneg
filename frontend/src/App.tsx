import { useCallback, useEffect, useState } from 'react'
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
import { MenuScreen } from './screens/MenuScreen'
import { ThemesScreen } from './screens/ThemesScreen'
import { SelectionScreen } from './screens/SelectionScreen'
import { TunnelScreen } from './screens/TunnelScreen'
import { EndScreen } from './screens/EndScreen'
import { ChoicePendingScreen } from './screens/ChoicePendingScreen'
import { StyleguideScreen } from './screens/StyleguideScreen'
import { ScreenShell } from './components/ScreenShell'

function renderScreen(
  phase: string,
  state: GameState,
  dispatch: ReturnType<typeof createNetworkDispatch>,
  role: Role,
  localPlayerId: string | null,
  roomCode: string,
) {
  switch (phase) {
    case 'menu':
      return <MenuScreen state={state} dispatch={dispatch} role={role} roomCode={roomCode} />
    case 'themes':
      return <ThemesScreen state={state} dispatch={dispatch} role={role} />
    // Couche show : choix de thème pas encore révélé par le Présentateur.
    case 'selection-pending':
      return (
        <ChoicePendingScreen state={state} dispatch={dispatch} isPresenterView={role === 'presentateur'} />
      )
    case 'selection':
      return <SelectionScreen state={state} dispatch={dispatch} role={role} localPlayerId={localPlayerId} />
    case 'tunnel':
      return (
        <TunnelScreen state={state} dispatch={dispatch} role={role} localPlayerId={localPlayerId} />
      )
    case 'end':
      return <EndScreen state={state} dispatch={dispatch} role={role} />
    default:
      return <MenuScreen state={state} dispatch={dispatch} role={role} roomCode={roomCode} />
  }
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

  // Identité de connexion (code de room + local_player_id) + message
  // d'erreur éventuel à afficher sur l'accueil, regroupés dans un seul état
  // pour n'avoir qu'une seule mutation par transition. null tant que
  // l'utilisateur n'a pas créé/rejoint de room via AccueilScreen, ou après un
  // room:closed / reconnexion impossible.
  const [session, setSession] = useState<{ identity: Identity | null; connectError: string | null }>(
    () => ({ identity: isStyleguide ? null : loadStoredIdentity(), connectError: null }),
  )
  const { identity, connectError } = session

  const connection = useRoomConnection(isStyleguide ? null : identity)

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

  if (isStyleguide) {
    // Pas de connexion réseau ici : bouton "Retour au menu" de la demo
    // ramène simplement sur l'accueil (hors scope du design system).
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

  return (
    <>
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

export default App
