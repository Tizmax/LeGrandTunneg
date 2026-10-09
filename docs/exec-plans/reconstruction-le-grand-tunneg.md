---
status: draft
created: 2026-10-10
updated: 2026-10-10
---

## Goal

Reconstruire intégralement "Le Grand Tunneg" — jeu de plateau/quiz multijoueur façon Fort Boyard — en quittant l'architecture Flask/session-cookie/Alpine.js monoposte de l'original pour une application web multi-device en temps réel (FastAPI + WebSocket + React/Vite/Tailwind + Postgres), avec un rôle Animateur central qui valide les réponses, une direction artistique "Jazz Club feutré / La La Land" soignée, et un déploiement Railway propre en un seul service.

## Contexte de référence (lecture obligatoire avant d'implémenter la logique de jeu)

Le code original à reproduire fidèlement pour la logique métier se trouve dans :
- `/home/tdyt8585/projets/Tunneg/flask-clean/app.py` — en particulier `get_question_points()` (lignes 114-122), `coffrer()` (lignes 133-144), `poursuivre()` (lignes 146-154), et le handler `update_progress()` (lignes 155-185) qui orchestre les 4 actions de jeu.
- `/home/tdyt8585/projets/Tunneg/flask-clean/templates/base.html` — en particulier la formule de coloration des cases (lignes 400-410 pour la mini-grille thème, lignes 454-464 pour le tunnel plein écran) et le minuteur 60s avec paliers de couleur (lignes 94-103).

Ce fichier exec-plan fige la spécification exacte de cette logique ci-dessous : tout implémenteur backend doit s'y référer en priorité, le code original n'étant utile que pour lever une ambiguïté résiduelle.

## Spécification figée des règles de jeu (dérivée du code original, ne pas réinterpréter)

### Modèle d'une barre de thème ("tunnel")
```
{
  progress_value: int,       // 0..10 — nombre de cases "jouées" (tentées), position de la prochaine case à contester
  validated_squares: int,    // 0..10 — haut-niveau atteint par le coffrage (compteur cumulatif, pas un ensemble)
  discovered: bool,          // true = une question est actuellement "live" sur ce thème (case en cours de contestation)
  completed: bool,           // true une fois la case 10 coffrée automatiquement
  nullified: int[]           // liste des numéros de case (1-indexés) définitivement passées, ne rapporteront jamais de points
}
```

### Barème de points (`get_question_points(n)`, n = numéro de case 1-indexé)
- n ∈ [1,3] → 1 point
- n ∈ [4,6] → 2 points
- n ∈ [7,9] → 3 points
- n == 10 → 5 points

### Couleur d'une case k (1-indexée, k ∈ [1,10]) — ordre de priorité strict
1. **Noir** si `k ∈ nullified` (toujours prioritaire, même si coffrée après coup — une case nullifiée ne rapporte jamais de points, peu importe l'état de `validated_squares`)
2. **Gris** sinon si `k <= validated_squares` (coffrée définitivement)
3. **Vert** sinon si `k <= progress_value` (répondue correctement, pas encore coffrée — prise de risque possible/vol par un adversaire)
4. **Jaune** sinon si `(k - 1) == progress_value` ET `discovered == true` (case actuellement en train d'être contestée, question lue par l'animateur)
5. **Vide** sinon

### Transition `discovered`
- Passe à `true` quand un thème est sélectionné (première fois ou reprise) et quand l'action "Continuer" est choisie après une bonne réponse.
- Passe à `false` uniquement au tout début du traitement d'une "Bonne réponse", avant l'avancement de `progress_value`.
- **Ne se réinitialise PAS** explicitement après "Mauvaise réponse", "Passer" ou un coffrage — ce comportement de l'original est intentionnel et doit être reproduit à l'identique : le flag `discovered` sert de marqueur "ce thème a une case activement contestée" qui survit au changement de joueur, ce qui permet à l'UI de renvoyer directement sur l'écran du tunnel (sans ré-afficher un écran intermédiaire) quand un autre joueur reprend ce thème.

### Actions de jeu — phase "question posée" (validées par l'Animateur)
- **Bonne réponse** : `discovered = false`, puis `poursuivre()` :
  - si `progress_value == 9` → `progress_value = 10`, déclenche un **coffrage automatique** (`coffrer()`, voir plus bas), puis `completed = true`.
  - sinon si `progress_value < 10` → `progress_value += 1`.
  - Résultat visuel : la case qui vient d'être validée passe en vert (ou le thème se termine et toutes ses cases encore vertes passent en gris avec crédit de points, cf coffrage auto).
- **Mauvaise réponse** : le tour passe au joueur suivant (`current_player_index + 1 mod n`), retour à l'écran de sélection de thème. **Aucune perte de progression** : `progress_value`, `validated_squares`, `nullified` restent inchangés — la case reste verte, exposée à un "vol" si un autre joueur reprend ce thème et le coffre plus tard.
- **Passer** : la case `progress_value + 1` est ajoutée à `nullified` (noire pour toujours), puis `poursuivre()` est appelée (la progression avance quand même d'une case, sans gain possible sur cette case précise). Le tour ne passe PAS automatiquement au joueur suivant dans l'original (le joueur courant reste actif) — reproduire ce comportement.

### Actions de jeu — phase "après bonne réponse" (risque/récompense, affichée seulement juste après une bonne réponse non terminale)
- **Continuer** : `discovered = true` (nouvelle question posée sur le même thème, la progression actuelle reste exposée au risque).
- **Coffrer** (`coffrer()`) : pour chaque case `i` de 1 à `progress_value` non encore comptée dans `validated_squares` (c'est-à-dire `i > validated_squares` courant, traité dans l'ordre croissant) : incrémenter `validated_squares`, et si `i ∉ nullified`, créditer `get_question_points(i)` au joueur courant. Puis faire passer le tour au joueur suivant et revenir à l'écran de sélection de thème. **Ce bloc de code est strictement identique que l'appel vienne de l'action manuelle "Coffrer" ou du coffrage automatique en case 10.**

### Thèmes complétés — garde-fou à AJOUTER (absent de l'original, classé comme dette à corriger)
Un thème avec `completed == true` (coffré jusqu'à la case 10) doit être non-sélectionnable : grisé côté UI et rejeté côté serveur si un message de sélection arrive malgré tout pour ce thème.

### Reset de partie vs retour au menu (comportement voulu, divergent du code original qui ne vide jamais rien sur "retour menu")
- **Réinitialiser la partie** (action réservée à l'Animateur) : remet tous les scores joueurs à 0 et toutes les barres de thème à l'état initial (`progress_value=0, validated_squares=0, discovered=false, completed=false, nullified=[]`), **conserve** la liste des joueurs et la liste des thèmes, reste dans la même room.
- **Quitter la partie / Retour à l'accueil** (action réservée à l'Animateur) : termine la room — vide joueurs, thèmes, état de jeu en mémoire pour cette room, déconnecte proprement tous les clients vers l'écran d'accueil. Diverge volontairement du code original (qui ne faisait rien à part changer un simple champ d'état) : c'était un bug de l'original, pas un comportement à reproduire.

## Décisions produit déjà actées (ne pas rouvrir, ne pas redemander à l'utilisateur)

1. **Architecture room multi-device** : chaque participant rejoint une room via code depuis son propre navigateur. Prévoir en plus des vues individuelles un rôle/vue "Écran principal" pour un affichage collectif unique (vidéoprojecteur/TV partagée).
2. **Rôle Animateur central et obligatoire** : crée la room, ne fournit aucune question (posées à l'oral depuis son propre support externe), est seul habilité à valider Bonne réponse / Mauvaise réponse / Passer / Continuer / Coffrer, quel que soit le joueur en train de jouer. Les joueurs choisissent eux-mêmes le thème qu'ils veulent tenter à leur tour depuis leur propre écran, mais ne valident jamais eux-mêmes leurs réponses.
3. **Authentification légère** : pseudo libre sans mot de passe pour rejoindre une room. Pas de compte email/mot de passe. Un identifiant local (ex. UUID stocké côté navigateur) permet de réconcilier le même joueur entre sessions pour les statistiques cumulées (mécanisme exact posé en Décision log ci-dessous).
4. **Persistance Postgres (Railway)** : historique des parties jouées, profils joueurs avec stats cumulées (parties jouées, victoires, meilleur thème, etc.), et reprise d'une partie en cours après rechargement/déconnexion (granularité exacte posée en Décision log).
5. **Stack imposée** : Backend FastAPI (Python) ; Frontend React + Vite + Tailwind CSS ; communication temps réel exclusivement via WebSocket natif FastAPI (pas de polling) pour synchroniser tous les écrans d'une room (tours, scores, progression, état des cases).
6. **Déploiement Railway en un seul service** : FastAPI sert l'API/WebSocket ET les fichiers statiques du build React. Pas de service frontend séparé. `SECRET_KEY` et `DATABASE_URL` en variables d'environnement, `PORT` dynamique, bind `0.0.0.0`, pas de `debug=True`.
7. **Direction artistique imposée** : "Jazz Club feutré / Industriel / Lumière chaude tamisée / esthétique La La Land". Palette chaude (ambres, bordeaux profonds, laiton/or vieilli, noir charbon, touches de bleu nuit), contraste serif élégant display + sans-serif lisible, textures subtiles (grain, vignettage, effet spotlight notamment sur le tunnel de jeu), animations théâtrales (rideaux, spots qui s'allument), pas de néon flashy. Le tunnel de jeu est la pièce maîtresse visuelle de l'app.
8. **Améliorations fonctionnelles obligatoires** : écran de fin de partie avec podium animé + stats de partie (meilleur thème, plus gros coup risqué, plus gros coffrage) ; historique des parties et profils persistants Postgres ; effets sonores sur actions clés + ambiance musicale discrète cohérente avec la DA jazz club ; banque de thèmes prédéfinis en option de la saisie manuelle ; écran de régie Animateur distinct de l'écran principal collectif.
9. **Dette à ne pas reproduire** : clé secrète en dur, `debug=True`, host IP codée en dur, état uniquement en cookie de session, mélange SSR/JS confus, absence de validation/échappement d'input, absence de garde-fous d'état, absence totale de tests/CI/déploiement.

## Scope

### In scope
- Monorepo backend (FastAPI) + frontend (React/Vite/Tailwind) dans un seul repo Git.
- Modèle de données Postgres + migrations Alembic pour rooms, joueurs, parties, thèmes de partie, historique d'événements, profils/stats joueurs.
- Protocole WebSocket documenté couvrant tous les événements de jeu et les 3 rôles (Animateur, Joueur, Écran principal).
- Moteur de règles de jeu backend fidèle à la spécification figée ci-dessus, avec tests unitaires.
- Endpoints REST pour création/jointure de room, banque de thèmes prédéfinis, historique et stats.
- Handlers WebSocket avec enforcement des permissions par rôle et persistance aux transitions clés.
- Design system React conforme à la DA imposée + tous les écrans listés en Bloc 7.
- Intégration audio (effets + ambiance) avec contrôle de volume/mute.
- Packaging déploiement Railway en service unique (build frontend servi par FastAPI).
- Suite de tests backend (règles de jeu) + pipeline CI minimal.
- Documentation de setup local et de déploiement.

### Out of scope
- Génération ou fourniture d'une banque de questions avec réponses (l'app ne fournit jamais le contenu des questions elles-mêmes, uniquement les thèmes).
- Authentification forte (email/mot de passe, OAuth, 2FA).
- Application mobile native.
- Internationalisation (l'app reste en français).
- Mode spectateur public sans pseudo / sans passer par une room.
- Mode hors-ligne / PWA installable.
- Vidéo/voix intégrée entre participants.
- Système de "réclamation d'historique" pour fusionner les stats de deux pseudos différents utilisés par la même personne.

## Esquisse du modèle de données (guidage pour Bloc 2, le database-architect finalise le DDL exact)

- `player_profiles` : identité persistante légère — `local_player_id` (UUID, clé primaire logique côté client), `pseudo` (dernier pseudo utilisé, mutable), `games_played`, `games_won`, `best_theme`, timestamps.
- `rooms` : `code` (court, lisible, unique, actif), `status` (lobby/in_progress/finished), `animateur_local_player_id`, timestamps, `current_game_id` nullable.
- `games` : une partie jouée dans une room — `room_id`, `started_at`, `ended_at`, `state_json` (snapshot courant complet : joueurs, tours, barres de thème — pour la reprise après déconnexion/reload), `winner_player_id` nullable.
- `game_players` : table de jonction `game_id` / `local_player_id` avec `points` courants et `turn_order`.
- `game_themes` : `game_id`, `label`, `progress_value`, `validated_squares`, `discovered`, `completed`, `nullified` (array ou JSON).
- `game_events` : journal append-only (`game_id`, `type`, `payload_json`, `created_at`, `actor_local_player_id`) pour l'historique/audit et le calcul des stats de fin de partie (plus gros coup risqué, plus gros coffrage) — pas destiné au replay/reconstruction d'état (voir Décision log).
- Index attendus : `rooms.code` unique, `player_profiles.local_player_id` unique, `game_events.game_id`.

## Building blocks

- [ ] **Bloc 1 — Setup du repo et scaffolding monorepo**
  - Déliverable : structure `backend/` (FastAPI, pyproject/requirements, venv ignoré) et `frontend/` (Vite + React + Tailwind) dans un repo Git initialisé, avec `.gitignore` couvrant `__pycache__`, `.venv`, `node_modules`, `dist`, `.env`.
  - Done when : `git log` montre un commit initial ; `backend/` lance un `uvicorn` "hello world" ; `frontend/` lance un `npm run dev` Vite par défaut avec Tailwind configuré ; README racine décrit l'arborescence du repo.
  - Depends on : rien.

- [ ] **Bloc 2 — Modèle de données Postgres + migrations Alembic**
  - Déliverable : schéma complet (voir esquisse ci-dessus, finalisé/adapté par le database-architect) avec migrations Alembic versionnées.
  - Done when : `alembic upgrade head` crée toutes les tables sur une instance Postgres locale sans erreur ; chaque table a au moins une migration ; le schéma final est documenté (commentaires ou fichier `docs/schema.md`) ; les contraintes d'unicité (`rooms.code`, `player_profiles.local_player_id`) sont en place.
  - Depends on : Bloc 1.
  - Bloquant à résoudre avant finalisation : voir Open questions (granularité de persistance, mécanisme d'identité).

- [ ] **Bloc 3 — Spécification du protocole WebSocket**
  - Déliverable : document `docs/websocket-protocol.md` listant chaque type de message (ex. `room:join`, `room:state_sync`, `role:assign`, `theme:select`, `answer:good`, `answer:bad`, `answer:pass`, `answer:continue`, `answer:vault`, `turn:changed`, `game:ended`, `error`), sa direction (client→serveur / serveur→client / broadcast room), le rôle autorisé à l'émettre, la forme JSON exacte du payload, et la stratégie de reconnexion (comment un client qui se reconnecte récupère l'état courant complet de la room).
  - Done when : chaque action de jeu de la spécification figée (Bonne réponse, Mauvaise réponse, Passer, Continuer, Coffrer, sélection de thème, reset, fin de partie) a un message WS correspondant documenté avec enforcement de rôle explicite ; le flux de reconnexion est décrit étape par étape.
  - Depends on : Bloc 2 (le protocole doit refléter les formes de données du schéma).

- [ ] **Bloc 4 — Backend FastAPI : moteur de règles + endpoints REST + tests unitaires**
  - Déliverable : module(s) Python pur(s) implémentant exactement la spécification figée (barème de points, coloration des cases, `coffrer`, `poursuivre`, gestion de `nullified`/`discovered`, garde-fou thème complété, reset vs quitter la partie) + endpoints REST (création de room, jointure, banque de thèmes prédéfinis, historique, stats joueur) avec validation d'input (longueur pseudo/thème, nombre min de joueurs ≥2, nombre min de thèmes ≥1, caractères autorisés).
  - Done when : suite `pytest` verte couvrant au minimum : barème de points par palier (1/2/3/5), coffrage automatique en case 10, non-perte de progression sur mauvaise réponse, non-gain définitif sur case passée même après coffrage ultérieur, vol de progression par un autre joueur, rejet de sélection d'un thème `completed`, comportement distinct reset-partie vs quitter-partie ; endpoints REST testés manuellement ou via `pytest` + client de test FastAPI.
  - Depends on : Bloc 2, Bloc 3.

- [ ] **Bloc 5 — WebSocket handlers + gestion d'état de room + persistance**
  - Déliverable : gestionnaire de rooms en mémoire (process-local) orchestrant les connexions WebSocket selon le protocole du Bloc 3, enforcement des permissions par rôle (seul l'Animateur peut valider une réponse/coffrer/continuer/reset/quitter ; seul le joueur courant peut sélectionner un thème à son tour), persistance Postgres aux transitions clés (fin de tour, fin de partie, événements notables pour l'historique), et reprise d'état après reconnexion.
  - Done when : un test manuel ou automatisé avec au moins 3 clients WebSocket simultanés (1 Animateur, 2 Joueurs) sur la même room montre une synchronisation correcte des scores/tours/état des cases en temps réel ; une tentative d'action réservée à l'Animateur envoyée par un rôle Joueur est rejetée ; un client qui se déconnecte puis se reconnecte reçoit l'état complet et à jour de la room ; une partie terminée crée un enregistrement persistant consultable via les endpoints d'historique.
  - Depends on : Bloc 4.

- [ ] **Bloc 6 — Design system frontend (DA Jazz Club)**
  - Déliverable : configuration Tailwind personnalisée (palette ambre/bordeaux/laiton/noir charbon/bleu nuit, typographie serif display + sans-serif lisible), composants de base réutilisables (boutons, cartes, modales, échelle typographique), traitement visuel de texture/grain/vignettage/spotlight.
  - Done when : une route ou page de démonstration interne rend la palette, l'échelle typographique et les composants de base de façon cohérente avec la DA décrite ; la config Tailwind est commentée/documentée (quelles couleurs/polices utiliser où).
  - Depends on : Bloc 1.

- [ ] **Bloc 7 — Écrans frontend + client WebSocket**
  - Déliverable : tous les écrans — Accueil (créer/rejoindre une room), Lobby, Saisie des thèmes (manuelle façon "points noirs" + sélection depuis une banque de thèmes prédéfinis), vue Animateur/régie (boutons de validation, vue d'ensemble de la room), vue Joueur (sélection de thème à son tour, attente sinon), vue Écran principal (affichage collectif en lecture seule, scores, tunnel en cours), tunnel de jeu animé (pièce maîtresse visuelle), écran de fin de partie avec podium animé et stats de partie — tous branchés au client WebSocket du protocole Bloc 3, avec routage conditionnel par rôle.
  - Done when : un playtest manuel complet sur 4 onglets/navigateurs (1 Animateur + 2 Joueurs + 1 Écran principal) permet de jouer une partie entière du début à la fin en respectant exactement la spécification figée (y compris vol de progression, coffrage auto en case 10, garde-fou thème complété) ; chaque écran listé existe et est accessible selon le rôle.
  - Depends on : Bloc 5, Bloc 6.

- [ ] **Bloc 8 — Intégration audio**
  - Déliverable : effets sonores sur bonne réponse, coffrage, tic-tac du chronomètre (paliers de couleur 60s→30s jaune→20s orange→10s rouge clignotant repris de l'original), ambiance musicale de fond discrète cohérente avec la DA jazz club, contrôle de volume/mute persistant côté client (ex. `localStorage`).
  - Done when : chaque effet sonore listé se déclenche sur l'événement correspondant pendant un playtest ; le mute persiste après rechargement de page ; les assets audio utilisés sont committés ou leur source libre de droits est documentée dans le README.
  - Depends on : Bloc 7.

- [ ] **Bloc 9 — Packaging déploiement Railway (service unique)**
  - Déliverable : configuration de build qui produit le bundle React statique et le fait servir par FastAPI (fichiers statiques + fallback SPA), fichier `Procfile` ou configuration Nixpacks adaptée, lecture de `SECRET_KEY`/`DATABASE_URL`/`PORT` depuis l'environnement, bind `0.0.0.0`, `debug` désactivé, endpoint de health check.
  - Done when : un déploiement Railway (ou une simulation locale équivalente type `docker run` avec les mêmes variables d'env) sert à la fois l'API/WS et le frontend buildé depuis un seul process ; aucune valeur sensible ou host/port n'est codée en dur dans le code ; le plugin Postgres Railway peut être branché via `DATABASE_URL` sans modification de code.
  - Depends on : Bloc 5, Bloc 7.

- [ ] **Bloc 10 — Tests complémentaires et CI**
  - Déliverable : tests d'intégration WebSocket/API en plus des tests unitaires du Bloc 4, pipeline CI (ex. GitHub Actions) exécutant lint + tests backend + build frontend à chaque push.
  - Done when : la CI échoue si un test de règle de jeu casse ou si le build frontend échoue ; le pipeline est versionné dans le repo.
  - Depends on : Bloc 4, Bloc 5, Bloc 7.

- [ ] **Bloc 11 — Documentation**
  - Déliverable : README décrivant le setup local (backend + frontend), les variables d'environnement requises (tableau), les étapes de déploiement Railway, et un lien vers `docs/websocket-protocol.md` et `docs/schema.md`.
  - Done when : un nouvel arrivant peut suivre le README pour faire tourner l'app en local et la déployer sur Railway sans information manquante.
  - Depends on : Blocs 1-9.

## Open questions

1. **Granularité de persistance pour la reprise de partie** : l'utilisateur demande de pouvoir "reprendre une partie en cours si possible" sans trancher la mécanique exacte. Proposition par défaut (à valider par le database-architect au Bloc 2, ne bloque pas le démarrage du Bloc 1) : un snapshot complet de l'état courant dans `games.state_json`, mis à jour de façon transactionnelle à chaque action qui modifie l'état, plus un `game_events` append-only séparé pour l'historique/les stats de fin de partie — pas d'event-sourcing complet avec replay. Si cette approche ne convient pas, le confirmer avant de clore le Bloc 2.
2. **Mécanisme exact de réconciliation d'identité joueur** : l'utilisateur veut un pseudo sans mot de passe avec stats cumulées dans le temps. Proposition par défaut (voir Décision log ci-dessous) : UUID `local_player_id` stocké côté navigateur comme clé réelle des stats, le pseudo restant un simple libellé d'affichage mutable. Limite connue acceptée : si le stockage local est vidé, l'historique de ce joueur n'est plus relié automatiquement (pas de système de réclamation, explicitement hors scope). Si l'utilisateur veut un comportement différent (ex. pseudo globalement unique et verrouillé), le signaler avant de clore le Bloc 2.

Aucune de ces deux questions ne bloque le démarrage du Bloc 1 ; elles doivent être tranchées (ou la proposition par défaut confirmée) avant de clore le Bloc 2.

**Confirmation Orion (2026-10-10)** : les deux propositions par défaut ci-dessus sont validées telles quelles, pas de remontée nécessaire à l'utilisateur — cohérentes avec les décisions déjà actées (pseudo simple sans mot de passe, persistance pragmatique plutôt qu'event-sourcing complet). Le Bloc 2 peut être clos sur cette base sans négociation supplémentaire.

## Decision log

- **Granularité de persistance (proposition de planning)** : snapshot transactionnel (`games.state_json`) + log d'événements append-only séparé pour l'historique, plutôt qu'event-sourcing complet. Raison : couvre le besoin exprimé ("reprendre si possible") avec une complexité d'implémentation bien moindre qu'un vrai replay d'événements, tout en gardant un historique exploitable pour les stats de fin de partie. Modifiable si le database-architect ou l'utilisateur identifie un besoin de replay fin.
- **Identité joueur via `local_player_id`** : UUID client-side comme clé de stats réelle, pseudo comme libellé mutable non unique globalement. Raison : respecte la contrainte "pseudo simple sans mot de passe" sans construire un vrai système de comptes, tout en permettant des stats cumulées cohérentes pour un même navigateur/joueur dans le temps.
- **Garde-fou thème complété ajouté (absent de l'original)** : un thème `completed=true` doit être non-sélectionnable. Raison : l'original permettait de resélectionner un thème terminé et aboutissait à un état mort (aucune case ne peut plus évoluer) — classé dans la dette "absence de garde-fous" explicitement à corriger.
- **"Quitter la partie" vide réellement l'état de la room (diverge du code original)** : le code original de `go_main_menu` ne faisait que changer un champ d'état sans rien vider, ce qui contredisait le comportement voulu décrit par l'utilisateur ("retour menu efface tout"). Raison du choix : la description fonctionnelle de l'utilisateur fait foi sur le comportement observé dans le code quand les deux divergent, car le code présente ce point comme un bug non intentionnel plutôt qu'une règle de jeu à préserver.
