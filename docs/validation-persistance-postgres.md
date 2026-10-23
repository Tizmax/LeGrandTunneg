# Validation Persistance Postgres

## Raccordement Du 2026-10-23 (Approuve En Revue)

Base Git `2ccf905f7d2b913ff7a69e0ebf35e35737526709`, arbre propre avant reprise :
aucun diff partiel de l'appel interrompu. Modifications ci-dessous non committees,
sans push/deploiement, sans acces DB/migration online/provisionnement. Les sections
historiques suivantes decrivent exclusivement la premiere tranche et ne sont plus
la description du runtime courant. Aucun artefact lifecycle protege modifie.

### Livre Dans Le Diff

- `DatabaseConfig.from_environment()` : `DATABASE_PRIVATE_URL` prioritaire si presente, `DATABASE_URL` compatible uniquement en son absence. Valeur privee invalide/vide : erreur sanitisee, jamais fallback. Meme choix serveur/Alembic. TLS reste un choix explicite independant du nom de variable, verify-full par defaut.
- `RoomManager(store, clock, utcnow)` : store injecte obligatoirement ; le singleton d'import ne peut pas admettre de room avant startup. `create_app(..., store=None)` selectionne reellement Postgres au lifespan sauf injection directe. Aucun faux store sous `backend/app/`, aucun mode memoire ou variable de bypass.
- Creation serialisee, adhesion, attach, commandes REST/WS, transfert/retrait, reset, close, expiration, detach et heartbeat passent par candidat prive immutable valide, write OCC, installation, puis publication. Preuves retournees seulement apres succes connu. Sessions anciennes/revoquees, revisions et games restent archivees ; nouveau game UUID au reset uniquement.
- COMMIT inconnu/conflit OCC : un readback borne sans retry. Ancienne revision confirmee => echec sans mutation, room debloquee. Candidat complet confirme (egalite incluant write UUID) => installation et completion/publication uniquement avec autorite valide et sans overlay. Un attach interrompu/non installe est reconcilie absent durablement avant de debloquer. Divergence/absence/readback annule => blocage conserve, readiness false et code de creation reserve ; restauration au startup reste disponible, aucun replay.
- Perte transport : retrait physique exact de l'autorite et capacite avant attente du verrou/DB, overlay absence bloquant commandes et publications. Detach committee puis overlay retire ; echec => blocage jusqu'au restart. Un vieux socket ne peut detacher son remplacant. Livraison bornee hors verrou ; extraction du slot sous verrou evite un envoi pendant la preparation d'un candidat.
- Startup fail-closed : schema head, codec prive et quotas verifies ; restoration avant admission, presence absente committee sans changer acteur/phase/sous-phase/history/deadline UTC. Expiration archivee avant ready. Heartbeat liveness-only a intervalle de sweep plafonne a 60s, idle TTL 24h par defaut, pas de renaissance apres crash.
- `/health` liveness inchangee ; `/health/ready` exige startup fini, aucun blocage/overlay/creation reservee et check DB borne. Echec d'une mutation REST => 503 no-store ; adhesion deja confirmee distincte d'une correction de presence ulterieure (voir cycle residuel ci-dessous). WS erreur sanitisee, auth ferme ensuite en 1013 transitoire sauf cause transport prioritaire, aucune fausse revocation.
- Fixtures TestClient injectees directement ; tests HTTP/WS reels utilisent une factory sous `backend/tests/` et un strict double, plus le test existant de configuration de l'entrypoint production. Ce transport n'est plus une preuve d'un serveur production avec store reel.
- Garde opt-in renforcee : base de test distincte des deux URLs applicatives ; alias DNS toujours a verifier par operateur. Aucun test Postgres execute ici.

### Verification Et Limites

Variables visibles par le processus de travail : `DATABASE_PRIVATE_URL`,
`DATABASE_URL` et `TEST_DATABASE_URL` **absentes** (test de presence uniquement).
Cela ne dit rien des variables Railway, de la connectivite ou du schema distant.
Aucune valeur secrete lue/affichee ; URLs des tests sont des fixtures fictives.

Premier run apres adaptation : 775 tests backend passes. Matrice ajoutee : gates
creation/join/attach/close/command/reset, readback committed/not_committed/blocked,
OCC, annulation pendant readback, reservation creation, detach immediat DB down,
detach pendant commit, six phases/sous-phases restaurees, expiration UTC exacte,
echec schema/load/recovery, heartbeat/reset/archive, priorite/redaction/TLS,
selection Postgres en factory, readiness et erreurs REST/WS.

Resultats finaux : `.venv/bin/python -m pytest -q` =>
**886 passed, 1 skipped, 5 warnings in 67.20s** (87 cas dans la matrice manager),
skip `TEST_DATABASE_URL absent: real Postgres validation deferred; no substitute database.`
Compilation SQL Alembic offline reussie sans connexion,
frontend 97 tests reussis, lint 0 erreur/7 avertissements
preexistants, build tsc/Vite reussi. Python local 3.14, pas une preuve Python 3.12.
Les cinq avertissements backend preexistants sont inchanges. `git diff --check`
sans diagnostic. Aucun test ignore artificiellement pour obtenir ce resultat.

Revue manager approuvee (voir dernier cycle). Restent requis AVANT activation : vrais tests
sur future base dediee autorisee (migration/constraints/OCC/COMMIT ambigu/pool),
restart/crash durable, backup/restore, Python 3.12/Docker/CI distante et Railway.
Un echec non resolu de readback ou de correction durable d'absence reste bloque
jusqu'a restauration. Une confirmation complete positive n'impose plus de restart.
Aucun claim de conformite DB
complete ni deployable ; presence de variable ne prouve jamais accessibilite.

### Propositions Lifecycle Exactes Au Lead

- Spec draft `postgres-persistence-railway-durability-contract` : remplacer `DATABASE_URL` obligatoire par `Une URL Postgres est obligatoire : DATABASE_PRIVATE_URL prioritaire si presente ; DATABASE_URL compatible uniquement en son absence. Une valeur privee invalide ou vide echoue sans fallback. Le choix TLS explicite reste independant du nom de variable.`
- Plan `reconstruction-le-grand-tunneg` : ajouter `Deuxieme tranche raccordee en diff local depuis 2ccf905 : manager/routes/WS/startup commit-gated, restore/readiness, doubles stricts injectes. Revue manager et validation sur vraie base differees ; aucun acces DB, migration online ou deploiement effectue.` Ne cocher ni Bloc 2 ni Bloc 14.
- Contrat Bloc 13 : conserver la baseline historique memoire comme historique et sa Purpose de transition ; ne pas presenter les doubles comme preuve de persistance. Ne pas promouvoir le draft avant review et preuves reelles.
- Railway, preparation uniquement : futur healthcheck `/health/ready`, pre-deploy explicite `python -m alembic upgrade head`, un worker/replica, variables via references secretes ; aucune configuration distante ni execution realisee.
- Spec draft, ajouter : `MAX_REST_OPERATIONS=32 borne les operations create/join/resume globales du processus depuis la lecture du corps jusqu'a la fin de l'attente verrou/persistance et de leur nettoyage. Admission immediate sans queue, saturation 503 no-store ; REST_OPERATION_TIMEOUT_SECONDS=15 declenche l'annulation, avec les budgets DB de resolution/nettoyage en supplement si necessaires. Entier positif pour la capacite, delai positif fini. Liberation en finally sur toutes les issues.`
- Precision protocole a valider, sans affaiblir le gate : `Une adhesion confirmee par COMMIT ou readback complet rend son identite/preuve privee lorsque le transport HTTP le permet, distinctement de la disponibilite de presence. Si la correction durable d'un autre transport echoue, HTTP 200 no-store confirme uniquement cette adhesion avec state:null et persistenceUnavailable:true ; room bloquee, aucune publication, reprise avec la meme preuve et aucune adhesion rejouee. Une mutation non confirmee ne rend jamais une preuve de succes. Aucune garantie exactly-once de livraison HTTP ; une coupure avant reception du credential reste une limite.`
- Client, ajouter : `Un recu JOIN degrade conserve la preuve dans l'identite v2 et affiche une indisponibilite sanitisee. Une erreur persistence_unavailable pre-auth ou une fermeture 1013 conserve cette identite, affiche la raison et permet reprise/backoff avec la meme preuve, y compris apres reload ; aucune nouvelle adhesion automatique. Seul room:state_sync authentifie ouvre le jeu.`
- Livraison, ajouter : `Sous verrou, avant extraction de tout slot pending, une room blocked ou avec overlay absent interdit l'envoi : slot obsolete jete et wake efface sans polling. Toute correction de presence committee enqueue ensuite le snapshot corrige aux destinataires autorises. Slot unique coalesce, ordre monotone et reseau hors verrou conserves.`
- Readiness, ajouter : `GET /health/ready admet au maximum une verification store.check simultanee par processus, admission immediate sans queue et sans setting supplementaire. Budget endpoint de verification 2 secondes, plus nettoyage borne du repository si necessaire ; finally libere sur succes/erreur/timeout/annulation. Saturation ou room deja indisponible : 503 sanitise no-store sans requete DB ; reponse ready egalement no-store. /health reste une liveness sans acces DB.`
- Precision livraison au lead, sans assouplissement : `Un snapshot extrait attendant le verrou d'envoi revalide disponibilite de room et autorite exacte socket/delivery apres acquisition de ce verrou, immediatement avant l'entree dans send_json sans nouvel await. Refus silencieux sans acquittement, aucun polling ; les erreurs ciblees restent distinctes. Un budget unique inclut attente du verrou et envoi. Ce point de linearisation ne rappelle pas les trames deja entrees dans le transport et ne garantit pas leur instant de reception. Aucun verrou de mutation pendant I/O.`

### Corrections Avant ROUND2 FINAL

- Presence croisee : A se detache pendant le commit d'attach B ; B jamais installe est aussi normalise absent durablement. Overlay maintenu et publication bloquee jusqu'au succes ; echec correction reste fail-closed.
- Lecteur transport unique independant du processeur DB, queue bornee au burst WS ; test avec vrai objet Starlette WebSocket et frame ASGI disconnect avant liberation du write, autorite retiree immediatement. Overflow retire aussi l'autorite avant toute fermeture reseau.
- Reservation auth globale avant premier await, incluant commits cross-room et sockets remplacees pas encore fermees ; finally sur annulation/echec/rejet. Tests plafond 1 cross-room et plafond 2 remplacement.
- Gate REST global incluant lecture/lock/DB, timeout et liberation ; suppression du sweep global avant create. Tests saturation HTTP avec write suspendu, annulation/timeout/requete suivante et deadline TTL non rafraichie par resume.
- Heartbeat a chaque sweep connecte (plus de filtre d'age dephase), scheduler monotone plafonne a 60s sans ajouter la duree du sweep ; readiness false si signal connecte age de plus de 60s ou echec write. Pas de promesse temps reel pendant DB bloquee/event loop suspendue, pas de heartbeat par message.
- Matching COMMIT : preuves tests strict double create/attach/commande sans replay, annulation attach postcommit suivie d'absence durable ; pas de modification du contrat pour masquer un blocage permanent.

Ces scenarios sont des preuves unitaires/adversariales offline seulement, jamais
une preuve de transaction ou de restauration sur vrai Postgres. Les cinq majeurs
ont ete confirmes resolus lors de la revue precedente ; trois residuels ont
necessite le nouveau cycle explicitement autorise ci-dessous. Aucune approbation
finale du raccordement n'est anticipee.

### Nouveau Cycle Apres Escalade R2

- Finalisation join : adhesion confirmee distincte de correction de presence. La route REST exacte A-connecte/join-B-suspendu/perte-A retourne l'identite de B, jamais un 503 qui orphelinerait son unique preuve. Correction reussie : etat corrige publie, auth et reprise possibles sans nouvelle place. Echec ou annulation de correction : 200 no-store avec preuve, state:null et persistenceUnavailable:true ; aucun sync incoherent, auth/reprise fail-closed jusqu'a restauration. Correction et readback utilisent les budgets DB existants, sans boucle/replay.
- Notification : la reconciliation de presence possede elle-meme l'enqueue du snapshot corrige apres commit et retrait d'overlay. Test A acteur/C connecte/attach B suspendu/perte A sans release : C recoit active-absent avec A et B absents meme si attach B echoue. Release A tardif n'est pas necessaire ; slots coalesces bornes, ordre monotone et aucun envoi sous verrou conserves.
- Cause terminale transport : le lecteur unique conserve overflow 4429/rate_limited, retire l'autorite immediatement, puis le finally attend le nettoyage durable avant erreur ciblee et fermeture unique. Aucune erreur persistence_unavailable/1013 concurrente ; disconnect normal ne devient pas une erreur auth. Matrice ASGI auth/post-auth x overflow/disconnect x correction succes/echec/annulation/COMMIT inconnu positivement confirme ; aucune commande en queue rejouee, aucune reservation/delivery restante.
- Reproduction avant correctifs : huit nouveaux cas adversariaux echouaient (dont une fixture acteur a corriger), un passait. Les assertions finales de protocole, publication et preuve ont ensuite ete executees, pas seulement inspectees. StrictStore reste uniquement sous tests ; aucune preuve de COMMIT/DDL/OCC sur vrai Postgres.
- Verification finale executee : matrice manager 79/79, backend complet 878 passes/1 skip/5 warnings, frontend 96/96, lint 0 erreur/7 warnings preexistants, build tsc/Vite reussi, Alembic SQL offline reussi et git diff --check sans diagnostic. Les 21 cas ajoutes depuis la baseline 857 couvrent quatre issues REST, une notification tierce et seize scenarios ASGI transport/nettoyage ; aucun test de vraie base execute.

Nouvelle revue manager obligatoire avant tout commit. Pas de contact DB,
provisionnement, migration online, push ou deploiement dans ce cycle ; specs et
plans proteges laisses intacts. Les propositions lifecycle ci-dessus restent au
lead. La validation de persistance reelle demeure differee.

### Dernier Cycle ROUND1 Vers ROUND2

Revue `ses_e97d506c6ffedr2o2YLE5db1lY` : trois majeurs et un mineur corriges,
approbation ROUND2 finale encore requise. Aucun changement du contrat protege.

- Pending avant perte transport : garde sous verrou dans `_deliver`, pas seulement a l'enqueue. Deux tests C-pending/A-perdu, avec overlay seul ou echec write de correction, verifient aucun sync A-connected apres unlock, slot vide/wake efface, puis uniquement snapshot absent apres reconciliation durable.
- Client degrade : type JOIN state nullable et flag explicite, propagation Accueil/App/hook, message local sanitise pre-auth, bouton reprise, backoff conserve. Test UI complet 200 null -> erreur pre-auth/1013 -> reprise -> reload -> erreur/1013 -> recovery : identite/preuve inchangees, un seul POST nouvelle adhesion, gameplay uniquement apres sync authentifie, aucune preuve rendue a l'ecran.
- Readiness publique : un seul check simultane sans file, timeout 2s ; quatre tests HTTP de 33 requetes concurrentes couvrent succes/erreur/cancel/timeout, rejet immediat des 32 autres, liberation pour la requete suivante et aucun check si room bloquee.
- Disconnect recu : le lecteur distingue le frame disconnect d'un echec transport. Retrait autorite immediat et nettoyage durable restent actifs ; release n'envoie aucun terminal ni fermeture apres disconnect recu. Les huit branches disconnect de la matrice ASGI assertent zero tentative close (dont aucun 1011) avec succes/echec/annulation/readback confirme.
- Verification executee apres correctifs : backend complet 884 passes/1 skip/5 warnings (47.52s), matrice manager 85 passes (7.39s), frontend 97 passes (14.61s), lint 0 erreur/7 warnings preexistants, build tsc/Vite reussi, Alembic upgrade head --sql reussi offline, git diff --check sans diagnostic. Six nouveaux cas backend et un test UI depuis la baseline 878/96 ; les assertions disconnect ont aussi ete renforcees dans les cas existants. Une erreur TypeScript dans le selecteur du nouveau test UI a ete corrigee avant le build final reussi.

Limite : le recu JOIN rend la preuve seulement lorsque le transport HTTP permet
la reponse, jamais une promesse exactly-once. Les nouveaux tests sont offline,
pas une preuve de disponibilite ni de persistance Postgres reelle.

### Cycle Cible Snapshot Extrait

Nouvelle autorisation apres ROUND2 de `ses_e97d506c6ffedr2o2YLE5db1lY` :
garde pending conservee, revalidation ajoutee dans `RoomManager.send` APRES
acquisition de `delivery.send_lock`. Snapshot seulement : room sans blocage,
overlay ni fermeture, delivery courante non arretee, socket exacte toujours
autorisee pour ce destinataire. Aucun await entre ces lectures et l'entree
directe dans `socket.send_json`. Le bool de retour empeche un snapshot jete
d'acquitter une authentification. Les erreurs ciblees ne sont pas interdites par
un blocage de room ; le budget send unique continue de couvrir lock et I/O.

- Reproduction executee avant correctif : 1 echec/1 succes. C recoit une erreur lente tenant send_lock ; worker extrait le snapshot A-connected et attend ce verrou ; perte A puis correction DB en echec ; liberation erreur avant timeout faisait entrer le snapshot obsolete dans le transport. Le test echouait sur la queue sortante non vide.
- Apres correctif : les deux cas passent. Le premier verifie erreur ciblee delivree, aucun snapshot/ack pendant blocage, puis snapshot A-absent apres reconciliation explicite confirmee. Le second remplace C pendant lockwait, verifie aucun snapshot sur l'ancien socket et que son release ne detache ni ne deconnecte le remplacant. Locks observes par evenements, reseau assert hors verrou de room, doubles uniquement sous tests.
- Regression executee : backend complet 886 passes/1 skip/5 warnings en 67.20s ; frontend 97 passes, lint 0 erreur/7 avertissements preexistants. La commande groupee frontend a atteint son timeout outil de 120s pendant build ; relance separee `npm run build` reussie (TypeScript puis Vite). Alembic `upgrade head --sql` offline reussi, sans connexion. `git diff --check` sans diagnostic.

Point de linearisation raisonnable : apres le verrou d'envoi, la tache asyncio
effectue validation synchrone et entree directe dans la coroutine send_json sans
ceder la main entre les deux. Starlette encode puis entre dans son send ASGI ;
une suspension interne du transport peut survenir ensuite. Impossible de rappeler
une trame deja engagee ni de promettre son heure de reception ; ce correctif ne
fait pas cette promesse. Pas de reseau sous room.lock, pas de polling, pas de
nouvelle queue ni retry de commande. Les tests offline ne prouvent pas Postgres.

Specs modifiees par le lead entre les cycles conservees intactes ; aucun edit
lifecycle par ce cycle. Revue manager `ses_e97c05b9bffeWcB6OHktksUTj2` :
**APPROVED** code/security/requirements, spec **NO_ACTION_NEEDED**, aucun residuel.
Le lead a actualise le journal du plan via lifecycle et valide sa structure.
Cette approbation autorise le commit du raccordement, pas son deploiement :
les validations sur vraie base Postgres restent **NON EXECUTEES** (transactions,
OCC/COMMIT ambigu reseau, migrations online, crash/restart et backup/restore).
Aucun push/deploiement/contact DB/provisionnement/migration online effectue.

## Historique Premiere Tranche

## Statut

2026-10-21, baseline `2d0e0cb` plus diff local non committe.
**Preparation partielle uniquement. NON deployable comme service persistant.**
La future base n'est pas disponible et aucun substitut n'a ete cree, utilise ou
configure. Aucun commit, push, provisionnement, deploiement ou service CI DB.
Les tests par mocks sont exclusivement dans `backend/tests/`.
ROUND2 FINAL APPROVED : preparation isolee approuvee ; les trois majeurs
ROUND1 sont resolus par inspection independante. Specs approuvees semantiquement.
Les preuves d'execution ci-dessous sont rapportees par le producteur, pas
reexecutees par les reviewers. Les vrais tests DB restent differes ; cette
approbation ne valide ni le raccordement applicatif ni un service durable deployable.

Le contrat draft `postgres-persistence-railway-durability-contract` a ete lu
integralement, ainsi que le contrat actif Bloc 13 et les blocs 2/5/14 du plan.
Les modifications preexistantes des deux specs ont ete preservees ; aucun plan
ni spec n'a ete edite par cette implementation.

L'outillage de cette session n'expose pas de delegation a des agents. Pour ne
pas simuler une revue/delegation ni realiser une bascule de production incomplete,
la tranche est limitee aux fichiers isoles stockage/codec/migrations et leurs
tests/documentation/packaging. Manager, routes REST/WS, main et lifecycle n'ont
pas ete modifies. Leurs tests restent des preuves du Bloc 13 en memoire, jamais
des preuves Postgres. Aucun nouveau backend memoire configurable/fallback.

## Interfaces Preparees

- `DatabaseConfig.from_environment()` : DATABASE_URL obligatoire pour le repository/les migrations online, Postgres uniquement ; pool et delais positifs finis, URL masquee. Ce n'est PAS encore une obligation au startup de l'application baseline.
- `encode(snapshot: Snapshot) -> str`, `decode(payload: str) -> Snapshot` : format prive v1 strict et immutable, validation profonde, versions/champs/types inconnus refuses ; conversion explicite GameState sans serialize_state ni runtime Room.
- `PostgresStore.write(candidate: Snapshot, expected_revision: int, event: Event | None) -> None` : candidat revalide, creation ou OCC verrouille NOWAIT, transaction unique pointeur/snapshot/sessions/event, COMMIT explicite ; None reserve au heartbeat liveness-only. Aucun callback d'installation/publication dans le repository.
- `PostgresStore.reconcile(candidate: Snapshot, expected_revision: int) -> Literal["committed", "not_committed", "blocked"]` : readback unique borne, egalite complete pour confirmer ; ancienne revision lue sous verrou pour constater non-commit ; absence a la creation/divergence/timeout => blocked. Aucun rejeu/retry automatique/exactly-once arbitraire.
- `PostgresStore.load_live() -> tuple[Snapshot, ...]` : lecture repeatable-read/read-only, coherence payload/colonnes/sessions, rejet de tout le restore si corruption. Ne normalise PAS encore la presence.
- `PostgresStore.check()` : revision Alembic exacte ; `close()` : disposal borne. Erreurs operationnelles sanitisees, `RevisionConflict` et `CommitUnknown` distincts mais sans detail SQL public.
- `PostgresStore.connection(timeout=None)` : contexte borne partage par lectures et Alembic online ; fermeture sous budget de nettoyage independant, sans `AsyncConnection.__aexit__` shield non borne.

## Correctifs ROUND1

- Nettoyage : `DB_CLEANUP_TIMEOUT_SECONDS=2`, positif fini et maximum 10.
  Budget supplementaire unique pour rollback pre-COMMIT puis fermeture, egalement
  pour lectures et migration online. Les annulations externes repetees ne
  reinitialisent pas ce budget. A expiration/echec, detachement synchrone du pool
  et `asyncpg.Connection.terminate()` ; aucune fermeture gracieuse attendue sans
  borne. Une tache de finalisation resistante a cancellation est annulee sans
  etre attendue, son exception consommee, son transport deja termine. Valeurs
  par defaut : transaction/readback 10s + nettoyage 2s, hors ordonnancement de
  l'event loop et travail synchrone ; pas une garantie temps reel. L'acquisition
  annulee avant retour de connexion reste geree par SQLAlchemy/asyncpg.
- Classification : avant soumission de COMMIT, erreur =>
  `PersistenceUnavailable`, conflit => `RevisionConflict`, cancellation externe
  => `CancelledError` conservee apres nettoyage. Apres soumission : echec,
  timeout ou cancellation => `CommitUnknown`, jamais de retry. Un echec de
  fermeture meme apres reponse COMMIT positive est classe conservativement
  `CommitUnknown` et impose le readback habituel, jamais un rollback/rejeu.
- Codec : case 10 implique `completed=true` ET `validated_squares=10` ; theme
  termine interdit comme theme actif en tunnel, pour les quatre sous-phases.
  Sous 10, progression non coffree autorisee, sans egalite forcee des compteurs.
  Roundtrip d'une sequence moteur reelle de dix reponses, auto-coffrage inclus.
- TLS : `DB_TLS_MODE=verify-full` par defaut dans repository ET Alembic online.
  `ssl.create_default_context()` utilise les CA systeme, `CERT_REQUIRED` et
  verification hostname. Pas de TLS `prefer`, fallback ou downgrade. L'option
  explicite `private-network` transmet `ssl=False` uniquement pour un hostname
  DNS valide termine par `.railway.internal`, jamais apex/IP/localhost/public.
  Cette garde valide le nom, pas l'appartenance reelle du processus au reseau
  Railway ; responsabilite operateur. Aucun CA custom/PKI ajoute.
- Erreurs de configuration directes : `Invalid DB_TLS_MODE or private-network hostname.`,
  `DB_CLEANUP_TIMEOUT_SECONDS must not exceed 10.`,
  `DB timeouts must be positive and finite.`. Chargement environnement :
  `Invalid Postgres configuration.`. Erreur store :
  `Room persistence unavailable.`. Aucun de ces messages ne contient URL,
  credentials ou detail SQL ; migration online : `Postgres migration failed.`.

Le store conserve les revisions et revocations, refuse une reactivation/omission
de preuve revoquee et impose game UUID nouveau sur reset uniquement. Le schema
et la migration additive sont documentes dans `schema.md`. Aucune suppression,
purge ou cascade. Les quotas applicatifs configurables ne sont pas figes dans
le format prive, pour eviter un echec de restauration apres changement de quota.

## Commandes Executees

Toutes les commandes ci-dessous ont termine avec exit 0 sur Python 3.14 local,
sauf l'essai explicite de pip mentionne ensuite.

| Repertoire | Commande | Resultat |
| --- | --- | --- |
| backend | `.venv/bin/python -m pytest -q -rs` | **775 passed, 1 skipped, 5 warnings in 14.18s** (dernier run ; precedent identique en 21.58s) |
| backend | `.venv/bin/python -m alembic upgrade head --sql` | SQL PostgreSQL genere : BEGIN, alembic_version, 4 tables, index partiel live_room_code_unique, contraintes/FK, stamp 0001_private_snapshots, COMMIT ; aucune connexion |
| frontend | `npm test -- --run` | **96 passed**, 5 fichiers, 9.96s |
| frontend | `npm run lint && npm run build` | **0 erreur, 7 avertissements**, tsc puis Vite reussis, 2347 modules ; JS 421.12 kB / gzip 130.39 kB |
| racine | `git diff --check` | Aucun diagnostic |

102 tests offline ajoutes aux 673 tests baseline (45 ajoutes apres ROUND1,
730 tests reussis avant correctifs). Ils couvrent codec roundtrip,
malformed/unknown/version/cles dupliquees/champs runtime, coherence sessions,
sous-phases avec acteur absent, config/url masquee, transaction creation et
mutation existante avec mocks SQLAlchemy, injection d'echec de chaque statement
de creation, OCC, COMMIT inconnu y compris cancellation, cancellation avant
commit, non-reactivation, game UUID reset, heartbeat, incoherence des lectures,
reconciliation committed/not_committed/blocked/timeout. Ils ne prouvent PAS les
transactions asyncpg reelles ni le gate de toutes les mutations du manager.
Correctifs testes hors DB : blocages execute/rollback/COMMIT/fermeture, annulations
externes repetees, fermeture resistante a cancellation, echec nettoyage sans
fuite, fermeture bornee check/load/reconcile, budgets invalides, TLS connect_args
store et Alembic online avec doubles injectes, CA/hostname et mauvais modes/hosts.
Un essai intermediaire a eu cinq echecs de fixtures (nouveaux joueurs absents par
defaut) ; fixtures corrigees via `engine.set_player_connected`, aucune assertion
de production relachee ni test desactive. Suite finale ci-dessus verte.

Skip exact : `tests/test_postgres_optin.py:38` :
`TEST_DATABASE_URL absent: real Postgres validation deferred; no substitute database.`
Le test futur couvre creation/restauration, fermeture archivee, OCC, reconciliation
et comptes de lignes. Exiger DB dediee distincte, suffixe `_test`, acquittement
`TEST_DATABASE_ACK=dedicated-disposable-database` et migration explicite prealable.
Il ecrit des donnees de test archivees, ne purge rien. Ce test n'a PAS ete execute
contre Postgres. Cette garde ne remplace pas la verification operateur des alias
DNS/credentials de la base dediee.

Warnings backend exacts : un StarletteDeprecationWarning sur httpx TestClient,
un DeprecationWarning websockets.legacy, un UvicornDeprecationWarning sur
websockets_impl, deux DeprecationWarning `remove second argument of ws_handler`.
Warnings lint : `only-export-components` AudioContext:181 et AvatarPicker:6/13,
`no-unused-vars` sounds:407/410/411, `set-state-in-effect` useRoomConnection:66.
Ils sont preexistants et aucun warning n'a ete desactive.

L'environnement n'avait pas greenlet : premiere compilation offline avant
separation des imports online a revele le besoin SQLAlchemy async. Extra
`sqlalchemy[asyncio]` declare dans requirements. Essai
`.venv/bin/python -m pip install 'sqlalchemy[asyncio]'` en echec
`No module named pip`, puis `uv pip install --python .venv/bin/python 'sqlalchemy[asyncio]'`
reussi (greenlet 3.5.6). Aucun composant d'infrastructure installe.

## Non Livre

- Store unique production branche au manager, DATABASE_URL obligatoire au startup et rejet de tout mode memoire applicatif.
- Orchestration candidate -> commit -> install -> publish pour create/join/revoke/transfer/reset/end/close/expiration/presence ; game UUID conserve sauf reset, selon le contrat.
- Overlay presence identity-safe immediat sur transport loss pendant DB down/COMMIT, gated eligibility, livraison hors lock bornee, doubles races DB/WS et tests de toutes les mutations.
- Blocage runtime/readiness false et reservation du code de creation pendant COMMIT inconnu ; scheduling de reconciliation et lifecycle d'annulation associes.
- Startup restore-before-admit, normalisation absente committee, aucun rerandomize/reset, heartbeat 60s, deadline UTC/monotonic sans renaissance TTL apres crash.
- `/health/ready` et distinction effective liveness/readiness. `/health` baseline reste inchange.
- Injection explicite des doubles dans les fixtures de routes adaptees au futur backend ; restriction des futurs tests serveur persistant a TEST_DATABASE_URL. Les tests Uvicorn actuels testent encore explicitement le serveur baseline non branche, sans faux backend Postgres.
- Vrais tests de migration/contraintes/rollback/OCC/commit inconnu sur future base, scenarios Railway/restart/backup/restore, Docker build, Python 3.12, CI distante, playtest navigateur et review independante.

L'absence de delegation et la taille de l'orchestration justifient une tranche
coherente, pas une affirmation de conformite complete. Les tests unitaires ne
doivent pas etre presentes comme validation des points ci-dessus.

## Activation Et Risques

Ne PAS activer/deployer cette preparation comme implementation de la spec.
Conserver un worker et un replica. Le Dockerfile embarque Alembic, mais ne lance
aucune migration implicitement. Commande pre-deploy future, seulement une fois
orchestration/tests/review termines : `python -m alembic upgrade head` depuis backend
ou /app, avec DATABASE_URL injectee. Compilation offline seule dans CI, aucun
service Postgres CI ajoute.

Avant activation : terminer tous les points non livres, revue croisee des
interfaces et invariants, puis tests sur future base dediee disponible. Tester
de vrais crashs/COMMIT ambigus et contraintes Postgres ; les mocks ne reproduisent
ni locks reseau, ni driver, ni resultat d'un COMMIT interrompu. La migration fixe
et les metadata dupliquent volontairement le schema ; verifier leur alignement
lors de chaque evolution. Retention indefinie augmente le volume en base ; aucun
quota disque ni backup externe livre. Le repository impose append-only, pas les
droits SQL d'un operateur privilegie. Cancellation et nettoyage du pool/connexion
doivent encore etre verifies avec asyncpg reel.

Rollback non destructif uniquement : binaire compatible schema/codec/sessions
valide, jamais DROP/TRUNCATE/downgrade destructif ni retour silencieux a la
memoire apres activation. `downgrade()` refuse explicitement la destruction.

## Propositions Pour Le Lead

Pas d'edition de plan realisee. Replacements courts exacts proposes :

- Bloc 2 : `sur une instance Postgres locale sans erreur` -> `sur une future base Postgres dediee disponible sans erreur`.
- Historique Bloc 13 : `consolidation suivante implémentée et approuvée par revue indépendante ROUND2, encore non committée.` -> `consolidation suivante implémentée et approuvée par revue indépendante ROUND2, committée en 2d0e0cb.`
- Ajouter une progression partielle : codec/store/schema/migration prepares, orchestration et vrais tests DB non livres. Ne cocher ni Bloc 2 ni Bloc 14 (Bloc 5 reste ouvert).
- Proposition settings/lifecycle au lead : `DB_TLS_MODE=verify-full par defaut (CA systeme + hostname), private-network explicite seulement pour *.railway.internal sans TLS ; DB_CLEANUP_TIMEOUT_SECONDS=2, maximum 10, budget additionnel sans retry COMMIT.` Aucun fichier protege modifie.
