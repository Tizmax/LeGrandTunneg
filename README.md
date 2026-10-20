# Le Grand Tunneg

Jeu multijoueur en ligne façon "Fort Boyard", avec un rôle Animateur central qui
pilote la partie et un écran collectif suivi par les joueurs sur leurs propres
appareils.

Pour le détail complet du projet (règles de jeu, décisions produit, modèle de
données et plan d'exécution), voir l'exec-plan de référence :
[`docs/exec-plans/reconstruction-le-grand-tunneg.md`](docs/exec-plans/reconstruction-le-grand-tunneg.md).

## Structure du repo

```
LeGrandTunneg/
├── backend/        Backend FastAPI (Python) — API REST + WebSocket
├── frontend/        Frontend React + Vite + Tailwind CSS
└── docs/             Documentation du projet (exec-plans, specs)
```

## Setup local rapide

### Backend (FastAPI)

```bash
cd backend
uv venv .venv                        # ou: python3 -m venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt   # ou: pip install -r requirements.txt
cp .env.example .env                 # puis ajuster les valeurs si besoin
python -m app.serve
```

L'API démarre sur `http://127.0.0.1:8000`. Vérifier avec :

```bash
curl http://127.0.0.1:8000/health
# -> {"status":"ok"}
```

### Frontend (React + Vite + Tailwind)

```bash
cd frontend
npm install
npm run dev
```

Le serveur de dev Vite démarre par défaut sur `http://localhost:5173`.

### Tester en multi-device (local)

Le mode room multi nécessite plusieurs navigateurs/appareils connectés en même
temps. En local sur le même réseau Wi-Fi :

```bash
# Terminal 1 — backend accessible depuis le réseau local
cd backend && ALLOWED_ORIGINS='http://<IP-LOCALE>:5173' python -m app.serve

# Terminal 2 — frontend pointant vers l'IP locale du backend
cd frontend && VITE_API_BASE_URL='http://<IP-LOCALE>:8000' npm run dev -- --host
```

Puis ouvrir `http://<IP-LOCALE>:5173` depuis chaque appareil (PC, téléphone,
tablette). Utiliser des profils de navigation isolés (navigation privée) pour
chaque rôle, car l'identité de session est stockée dans `localStorage`
(clé `legrandtunneg:identity:v2`) et serait partagée entre onglets du même
profil. La dernière socket authentifiée gagne; l'autre onglet n'essaie pas de
reprendre automatiquement la main. Utiliser des profils isolés, pas seulement
plusieurs onglets.

⚠️ L'état des rooms est actuellement en mémoire uniquement (pas de
persistance Postgres, voir Bloc 2) : un redémarrage du backend efface toutes
les parties en cours.

## Validation et CI

Depuis la racine, avec les dépendances installées :

```bash
(cd backend && timeout 120s .venv/bin/python -m pytest -q)
(cd frontend && npm test && npm run lint && npm run build)
```

`npm run lint` utilise Oxlint. Le timeout pytest borne aussi les attentes
WebSocket ; code 124 signifie un timeout, pas un succès. Sur un système sans
`timeout`, utiliser un équivalent avec échec explicite à expiration.

Le workflow [CI](.github/workflows/ci.yml) exécute les tests sous Python 3.12
et tests frontend + Oxlint + build sous Node 22.22.1 à chaque push et pull request. Ces versions
sont compatibles avec le Dockerfile (Python 3.12, Node 22) et les engines npm.
Les deux jobs doivent réussir ; aucun échec n'est ignoré.

- [Protocole REST/WebSocket actuel](docs/websocket-protocol.md).
- [Référence validée, baseline et limites du premier jalon](docs/validation-jalon-1.md).
- [Validation locale Bloc 13 et limites de preuve](docs/validation-bloc-13.md).

Un workflow versionné n'active **pas** à lui seul les checks de fusion ni
l'attente de la CI côté Railway. Leur configuration et la preuve de blocage
d'une révision rouge restent à établir par le responsable des accès distants,
selon la procédure du compte-rendu. Aucun gate distant n'est déclaré validé.

## Déploiement (Railway)

Le projet se déploie comme un service unique : un seul process FastAPI sert
à la fois l'API REST, le WebSocket, et le bundle frontend statique (fallback
SPA). Le build est défini par le `Dockerfile` à la racine du repo (étape 1 :
build du frontend avec Node ; étape 2 : image Python qui copie le bundle
buildé et sert tout via `uvicorn`).

### Variables d'environnement

| Variable          | Requise | Défaut | Description |
|--------------------|---------|--------|-------------|
| `PORT` | Non (Railway la fournit) | `8000` | Port lu par `python -m app.serve`. |
| `APP_ENV` | Oui en production | `development` | Utiliser `production`; configuration invalide bloque le démarrage. |
| `ALLOWED_ORIGINS` | Oui en production | `http://localhost:5173,http://127.0.0.1:5173` en dev | Origines exactes CORS **et WS**, liste HTTPS explicite en production, sans chemin ni wildcard. Même host n'est pas une exemption. |

Le point d'entrée `python -m app.serve` applique `MAX_MESSAGE_BYTES` à Uvicorn
avant décodage JSON et borne sa queue de transport. Ne pas le remplacer par un
`uvicorn app.main:app` nu qui perdrait ces paramètres. Un seul worker/réplica;
rooms, secrets hachés, quotas et verrous restent process-local. Les métadonnées
forwarded/proxy ne sont pas fiables par défaut; les quotas sont globaux et ne
dépendent pas d'une IP annoncée par le client.

Toutes les bornes suivantes sont configurables, positives et finies, vérifiées
au démarrage. Les entiers n'acceptent pas de flottants ou valeurs illimitées.
`MAX_PLAYERS` ne peut excéder les 16 avatars; l'intervalle de nettoyage ne peut
excéder le TTL.

| Variable | Défaut |
|---|---|
| `MAX_ROOMS` / `MAX_PLAYERS` / `MAX_SCREENS` / `MAX_THEMES` | `10` / `16` / `4` / `32` |
| `MAX_NAME_CHARS` / `MAX_THEME_LABEL_CHARS` | `24` / `100` |
| `MAX_MESSAGE_BYTES` / `MAX_REST_BODY_BYTES` | `8192` / `8192` |
| `REST_BODY_TIMEOUT_SECONDS` / `MAX_REST_BODY_READERS` | `5` / `32` |
| `AUTH_TIMEOUT_SECONDS` / `SEND_TIMEOUT_SECONDS` | `5` / `2` |
| `MAX_PREAUTH_CONNECTIONS` / `MAX_AUTHENTICATED_CONNECTIONS` | `32` / `200` |
| `ROOM_IDLE_TTL_SECONDS` / `ROOM_CLEANUP_INTERVAL_SECONDS` | `86400` / `60` |
| `REST_RATE_PER_SECOND` / `REST_RATE_BURST` | `5` / `20` |
| `WS_UPGRADE_RATE_PER_SECOND` / `WS_UPGRADE_RATE_BURST` | `10` / `20` |
| `WS_COMMAND_RATE_PER_SECOND` / `WS_COMMAND_RATE_BURST` | `20` / `40` |
| `WS_GLOBAL_RATE_PER_SECOND` / `WS_GLOBAL_RATE_BURST` | `200` / `400` |

Les lectures create/join/reprise partagent au plus 32 places par process, sans
file d'attente. La lecture du corps a une deadline absolue de 5 secondes, non
renouvelée par les chunks. Timeout : HTTP 408 `request_timeout`; lecteurs saturés :
HTTP 503 `capacity_exceeded`, avec `Cache-Control: no-store`. Le quota de débit
REST reste distinct (HTTP 429). Ces bornes sont appliquées par l'application,
sans hypothèse sur un timeout du proxy Railway.

Le TTL commence sans socket authentifiée (écrans compris); REST et preuves
incorrectes ne le prolongent pas. Aucune persistance après restart. Les valeurs
`DATABASE_URL` et `SECRET_KEY` ne fournissent ici ni sauvegarde ni comptes.

L'identité v2 contient une preuve bearer dans localStorage : tout JavaScript
same-origin compromis peut la voler. Ne pas enregistrer les corps create/join
ou les trames `session:auth` dans les logs/traces. Le secret ne passe jamais en
URL, DTO public ou broadcast. La suppression d'un joueur révoque son accès.
Déconnexion volontaire conserve la preuve mais exige un clic Reprendre, même
après reload. Les anciens clients UUID-only doivent rejoindre explicitement.

### Déployer sur Railway (via GitHub)

1. Pousser le repo sur GitHub (`git remote add origin <url> && git push -u origin main`).
2. Sur [railway.app](https://railway.app) : **New Project → Deploy from GitHub repo**, sélectionner ce repo.
3. Railway détecte le `Dockerfile` à la racine (confirmé par `railway.toml`, builder `DOCKERFILE`) et lance le build automatiquement.
   Configurer `APP_ENV=production` et `ALLOWED_ORIGINS=https://<domaine-public>`
   avant démarrage. Une mise à jour Bloc 13 est incompatible avec les anciens
   clients : fenêtre sans partie, puis reload de chaque client.
4. Une fois déployé, Railway fournit une URL publique HTTPS/WSS unique — vérifier `/health` pour confirmer que le service tourne.
5. Chaque `git push` sur la branche connectée peut déclencher un déploiement.
   Activer et vérifier l'attente des checks CI côté Railway avant de considérer
   la livraison comme protégée ; le health check `/health` ne remplace pas la CI.

### Tester le build de production en local (sans Railway)

```bash
docker build -t legrandtunneg .
docker run -p 8000:8000 -e APP_ENV=production -e 'ALLOWED_ORIGINS=https://<domaine-public>' legrandtunneg
curl http://127.0.0.1:8000/health
```

Ces commandes décrivent la procédure; elles ne constituent pas une preuve de
build Docker ou de déploiement Railway. Le compte-rendu distingue les
vérifications réellement exécutées des accès distants non vérifiés.
