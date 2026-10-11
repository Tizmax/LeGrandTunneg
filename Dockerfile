# syntax=docker/dockerfile:1

# --- Étape 1 : build du frontend (bundle statique React/Vite) --------------
FROM node:22-slim AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# --- Étape 2 : image finale (backend FastAPI + frontend statique) ---------
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

# Le frontend buildé est copié dans app/static : main.py le sert en fallback
# SPA (voir backend/app/main.py, section "Service du frontend statique").
COPY --from=frontend-build /app/frontend/dist ./app/static

# Railway (et la plupart des PaaS) injectent PORT dynamiquement ; 8000 sert
# de valeur par défaut pour un `docker run` local sans variable d'env.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
