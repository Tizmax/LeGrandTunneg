import type { GameAction } from '../game/gameReducer'
import type { OutgoingMessage } from './useRoomConnection'

/**
 * Adapte l'ancienne interface `React.Dispatch<GameAction>` (POC hotseat local,
 * voir game/gameReducer.ts) vers l'émission de messages WebSocket réels, afin
 * de réutiliser les écrans existants (SelectionScreen, TunnelScreen,
 * ChoicePendingScreen, EndScreen...) sans les réécrire : ces écrans continuent
 * d'appeler `dispatch({ type: 'SELECT_THEME', index })` comme avant, mais
 * l'action part désormais sur le réseau au lieu de muter un reducer local.
 *
 * `ADD_PLAYER` n'a pas d'équivalent réseau : en mode multi, un joueur rejoint
 * la room avec son propre pseudo via `POST /api/rooms/{code}/join` (voir
 * net/roomApi.ts et screens/AccueilScreen.tsx), pas via une action WS émise
 * par un autre participant.
 */
export function createNetworkDispatch(send: (message: OutgoingMessage) => void) {
  return (action: GameAction): void => {
    switch (action.type) {
      case 'ADD_PLAYER':
        return
      case 'REMOVE_PLAYER':
        send({ type: 'player:remove', payload: { index: action.index } })
        return
      case 'RENAME_SELF':
        send({ type: 'player:rename', payload: { name: action.name } })
        return
      case 'SET_AVATAR':
        send({ type: 'player:set_avatar', payload: { avatar: action.avatar } })
        return
      case 'ADD_THEME':
        send({ type: 'theme:add', payload: { label: action.label } })
        return
      case 'REMOVE_THEME':
        send({ type: 'theme:remove', payload: { index: action.index } })
        return
      case 'START_GAME':
        send({ type: 'game:start', payload: {} })
        return
      case 'SELECT_THEME':
        send({ type: 'theme:select', payload: { index: action.index } })
        return
      case 'START_TIMER':
        send({ type: 'timer:start', payload: {} })
        return
      case 'GOOD_ANSWER':
        send({ type: 'answer:good', payload: {} })
        return
      case 'BAD_ANSWER':
        send({ type: 'answer:bad', payload: {} })
        return
      case 'PASS':
        send({ type: 'answer:pass', payload: {} })
        return
      case 'CONTINUE':
        send({ type: 'answer:continue', payload: {} })
        return
      case 'COFFRER':
        send({ type: 'answer:vault', payload: {} })
        return
      case 'RESET_GAME':
        send({ type: 'game:reset', payload: {} })
        return
      case 'QUIT_TO_MENU':
        send({ type: 'room:quit', payload: {} })
        return
      case 'END_GAME_EARLY':
        send({ type: 'game:end_early', payload: {} })
        return
      case 'REVEAL_CHOICE':
        send({ type: 'choice:reveal', payload: {} })
        return
    }
  }
}

export type NetworkDispatch = ReturnType<typeof createNetworkDispatch>
