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

## Déploiement

Le déploiement cible (Railway, service unique servant l'API/WebSocket et le
build statique du frontend) sera documenté en détail au Bloc 11 du plan
d'exécution. Cette section sera complétée à ce moment-là.
