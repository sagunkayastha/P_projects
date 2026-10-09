# PROGRESS — ADHD Helper (2026-10-09)

Quick session log. Newest entry first.

## 2026-10-09 — Spec + 7-phase plan written; nothing built yet
Brainstormed a personal ADHD task app (Google Tasks clone + Claude assistant/notes inbox). Spec and plans committed; implementation not started.
- **Spec:** `docs/superpowers/specs/2026-10-09-adhd-helper-design.md` (commit `5447c57`).
- **Plans:** `docs/superpowers/plans/2026-10-09-00-index.md` (order, Global Constraints, binding interface contract) + `p1-foundation` (7 tasks), `p2-server` (8), `p3-client-data` (10), `p4-android` (25), `p5-desktop` (10), `p6-assistant` (15), `p7-deploy` (8). Commit `ec1621f`.
- **Decisions:** native Android + native Linux desktop (Compose Multiplatform, shared `shared/` + `ui/` modules), Ktor server in Docker on archbox, local SQLite per device, whole-row LWW sync on HLC. Reminders = local alarms (no Firebase). Assistant = `claude` CLI on subscription (`CLAUDE_CODE_OAUTH_TOKEN`) against the server's own `/mcp`; every message saved as a note first. Remote access via personal tailnet: `media-tailscale` + `media-caddy` → `https://tasks.sagunkayastha.com` → `tasks-server:8020` on `media_default` network.
- User rejected: web/WebView/PWA ("not like fin"), sharing/multi-user. Chose Kotlin-everywhere (option 2) over Python server.
- **DO NOT** bind `0.0.0.0` on archbox — host `tailscale0` is the employer tailnet. Publish only `192.168.0.162:8020`.
- **DO NOT** install JDK/Gradle/Android SDK/adb on the host — everything runs in the `adhd-build` container (test command in plan index).
- Caddyfile on archbox is a single-file read-only bind mount: append with `>>` / restore with `cp`, never `sed -i` (inode change → Caddy keeps old file). See p7.

### NEXT
1. ~~Review + defaults~~ — user approved plans and all 5 defaults (2026-10-09).
2. Execution: **subagent-driven** chosen. Start Phase 1.
3. Blocked on user later: `claude setup-token` → `~/stacks/tasks/.env` on archbox (p7); Cloudflare A record `tasks.sagunkayastha.com → 100.96.124.103`; phone on USB for first APK install; OK for desktop `.desktop`/autostart files.
4. Unverified until first build: kotlinx-datetime 0.7 `LocalDate.day`, `${VAR:-default}` in Dockerfile `FROM`, pinned `claude` CLI version (p2 Task 8 re-pins). Robolectric re-downloads jars each run (slow, works).
