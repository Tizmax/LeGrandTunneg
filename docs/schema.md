# Schema Postgres Prepare

Tranche de preparation uniquement, non branchee au manager. Voir
`validation-persistance-postgres.md`. Aucun historique/profil/bibliotheque/UI.

Migration additive : `backend/migrations/versions/0001_private_snapshots.py`.
Le DDL est fige dans la migration, pas importe depuis les modeles futurs.

| Table | Identite / contenu |
| --- | --- |
| rooms | UUID stable, code reutilisable, game UUID courant, revision et write UUID, statut live/closed/expired, dates UTC de creation/fermeture/liveness/deadline |
| snapshots | Cle (room UUID, revision), game UUID, write UUID unique, format prive v1, payload JSONB complet et immuable par l'API repository |
| sessions | Cle (room UUID, revision, participant UUID), digest SHA-256 32 octets, role, statut active/revoked, dates ; chaque revision garde les preuves revoquees |
| events | Event UUID = write UUID, room/game UUID, revision unique par room, date UTC, commande enumeree, acteur/cible UUID ; aucun payload arbitraire |

Seuls les codes `live` sont uniques (index partiel). Les fermetures ne suppriment
aucune ligne. Reset change le game UUID sans supprimer les anciennes revisions.
Les sessions courantes se lisent exclusivement a la revision pointee par rooms ;
une ancienne preuve archivee n'autorise jamais une session. Les index/FK ne
contiennent aucun `ON DELETE CASCADE`. Aucune purge et aucun downgrade destructif.
L'immutabilite est une regle du repository, pas une protection contre un operateur
SQL ayant des droits d'ecriture directs.

Le codec valide les references joueurs/presentateur/sessions, les enums, types,
index, sous-phases, avatars, champs de themes et dates UTC. Seuls les digests sont
acceptes. Il refuse les champs inconnus, les versions inconnues et les cles JSON
dupliquees. Sockets, locks, tasks, files et horloges monotoniques n'en font pas
partie. `serialize_state` n'est jamais utilise pour persister.

`PostgresStore.write(candidate, expected_revision, event)` verrouille la ligne
existante sans attente, verifie la revision et les invariants inter-revisions,
ecrit pointeur/snapshot/sessions/event dans une transaction unique. Le timeout
inclut COMMIT. L'appelant ne doit installer/publier qu'apres retour confirme ou
readback complet correspondant. `CommitUnknown` et `RevisionConflict` exigent
un blocage runtime, non encore implemente dans cette tranche.

`reconcile(candidate, expected_revision)` fait un seul readback borne avec verrou
de ligne NOWAIT : egalite complete => committed ; ancienne revision verrouillee
apres resolution de la transaction => not_committed ; sinon blocked. Une ligne
absente a la creation reste blocked, jamais interpretee comme rollback. Aucun
retry/rejeu et aucune garantie arbitraire exactly-once.

`load_live()` verifie payload et duplications rooms/snapshots/sessions dans une
transaction read-only repeatable-read bornee ; toute corruption rejette l'ensemble.
La normalisation de presence/restauration et l'admission restent a implementer.
