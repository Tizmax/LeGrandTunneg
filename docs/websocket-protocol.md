---
status: draft
created: 2026-10-11
---

# Protocole WebSocket — mode room multi (Bloc 3)

**Mise à jour 2026-10-11** : ajout du sous-état `question-pending` entre la
sélection du thème (ou "Continuer") et le lancement effectif du chrono. Le
Présentateur pose désormais sa question à l'oral avant de déclencher
manuellement le minuteur via `timer:start` — voir table des messages et la
spécification figée dans l'exec-plan pour le détail des deux temps côté
joueur ("écoute la question" puis "attend le verdict").

Portée de cette version : **état de room et de partie entièrement en mémoire
process-local** (pas de Postgres branché). La persistance (Bloc 2) et la
reprise après redémarrage du serveur viendront dans une passe ultérieure — ce
document sera mis à jour à ce moment-là pour la stratégie de reconnexion
post-crash serveur. Ici, « reconnexion » signifie uniquement : un client qui
perd puis rouvre sa connexion WebSocket pendant que le process serveur tourne
toujours.

## Vue d'ensemble du flux

1. **Créer une room** : `POST /api/rooms` `{pseudo}` → le créateur devient
   **Présentateur**. Réponse : `{code, localPlayerId, role: "presentateur"}`.
2. **Rejoindre une room** : `POST /api/rooms/{code}/join` `{pseudo, role?}`
   (`role` ∈ `"joueur"` (défaut) | `"ecran-principal"`). Réponse :
   `{code, localPlayerId, role}`.
   - Rejoindre en tant que `joueur` n'est accepté que tant que la partie est
     en lobby (`phase === "menu"`) : ajoute immédiatement une entrée dans
     `players` via le moteur de règles.
   - Rejoindre en tant que `ecran-principal` est accepté à tout moment ; ce
     rôle n'est jamais ajouté à `players` (lecture seule, aucune action de
     jeu possible).
   - Si `localPlayerId` est fourni dans le corps de la requête et correspond
     à un participant déjà connu de cette room, c'est une **reconnexion** :
     aucun nouveau joueur n'est créé, le rôle existant est simplement
     retourné.
3. **Ouvrir le WebSocket** : `GET /ws/{code}?local_player_id=...` (upgrade).
   Le serveur vérifie que `local_player_id` est bien connu de la room (via
   l'étape REST précédente), attache la connexion, puis envoie immédiatement
   un message `room:state_sync` complet.
4. **Échanges en cours de partie** : chaque action de jeu est un message
   client→serveur avec enforcement de rôle strict (voir table ci-dessous).
   Après chaque action acceptée, le serveur **rediffuse l'état complet** de
   la room à toutes les connexions actives (`room:state_sync` broadcast) —
   pas de diffs incrémentaux dans cette version.
5. **Fin de room** : `room:quit` (Présentateur uniquement) vide l'état de la
   room en mémoire, diffuse `room:closed` à tous les clients connectés, puis
   ferme toutes les connexions WebSocket et supprime la room du
   `RoomManager`.

## Identité et rôles

- `localPlayerId` : UUID généré par le serveur à la création/jointure,
  renvoyé au client qui doit le conserver (`localStorage`) pour se
  reconnecter. Un seul `localPlayerId` par onglet/participant.
- Rôles possibles : `presentateur` (exactement un par room, le créateur —
  le transfert de rôle en lobby n'est **pas** implémenté dans cette passe,
  voir Limitations connues), `joueur` (entrée dans `players`), `ecran-principal`
  (lecture seule, jamais dans `players`).
- Le serveur associe en interne chaque entrée `players[i]` à son
  `localPlayerId` d'origine (champ `id` dans le DTO `Player`, voir plus bas)
  — c'est ce qui permet au serveur de savoir si un message `theme:select`
  émis par tel `localPlayerId` correspond bien au joueur dont c'est le tour
  (`players[currentPlayerIndex].id === localPlayerId` de la connexion).

## Enveloppe des messages

```jsonc
// client → serveur
{ "type": "theme:select", "payload": { "index": 2 } }

// serveur → client (état)
{ "type": "room:state_sync", "payload": { "code": "ABCD", "role": "joueur", "localPlayerId": "...", "state": { /* GameStateDTO */ } } }

// serveur → client (erreur, jamais broadcastée, uniquement au client fautif)
{ "type": "error", "payload": { "code": "forbidden_role", "message": "..." } }
```

## DTO `GameState` (JSON, camelCase — miroir direct de `frontend/src/game/types.ts`)

```ts
type Theme = {
  label: string
  progressValue: number      // 0-10
  validatedSquares: number   // 0-10
  discovered: boolean
  completed: boolean
  nullified: number[]
}

type Player = {
  id: string        // localPlayerId d'origine — NOUVEAU vs le POC frontend-only
  name: string
  points: number
}

type GamePhase =
  | 'menu' | 'themes' | 'selection-pending' | 'selection' | 'tunnel' | 'end'

type TunnelSubPhase =
  | 'question-pending' | 'question' | 'after-success-pending' | 'after-success-open' | null

type HistoryEntry = { themeLabel: string; playerName: string; pointsGained: number }

type GameState = {
  phase: GamePhase
  players: Player[]
  themes: Theme[]
  currentPlayerIndex: number
  activeThemeIndex: number | null
  tunnelSubPhase: TunnelSubPhase
  history: HistoryEntry[]
}
```

## Table des messages client → serveur

| Type              | Payload                | Rôle autorisé                                  | Précondition d'état serveur                                             | Action moteur équivalente (gameReducer.ts) |
|-------------------|-------------------------|-------------------------------------------------|---------------------------------------------------------------------------|----------------------------------------------|
| `theme:add`       | `{ label }`             | Présentateur                                    | `phase === 'themes'`                                                      | `ADD_THEME`                                  |
| `theme:remove`    | `{ index }`             | Présentateur                                    | `phase === 'themes'`                                                      | `REMOVE_THEME`                               |
| `player:remove`   | `{ index }`             | Présentateur                                    | `phase === 'menu'`                                                        | `REMOVE_PLAYER`                              |
| `lobby:go_to_themes` | `{}`                 | Présentateur                                    | `phase === 'menu'`, `players.length >= 2`                                 | `GO_TO_THEMES`                               |
| `game:start`      | `{}`                    | Présentateur                                    | `phase === 'themes'`, `themes.length >= 1`                                | `START_GAME`                                 |
| `choice:reveal`   | `{}`                    | Présentateur                                    | `phase === 'selection-pending'` OU `tunnelSubPhase === 'after-success-pending'` | `REVEAL_CHOICE`                         |
| `theme:select`    | `{ index }`             | **Joueur concerné** (`players[currentPlayerIndex].id`) | `phase === 'selection'` (choice_open), thème visé non `completed`    | `SELECT_THEME`                               |
| `timer:start`     | `{}`                    | Présentateur                                    | `phase === 'tunnel'`, `tunnelSubPhase === 'question-pending'`              | *(nouveau — pas d'équivalent POC)*           |
| `answer:good`     | `{}`                    | Présentateur                                    | `phase === 'tunnel'`, `tunnelSubPhase === 'question'`                      | `GOOD_ANSWER`                                |
| `answer:bad`      | `{}`                    | Présentateur                                    | `phase === 'tunnel'`, `tunnelSubPhase === 'question'`                      | `BAD_ANSWER`                                 |
| `answer:pass`     | `{}`                    | Présentateur                                    | `phase === 'tunnel'`, `tunnelSubPhase === 'question'`                      | `PASS`                                       |
| `answer:continue` | `{}`                    | **Joueur concerné**                              | `tunnelSubPhase === 'after-success-open'`                                  | `CONTINUE`                                   |
| `answer:vault`    | `{}`                    | **Joueur concerné**                              | `tunnelSubPhase === 'after-success-open'`                                  | `COFFRER`                                    |
| `game:reset`      | `{}`                    | Présentateur                                    | aucune (toute phase post-lobby)                                           | `RESET_GAME`                                 |
| `room:quit`       | `{}`                    | Présentateur                                    | aucune                                                                     | `QUIT_TO_MENU` + fermeture de la room          |

« Joueur concerné » = le `localPlayerId` de la connexion émettrice doit être
strictement égal à `players[currentPlayerIndex].id` au moment du message. Toute
autre connexion de rôle `joueur` tentant la même action reçoit `error` avec
`code: "not_your_turn"`.

Toute action envoyée par un rôle non autorisé reçoit `error` avec
`code: "forbidden_role"`. Toute action envoyée alors que la précondition
d'état n'est pas remplie reçoit `error` avec `code: "invalid_phase"`
(ex. `theme:select` reçu alors que `phase === 'selection-pending'` — le choix
n'est pas encore révélé). Dans tous les cas d'erreur, l'état de la room n'est
pas modifié et **aucun broadcast n'est émis** — seul le client fautif reçoit
le message `error`.

Note sur `player:add` : volontairement absent de cette table. En mode multi,
un joueur rejoint la room avec son propre pseudo via `POST
/api/rooms/{code}/join` (étape REST, pas un message WS) — il n'y a pas de
action WS équivalente à l'ancien `ADD_PLAYER` du POC hotseat.

## Messages serveur → client

| Type              | Quand                                                          | Payload                                                  |
|-------------------|------------------------------------------------------------------|-----------------------------------------------------------|
| `room:state_sync` | À chaque connexion WS ouverte, et après chaque action acceptée (broadcast à toute la room) | `{ code, role, localPlayerId, state: GameState }` — `role`/`localPlayerId` sont spécifiques au destinataire, `state` est identique pour tous |
| `room:closed`     | Après un `room:quit` accepté, avant fermeture des connexions      | `{}`                                                       |
| `error`           | Après une action rejetée (rôle ou phase invalide), envoyé **uniquement au client fautif** | `{ code: "forbidden_role" \| "not_your_turn" \| "invalid_phase" \| "invalid_payload" \| "room_not_found", message: string }` |

## Reconnexion (process serveur toujours vivant)

1. Le client garde en mémoire locale (`localStorage`) : `code`, `localPlayerId`.
2. À la perte de connexion WS (ex. veille, rechargement de page), le client
   rouvre `GET /ws/{code}?local_player_id=...` avec le même `localPlayerId`.
3. Le serveur retrouve l'entrée existante dans `room.roles[localPlayerId]`
   (la room et l'état de jeu étant restés en mémoire, rien n'a été perdu côté
   serveur), ré-attache la connexion, et renvoie immédiatement
   `room:state_sync` avec l'état courant complet — y compris un
   `choice_pending` en cours le cas échéant (le client affiche directement
   l'écran d'attente neutre adéquat, sans action supplémentaire).
4. Si `code` est inconnu du `RoomManager` (room jamais créée, ou déjà
   `room:quit`), le serveur refuse l'upgrade WebSocket (fermeture immédiate
   avec code de fermeture applicatif, le client retombe sur l'écran
   d'accueil).

## Limitations connues de cette passe (à lever dans une passe ultérieure)

- **Pas de persistance Postgres** : si le process serveur redémarre, toutes
  les rooms et parties en cours sont perdues. Bloc 2 (schéma + Alembic) et la
  persistance aux transitions clés (Bloc 5 version complète) ajouteront la
  survie au redémarrage et l'historique consultable après coup.
- **Pas de transfert de Présentateur en lobby** : la décision produit prévoit
  que le Présentateur puisse désigner un autre participant avant le début de
  partie ; ce message WS (`room:transfer_presentateur` ou équivalent) n'est
  pas implémenté dans cette passe — un seul Présentateur fixe (le créateur de
  la room) pour l'instant.
- **Pas de banque de thèmes prédéfinis ni d'historique/stats** : hors scope
  de cette passe, prévus respectivement en Bloc 4 (endpoints REST
  complémentaires) et Bloc 2/5 (persistance).
</content>
