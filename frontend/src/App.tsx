import { useGame } from './game/useGame'
import { MenuScreen } from './screens/MenuScreen'
import { ThemesScreen } from './screens/ThemesScreen'
import { SelectionScreen } from './screens/SelectionScreen'
import { TunnelScreen } from './screens/TunnelScreen'
import { EndScreen } from './screens/EndScreen'

function App() {
  const { state, dispatch } = useGame()

  switch (state.phase) {
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

export default App
