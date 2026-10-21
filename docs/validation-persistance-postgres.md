# Validation Persistance Postgres

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
