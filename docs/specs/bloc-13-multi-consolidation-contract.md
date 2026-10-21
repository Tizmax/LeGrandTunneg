---
title: "Bloc 13 — Multi consolidation contract"
id: bloc-13-multi-consolidation-contract
type: "technical"
status: active
created: 2026-10-20
---

# Bloc 13 — Multi consolidation contract

## Purpose

Define the requested consolidation boundary for the already playable multiplayer service before persistence work. This is the **reference contract for Bloc 13 consolidation, not a certification of deployment or exhaustive validation**. The supplied pre-consolidation baseline was `c3fdbf6` (66 passing backend tests reported, first milestone committed). The local Bloc 13 delivery and its reported execution evidence are recorded in `docs/validation-bloc-13.md`; that report does not establish a committed or deployed revision. Observed contracts and known gaps come from `docs/websocket-protocol.md`, `docs/validation-jalon-1.md`, `backend/app/api/{rooms,ws}.py`, `backend/app/rooms/manager.py`, the Python engine and the frontend connection/timer components. Preserve complete games for a small Railway group (normally fewer than five rooms); do not rewrite the game.

Bloc 13 defines the pre-persistence consolidation baseline. The draft `postgres-persistence-railway-durability-contract` defines the subsequent target for durable storage, session survival, commit ordering, recovery and archival retention; it does not certify implementation or database validation. During preparation, its explicit persistence changes supersede the historical in-memory lifecycle assumptions below only in the new Postgres code path. Identity, protocol, gameplay and resource protections otherwise remain applicable. Production deployment and durable-validation claims remain gated on real Postgres checks.

## Behavior

### Public identity and private session proof

`localPlayerId` remains the public UUID, including `players[].id`; it never authorizes REST or WebSocket access. Every participant, including an `ecran-principal`, receives a distinct `sessionToken`: 32 cryptographically random bytes encoded as unpadded base64url (43 characters), independent of that UUID. The server retains only its SHA-256 digest, scoped to room and participant, and compares proofs in constant time. The plaintext exists only while processing an individual request/handshake and on the owning client.

- `POST /api/rooms` accepts exactly `{pseudo}` and returns `{code, localPlayerId, role, sessionToken}`, with role `presentateur`.
- New membership uses `POST /api/rooms/{code}/join` with `{pseudo, role?}`; role defaults to `joueur` and permits only `joueur` or `ecran-principal`. Response: `{code, localPlayerId, role, sessionToken, state}`. New players join only in `lobby`; screens may join any live room. REST membership alone leaves `players[].connected` false.
- Resume uses the same join endpoint with exactly `{localPlayerId, sessionToken}` and returns `{code, localPlayerId, role, state}` without issuing or rotating a secret. It accepts an existing live session in any phase, ignores no submitted fields, creates no membership, changes no presence and produces no broadcast. Mixed new/resume fields or a missing half of the proof are invalid payloads. An unknown or invalid proof **never falls through to new membership**.
- Room codes normalize to uppercase. UUIDs must use canonical UUID text; token encoding/length must match the format above. Names are trimmed before nonempty/length checks.
- Successful new membership broadcasts only the updated public state. All create/join responses, including errors, carry `Cache-Control: no-store`. Secrets never enter state DTOs, broadcasts, URLs, query parameters, error text, analytics or application/proxy logs. Request-body and WS-frame logging must exclude proof-bearing messages.

Sessions live for the room's in-memory lifetime, without a separate login or sliding session expiry. Removal revokes the target proof; room closure/expiry revokes all proofs. Transfer changes roles, not proofs. Resume with any unknown/revoked/bad proof in an existing room returns HTTP 401 with `detail: {code: "session_revoked", message: "Session unavailable."}`; it deliberately reveals no revocation history. Missing rooms return 404 `room_not_found`.

### WebSocket handshake and terminal protocol

The URL is `/ws/{code}`, with no identity/proof query parameters; legacy `local_player_id` queries are rejected. Validate the browser `Origin` before upgrade. After upgrade, the first text message must be exactly `{"type":"session:auth","payload":{"localPlayerId":"…","sessionToken":"…"}}`. Complete authentication within 5 seconds measured from acceptance. No attachment, presence change, room state or other room data may precede proof validation. The first successful response is the recipient-specific `room:state_sync`; it serves as authentication acknowledgement. A second `session:auth` is an invalid command.

Within the room lock, verify the room is still live, validate the session and install the socket as the only active socket for that participant. **The last successfully authenticated socket wins.** Invalidate the former socket's authority before any network notification. Successful replacement keeps presence true without an intermediate absent state. Notify/close the former socket as `session_replaced`; its eventual commands, send failures and disconnect cleanup cannot mutate state or detach the new socket.

For terminal conditions, send `{"type":"session:ended","payload":{"code":"session_replaced","message":"Session opened elsewhere."}}` with the applicable code/message below, then close. Sending the notification is best effort; the close code remains authoritative if it cannot be delivered.

| Terminal code | WS close code | Message |
| --- | --- | --- |
| `session_revoked` | 4401 | `Session unavailable.` |
| `player_kicked` | 4403 | `You were removed from the room.` |
| `room_closed` | 4404 | `Room closed or unavailable.` |
| `session_replaced` | 4409 | `Session opened elsewhere.` |

Preserve existing `player:kicked` and `room:closed` events with `{}` payloads for removal/closure, before `session:ended` when delivery succeeds. These events are terminal aliases for clients. Missing/expired rooms map to `room_closed`; invalid/unknown proofs map to `session_revoked`. Malformed first messages close with 1008 (`invalid_payload`); authentication timeout closes with 4408 (`auth_timeout`); excessive resource/rate use closes with 4429 (`rate_limited`); oversized messages close with 1009. Pre-upgrade origin or capacity rejection returns HTTP 403 or 429 respectively, with no room data.

### Authority, ordering and failure isolation

Every command, attachment, REST membership/resume, revocation, presence transition and cleanup serializes against the room lock. Before a command mutates anything, recheck room liveness, live session, **exact active socket object**, current server role, phase and actor eligibility under that lock. Do not authorize using a role captured at handshake. Transfer in the lobby atomically updates `isPresenter`, the role table and presenter identity: the former presenter immediately loses presenter permissions on their existing socket; the new presenter immediately gains them.

Removal in the lobby atomically removes the non-presenter participant, revokes their session and invalidates their socket before any send/close. Closure/expiry first marks the room closed and invalidates all authority, then performs notifications and deletion. Notifications and failed sends cannot roll back revocation. Disconnect/send-failure cleanup only detaches the exact socket still registered for that identity, and only then marks that participant absent. Screens never enter `players`; they cannot rename, change avatar or issue game commands (`forbidden_role`).

Accepted commands publish full recipient-specific `room:state_sync` snapshots with `{code, role, localPlayerId, state}`; roles reflect the same committed state. Snapshot delivery must preserve commit order per socket; repeated equal snapshots are harmless. Rejects never mutate game/session/presence state or broadcast. A slow/dead recipient cannot block other recipients indefinitely. Network sends do not hold the mutation lock; bounded delivery failure invokes identity-safe cleanup.

### Turn eligibility and suspended play

Keep the existing player array/order, score calculations, manual judging, reveal gates, theme rules and terminal case-10 coffrage. The presenter never owns a playable turn, earns points or enters the player ranking. These are conservative technical eligibility choices, not new scoring rules.

Add public DTO fields `turnStatus: "idle" | "ready" | "active-absent" | "waiting-eligible"` and `rotationAnchorIndex: number | null`; change `currentPlayerIndex` to `number | null`. Indexes refer to the full `players` array. `idle` applies in lobby/end, with both indexes null. `ready` has a connected non-presenter current index and null anchor. `active-absent` retains the absent non-presenter's index and has null anchor. `waiting-eligible` has no current index and retains the index of the player whose completed turn triggered rotation as its anchor. No sentinel index may accidentally designate the presenter.

- `game:start` retains the existing requirements of lobby, at least two registered non-presenter players and at least one theme; it additionally requires at least one connected non-presenter. Choose the initial actor randomly **only among connected non-presenters**. Registered absent players do not enter that draw.
- `game:reset` is post-lobby only and requires at least one theme and one connected non-presenter. Otherwise return `invalid_phase` without changing scores, history or any state. A successful reset clears scores/history/progression as before, enters `selection-pending`, and selects the first connected non-presenter in array order, never index zero by default.
- Rotation applies only where existing game rules advance the actor; `answer:pass` retains the current actor, including after automatic coffrage. If an accepted transition completes all themes, enter `end` with `turnStatus: "idle"` and both turn indexes null, without entering `waiting-eligible`.
- A completed turn rotates cyclically from the departing actor to the next connected non-presenter, including that actor after one full cycle if they alone remain eligible. If no actor qualifies, finish that already accepted scoring/transition normally, enter `selection-pending` with `waiting-eligible`, null current index and the departing index as anchor. A later authenticated connection chooses the first eligible actor cyclically after the anchor, clears the anchor and enters `ready`. Mere absence/return never scores.
- Losing the current actor's connection during `selection-pending`, `selection` or any tunnel subphase changes only presence/turnStatus to `active-absent`. Preserve current index, phase, theme, progress, history and subphase: do not skip or finish that turn. Other players reconnecting cannot take it. The same actor's authenticated return restores `ready` and that exact turn/subphase.
- In `active-absent` or `waiting-eligible`, reject `choice:reveal`, `theme:select`, `timer:start` and all `answer:*` with `game_suspended`, without mutation. The current presenter retains `game:end_early`, eligible `game:reset` and `room:quit`. Returning to lobby clears turn metadata while retaining participants/themes and resetting scores/progression as before.

Clients display the suspension reason and disable the corresponding game controls. The existing countdown remains a **local indicative 60-second display**, mounted only in tunnel subphase `question`, keyed by theme index/progress/subphase. A presence-only suspension does not unmount, freeze or restart an already mounted countdown: it may reach zero while play is suspended. Remount/reload/reconnect in `question` starts a fresh local 60-second display. Equal state syncs do not reset a mounted timer. Zero triggers no server command, failure, rotation or coffrage. The presenter still judges explicitly after the actor returns. No synchronized remaining-time or exact elapsed-time guarantee exists.

### Client recovery and deployment compatibility

Store `{version: 2, code, localPlayerId, sessionToken, autoResume}` at `legrandtunneg:identity:v2`; never store a trusted role. Validate the stored shape before use. New membership sets `autoResume: true`. localStorage is an explicit small-service compromise: any same-origin JavaScript/XSS can steal the bearer proof; this is not an account system.

Transient transport failures keep identity and retry authentication with capped exponential backoff and jitter: attempt n starts at 0; draw uniformly between 0.5 and 1 times `min(30000, 500 * 2^n)` milliseconds. Reset n only after a successful state sync. No command queue or command replay exists: disable sending until authenticated, discard unsent actions, and recover only through the latest complete state. Cancel timers and ignore obsolete socket callbacks on unmount, identity change or voluntary disconnect; at most one pending retry exists per client connection controller.

Voluntary disconnect retains proof, persists `autoResume: false`, cancels retry and requires an explicit Resume action (also after reload). Explicit Resume sets it true. `session_replaced` also persists false and retains proof for an explicit takeover; no automatic reconnect tug-of-war between tabs. `session_revoked`, `player_kicked` and `room_closed` erase the usable proof. All terminal statuses stop retries and preserve a visible explanation across subsequent `onclose`/`onerror`; they never collapse into a generic disconnected state. 1008/1009/4429 are non-retrying policy errors requiring explicit user action; 4408 and abnormal network/server failures are transient.

The legacy key `legrandtunneg:identity` never authenticates or silently creates a new membership. On reload show that explicit rejoin is necessary; only a new create/join obtains a proof. Deploy this incompatible protocol in a window with no running game and reload clients. In-memory rooms/sessions still disappear on restart; a missing room terminates recovery, not a claim of durable resumption.

### Strict validation and resource failures

Authenticated text messages must be JSON objects with exactly `type` (known string) and `payload` (object). Reject null, arrays, primitives, invalid JSON, missing/extra keys, coercions and unknown command types with a targeted `error` payload `{code: "invalid_payload", message: "Invalid message."}`. The socket remains usable within message/rate bounds. Never echo malformed input or proofs in errors. Binary frames are invalid payloads within the same size limit.

Per-command payloads are exact: `theme:add` has nonempty trimmed `label`; `theme:remove`, `theme:select`, `player:remove` have in-range nonnegative integer `index` (**not boolean or float**); `player:rename` has trimmed nonempty `name`; `player:set_avatar` has one allowed avatar string; `presenter:transfer` has canonical UUID `targetPlayerId` for an existing non-presenter. All other existing commands in the protocol table require `{}`. Avatar availability and existing phase/role/turn checks still apply; transfer stays lobby-only. Validation precedes any mutation. Preserve `forbidden_role`, `not_your_turn`, `invalid_phase`; add `game_suspended`, `capacity_exceeded` and `rate_limited` as targeted error codes.

REST bodies use the same strict types, no extra fields/coercion, and an 8 KiB raw-body limit. HTTP errors use `detail: {code, message}`: 422 `invalid_payload`, 401 `session_revoked`, 404 `room_not_found`, 409 `invalid_phase` or `capacity_exceeded`, 429 `rate_limited` with `Retry-After`, 413 `payload_too_large`; room-count or body-reader capacity exhaustion is 503 `capacity_exceeded`; expiration of the absolute body-read deadline is 408 `request_timeout`. All create/join responses, including these errors, carry `Cache-Control: no-store`. Rejected requests create no partial room, session or player. Resume/replacement of existing sessions does not consume a new membership slot.

## Constraints

This stage uses one process and one authoritative in-memory room manager. Multiple workers/replicas and restart survival are unsupported. All limits below are configurable positive finite values validated at startup; malformed/zero/unbounded settings fail startup. Defaults are intentionally above the expected fewer-than-five-room usage.

| Setting | Default / enforced scope |
| --- | --- |
| `MAX_ROOMS` | 10 live rooms; admissions atomic process-wide |
| `MAX_PLAYERS` | 16 per room including presenter, connected or absent; cannot exceed the existing 16-avatar pool |
| `MAX_SCREENS` | 4 screen memberships per room, connected or absent |
| `MAX_THEMES` | 32 per room |
| `MAX_NAME_CHARS` / `MAX_THEME_LABEL_CHARS` | 24 / 100 Unicode code points after trim |
| `MAX_MESSAGE_BYTES` | 8192 UTF-8 bytes per complete WS message, including auth; transport enforces before JSON decoding |
| `MAX_REST_BODY_BYTES` | 8192 before JSON decoding |
| `REST_BODY_TIMEOUT_SECONDS` / `MAX_REST_BODY_READERS` | 5 / 32; absolute body-read deadline and process-wide concurrent body-reader capacity shared by create, join and resume |
| `AUTH_TIMEOUT_SECONDS` / `MAX_PREAUTH_CONNECTIONS` | 5 / 32 process-wide; release reservations on every exit |
| `MAX_AUTHENTICATED_CONNECTIONS` | 200 process-wide, counting replaced sockets until closed; replacements remain bounded |
| `SEND_TIMEOUT_SECONDS` | 2 per recipient send or close; no unbounded delivery queues |
| `ROOM_IDLE_TTL_SECONDS` | 86400 continuously without any authenticated connection |
| `ROOM_CLEANUP_INTERVAL_SECONDS` | 60; positive and no greater than TTL |
| `REST_RATE_PER_SECOND` / `REST_RATE_BURST` | 5 / 20 process-wide, shared across create and join including resume |
| `WS_UPGRADE_RATE_PER_SECOND` / `WS_UPGRADE_RATE_BURST` | 10 / 20 process-wide, before upgrade/auth work |
| `WS_COMMAND_RATE_PER_SECOND` / `WS_COMMAND_RATE_BURST` | 20 / 40 per authenticated socket, including invalid commands |
| `WS_GLOBAL_RATE_PER_SECOND` / `WS_GLOBAL_RATE_BURST` | 200 / 400 across all authenticated commands |

After REST rate admission, reserve a body-reader slot immediately without waiting or a queue. Saturation returns HTTP 503 `capacity_exceeded` with message `Body reader capacity exceeded.`. A monotonic absolute deadline starts at reader admission and bounds the entire body read; chunks never renew it. Expiration returns HTTP 408 `request_timeout` with message `Request body timed out.`. Release the slot in `finally` on success, timeout, cancellation, oversize input, invalid JSON, disconnect or read failure. Keep the raw-byte limit before decoding; do not assume a proxy timeout. Regression tests cover incomplete/slow streams, saturation, all release paths and subsequent normal admission.

Rate limits use monotonic token buckets initially full; no sleeping request backlog. WS command overflow sends targeted `rate_limited` then closes 4429; rejected REST/upgrade requests use 429. Process-global admission/rate bounds do not trust IP headers and require no unbounded per-IP map. Do not treat arbitrary `X-Forwarded-For`/`Forwarded` values as Railway client identities. Only explicitly configured trusted proxy hops may supply forwarded scheme/client metadata; these defaults remain effective even when every request appears to share one proxy IP.

- TTL starts at creation if no socket authenticates, or at loss of the last authenticated socket (players, presenter **or screens** count). REST requests, preauth traffic and rejected proofs do not refresh it. Authentication before expiry cancels the idle interval; authentication at/after expiry fails even between sweeps. Use monotonic elapsed time. Each sweep revokes/deletes expired rooms; cancel/await the periodic task at application shutdown. State records cannot accumulate beyond live room/membership/theme bounds; do not retain unbounded revoked-session tombstones or delivery queues.
- `ALLOWED_ORIGINS` is the shared exact CORS/WS origin allowlist: scheme, hostname and port, no wildcard, suffix matching or path. Local development default: `http://localhost:5173,http://127.0.0.1:5173`. Production (`APP_ENV=production`) requires an explicit nonempty HTTPS origin list, for example the deployed Railway public origin; fail startup for missing/invalid configuration. Reject missing, literal `null`, duplicate or nonlisted WS Origin headers before upgrade. There is no browser Origin exemption, including same-host traffic. Origin checks complement, never replace session proof; non-browser callers can forge Origin.
- Static delivery resolves root and candidate paths, including symlinks, before serving any file. Only descendants of the resolved static root qualify; traversal or symlink escape returns 404, never a file or SPA fallback. Apply the same confinement to index/assets. Unknown `/api` and `/ws` paths (exact prefix segment and descendants), and unknown `/health` descendants, return 404, not SPA HTML. Safe unknown frontend paths may return the confined `index.html`.
- Required regression evidence includes public-UUID impersonation rejected on REST/WS; no state before auth; live permissions after transfer; removal/reconnect revoked; old-socket command/disconnect/send-failure unable to affect replacement; reset/rotation excluding presenter; no-eligible anchor recovery; active loss/return in every tunnel subphase; no countdown-triggered mutation; malformed payload followed by a valid command on the same socket; capacity/rate/auth/send timeout/TTL boundaries; exact Origin refusals; traversal, symlink escape and reserved-route fallback refusals. Preserve the complete-game scoring scenario (1 then 22 points, presenter zero) as well as lint/build and existing tests. This spec claims no execution of that evidence.

## Examples

With origin `https://tunneg.up.railway.app` configured, Alice opens `/ws/ABCD` and sends `{"type":"session:auth","payload":{"localPlayerId":"ecaa8b4a-762f-4dc2-8b3c-f270f512a45f","sessionToken":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"}}`. The token is a format-only fixture representing bytes 0–31, never a production credential. If its stored digest matches, Alice receives a state sync; knowing Alice's public UUID without this proof yields 4401 and no state. Resuming with REST `{ "localPlayerId": "ecaa8b4a-762f-4dc2-8b3c-f270f512a45f" }` yields 422 and never creates Alice again.

In array order Paul (presenter, connected), Alice (absent), Bob (connected), reset chooses Bob at index 2. If Bob disconnects during `question`, the DTO retains index 2 and subphase `question`, with `turnStatus: "active-absent"`. Paul's `answer:good` returns `game_suspended`; zero on Paul's local countdown changes nothing. Bob's return restores `ready`; Paul can then judge explicitly. If Bob later finishes a turn while all other players are absent, Bob remains the next eligible player after a full cycle.

Socket A authenticates, then socket B authenticates with the same valid proof. B becomes active; A receives close 4409 and stops automatic retries. A's delayed disconnect cannot set B absent. After a lobby transfer from Paul to Alice, Paul's already-open socket receives `forbidden_role` for `theme:add`; Alice's already-open socket can add `{"type":"theme:add","payload":{"label":"Cinema"}}`. Sending `{"type":"theme:remove","payload":{"index":true}}` instead returns `invalid_payload`, does not broadcast and leaves the connection usable.

## Rationale

Separate public identity from bearer authority and serialize authority with mutations to address the confirmed high-severity session flaws without introducing accounts. Explicit suspension avoids silently inventing absence penalties, automatic coffrage or timer adjudication. Global bounds suit one small Railway service without assuming trustworthy forwarded client IPs. `docs/websocket-protocol.md` describes the incompatible Bloc 13 protocol. This specification defines its required guarantees; execution evidence and its limits are recorded separately in `docs/validation-bloc-13.md` and do not establish remote delivery.

## Non-goals

No accounts, Postgres, durable sessions/game saves, cross-process coordination, solo/hotseat work, historical profiles, theme/question/indicative-answer library, new scoring, automatic absence resolution, or authoritative/durable server clock. Stabilization precedes persistence; library enrichment remains later. Specification activation does not authorize a commit, push, deployment, plan edit or remote configuration change.