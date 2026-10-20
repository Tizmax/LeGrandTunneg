# Validation Locale Bloc 13

Date : 2026-10-20. Baseline : `c3fdbf6`. Ce document décrit le travail local,
pas une approbation indépendante de la spec ni un statut de livraison distant.
Aucun commit, push ou déploiement n'est effectué dans cette intervention.
La spec et le plan restent sous le contrôle du responsable de leur lifecycle.

## Organisation

La répartition initiale comportait quatre producteurs, sur le même workspace :

| Zone | Ownership |
|---|---|
| Moteur / DTO | `backend/app/game/*`, tests moteur et éligibilité |
| Sessions / REST / WS | `backend/app/rooms/manager.py`, `backend/app/api/*`, tests sessions et intégration existante |
| Frontend | `frontend/*`, workflow CI frontend, reprise/UI/tests |
| Ressources | `backend/app/core/*`, `backend/app/main.py`, `backend/app/serve.py`, configuration de lancement, tests ressources |
| Coordination | Ce rapport, README, protocole et test local HTTP/WS de bout en bout |

Les interfaces partagées sont `settings` (objet conservant son identité),
`TokenBucket`, la vérification exacte d'Origin, `cleanup_loop()` annulable,
`set_player_connected()` et le DTO public avec indexes nullables. Aucun transport
ne décide à la place du moteur de l'acteur ou du score.

Une collision interne de délégation a laissé des appels de lifecycle sans leurs
méthodes. Ce n'était pas une intervention utilisateur. Après sortie des
producteurs, le coordinateur a repris seul `manager.py` et `ws.py`, réconcilié
les méthodes et appels, puis relancé toutes les validations. Aucun ancien patch
n'a été restauré aveuglément.

## Décisions

- Une preuve individuelle opaque remplace l'autorisation par UUID public.
- REST ne simule aucune présence ; seule une socket authentifiée la crée.
- La session et l'objet socket exact sont vérifiés sous verrou à chaque action.
- Une absence active suspend le tour sans le céder ; `pass` conserve l'acteur.
- Le chrono de 60 secondes reste local, indicatif et sans jugement automatique.
- Un seul process/worker possède les rooms en mémoire ; pas de base, compte,
  multiworker, banque de questions ou refonte du reducer solo.
- `python -m app.serve` applique la limite WS dans Uvicorn, pas seulement après
  réception JSON. Les origines HTTPS de production sont explicites.

## Vérifications

Environnement local : Node `22.22.1`, Python du venv `3.14`. Python `3.12`
reste la cible Docker/CI ; son exécutable n'est pas installé localement. Les
résultats locaux ne prouvent pas l'exécution du workflow distant.

Depuis `frontend`, après installation propre :

| Commande | Résultat |
|---|---|
| `npm ci` | 125 packages installés, audit de 126 packages, 0 vulnérabilité signalée |
| `npm test` | 5 fichiers, 96 tests réussis, 11,96 s |
| `npm run lint` | Code 0, 0 erreur et 7 avertissements, 620 ms |
| `npm run build` | Code 0, TypeScript et Vite réussis, 2347 modules, Vite 1,60 s |

Les avertissements lint sont six avertissements existants (exports Fast Refresh
et paramètres catch inutilisés) et un avertissement nouveau de remise à zéro
d'état dans l'effet du contrôleur de connexion. Aucune règle n'est désactivée
pour faire passer la vérification. Le build produit 421,12 kB JS (130,39 kB gzip)
et 63,60 kB CSS (10,55 kB gzip).

Vitest, jsdom et Testing Library sont les seules nouvelles dépendances directes,
en développement : runner/timers, DOM simulé et montage React. La CI exécute
`npm test` avant lint/build. Les tests couvrent proof v2 stricte, codes de room
alphanumériques, faux WS, retry/jitter, absence de replay, callbacks obsolètes,
remplacement et arrêts terminaux, déconnexion/reload/reprise explicite, identité
plus récente d'un autre onglet, App et reset selon éligibilité, ainsi que le
chrono local conservé pendant les synchronisations de présence.

Depuis `backend`, sur l'état final :

| Commande | Résultat |
|---|---|
| `timeout 120s .venv/bin/python -m pytest -q` | Code 0, **673 tests réussis**, 5 avertissements, 20,07 s |
| `timeout 30s .venv/bin/python -m pytest tests/test_rest_body_readers.py tests/test_sessions_lifecycle.py -q --tb=short` | Passe ciblée intermédiaire : code 0, 23 tests réussis, 1 avertissement, 2,30 s ; quatre cas HTTP ajoutés ensuite et repassés dans la suite finale |

Depuis la racine : `git diff --check`, code 0, aucune sortie. Les cinq
avertissements backend sont des dépréciations des dépendances TestClient/httpx
et du transport websockets legacy utilisé par Uvicorn. Aucun test n'est ignoré
ou marqué xfail pour contourner le contrat. Les tests du jalon initial sont
conservés et adaptés à la présence réellement authentifiée.

Vérification ciblée déjà exécutée par le producteur : depuis `backend`,
`timeout 30s .venv/bin/python -m pytest tests/test_transport_e2e.py -q` :
**2 tests réussis**, 3,59 s lors de l'exécution ciblée initiale, et repassés dans
la suite finale de 673 tests. Ce scénario utilise réellement HTTP et WS sur
`python -m app.serve`, avec Origin de production explicite. Il couvre la partie
complète (1 puis 22), le coffrage avant 10, fin sans acteur, JSON invalide puis
commande valide sur la même socket, transfert immédiat des droits, remplacement
4409, retrait/révocation 4403 et REST 401, dépassement transport 1009, et Origin
refusée avant upgrade. Cela ne remplace pas la matrice de courses simulées.

## Limites De Preuve

- Aucune preuve navigateur réel, test mobile visuel ou mesure d'accessibilité.
- Aucun build Docker, déploiement Railway, check GitHub distant ou gate de
  fusion/de livraison n'est déclaré validé sans exécution correspondante.
- Le test HTTP/WS local utilise le point d'entrée de production, mais ce n'est
  ni une simulation de tous les navigateurs ni une preuve de réseau distant.
- Les sessions et parties sont perdues au redémarrage du process.
- Le bearer en localStorage reste accessible à un JavaScript same-origin
  compromis ; ne jamais tracer les corps create/join ou `session:auth`.

## Critères Et Écarts

Les scénarios locaux ci-dessous sont couverts par la suite finale du producteur ;
la portée de l'approbation indépendante ROUND2 est précisée après le tableau :

| Critère | Preuves principales |
|---|---|
| Preuve individuelle, SHA-256, UUID public sans autorité, no-store, reprise stricte | `backend/tests/test_sessions_security.py` |
| Auth premier message, aucune donnée avant preuve, Origin exacte, formats et tailles | Tests sécurité, ressources et transport réel |
| Transfert vivant, retrait/révocation, remplacement sans absence intermédiaire | Tests sécurité, intégration et transport réel |
| Ancienne commande, ancien detach et échec d'envoi tardif sans effet sur remplacement | `backend/tests/test_sessions_lifecycle.py` |
| Double commande, envois hors verrou, destinataire lent isolé, file bornée | Tests lifecycle avec sockets déterministes et assertions de verrou |
| Motif terminal préservé face au cleanup concurrent, close borné, capacité des remplacements | Tests lifecycle et sécurité |
| Quotas globaux et par socket, capacité avant upgrade, auth timeout, settings au démarrage | Tests sécurité, lifecycle et ressources |
| Deadline absolue REST, capacité de lecteurs sans queue, libération toutes branches et erreurs HTTP no-store | `backend/tests/test_rest_body_readers.py` ; validation numérique des deux settings dans les tests ressources |
| TTL monotone à la borne exacte, écran seul, REST sans rafraîchissement, annulation du sweep | Tests lifecycle et ressources |
| Reset sans présentateur, suspension de chaque sous-phase, ancre sans éligible | `backend/tests/test_turn_eligibility.py` |
| Pass conserve acteur, coffrage avant 10, partie entière 1 puis 22, fin idle/indexes nuls | Tests moteur, éligibilité, intégration et transport |
| Reprise v2, backoff/jitter, callbacks obsolètes, terminaux, déconnexion/reload explicites | Tests hook, identité et App |
| Chrono local 60 s conservé sur sync/absence, zéro sans commande | `frontend/src/screens/TunnelScreen.test.tsx` |
| SPA confinée, symlinks, traversée et préfixes réservés | `backend/tests/test_resources.py` |

Livraison bornée : un snapshot en cours et un slot du dernier snapshot par
socket, sans queue croissante. Les snapshots livrés ne sont pas réordonnés ;
les états intermédiaires encore en attente peuvent être coalescés. Une tâche
terminale unique conserve le premier motif d'invalidation, interrompt l'attente
de réception et ne libère la capacité authentifiée qu'après fermeture bornée.
Les buckets globaux sont recréés au démarrage depuis les settings validés.

La revue indépendante ROUND1 a demandé des changements : la taille REST seule
ne bornait ni la durée d'un corps incomplet ni les lectures pendantes. La
correction ajoute une deadline absolue et une admission process-wide sans queue,
avec libération garantie en `finally`. `backend/tests/test_rest_body_readers.py`
couvre corps incomplet, chunks lents sans renouvellement du délai, saturation
commune create/join/reprise, annulation, succès, JSON/forme invalides, taille,
déconnexion et erreur de lecture, puis réadmission normale. Les délais de test
sont courts (40 ms), pas des attentes de production de plusieurs secondes.

La couverture mineure demandée ajoute trois courses : envoi d'erreur déjà
bloqué sous `send_lock`, puis remplacement, retrait ou fermeture. Les tests
vérifient timeout d'envoi, fermeture bornée avec motif terminal préservé et,
pour le remplacement, socket et preuve du remplaçant intactes. Aucun défaut de
locking n'a été reproduit ; aucun remaniement du locking n'a été effectué.

La revue indépendante ROUND2 conclut **APPROVED** : approbation globale de
l'état local non committé sur la baseline `c3fdbf6`, limitée au périmètre du
Bloc 13. Les 673 tests backend, 96 tests frontend, lint et build sont des preuves
d'exécution du producteur, non réexécutées par les reviewers. Ceux-ci ont mené
indépendamment l'inspection du code et des assertions de tests, ainsi que les
contrôles git HEAD, status et `git diff --check`.
Cette approbation ne prouve ni Python 3.12, ni Docker, ni navigateur réel, ni CI
distante, ni Railway, ni durabilité des sessions ou des parties.

### Contrat REST Mis À Jour

Le lead a intégré ces exigences dans la spec via son lifecycle :
`REST_BODY_TIMEOUT_SECONDS=5` (nombre positif fini) et
`MAX_REST_BODY_READERS=32` (entier strict positif). Create, join et reprise
partagent cette capacité process-wide de lectures en cours. Après quota de
débit REST, l'admission est immédiate sans attente ni queue ; la saturation
retourne HTTP 503 `capacity_exceeded` (`Body reader capacity exceeded.`).
Une deadline absolue monotone à partir de l'admission borne la lecture complète,
sans renouvellement par chunk ; son expiration retourne HTTP 408
`request_timeout` (`Request body timed out.`).

Toutes les réponses create/join, erreurs comprises, portent
`Cache-Control: no-store`, avec des erreurs structurées `{detail: {code, message}}`.
La place est libérée en `finally` sur succès, timeout, annulation, taille
excessive, JSON invalide, déconnexion ou erreur de lecture. La limite brute de
8 KiB reste appliquée avant décodage. Aucun timeout de proxy n'est présumé.

## Fichiers Modifiés

- Backend : `backend/app/api/rooms.py`, `backend/app/api/ws.py`,
  `backend/app/rooms/manager.py`, `backend/app/game/engine.py`,
  `backend/app/game/serialize.py`, `backend/app/game/types.py`,
  `backend/app/main.py`, nouveaux `backend/app/core/settings.py`,
  `backend/app/core/limits.py`, `backend/app/core/origins.py`, `backend/app/serve.py`.
- Tests backend : `backend/tests/test_game_engine.py`,
  `backend/tests/test_rooms_integration.py`, nouveaux
  `backend/tests/test_turn_eligibility.py`, `backend/tests/test_resources.py`,
  `backend/tests/test_sessions_security.py`, `backend/tests/test_sessions_lifecycle.py`,
  `backend/tests/test_transport_e2e.py`, `backend/tests/test_rest_body_readers.py`.
- Frontend : `frontend/src/App.tsx`, `frontend/src/net/roomApi.ts`,
  `frontend/src/net/types.ts`, `frontend/src/net/useRoomConnection.ts`, nouveau
  `frontend/src/net/identity.ts`, `frontend/src/game/types.ts`,
  `frontend/src/game/gameReducer.ts` (typing nullable uniquement),
  `frontend/src/components/GameControls.tsx`, `frontend/src/components/ScoreBoard.tsx`,
  `frontend/src/screens/AccueilScreen.tsx`, `frontend/src/screens/EndScreen.tsx`,
  `frontend/src/screens/LobbyScreen.tsx`, `frontend/src/screens/SelectionScreen.tsx`,
  `frontend/src/screens/TunnelScreen.tsx`.
- Tests frontend : nouveaux `frontend/src/App.test.tsx`,
  `frontend/src/net/identity.test.ts`, `frontend/src/net/roomApi.test.ts`,
  `frontend/src/net/useRoomConnection.test.tsx`,
  `frontend/src/screens/TunnelScreen.test.tsx`, `frontend/vitest.config.ts`.
- Outillage/config : `frontend/package.json`, `frontend/package-lock.json`,
  `.github/workflows/ci.yml`, `backend/.env.example`, `Dockerfile`, `railway.toml`.
- Documentation : `README.md`, `docs/websocket-protocol.md`, ce rapport.
  La spec `docs/specs/bloc-13-multi-consolidation-contract.md` a été enrichie par
  le lead via son lifecycle ; l'actualisation du plan est réservée au lead seul.
  Cette intervention documentaire ne modifie ni la spec ni l'exec-plan.
