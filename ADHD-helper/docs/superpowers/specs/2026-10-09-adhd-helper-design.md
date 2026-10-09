# ADHD Helper: native task app with a Claude assistant

Working name **ADHD Helper** (rename any time; the package id is set once, see Open questions).

## Goal

A personal, single-user task app for someone with ADHD who gets distracted and forgets things.
Two jobs, in priority order:

1. **Capture fast**, before the thought is gone: one tap to add a task, or say it to the assistant
   in plain words.
2. **Pull the user back**: reminders that fire on time on the phone, even offline, and keep
   nudging until handled.

Looks and works like Google Tasks, plus an assistant chat that also acts as a notes-to-self inbox.

### Success criteria

- A task with a time set on the PC rings on the phone at that time (phone synced at least once
  after the task was made; see Sync timing).
- Adding a task works with no network, on both devices; it syncs later with no loss or duplicates.
- "remind me to call mom tomorrow 6pm" in chat produces a task in the right list with the right
  due time, visible on both devices.
- Reachable from anywhere the phone has Tailscale on; unreachable from the public internet.

## Decisions (agreed in brainstorming)

| Topic | Decision |
|---|---|
| Users | One user. No sharing, no chat with other people. |
| Clients | **Native** Android app and **native** Linux desktop app (this PC). No WebView, no web UI. |
| Stack | **Kotlin everywhere**: Compose Multiplatform clients (Android + desktop JVM) and a Ktor server. Shared models and sync code. |
| Server | Docker container on **archbox**. SQLite. |
| Remote access | Personal tailnet through the existing `~/stacks/media` node (`media-tailscale` + `media-caddy`), at `https://tasks.sagunkayastha.com`. Same pattern as `tmls`. Never the host's employer tailnet. |
| Assistant | Claude via the `claude` CLI on the user's subscription (`CLAUDE_CODE_OAUTH_TOKEN`), as in fin. Runs on the server. Tools exposed through MCP served by the Ktor server itself. |
| Notes-to-self | The chat is also the inbox. Anything not a clear task is kept as a note. |

## Decisions made by default (override at spec review)

- **Google Tasks parity for v1:** multiple lists; task title + details; due date with optional
  time; repeat (daily / weekly on chosen days / monthly / yearly, every N); one level of subtasks;
  star; complete (collapsed "Completed" section); drag to reorder; "Starred" view.
- **ADHD extras in v1:**
  - Notification actions: **Done**, **Snooze 10 min**, **Snooze 1 h**, **Tomorrow 9am**.
  - **Nag:** an unhandled reminder re-alerts every 10 min, up to 3 times (setting; on by default).
  - **Quick add** from anywhere on Android: app shortcut "New task", share-to-app (shared text
    becomes a task), and a Quick Settings tile. Voice input comes from the keyboard's mic.
- **Assistant model:** `claude-sonnet-5-5` default, switchable in settings (Haiku for speed,
  Opus for hard asks). Max 8 tool turns per message.
- **Chat offline:** messages queue on the device and send when the server is reachable; the
  queued message is already saved as a note, so nothing is lost if the assistant never runs.
- **Desktop app:** lives in the system tray, shows desktop notifications via `notify-send`,
  fires reminders only while running. Optional autostart entry.
- **No Firebase / Google push.** Phone reminders are local alarms; sync runs on app open, on
  every local change, every 15 min in the background (WorkManager), and live while open.

## Out of scope for v1

Home-screen widget, Wear OS, calendar view, location reminders, attachments, sharing,
Play Store, iOS, Windows/macOS builds, web UI, proactive assistant messages (e.g. morning
summary), push from server to a closed app. Widget and morning summary are the first
candidates for v1.1.

## Architecture

```
 Android phone                 Linux PC                       archbox (Docker)
┌─────────────────┐       ┌─────────────────┐       ┌──────────────────────────────┐
│ Compose UI      │       │ Compose UI      │       │ tasks-server (Ktor, JVM 21)  │
│ shared module:  │       │ shared module:  │ HTTPS │  /api/v1  sync, chat, pair   │
│  models, sync,  │◄─────►│  models, sync,  │◄─────►│  /mcp     task tools (MCP)   │
│  local SQLite   │       │  local SQLite   │       │  SQLite /data/tasks.db       │
│ AlarmManager    │       │ notify-send     │       │  claude CLI subprocess ──────┼─► Anthropic
│ WorkManager     │       │ tray            │       └──────────────┬───────────────┘
└─────────────────┘       └─────────────────┘                      │ media network
          └──── Tailscale (personal tailnet) ──► media-tailscale ─► media-caddy
                                                  tasks.sagunkayastha.com ─┘
```

### Repo layout (`ADHD-helper/`, one Gradle build)

| Module | Purpose |
|---|---|
| `shared/` | Kotlin Multiplatform (`commonMain`, `androidMain`, `jvmMain`). Data models, kotlinx.serialization DTOs, recurrence math, HLC clock, merge rules, sync client (Ktor client), SQLDelight schema for the client DB, repositories, shared Compose UI screens. |
| `androidApp/` | Android entry point, AlarmManager scheduling, notification actions, WorkManager sync, boot receiver, share target, QS tile, shortcuts. |
| `desktopApp/` | Desktop entry point, tray, reminder timer, `notify-send` notifier, packaging. |
| `server/` | Ktor server (JVM). Server DB, sync endpoints, pairing, chat runner, MCP endpoint, backups. Depends on `shared` (`jvmMain`) for models and merge rules. |
| `docker/` | `build.Dockerfile` (JDK + Android SDK + Gradle, as in fin), `server.Dockerfile` (JRE 21 + Node + pinned `claude` CLI), `compose.yml`. |

All builds and tests run inside the build container. Nothing installed on the host.

## Data model

All ids are client-generated UUIDv7 strings. Every synced row carries `hlc` (hybrid logical
clock string, sortable) and `deleted` (tombstone flag).

```
task_list(id, title, sort_key, hlc, deleted)
task(id, list_id, parent_id NULL, title, details, starred,
     due_date NULL,            -- local date 'YYYY-MM-DD'
     due_time NULL,            -- local time 'HH:MM'; NULL = all-day, no alarm
     repeat NULL,              -- JSON rule, see Recurrence
     completed_at NULL, sort_key, snooze_until NULL, hlc, deleted)
note(id, text, created_at, task_id NULL, hlc, deleted)   -- notes-to-self; task_id set if turned into a task
chat_message(id, role, text, created_at, status, hlc)    -- role user|assistant; status queued|sent|answered|failed
```

- `sort_key` is a fractional-index string, so reordering touches one row.
- Times are wall-clock local in the zone `America/Denver` stored in settings; a reminder at 18:00
  stays 18:00 across DST.
- Subtasks: `parent_id` points at a top-level task; one level only (enforced in the repository).
  Completing a parent does not complete children (Google Tasks behaviour); deleting a parent
  tombstones its children.

### Recurrence

`repeat = {"freq":"daily|weekly|monthly|yearly","every":N,"days":["MO",...]}` (`days` weekly only).
Completing a repeating task writes `completed_at` on the current row **and** inserts the next
occurrence as a new task with the next due date. Recurrence math lives in `shared` and is unit-tested
around month ends, leap years, and DST.

## Sync

One protocol, used by both clients; the server's assistant writes through the same merge code.

- **Clock:** each device keeps a hybrid logical clock (wall time + counter + device id). Every local
  edit stamps the row's `hlc`.
- **Merge rule:** whole-row **last-writer-wins by `hlc`**. Tombstones are rows with `deleted=1`
  and win or lose like any edit. Single user makes real conflicts rare; LWW keeps it simple and
  deterministic. (Per-field merge is a later change if lost edits ever show up.)
- **Server log:** the server assigns a monotonic `rev` to every accepted row change.
- **`POST /api/v1/sync`** body: `{cursor, changes:[row...]}`. Server merges each change by `hlc`,
  bumps `rev` for winners, and replies `{cursor:newRev, changes:[rows with rev > cursor]}`.
  The client applies returned rows through the same merge rule and stores the cursor.
- **Outbox:** local edits are written to the local DB and to an outbox table in one transaction;
  the outbox drains on sync. Idempotent: resending a row is harmless (same `hlc` = no-op).
- **Live updates:** while an app is open it holds a WebSocket (`/api/v1/events`); the server sends
  `{"rev":N}` on any change and the client runs a sync. No payload over the socket.
- **Sync timing on Android:** on app start, after each local edit (debounced 2 s), every 15 min via
  WorkManager (network-constrained), and on the WebSocket poke while open. A reminder set on the
  PC less than ~15 min ahead may not reach a phone whose app is closed; documented limitation.
- **Tombstone cleanup:** server purges tombstones older than 90 days; a client whose cursor is
  older than the purge horizon does a full resync.

## Reminders

- **Android:** after every sync and edit, a `ReminderScheduler` computes the next fire time of
  each open task with `due_time` (respecting `snooze_until`) and sets one exact alarm per task
  (`AlarmManager.setExactAndAllowWhileIdle`, `USE_EXACT_ALARM` permission, fine for a sideloaded
  reminders app). Alarms are rescheduled on boot, time-zone change, and app update.
  The alarm posts a high-priority notification on channel "Reminders" with the actions above.
  Nag: if not acted on, it re-posts every 10 min, up to 3 times. Action handlers write through the
  repository (so they sync) and work with the app closed.
- **Desktop:** while the app runs, a coroutine timer fires due reminders through `notify-send`
  with the same actions where the notification daemon supports them; fall back to tray click.
- Both devices ring for the same task. Handling it on one cancels it on the other after the next sync.

## Assistant

- **Flow:** the client posts a message to `POST /api/v1/chat` and receives the reply as a
  server-sent event stream. Before running Claude the server saves the user message as a `note`,
  so capture never depends on the model.
- **Runner:** the server starts `claude -p --output-format stream-json` with
  `--tools ""`, `--strict-mcp-config`, `--mcp-config` pointing at the server's own `/mcp` endpoint
  (HTTP transport, loopback, per-run token), `--allowedTools` limited to the task tools,
  `--permission-mode bypassPermissions`, `--max-turns 8`, a system prompt with today's date, time
  zone and list names, and `--resume <session>` to keep one rolling conversation. Lessons from fin:
  auth only via `CLAUDE_CODE_OAUTH_TOKEN` in the container env; no credentials-file mount; the
  probe must run a real one-token request, not just `claude --version`; if `--resume` is rejected,
  start a fresh session.
- **MCP tools:** `list_lists`, `find_tasks(query?, list?, due_before?, include_completed?)`,
  `add_task(title, list?, details?, due_date?, due_time?, repeat?, starred?, parent?)`,
  `update_task(id, ...fields)`, `complete_task(id)`, `delete_task(id)`, `add_note(text)`,
  `note_to_task(note_id, ...)`. Each write goes through the shared merge code with the server's own
  HLC, so it syncs like any device edit.
- **Prompt behaviour:** clear request becomes a task (and the reply names list and time); vague
  thought stays a note and the reply says so in one line; questions ("what's left today?") are
  answered from `find_tasks`. Replies are short.
- **Notes view:** the chat screen has a toggle between "Chat" and "Notes". Long-press a note to make
  it a task.
- **Privacy:** messages and the task data the tools return go to Anthropic. The chat screen says so
  once, on first use.
- **Failure:** if Claude errors or times out (90 s idle, 300 s total), the message is marked
  `failed`, stays as a note, and can be retried.

## Server, auth, deploy

- **Pairing:** `docker exec tasks-server tasks pair` prints a one-time 8-character code (valid
  10 min). The app's setup screen takes server URL + code and receives a long random device token,
  stored in Android Keystore-backed storage / a 0600 file on desktop. All `/api/v1` calls need
  `Authorization: Bearer <token>`. Tokens can be listed and revoked (`tasks devices`,
  `tasks revoke <id>`). Tailnet membership is the outer gate; the token is the inner one.
- **Container:** `tasks-server`, port `8020`, published **only** on `192.168.0.162:8020` (never
  `0.0.0.0`: the host's `tailscale0` is the employer tailnet). Joins the external `media_default` network (as `~/stacks/tmls` does) so
  `media-caddy` reaches it as `tasks-server:8020`. Volume `tasks-data:/data`. `TZ=America/Denver`.
  `restart: unless-stopped`. Lives in `~/stacks/tasks/` on archbox, built from this repo.
- **Caddy:** add to `~/stacks/media/config/caddy/Caddyfile`:
  ```
  tasks.sagunkayastha.com {
  	import cf
  	import access
  	reverse_proxy tasks-server:8020
  }
  ```
  plus a Cloudflare DNS A record `tasks.sagunkayastha.com -> 100.96.124.103` (as for the other names).
  Back up the Caddyfile before editing, as the existing `.bak-YYYYMMDD` files do.
- **Secrets:** `~/stacks/tasks/.env` (0600) holds `CLAUDE_CODE_OAUTH_TOKEN=YOUR_TOKEN_HERE`; the
  user fills it from `claude setup-token`. Never committed, never logged; the chat runner passes it
  to the CLI child and nothing else.
- **Backups:** nightly `VACUUM INTO /data/backups/tasks-YYYY-MM-DD.db`, keep 14.
- **Health:** `GET /health` returns `{ok, rev, claude:"ok|unauthenticated|missing"}`.
- **APK distribution:** sideloaded. The server serves the latest signed APK at
  `/app/adhd-helper.apk` (token-protected), and the app shows "update available" when the server's
  version is newer.
- **Desktop install:** `jpackage` app image (bundled runtime) unpacked into the project's
  `dist/` folder, run from there; a `.desktop` launcher and optional autostart file are the only
  things placed outside it, and only after the user okays them (host-install rule).

## Error handling

- Offline is normal, not an error: UI shows a small "offline, N changes waiting" chip.
- Server rejects a change with a bad schema: returns it in `rejected[]`; the client logs it and
  drops it from the outbox so sync is never stuck.
- Token revoked or invalid: app goes to the setup screen; local data is kept.
- Alarm permission denied by the user: a persistent banner explains reminders will not fire.

## Testing

- `shared` (commonTest): HLC ordering, merge rules (LWW, tombstones, idempotent resend),
  recurrence math, fractional index, reminder next-fire computation.
- Server: Ktor `testApplication` for sync (two simulated devices editing offline then syncing,
  converging), pairing, auth, MCP tools; chat runner tested with a fake `claude` script that emits
  canned stream-json.
- Android: Robolectric tests for `ReminderScheduler` and notification actions; one instrumented
  smoke test is optional (no emulator on the host).
- Deploy smoke test: `/health` shows `claude: ok` after a real one-token request; a task created
  through the API appears in a second paired client.

## Open questions (answer at review; defaults in brackets)

1. App name and Android package id [`ADHD Helper`, `com.sagunkayastha.adhdhelper`].
2. Nag defaults [every 10 min, 3 times, on].
3. Default assistant model [Sonnet 5.5].
4. Desktop autostart on login [off; offered after first run].
5. Create the Cloudflare DNS record yourself, or let Claude use the existing Caddy CF token
   [you create it; one A record].
