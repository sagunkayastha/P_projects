# Plan: manager talks to sessions with Claude's built-in messaging; office gets one cubicle area per machine

Written by the manager session, 2026-10-11 (night). Scope tonight: this PC (laanta-chy) and archbox only.

## What the user asked for

1. The manager stops using the Python script to talk to sessions and uses Claude's built-in tools
   (`ListAgents`, `SendMessage`), including sessions on other machines, the way tmls does it (`ag`).
2. This should also open the way to adding Codex agents.
3. The office shows a separate cubicle area per machine.
4. Tomorrow the user wants to see the manager talking to agents this way.

## What I measured tonight (all run from the manager session, bypass mode)

| Test | Result |
|---|---|
| `SendMessage` → `Raid` (archbox, Remote Control, bypass mode) | Delivered at once. Raid answered with `SendMessage`; answer arrived here as a `<cross-session-message from-name="Raid">` turn. Full round trip, about 40 s. |
| `ag send archbox:vision-f1 … --from manager --mode bypass` (archbox, auto mode) | Submitted, then **held** on archbox: "The sending session's permission mode class doesn't match this session's". It reached Claude only after it was approved there. The answer then came back through built-in `SendMessage`. |
| `ListAgents` from the manager | Shows this PC's sessions and every session with Remote Control on. Missing: archbox `TMLS` (Remote Control off). |
| `ag ls` on both machines | Each machine lists the other (`~/.config/tmls/hosts` is set on both). On archbox `ag` is at `~/.local/bin/ag`, which is not on the PATH of a non-login ssh shell. |

Facts that follow:

- **Names differ per tool.** `ListAgents` shows the session title (vision-f1 appears as
  "Ph-2 outage and worker status"); `ag` uses the `--name` (`vision-f1`); Standup's board uses the
  title plus a session id. The manager needs one table that joins the three.
- **Mode mismatch holds messages.** A bypass sender to an auto-mode or prompting session is held
  until the user approves it there, unless that session sets `"crossSessionInbound": "accept"`.
  Changing that setting is the user's call, per session or per machine. Nobody else changes it.
- **Remote Control routes give no read receipt.** Only sessions on this PC send a delivery notice,
  and only they support `notify_when_idle`.
- A built-in message arrives marked as coming from the manager, not as the user's own typing. The
  old `./sessions tell` typed into the pane as the user. The built-in route is the more honest one.

## Design

### Part A: the manager (folder `office-manager`, done by the manager itself)

Routing rule, first match wins:

1. Session is in `ListAgents` (this PC, or Remote Control on another machine) → `SendMessage` by name.
   On this PC add `notify_when_idle: true` when the user wants to hear the result.
2. Claude session not in `ListAgents` (Remote Control off, e.g. archbox `TMLS`) →
   `ag send HOST:NAME "…" --from manager --mode bypass`.
3. Codex thread → `ag send THREAD "From Claude (manager): … Reply with: ag send manager \"…\" --from THREAD --mode bypass"`
   (contract in `~/.claude/docs/claude-codex-messaging.md`).

Reading stays as it is: `./sessions` and `./sessions read NAME` (Standup knows `WAITING ON YOU` and
`API ERROR`, which `ListAgents` does not), with `ag read HOST:NAME` for the live screen.
`./sessions tell` is kept only for the case where the user says to type something as their own message.

Status: `CLAUDE.md` in this folder is updated with this rule tonight. No code needed for Part A.

### Part B: the office (repos `pixel-agents` and `agent-standup`, for the Agent Thing session)

B1. **Archbox sessions get characters.** Today the office reads this PC's transcripts only
    (`~/.claude/projects`, read-only mount). Standup's helper already mirrors running archbox
    sessions to `/run/user/1000/agent-standup/remote` every 3 s. Feed that mirror to the office and
    carry a `host` field on every agent ("" = this PC, "archbox").

B2. **One cubicle area per machine.** In the layout, give every seat a `zone`. Generate the zones in
    `layouts/make_cubicles.py`: the two existing blocks become "this PC" and "archbox", with a sign
    or floor colour per area so the user can tell them apart at a glance. Seat assignment in
    `officeState.addAgent` picks a free seat in the zone of the agent's host; if the zone is full,
    fall back to any free seat. Keep the zone list as data (host name → zone), no code per host.
    The reporting desk stays shared in the middle; the manager keeps her own spot.

B3. **Manager lookup stays local.** `findManager` in `server/src/standupProxy.ts` filters `!row.host`
    on purpose: keep it.

B4. **Board carries the names the manager needs.** Add to Standup's `/api/board` rows the session's
    `--name` (from `~/.claude/sessions/<pid>.json`, also on the mirrored host) next to title and id,
    so `./sessions` can print title, `ag` name and host in one line. Small; do it only if B1 and B2
    are done.

B5. **Codex agents (design only tonight, do not build).** Messaging is already covered by `ag send`.
    To show a Codex thread in the office it needs a transcript source (Codex session files) and a
    state rule. Write down where those files are and what a row would need; stop there.

Out of scope tonight: other hosts (ampere, NERSC, pollenhunter, nano), committing or pushing any
repo, restarting tmls, changing any session's permission or `crossSessionInbound` setting.

## Checks (each step is done only when its check passes)

| Step | Check |
|---|---|
| A | Manager sends to one PC session and one archbox session with `SendMessage` and gets both answers. (Archbox half passed tonight with Raid.) |
| B1 | With Raid or TMLS running on archbox, a character for it appears in the office within about 10 s; it leaves when the session ends. |
| B2 | Screenshot of the office: PC sessions sit in the PC area, archbox sessions in the archbox area, areas are labelled. Looked at by the agent before reporting. |
| B1–B2 | Existing tests still pass: webview (118), `standupProxy.test.ts` (20), Standup node tests (11), bridge tests (5). New tests for zone seat choice and host field. |
| B4 | `./sessions` prints host and `ag` name for an archbox session. |

## Rules for whoever does Part B

- Docker only: no installs on the host. Never run `docker builder prune`.
- The GPU is shared; this work needs no model.
- A browser test tab opened by automation is `document.hidden`: the canvas does not run there. Check
  layout with the layout JSON and a real window screenshot.
- The live layout is in Docker volume `pixel-agents-data`; `docker cp layouts/cubicles.json
  pixel-agents:/root/.pixel-agents/layout.json` updates it live. Keep a copy of the current live
  layout before replacing it.
- Do not commit or push. Log the session in `pixel-agents/PROGRESS.md`.
- Other sessions may be working in the same worktrees: never revert or stash files you did not change.

## Open for the user (morning)

1. Auto-mode and prompting sessions hold the manager's messages. Either approve each one there, or
   set `"crossSessionInbound": "accept"` for those sessions. Which?
2. Turn Remote Control on for archbox `TMLS` so it shows in `ListAgents`? Until then it is reached by `ag`.
3. Zone look: signs, floor colour, or both.
