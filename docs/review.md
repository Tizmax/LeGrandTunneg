# Code Review — Le Grand Tunneg

> Généré le 2026-10-11. Scope : backend Python, frontend TypeScript/React, infra Docker/Railway.  
> Sévérité : **critique** › **majeur** › **mineur**

---

## Sommaire

| Catégorie | Critique | Majeur | Mineur |
|-----------|----------|--------|--------|
| Bugs logiques | 2 | 7 | 4 |
| Sécurité | 2 | 4 | 5 |
| Pratiques / qualité | 1 | 6 | 10 |
| Tests | — | 1 | 4 |
| **Total** | **5** | **18** | **23** |

---

## 1. Bugs — Backend

### [CRITIQUE] `assert` utilisé comme garde runtime en production
**Fichier :** `backend/app/game/engine.py` — lignes 286 et 336  
**Problème :** `assert idx is not None` dans `good_answer` et `pass_question`. Les assertions sont silencieusement supprimées avec `python -O`. En production, cela provoque un `TypeError: 'NoneType' object is not subscriptable` non capturé, renvoyé en 500 et déconnectant le joueur.  
**Fix :**
```python
if idx is None:
    raise GameError("invalid_phase", "Aucun thème actif.")
```

---

### [CRITIQUE] `websocket.accept()` appelé APRÈS les retours anticipés
**Fichier :** `backend/app/api/ws.py` — lignes 170–179  
**Problème :** Les `websocket.close(...)` + `return` sur les erreurs `attach_connection` ont lieu avant que `accept()` ait été appelé. Le handshake n'est jamais complété ; le close frame est sans effet ; la connexion est simplement droppée sans raison lisible côté client.  
**Fix :** Appeler `await websocket.accept()` en tout premier dans le handler, avant toute logique métier :
```python
async def websocket_endpoint(...) -> None:
    await websocket.accept()
    code = code.upper()
    try:
        room = room_manager.attach_connection(code, local_player_id, websocket)
    except RoomNotFoundError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="room_not_found")
        return
    except UnknownParticipantError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="unknown_participant")
        return
```

---

### [MAJEUR] Race condition : `broadcast_state` depuis REST sans lock
**Fichiers :** `backend/app/rooms/manager.py` lignes 177–211 ; `backend/app/api/rooms.py` ligne 78  
**Problème :** `broadcast_state` est appelé depuis la route REST après `join_room` sans tenir le `room.lock`. Un handler WS concurrent peut muter `room.state` entre le `join_room` et le `broadcast_state`, envoyant un état périmé ou partiel.  
**Fix :** Acquérir `room.lock` autour du couple join + broadcast dans la route REST :
```python
async with room.lock:
    room = await room_manager.join_room(...)
    await room_manager.broadcast_state(code)
```

---

### [MAJEUR] Race condition : double-ajout de joueur via POST concurrent
**Fichier :** `backend/app/rooms/manager.py` — lignes 102–136  
**Problème :** `join_room` mute `room.state` (via `engine.add_player`) sans tenir `room.lock`. Deux `POST /api/rooms/{code}/join` simultanés partent du même `room.state`, l'un des deux joueurs est silencieusement perdu (last-write-wins).  
**Fix :** Rendre `join_room` async et acquérir `room.lock` autour de la mutation d'état.

---

### [MAJEUR] `_h_theme_add` : crash si `label` n'est pas une string
**Fichier :** `backend/app/api/ws.py` — ligne 78  
**Problème :** `payload.get("label", "")` passe directement à l'engine. Si le client envoie `{"label": 42}`, `engine.add_theme` appelle `.strip()` sur un entier → `AttributeError` non capturé → déconnexion du joueur.  
**Fix :** Valider le type avant dispatch :
```python
label = payload.get("label", "")
if not isinstance(label, str):
    raise engine.GameError("invalid_payload", "label doit être une chaîne.")
```

---

### [MAJEUR] `payload` non-dict accepté silencieusement
**Fichier :** `backend/app/api/ws.py` — ligne 207  
**Problème :** `payload = message.get("payload") or {}`. Si `payload` est une string truthy (ex. `"surprise"`), l'expression retourne la string. L'appel à `.get("label", "")` dessus lève `AttributeError`.  
**Fix :**
```python
payload = message.get("payload")
if not isinstance(payload, dict):
    payload = {}
```

---

### [MAJEUR] `_require_int` accepte les booléens
**Fichier :** `backend/app/api/ws.py` — ligne 134  
**Problème :** `isinstance(True, int) == True` en Python. Un client envoyant `{"index": true}` est accepté comme `index=1`.  
**Fix :**
```python
if isinstance(value, bool) or not isinstance(value, int):
    raise engine.GameError("invalid_payload", f"{key} doit être un entier.")
```

---

### [MAJEUR] `_record_coffrage` : annotation de retour incorrecte
**Fichier :** `backend/app/game/engine.py` — lignes 98–112  
**Problème :** La fonction est annotée `-> tuple[Player, ...]` mais retourne `tuple[HistoryEntry, ...]`. Trompe le type-checker et les futurs contributeurs.  
**Fix :**
```python
def _record_coffrage(...) -> tuple[HistoryEntry, ...]:
```

---

### [CRITIQUE] `coffrer()` frontend ne met jamais `completed: true`
**Fichier :** `frontend/src/game/rules.ts` — lignes 41–53  
**Problème :** `coffrer` avance `validatedSquares` mais ne pose jamais `completed: true`. Après un coffrage volontaire du joueur, `allThemesCompleted()` ne retourne jamais `true` → la partie ne peut pas se terminer via un coffrage manuel dans le reducer local (utilisé par StyleguideScreen et future mode solo).  
**Fix :**
```ts
return {
  theme: { ...theme, validatedSquares, completed: true },
  pointsGained,
}
```

---

### [MINEUR] `reset_game` vs `end_game_early` : phases asymétriques non documentées
**Fichier :** `backend/app/game/engine.py` — lignes 471–482  
**Problème :** `reset_game` → `selection-pending` (bypasse le lobby), `end_game_early` → `lobby`. Deux comportements différents avec des corps quasi-identiques, sans docstring ni commentaire expliquant l'intentionnalité.  
**Fix :** Ajouter des docstrings explicites sur les deux fonctions.

---

### [MINEUR] `_next_player_index` non implémenté dans le reducer frontend
**Fichier :** `frontend/src/game/gameReducer.ts`  
**Problème :** Le reducer local utilise `(current + 1) % count` sans sauter les joueurs déconnectés, contrairement à `engine.py`. Si le mode solo (Bloc 7bis) utilise ce reducer, les joueurs déconnectés ne seront pas sautés.  
**Fix :** Porter `_next_player_index` depuis `engine.py` dans le reducer frontend.

---

### [MINEUR] `CountdownTimer` : drift progressif avec `setTimeout` chaîné
**Fichier :** `frontend/src/components/CountdownTimer.tsx` — lignes 22–26  
**Problème :** Enchaîner des `setTimeout(…, 1000)` accumule un drift JS. Sur 60s, le timer peut retarder de plusieurs secondes.  
**Fix :** Utiliser une référence `startTime` et calculer depuis `Date.now()` :
```ts
useEffect(() => {
  const start = Date.now()
  const id = setInterval(() => {
    const remaining = Math.max(0, Math.ceil((durationSeconds * 1000 - (Date.now() - start)) / 1000))
    setSeconds(remaining)
    if (remaining <= 0) clearInterval(id)
  }, 250)
  return () => clearInterval(id)
}, [durationSeconds])
```

---

### [MINEUR] `Tunnel.tsx` : détection de changement sur `.nullified.length` uniquement
**Fichier :** `frontend/src/components/Tunnel.tsx` — ligne 32  
**Problème :** Si une case nullifiée changeait sans changer la longueur (même longueur, case différente), l'animation ne se déclencherait pas.  
**Fix :**
```ts
}, [theme.progressValue, theme.validatedSquares, theme.discovered, theme.nullified.join(',')])
```

---

### [MINEUR] `CurtainClose.tsx` : `onDone` inline recréé à chaque render relance le timer
**Fichier :** `frontend/src/components/decor/CurtainClose.tsx` — lignes 23–26 ; `frontend/src/App.tsx` — ligne 218  
**Problème :** `onDone={() => setClosing(false)}` est recréé à chaque render de `App`. Le `useEffect` qui en dépend repart, annulant et relançant le timeout de fermeture de rideau si un `state_sync` arrive pendant l'animation.  
**Fix :** Utiliser un `useRef` pour stabiliser le callback :
```ts
const stableOnDone = useRef(onDone)
useEffect(() => { stableOnDone.current = onDone })
useEffect(() => {
  const timer = setTimeout(() => stableOnDone.current(), CLOSE_DURATION * 1000 + HOLD_MS)
  return () => clearTimeout(timer)
}, []) // pas de dep sur onDone
```

---

## 2. Sécurité

### [CRITIQUE] CORS wildcard en production
**Fichier :** `backend/app/main.py` — lignes 30–42  
**Problème :** `ALLOWED_ORIGINS` vaut `"*"` par défaut. En production sur Railway, n'importe quelle page tiers peut faire des requêtes cross-origin vers `/api/rooms` et rejoindre/créer des rooms au nom d'un visiteur.  
**Fix :** Supprimer le fallback `"*"`. Lever une erreur au démarrage si la variable n'est pas définie :
```python
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS")
if not _allowed_origins_env:
    raise RuntimeError("ALLOWED_ORIGINS doit être défini en production")
```

---

### [CRITIQUE] `local_player_id` comme seul credential — usurpation d'identité
**Fichiers :** `backend/app/api/ws.py` ligne 168 ; `frontend/src/net/useRoomConnection.ts` ligne 85  
**Problème :** L'UUID stocké en localStorage est le seul proof d'identité. Il transite en query param (visible dans les logs serveur, l'historique du navigateur, les proxies). Quiconque l'observe peut se connecter en WS comme la victime, y compris avec le rôle `presentateur`.  
**Fix :** Émettre un token signé (HMAC ou JWT) au moment du join, l'échanger dans le premier message WS (pas en query param). Ne jamais exposer l'UUID stable comme bearer credential.

---

### [MAJEUR] Pas de rate limiting sur la création de rooms — épuisement mémoire
**Fichiers :** `backend/app/api/rooms.py` ; `backend/app/rooms/manager.py`  
**Problème :** Aucun rate limit sur `POST /api/rooms`. Pas de plafond global de rooms. Un attaquant peut saturer la mémoire du processus en quelques secondes.  
**Fix :**
- Limiter le nombre de rooms global (ex. 500).
- Rate-limiter par IP avec `slowapi`.
- Expirer les rooms sans connexion après N minutes (TTL).

---

### [MAJEUR] Pas de rate limiting sur la boucle WebSocket — DoS
**Fichier :** `backend/app/api/ws.py` — lignes 204–253  
**Problème :** Aucun throttle sur les messages WS. Pas de limite sur la taille des payloads. Un joueur connecté peut saturer la boucle asyncio ou injecter des labels de taille arbitraire.  
**Fix :**
- Token bucket par connexion (~30 msg/s).
- `max_length` sur les labels dans `engine.add_theme` (≤100 chars).
- Limiter la taille des frames uvicorn.

---

### [MAJEUR] Traversée de chemin dans le fallback SPA
**Fichier :** `backend/app/main.py` — lignes 66–77  
**Problème :** `candidate = _STATIC_DIR / full_path` sans `.resolve()` ni vérification de confinement. Un path `../../etc/passwd` peut sortir du répertoire static.  
**Fix :**
```python
candidate = (_STATIC_DIR / full_path).resolve()
if full_path and candidate.is_file() and candidate.is_relative_to(_STATIC_DIR):
    return FileResponse(candidate)
```

---

### [MAJEUR] Reconnexion par UUID sans vérification — prise de contrôle de session
**Fichier :** `backend/app/api/rooms.py` — lignes 60–65  
**Problème :** `POST /api/rooms/{code}/join` avec un `localPlayerId` existant → retourne le rôle de ce participant sans aucune preuve supplémentaire. Brute-force du code (4 chars = 923K combos) + UUID → accès présentateur.  
**Fix :** La reconnexion doit exiger un token signé côté serveur, pas seulement posséder l'UUID.

---

### [MAJEUR] Pas de plafond joueurs/thèmes — croissance mémoire non bornée
**Fichier :** `backend/app/game/engine.py` — `add_player` et `add_theme`  
**Problème :** Aucune limite sur le nombre de joueurs ou de thèmes. Un présentateur peut spammer `theme:add` ; les broadcasts sont O(N²).  
**Fix :**
```python
MAX_PLAYERS = 20
MAX_THEMES = 20
if len(state.players) >= MAX_PLAYERS:
    raise GameError("invalid_payload", "Nombre maximum de joueurs atteint.")
```

---

### [MINEUR] Le container Docker tourne en root
**Fichier :** `Dockerfile`  
**Problème :** Aucune instruction `USER`. Toute RCE dans l'app donne root dans le container.  
**Fix :**
```dockerfile
RUN addgroup --system app && adduser --system --ingroup app app
USER app
```

---

### [MINEUR] `player:rename` non limité en longueur côté serveur
**Fichier :** `backend/app/api/ws.py` — lignes 221–237  
**Problème :** Le nom envoyé via WS n'a pas de `max_length` serveur, contrairement au pseudo HTTP (limité à 24). Un participant peut injecter un nom très long dans tous les `state_sync`.  
**Fix :** Ajouter dans `engine.rename_player` et `manager.rename_participant` :
```python
if len(name) > 24:
    raise GameError("invalid_payload", "Nom trop long.")
```

---

### [MINEUR] Dépendances Python non pinnées — risque supply-chain
**Fichier :** `backend/requirements.txt`  
**Problème :** Aucun fichier verrouilé. Chaque build peut importer une version cassante ou compromise. `pytest`/`pytest-asyncio`/`httpx` sont installés en production.  
**Fix :**
- Générer `requirements.lock` avec `pip-compile` ou `uv lock`.
- Séparer `requirements-dev.txt` pour les outils de test.
- N'installer que les dépendances runtime dans le `Dockerfile`.

---

### [MINEUR] Code de room 4 caractères — énumérable sans rate limit
**Fichier :** `backend/app/rooms/manager.py` — ligne 34  
**Problème :** 923 521 combinaisons possibles. Sans rate limit sur `/join`, enumération triviale.  
**Fix :** Passer à 6 caractères (~887M combos) + rate limit sur les tentatives de join.

---

### [MINEUR] `SECRET_KEY` documenté mais jamais chargé ni validé
**Fichier :** `backend/.env.example` ligne 10 ; `backend/app/main.py` (absent)  
**Fix :** Ajouter au démarrage :
```python
secret = os.environ.get("SECRET_KEY", "")
if secret in ("", "change-me-dev-secret-key"):
    warnings.warn("SECRET_KEY non défini ou valeur exemple")
```

---

## 3. Qualité & pratiques

### [MAJEUR] `window.confirm()` bloquant dans `GameControls`
**Fichier :** `frontend/src/components/GameControls.tsx` — lignes 31, 43  
**Problème :** Synchrone, bloque l'event loop, style OS, ne correspond pas à l'esthétique du jeu, comportement variable selon les navigateurs (Safari supprime les dialogues répétés).  
**Fix :** Remplacer par un panneau de confirmation inline ou une modal React.

---

### [MAJEUR] `useRoomConnection` : messages droppés silencieusement
**Fichier :** `frontend/src/net/useRoomConnection.ts` — lignes 138–142  
**Problème :** Si le socket est en `CONNECTING` ou `CLOSING`, `send()` retourne sans rien faire. L'action de l'utilisateur est perdue sans feedback.  
**Fix :** Logger au minimum : `console.warn('[WS] Message dropped, socket not open:', message)`. Idéalement : file d'attente + flush à l'ouverture.

---

### [MAJEUR] `clearStoredIdentity` appelé deux fois sur `room:closed` — ownership splitté
**Fichiers :** `frontend/src/net/useRoomConnection.ts` ligne 115 ; `frontend/src/App.tsx` lignes 120–121  
**Problème :** Le hook gère `localStorage` ET `App.tsx` aussi, sur les mêmes événements. Ownership incohérent.  
**Fix :** Retirer `clearStoredIdentity()` du hook ; `App.tsx` est le seul propriétaire du localStorage.

---

### [MAJEUR] `LobbyScreen` : `index` comme `key` sur une liste mutable
**Fichier :** `frontend/src/screens/LobbyScreen.tsx` — ligne 207 (idem `RoomOverview.tsx` ligne 21, `SelectionScreen.tsx` lignes 107/115)  
**Problème :** React produit une réconciliation incorrecte si les thèmes sont supprimés (ex. supprimer le 1er rekey tous les suivants). Problèmes d'animation et d'état local.  
**Fix :** Utiliser `theme.label` comme key (ou ajouter un `id` au type `Theme`) :
```tsx
<li key={theme.label} ...>
```

---

### [MAJEUR] `EndScreen` : `key` sur `player.name` non unique
**Fichier :** `frontend/src/screens/EndScreen.tsx` — ligne 63  
**Problème :** Deux joueurs avec le même nom (le serveur ne l'interdit pas) → warning React + animations incorrectes.  
**Fix :** Utiliser `player.id` comme key.

---

### [MAJEUR] `handleLeave` recréé à chaque render, défini sous un return conditionnel
**Fichier :** `frontend/src/App.tsx` — lignes 168–172  
**Problème :** Pas de `useCallback`. Nouveau référence passée à `GameControls` à chaque render → re-render inutile. Placement sous le `ConnectingScreen` early-return rend le code fragile à toute réorganisation.  
**Fix :**
```ts
const handleLeave = useCallback(() => {
  connection.disconnect()
  clearStoredIdentity()
  setSession({ identity: null, connectError: null })
}, [connection])
```

---

### [MAJEUR] `AccueilScreen` : état `error` non synchronisé avec la prop
**Fichier :** `frontend/src/screens/AccueilScreen.tsx` — ligne 31  
**Problème :** `useState(initialError)` seede l'état une seule fois au mount. Si le parent re-render avec une nouvelle `initialError`, l'erreur affichée est périmée.  
**Fix :** `useEffect` de synchronisation, ou forcer un re-mount avec `key={initialError ?? 'none'}` au site d'appel.

---

### [MINEUR] `isStyleguide` recalculé à chaque render
**Fichier :** `frontend/src/App.tsx` — lignes 89–91  
**Fix :** Sortir du composant comme constante module-level :
```ts
const IS_STYLEGUIDE = new URLSearchParams(window.location.search).get('debug') === 'styleguide'
```

---

### [MINEUR] `renderScreen` est une fonction, pas un composant React
**Fichier :** `frontend/src/App.tsx` — lignes 22–66  
**Problème :** Pas de boundary d'erreur, pas de `displayName` dans les DevTools. Impossible d'y utiliser des hooks à l'avenir.  
**Fix :** Convertir en composant `<RenderScreen .../>` ou inliner le switch directement dans le JSX de `App`.

---

### [MINEUR] `main.tsx` : assertion non-null sans message d'erreur utile
**Fichier :** `frontend/src/main.tsx` — ligne 6  
**Fix :**
```ts
const root = document.getElementById('root')
if (!root) throw new Error('Root element #root not found in DOM')
createRoot(root).render(...)
```

---

### [MINEUR] `_generate_unique_code` utilise `random` au lieu de `secrets`
**Fichier :** `backend/app/rooms/manager.py` — ligne 77  
**Fix :**
```python
import secrets
code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
```

---

### [MINEUR] `_broadcast_closed` re-lookup la room inutilement
**Fichier :** `backend/app/api/ws.py` — lignes 59–66  
**Fix :** Passer l'objet `room` directement en paramètre au lieu de faire `get_room(code)`.

---

### [MINEUR] `quit_to_menu` : retour discardé silencieusement
**Fichier :** `backend/app/api/ws.py` — lignes 212–213  
**Fix :** Assigner à `_` avec un commentaire : `_ = engine.quit_to_menu(...)  # room fermée immédiatement`.

---

### [MINEUR] `prefers-reduced-motion` incomplet
**Fichier :** `frontend/src/index.css` — lignes 297–305  
**Problème :** Manquent : `animate-rise-up`, `animate-screen-fade`, `animate-square-ignite`, `animate-blink-red`, `sweep-across`. Les animations Framer Motion ne sont pas couvertes.  
**Fix :**
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```
Pour Framer Motion : utiliser `useReducedMotion()` dans les composants animés.

---

### [MINEUR] Accessibilité : onglets sans ARIA, inputs sans label
**Fichiers :** `frontend/src/screens/AccueilScreen.tsx` lignes 83–125  
**Problème :** Les boutons mode (Créer/Rejoindre) sont des `<button>` sans `role="tab"` ni `aria-selected`. Les `<input>` n'ont que `placeholder` comme identification.  
**Fix :**
```tsx
<div role="tablist">
  <button role="tab" aria-selected={mode === 'create'}>Créer une room</button>
  <button role="tab" aria-selected={mode === 'join'}>Rejoindre</button>
</div>
// Sur chaque input :
<input aria-label="Votre pseudo" ... />
```

---

### [MINEUR] `SelectionScreen` : carte non-interactive sans sémantique disabled
**Fichier :** `frontend/src/screens/SelectionScreen.tsx` — lignes 105–118  
**Problème :** Les cartes non-interactives sont des `<div>` sans `role="button"` ni `aria-disabled`.  
**Fix :** Toujours rendre un `<button disabled>` ou ajouter `aria-disabled="true" role="button"`.

---

## 4. Tests

### [MAJEUR] Aucun test frontend
**Problème :** Pas de Vitest / Jest / testing-library. La logique complexe dans `rules.ts` et `gameReducer.ts` (scoring, auto-coffrage, transitions d'état) n'est pas couverte. Le bug `coffrer/completed` ci-dessus n'aurait pas été découvert avec des tests.  
**Fix :** Ajouter Vitest + testing-library. Priorité : `rules.ts` (fonctions pures, facile à tester), `gameReducer.ts`.

---

### [MINEUR] Isolation des tests via `_reset_rooms()` manuelle — fragile
**Fichier :** `backend/tests/test_rooms_integration.py` — ligne 24  
**Problème :** Si un test crash avant le reset, les suivants héritent d'un état souillé.  
**Fix :**
```python
@pytest.fixture(autouse=True)
def reset_rooms():
    room_manager._rooms.clear()
    yield
    room_manager._rooms.clear()
```

---

### [MINEUR] Pas de test pour `pass_question` à `progress_value == 9`
**Fichier :** `backend/tests/test_game_engine.py`  
**Problème :** Cas limite : passer quand le thème est en case 9 → la case 10 est nullifiée avant l'auto-coffrage. Non testé.

---

### [MINEUR] Pas de test pour `room:quit` (fermeture de toutes les connexions)
**Fichier :** `backend/tests/test_rooms_integration.py`  
**Problème :** Le message `room:quit` et la diffusion de `room:closed` ne sont pas couverts en intégration.

---

### [MINEUR] Test de reconnexion trop superficiel
**Fichier :** `backend/tests/test_rooms_integration.py` — lignes 174–194  
**Problème :** Vérifie uniquement la présence du message `room:state_sync` et le `localPlayerId`. Ne vérifie pas que le contenu de l'état est cohérent après reconnexion.

---

## 5. Aucun CI/CD

**Problème :** Pas de GitHub Actions ni aucun pipeline. Le linter (`oxlint`), le type-checker (`tsc`), et les tests (`pytest`) ne tournent jamais automatiquement.  
**Fix :** Ajouter `.github/workflows/ci.yml` avec :
- `pip install -r requirements.txt && pytest`
- `npm run lint && npm run build` (ou `tsc -b && oxlint`)
- Déclenchement sur `push` et `pull_request`.
