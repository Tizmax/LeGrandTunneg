import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useGame } from './game/useGame'
import type { ViewRole } from './viewRole'
import { RoleSwitcher } from './components/RoleSwitcher'
import { MenuScreen } from './screens/MenuScreen'
import { ThemesScreen } from './screens/ThemesScreen'
import { SelectionScreen } from './screens/SelectionScreen'
import { TunnelScreen } from './screens/TunnelScreen'
import { EndScreen } from './screens/EndScreen'
import { ChoicePendingScreen } from './screens/ChoicePendingScreen'
import { StyleguideScreen } from './screens/StyleguideScreen'

function renderScreen(
  phase: string,
  state: ReturnType<typeof useGame>['state'],
  dispatch: ReturnType<typeof useGame>['dispatch'],
  role: ViewRole,
) {
  switch (phase) {
    case 'menu':
      return <MenuScreen state={state} dispatch={dispatch} />
    case 'themes':
      return <ThemesScreen state={state} dispatch={dispatch} />
    // Couche show : choix de thème pas encore révélé par le Présentateur.
    case 'selection-pending':
      return (
        <ChoicePendingScreen state={state} dispatch={dispatch} isPresenterView={role === 'presentateur'} />
      )
    case 'selection':
      return <SelectionScreen state={state} dispatch={dispatch} role={role} />
    case 'tunnel':
      return <TunnelScreen state={state} dispatch={dispatch} role={role} />
    case 'end':
      return <EndScreen state={state} dispatch={dispatch} />
    default:
      return <MenuScreen state={state} dispatch={dispatch} />
  }
}

function App() {
  const { state, dispatch } = useGame()

  // Rôle d'affichage LOCAL (prévisualisation sans réseau, voir src/viewRole.ts
  // et src/components/RoleSwitcher.tsx pour le détail de la limitation).
  const [role, setRole] = useState<ViewRole>('presentateur')

  // Route de démonstration interne du design system (Bloc 6), atteignable
  // via ?debug=styleguide — jamais exposée dans le flux de jeu normal.
  const isStyleguide =
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).get('debug') === 'styleguide'

  if (isStyleguide) {
    return <StyleguideScreen dispatch={dispatch} />
  }

  const showRoleSwitcher = state.phase !== 'menu' && state.phase !== 'themes'

  return (
    <>
      {showRoleSwitcher && <RoleSwitcher role={role} onChange={setRole} />}
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
          {renderScreen(state.phase, state, dispatch, role)}
        </motion.div>
      </AnimatePresence>
    </>
  )
}

export default App
