# AHelp (ADHD-helper) — STATE
Updated: 2026-10-24 · by rem-statepc (converted from PROGRESS.md)

## Goal
AHelp: the user's tasks/reminders app (Kotlin Multiplatform: Android, Linux desktop, Ktor server) with a Claude-backed assistant. Done = deployed on archbox, used daily on Pixel/Samsung/desktop, branch merged to `main`.

## Status
- Overall: active; last entry 2026-10-12. Server LIVE; all devices on the real server.
- Real server: container `tasks-server` on archbox (`~/stacks/tasks`), `192.168.0.162:8020`, volume `tasks-data` (DB + 14 daily backups + `apk/`). `https://tasks.sagunkayastha.com` works via Caddy (DNS A record -> `100.96.124.103`, DNS only). At home it also works without Tailscale (AdGuard rewrite -> `192.168.0.162`, container `tasks-lan` socat on :443).
- Paired: Pixel 9 Pro XL, Samsung A52s (test phone), Linux desktop (laanta-chy, LAN `http://192.168.0.162:8020`). Demo server is gone; its data (the user's real tasks) was moved to the real server.
- Code is NOT in this dir: worktree `~/Others/P_projects-wt/adhd-helper/ADHD-helper` on branch `adhd-helper` (head about `55fbb0f`; nothing merged or pushed). Tests at last full run: shared 320, ui 231, desktopApp 127, androidApp 185, server 320, 0 failures.
- Desktop app runs from `<worktree>/ADHD-helper/local/run.sh` (data in git-ignored `local/`), launcher `~/.local/share/applications/ahelp.desktop`. No autostart.

## Next
1. Deploy plan `ADHD-helper/docs/superpowers/plans/2026-10-09-p7-deploy.md`: Task 7 smoke tests (reminder rings on phone, offline add, reboot), Task 8 README "Deploy" section.
2. Check the first real backup exists in `/data/backups/` on the server (03:30 run).
3. Pixel: press "Update available" (build 29861783) once.
4. Open questions for the user, one at a time: (a) Done on an undated task: keep "sets today"? (b) chat jump while a long reply streams and user scrolled up: fix or park? (c) copy of server backups on another disk? (d) own signing key now (one uninstall per phone) or later? (e) centred month title like Google Tasks?
5. UI cleanup batch 2: M3 `ListItem` rows, add-sheet icon alignment, cramped `Completed` header, Calendar weekday labels vs picker, audit detail/Assistant/desktop/Pixel portrait. Use stock Material 3.
6. Unreviewed work: nag setting `c7b639d`, New chat `73c61b2`, back-closes-app fix `110bcbd` (unproven). Commit uncommitted `deploy/archbox/docker-compose.yml` change if still pending (unverified).
7. Parked: Denver zone vs phone zone; 15-min background sync; Notes inbox delete; reminder re-show after reboot; silent self-update; Wayland bring-to-desktop; unchecked phone features (snooze, QS tile, share target, shortcuts).
8. Last: merge `adhd-helper` -> `main`; then move `local/` and `dist/` and fix `ahelp.desktop` paths.

## Blockers / waiting on
- User answers to the open questions (Next 4) and a yes/no on a permanent desktop autostart.
- This PC's Tailscale is on the employer tailnet: `*.sagunkayastha.com` is not reachable from here; use the LAN address.

## Decisions
- 2026-10-12: visible app name is `AHelp`; package id, binary `adhd-helper`, repo dir, container names unchanged.
- 2026-10-12: home Wi-Fi access via AdGuard rewrite + `tasks-lan` (option A, "AHelp only"); release Android blocks cleartext http.
- 2026-10-12: desktop app data lives in the project worktree (`local/`), not under `~`.
- Android uses the phone's dynamic colours and 24h clock; desktop stays purple, 12h.
- Starred open tasks sort above unstarred; use stock Google/Material 3 components.

## Gotchas / do-not
- DO NOT restart/recreate demo containers (gone); DO NOT run `docker/build-desktop.sh` while the desktop app runs.
- Debug signing key lives in volume `adhd-gradle` on this PC: losing it means uninstall + reinstall on both phones. Updates must keep the same key.
- `tasks pair`: line 1 is the 8-char code; never echo codes or tokens. Claude token only in `~/stacks/tasks/.env` (0600) on archbox.
- Cisco VPN on this PC routes 172.17.0.0/16: containers lose internet and host cannot reach them while up.
- Android Private DNS skips AdGuard (then Tailscale needed). Pixel's per-phone nag setting is default.
- Server update: commit -> `deploy/sync-src.sh` -> `ssh archbox.local 'cd ~/stacks/tasks && docker compose up -d --build'`. Publish APK: `deploy/publish-apk.sh <apk> <versionCode>`.

## Key paths & commands
- This dir: only `docs/superpowers/` (specs, plans) and logs. Code: `~/Others/P_projects-wt/adhd-helper/ADHD-helper` (`server/`, `androidApp/`, `desktopApp/`, `shared/`, `ui/`, `deploy/`, `docker/`).
- Adding a task as an agent: `~/.claude/docs/ahelp.md`.
- Server CLI: `ssh archbox.local docker exec tasks-server tasks pair|devices|revoke <id>`; health `curl -s <base>/health`.
- Phone adb: container `adhd-adb` (image `adhd-build`, command in STATE-LOG 2026-10-11 entry); Pixel serial `4A111FDAS000WF`, Samsung `RZCR908FCPN`.
- Service index row: `~/Others/P_projects/homelab/SERVICES.md`.
