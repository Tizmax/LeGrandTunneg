import { AnimatePresence, motion } from 'framer-motion'
import { useGame } from './game/useGame'
import { MenuScreen } from './screens/MenuScreen'
import { ThemesScreen } from './screens/ThemesScreen'
import { SelectionScreen } from './screens/SelectionScreen'
import { TunnelScreen } from './screens/TunnelScreen'
import { EndScreen } from './screens/EndScreen'

function renderScreen(
  phase: string,
  state: ReturnType<typeof useGame>['state'],
  dispatch: ReturnType<typeof useGame>['dispatch'],
) {
  switch (phase) {
    case 'menu':
      return <MenuScreen state={state} dispatch={dispatch} />
    case 'themes':
      return <ThemesScreen state={state} dispatch={dispatch} />
    case 'selection':
      return <SelectionScreen state={state} dispatch={dispatch} />
    case 'tunnel':
      return <TunnelScreen state={state} dispatch={dispatch} />
    case 'end':
      return <EndScreen state={state} dispatch={dispatch} />
    default:
      return <MenuScreen state={state} dispatch={dispatch} />
  }
}

function App() {
  const { state, dispatch } = useGame()

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
          {renderScreen(state.phase, state, dispatch)}
        </motion.div>
      </AnimatePresence>
    </>
  )
}

export default App
