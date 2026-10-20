---
status: draft
created: 2026-10-10
updated: 2026-10-20
---

## Functional objective

Permettre à un très petit groupe (moins de cinq rooms simultanées) d'utiliser régulièrement Le Grand Tunneg comme un service durable sur Railway. Préserver la partie multijoueur déjà fonctionnelle, fiabiliser sessions, permissions et tests, puis sauvegarder et reprendre les parties après redéploiement avant de compléter historique, profils et fonctions secondaires.

### Objectif historique de reconstruction

Reconstruire intégralement "Le Grand Tunneg" — jeu de plateau/quiz façon Fort Boyard — en quittant l'architecture Flask/session-cookie/Alpine.js monoposte de l'original pour une application web (FastAPI + WebSocket + React/Vite/Tailwind + Postgres) proposant deux modes de room (multi-device temps réel, et solo hotseat mono-écran), avec un rôle Présentateur central qui juge les réponses orales et orchestre le rythme du show (délai de révélation des choix joueur façon jeu télé), une direction artistique "Jazz Club feutré / La La Land" soignée, et un déploiement Railway propre en un seul service.

## Réorientation acceptée — service durable à faible fréquentation (2026-10-20)

### Objectif fonctionnel actuel

Préserver le parcours multijoueur qui fonctionne déjà et permettre son utilisation régulière par un petit groupe, sans perte de partie lors d'un redéploiement et sans confusion de permissions. La priorité acceptée par l'utilisateur est : stabiliser le multijoueur, puis ajouter sauvegarde et reprise, puis historique et profils ; le solo et les enrichissements viennent ensuite. La reconstruction initiale reste le contexte historique, pas une invitation à réécrire le jeu.

### Current context

**Observed facts**
- L'utilisateur confirme le 2026-10-20 qu'une version Railway est actuellement en déploiement et qu'une partie complète fonctionne. Cette confirmation est une preuve d'usage rapportée, pas un test exécuté pendant l'état des lieux.
- La fréquentation attendue est inférieure à cinq rooms simultanées ; la cible est un service durable accessible à très peu de personnes à la fois.
- La lecture du dépôt confirme le moteur Python indépendant du transport, les rooms en mémoire, les interfaces multi, les avatars, le transfert de Présentateur, les animations, le podium et le plus gros coffrage.
- L'audio existe dans `frontend/src/audio/` : sons synthétisés, ambiance jazz et préférences locales. Son existence ne vaut pas validation complète sur navigateurs réels.
- Postgres n'est pas branché ; aucune migration n'est présente dans le backend inspecté. Historique durable, profils cumulés, banque de thèmes et parcours solo restent à construire.
- Des tests d'intégration et le protocole décrivent encore l'ancien modèle sans Présentateur dans `players`, alors que le code le représente désormais avec `isPresenter: true` et exclut son tour et son classement de joueur.
- Aucun test ni build n'a été exécuté pendant cet état des lieux ; aucune garantie de suite actuellement verte n'est donnée.

**Inferences**
- Le besoin prioritaire est la continuité et la fiabilité, pas la capacité de traitement.
- Les identifiants publics des participants sont diffusés dans l'état, mais servent aussi à ouvrir les connexions : il faut séparer identité publique et preuve de session avant de considérer les permissions fiables.
- Le rôle conservé au début d'une connexion peut devenir périmé après un transfert de Présentateur ; les autorisations doivent être évaluées sur l'état serveur courant.
- Le reset à l'index zéro peut désigner le Présentateur depuis son intégration à `players` ; la relance doit choisir un joueur éligible.
- Le client ne possède pas de boucle de reconnexion automatique et efface l'identité sur fermeture : la reprise durable exige aussi une évolution du navigateur, pas seulement une base.
- Les règles Python et TypeScript existent séparément et divergent déjà. Le partage strict du moteur en solo reste un problème à résoudre, pas une propriété acquise.

**Unknowns**
- Configuration réelle du service Railway, offre Postgres, sauvegardes disponibles, procédure de restauration et durée d'interruption acceptable.
- Durée souhaitée de conservation des parties et profils ; objectifs chiffrés de perte de données et de délai de restauration.
- Résultats actuels des tests et correspondance exacte entre la révision déployée et le dépôt inspecté.

### Target

```text
[Navigateurs]
      |
[FastAPI unique]
      |
[Moteur de jeu]
      |
[Postgres]
```

Les navigateurs affichent et transmettent les commandes. FastAPI authentifie les sessions, vérifie les permissions courantes et orchestre les actions. Le moteur reste indépendant du transport et de la base. Postgres conserve les états et événements ; les connexions et verrous restent temporaires en mémoire.

### Decisions and trade-offs

- **Option retenue explicitement par l'utilisateur** : stabiliser le multijoueur puis le rendre persistant, sans réécriture. Préserver le monorepo, FastAPI, React et le service applicatif unique Railway, avec Postgres comme service de données associé.
- **Option viable mais écartée comme cible durable** : conserver uniquement les rooms en mémoire pour des soirées encadrées ; simple, mais perte des parties à chaque redémarrage.
- **Option différée** : développer d'abord le solo et les enrichissements ; apporte des usages mais étend la surface de régression avant consolidation.
- Un seul processus applicatif propriétaire des rooms actives dans cette phase. Ne pas activer plusieurs workers ou réplicas : Postgres seul ne synchronise pas leurs états en mémoire. Redis, microservices et architecture distribuée ne sont pas justifiés par moins de cinq rooms.
- Pseudos sans mot de passe conservés. Un identifiant de profil/participant public n'est jamais une preuve d'identité : ajouter un secret de session vérifié côté serveur, non diffusé aux autres participants. Le mécanisme exact, sa durée et son renouvellement sont à documenter avant réalisation ; pas d'obligation de JWT ni de comptes forts.
- Sauvegarde par snapshot complet versionné et journal d'événements utiles dans une même transaction pour chaque commande durable acceptée. Ne pas introduire de reconstruction par rejeu de tous les événements.
- L'état accepté est calculé par le moteur, enregistré, puis publié en mémoire et diffusé. En cas d'échec de transaction, aucun succès ni nouvel état non durable n'est annoncé. La fin de partie et les statistiques ne doivent pas être créditées deux fois après reprise ou nouvelle tentative.
- Reprise après redéploiement, reconnexion navigateur et restauration de sauvegarde sont des critères distincts, tous nécessaires à la durabilité. Ne pas promettre d'absence totale d'interruption lors d'un déploiement à processus unique.

### Incremental migration path

```text
[Jeu actuel]
      |
[Tests et sessions fiables]
      |
[Sauvegarde transactionnelle]
      |
[Reprise et restauration]
      |
[Historique et profils]
      |
[Solo et enrichissements]
```

Chaque palier conserve le jeu multi et ajoute une garantie vérifiable. L'ordre d'exécution ci-dessous remplace l'ordre numérique historique des blocs :

1. **Référence et garde-fous** — Bloc 12 puis première tranche du Bloc 10 : aligner protocole/tests sur le modèle actuel, automatiser tests, lint et build ; consigner la révision de référence et le scénario complet validé.
2. **Sessions et fonctionnement fiable** — Bloc 13 : identité, permissions après transfert, relance, déconnexions, messages malformés et protections raisonnables des ressources. Vérifier une partie à quatre clients avec transfert et Rejouer, sans modifier les règles métier.
3. **Stockage** — Bloc 2 puis complément du Bloc 5 : introduire une interface de stockage, des migrations additives et la sauvegarde transactionnelle ; conserver le contrat réseau existant autant que possible.
4. **Reprise réelle** — Bloc 14 : restaurer les rooms, reconnecter les clients, tester un redéploiement et une restauration de sauvegarde sur un environnement de test Railway avant activation durable.
5. **Fonctions durables** — Bloc 15 et compléments des Blocs 4/7 : historique et profils, puis statistiques finales et banque de thèmes.
6. **Fonctions différées** — Bloc 7bis après décision technique sur le moteur solo ; finaliser audio, documentation et tests de parité sans retarder la première CI.

**Compatibilité et retour arrière** : livrer les changements de session avec une stratégie documentée pour les anciennes sessions (transition bornée ou reconnexion explicite, jamais maintien indéfini de l'UUID public comme secret). Planifier une fenêtre sans partie active tant que les anciennes rooms en mémoire ne peuvent pas être migrées. Pour Postgres, tester les migrations sur une copie et garder un ancien binaire compatible avec le nouveau schéma ; ne pas revenir vers une version ignorant les sauvegardes si cela ferait perdre des actions déjà confirmées. Une fois la durabilité activée, une panne de base doit produire un refus clair des mutations, pas un repli silencieux en mémoire. Les points de retour arrière sont à valider avant chaque activation.

### État des blocs au 2026-10-20

Une case cochée signifie que tous les critères du bloc sont établis ; « code présent », « partiel » et « validé » doivent rester distincts. Le nombre de cases ne représente pas un pourcentage d'avancement.

| Bloc | État établi / reste à faire |
|---|---|
| 1 | Socle construit ; conservé. |
| 2 | À faire : modèle, migrations et intégration Postgres. |
| 3 | Protocole présent mais à réaligner sur participants, avatars, transfert, sessions et reprise. |
| 4 | Moteur et API multi présents ; tests à réaligner, API historique/stats/banque et solo non réalisés. |
| 5 | Temps réel mémoire présent ; permissions/session/reconnexion à fiabiliser et persistance absente. |
| 6 | Design system présent ; conservé. |
| 7 | Parcours multi fonctionnel confirmé par l'utilisateur ; solo, banque et statistiques finales complètes manquent au périmètre initial. |
| 7bis | Non réalisé ; différé, architecture du moteur à clarifier avant réalisation. |
| 8 | Audio implémenté ; validation complète, politique de diffusion sonore multi-écrans et documentation restantes. |
| 9 | Packaging présent et version Railway signalée en déploiement ; critères de configuration durable à terminer avec Postgres/sessions. |
| 10 | Tests backend présents, certains périmés ; CI et tests frontend à faire. Première tranche prioritaire, sans dépendre du solo. |
| 11 | README/protocole présents ; mise à jour opérationnelle et schéma à compléter. |
| 12–15 | Nouveaux compléments de consolidation décrits ci-dessous. |
| 16–18 | Nouvelle dimension demandée : contrat de bibliothèque, saisie/conservation des contenus, réutilisation et lecture privée en régie. À construire après consolidation, décisions de partage/sélection à préciser. |

**Règle de priorité documentaire** : cette réorientation et les annotations datées du 2026-10-20 priment sur les descriptions historiques contradictoires ci-dessous. Les règles métier restent inchangées ; le Présentateur peut être représenté dans la liste technique des participants sans devenir un joueur éligible aux tours/points. Un panneau caché dans l'interface ne garantit pas la confidentialité des données déjà envoyées au navigateur. Le rapport `docs/review.md` est un inventaire historique à requalifier, pas une liste de correctifs à appliquer aveuglément (notamment ne pas marquer un thème terminé après un coffrage avant la case 10).

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
4. **Jaune** sinon si `(k - 1) == progress_value` ET `discovered == true` (case actuellement en train d'être contestée, question lue par le présentateur)
5. **Vide** sinon

### Transition `discovered`
- Passe à `true` quand un thème est sélectionné (première fois ou reprise) et quand l'action "Continuer" est choisie après une bonne réponse.
- Passe à `false` uniquement au tout début du traitement d'une "Bonne réponse", avant l'avancement de `progress_value`.
- **Ne se réinitialise PAS** explicitement après "Mauvaise réponse", "Passer" ou un coffrage — ce comportement de l'original est intentionnel et doit être reproduit à l'identique : le flag `discovered` sert de marqueur "ce thème a une case activement contestée" qui survit au changement de joueur, ce qui permet à l'UI de renvoyer directement sur l'écran du tunnel (sans ré-afficher un écran intermédiaire) quand un autre joueur reprend ce thème.

### Actions de jeu — phase "question posée" (jugement de la réponse orale, validé exclusivement par le Présentateur — lui seul connaît la réponse)
- **Bonne réponse** : `discovered = false`, puis `poursuivre()` :
  - si `progress_value == 9` → `progress_value = 10`, déclenche un **coffrage automatique** (`coffrer()`, voir plus bas), puis `completed = true`.
  - sinon si `progress_value < 10` → `progress_value += 1`.
  - Résultat visuel : la case qui vient d'être validée passe en vert (ou le thème se termine et toutes ses cases encore vertes passent en gris avec crédit de points, cf coffrage auto).
- **Mauvaise réponse** : le tour passe au joueur suivant (`current_player_index + 1 mod n`), retour à l'écran de sélection de thème. **Aucune perte de progression** : `progress_value`, `validated_squares`, `nullified` restent inchangés — la case reste verte, exposée à un "vol" si un autre joueur reprend ce thème et le coffre plus tard.
- **Passer** : la case `progress_value + 1` est ajoutée à `nullified` (noire pour toujours), puis `poursuivre()` est appelée (la progression avance quand même d'une case, sans gain possible sur cette case précise). Le tour ne passe PAS automatiquement au joueur suivant dans l'original (le joueur courant reste actif) — reproduire ce comportement.

### Actions de jeu — phase "après bonne réponse" (choix de risque/récompense, appartient exclusivement au joueur concerné — PAS au Présentateur)
Affichée seulement juste après une bonne réponse non terminale. Le Présentateur ne valide/ne tranche jamais ce choix ; il ne contrôle que le **timing d'ouverture** de ce choix côté joueur (voir couche "show — délai d'ouverture des choix joueur" ci-dessous). Une fois le choix révélé, c'est le joueur, et lui seul, qui sélectionne l'option :
- **Continuer** : `discovered = true` (nouvelle question posée sur le même thème, la progression actuelle reste exposée au risque).
- **Coffrer** (`coffrer()`) : pour chaque case `i` de 1 à `progress_value` non encore comptée dans `validated_squares` (c'est-à-dire `i > validated_squares` courant, traité dans l'ordre croissant) : incrémenter `validated_squares`, et si `i ∉ nullified`, créditer `get_question_points(i)` au joueur courant. Puis faire passer le tour au joueur suivant et revenir à l'écran de sélection de thème. **Ce bloc de code est strictement identique que l'appel vienne de l'action manuelle "Coffrer" ou du coffrage automatique en case 10.** Le coffrage automatique en case 10 ne passe par aucun choix joueur ni couche de show — il est déclenché mécaniquement par le moteur de règles, sans intervention du Présentateur ni du joueur.

### Couche "show" — délai d'ouverture des choix joueur (NOUVEAU)
S'applique aux deux choix qui reviennent à un joueur : la **sélection de thème en début de tour** et le choix **Continuer vs Coffrer** après une bonne réponse non terminale. Le coffrage automatique en case 10 n'est PAS concerné (aucun choix humain à révéler).

- Dès qu'un choix joueur devient éligible (c'est au tour d'un joueur de choisir son thème, ou une bonne réponse non terminale vient d'être validée), l'état de jeu entre dans un nouveau sous-état **`choice_pending`** (choix en attente de révélation) plutôt que de passer directement à un état "choix actif".
  - **Continuer/Coffrer** : le joueur concerné ne voit aucune option, aucun bouton grisé, aucune case cliquable désactivée — un écran d'attente/suspense neutre uniquement (rien à anticiper, ce sont deux actions génériques).
  - **Sélection de thème** (révisé le 2026-10-11, retour utilisateur post-playtest) : la grille des thèmes reste VISIBLE pour tous (contenu informatif, le joueur peut réfléchir à son choix pendant que le Présentateur parle) mais NON CLIQUABLE pour personne, y compris le joueur concerné — seul le suspense sur le DROIT d'agir est maintenu, pas sur le contenu. Le serveur rejette de toute façon tout `theme:select` reçu tant que l'état est encore `choice_pending` (voir Bloc 4/5), donc cacher la grille au joueur n'apportait aucune garantie supplémentaire et nuisait à l'ergonomie.
- Le Présentateur, et lui seul, dispose d'un contrôle explicite ("Lancer le choix") pour faire transitionner l'état de `choice_pending` à **`choice_open`** (choix révélé/actif). Dès cette transition, les options deviennent visibles et cliquables pour le joueur concerné, de façon synchronisée en temps réel en mode room multi.
- Une fois le joueur passé à `choice_open` et son choix effectué (thème sélectionné, ou Continuer/Coffrer tranché), l'état de jeu suit le comportement déjà décrit plus haut (passage à `discovered=true`, ou exécution de `coffrer()`, etc.) — la couche show n'affecte que le moment de la révélation, jamais la logique de jeu elle-même.

### Couche "show" — délai de lancement du chrono (NOUVEAU, 2026-10-11)
S'applique à chaque fois qu'une question démarre : juste après la sélection d'un thème (`SELECT_THEME`) ET juste après le choix "Continuer" (nouvelle question sur le même thème). Avant cette passe, `tunnelSubPhase` passait directement à `'question'` avec le chrono démarré immédiatement ; désormais un sous-état intermédiaire **`question-pending`** est inséré :

- `question-pending` : le Présentateur vient d'ouvrir le thème (ou le joueur vient de choisir Continuer) mais n'a pas encore posé sa question à l'oral. Le chrono n'est PAS affiché/démarré. Côté joueur concerné : écran "Écoutez la question…" sans minuteur ni boutons de jugement. Côté autres rôles : même affichage de contexte (thème, tableau de scores) mais pas de chrono non plus.
- Le Présentateur, et lui seul, dispose d'un contrôle explicite **"Lancer le chrono"** qui fait transitionner `question-pending` → `question` (action `timer:start`). C'est seulement à cet instant que le minuteur démarre réellement et que les boutons de jugement (Bonne réponse/Mauvaise réponse/Passer) apparaissent côté Présentateur.
- Résultat : le joueur concerné traverse donc deux temps côté tunnel : (1) écoute la question (pas de chrono), (2) attend le verdict du Présentateur une fois le chrono lancé et la réponse donnée (état `question` existant, inchangé dans sa logique de jugement).
- Ce nouveau sous-état ne s'applique PAS au coffrage automatique en case 10 (aucune question n'est reposée, le thème se termine mécaniquement) ni au passage `question-pending`→`question` lui-même qui ne déclenche aucune mutation du barème/progression — c'est une pure temporisation d'affichage/rythme, comme la couche `choice_pending`/`choice_open` existante.
- En mode room solo (hotseat, un seul écran), cette couche reste active à l'identique : le contrôle "Lancer le choix" doit rester disponible pour le joueur humain qui tient le rôle de Présentateur à ce moment-là, même sans second device à synchroniser.

### Thèmes complétés — garde-fou à AJOUTER (absent de l'original, classé comme dette à corriger)
Un thème avec `completed == true` (coffré jusqu'à la case 10) doit être non-sélectionnable : grisé côté UI et rejeté côté serveur si un message de sélection arrive malgré tout pour ce thème.

### Reset de partie vs retour au menu (comportement voulu, divergent du code original qui ne vide jamais rien sur "retour menu")
- **Réinitialiser la partie** (action réservée au Présentateur) : remet tous les scores joueurs à 0 et toutes les barres de thème à l'état initial (`progress_value=0, validated_squares=0, discovered=false, completed=false, nullified=[]`), **conserve** la liste des joueurs et la liste des thèmes, reste dans la même room.
- **Quitter la partie / Retour à l'accueil** (action réservée au Présentateur) : termine la room — vide joueurs, thèmes, état de jeu en mémoire pour cette room, déconnecte proprement tous les clients vers l'écran d'accueil. Diverge volontairement du code original (qui ne faisait rien à part changer un simple champ d'état) : c'était un bug de l'original, pas un comportement à reproduire.

## Décisions produit déjà actées (ne pas rouvrir, ne pas redemander à l'utilisateur)

1. **Deux types de room à la création** : l'écran de création propose deux choix — **"Créer une room multi"** (mis en avant visuellement, choix principal) et **"Créer une room solo"** (option secondaire, moins mise en avant).
   - **Room multi** : chaque participant rejoint une room via code depuis son propre navigateur. Prévoir en plus des vues individuelles un rôle/vue "Écran principal" pour un affichage collectif unique (vidéoprojecteur/TV partagée).
   - **Room solo (NOUVEAU)** : hotseat local pur sur un seul navigateur — pas de code de room à partager, pas de WebSocket ni de synchronisation multi-device nécessaire pour ce mode ; un même écran bascule manuellement entre la vue Présentateur et la vue de chaque Joueur à tour de rôle, reproduisant le fonctionnement mono-écran de l'ancien jeu Flask. La partie peut être non persistée en base, ou persistée de façon simplifiée, au choix de l'implémenteur du Bloc concerné (ce n'est pas le cœur de la logique multi-device). Ce mode réutilise impérativement le même moteur de règles de jeu (Bloc 4) que le mode multi — seule la couche transport/affichage diffère, jamais la logique de jeu.
2. **Rôle Présentateur central et obligatoire** (renommé depuis "Animateur") : crée la room, choisit/saisit la liste des thèmes de la partie en phase de setup/lobby et pose les questions à l'oral. Actuellement son support est externe ; à terme il pourra préparer, conserver et réutiliser ses thèmes, leurs questions et des réponses types indicatives dans l'application (amendement utilisateur du 2026-10-20, Blocs 16–18), est seul habilité à valider **Bonne réponse / Mauvaise réponse / Passer** (jugement de la réponse orale — lui seul connaît la réponse), et déclenche le **timing d'ouverture** des choix joueur (voir couche "show" dans la spécification figée). Il peut désigner un autre participant comme nouveau Présentateur **uniquement dans le lobby, jamais en cours de partie** (un seul Présentateur actif à la fois). Les joueurs choisissent eux-mêmes le thème qu'ils veulent tenter à leur tour, et choisissent eux-mêmes **Continuer vs Coffrer** après une bonne réponse non terminale (NOUVEAU — ce pouvoir de décision appartient au joueur concerné, pas au Présentateur) ; mais ne valident jamais eux-mêmes leurs réponses orales.
3. **Authentification légère** : pseudo libre sans mot de passe pour rejoindre une room. Pas de compte email/mot de passe. Un identifiant local (ex. UUID stocké côté navigateur) permet de réconcilier le même joueur entre sessions pour les statistiques cumulées (mécanisme exact posé en Décision log ci-dessous).
4. **Persistance Postgres (Railway)** : historique des parties jouées, profils joueurs avec stats cumulées (parties jouées, victoires, meilleur thème, etc.), et reprise d'une partie en cours après rechargement/déconnexion (granularité exacte posée en Décision log).
5. **Stack imposée** : Backend FastAPI (Python) ; Frontend React + Vite + Tailwind CSS ; communication temps réel exclusivement via WebSocket natif FastAPI (pas de polling) pour synchroniser tous les écrans d'une room (tours, scores, progression, état des cases).
6. **Déploiement Railway en un seul service** : FastAPI sert l'API/WebSocket ET les fichiers statiques du build React. Pas de service frontend séparé. `SECRET_KEY` et `DATABASE_URL` en variables d'environnement, `PORT` dynamique, bind `0.0.0.0`, pas de `debug=True`.
7. **Direction artistique imposée** : "Jazz Club feutré / Industriel / Lumière chaude tamisée / esthétique La La Land". Palette chaude (ambres, bordeaux profonds, laiton/or vieilli, noir charbon, touches de bleu nuit), contraste serif élégant display + sans-serif lisible, textures subtiles (grain, vignettage, effet spotlight notamment sur le tunnel de jeu), animations théâtrales (rideaux, spots qui s'allument), pas de néon flashy. Le tunnel de jeu est la pièce maîtresse visuelle de l'app.
8. **Améliorations fonctionnelles obligatoires** : écran de fin de partie avec podium animé + stats de partie (meilleur thème, plus gros coup risqué, plus gros coffrage) ; historique des parties et profils persistants Postgres ; effets sonores sur actions clés + ambiance musicale discrète cohérente avec la DA jazz club ; banque de thèmes prédéfinis en option de la saisie manuelle ; écran de régie Présentateur distinct de l'écran principal collectif.
9. **Dette à ne pas reproduire** : clé secrète en dur, `debug=True`, host IP codée en dur, état uniquement en cookie de session, mélange SSR/JS confus, absence de validation/échappement d'input, absence de garde-fous d'état, absence totale de tests/CI/déploiement.

## Scope

### In scope
- Monorepo backend (FastAPI) + frontend (React/Vite/Tailwind) dans un seul repo Git.
- Modèle de données Postgres + migrations Alembic pour rooms, joueurs, parties, thèmes de partie, historique d'événements, profils/stats joueurs.
- Écran de création de room avec les deux choix "Créer une room multi" (mis en avant) et "Créer une room solo" (secondaire), et les deux modes de room correspondants (multi-device temps réel via WebSocket ; solo hotseat mono-écran sans code de room ni synchronisation réseau).
- Protocole WebSocket documenté couvrant tous les événements de jeu et les 3 rôles (Présentateur, Joueur, Écran principal) pour le mode room multi, y compris les nouveaux messages de la couche show (`choice_pending` / `choice_open`).
- Moteur de règles de jeu backend fidèle à la spécification figée ci-dessus (y compris la couche show et le partage de pouvoirs Présentateur/Joueur), avec tests unitaires — moteur partagé/réutilisé à l'identique par le mode room solo.
- Endpoints REST pour création/jointure de room, banque de thèmes prédéfinis, historique et stats.
- Bibliothèque persistante alimentée par les Présentateurs : création et modification de thèmes, saisie des questions associées et de réponses types purement indicatives ; consultation et réutilisation dans des parties futures, indépendamment de la durée de vie d'une room.
- Préparation d'une partie à partir de cette bibliothèque et consultation des questions/réponses dans la régie Présentateur. Le jugement oral et les commandes Bonne réponse/Mauvaise réponse/Passer restent inchangés. Les règles de partage et d'affectation des questions sont à confirmer avant réalisation (Blocs 16–18).
- Handlers WebSocket avec enforcement des permissions par rôle (distinguant actions de jugement de réponse réservées au Présentateur, actions de choix réservées au joueur concerné, et déclenchement de révélation réservé au Présentateur) et persistance aux transitions clés.
- Design system React conforme à la DA imposée + tous les écrans listés en Bloc 7, incluant l'écran d'attente/suspense joueur et le contrôle "Lancer le choix" côté Présentateur.
- Intégration audio (effets + ambiance) avec contrôle de volume/mute.
- Packaging déploiement Railway en service unique (build frontend servi par FastAPI).
- Suite de tests backend (règles de jeu) + pipeline CI minimal.
- Documentation de setup local et de déploiement.

### Out of scope
- Génération automatique de questions/réponses et fourniture éditoriale d'une banque préremplie. En revanche, la saisie, la conservation et la réutilisation des thèmes, questions et réponses indicatives fournis par les Présentateurs font désormais partie du périmètre (amendement utilisateur du 2026-10-20, Blocs 16–18).
- Validation automatique, comparaison textuelle ou attribution automatique d'un verdict à partir d'une réponse type : le jugement reste exclusivement humain.
- Authentification forte (email/mot de passe, OAuth, 2FA).
- Application mobile native.
- Internationalisation (l'app reste en français).
- Mode spectateur public sans pseudo / sans passer par une room.
- Mode hors-ligne / PWA installable.
- Vidéo/voix intégrée entre participants.
- Persistance Postgres complète et obligatoire pour le mode room solo (simplifiée ou absente, au choix de l'implémenteur — voir décision ci-dessus).
- Changement de Présentateur en cours de partie (uniquement possible dans le lobby, voir décisions actées).
- Système de "réclamation d'historique" pour fusionner les stats de deux pseudos différents utilisés par la même personne.

## Dimension questions/réponses — besoin utilisateur accepté (2026-10-20)

### Current context

**Observed facts** : l'utilisateur indique que les questions sont actuellement lues depuis un support annexe. `Theme` dans `backend/app/game/types.py` ne contient ni question ni réponse ; `LobbyScreen.tsx` saisit seulement le libellé du thème, et `serialize_state` diffuse le même contenu de jeu à tous les rôles. Aucun contenu questions/réponses n'a été intégré par cette mise à jour documentaire.

**Inferences** : le contenu réutilisable doit survivre à la room et être distingué de la progression d'un thème dans une partie. Ajouter des réponses dans l'état commun exposerait ces réponses aux joueurs, même avec un panneau caché. La politique de questions peut aussi modifier l'équité : une case reste contestable après une mauvaise réponse, donc l'association question/case ne doit pas être improvisée.

**Unknowns** : bibliothèque personnelle, partagée avec des personnes autorisées ou commune au groupe ; droits de modification ; nombre et ordre des questions ; choix manuel ou affectation aux dix cases ; question conservée ou renouvelée après échec ; possibilité de créer du contenu pendant la partie. Aucune de ces politiques n'est considérée acceptée à ce stade.

### Target

Le Présentateur peut saisir ses thèmes, les questions de chaque thème et des réponses types indicatives, conserver ces contenus après la partie, puis les réutiliser lors de parties futures. Le stock de contenus s'enrichit progressivement par saisie humaine. L'application n'utilise jamais les réponses types pour valider les réponses des joueurs : le Présentateur reste seul juge et lit les questions à l'oral.

### Decisions and trade-offs

- **Besoin explicitement demandé, à réaliser** : bibliothèque persistante de contenus fournis par les Présentateurs, préparation/réutilisation des contenus et support de lecture dans la régie. Cette demande remplace l'ancien hors-périmètre « l'app ne fournit jamais les questions ». Elle ne demande ni génération automatique, ni questions préremplies, ni verdict automatique.
- **Alternative actuelle** : conserver uniquement les libellés et le support externe. Elle reste un chemin de compatibilité pendant la transition, mais ne satisfait pas la capitalisation souhaitée.
- **Alternative minimale** : conserver les questions uniquement dans une partie. Plus simple mais insuffisant : la réutilisation dépendrait de l'historique des rooms.
- **Proposition recommandée, à confirmer au Bloc 16** : séparer bibliothèque éditable et copie de contenu utilisée pour une partie, avec références d'origine. Cela permet de corriger la bibliothèque sans changer rétroactivement une question en cours ou l'historique. Coût : données dupliquées et règles de copie/édition à expliciter. Une version immuable référencée est une autre solution réaliste ; ne pas imposer un système complet de versions sans besoin.
- **Frontière de sécurité à respecter** : réponses types et questions futures réservées aux personnes autorisées à préparer/présenter ; aucun envoi dans l'état commun des joueurs/Écran principal. Si l'affichage public de la question courante devient souhaité, il nécessite une décision distincte. Le rôle Présentateur d'une room ne donne pas automatiquement accès à toutes les bibliothèques des autres.
- **Priorité** : la consolidation/sauvegarde/reprise multi reste première. Prévoir les limites et relations du futur contenu dans le travail de schéma, sans faire dépendre la première sauvegarde de partie de toutes les fonctionnalités éditoriales. Ne pas fusionner cette bibliothèque utilisateur avec une hypothétique banque éditoriale prédéfinie.

### Incremental migration path

```text
[Saisie Présentateur]
        |
[Bibliothèque persistante]
        |
[Préparation de partie]
        |
[Régie : lecture et repères]
        |
[Verdict humain]
```

La saisie alimente des contenus durables, indépendants des rooms. La préparation choisit ce qui sera utilisé dans une partie. La régie consulte ces contenus avec des droits spécifiques ; seul le verdict humain appelle les règles de progression et de points.

1. Bloc 16 : confirmer partage, droits, sélection et comportement des nouvelles tentatives ; documenter le contrat sans modifier les règles existantes.
2. Bloc 17 : livrer création, édition, conservation et consultation de la bibliothèque avec migrations additives et tests d'accès. La suppression d'une room ne supprime aucun contenu de bibliothèque ; la politique de suppression/archivage de contenu doit préserver les parties existantes.
3. Bloc 18 : ajouter sélection pour une partie et lecture privée en régie ; conserver le mode support externe pour les anciens thèmes. Sauvegarder le contenu de partie et la question courante selon la politique retenue, afin de reprendre exactement après redémarrage.
4. Vérifier deux parties successives réutilisant le même thème et ses questions, puis un redéploiement et une restauration de sauvegarde. L'ancien parcours reste disponible tant que cette chaîne n'est pas validée. Ne pas revenir vers un binaire ignorant les états de parties enrichis sans compatibilité testée.

## Esquisse du modèle de données (guidage pour Bloc 2, le database-architect finalise le DDL exact)

- `player_profiles` : identité persistante légère — `local_player_id` (UUID, clé primaire logique côté client), `pseudo` (dernier pseudo utilisé, mutable), `games_played`, `games_won`, `best_theme`, timestamps.
- `rooms` : `code` (court, lisible, unique, actif ; nullable/non applicable pour une room solo qui n'a pas de code à partager), `mode` (`multi` | `solo`), `status` (lobby/in_progress/finished), `presentateur_local_player_id`, timestamps, `current_game_id` nullable.
- `games` : une partie jouée dans une room — `room_id`, `started_at`, `ended_at`, `state_json` (snapshot courant complet : joueurs, tours, barres de thème — pour la reprise après déconnexion/reload), `winner_player_id` nullable, et un flag de sous-état de choix joueur type `pending_choice` (nullable, porté ici ou sur `game_themes`/`game_players` selon ce que le database-architect juge le plus pertinent — décrit le type de choix en attente — sélection de thème ou continuer/coffrer — et le joueur concerné) pour refléter la couche show (`choice_pending`/`choice_open`) ; absent/`null` quand aucun choix n'est en attente de révélation.
- `game_players` : table de jonction `game_id` / `local_player_id` avec `points` courants et `turn_order`.
- `game_themes` : `game_id`, `label`, `progress_value`, `validated_squares`, `discovered`, `completed`, `nullified` (array ou JSON).
- `game_events` : journal append-only (`game_id`, `type`, `payload_json`, `created_at`, `actor_local_player_id`) pour l'historique/audit et le calcul des stats de fin de partie (plus gros coup risqué, plus gros coffrage) — pas destiné au replay/reconstruction d'état (voir Décision log).
- Index attendus : `rooms.code` unique (parmi les valeurs non nulles — nul autorisé pour une room solo sans code à partager), `player_profiles.local_player_id` unique, `game_events.game_id`.

### Extension de données questions/réponses (indicative, à finaliser après Bloc 16)

- Contenus de bibliothèque : thèmes identifiés de façon stable et questions associées, libellé/énoncé, réponse(s) indicative(s), auteur/propriétaire ou périmètre de partage, dates et statut d'archivage selon la politique retenue. Un même libellé ne doit pas fusionner arbitrairement deux thèmes.
- Séparer l'identité du créateur durable de son rôle temporaire de Présentateur dans une room. La perte de stockage navigateur et l'accès aux contenus doivent avoir une limite clairement documentée, cohérente avec les profils légers ; ne pas présumer de comptes forts.
- Contenu utilisé en partie : lien vers la source et copie figée ou version immuable selon décision du Bloc 16 ; sélection/ordre/question courante et tentatives seulement selon politique confirmée. Ne pas supposer exactement dix questions par thème parce que le tunnel comporte dix cases.
- Intégrité : fermeture, reset ou purge d'une room n'effacent pas la bibliothèque ; modification/archivage de la source n'altèrent pas une partie existante. Les sauvegardes/restaurations couvrent bibliothèque et contenus de partie.
- Projections réseau séparées : état public du jeu sans réponses ni questions futures ; accès privé autorisé à la bibliothèque et à la régie. La réponse type n'entre jamais dans les fonctions de scoring ou de jugement automatique.

## Building blocks

- [x] **Bloc 1 — Setup du repo et scaffolding monorepo**
  - Déliverable : structure `backend/` (FastAPI, pyproject/requirements, venv ignoré) et `frontend/` (Vite + React + Tailwind) dans un repo Git initialisé, avec `.gitignore` couvrant `__pycache__`, `.venv`, `node_modules`, `dist`, `.env`.
  - Done when : `git log` montre un commit initial ; `backend/` lance un `uvicorn` "hello world" ; `frontend/` lance un `npm run dev` Vite par défaut avec Tailwind configuré ; README racine décrit l'arborescence du repo.
  - Depends on : rien.

- [ ] **Bloc 2 — Modèle de données Postgres + migrations Alembic**
  - Déliverable : schéma complet (voir esquisse ci-dessus, finalisé/adapté par le database-architect) avec migrations Alembic versionnées.
  - Done when : `alembic upgrade head` crée toutes les tables sur une instance Postgres locale sans erreur ; chaque table a au moins une migration ; le schéma final est documenté (commentaires ou fichier `docs/schema.md`) ; les contraintes d'unicité (`rooms.code` unique quand non nul, `player_profiles.local_player_id`) sont en place, en tenant compte du fait qu'une room solo peut ne pas avoir de `code`.
  - Depends on : Bloc 1.
  - Bloquant à résoudre avant finalisation : voir Open questions (granularité de persistance, mécanisme d'identité, persistance du mode solo).

- [ ] **Bloc 3 — Spécification du protocole WebSocket (mode room multi)**
  - État 2026-10-20 : document existant, bloc rouvert pour alignement sur le code actuel puis sessions/reprise ; ne pas attendre Postgres pour corriger le contrat courant.
  - Déliverable : document `docs/websocket-protocol.md` listant chaque type de message (ex. `room:join`, `room:state_sync`, `role:assign`, `theme:select`, `choice:pending`, `choice:reveal`, `answer:good`, `answer:bad`, `answer:pass`, `answer:continue`, `answer:vault`, `turn:changed`, `game:ended`, `error`), sa direction (client→serveur / serveur→client / broadcast room), le **rôle exact autorisé à l'émettre** — en distinguant explicitement trois catégories : (1) jugement de réponse orale (`answer:good`/`answer:bad`/`answer:pass`) réservé au Présentateur, (2) choix de jeu du joueur (`theme:select`, `answer:continue`/`answer:vault`) réservé au joueur concerné et acceptés par le serveur uniquement si l'état courant est `choice:open` pour ce joueur, (3) déclenchement de révélation (`choice:reveal`) réservé au Présentateur — la forme JSON exacte du payload de chaque message, et la stratégie de reconnexion (comment un client qui se reconnecte récupère l'état courant complet de la room, y compris un `choice:pending` en cours).
  - Done when : chaque action de jeu de la spécification figée (Bonne réponse, Mauvaise réponse, Passer, Continuer, Coffrer, sélection de thème, reset, fin de partie) a un message WS correspondant documenté avec enforcement de rôle explicite ; le cycle `choice:pending` → `choice:reveal` → `choice:open` est documenté pour la sélection de thème ET pour Continuer/Coffrer, avec le rôle autorisé à faire avancer chaque transition ; le flux de reconnexion est décrit étape par étape.
  - Depends on : Bloc 2 (le protocole doit refléter les formes de données du schéma).

- [ ] **Bloc 4 — Backend FastAPI : moteur de règles + endpoints REST + tests unitaires**
  - État 2026-10-20 : moteur/API multi construits ; bloc rouvert car critères complets non établis. Fiabiliser les tests avant persistance, puis compléter historique/stats/banque après celle-ci. La solution de partage du moteur solo reste à décider avant le Bloc 7bis.
  - Déliverable : module(s) Python pur(s), découplés de tout transport (réutilisables tels quels par le mode room multi via Bloc 5 ET par le mode room solo hotseat), implémentant exactement la spécification figée (barème de points, coloration des cases, `coffrer`, `poursuivre`, gestion de `nullified`/`discovered`, garde-fou thème complété, reset vs quitter la partie, sous-état `choice_pending`/`choice_open` pour la sélection de thème et pour Continuer/Coffrer, coffrage automatique en case 10 qui ne passe jamais par cet état intermédiaire) + endpoints REST (création de room multi ou solo, jointure, banque de thèmes prédéfinis, historique, stats joueur) avec validation d'input (longueur pseudo/thème, nombre min de joueurs ≥2, nombre min de thèmes ≥1, caractères autorisés).
  - Done when : suite `pytest` verte couvrant au minimum : barème de points par palier (1/2/3/5), coffrage automatique en case 10 (sans passage par `choice_pending`), non-perte de progression sur mauvaise réponse, non-gain définitif sur case passée même après coffrage ultérieur, vol de progression par un autre joueur, rejet de sélection d'un thème `completed`, comportement distinct reset-partie vs quitter-partie, transition `choice_pending` → `choice_open` déclenchable uniquement par une action "Présentateur" et rejet d'un choix joueur tant que l'état est encore `choice_pending` ; endpoints REST testés manuellement ou via `pytest` + client de test FastAPI.
  - Depends on : Bloc 2, Bloc 3.

- [ ] **Bloc 5 — WebSocket handlers + gestion d'état de room + persistance (mode room multi)**
  - État 2026-10-20 : transport et rooms mémoire présents ; bloc rouvert pour sessions/permissions, reconnexion et persistance transactionnelle. Le snapshot et les événements sont enregistrés à chaque commande durable acceptée, pas seulement en fin de tour. Toute mise à jour des profils en fin de partie doit résister aux nouvelles tentatives sans double comptage.
  - Déliverable : gestionnaire de rooms en mémoire (process-local) orchestrant les connexions WebSocket selon le protocole du Bloc 3, enforcement des permissions par rôle en respectant la répartition fine actée (seul le Présentateur peut juger une réponse orale — Bonne réponse/Mauvaise réponse/Passer — et reset/quitter ; seul le joueur concerné peut sélectionner un thème à son tour ou trancher Continuer/Coffrer, et seulement une fois l'état `choice_open` pour lui ; seul le Présentateur peut déclencher la transition `choice_pending` → `choice_open` via `choice:reveal`), persistance Postgres aux transitions clés (fin de tour, fin de partie, événements notables pour l'historique), et reprise d'état après reconnexion (y compris un `choice_pending` en cours).
  - Done when : un test manuel ou automatisé avec au moins 3 clients WebSocket simultanés (1 Présentateur, 2 Joueurs) sur la même room montre une synchronisation correcte des scores/tours/état des cases en temps réel ; une tentative de jugement de réponse envoyée par un rôle Joueur est rejetée ; une tentative de choix joueur (sélection thème ou Continuer/Coffrer) envoyée par le Présentateur à la place du joueur concerné est rejetée ; une tentative de choix joueur envoyée par le joueur concerné alors que l'état est encore `choice_pending` est rejetée ; une tentative de `choice:reveal` envoyée par un Joueur est rejetée ; un client qui se déconnecte puis se reconnecte reçoit l'état complet et à jour de la room ; une partie terminée crée un enregistrement persistant consultable via les endpoints d'historique.
  - Depends on : Bloc 4.

- [x] **Bloc 6 — Design system frontend (DA Jazz Club)**
  - Déliverable : configuration Tailwind personnalisée (palette ambre/bordeaux/laiton/noir charbon/bleu nuit, typographie serif display + sans-serif lisible), composants de base réutilisables (boutons, cartes, modales, échelle typographique), traitement visuel de texture/grain/vignettage/spotlight.
  - Done when : une route ou page de démonstration interne rend la palette, l'échelle typographique et les composants de base de façon cohérente avec la DA décrite ; la config Tailwind est commentée/documentée (quelles couleurs/polices utiliser où).
  - Depends on : Bloc 1.

- [ ] **Bloc 7 — Écrans frontend + client WebSocket (mode room multi)**
  - État 2026-10-20 : parcours multi fonctionnel confirmé par l'utilisateur, avatars/transfert présents ; bloc rouvert uniquement pour son périmètre complet (banque, statistiques et accès solo) et la fiabilisation du client. Préserver l'affichage du tunnel pendant l'attente Continuer/Coffrer, boutons de choix absents jusqu'à révélation.
  - Déliverable : tous les écrans — Accueil avec le choix "Créer une room multi" (mis en avant) / "Créer une room solo" (secondaire) / rejoindre une room, Lobby (avec la possibilité pour le Présentateur d'y désigner un autre Présentateur), Saisie des thèmes par le Présentateur (manuelle façon "points noirs" + sélection depuis une banque de thèmes prédéfinis), vue Présentateur/régie (boutons de validation Bonne réponse/Mauvaise réponse/Passer, contrôle explicite "Lancer le choix" pour déclencher `choice:reveal`, vue d'ensemble de la room), vue Joueur (sélection de thème à son tour ou choix Continuer/Coffrer une fois révélés, **écran d'attente/suspense neutre** tant que l'état est `choice_pending` — aucune option ni bouton désactivé visible, attente sinon), vue Écran principal (affichage collectif en lecture seule, scores, tunnel en cours), tunnel de jeu animé (pièce maîtresse visuelle), écran de fin de partie avec podium animé et stats de partie — tous branchés au client WebSocket du protocole Bloc 3, avec routage conditionnel par rôle.
  - Done when : un playtest manuel complet sur 4 onglets/navigateurs (1 Présentateur + 2 Joueurs + 1 Écran principal) permet de jouer une partie entière du début à la fin en respectant exactement la spécification figée (y compris vol de progression, coffrage auto en case 10, garde-fou thème complété, délai de révélation via "Lancer le choix" pour la sélection de thème ET pour Continuer/Coffrer) ; chaque écran listé existe et est accessible selon le rôle ; un joueur en attente de révélation du choix Continuer/Coffrer ne voit strictement aucune option, même désactivée ; un joueur en attente de révélation de la sélection de thème voit la grille des thèmes mais ne peut cliquer sur aucun d'eux (voir révision du 2026-10-11 ci-dessus).
  - Depends on : Bloc 5, Bloc 6.

- [ ] **Bloc 7bis — Mode room solo (hotseat mono-écran)**
  - Priorité 2026-10-20 : différé après consolidation durable du multi. Avant réalisation, soumettre une décision technique sur le partage du moteur Python avec un navigateur local ; ne pas présenter le reducer TypeScript actuel comme un moteur strictement partagé. Conserver les contraintes produit sans code de room ni WebSocket ; si leur respect exige un changement architectural, obtenir un accord explicite avant modification. La persistance solo reste optionnelle et ne bloque pas la persistance multi.
  - Déliverable : écran de création de room solo accessible depuis l'Accueil (Bloc 7), flux hotseat sur un seul navigateur qui bascule manuellement entre la vue Présentateur et la vue du Joueur actif (pas de code de room, pas de connexion WebSocket), en réutilisant tel quel le moteur de règles du Bloc 4 (y compris la couche show `choice_pending`/`choice_open` et le contrôle "Lancer le choix", pertinents même à écran unique pour garder le rythme de jeu télé) et les composants d'écran du Bloc 7 adaptés à une bascule locale de vue plutôt qu'à un flux réseau.
  - Done when : un playtest manuel sur un seul navigateur permet de jouer une partie entière en mode solo du début à la fin (bascule Présentateur ↔ Joueurs, jugement de réponse, choix de thème et Continuer/Coffrer avec délai de révélation via "Lancer le choix"), en respectant exactement la même spécification figée que le mode multi (même barème, même coloration, même coffrage auto case 10) sans qu'aucun code de room ne soit généré ni qu'aucune connexion WebSocket ne soit requise.
  - Depends on : Bloc 4, Bloc 7.

- [ ] **Bloc 8 — Intégration audio**
  - État 2026-10-20 : implémentation présente (`AudioContext.tsx`, `sounds.ts`, bouton mute et branchements dans les écrans). Reste à valider effets/ambiance et préférences après reload sur navigateurs réels, documenter la synthèse sans assets externes, et préciser quels écrans émettent les sons pour éviter une cacophonie multi-appareils. Les effets actuellement liés aux clics locaux ne prouvent pas une diffusion synchronisée de chaque événement.
  - Déliverable : effets sonores sur bonne réponse, coffrage, tic-tac du chronomètre (paliers de couleur 60s→30s jaune→20s orange→10s rouge clignotant repris de l'original), ambiance musicale de fond discrète cohérente avec la DA jazz club, contrôle de volume/mute persistant côté client (ex. `localStorage`).
  - Done when : chaque effet sonore listé se déclenche sur l'événement correspondant pendant un playtest ; le mute persiste après rechargement de page ; les assets audio utilisés sont committés ou leur source libre de droits est documentée dans le README.
  - Depends on : Bloc 7.

- [ ] **Bloc 9 — Packaging déploiement Railway (service unique)**
  - État 2026-10-20 : Docker/Railway présents, version Railway en déploiement selon l'utilisateur ; bloc rouvert pour satisfaire les critères complets de configuration Postgres/sessions et exploitation durable. Conserver un seul processus applicatif et vérifier le déploiement/restauration via Bloc 14.
  - Déliverable : configuration de build qui produit le bundle React statique et le fait servir par FastAPI (fichiers statiques + fallback SPA), fichier `Procfile` ou configuration Nixpacks adaptée, lecture de `SECRET_KEY`/`DATABASE_URL`/`PORT` depuis l'environnement, bind `0.0.0.0`, `debug` désactivé, endpoint de health check.
  - Done when : un déploiement Railway (ou une simulation locale équivalente type `docker run` avec les mêmes variables d'env) sert à la fois l'API/WS et le frontend buildé depuis un seul process ; aucune valeur sensible ou host/port n'est codée en dur dans le code ; le plugin Postgres Railway peut être branché via `DATABASE_URL` sans modification de code.
  - Depends on : Bloc 5, Bloc 7.

- [ ] **Bloc 10 — Tests complémentaires et CI**
  - Déliverable : tests d'intégration WebSocket/API en plus des tests unitaires du Bloc 4, pipeline CI (ex. GitHub Actions) exécutant lint + tests backend + build frontend à chaque push.
  - Done when : la CI échoue si un test de règle de jeu casse ou si le build frontend échoue ; le pipeline est versionné dans le repo. Couverture attendue incluant au moins un scénario d'intégration vérifiant que le moteur de règles du Bloc 4 produit un résultat identique utilisé depuis le mode room multi (Bloc 5) et depuis le mode room solo (Bloc 7bis).
  - Depends on : première tranche immédiate sur le multi existant (Blocs 4/5/7 et Bloc 12), sans dépendance au solo ; ajouter les tests de parité seulement après Bloc 7bis.
  - État 2026-10-20 : tests backend présents mais périmés sur certains contrats. La première CI doit exécuter pytest, lint frontend et build TypeScript/Vite à chaque changement, et bloquer une livraison défectueuse. Ajouter ensuite les scénarios de sécurité, reprise et tests frontend ciblés. Ne pas déclarer la suite verte sans exécution.

- [ ] **Bloc 11 — Documentation**
  - Déliverable : README décrivant le setup local (backend + frontend), les variables d'environnement requises (tableau), les étapes de déploiement Railway, et un lien vers `docs/websocket-protocol.md` et `docs/schema.md`.
  - Done when : un nouvel arrivant peut suivre le README pour faire tourner l'app en local et la déployer sur Railway sans information manquante.
  - Depends on : Blocs 1-9, Bloc 7bis.

- [ ] **Bloc 12 — Référence fonctionnelle et réalignement des contrats**
  - Déliverable : état d'avancement distinguant présent/partiel/validé, protocole à jour et tests adaptés au modèle actuel de participants. Consigner la révision testée et la version Railway de référence sans supposer qu'elles sont identiques.
  - Done when : tests ne supposent plus `presentateurName` ni des index excluant le Présentateur ; DTO et documentation couvrent `isPresenter`, avatars, transfert et retrait ciblé ; scénario de référence à quatre clients décrit et exécuté (Présentateur, deux Joueurs, Écran principal), résultat consigné.
  - Depends on : multi existant ; première tranche du Bloc 10 menée avec ce bloc.

- [ ] **Bloc 13 — Sessions, permissions et robustesse du multijoueur**
  - Déliverable : preuve de session distincte des identifiants publics, autorisations évaluées sur le serveur courant à chaque commande, validation structurée des messages et cycle de connexion cohérent. Limites raisonnables de messages, taille de saisies, rooms inactives et ressources ; protection des fichiers statiques et configuration des origines vérifiées. Fixer des bornes adaptées au petit public sans imposer une architecture distribuée.
  - Done when : connaître le code de room et tous les identifiants publics ne permet pas d'usurper un participant ; le transfert retire immédiatement les pouvoirs de l'ancien Présentateur et les donne au nouveau sur leurs connexions existantes ; un participant retiré ne récupère pas son accès via un ancien secret ; Rejouer ne donne jamais un tour au Présentateur ; payload non objet, types incorrects et index booléens produisent une erreur contrôlée sans couper arbitrairement la partie. Tester joueur actif absent, tous joueurs absents, perte réseau, doublon de connexion et départ volontaire sans perte involontaire de l'accès de reprise. Consigner le traitement des anciennes sessions et vérifier une partie entière sans régression.
  - Depends on : Bloc 12 et CI initiale du Bloc 10 ; évolution du protocole Bloc 3 livrée avec les clients/serveur correspondants.

- [ ] **Bloc 14 — Reprise et exploitation durable sur Railway**
  - Déliverable : restauration des rooms/participants/rôles et états depuis Postgres, reconnexion navigateur avec conservation de la session lors d'une coupure transitoire, procédure de déploiement et de sauvegarde/restauration. Ne jamais sérialiser les sockets ni les verrous ; recalculer la présence réelle au retour des connexions. Définir explicitement le traitement du chrono en cours lors d'un reload/redémarrage (horodatage serveur ou reprise documentée), sans changement implicite des règles de jugement oral.
  - Done when : sur environnement de test Railway, redéploiement pendant sélection en attente, choix Continuer/Coffrer en attente et question en cours ; les clients retrouvent rôle, scores, progression, tour et sous-phase cohérents. Transaction échouée : aucun changement confirmé ; transaction validée puis diffusion interrompue : la reconnexion retrouve l'état enregistré, sans double attribution de points/statistiques. Restaurer une sauvegarde sur une base séparée et vérifier une partie récupérée. Documenter fréquence/rétention des sauvegardes, perte de données et délai de reprise visés après confirmation ; logs utiles sans secrets et vérification des migrations/health checks. Retour arrière testé vers une version compatible avec le schéma et les sessions.
  - Depends on : Blocs 2, 5, 13, tranche reprise du Bloc 10 ; complète Blocs 9/11.

- [ ] **Bloc 15 — Historique et profils durables, puis enrichissements**
  - Déliverable : endpoints et vues d'historique/profil, identité légère durable distincte du pseudo et du secret de session, statistiques de fin de partie calculables à partir des événements. Compléter ensuite banque de thèmes et statistiques finales annoncées, sans réécriture du parcours.
  - Done when : une partie terminée reste consultable après redémarrage ; deux parties avec le même profil alimentent les statistiques une seule fois chacune ; un changement de pseudo n'efface ni ne fusionne arbitrairement les profils ; un identifiant public seul ne permet pas de réclamer un profil. Règles d'égalité, d'abandon/fin anticipée et définition de meilleur thème/plus gros risque documentées avant calcul. Durée de conservation et suppression opérationnelle documentées. Banque et statistiques finales couvertes par tests ciblés et playtest.
  - Depends on : Bloc 14 ; complète les périmètres initiaux des Blocs 4/7. Solo reste différé et ne bloque pas ce bloc.

- [ ] **Bloc 16 — Contrat produit et données de la bibliothèque questions/réponses**
  - Déliverable : préciser avec l'utilisateur le partage de la bibliothèque et ses droits, les opérations de préparation/édition, l'association questions/thème/partie, le nombre requis, l'ordre ou la sélection manuelle, le comportement après mauvaise réponse/reprise d'une case, et le traitement des contenus incomplets. Comparer copie de partie et versions immuables ; formaliser la solution retenue après accord.
  - Done when : politiques ci-dessus explicitement confirmées, responsabilités bibliothèque/partie/règles documentées et droits définis pour créateur, autre Présentateur, Joueur et Écran principal. Critère invariant : réponses indicatives seulement, sans validation automatique. Pas d'hypothèse arbitraire « une question par case », « bibliothèque commune » ou « chaque Présentateur peut tout éditer ».
  - Depends on : besoin accepté le 2026-10-20 ; peut être clarifié en parallèle de la consolidation. Ne bloque pas la première version de persistance multi.

- [ ] **Bloc 17 — Bibliothèque persistante de thèmes, questions et réponses indicatives**
  - Déliverable : modèle/migrations, endpoints et interface de préparation permettant de créer et modifier un thème, saisir ses questions et réponses types, enregistrer, retrouver et réutiliser les contenus indépendamment de la room ; archivage/suppression selon politique du Bloc 16. Validation des tailles/types et autorisations côté serveur.
  - Done when : un Présentateur prépare des contenus, ferme sa room, recharge le navigateur et retrouve ses contenus avec sa session/profil autorisé ; les contenus persistent après redémarrage et restauration d'une sauvegarde. Tests d'accès croisé entre propriétaires/périmètres selon droits confirmés ; accès refusé aux joueurs et écrans non autorisés. La suppression d'une room ne détruit pas la bibliothèque ; une modification de source ne change pas les contenus déjà figés pour une partie. CI couvre CRUD, intégrité et accès.
  - Depends on : Bloc 16, schéma Bloc 2, sessions Bloc 13 et exploitation Bloc 14 ; migrations additives, sans bloquer l'étape initiale de sauvegarde multi.

- [ ] **Bloc 18 — Réutilisation en partie et support questions/réponses de la régie**
  - Déliverable : sélection de thèmes/questions de bibliothèque lors de la préparation et consultation par le Présentateur de l'énoncé et des réponses indicatives pendant le tunnel. Raccordement aux phases existantes question-pending/question sans changer les pouvoirs, le barème ou la validation orale ; conserver les thèmes avec support externe comme chemin de compatibilité.
  - Done when : deux parties distinctes utilisent les mêmes contenus sans ressaisie ; fin/reset/fermeture de la première ne détruit pas la source. Tests de sélection/reprise après échec selon politique du Bloc 16 et restauration exacte du contexte de question après redéploiement. Inspection des réponses REST et messages WebSocket prouve l'absence de réponses/questions futures dans les flux Joueur/Écran principal ; un changement de rôle retire l'accès privé et ne se contente pas de cacher des boutons (un contenu déjà vu par un ancien Présentateur ne peut toutefois pas être effacé de sa mémoire). Modifier une réponse type ne déclenche jamais un verdict ou une attribution de points. Playtest complet avec questions intégrées, puis vérification du parcours externe historique.
  - Depends on : Bloc 17 et base multi consolidée (Blocs 5/7/13/14), contrat privé du Bloc 3 et tests du Bloc 10 ; documenter usage et restauration au Bloc 11.

## Open questions

### Questions actuelles — 2026-10-20

- **Bibliothèque questions/réponses (nouveau besoin)** : personnelle ou partagée, bénéficiaires et droits de modification ; mode de sélection/ordre, nombre de questions nécessaire pour lancer, gestion des questions manquantes et des tentatives après échec ; saisie seulement en préparation ou également en partie. Confirmer copie de partie ou référence à une version immuable avant réalisation. La demande n'autorise pas implicitement l'accès de tous à tous les contenus.
- Offre Postgres et sauvegardes réellement disponibles sur Railway ; procédure et test de restauration.
- Rétention des parties/profils, délai de reprise acceptable et perte de données acceptable pour les sauvegardes. La cible des commandes confirmées est leur enregistrement transactionnel ; une sauvegarde périodique a une garantie différente.
- Mécanisme exact des secrets de session/profil, durée, renouvellement et compatibilité avec les navigateurs déjà connectés ; à trancher au Bloc 13 sans introduire de comptes forts.
- Politique du chronomètre et de la présence lors d'une reprise ; règles statistiques des fins anticipées/égalités et métriques à finaliser.
- Architecture du moteur solo à décider avant Bloc 7bis, sans bloquer le multi durable. Sa persistance facultative ne bloque plus la clôture du schéma multi : documenter explicitement son exclusion de cette première version du schéma si retenue.

Le snapshot transactionnel plus journal séparé et la séparation identité publique/secret de session sont actés. Les anciennes propositions d'UUID ci-dessous ne doivent jamais être interprétées comme une autorisation de s'authentifier avec un identifiant diffusé.

### Historique des questions initiales (supplanté par les décisions du 2026-10-20 en cas de conflit)

1. **Granularité de persistance pour la reprise de partie** : l'utilisateur demande de pouvoir "reprendre une partie en cours si possible" sans trancher la mécanique exacte. Proposition par défaut (à valider par le database-architect au Bloc 2, ne bloque pas le démarrage du Bloc 1) : un snapshot complet de l'état courant dans `games.state_json`, mis à jour de façon transactionnelle à chaque action qui modifie l'état, plus un `game_events` append-only séparé pour l'historique/les stats de fin de partie — pas d'event-sourcing complet avec replay. Si cette approche ne convient pas, le confirmer avant de clore le Bloc 2.
2. **Mécanisme exact de réconciliation d'identité joueur** : l'utilisateur veut un pseudo sans mot de passe avec stats cumulées dans le temps. Proposition par défaut (voir Décision log ci-dessous) : UUID `local_player_id` stocké côté navigateur comme clé réelle des stats, le pseudo restant un simple libellé d'affichage mutable. Limite connue acceptée : si le stockage local est vidé, l'historique de ce joueur n'est plus relié automatiquement (pas de système de réclamation, explicitement hors scope). Si l'utilisateur veut un comportement différent (ex. pseudo globalement unique et verrouillé), le signaler avant de clore le Bloc 2.
3. **Persistance exacte du mode room solo** : la décision actée laisse le choix "persisté de façon simplifiée ou pas du tout" à l'implémenteur, sans trancher. Proposition par défaut (ne bloque pas le démarrage du Bloc 1, ni même du Bloc 2) : ne PAS créer de ligne `rooms`/`games` en base pour une partie solo — l'état de jeu solo vit uniquement en mémoire/`localStorage` côté client le temps de la partie, et n'alimente ni l'historique (`game_events`) ni les stats cumulées de `player_profiles`. Raison : le mode solo est positionné comme un mode d'appoint hotseat (reproduction de l'ancien jeu Flask mono-écran), pas comme le cas d'usage central nécessitant reprise après crash ou stats long terme ; réduit aussi la surface de code du Bloc 7bis. Si l'utilisateur souhaite que les parties solo alimentent quand même les stats de profil, le signaler avant de clore le Bloc 2 (impact sur le schéma : `rooms.mode` devrait alors être vérifié par le database-architect pour s'assurer qu'une room solo sans code reste compatible avec les contraintes d'unicité de `rooms.code`, ex. `code` nullable pour ce mode).

Aucune de ces trois questions ne bloque le démarrage du Bloc 1 ; elles doivent être tranchées (ou la proposition par défaut confirmée) avant de clore le Bloc 2.

**Confirmation Orion (2026-10-10)** : les propositions par défaut 1 et 2 ci-dessus sont validées telles quelles, pas de remontée nécessaire à l'utilisateur — cohérentes avec les décisions déjà actées (pseudo simple sans mot de passe, persistance pragmatique plutôt qu'event-sourcing complet). La question 3 (persistance du mode solo) est nouvelle suite à l'amendement de ce plan sur les rôles/room et n'a pas encore reçu de confirmation explicite ; sa proposition par défaut est néanmoins raisonnable et n'empêche pas de démarrer le Bloc 1 ou le Bloc 2.

## Decision log

- **Bibliothèque thèmes/questions/réponses demandée par l'utilisateur (2026-10-20)** : le support annexe actuel doit pouvoir être remplacé à terme par la préparation dans l'application de thèmes, questions associées et réponses types uniquement indicatives. Les contenus persistent après la partie et sont réutilisables dans des parties futures pour constituer progressivement une base. Le jugement reste humain, sans validation automatique. Remplace l'ancienne exclusion des questions/réponses et la description du support externe comme seul fonctionnement possible ; la consolidation durable reste prioritaire. Ajout des Blocs 16–18. Le partage, l'ordre des questions, le traitement des nouvelles tentatives et le choix copie/version restent à confirmer, non présumés acceptés.
- **Service durable à faible fréquentation — accepté explicitement par l'utilisateur (2026-10-20)** : une version Railway est en déploiement et une partie complète fonctionne ; moins de cinq rooms simultanées attendues. Option 2 acceptée : fiabiliser le multijoueur, ajouter sauvegarde/reprise, puis historique/profils ; différer solo et enrichissements. Préserver le monorepo et un service applicatif/processus unique ; pas de Redis, microservices ni réécriture.
- **Durabilité et sécurité de session (2026-10-20)** : identifiant public de participant/profil distinct du secret de session ; permissions vérifiées sur l'état serveur courant, y compris après transfert. Snapshot versionné et événements utiles dans une transaction avant publication du nouvel état ; reprise des rooms et reconnexion navigateur nécessaires en plus de Postgres. Sauvegarde et restauration réellement testées avant de déclarer le service durable. Détails de stockage des secrets et objectifs opérationnels restent à préciser dans les blocs correspondants.
- **Suivi réaliste et ordre de consolidation (2026-10-20)** : blocs 3/4/5/7/9 rouverts car leurs critères complets ne sont pas établis, sans nier le code existant ni le parcours fonctionnel confirmé. Audio présent mais validation restante ; tests backend à réaligner, CI prioritaire sans attendre le solo. Ajout des Blocs 12–15 pour référence, sessions/robustesse, reprise/exploitation et fonctions durables. Les confirmations historiques de tests ne valent pas exécution sur la version inspectée.

- **Granularité de persistance (proposition de planning)** : snapshot transactionnel (`games.state_json`) + log d'événements append-only séparé pour l'historique, plutôt qu'event-sourcing complet. Raison : couvre le besoin exprimé ("reprendre si possible") avec une complexité d'implémentation bien moindre qu'un vrai replay d'événements, tout en gardant un historique exploitable pour les stats de fin de partie. Modifiable si le database-architect ou l'utilisateur identifie un besoin de replay fin.
- **Identité joueur via `local_player_id`** : UUID client-side comme clé de stats réelle, pseudo comme libellé mutable non unique globalement. Raison : respecte la contrainte "pseudo simple sans mot de passe" sans construire un vrai système de comptes, tout en permettant des stats cumulées cohérentes pour un même navigateur/joueur dans le temps.
- **Garde-fou thème complété ajouté (absent de l'original)** : un thème `completed=true` doit être non-sélectionnable. Raison : l'original permettait de resélectionner un thème terminé et aboutissait à un état mort (aucune case ne peut plus évoluer) — classé dans la dette "absence de garde-fous" explicitement à corriger.
- **"Quitter la partie" vide réellement l'état de la room (diverge du code original)** : le code original de `go_main_menu` ne faisait que changer un champ d'état sans rien vider, ce qui contredisait le comportement voulu décrit par l'utilisateur ("retour menu efface tout"). Raison du choix : la description fonctionnelle de l'utilisateur fait foi sur le comportement observé dans le code quand les deux divergent, car le code présente ce point comme un bug non intentionnel plutôt qu'une règle de jeu à préserver.
- **Renommage Animateur → Présentateur (2026-10-10)** : tous les usages du terme "Animateur" (texte, décisions, scope, modèle de données, building blocks) sont renommés en "Présentateur", y compris le champ `rooms.animateur_local_player_id` devenu `rooms.presentateur_local_player_id`. Raison : terme plus cohérent avec la couche "show" ajoutée (le rôle anime littéralement un numéro façon jeu télé, pas seulement une session technique) — demande explicite de l'utilisateur après clarification du concept de rôle.
- **Continuer/Coffrer repasse au joueur, pas au Présentateur (2026-10-10)** : le pouvoir de choisir entre Continuer et Coffrer après une bonne réponse non terminale appartient désormais exclusivement au joueur concerné, et non plus au Présentateur. Raison : c'est un choix de risque/récompense qui porte sur le propre gain du joueur — le faire trancher par un tiers (le Présentateur) n'avait de sens que dans l'ancienne architecture mono-écran où un seul device existait pour afficher des boutons ; en multi-device, chaque joueur peut recevoir son propre choix sur son propre écran, ce qui est plus fidèle à l'intention du jeu. Le Présentateur garde uniquement la main sur le jugement de la réponse orale (Bonne réponse/Mauvaise réponse/Passer), car lui seul connaît la bonne réponse.
- **Couche "show" de délai de révélation des choix joueur (2026-10-10)** : introduction d'un sous-état `choice_pending` (écran d'attente neutre côté joueur) avant `choice_open` (choix visible/cliquable), déclenché manuellement par le Présentateur via un contrôle "Lancer le choix", pour la sélection de thème ET pour Continuer/Coffrer. Raison : reproduit le rythme d'un vrai jeu télé/cabaret où l'animateur s'exprime à l'oral et crée du suspense avant de révéler les options au candidat — sans cette couche, un choix purement multi-device synchronisé en temps réel s'afficherait instantanément au joueur dès que les conditions sont remplies, cassant l'effet de showmanship voulu par l'utilisateur. Le coffrage automatique en case 10 reste exclu de cette couche car aucun choix humain n'y intervient.
- **Couche "show" de délai de lancement du chrono (2026-10-11)** : introduction du sous-état `question-pending` avant `question`, déclenché manuellement par le Présentateur via "Lancer le chrono" (`timer:start`), appliqué à la fois après `SELECT_THEME` et après `CONTINUE`. Raison : retour utilisateur — le Présentateur doit pouvoir poser sa question à l'oral avant que le chrono ne démarre, sans quoi le minuteur s'écoule pendant qu'il parle encore, ce qui est injuste pour le joueur. Introduit mécaniquement deux temps côté joueur concerné : écoute de la question (pas de chrono) puis attente du verdict (chrono lancé). Choix de nommer l'action "Lancer le chrono" (et non "Poser la question") pour rester explicite sur l'effet technique déclenché, cohérent avec "Lancer le choix" déjà utilisé pour la couche choice_pending/choice_open.
- **Room solo = hotseat local pur, sans code de room ni WebSocket (2026-10-10)** : le mode "Créer une room solo" ne génère pas de code à partager et ne passe pas par le protocole WebSocket du Bloc 3 — un seul navigateur bascule manuellement entre les vues des rôles. Raison : reproduit fidèlement le fonctionnement mono-écran de l'ancien jeu Flask pour les usages où un seul appareil est disponible (ex. jouer autour d'un unique ordinateur/TV sans que chaque participant ait son propre device), sans forcer l'utilisateur à ouvrir artificiellement plusieurs onglets ou à gérer un code de room inutile dans ce contexte. Le moteur de règles (Bloc 4) reste strictement partagé avec le mode multi pour éviter une double implémentation de la logique de jeu — seule la couche transport/affichage (Bloc 7bis) diffère.
- **Fusion des phases `menu` et `themes` en un lobby unique + renommage de soi (2026-10-11)** : les anciennes phases séparées "attente des joueurs" et "saisie des thèmes" sont fusionnées en une seule phase `lobby` affichant simultanément la liste des joueurs connectés, le nom du Présentateur, et la saisie des thèmes (réservée au Présentateur). Le message `lobby:go_to_themes` est supprimé ; `game:start` vérifie désormais en une seule fois `players.length >= 2` ET `themes.length >= 1`. Raison : retour utilisateur — avoir deux écrans séquentiels pour une phase qui est de toute façon entièrement pilotée par le Présentateur en amont de la partie n'apportait aucune valeur de suspense (contrairement aux couches "show" en cours de partie) et complexifiait inutilement la navigation. Ajout du message `player:rename` permettant à n'importe quel participant (Présentateur, Joueur, Écran principal) de changer SON PROPRE pseudo, mais uniquement tant que `phase === 'lobby'` (figé dès `game:start`) — chacun ne peut renommer que soi-même, jamais un autre participant. Le nom du Présentateur, qui n'a jamais existé dans `state.players` (il n'est pas un joueur), est désormais exposé à tous les clients via le nouveau champ `GameState.presentateurName`, alimenté côté serveur par `Room.names`/`Room.presentateur_name` (voir `backend/app/rooms/manager.py`).
- **Présence/absence de joueur + fin de partie anticipée + sobriété scénique (2026-10-11)** : série de retours UX/DA. (1) Un Joueur peut quitter SA partie individuellement (bouton "Quitter la partie") sans affecter les autres : il reste dans `state.players` (classement final préservé) mais passe `connected: false`, son tour est sauté par la rotation (`engine._next_player_index` saute désormais les joueurs non connectés), et il peut rejoindre la même room plus tard pour reprendre sa place (`engine.set_player_connected`). (2) Action séparée et distincte `game:end_early` (bouton "Terminer la partie", Présentateur uniquement, visible sur tous les écrans de jeu via `frontend/src/components/GameControls.tsx`) qui ramène tout le monde au lobby en conservant joueurs/thèmes, scores remis à zéro — différent de `room:quit` qui ferme intégralement la room. (3) Textes retravaillés dans l'esprit scénographie/cabaret : "Tour de X" devient "X monte sur scène"/"X est sur scène", les boutons Continuer/Coffrer sont renommés "Rester sur scène"/"Descendre" (sans changer les actions internes `CONTINUE`/`COFFRER`). (4) `ChoicePendingScreen` (écran avant Continuer/Coffrer) allégé textuellement : le bouton "Lancer le choix" est conservé mais la phrase explicative est supprimée, car un Présentateur humain parle déjà à l'oral. (5) L'animation de rideau d'ouverture reste réservée à l'entrée dans le tunnel (sélection de thème) ; une nouvelle animation de **fermeture** (`frontend/src/components/decor/CurtainClose.tsx`) se joue systématiquement à CHAQUE sortie du tunnel vers l'écran Sélection, peu importe la cause (mauvaise réponse, Passer, Descendre, ou coffrage automatique case 10). (6) `ScoreBoard` réorganisé en sémiologie théâtrale "Cour"/"Jardin" : le joueur actif est mis en avant au centre sous "Sur scène", les joueurs déjà passés dans ce tour de table sont groupés à gauche sous "Cour", les prochains à droite sous "Jardin" — convention explicitement choisie par l'utilisateur (même si elle diverge de la convention théâtrale standard où jardin=gauche vu de la salle). Raison globale : rendre l'interface plus tolérante aux aléas de connexion réseau en partie (un joueur qui perd sa connexion ne doit pas bloquer la partie des autres) et renforcer l'identité "spectacle vivant/cabaret" de la direction artistique jusque dans le choix des mots et des transitions visuelles.
- **Fusion de l'écran d'attente Rester sur scène/Descendre dans le Tunnel, lobby thèmes masqué, densité visuelle (2026-10-11)** : six retours UX supplémentaires. (1) Correction d'un bug réel du `ScoreBoard` : les deux moitiés "Cour"/"Jardin" étaient construites en parcourant chacune l'intégralité du cercle des autres joueurs au lieu de se le partager, dupliquant chaque joueur non actif des deux côtés — corrigé en répartissant les `count - 1` joueurs restants en deux moitiés disjointes (`Math.ceil((count-1)/2)` de chaque côté) ; un joueur diamétralement opposé au joueur actif peut légitimement apparaître une fois à chaque extrémité lorsque le nombre de joueurs est pair (comportement voulu, pas un résidu du bug). (2) Suppression de `ChoicePendingScreen.tsx` : l'écran de suspense neutre avant Rester sur scène/Descendre démontait tout le contexte visuel du thème en cours ; désormais le thème, le tunnel et le `ScoreBoard` restent affichés sans interruption pendant l'attente, seuls les boutons de décision sont conditionnés à la révélation — principe général retenu : un temps d'attente imposé par le Présentateur ne doit jamais changer drastiquement ce que voit le joueur, pour lui permettre un choix éclairé et éviter un rideau déclenché inutilement à ce palier interne (le rideau de sortie de tunnel reste déclenché uniquement par le changement de `phase`, donc non affecté). (3) Le panneau de saisie des thèmes dans le lobby est désormais entièrement absent du DOM pour les rôles Joueur/Écran principal (plus de pastilles d'attente, plus aucune trace du panneau) — le secret est garanti par l'invisibilité du panneau plutôt que par un masquage visuel. (4) Côté Présentateur, le panneau Thèmes est déplacé dans une colonne latérale dédiée (disposition `flex-row` sur grand écran), l'input de saisie n'est plus masqué en `type="password"` (redondant désormais) et les thèmes existants s'affichent en clair ; la liste des thèmes a un défilement interne propre (`max-h-64 overflow-y-auto`) qui empêche la page entière de devenir scrollable même avec de nombreux thèmes. (5) Les cartes de thèmes de l'écran Sélection sont resserrées (grille plus dense, textes et paddings réduits) pour accueillir plus de thèmes à l'écran sans perte de lisibilité. (6) Les cases de couleur du tunnel sont agrandies à la fois en miniature (`MiniProgressBar`, cartes de sélection) et en grand format (`Tunnel`, écran de jeu), pour une meilleure lisibilité de la progression à distance. Validé par 54 tests backend inchangés (changements purement frontend) et un playtest Playwright à 5 clients (1 Présentateur + 4 joueurs, nombre pair choisi pour couvrir le cas de duplication légitime Cour/Jardin).
