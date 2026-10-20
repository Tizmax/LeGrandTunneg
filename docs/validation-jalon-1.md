# Validation du premier jalon

Date : 2026-10-20. Périmètre : Bloc 12 et tranche initiale du Bloc 10 uniquement.
Révision locale de base : `d0d97ef2177467a0189d86fd8c3a090a0f8cae4e`, plus les
changements non commités de ce jalon. Aucun commit, push ou déploiement effectué.
La précision documentaire préexistante Oxlint/verrou Railway dans
`docs/exec-plans/reconstruction-le-grand-tunneg.md` est conservée sans modification.
Ni plan ni spec modifiés par cette tâche.

## Référence et environnement

- L'utilisateur confirme qu'une partie complète fonctionne et qu'un déploiement
  Railway est en cours. Cela n'identifie pas sa révision ni sa configuration.
- Révision Railway : **inconnue**, aucun SHA de déploiement prouvé.
- `git ls-remote origin HEAD` (lecture seule) retourne
  `72257bf683e0ed9d9d4aeb3aa1208c64775af392`. Ce SHA distant n'est ni la révision
  locale testée ni une preuve du déploiement Railway.
- `gh` et `railway` ne sont pas installés dans l'environnement. Une lecture
  anonyme de `https://api.github.com/repos/Tizmax/LeGrandTunneg` retourne HTTP 403.
  Aucune recherche de secrets ni modification distante effectuée. Les règles
  de fusion, checks exécutés et réglages Railway n'ont pas été consultables.
- Environnement existant : Python 3.14.4 dans `backend/.venv`, Node 22.22.1,
  npm 9.2.0, Vite 8.3.4, Oxlint 1.87.0. CI ciblée sur Python 3.12 comme Docker ;
  cette version Python n'a pas été exécutée localement.
- Engines installés de Vite/Oxlint/plugin React : `^20.19.0 || >=22.12.0`.
- Aucun fichier `AGENTS.md` trouvé aux emplacements racine/parents et répertoires
  concernés vérifiés ; consignes de travail utilisateur et plan lus avant modification.

## Commandes et résultats

Commandes exécutées dans `backend` et `frontend` respectivement, avec dépendances
existantes, sans installation ni changement de lockfile :

| Commande | Baseline avant modification | Après modification |
| --- | --- | --- |
| `timeout 120s .venv/bin/python -m pytest -q` | code 1 : 50 passed, 4 failed, 1 warning (1.55 s) | code 0 : 66 passed, 1 warning (1.17 s) |
| `npm run lint` | code 0 : 6 warnings, 0 errors | code 0 : 6 warnings, 0 errors |
| `npm run build` | code 0 : TypeScript + Vite, 2346 modules (1.04 s) | code 0 : TypeScript + Vite, 2346 modules (709 ms) |

`git diff --check` : code 0. Les deux scénarios WS principaux ont aussi été
répétés cinq fois sous `timeout 20s` par exécution : 2 passed à chaque fois
(0.76 s, 0.86 s, 0.94 s, 0.86 s, 0.83 s), sans timeout ni échec.

Les quatre échecs initiaux étaient :

- `test_rename_rejected_for_non_joueur_role` : attendait le refus du renommage
  Présentateur, désormais accepté pour sa propre identité.
- `test_full_multi_client_flow` : attendait deux entrées dans `players` au lieu
  de trois (Présentateur inclus), puis utilisait l'ancien champ et des index filtrés.
- `test_player_and_presentateur_can_rename_themselves_in_lobby` : attendait
  `presentateurName`, supprimé du DTO.
- `test_game_end_early_returns_everyone_to_lobby` : attendait deux entrées
  au lieu des trois participants conservés.

Les tests de refus restent présents : participant inconnu au renommage,
renommage hors lobby, nom vide, rôles/tours/phases invalides. Un test existant
de refus WS qui avalait toute exception, y compris son propre échec, exige
maintenant réellement `WebSocketDisconnect` code 1008. L'assertion de présence
à la reconnexion cible l'ID du joueur, pas l'index zéro du Présentateur.

L'avertissement pytest est la dépréciation Starlette de `httpx` dans TestClient
(conseille `httpx2`). Aucun changement de dépendance pour contourner cela.
Les six avertissements Oxlint préexistants subsistent : trois exports Fast Refresh
dans AudioContext/AvatarPicker, trois paramètres catch inutilisés dans sounds.
Ce ne sont pas des erreurs bloquantes ; aucune règle n'a été désactivée.

## Scénario de référence

Test automatisé `backend/tests/test_rooms_integration.py::test_full_multi_client_flow`,
REST + WebSocket FastAPI TestClient, **quatre connexions simultanées** :
Présentateur Paul, Alice, Bob, Écran principal. Il ne s'agit **pas d'un playtest
navigateur**, ni d'un test réseau réel à travers Railway.

1. Création/jointure REST, vérification des identifiants/rôles, Présentateur dans
   `players` avec avatar et `isPresenter`, Écran principal hors `players`.
2. À chaque action acceptée, les quatre destinataires reçoivent exactement le
   même état public, avec leur propre `role`, `localPlayerId` et code de room.
3. Ajout de thème, démarrage à deux joueurs hors Présentateur, sélection en attente,
   révélation, question en attente, lancement chrono et bonne réponse.
4. Refus d'action de jeu Écran principal, jugement/révélation/chrono Joueur,
   sélection Présentateur, sélection du mauvais joueur, choix avant révélation,
   jugement avant chrono, changement d'identité hors lobby. Les réceptions
   suivantes vérifient aussi l'absence de broadcast parasite sur rejet.
5. Coffrage manuel après la case 1 : exactement 1 point au premier joueur,
   zéro à l'autre, passage au second joueur identifié par ID.
6. Le second joueur reprend les cases 2 à 10, choisit Continuer après chaque
   révélation puis obtient le coffrage automatique terminal : 22 points, total
   23, thème achevé et validé à 10, phase `end`, sous-phase/thème actif effacés,
   historique exact des deux coffrages. Présentateur toujours à zéro et jamais
   actif dans tous les états de jeu reçus.

Tests complémentaires : avatars libres/occupés/inconnus et identité ciblée,
retrait interdit au Joueur et sur le Présentateur, notification `player:kicked`
uniquement à la cible puis fermeture et état public sans elle ; transfert en
lobby et rôles/isPresenter envoyés aux destinataires (deux sync actuels).
Le transfert ne prétend pas valider les permissions des sockets existantes.
Tests moteur sur dix graines de démarrage et plusieurs rotations excluant le
Présentateur ; minimum deux joueurs requis même si le Présentateur est présent.
Reconnexion, absence, fin anticipée et règles métier historiques restent testées.

Toutes les exécutions pytest sont bornées par `timeout 120s` ; code 124 serait
un échec. Le workflow borne aussi chaque job à cinq minutes.

## Diagnostic et limites

- Aucun bug moteur/serveur n'a bloqué le scénario de partie complète et aucun
  correctif applicatif backend n'a été nécessaire. Les échecs initiaux ont été
  confrontés à engine/manager/serialize avant réalignement des assertions.
- `TunnelScreen.tsx` appelait `useEffect` après un retour conditionnel et masquait
  la règle de hooks. L'effet est désormais avant le retour, gardé par l'index
  de thème non nul ; suppression `rules-of-hooks` retirée, effet sonore conservé.
  Diagnostic par inspection de l'ordre des hooks ; outil/agent `bug-finder`
  indisponible dans cette session, aucune délégation de diagnostic revendiquée.
- Limites connues laissées au Bloc 13 : rôle capturé à l'ouverture WS après
  transfert, retrait sans révocation de `room.roles`, reset à l'index zéro,
  identifiants publics utilisés comme reprise, doublons de connexion/présence,
  messages malformés. Ces limites ne sont ni corrigées ni déclarées vertes.
- Pas de persistance, reprise de redéploiement, solo/parité, questions ou
  bibliothèque (Blocs 16-18), refonte UX/audio, ni nouvelle dépendance.
- Build et lint vérifient la compilation/analyse, pas le rendu, les clics ni
  la lecture audio dans un vrai navigateur. Pas de test Docker local.

## CI et verrou distant

Présent : `.github/workflows/ci.yml`, événements `push`/`pull_request`, permissions
`contents: read`, jobs indépendants `Backend pytest` et `Frontend Oxlint and build`,
Python 3.12, Node 22.22.1, installation depuis requirements et `npm ci`, scripts
existants exécutés sans `continue-on-error`, filtre de chemins ni court-circuit.
Toute commande en échec fait échouer son job. Le timeout WS retourne un échec.
**CI GitHub non exécutée ici** : workflow local uniquement, pas de push autorisé.

Procédure à réaliser par le responsable distant, pas réalisée par cette tâche :

1. Après publication autorisée, attendre une première exécution CI sur le SHA
   concerné et relever les deux checks avec leur nom exact dans GitHub.
2. Dans un ruleset/protection de la branche de fusion, exiger PR et succès des
   deux checks (`Backend pytest`, `Frontend Oxlint and build`, noms à confirmer
   sur le premier run), branche à jour ou merge queue adaptée, sans bypass
   non maîtrisé. Vérifier aussi la couverture des pushes directs.
3. Dans Railway, service connecté au bon dépôt/branche, activer l'option
   **Wait for CI** si disponible et vérifier son comportement sur les checks
   requis. `railway.toml` configure un health check, pas cette attente.
4. Sur environnement de test uniquement et après autorisation, publier une
   révision avec test/build volontairement rouge ; conserver URL/SHA/run CI et
   preuve qu'elle n'est ni livrée ni devenue active. Vérifier ensuite qu'une
   révision verte peut être livrée, relever SHA déployé et `/health`.
5. Consigner captures/exports sans secrets, réglages, branche et exceptions.
   Sans cette preuve négative/positive, ne pas annoncer un verrou effectif.

## Proposition au Team Lead

- Bloc 12 : proposer clôture de la référence locale après revue des contrats et
  du scénario, en conservant explicitement révision Railway inconnue et absence
  de playtest navigateur. Mettre à jour l'état présent/partiel/validé du plan
  protégé séparément ; aucune case cochée par cette tâche.
- Bloc 10 : tranche initiale locale livrée (tests/protocole/workflow). Exécution
  GitHub et verrou distant restent non vérifiés ; ne pas clore le bloc entier.
  Parité solo et tests sessions/sécurité/reprise restent différés selon dépendances.
- Pour la spec review : joindre SHA de base et diff local final, DTO `Player`
  (`id`, `name`, `points`, `connected`, `avatar`, `isPresenter`), index dans la
  liste complète, messages `player:set_avatar`, `presenter:transfer`,
  `player:remove`/`player:kicked`, préconditions et limites d'enforcement,
  preuves de tests quatre clients/scores/fin/non-participation Présentateur,
  matrice baseline/après, versions CI, liste des risques Bloc 13 et preuves
  distantes manquantes. Pas de spec créée ou modifiée sans accord sur ce contenu.
