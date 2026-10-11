# Le Grand Tunneg

Jeu multijoueur en ligne façon "Fort Boyard", avec un rôle Animateur central qui
pilote la partie et un écran collectif suivi par les joueurs sur leurs propres
appareils.

Pour le détail complet du projet (règles de jeu, décisions produit, modèle de
données, plan d'exécution en 11 blocs), voir l'exec-plan de référence :
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
uvicorn app.main:app --reload
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
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — frontend pointant vers l'IP locale du backend
cd frontend && VITE_API_BASE_URL=http://<IP-LOCALE>:8000 npm run dev -- --host
```

Puis ouvrir `http://<IP-LOCALE>:5173` depuis chaque appareil (PC, téléphone,
tablette). Utiliser des profils de navigation isolés (navigation privée) pour
chaque rôle, car l'identité de session est stockée dans `localStorage`
(clé `legrandtunneg:identity`) et serait partagée entre onglets du même
profil.

⚠️ L'état des rooms est actuellement en mémoire uniquement (pas de
persistance Postgres, voir Bloc 2) : un redémarrage du backend efface toutes
les parties en cours.

## Déploiement (Railway)

Le projet se déploie comme un service unique : un seul process FastAPI sert
à la fois l'API REST, le WebSocket, et le bundle frontend statique (fallback
SPA). Le build est défini par le `Dockerfile` à la racine du repo (étape 1 :
build du frontend avec Node ; étape 2 : image Python qui copie le bundle
buildé et sert tout via `uvicorn`).

### Variables d'environnement

| Variable          | Requise | Défaut | Description |
|--------------------|---------|--------|-------------|
| `PORT`             | Non (fournie par Railway) | `8000` | Port d'écoute HTTP, lu dynamiquement par le `Dockerfile`. |
| `ALLOWED_ORIGINS`  | Non | `*` | Liste d'origines CORS autorisées, séparées par des virgules. Le service étant unique (API + frontend sur le même host), `*` est sans risque ; à restreindre uniquement si le frontend est un jour servi depuis un domaine distinct. |
| `DATABASE_URL`     | Non pour l'instant | — | Prévue pour le Bloc 2 (persistance Postgres). Le plugin Postgres de Railway peut être branché sans modification de code dès que ce bloc sera implémenté. |
| `SECRET_KEY`       | Non pour l'instant | — | Réservée pour une future couche d'authentification/signature. |

### Déployer sur Railway (via GitHub)

1. Pousser le repo sur GitHub (`git remote add origin <url> && git push -u origin main`).
2. Sur [railway.app](https://railway.app) : **New Project → Deploy from GitHub repo**, sélectionner ce repo.
3. Railway détecte le `Dockerfile` à la racine (confirmé par `railway.toml`, builder `DOCKERFILE`) et lance le build automatiquement.
4. Une fois déployé, Railway fournit une URL publique HTTPS/WSS unique — vérifier `/health` pour confirmer que le service tourne.
5. Chaque `git push` sur la branche connectée redéploie automatiquement (CI/CD continu).

### Tester le build de production en local (sans Railway)

```bash
docker build -t legrandtunneg .
docker run -p 8000:8000 legrandtunneg
curl http://127.0.0.1:8000/health
```
