---
status: draft
created: 2026-10-11
updated: 2026-10-20
---

# Protocole Multi Bloc 13

Contrat incompatible avec le premier jalon `c3fdbf6`. La spec de référence est
[`bloc-13-multi-consolidation-contract`](specs/bloc-13-multi-consolidation-contract.md).
Les preuves d'exécution et limites sont dans [la validation Bloc 13](validation-bloc-13.md).
Un seul process possède les rooms en mémoire : aucun compte, aucune sauvegarde,
aucune reprise après redémarrage. Déployer pendant une fenêtre sans partie et
recharger les clients. Plusieurs workers/réplicas ne sont pas supportés.

## Identité Et REST

`localPlayerId` est un UUID public canonique, jamais une autorisation. Chaque
adhésion reçoit un secret indépendant de 32 octets aléatoires, base64url sans
padding (43 caractères). Seul son SHA-256 reste au serveur; comparaison en temps
constant. Ne jamais journaliser corps REST, trames d'authentification ou secrets.

| Requête | Corps exact | Réponse |
|---|---|---|
| `POST /api/rooms` | `{pseudo}` | `{code, localPlayerId, role: "presentateur", sessionToken}` |
| `POST /api/rooms/{code}/join` nouvelle adhésion | `{pseudo, role?}` | `{code, localPlayerId, role, sessionToken, state}` |
| Même endpoint, reprise | `{localPlayerId, sessionToken}` | `{code, localPlayerId, role, state}` |

Rôles de jointure : `joueur` par défaut, ou `ecran-principal`. Joueurs uniquement
en lobby; écrans à tout moment. La reprise ne crée rien, ne renouvelle pas le
secret, ne change pas la présence et ne diffuse rien. Une preuve incorrecte ne
devient jamais une nouvelle adhésion. Codes de room normalisés en majuscules.
REST laisse `connected: false` jusqu'à l'authentification WS. Les réponses
create/join, erreurs comprises, portent `Cache-Control: no-store`.

Corps JSON strict : champs exacts, aucun coercing, noms trimés avant contrôle,
limite brute 8192 octets par défaut avant décodage. Erreurs HTTP :
`{detail: {code, message}}`. Codes : 422 `invalid_payload`, 401 `session_revoked`
(`Session unavailable.`), 404 `room_not_found`, 409 `invalid_phase` ou
`capacity_exceeded`, 429 `rate_limited` avec `Retry-After`, 413
`payload_too_large`, 503 `capacity_exceeded` pour épuisement des rooms ou des
lecteurs de corps, 408 `request_timeout` pour expiration de lecture du corps.

Create, join et reprise partagent une capacité process-wide de lectures de corps
en cours : `MAX_REST_BODY_READERS=32`, entier strict positif. Admission immédiate
sans attente ni queue après le quota de débit REST ; saturation : HTTP 503,
`{detail:{code:"capacity_exceeded",message:"Body reader capacity exceeded."}}`.
`REST_BODY_TIMEOUT_SECONDS=5`, nombre positif fini, borne la lecture complète
par une deadline absolue monotone à partir de l'admission, non renouvelée à
chaque chunk. Expiration : HTTP 408,
`{detail:{code:"request_timeout",message:"Request body timed out."}}`.
Ces erreurs portent `Cache-Control: no-store`. La place est libérée en `finally`
après succès, timeout, annulation, corps trop grand, JSON invalide, déconnexion
ou erreur de lecture. La limite brute reste appliquée avant décodage. Aucun
timeout de proxy n'est présumé.

## Authentification WS

Ouvrir `/ws/{code}` sans query d'identité/secret. L'ancien
`?local_player_id=...` est rejeté. Le navigateur doit envoyer exactement une
origine de l'allowlist, même en same-host : absence, `null`, doublons, wildcard
et correspondances de suffixe refusés avant upgrade (HTTP 403). Capacité ou
débit d'upgrade épuisés : HTTP 429. Origin complète la preuve, sans la remplacer.

Le premier message texte, dans les 5 secondes après acceptation, est exactement :

```json
{"type":"session:auth","payload":{"localPlayerId":"UUID canonique","sessionToken":"secret base64url de 43 caractères"}}
```

Aucun état ni changement de présence ne précède la vérification. Le premier
`room:state_sync` est l'acquittement. Un deuxième `session:auth` est invalide.
La dernière socket authentifiée gagne, sans passage absent intermédiaire.
L'ancienne perd son autorité avant notification. Ses commandes, déconnexions et
échecs d'envoi tardifs ne peuvent détacher la nouvelle.

```json
{"type":"room:state_sync","payload":{"code":"ABCD","role":"joueur","localPlayerId":"UUID public","state":{}}}
```

Les rôles et identifiants de chaque enveloppe sont spécifiques au destinataire;
`state` est public et ne contient aucun secret. Les snapshots complets sont
ordonnés par socket, à livraison bornée, hors verrou de mutation. Des états égaux
répétés sont acceptables. Chaque commande revérifie sous verrou la room vivante,
la session, l'objet socket exact et le rôle actuel. Le transfert de Présentateur
agit immédiatement sur les sockets déjà ouvertes et ne change aucun secret.

## Commandes

L'enveloppe doit avoir exactement `type` (chaîne connue) et `payload` (objet).
Null, tableau, primitive, JSON invalide, clés supplémentaires, coercions et
types inconnus donnent une erreur ciblée sans fermer la socket dans les bornes
de ressources :

```json
{"type":"error","payload":{"code":"invalid_payload","message":"Invalid message."}}
```

Les binaires sont invalides, soumis à la même limite de taille. Les rejets ne
mutent ni ne diffusent. Autres erreurs : `forbidden_role`, `not_your_turn`,
`invalid_phase`, `game_suspended`, `capacity_exceeded`, `rate_limited`.

| Commande | Payload exact | Autorité et précondition |
|---|---|---|
| `theme:add` | `{label}` | Présentateur, lobby, label non vide après trim |
| `theme:remove` | `{index}` | Présentateur, lobby |
| `player:remove` | `{index}` | Présentateur, lobby, cible non présentateur |
| `player:rename` | `{name}` | Participant, soi-même, lobby |
| `player:set_avatar` | `{avatar}` | Participant, soi-même, lobby, avatar connu/libre |
| `presenter:transfer` | `{targetPlayerId}` | Présentateur, lobby, UUID canonique d'un joueur |
| `game:start` | `{}` | Présentateur, lobby, 2 joueurs inscrits, 1 thème, 1 joueur connecté |
| `choice:reveal` | `{}` | Présentateur, sélection ou succès en attente de révélation |
| `theme:select` | `{index}` | Joueur actif, sélection révélée, thème non terminé |
| `timer:start` | `{}` | Présentateur, `question-pending` |
| `answer:good`, `answer:bad`, `answer:pass` | `{}` | Présentateur, `question` |
| `answer:continue`, `answer:vault` | `{}` | Joueur actif, `after-success-open` |
| `game:reset` | `{}` | Présentateur, post-lobby, thème et joueur connecté requis |
| `game:end_early` | `{}` | Présentateur, retour lobby, participants/thèmes conservés |
| `room:quit` | `{}` | Présentateur, révocation et fermeture de la room |

`index` est un entier non négatif en bornes, ni booléen ni flottant. Un écran
n'est jamais dans `players` et ne peut ni jouer ni modifier nom/avatar. Avatars :
`alice,bob,charlie,diana,edgar,flora,gareth,hannah,ivan,julia,kevin,luna,marco,nina,oscar,petra`.
Le retrait révoque la preuve avant toute notification/fermeture, sans tombstone
illimité. Les secrets ne sont jamais réintroduits dans une synchronisation.

## DTO Et Tours

```ts
type GameState = {
  phase: 'lobby' | 'selection-pending' | 'selection' | 'tunnel' | 'end'
  players: {id: string; name: string; points: number; connected: boolean;
    avatar: string; isPresenter: boolean}[]
  themes: {label: string; progressValue: number; validatedSquares: number;
    discovered: boolean; completed: boolean; nullified: number[]}[]
  currentPlayerIndex: number | null
  turnStatus: 'idle' | 'ready' | 'active-absent' | 'waiting-eligible'
  rotationAnchorIndex: number | null
  activeThemeIndex: number | null
  tunnelSubPhase: 'question-pending' | 'question' | 'after-success-pending'
    | 'after-success-open' | null
  history: {themeLabel: string; playerName: string; pointsGained: number}[]
}
```

Les indexes portent sur le tableau complet. Lobby/end : `idle`, les deux indexes
nuls. `ready` : acteur connecté non présentateur, ancre nulle. Perte de l'acteur :
`active-absent`, même index, phase, sous-phase, progression et historique. Son
retour authentifié restaure ce tour; un autre retour ne le prend pas. Un tour
terminé tourne cycliquement parmi les joueurs connectés, y compris soi après un
cycle complet. Sans éligible : `selection-pending`, `waiting-eligible`, acteur
nul, ancre sur l'acteur sortant. Le prochain retour choisit après l'ancre.

Pendant suspension, révélation, sélection, chrono et toutes les réponses sont
rejetés `game_suspended`. Le Présentateur peut reset si éligible, terminer vers
lobby ou fermer. Reset prend le premier joueur connecté en ordre de tableau,
jamais arbitrairement l'index zéro. Fin de tous les thèmes : end/idle/indexes nuls.
`answer:pass` conserve l'acteur, y compris au coffrage automatique. Coffrer avant
10 ne termine pas le thème. Le Présentateur n'a ni tour ni points ni classement.

Le chrono est un affichage **local indicatif de 60 secondes**, seulement en
`question`, clé thème/progression/sous-phase. Une présence sync/suspension ne le
remonte, ne le gèle et ne le redémarre pas. Remontage/reload/reconnexion en
question repart à 60. Zéro n'envoie aucune commande : jugement toujours humain.

## Fermetures Et Reprise

Terminal : `{"type":"session:ended","payload":{"code":"…","message":"…"}}`,
puis fermeture; notification best effort, code de fermeture faisant autorité.

| Code | Fermeture | Message exact |
|---|---|---|
| `session_revoked` | 4401 | `Session unavailable.` |
| `player_kicked` | 4403 | `You were removed from the room.` |
| `room_closed` | 4404 | `Room closed or unavailable.` |
| `session_replaced` | 4409 | `Session opened elsewhere.` |

Les alias `player:kicked` et `room:closed`, payload `{}`, précèdent le terminal
si livrables. Première trame invalide : 1008; délai auth : 4408; débit : erreur
ciblée puis 4429; taille : 1009. Les tailles sont aussi bornées au transport
Uvicorn, avant JSON. Les autres erreurs de commandes laissent la socket utilisable.

Le client stocke à `legrandtunneg:identity:v2` exactement
`{version:2, code, localPlayerId, sessionToken, autoResume}`, jamais de rôle de
confiance. C'est un compromis localStorage : un XSS same-origin vole ce bearer.
L'ancienne clé `legrandtunneg:identity` demande explicitement une nouvelle
jointure; elle n'authentifie/crée jamais silencieusement.

Perte transitoire : identité conservée, une seule retry, jitter uniforme entre
0.5 et 1 fois `min(30000, 500 * 2^n)` ms, n initial 0, remis à zéro seulement
après sync réussie. Aucun replay ni queue de commandes. Envoi désactivé avant
auth, callbacks obsolètes ignorés, retries annulées au démontage/changement
d'identité/déconnexion volontaire. Déconnexion volontaire et remplacement :
preuve conservée, `autoResume:false` persisté, bouton Reprendre explicite, même
après reload. Révoqué/retiré/room fermée effacent la preuve utilisable; tous les
terminaux gardent l'explication visible. 1008/1009/4429 demandent une action
explicite, 4408 et pannes réseau sont transitoires. Room perdue après restart :
reprise terminée, pas une sauvegarde durable.

## Ressources

Configuration et commande de production : [README](../README.md). Défauts :
10 rooms, 16 participants/room (Présentateur inclus), 4 écrans, 32 thèmes,
24 caractères/nom, 100/label; 8192 octets WS et REST; auth 5s, 32 preauth,
200 sockets authentifiées (anciennes remplacées jusqu'à fermeture comprises),
envoi/fermeture 2s. Buckets monotones initialement pleins : REST 5/s burst20,
upgrade 10/s burst20, commandes 20/s burst40/socket et 200/s burst400 global.
Pas de backlog dormant ni de map IP illimitée; headers proxy non fiables par
défaut. L'absence de toute socket authentifiée (écrans inclus) démarre un TTL
monotone de 86400s, sweep 60s annulé/attendu au shutdown. REST, preauth et preuves
invalides ne rafraîchissent pas ce TTL; auth à la borne d'expiration échoue.
