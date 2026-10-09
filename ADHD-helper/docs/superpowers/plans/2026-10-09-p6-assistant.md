# Phase 6: Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The user can type "remind me to call mom tomorrow 6pm" on either device and get a task (or a note) created by Claude, streamed back live, with every message saved as a note before Claude runs and queued messages sent when the server is reachable again.

**Architecture:** The Ktor server gains a hand-rolled MCP endpoint (`POST /mcp`, JSON-RPC 2.0, streamable-HTTP JSON-response mode, loopback-only, per-run token) exposing eight task tools that write through `SyncService.write` with the server HLC. A `ChatRunner` spawns the `claude` CLI (`-p --output-format stream-json`) against that endpoint through a `ProcessLauncher` seam (faked in tests), and `POST /api/v1/chat` saves the user message + note first, then streams `delta` / `done` / `failed` server-sent events. On the client, `ChatClient` posts and parses the SSE stream, applies the server's rows locally, and flushes queued messages oldest-first when sync goes online; a shared Compose Assistant screen (Chat / Notes toggle) sits in `AppContainer.chat`'s slot.

**Tech Stack:** Kotlin 2.2.0, Ktor 3.2.0 (server core + test host, client core + MockEngine), kotlinx-serialization-json 1.9.0 (`JsonObject` builders, no MCP SDK), kotlinx-coroutines 1.10.2, kotlinx-datetime 0.7.1, SQLDelight 2.1.0 (one `setting` table for the Claude session id), Compose Multiplatform 1.8.2 Material3, `claude` CLI (pinned in Phase 2's server image).

**Spec:** `docs/superpowers/specs/2026-10-09-adhd-helper-design.md` (section "Assistant"; also "Server, auth, deploy" for secrets and `/health`). Index: `docs/superpowers/plans/2026-10-09-00-index.md`.

## Global Constraints

- **Docker-only:** every build/test runs in the build container. Test command template (each step writes the Gradle part only, meaning this full line):
  `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle <task> --no-daemon`
- Never bind `0.0.0.0` on archbox (host publishing is Phase 2/7's job; inside the container the server listens on its port, so `127.0.0.1:8020` reaches it).
- **Secrets:** `CLAUDE_CODE_OAUTH_TOKEN` comes only from the container env (`~/stacks/tasks/.env`, placeholder `YOUR_TOKEN_HERE`). Auth is that env var only: it is passed **unchanged** to the `claude` child (the fin bug was stripping it); no credentials-file mount. The token is never logged, never put in an SSE frame, never in an exception message: any CLI stderr surfaced to the user goes through `redact()` first. Device tokens and run tokens are never logged.
- `/mcp` accepts loopback connections only (checked on the real socket address, not `X-Forwarded-For`) and a live `X-Run-Token`; it is outside the Bearer-auth block. `/api/v1/chat` is inside it.
- Contract names are binding: `ChatClient(http: HttpClient, settings: AppSettings, repo: TaskRepository)` with `suspend fun send(message: ChatMessage): Flow<ChatEvent>` and `suspend fun flushQueued()`; `sealed interface ChatEvent { Delta(text), Done(reply: ChatMessage), Failed(reason) }`; `fun interface ClaudeProbe { fun status(): String }` returning `"ok" | "unauthenticated" | "missing"`; `SyncService.write(changes): Long`, `SyncService.snapshot(): Changes`, `SyncService.stamp(): String` (every server-written row is stamped with this; `Hlc` is not thread-safe). `/api/v1/chat` sits in `authenticate(AUTH_DEVICE) { }`.
- Assistant models: `claude-sonnet-5-5` (default, label "Sonnet 5.5"), `claude-haiku-5-5` ("Haiku 5.5"), `claude-opus-5-5` ("Opus 5.5"). Max 8 turns. Timeouts 90 s idle / 300 s total.
- Deterministic ids (so retries and two devices never duplicate): the note for chat message `m` is `Ids.derived("note:$m")`; the assistant reply is `Ids.derived("reply:$m")`; a repeating task's next occurrence is `Ids.derived("${id}:${nextDate}")` (index RF3).
- `Instant` is `kotlin.time.Instant`; `shared` already opts in to `kotlin.time.ExperimentalTime` (Phase 1). The `server` module must opt in too (Task 3 Step 1 checks).
- Package root `com.sagunkayastha.adhdhelper`. Server code of this phase: `...server.assistant`. Shared wire types: `...chat`. Client (incl. the Compose-free `AssistantController`): `...client` in `shared/`. Compose screen: `...ui.assistant` in the `ui/` module.
- Commits end with the two trailer lines below (every commit step uses `git commit -F -` with a heredoc so the trailers stay one paragraph):
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
  ```

### Facts from earlier phase plans this plan relies on

| Fact (from `2026-10-09-p2-server.md` / `-p3-client-data.md` / `-p5-desktop.md`) | Used in |
|---|---|
| `server/.../server/Module.kt`: `fun interface ClaudeProbe`, `data class ServerDeps(config, db, sync, events, auth, claude: ClaudeProbe = ClaudeProbe { "missing" })`, `const val AUTH_DEVICE = "device"`, `Application.module` with `routing { healthRoutes; pairRoutes; authenticate(AUTH_DEVICE) { syncRoutes; eventRoutes; appRoutes } }`; `/health` calls `deps.claude.status()` on every request | Tasks 7, 9 |
| `SyncService.stamp(): String` is the only thread-safe server HLC; server-side writers never call `hlc.now()` | Tasks 4, 8 |
| `ServerDb` keeps its driver private; access is `internal fun <T> tx(block: ServerDatabase.() -> T)`; schema is created only for a new file (`user_version == 0`) | Task 6 |
| `Cli.kt` `serve(config)` builds `ServerDeps(config, db, sync, events, DeviceAuth(db))` | Task 9 |
| Phase 3 already provides (written once there, this plan only uses them): `queueChat` stores its note as `Ids.derived("note:" + messageId)` (= `ChatIds.noteFor`), `TaskRepository.setChatStatus(id, status)`, `TaskRepository.noteToTask(noteId, listId)`, `object Completion { nextOccurrence(task, sortKey, hlc); anchored(task) }` in `shared/.../core/Completion.kt` (`TaskRepository.complete` uses it); jvmTest fixture `TestDevice`; `FileAppSettings(path)`; `createHttpClient()` installs `HttpTimeout` + `ContentNegotiation` + `WebSockets` | Tasks 2, 4, 10-13 |
| Shared Compose screens live in module `ui/` (package `com.sagunkayastha.adhdhelper.ui`, `AppContainer`, `AppRoot`); Phase 4 Task 13 creates the placeholder `AssistantSlot(container)` in `ui/.../ui/AssistantSlot.kt`, routed from `AppRoot` as `Screen.Assistant` and shown in the drawer only when `container.chat != null` | Task 14 |
| `DesktopApp.create` passes `chat = null, // Phase 6 wires ChatClient here`; `DesktopAppWiringTest` asserts `chat == null`; the desktop HTTP client is Phase 3's `createHttpClient()` | Task 15 |
| Phase 4 Task 1 creates the placeholder `class ChatClient` (no constructor) at `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/ChatClient.kt` so `AppContainer` compiles; Task 10 replaces that exact file | Task 10 |

## Review Focus

1. **Claude down or token missing / placeholder** — the user's message is still a note, marked FAILED, retryable; `/health` says `claude: "unauthenticated"`; the token never appears in the failure text. (Task 7 probe tests, Task 8 `failureKeepsNoteAndMarksFailedThenRetrySucceeds`, Task 6 `stderrIsRedacted`, Task 9 `healthReportsUnauthenticatedWithoutToken`.)
2. **Same message sent twice** (UI send + reconnect flush, or Retry after a dropped connection) — one note, one reply, and an already-answered message is not run through Claude again. (Task 8 `answeredMessageIsNotRunAgain`, `noteAlreadySyncedFromClientIsNotRewritten`; Task 12 `queueChatNoteIdMatchesServer`.)
3. **"tomorrow" late in the evening** — at 21:30 in Denver it is already the next day in UTC; the prompt must give Claude the local date so "tomorrow" lands on the right day. (Task 5 `dateIsLocalNotUtcNearMidnight`.)
4. **Something other than this server's own Claude run calling `/mcp`** (another device on the LAN/tailnet via Caddy, or a leaked old run token) — rejected. (Task 3 `rejectsMissingOrRevokedToken`, `loopbackCheck`; Task 6 token revoked after run; Task 9 `mcpNeedsRunTokenButNotBearer`.)
5. **Claude hangs or the phone drops the connection mid-reply** — the run is killed at 90 s idle / 300 s total, the message is marked FAILED (never stuck at SENT), and the next chat is not blocked. (Task 6 `idleTimeoutKillsProcess`, `totalTimeoutKillsProcess`; Task 8 `runnerCrashMarksFailed`, `secondConcurrentChatGets409` then lock released.)

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/chat/ChatWire.kt` | `ChatRequest`, SSE frame DTOs, `ChatJson`, `ChatModels`, `ChatIds`, `Sse` encode/parse | 1 |
| `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/Mcp.kt` | `ToolSet`, `ToolResult`, `ToolError`, `RunTokens`, `McpServer`, `Route.mcpRoute`, `isLoopback` | 3 |
| `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/TaskTools.kt` | the eight tools + JSON schemas | 4 |
| `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/StreamJson.kt` | stream-json line parser | 5 |
| `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/SystemPrompt.kt` | system prompt builder | 5 |
| `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/Process.kt` | `ProcessLauncher`, `RunningProcess`, `SystemProcessLauncher` | 6 |
| `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/SessionStore.kt`, `server/src/main/sqldelight/com/sagunkayastha/adhdhelper/server/db/Setting.sq` | `SessionStore`, `DbSessionStore` (settings row) | 6 |
| `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/ChatRunner.kt` | `RunnerConfig`, `RunEvent`, `ChatRunner` | 6 |
| `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/CliClaudeProbe.kt` | real `ClaudeProbe` | 7 |
| `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/ChatService.kt` | `ChatService`, `Route.chatRoute` (SSE) | 8 |
| `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/Assistant.kt` | wiring bundle `Assistant.create(...)` | 9 |
| `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/Module.kt`, `Cli.kt` (Phase 2) | add `assistant` field, mount routes, real probe | 9 |
| `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/TestStore.kt`, `FakeClaude.kt`, `TestServer.kt` | test fixtures | 4, 6, 9 |
| `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/ChatClient.kt` | replaces Phase 4's stub: `ChatEvent`, `ChatClient`, `flushWhenOnline` | 10, 11 |
| `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/ChatNoteIdTest.kt` | pins Phase 3's chat note id = `ChatIds.noteFor` | 12 |
| `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/AssistantController.kt` | UI state holder (testable without Compose) | 13 |
| `ui/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/ui/assistant/AssistantScreen.kt` | Compose screen, bubbles, notes, privacy notice, `ModelPicker` | 14 |
| `desktopApp/.../desktop/DesktopApp.kt`, Android container wiring (Phase 4) | pass a real `ChatClient`, start flush | 15 |

---

### Task 1: Shared chat wire types

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/chat/ChatWire.kt`
- Test: `shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/chat/ChatWireTest.kt`

**Interfaces:**
- Consumes: Phase 1 `ChatMessage`, `Ids.derived(name)`.
- Produces (package `com.sagunkayastha.adhdhelper.chat`):
  - `@Serializable data class ChatRequest(val messageId: String, val text: String, val model: String? = null)`
  - `@Serializable data class ChatDeltaFrame(val text: String)`; `@Serializable data class ChatDoneFrame(val message: ChatMessage, val reply: ChatMessage)`; `@Serializable data class ChatFailedFrame(val reason: String, val message: ChatMessage? = null)`
  - `val ChatJson: Json` (ignoreUnknownKeys)
  - `object ChatModels { const val DEFAULT = "claude-sonnet-5-5"; val ALL: List<Pair<String, String>>; fun resolve(requested: String?): String; fun label(id: String): String }`
  - `object ChatIds { fun noteFor(messageId: String): String; fun replyFor(messageId: String): String }`
  - `data class SseFrame(val event: String, val data: String)`; `object Sse { fun encode(event: String, data: String): String; class Parser { fun feed(line: String): SseFrame? } }`
  - SSE events on `/api/v1/chat`: `delta` (data `ChatDeltaFrame`), `done` (data `ChatDoneFrame`), `failed` (data `ChatFailedFrame`).

- [ ] **Step 1: Write the failing test**

```kotlin
package com.sagunkayastha.adhdhelper.chat

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNull

class ChatWireTest {
    @Test
    fun sseEncodeThenParseRoundTrips() {
        val text = Sse.encode("delta", """{"text":"a"}""") + Sse.encode("done", "{}")
        val parser = Sse.Parser()
        val frames = text.split("\n").mapNotNull { parser.feed(it) }
        assertEquals(listOf(SseFrame("delta", """{"text":"a"}"""), SseFrame("done", "{}")), frames)
    }

    @Test
    fun parserIgnoresCommentsAndJoinsDataLines() {
        val parser = Sse.Parser()
        val frames = listOf(": keep-alive", "data: a", "data:b", "").mapNotNull { parser.feed(it) }
        assertEquals(listOf(SseFrame("message", "a\nb")), frames)
    }

    @Test
    fun modelsResolveToKnownIdsOnly() {
        assertEquals("claude-sonnet-5-5", ChatModels.DEFAULT)
        assertEquals(ChatModels.DEFAULT, ChatModels.resolve(null))
        assertEquals("claude-haiku-5-5", ChatModels.resolve("claude-haiku-5-5"))
        assertEquals("claude-opus-5-5", ChatModels.resolve("claude-opus-5-5"))
        assertEquals(ChatModels.DEFAULT, ChatModels.resolve("gpt-4"))
        assertEquals("Sonnet 5.5", ChatModels.label("claude-sonnet-5-5"))
    }

    @Test
    fun derivedIdsAreStableAndDistinct() {
        assertEquals(ChatIds.noteFor("m1"), ChatIds.noteFor("m1"))
        assertNotEquals(ChatIds.noteFor("m1"), ChatIds.replyFor("m1"))
        assertNotEquals(ChatIds.noteFor("m1"), ChatIds.noteFor("m2"))
        assertEquals(36, ChatIds.noteFor("m1").length)
    }

    @Test
    fun requestModelIsOptional() {
        val req = ChatJson.decodeFromString(ChatRequest.serializer(), """{"messageId":"m","text":"t"}""")
        assertNull(req.model)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.chat.ChatWireTest'`
Expected: FAIL to compile, `Unresolved reference: Sse` / `ChatModels`.

- [ ] **Step 3: Write the implementation**

```kotlin
package com.sagunkayastha.adhdhelper.chat

import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.sync.Ids
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** Body of POST /api/v1/chat. `model` is optional; unknown values fall back to the default. */
@Serializable
data class ChatRequest(val messageId: String, val text: String, val model: String? = null)

@Serializable data class ChatDeltaFrame(val text: String)
@Serializable data class ChatDoneFrame(val message: ChatMessage, val reply: ChatMessage)
@Serializable data class ChatFailedFrame(val reason: String, val message: ChatMessage? = null)

val ChatJson: Json = Json { ignoreUnknownKeys = true }

object ChatModels {
    const val DEFAULT = "claude-sonnet-5-5"
    val ALL: List<Pair<String, String>> = listOf(
        "claude-sonnet-5-5" to "Sonnet 5.5",
        "claude-haiku-5-5" to "Haiku 5.5",
        "claude-opus-5-5" to "Opus 5.5",
    )

    fun resolve(requested: String?): String =
        if (requested != null && ALL.any { it.first == requested }) requested else DEFAULT

    fun label(id: String): String = ALL.firstOrNull { it.first == id }?.second ?: id
}

/** Deterministic ids so a resent or retried message never creates a second note or reply. */
object ChatIds {
    fun noteFor(messageId: String): String = Ids.derived("note:$messageId")
    fun replyFor(messageId: String): String = Ids.derived("reply:$messageId")
}

data class SseFrame(val event: String, val data: String)

/** Minimal server-sent events: `event:` + one or more `data:` lines + blank line. */
object Sse {
    fun encode(event: String, data: String): String = "event: $event\ndata: $data\n\n"

    class Parser {
        private var event = "message"
        private val data = StringBuilder()

        /** Feed one line (without the newline). Returns a frame when a blank line ends one. */
        fun feed(line: String): SseFrame? {
            if (line.isEmpty()) {
                if (data.isEmpty()) return null
                val frame = SseFrame(event, data.toString())
                event = "message"
                data.clear()
                return frame
            }
            if (line.startsWith(":")) return null
            val field = line.substringBefore(':')
            val value = line.substringAfter(':', "").removePrefix(" ")
            when (field) {
                "event" -> event = value
                "data" -> {
                    if (data.isNotEmpty()) data.append('\n')
                    data.append(value)
                }
            }
            return null
        }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.chat.ChatWireTest'`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/chat/ChatWire.kt shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/chat/ChatWireTest.kt
git commit -F - <<'EOF'
feat(shared): chat wire types, model list, deterministic chat ids, SSE codec

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 2: (provided by Phase 3) shared next-occurrence helper

Nothing to write. `object Completion { fun nextOccurrence(task: Task, sortKey: String, hlc: String): Task?; fun anchored(task: Task): Task }` lives in `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/Completion.kt`, written and tested in Phase 3 Task 4 (`CompletionTest`), and `TaskRepository.complete` already uses it. Task 4 below reuses it in the server tools.

- [ ] **Step 1: Confirm it exists**

Run: `grep -n "fun nextOccurrence\|fun anchored" shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/Completion.kt`
Expected: two lines. (No code, no commit in this task.)

---

### Task 3: MCP endpoint (JSON-RPC over streamable HTTP, JSON response mode)

**Files:**
- Create: `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/Mcp.kt`
- Test: `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/McpServerTest.kt`
- Possibly modify: `server/build.gradle.kts` (opt-in, Step 1)

**Interfaces:**
- Consumes: Ktor server routing, `kotlinx.serialization.json`.
- Produces:
  - `data class ToolResult(val text: String, val isError: Boolean = false)`
  - `class ToolError(message: String) : Exception(message)`
  - `interface ToolSet { fun definitions(): List<JsonObject>; fun call(name: String, args: JsonObject): ToolResult }`
  - `class RunTokens { fun issue(): String; fun revoke(token: String); fun valid(token: String?): Boolean }`
  - `class McpServer(tools: ToolSet) { fun handle(body: String): JsonObject? }` (null = notification/response, reply 202)
  - `fun Route.mcpRoute(server: McpServer, tokens: RunTokens)` mounts `POST/GET/DELETE /mcp`
  - `fun isLoopback(address: String): Boolean`
  - `const val MCP_PROTOCOL_VERSION = "2025-06-18"`
- Protocol: `initialize` → `{protocolVersion:"2025-06-18", capabilities:{tools:{listChanged:false}}, serverInfo:{name:"adhd-helper-tasks", version:"1"}}`; `ping` → `{}`; `tools/list` → `{tools:[...]}`; `tools/call` → `{content:[{type:"text",text}], isError}`; any message without `id` (e.g. `notifications/initialized`) → HTTP 202, empty body; unknown method → error `-32601`; unparseable body → error `-32700` with `id: null`. `GET`/`DELETE /mcp` → 405 (no server-initiated stream, no session). Auth: socket remote address must be loopback (else 403) and `X-Run-Token` must be live (else 401).

- [ ] **Step 1: Make sure the server module opts in to `kotlin.time.ExperimentalTime`**

Run: `grep -n "ExperimentalTime" server/build.gradle.kts`
If there is no match, add inside the existing `kotlin { }` block of `server/build.gradle.kts` (create the block if absent):

```kotlin
kotlin {
    compilerOptions { optIn.add("kotlin.time.ExperimentalTime") }
}
```

- [ ] **Step 2: Write the failing test**

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import io.ktor.client.request.accept
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.server.testing.ApplicationTestBuilder
import io.ktor.server.testing.testApplication
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class McpServerTest {
    private val echo = object : ToolSet {
        override fun definitions() = listOf(buildJsonObject {
            put("name", "echo"); put("description", "Echo text")
            putJsonObject("inputSchema") { put("type", "object") }
        })
        override fun call(name: String, args: JsonObject) =
            if (name == "echo") ToolResult(args["text"]!!.jsonPrimitive.content)
            else ToolResult("Unknown tool: $name", isError = true)
    }

    private fun rpc(id: Int?, method: String, params: JsonObject = JsonObject(emptyMap())) = buildJsonObject {
        put("jsonrpc", "2.0"); if (id != null) put("id", id); put("method", method); put("params", params)
    }.toString()

    private suspend fun ApplicationTestBuilder.mcp(body: String, token: String?): HttpResponse =
        client.post("/mcp") {
            if (token != null) header("X-Run-Token", token)
            contentType(ContentType.Application.Json)
            accept(ContentType.Application.Json); accept(ContentType.Text.EventStream)
            setBody(body)
        }

    private fun json(r: String) = Json.parseToJsonElement(r).jsonObject

    @Test
    fun handshakeListAndCall() = testApplication {
        val tokens = RunTokens(); val t = tokens.issue()
        routing { mcpRoute(McpServer(echo), tokens) }

        val init = mcp(rpc(1, "initialize", buildJsonObject {
            put("protocolVersion", "2025-06-18"); putJsonObject("capabilities") {}
            putJsonObject("clientInfo") { put("name", "test"); put("version", "0") }
        }), t)
        assertEquals(HttpStatusCode.OK, init.status)
        assertTrue(init.headers["Content-Type"]!!.startsWith("application/json"))
        val result = json(init.bodyAsText())["result"]!!.jsonObject
        assertEquals("2025-06-18", result["protocolVersion"]!!.jsonPrimitive.content)
        assertNotNull(result["capabilities"]!!.jsonObject["tools"])
        assertEquals("adhd-helper-tasks", result["serverInfo"]!!.jsonObject["name"]!!.jsonPrimitive.content)

        val note = mcp(rpc(null, "notifications/initialized"), t)
        assertEquals(HttpStatusCode.Accepted, note.status)
        assertEquals("", note.bodyAsText())

        val tools = json(mcp(rpc(2, "tools/list"), t).bodyAsText())["result"]!!.jsonObject["tools"]!!.jsonArray
        assertEquals("echo", tools.single().jsonObject["name"]!!.jsonPrimitive.content)

        val call = json(mcp(rpc(3, "tools/call", buildJsonObject {
            put("name", "echo"); putJsonObject("arguments") { put("text", "hi") }
        }), t).bodyAsText())
        assertEquals(3, call["id"]!!.jsonPrimitive.int)
        val content = call["result"]!!.jsonObject
        assertEquals("hi", content["content"]!!.jsonArray[0].jsonObject["text"]!!.jsonPrimitive.content)
        assertFalse(content["isError"]!!.jsonPrimitive.boolean)

        assertEquals("{}", json(mcp(rpc(4, "ping"), t).bodyAsText())["result"].toString())
    }

    @Test
    fun errorsFollowJsonRpc() = testApplication {
        val tokens = RunTokens(); val t = tokens.issue()
        routing { mcpRoute(McpServer(echo), tokens) }
        val unknown = json(mcp(rpc(5, "resources/list"), t).bodyAsText())
        assertEquals(-32601, unknown["error"]!!.jsonObject["code"]!!.jsonPrimitive.int)
        val garbage = json(mcp("{not json", t).bodyAsText())
        assertEquals(-32700, garbage["error"]!!.jsonObject["code"]!!.jsonPrimitive.int)
        assertEquals(JsonNull, garbage["id"])
        val badTool = json(mcp(rpc(6, "tools/call", buildJsonObject { put("name", "nope") }), t).bodyAsText())
        assertTrue(badTool["result"]!!.jsonObject["isError"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun rejectsMissingOrRevokedToken() = testApplication {
        val tokens = RunTokens(); val t = tokens.issue()
        routing { mcpRoute(McpServer(echo), tokens) }
        assertEquals(HttpStatusCode.Unauthorized, mcp(rpc(1, "ping"), null).status)
        assertEquals(HttpStatusCode.Unauthorized, mcp(rpc(1, "ping"), "wrong").status)
        tokens.revoke(t)
        assertEquals(HttpStatusCode.Unauthorized, mcp(rpc(1, "ping"), t).status)
    }

    @Test
    fun getIsNotAllowed() = testApplication {
        routing { mcpRoute(McpServer(echo), RunTokens()) }
        assertEquals(HttpStatusCode.MethodNotAllowed, client.get("/mcp").status)
    }

    @Test
    fun loopbackCheck() {
        listOf("127.0.0.1", "127.0.0.53", "::1", "0:0:0:0:0:0:0:1", "localhost").forEach { assertTrue(isLoopback(it), it) }
        listOf("192.168.0.162", "172.18.0.5", "100.96.124.103", "10.0.0.1", "").forEach { assertFalse(isLoopback(it), it) }
    }

    @Test
    fun tokensAreLongAndUnique() {
        val tokens = RunTokens()
        val a = tokens.issue(); val b = tokens.issue()
        assertEquals(64, a.length)
        assertTrue(a != b && tokens.valid(a) && tokens.valid(b))
        assertFalse(tokens.valid(null))
    }
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.McpServerTest'`
Expected: FAIL to compile, `Unresolved reference: ToolSet` / `mcpRoute`.

- [ ] **Step 4: Write the implementation**

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.server.request.receiveText
import io.ktor.server.response.respond
import io.ktor.server.response.respondText
import io.ktor.server.routing.Route
import io.ktor.server.routing.delete
import io.ktor.server.routing.get
import io.ktor.server.routing.post
import io.ktor.server.routing.route
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.addJsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import java.security.SecureRandom
import java.util.concurrent.ConcurrentHashMap

const val MCP_PROTOCOL_VERSION = "2025-06-18"

data class ToolResult(val text: String, val isError: Boolean = false)

/** Thrown by tools for bad input; becomes an `isError` result Claude can read and fix. */
class ToolError(message: String) : Exception(message)

interface ToolSet {
    fun definitions(): List<JsonObject>          // each {name, description, inputSchema}
    fun call(name: String, args: JsonObject): ToolResult
}

/** One random token per claude run; /mcp accepts only live ones. */
class RunTokens {
    private val live = ConcurrentHashMap.newKeySet<String>()
    private val random = SecureRandom()

    fun issue(): String {
        val bytes = ByteArray(32).also { random.nextBytes(it) }
        return bytes.joinToString("") { "%02x".format(it) }.also { live += it }
    }

    fun revoke(token: String) { live -= token }
    fun valid(token: String?): Boolean = token != null && token in live
}

/** Minimal MCP server: JSON-RPC 2.0, one JSON response per POST (streamable HTTP, JSON mode). */
class McpServer(private val tools: ToolSet) {
    fun handle(body: String): JsonObject? {
        val msg = try {
            Json.parseToJsonElement(body).jsonObject
        } catch (e: IllegalArgumentException) {
            return error(JsonNull, -32700, "parse error")
        }
        val method = (msg["method"] as? kotlinx.serialization.json.JsonPrimitive)?.contentOrNull ?: return null
        val id = msg["id"] ?: return null   // notification: nothing to answer
        val params = msg["params"] as? JsonObject ?: JsonObject(emptyMap())
        return when (method) {
            "initialize" -> result(id, buildJsonObject {
                put("protocolVersion", MCP_PROTOCOL_VERSION)
                putJsonObject("capabilities") { putJsonObject("tools") { put("listChanged", false) } }
                putJsonObject("serverInfo") { put("name", "adhd-helper-tasks"); put("version", "1") }
            })
            "ping" -> result(id, JsonObject(emptyMap()))
            "tools/list" -> result(id, buildJsonObject { put("tools", JsonArray(tools.definitions())) })
            "tools/call" -> {
                val name = params["name"]?.jsonPrimitive?.contentOrNull
                    ?: return error(id, -32602, "missing tool name")
                val args = params["arguments"] as? JsonObject ?: JsonObject(emptyMap())
                val r = try {
                    tools.call(name, args)
                } catch (e: ToolError) {
                    ToolResult(e.message ?: "invalid input", isError = true)
                } catch (e: Exception) {
                    ToolResult("tool failed: ${e.message ?: e::class.simpleName}", isError = true)
                }
                result(id, buildJsonObject {
                    putJsonArray("content") { addJsonObject { put("type", "text"); put("text", r.text) } }
                    put("isError", r.isError)
                })
            }
            else -> error(id, -32601, "method not found: $method")
        }
    }

    private fun result(id: JsonElement, result: JsonElement) = buildJsonObject {
        put("jsonrpc", "2.0"); put("id", id); put("result", result)
    }

    private fun error(id: JsonElement, code: Int, message: String) = buildJsonObject {
        put("jsonrpc", "2.0"); put("id", id)
        putJsonObject("error") { put("code", code); put("message", message) }
    }
}

fun isLoopback(address: String): Boolean =
    address == "localhost" || address == "::1" || address == "0:0:0:0:0:0:0:1" || address.startsWith("127.")

/** Mount outside the Bearer-auth block: auth here is loopback + per-run token. */
fun Route.mcpRoute(server: McpServer, tokens: RunTokens) {
    route("/mcp") {
        post {
            // `local` is the real socket peer; `origin` could be spoofed with X-Forwarded-For.
            if (!isLoopback(call.request.local.remoteAddress)) {
                call.respond(HttpStatusCode.Forbidden); return@post
            }
            if (!tokens.valid(call.request.headers["X-Run-Token"])) {
                call.respond(HttpStatusCode.Unauthorized); return@post
            }
            val out = server.handle(call.receiveText())
            if (out == null) call.respond(HttpStatusCode.Accepted)
            else call.respondText(out.toString(), ContentType.Application.Json)
        }
        get { call.respond(HttpStatusCode.MethodNotAllowed) }
        delete { call.respond(HttpStatusCode.MethodNotAllowed) }
    }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.McpServerTest'`
Expected: PASS (6 tests). If `handshakeListAndCall` gets 403, print `call.request.local.remoteAddress` in the test engine once and add that exact literal to `isLoopback` (the Ktor test engine reports `localhost`).

- [ ] **Step 6: Commit**

```bash
git add server/build.gradle.kts server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/Mcp.kt server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/McpServerTest.kt
git commit -F - <<'EOF'
feat(server): minimal MCP endpoint (JSON-RPC, loopback + run token)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 4: Task tools

**Files:**
- Create: `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/TaskTools.kt`
- Create: `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/TestStore.kt`
- Test: `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/TaskToolsTest.kt`, `McpToolsRoundTripTest.kt`

**Interfaces:**
- Consumes: Task 3 `ToolSet`, `ToolResult`, `ToolError`, `McpServer`, `mcpRoute`, `RunTokens`; Phase 3 `Completion.nextOccurrence` and `Completion.anchored` (package `com.sagunkayastha.adhdhelper.core`, already in `shared`); Phase 1 `SortKey.between`, `Ids.newId`, models; Phase 2 `SyncService.write(changes): Long`, `SyncService.snapshot(): Changes` (non-deleted rows only), `SyncService.stamp(): String` (thread-safe server HLC; never call `hlc.now()` directly on the server), `ServerDb(jdbcUrl)`, `EventBus()`.
- Produces: `class TaskTools(sync: SyncService, clock: () -> Instant = { Clock.System.now() }) : ToolSet` with tools:
  - `list_lists()` → `[{id,title}]` by sortKey
  - `find_tasks(query?, list?, due_before?, include_completed?)` → up to 50 tasks, open only by default, `due_before` inclusive, sorted by due date/time then sortKey
  - `add_task(title, list?, details?, due_date?, due_time?, repeat?, starred?, parent?)` → `{added: task}`; default list = first by sortKey, or a new "My Tasks" list if none exist; new task goes to the top of its siblings
  - `update_task(id, title?, list?, details?, due_date?|null, due_time?|null, repeat?|null, starred?)` → `{updated: task}`; JSON `null` clears; a due change clears `snoozeUntil`; moving lists moves subtasks
  - `complete_task(id)` → `{completed, next?}` or `{already_completed}`
  - `delete_task(id)` → `{deleted, subtasks_deleted}` (tombstones)
  - `add_note(text)` → `{note_id}`
  - `note_to_task(note_id, title?, list?, details?, due_date?, due_time?, repeat?, starred?)` → `{added, note_id}`, sets `note.taskId`
  - Task JSON shape: `{id, list (title), title, details?, due_date?, due_time?, starred?, completed_at?, repeat?, parent?}`; repeat JSON `{freq:"daily|weekly|monthly|yearly", every, days?:["MO",..]}`.
  - Every task the tools write goes through `Completion.anchored`, so a monthly/yearly rule set by Claude gets `anchorDay` = its due day like a device edit (Jan 31 -> Feb 28 -> Mar 31). `update_task` that moves `due_date` drops the old anchor first, so the rule re-anchors to the new day.
- Produces (test): `class TestStore` with `dir`, `db`, `hlc`, `events`, `sync`, `fun addList(title): TaskList`.

- [ ] **Step 1: Write the test fixture**

`TestStore.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import com.sagunkayastha.adhdhelper.core.SortKey
import com.sagunkayastha.adhdhelper.model.TaskList
import com.sagunkayastha.adhdhelper.server.EventBus
import com.sagunkayastha.adhdhelper.server.ServerDb
import com.sagunkayastha.adhdhelper.server.SyncService
import com.sagunkayastha.adhdhelper.sync.Changes
import com.sagunkayastha.adhdhelper.sync.Hlc
import com.sagunkayastha.adhdhelper.sync.Ids
import java.io.File
import kotlin.io.path.createTempDirectory

/** A real server store on a temp SQLite file. */
class TestStore {
    val dir: File = createTempDirectory("adhd-p6").toFile()
    val db = ServerDb("jdbc:sqlite:${File(dir, "tasks.db").path}")
    val hlc = Hlc("server") { System.currentTimeMillis() }
    val events = EventBus()
    val sync = SyncService(db, hlc, events)

    fun addList(title: String): TaskList {
        val last = sync.snapshot().lists.maxOfOrNull { it.sortKey }
        return TaskList(Ids.newId(), title, SortKey.between(last, null), sync.stamp())
            .also { sync.write(Changes(lists = listOf(it))) }
    }
}
```

- [ ] **Step 2: Write the failing tests**

`TaskToolsTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import com.sagunkayastha.adhdhelper.model.Freq
import com.sagunkayastha.adhdhelper.model.RepeatRule
import com.sagunkayastha.adhdhelper.sync.Ids
import kotlinx.datetime.DayOfWeek
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObjectBuilder
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant

class TaskToolsTest {
    private val store = TestStore()
    private val now = Instant.parse("2026-10-09T16:00:00Z")
    private val tools = TaskTools(store.sync) { now }

    private fun call(name: String, args: JsonObjectBuilder.() -> Unit = {}): ToolResult =
        tools.call(name, buildJsonObject(args))

    private fun ok(name: String, args: JsonObjectBuilder.() -> Unit = {}): JsonElement {
        val r = call(name, args)
        assertFalse(r.isError, r.text)
        return Json.parseToJsonElement(r.text)
    }

    private fun idOf(e: JsonElement, key: String = "added") = e.jsonObject[key]!!.jsonObject["id"]!!.jsonPrimitive.content
    private fun tasks() = store.sync.snapshot().tasks

    @Test
    fun definesEightToolsWithObjectSchemas() {
        val defs = tools.definitions()
        assertEquals(
            listOf("list_lists", "find_tasks", "add_task", "update_task", "complete_task", "delete_task", "add_note", "note_to_task"),
            defs.map { it["name"]!!.jsonPrimitive.content },
        )
        defs.forEach { assertEquals("object", it["inputSchema"]!!.jsonObject["type"]!!.jsonPrimitive.content) }
        val addRequired = defs[2]["inputSchema"]!!.jsonObject["required"]!!.jsonArray.map { it.jsonPrimitive.content }
        assertEquals(listOf("title"), addRequired)
    }

    @Test
    fun listListsInOrder() {
        store.addList("Personal"); store.addList("Work")
        assertEquals(listOf("Personal", "Work"), ok("list_lists").jsonArray.map { it.jsonObject["title"]!!.jsonPrimitive.content })
    }

    @Test
    fun addTaskByListNameWithTimeAndRepeat() {
        store.addList("Personal"); val work = store.addList("Work")
        val out = ok("add_task") {
            put("title", "Call mom"); put("list", "work"); put("due_date", "2026-10-10"); put("due_time", "18:00")
            putJsonObject("repeat") { put("freq", "weekly"); putJsonArray("days") { add("MO"); add("TH") } }
        }
        val t = tasks().single()
        assertEquals(work.id, t.listId)
        assertEquals(LocalDate(2026, 10, 10), t.dueDate)
        assertEquals(LocalTime(18, 0), t.dueTime)
        assertEquals(RepeatRule(Freq.WEEKLY, 1, listOf(DayOfWeek.MONDAY, DayOfWeek.THURSDAY)), t.repeat)
        val added = out.jsonObject["added"]!!.jsonObject
        assertEquals("Work", added["list"]!!.jsonPrimitive.content)
        assertEquals("18:00", added["due_time"]!!.jsonPrimitive.content)
    }

    @Test
    fun newTasksGoToTop() {
        store.addList("Personal")
        ok("add_task") { put("title", "first") }
        ok("add_task") { put("title", "second") }
        assertEquals(listOf("second", "first"), tasks().sortedBy { it.sortKey }.map { it.title })
    }

    @Test
    fun addTaskCreatesDefaultListWhenNoneExist() {
        ok("add_task") { put("title", "Water plants") }
        val list = store.sync.snapshot().lists.single()
        assertEquals("My Tasks", list.title)
        assertEquals(list.id, tasks().single().listId)
    }

    @Test
    fun addTaskRejectsBadInputAndWritesNothing() {
        store.addList("Personal")
        val unknown = call("add_task") { put("title", "x"); put("list", "Groceries") }
        assertTrue(unknown.isError && "Personal" in unknown.text, unknown.text)
        assertTrue(call("add_task") { put("title", "x"); put("due_time", "18:00") }.isError)
        assertTrue(call("add_task") { put("title", "x"); put("due_date", "tomorrow") }.isError)
        assertTrue(call("add_task") { put("title", "x"); put("due_date", "2026-10-10"); put("due_time", "6pm") }.isError)
        assertTrue(call("add_task") { put("title", "   ") }.isError)
        assertTrue(call("add_task") { put("title", "x"); putJsonObject("repeat") { put("freq", "hourly") } }.isError)
        assertTrue(tasks().isEmpty())
    }

    @Test
    fun subtasksAreOneLevelOnly() {
        store.addList("Personal")
        val parent = idOf(ok("add_task") { put("title", "Trip") })
        val child = idOf(ok("add_task") { put("title", "Pack"); put("parent", parent) })
        assertEquals(parent, tasks().single { it.id == child }.parentId)
        assertTrue(call("add_task") { put("title", "Socks"); put("parent", child) }.isError)
    }

    @Test
    fun findTasksFilters() {
        store.addList("Personal")
        ok("add_task") { put("title", "Buy milk"); put("due_date", "2026-10-09") }
        ok("add_task") { put("title", "Buy bread"); put("due_date", "2026-10-12") }
        val read = idOf(ok("add_task") { put("title", "Read book") })
        ok("complete_task") { put("id", read) }
        fun titles(e: JsonElement) = e.jsonArray.map { it.jsonObject["title"]!!.jsonPrimitive.content }
        assertEquals(listOf("Buy milk", "Buy bread"), titles(ok("find_tasks") { put("query", "BUY") }))
        assertEquals(listOf("Buy milk"), titles(ok("find_tasks") { put("due_before", "2026-10-09") }))
        assertEquals(listOf("Buy milk", "Buy bread"), titles(ok("find_tasks")))
        assertTrue("Read book" in titles(ok("find_tasks") { put("include_completed", true) }))
    }

    @Test
    fun updateTaskChangesAndClears() {
        store.addList("Personal")
        val id = idOf(ok("add_task") { put("title", "Dentist"); put("due_date", "2026-10-10"); put("due_time", "09:00") })
        val before = tasks().single()
        ok("update_task") { put("id", id); put("title", "Dentist (call first)"); put("due_time", JsonNull) }
        val after = tasks().single()
        assertEquals("Dentist (call first)", after.title)
        assertEquals(LocalDate(2026, 10, 10), after.dueDate)
        assertNull(after.dueTime)
        assertTrue(after.hlc > before.hlc)
        assertTrue(call("update_task") { put("id", "nope"); put("title", "x") }.isError)
        assertTrue(call("update_task") { put("id", id); put("due_date", JsonNull); put("due_time", "10:00") }.isError)
    }

    @Test
    fun updateTaskMovesListWithSubtasks() {
        store.addList("Personal"); val work = store.addList("Work")
        val parent = idOf(ok("add_task") { put("title", "Report") })
        ok("add_task") { put("title", "Draft"); put("parent", parent) }
        ok("update_task") { put("id", parent); put("list", "Work") }
        assertTrue(tasks().all { it.listId == work.id })
    }

    @Test
    fun completeRepeatingTaskCreatesExactlyOneNextOccurrence() {
        store.addList("Personal")
        val id = idOf(ok("add_task") {
            put("title", "Pills"); put("due_date", "2026-10-09"); put("due_time", "08:00")
            putJsonObject("repeat") { put("freq", "daily") }
        })
        val out = ok("complete_task") { put("id", id) }
        val nextId = out.jsonObject["next"]!!.jsonObject["id"]!!.jsonPrimitive.content
        assertEquals(Ids.derived("$id:2026-10-10"), nextId)
        assertEquals(now, tasks().single { it.id == id }.completedAt)
        val again = ok("complete_task") { put("id", id) }
        assertTrue("already_completed" in again.jsonObject)
        assertEquals(2, tasks().size)
        assertEquals(LocalDate(2026, 10, 10), tasks().single { it.id == nextId }.dueDate)
    }

    @Test
    fun monthlyRepeatIsAnchoredToItsDueDay() {
        store.addList("Personal")
        val id = idOf(ok("add_task") {
            put("title", "Rent"); put("due_date", "2027-01-31")
            putJsonObject("repeat") { put("freq", "monthly") }
        })
        assertEquals(31, tasks().single().repeat!!.anchorDay)
        val feb = ok("complete_task") { put("id", id) }.jsonObject["next"]!!.jsonObject["id"]!!.jsonPrimitive.content
        assertEquals(LocalDate(2027, 2, 28), tasks().single { it.id == feb }.dueDate)
        val mar = ok("complete_task") { put("id", feb) }.jsonObject["next"]!!.jsonObject["id"]!!.jsonPrimitive.content
        assertEquals(LocalDate(2027, 3, 31), tasks().single { it.id == mar }.dueDate)
        // Moving the date re-anchors.
        ok("update_task") { put("id", mar); put("due_date", "2027-04-15") }
        assertEquals(15, tasks().single { it.id == mar }.repeat!!.anchorDay)
    }

    @Test
    fun deleteTombstonesSubtasks() {
        store.addList("Personal")
        val parent = idOf(ok("add_task") { put("title", "Move house") })
        ok("add_task") { put("title", "Boxes"); put("parent", parent) }
        val out = ok("delete_task") { put("id", parent) }
        assertEquals(1, out.jsonObject["subtasks_deleted"]!!.jsonPrimitive.content.toInt())
        assertTrue(tasks().isEmpty())
    }

    @Test
    fun noteToTaskLinksNoteAndDefaultsTitle() {
        store.addList("Personal")
        val noteId = ok("add_note") { put("text", "renew passport\nneeds photo") }.jsonObject["note_id"]!!.jsonPrimitive.content
        val out = ok("note_to_task") { put("note_id", noteId); put("due_date", "2026-10-20") }
        val task = tasks().single()
        assertEquals("renew passport", task.title)
        assertEquals(task.id, idOf(out))
        assertEquals(task.id, store.sync.snapshot().notes.single().taskId)
        assertTrue(call("note_to_task") { put("note_id", noteId) }.isError)
        assertTrue(call("note_to_task") { put("note_id", "missing") }.isError)
    }

    @Test
    fun unknownToolIsAnError() {
        assertTrue(call("drop_database").isError)
        assertNotEquals("", call("drop_database").text)
    }
}
```

`McpToolsRoundTripTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.server.testing.testApplication
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.time.Instant

class McpToolsRoundTripTest {
    @Test
    fun claudeStyleSessionAddsATask() = testApplication {
        val store = TestStore().apply { addList("Personal") }
        val tokens = RunTokens(); val t = tokens.issue()
        routing { mcpRoute(McpServer(TaskTools(store.sync) { Instant.parse("2026-10-09T16:00:00Z") }), tokens) }
        suspend fun rpc(id: Int?, method: String, params: JsonObject = JsonObject(emptyMap())): String =
            client.post("/mcp") {
                header("X-Run-Token", t); contentType(ContentType.Application.Json)
                setBody(buildJsonObject {
                    put("jsonrpc", "2.0"); if (id != null) put("id", id); put("method", method); put("params", params)
                }.toString())
            }.bodyAsText()

        rpc(1, "initialize", buildJsonObject { put("protocolVersion", "2025-06-18") })
        rpc(null, "notifications/initialized")
        val tools = Json.parseToJsonElement(rpc(2, "tools/list")).jsonObject["result"]!!.jsonObject["tools"]!!.jsonArray
        assertEquals(8, tools.size)

        val call = Json.parseToJsonElement(rpc(3, "tools/call", buildJsonObject {
            put("name", "add_task")
            putJsonObject("arguments") { put("title", "Call mom"); put("due_date", "2026-10-10"); put("due_time", "18:00") }
        })).jsonObject["result"]!!.jsonObject
        assertFalse(call["isError"]!!.jsonPrimitive.boolean)
        assertEquals("Call mom", store.sync.snapshot().tasks.single().title)

        val bad = Json.parseToJsonElement(rpc(4, "tools/call", buildJsonObject {
            put("name", "add_task"); putJsonObject("arguments") { put("title", "x"); put("list", "Nope") }
        })).jsonObject["result"]!!.jsonObject
        assertTrue(bad["isError"]!!.jsonPrimitive.boolean)
    }
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.TaskToolsTest' --tests 'com.sagunkayastha.adhdhelper.server.assistant.McpToolsRoundTripTest'`
Expected: FAIL to compile, `Unresolved reference: TaskTools`.

- [ ] **Step 4: Write the implementation**

`TaskTools.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import com.sagunkayastha.adhdhelper.core.Completion
import com.sagunkayastha.adhdhelper.core.SortKey
import com.sagunkayastha.adhdhelper.model.Freq
import com.sagunkayastha.adhdhelper.model.Note
import com.sagunkayastha.adhdhelper.model.RepeatRule
import com.sagunkayastha.adhdhelper.model.Task
import com.sagunkayastha.adhdhelper.model.TaskList
import com.sagunkayastha.adhdhelper.server.SyncService
import com.sagunkayastha.adhdhelper.sync.Changes
import com.sagunkayastha.adhdhelper.sync.Ids
import kotlinx.datetime.DayOfWeek
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.add
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import kotlin.time.Clock
import kotlin.time.Instant

/** The assistant's tools. Every row is stamped with SyncService.stamp() (thread-safe server HLC) and written with SyncService.write, so it syncs like a device edit. */
class TaskTools(
    private val sync: SyncService,
    private val clock: () -> Instant = { Clock.System.now() },
) : ToolSet {

    override fun definitions(): List<JsonObject> = listOf(
        tool("list_lists", "List the user's task lists (id and title).", emptyList()),
        tool(
            "find_tasks",
            "Find tasks. With no arguments returns all open tasks. For \"what's left today\" pass due_before = today's date.",
            emptyList(),
            "query" to str("Case-insensitive text to match in title or details"),
            "list" to str("List title or id"),
            "due_before" to str("Only tasks due on or before this date, YYYY-MM-DD"),
            "include_completed" to bool("Also return completed tasks"),
        ),
        tool(
            "add_task", "Add a task. In your reply, name the list and the due date/time.", listOf("title"),
            *taskFields(nullable = false),
            "parent" to str("Id of a top-level task to put this under as a subtask"),
        ),
        tool(
            "update_task", "Change fields of a task. Pass null to clear due_date, due_time or repeat.", listOf("id"),
            "id" to str("Task id from find_tasks"),
            *taskFields(nullable = true),
        ),
        tool(
            "complete_task", "Mark a task done. A repeating task gets its next occurrence automatically.", listOf("id"),
            "id" to str("Task id from find_tasks"),
        ),
        tool("delete_task", "Delete a task and its subtasks.", listOf("id"), "id" to str("Task id from find_tasks")),
        tool("add_note", "Save a note-to-self that is not a task.", listOf("text"), "text" to str("Note text")),
        tool(
            "note_to_task", "Turn a saved note into a task and link them. title defaults to the note's first line.",
            listOf("note_id"),
            "note_id" to str("Note id"),
            *taskFields(nullable = false),
        ),
    )

    override fun call(name: String, args: JsonObject): ToolResult = try {
        val out: JsonElement = when (name) {
            "list_lists" -> listLists()
            "find_tasks" -> findTasks(args)
            "add_task" -> addTask(args)
            "update_task" -> updateTask(args)
            "complete_task" -> completeTask(args)
            "delete_task" -> deleteTask(args)
            "add_note" -> addNote(args)
            "note_to_task" -> noteToTask(args)
            else -> throw ToolError("Unknown tool: $name")
        }
        ToolResult(out.toString())
    } catch (e: ToolError) {
        ToolResult(e.message ?: "invalid input", isError = true)
    }

    // ---------- tools ----------

    private fun listLists(): JsonElement = JsonArray(
        sync.snapshot().lists.sortedBy { it.sortKey }.map { buildJsonObject { put("id", it.id); put("title", it.title) } }
    )

    private fun findTasks(args: JsonObject): JsonElement {
        val snap = sync.snapshot()
        val list = args.string("list")?.let { resolveList(snap, it) }
        val query = args.string("query")?.lowercase()
        val dueBefore = args.string("due_before")?.let(::parseDate)
        val withCompleted = args.boolean("include_completed") ?: false
        val lists = snap.lists.associateBy { it.id }
        val found = snap.tasks
            .filter { withCompleted || it.completedAt == null }
            .filter { list == null || it.listId == list.id }
            .filter { query == null || query in it.title.lowercase() || query in it.details.lowercase() }
            .filter { dueBefore == null || it.dueDate?.let { d -> d <= dueBefore } == true }
            .sortedWith(
                compareBy<Task, LocalDate?>(nullsLast()) { it.dueDate }
                    .thenBy(nullsLast<LocalTime>()) { it.dueTime }
                    .thenBy { it.sortKey }
            )
            .take(50)
            .map { taskJson(it, lists) }
        return JsonArray(found)
    }

    private fun addTask(args: JsonObject): JsonElement {
        val task = buildTask(args, sync.snapshot(), defaultTitle = null)
        sync.write(Changes(tasks = listOf(task)))
        return buildJsonObject { put("added", taskJson(task, listsById())) }
    }

    private fun updateTask(args: JsonObject): JsonElement {
        val snap = sync.snapshot()
        val old = findTask(snap, args.string("id"))
        var t = old
        args.string("title")?.trim()?.takeIf { it.isNotEmpty() }?.let { t = t.copy(title = it) }
        args.string("details")?.let { t = t.copy(details = it) }
        args.boolean("starred")?.let { t = t.copy(starred = it) }
        if ("due_date" in args) t = t.copy(dueDate = args.string("due_date")?.let(::parseDate))
        if ("due_time" in args) t = t.copy(dueTime = args.string("due_time")?.let(::parseTime))
        if (t.dueTime != null && t.dueDate == null) throw ToolError("due_time needs due_date")
        if ("repeat" in args) t = t.copy(repeat = (args["repeat"] as? JsonObject)?.let(::parseRepeat))
        if (t.dueDate != old.dueDate || t.dueTime != old.dueTime) t = t.copy(snoozeUntil = null)
        if (t.dueDate != old.dueDate) t = t.copy(repeat = t.repeat?.copy(anchorDay = null))
        t = Completion.anchored(t)
        val moved = mutableListOf<Task>()
        args.string("list")?.let { ref ->
            val target = resolveList(snap, ref)
            if (target.id != t.listId) {
                if (t.parentId != null) throw ToolError("Move the parent task instead of a subtask")
                val firstKey = snap.tasks.filter { it.listId == target.id && it.parentId == null }.minOfOrNull { it.sortKey }
                t = t.copy(listId = target.id, sortKey = SortKey.between(null, firstKey))
                snap.tasks.filter { it.parentId == old.id }.forEach { moved += it.copy(listId = target.id, hlc = sync.stamp()) }
            }
        }
        val updated = t.copy(hlc = sync.stamp())
        sync.write(Changes(tasks = listOf(updated) + moved))
        return buildJsonObject { put("updated", taskJson(updated, listsById())) }
    }

    private fun completeTask(args: JsonObject): JsonElement {
        val snap = sync.snapshot()
        val task = findTask(snap, args.string("id"))
        if (task.completedAt != null) return buildJsonObject { put("already_completed", taskJson(task, listsById())) }
        val done = task.copy(completedAt = clock(), snoozeUntil = null, hlc = sync.stamp())
        val firstKey = snap.tasks.filter { it.listId == task.listId && it.parentId == task.parentId }.minOfOrNull { it.sortKey }
        val next = Completion.nextOccurrence(task, SortKey.between(null, firstKey), sync.stamp())
            ?.takeIf { n -> snap.tasks.none { it.id == n.id } }
        sync.write(Changes(tasks = listOfNotNull(done, next)))
        val lists = listsById()
        return buildJsonObject {
            put("completed", taskJson(done, lists))
            next?.let { put("next", taskJson(it, lists)) }
        }
    }

    private fun deleteTask(args: JsonObject): JsonElement {
        val snap = sync.snapshot()
        val task = findTask(snap, args.string("id"))
        val rows = (listOf(task) + snap.tasks.filter { it.parentId == task.id })
            .map { it.copy(deleted = true, hlc = sync.stamp()) }
        sync.write(Changes(tasks = rows))
        return buildJsonObject { put("deleted", task.id); put("subtasks_deleted", rows.size - 1) }
    }

    private fun addNote(args: JsonObject): JsonElement {
        val text = args.string("text")?.trim().orEmpty()
        if (text.isEmpty()) throw ToolError("text is required")
        val note = Note(id = Ids.newId(), text = text, createdAt = clock(), hlc = sync.stamp())
        sync.write(Changes(notes = listOf(note)))
        return buildJsonObject { put("note_id", note.id) }
    }

    private fun noteToTask(args: JsonObject): JsonElement {
        val snap = sync.snapshot()
        val id = args.string("note_id") ?: throw ToolError("note_id is required")
        val note = snap.notes.firstOrNull { it.id == id } ?: throw ToolError("No note with id $id")
        note.taskId?.let { throw ToolError("Note $id is already task $it") }
        val firstLine = note.text.lineSequence().map { it.trim() }.firstOrNull { it.isNotEmpty() }?.take(200)
        val task = buildTask(args, snap, defaultTitle = firstLine)
        sync.write(Changes(tasks = listOf(task), notes = listOf(note.copy(taskId = task.id, hlc = sync.stamp()))))
        return buildJsonObject { put("added", taskJson(task, listsById())); put("note_id", id) }
    }

    // ---------- helpers ----------

    private fun buildTask(args: JsonObject, snap: Changes, defaultTitle: String?): Task {
        val title = (args.string("title") ?: defaultTitle)?.trim().orEmpty()
        if (title.isEmpty()) throw ToolError("title is required")
        val parent = args.string("parent")?.let { findTask(snap, it) }
        if (parent != null && parent.parentId != null) {
            throw ToolError("Subtasks are one level only; ${parent.id} is already a subtask")
        }
        val dueDate = args.string("due_date")?.let(::parseDate)
        val dueTime = args.string("due_time")?.let(::parseTime)
        if (dueTime != null && dueDate == null) throw ToolError("due_time needs due_date")
        val repeat = (args["repeat"] as? JsonObject)?.let(::parseRepeat)
        val list = resolveList(snap, parent?.listId ?: args.string("list"))
        val firstKey = snap.tasks.filter { it.listId == list.id && it.parentId == parent?.id }.minOfOrNull { it.sortKey }
        return Completion.anchored(
            Task(
                id = Ids.newId(), listId = list.id, parentId = parent?.id, title = title,
                details = args.string("details").orEmpty(), starred = args.boolean("starred") ?: false,
                dueDate = dueDate, dueTime = dueTime, repeat = repeat,
                sortKey = SortKey.between(null, firstKey), hlc = sync.stamp(),
            )
        )
    }

    /** Null ref = first list (creating "My Tasks" if there are none). Otherwise match id, then title ignoring case. */
    private fun resolveList(snap: Changes, ref: String?): TaskList {
        val lists = snap.lists.sortedBy { it.sortKey }
        if (ref == null) {
            return lists.firstOrNull()
                ?: TaskList(Ids.newId(), DEFAULT_LIST, SortKey.between(null, null), sync.stamp())
                    .also { sync.write(Changes(lists = listOf(it))) }
        }
        return lists.firstOrNull { it.id == ref }
            ?: lists.firstOrNull { it.title.equals(ref.trim(), ignoreCase = true) }
            ?: throw ToolError("No list named '$ref'. Lists: ${lists.joinToString { it.title }.ifEmpty { "(none)" }}")
    }

    private fun findTask(snap: Changes, id: String?): Task {
        if (id == null) throw ToolError("id is required")
        return snap.tasks.firstOrNull { it.id == id } ?: throw ToolError("No task with id $id; use find_tasks to get ids")
    }

    private fun listsById(): Map<String, TaskList> = sync.snapshot().lists.associateBy { it.id }

    private fun parseDate(s: String): LocalDate =
        try { LocalDate.parse(s.trim()) } catch (e: IllegalArgumentException) { throw ToolError("due_date must be YYYY-MM-DD, got '$s'") }

    private fun parseTime(s: String): LocalTime =
        try { LocalTime.parse(s.trim()) } catch (e: IllegalArgumentException) { throw ToolError("due_time must be HH:MM (24h), got '$s'") }

    private fun parseRepeat(o: JsonObject): RepeatRule {
        val f = o.string("freq")?.uppercase()
        val freq = Freq.entries.firstOrNull { it.name == f }
            ?: throw ToolError("repeat.freq must be daily, weekly, monthly or yearly")
        val every = (o["every"] as? JsonPrimitive)?.intOrNull ?: 1
        if (every < 1) throw ToolError("repeat.every must be at least 1")
        val days = (o["days"] as? JsonArray)?.map { e ->
            DAYS[(e as? JsonPrimitive)?.content?.uppercase()] ?: throw ToolError("repeat.days uses MO TU WE TH FR SA SU")
        } ?: emptyList()
        return RepeatRule(freq, every, if (freq == Freq.WEEKLY) days else emptyList())
    }

    private fun taskJson(t: Task, lists: Map<String, TaskList>): JsonObject = buildJsonObject {
        put("id", t.id)
        put("list", lists[t.listId]?.title ?: t.listId)
        put("title", t.title)
        if (t.details.isNotEmpty()) put("details", t.details)
        t.dueDate?.let { put("due_date", it.toString()) }
        t.dueTime?.let { put("due_time", "%02d:%02d".format(it.hour, it.minute)) }
        if (t.starred) put("starred", true)
        t.completedAt?.let { put("completed_at", it.toString()) }
        t.repeat?.let { r ->
            putJsonObject("repeat") {
                put("freq", r.freq.name.lowercase()); put("every", r.every)
                if (r.days.isNotEmpty()) putJsonArray("days") { r.days.forEach { d -> add(DAYS.entries.first { it.value == d }.key) } }
            }
        }
        t.parentId?.let { put("parent", it) }
    }

    // ---------- schema builders ----------

    private fun taskFields(nullable: Boolean): Array<Pair<String, JsonObject>> = arrayOf(
        "title" to str("Short task title"),
        "list" to str("List title or id; default is the first list"),
        "details" to str("Longer notes for the task"),
        "due_date" to str("Due date YYYY-MM-DD in the user's time zone", nullable),
        "due_time" to str("Due time HH:MM 24h, user's time zone; needs due_date; makes the phone ring", nullable),
        "repeat" to repeatSchema(nullable),
        "starred" to bool("Star the task"),
    )

    private fun tool(name: String, description: String, required: List<String>, vararg props: Pair<String, JsonObject>) =
        buildJsonObject {
            put("name", name)
            put("description", description)
            putJsonObject("inputSchema") {
                put("type", "object")
                putJsonObject("properties") { props.forEach { (k, v) -> put(k, v) } }
                putJsonArray("required") { required.forEach { add(it) } }
                put("additionalProperties", false)
            }
        }

    private fun str(description: String, nullable: Boolean = false) = buildJsonObject {
        if (nullable) putJsonArray("type") { add("string"); add("null") } else put("type", "string")
        put("description", description)
    }

    private fun bool(description: String) = buildJsonObject { put("type", "boolean"); put("description", description) }

    private fun repeatSchema(nullable: Boolean) = buildJsonObject {
        if (nullable) putJsonArray("type") { add("object"); add("null") } else put("type", "object")
        put("description", "Repeat rule, e.g. {\"freq\":\"weekly\",\"every\":1,\"days\":[\"MO\",\"TH\"]}")
        putJsonObject("properties") {
            putJsonObject("freq") {
                put("type", "string")
                putJsonArray("enum") { listOf("daily", "weekly", "monthly", "yearly").forEach { add(it) } }
            }
            putJsonObject("every") { put("type", "integer"); put("minimum", 1) }
            putJsonObject("days") {
                put("type", "array")
                putJsonObject("items") { put("type", "string"); putJsonArray("enum") { DAYS.keys.forEach { add(it) } } }
            }
        }
        putJsonArray("required") { add("freq") }
    }

    companion object {
        const val DEFAULT_LIST = "My Tasks"
        val DAYS: Map<String, DayOfWeek> = linkedMapOf(
            "MO" to DayOfWeek.MONDAY, "TU" to DayOfWeek.TUESDAY, "WE" to DayOfWeek.WEDNESDAY,
            "TH" to DayOfWeek.THURSDAY, "FR" to DayOfWeek.FRIDAY, "SA" to DayOfWeek.SATURDAY, "SU" to DayOfWeek.SUNDAY,
        )
    }
}

private fun JsonObject.string(key: String): String? = (this[key] as? JsonPrimitive)?.takeUnless { it is JsonNull }?.content
private fun JsonObject.boolean(key: String): Boolean? = (this[key] as? JsonPrimitive)?.booleanOrNull
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.TaskToolsTest' --tests 'com.sagunkayastha.adhdhelper.server.assistant.McpToolsRoundTripTest'`
Expected: PASS (15 + 1 tests).

- [ ] **Step 6: Commit**

```bash
git add server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/TaskTools.kt server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/TestStore.kt server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/TaskToolsTest.kt server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/McpToolsRoundTripTest.kt
git commit -F - <<'EOF'
feat(server): eight MCP task tools writing through SyncService

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 5: stream-json parser and system prompt

**Files:**
- Create: `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/StreamJson.kt`
- Create: `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/SystemPrompt.kt`
- Test: `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/StreamJsonTest.kt`, `SystemPromptTest.kt`

**Interfaces:**
- Produces:
  - `sealed interface StreamEvent { data class Text(val text: String); data class Result(val text: String, val sessionId: String?, val error: String?) }`
  - `object StreamJson { fun parse(line: String): StreamEvent? }` — `stream_event` with `event.delta.type == "text_delta"` → `Text`; `result` → `Result` (`error` non-null when `is_error`: `result` text, else joined `errors`, else `subtype`); anything else or bad JSON → null.
  - `object SystemPrompt { fun build(now: Instant, zone: TimeZone, lists: List<String>, noteId: String): String }`

- [ ] **Step 1: Write the failing tests**

`StreamJsonTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class StreamJsonTest {
    @Test
    fun textDeltaBecomesText() {
        val line = """{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hel"}}}"""
        assertEquals(StreamEvent.Text("Hel"), StreamJson.parse(line))
    }

    @Test
    fun otherLinesAreIgnored() {
        assertNull(StreamJson.parse("""{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"input_json_delta","partial_json":"{"}}}"""))
        assertNull(StreamJson.parse("""{"type":"system","subtype":"init","session_id":"s1"}"""))
        assertNull(StreamJson.parse("""{"type":"assistant","message":{"content":[{"type":"tool_use","name":"mcp__tasks__add_task"}]}}"""))
        assertNull(StreamJson.parse("not json"))
        assertNull(StreamJson.parse("[1,2]"))
        assertNull(StreamJson.parse(""))
    }

    @Test
    fun successResult() {
        val line = """{"type":"result","subtype":"success","is_error":false,"result":"Added to Personal.","session_id":"s1"}"""
        assertEquals(StreamEvent.Result("Added to Personal.", "s1", null), StreamJson.parse(line))
    }

    @Test
    fun errorResultPrefersResultTextThenErrorsThenSubtype() {
        assertEquals(
            StreamEvent.Result("", "s2", "No conversation found with session ID: s2"),
            StreamJson.parse("""{"type":"result","subtype":"error_during_execution","is_error":true,"result":"No conversation found with session ID: s2","session_id":"s2"}"""),
        )
        assertEquals(
            StreamEvent.Result("", null, "a; b"),
            StreamJson.parse("""{"type":"result","subtype":"error_during_execution","is_error":true,"errors":["a","b"]}"""),
        )
        assertEquals(
            StreamEvent.Result("", "s3", "error_max_turns"),
            StreamJson.parse("""{"type":"result","subtype":"error_max_turns","is_error":true,"session_id":"s3"}"""),
        )
    }
}
```

`SystemPromptTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import kotlinx.datetime.TimeZone
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.time.Instant

class SystemPromptTest {
    private val denver = TimeZone.of("America/Denver")

    @Test
    fun includesLocalDateTimeZoneListsAndNoteId() {
        val p = SystemPrompt.build(Instant.parse("2026-10-09T16:00:00Z"), denver, listOf("Personal", "Work"), "note-123")
        assertTrue("2026-10-09" in p, p)
        assertTrue("Friday" in p, p)
        assertTrue("10:00" in p, p)
        assertTrue("America/Denver" in p, p)
        assertTrue("Personal, Work" in p, p)
        assertTrue("note-123" in p, p)
        assertTrue("note_to_task" in p && "find_tasks" in p, p)
    }

    @Test
    fun dateIsLocalNotUtcNearMidnight() {   // Review Focus 3
        val p = SystemPrompt.build(Instant.parse("2026-10-10T03:30:00Z"), denver, emptyList(), "n")
        assertTrue("2026-10-09" in p, p)
        assertTrue("21:30" in p, p)
        assertFalse("2026-10-10" in p, p)
        assertTrue("(none yet)" in p, p)
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.StreamJsonTest' --tests 'com.sagunkayastha.adhdhelper.server.assistant.SystemPromptTest'`
Expected: FAIL to compile, `Unresolved reference: StreamJson` / `SystemPrompt`.

- [ ] **Step 3: Write the implementation**

`StreamJson.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject

sealed interface StreamEvent {
    data class Text(val text: String) : StreamEvent
    data class Result(val text: String, val sessionId: String?, val error: String?) : StreamEvent
}

/** Parses one line of `claude -p --output-format stream-json --include-partial-messages --verbose`. */
object StreamJson {
    fun parse(line: String): StreamEvent? {
        val o = try {
            Json.parseToJsonElement(line).jsonObject
        } catch (e: IllegalArgumentException) {
            return null
        }
        return when (o.str("type")) {
            "stream_event" -> {
                val delta = (o["event"] as? JsonObject)?.get("delta") as? JsonObject
                if (delta?.str("type") == "text_delta") delta.str("text")?.takeIf { it.isNotEmpty() }?.let { StreamEvent.Text(it) }
                else null
            }
            "result" -> {
                val sid = o.str("session_id")
                if ((o["is_error"] as? JsonPrimitive)?.booleanOrNull == true) {
                    val errors = (o["errors"] as? JsonArray)?.joinToString("; ") { (it as? JsonPrimitive)?.content ?: it.toString() }
                    val msg = o.str("result")?.takeIf { it.isNotBlank() }
                        ?: errors?.takeIf { it.isNotBlank() }
                        ?: o.str("subtype")
                        ?: "agent error"
                    StreamEvent.Result("", sid, msg)
                } else {
                    StreamEvent.Result(o.str("result").orEmpty(), sid, null)
                }
            }
            else -> null
        }
    }

    private fun JsonObject.str(key: String): String? = (this[key] as? JsonPrimitive)?.contentOrNull
}
```

`SystemPrompt.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import kotlin.time.Instant

object SystemPrompt {
    fun build(now: Instant, zone: TimeZone, lists: List<String>, noteId: String): String {
        val local = now.toLocalDateTime(zone)
        val day = local.date.dayOfWeek.name.lowercase().replaceFirstChar { it.uppercase() }
        val time = "%02d:%02d".format(local.hour, local.minute)
        val listText = lists.joinToString(", ").ifEmpty { "(none yet)" }
        return """
            You are the assistant inside ADHD Helper, a personal task app for one person with ADHD. Keep replies short: one or two sentences.
            Right now it is $day ${local.date} $time in time zone ${zone.id}. Work out "today", "tomorrow", "tonight" and weekdays from this local date.
            Task lists: $listText.
            The user's message is already saved as note $noteId.
            Rules:
            - A clear thing to do: call note_to_task with note_id "$noteId" and the title, list, due_date (YYYY-MM-DD), due_time (HH:MM, 24h) and repeat it needs. Your reply names the list and the due day and time.
            - A vague thought, idea or feeling: call no tool. Reply in one line that it is kept as a note.
            - A question about tasks ("what's left today?"): answer from find_tasks.
            - To change, finish or delete existing tasks: find them with find_tasks first, then use update_task, complete_task or delete_task.
            - All dates and times are wall-clock in ${zone.id}. Never invent ids.
        """.trimIndent()
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.StreamJsonTest' --tests 'com.sagunkayastha.adhdhelper.server.assistant.SystemPromptTest'`
Expected: PASS (4 + 2 tests).

- [ ] **Step 5: Commit**

```bash
git add server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/StreamJson.kt server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/SystemPrompt.kt server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/StreamJsonTest.kt server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/SystemPromptTest.kt
git commit -F - <<'EOF'
feat(server): claude stream-json parser and local-date system prompt

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 6: ProcessLauncher, session store, ChatRunner

**Files:**
- Create: `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/Process.kt`
- Create: `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/SessionStore.kt`
- Create: `server/src/main/sqldelight/com/sagunkayastha/adhdhelper/server/db/Setting.sq`
- Create: `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/ChatRunner.kt`
- Create: `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/FakeClaude.kt`
- Test: `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/ChatRunnerTest.kt`, `SessionStoreTest.kt`

**Interfaces:**
- Consumes: Task 3 `RunTokens`; Task 5 `StreamJson`, `StreamEvent`.
- Produces:
  - `interface RunningProcess { val stdin: OutputStream; val stdout: InputStream; val stderr: InputStream; fun waitFor(timeoutMs: Long): Int?; fun kill() }`
  - `fun interface ProcessLauncher { fun start(command: List<String>, env: Map<String, String>, cwd: File): RunningProcess }` (throws `IOException` when the binary is missing); `object SystemProcessLauncher : ProcessLauncher`
  - `interface SessionStore { fun get(): String?; fun set(id: String?) }`; `class DbSessionStore(db: ServerDb) : SessionStore` (new SQLDelight table `setting(setting_key, setting_value)` in Phase 2's `ServerDatabase`, accessed through `ServerDb.tx { settingQueries... }`; key `claude_session`). Phase 2's `ServerDb` creates the schema only for a brand-new file (`user_version == 0`), so this table exists in every DB created from now on; the production DB is first created in Phase 7, after this phase. A dev DB created before this task must be deleted.
  - `data class RunnerConfig(val cli: String = "claude", val mcpUrl: String, val workDir: File, val configDir: File? = null, val idleMs: Long = 90_000, val totalMs: Long = 300_000, val maxTurns: Int = 8)`
  - `sealed interface RunEvent { data class Delta(val text: String); data class Done(val text: String); data class Failed(val reason: String) }`
  - `class ChatRunner(launcher, config, tokens, sessions, env: () -> Map<String, String> = { System.getenv() }) { fun run(text: String, system: String, model: String): Flow<RunEvent>; fun command(system, model, mcpConfig: File, resume: String?): List<String>; companion { val ALLOWED_TOOLS: List<String>; const val RESUME_MISSING = "no conversation found" } }`
  - Behaviour: user text goes to stdin; mcp-config temp file (0600, deleted after) holds `{"mcpServers":{"tasks":{"type":"http","url":<mcpUrl>,"headers":{"X-Run-Token":<fresh token>}}}}`; token revoked after the run; env passed through unchanged plus `CLAUDE_CONFIG_DIR=<configDir>` (so `--resume` survives container restarts); a `--resume` rejection before any text → session cleared, one fresh retry; session id from the `result` line saved; idle/total timeout → process killed, `Failed("timed out waiting for Claude")`; non-zero exit without a result → `Failed(<last stderr line, redacted, ≤500 chars>)`; missing binary → `Failed("claude CLI not found")`.
- Produces (test, `FakeClaude.kt`): `class FakeProcess(lines, exit = 0, stderrText = "", hang = false, lineDelayMs = 0)` with `val input: ByteArrayOutputStream`, `@Volatile var killed`; `class FakeLauncher(vararg factories: () -> RunningProcess)` with `commands`, `envs`, `mcpConfigs`, `var onStart`; `object Canned { init(sid), delta(text), result(text, sid), errorResult(message, sid?) }`; `class MemorySessions : SessionStore`.

- [ ] **Step 1: Write the test fakes**

`FakeClaude.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.io.PipedInputStream
import java.io.PipedOutputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/** In-JVM stand-in for the claude CLI: writes canned stdout lines, then exits (or hangs until killed). */
class FakeProcess(
    private val lines: List<String>,
    private val exit: Int = 0,
    private val stderrText: String = "",
    private val hang: Boolean = false,
    private val lineDelayMs: Long = 0,
) : RunningProcess {
    val input = ByteArrayOutputStream()
    @Volatile var killed = false
    private val out = PipedOutputStream()
    private val err = PipedOutputStream()
    override val stdout: InputStream = PipedInputStream(out, 1 shl 16)
    override val stderr: InputStream = PipedInputStream(err, 1 shl 16)
    override val stdin: OutputStream get() = input
    private val finished = CountDownLatch(1)

    init {
        thread(isDaemon = true) {
            try {
                for (l in lines) {
                    if (killed) break
                    out.write((l + "\n").toByteArray()); out.flush()
                    if (lineDelayMs > 0) Thread.sleep(lineDelayMs)
                }
                if (hang) {
                    finished.await()          // keep the writer thread alive so pipes do not report "write end dead"
                } else {
                    err.write(stderrText.toByteArray()); err.close(); out.close()
                    finished.countDown()
                }
            } catch (e: IOException) {
                // killed while writing
            }
        }
    }

    override fun waitFor(timeoutMs: Long): Int? =
        if (finished.await(timeoutMs, TimeUnit.MILLISECONDS)) (if (killed) 137 else exit) else null

    override fun kill() {
        killed = true
        runCatching { out.close() }
        runCatching { err.close() }
        finished.countDown()
    }
}

class FakeLauncher(vararg factories: () -> RunningProcess) : ProcessLauncher {
    private val queue = ArrayDeque(factories.toList())
    val commands = mutableListOf<List<String>>()
    val envs = mutableListOf<Map<String, String>>()
    val mcpConfigs = mutableListOf<String>()
    var onStart: (List<String>) -> Unit = {}

    override fun start(command: List<String>, env: Map<String, String>, cwd: File): RunningProcess {
        commands += command
        envs += env
        command.indexOf("--mcp-config").takeIf { it >= 0 }?.let { mcpConfigs += File(command[it + 1]).readText() }
        onStart(command)
        return queue.removeFirst()()
    }
}

object Canned {
    fun init(sid: String) = """{"type":"system","subtype":"init","session_id":"$sid","tools":[]}"""
    fun delta(text: String) = buildJsonObject {
        put("type", "stream_event")
        putJsonObject("event") {
            put("type", "content_block_delta"); put("index", 0)
            putJsonObject("delta") { put("type", "text_delta"); put("text", text) }
        }
    }.toString()
    fun result(text: String, sid: String) = buildJsonObject {
        put("type", "result"); put("subtype", "success"); put("is_error", false); put("result", text); put("session_id", sid)
    }.toString()
    fun errorResult(message: String, sid: String?) = buildJsonObject {
        put("type", "result"); put("subtype", "error_during_execution"); put("is_error", true); put("result", message)
        if (sid != null) put("session_id", sid)
    }.toString()
}

class MemorySessions : SessionStore {
    @Volatile private var value: String? = null
    override fun get(): String? = value
    override fun set(id: String?) { value = id }
}
```

- [ ] **Step 2: Write the failing tests**

`ChatRunnerTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ChatRunnerTest {
    private val dir: File = createTempDirectory("runner").toFile()
    private val tokens = RunTokens()
    private val sessions = MemorySessions()
    private val secret = "sk-ant-oat01-secret-value-123"
    private val env = mapOf("CLAUDE_CODE_OAUTH_TOKEN" to secret, "PATH" to "/usr/bin")

    private fun runner(launcher: ProcessLauncher, idleMs: Long = 5_000, totalMs: Long = 10_000) = ChatRunner(
        launcher,
        RunnerConfig(mcpUrl = "http://127.0.0.1:8020/mcp", workDir = dir, configDir = File(dir, "cfg"), idleMs = idleMs, totalMs = totalMs),
        tokens, sessions,
    ) { env }

    private fun collect(r: ChatRunner, text: String = "buy milk", model: String = "claude-sonnet-5-5") =
        runBlocking { r.run(text, "SYSTEM", model).toList() }

    @Test
    fun streamsDeltasThenDoneAndSavesSession() {
        val proc = FakeProcess(listOf(Canned.init("s1"), Canned.delta("Added "), Canned.delta("to Personal."), Canned.result("Added to Personal.", "s1")))
        val launcher = FakeLauncher({ proc })
        val events = collect(runner(launcher))
        assertEquals(listOf(RunEvent.Delta("Added "), RunEvent.Delta("to Personal."), RunEvent.Done("Added to Personal.")), events)
        assertEquals("s1", sessions.get())
        assertEquals("buy milk", proc.input.toString())
        assertFalse("--resume" in launcher.commands.single())
    }

    @Test
    fun resumesSavedSession() {
        sessions.set("s1")
        val launcher = FakeLauncher({ FakeProcess(listOf(Canned.result("ok", "s1"))) })
        collect(runner(launcher))
        val cmd = launcher.commands.single()
        assertEquals("s1", cmd[cmd.indexOf("--resume") + 1])
    }

    @Test
    fun commandConfigAndEnvAreLockedDown() {
        var tokenLiveDuringRun = false
        val launcher = FakeLauncher({ FakeProcess(listOf(Canned.result("ok", "s1"))) })
        launcher.onStart = { cmd ->
            val path = File(cmd[cmd.indexOf("--mcp-config") + 1]).toPath()
            assertEquals(PosixFilePermissions.fromString("rw-------"), Files.getPosixFilePermissions(path))
            val tok = Json.parseToJsonElement(launcher.mcpConfigs.last()).jsonObject["mcpServers"]!!.jsonObject["tasks"]!!
                .jsonObject["headers"]!!.jsonObject["X-Run-Token"]!!.jsonPrimitive.content
            tokenLiveDuringRun = tokens.valid(tok)
        }
        collect(runner(launcher), model = "claude-haiku-5-5")
        val cmd = launcher.commands.single()
        fun after(flag: String) = cmd[cmd.indexOf(flag) + 1]
        assertEquals("claude", cmd[0])
        assertTrue("-p" in cmd && "--strict-mcp-config" in cmd && "--include-partial-messages" in cmd && "--verbose" in cmd)
        assertEquals("stream-json", after("--output-format"))
        assertEquals("", after("--tools"))
        assertEquals("local", after("--setting-sources"))
        assertEquals("bypassPermissions", after("--permission-mode"))
        assertEquals("8", after("--max-turns"))
        assertEquals("claude-haiku-5-5", after("--model"))
        assertEquals("SYSTEM", after("--system-prompt"))
        assertEquals(ChatRunner.ALLOWED_TOOLS.joinToString(","), after("--allowedTools"))
        assertEquals(8, ChatRunner.ALLOWED_TOOLS.size)
        assertTrue(ChatRunner.ALLOWED_TOOLS.all { it.startsWith("mcp__tasks__") })

        val tasks = Json.parseToJsonElement(launcher.mcpConfigs.single()).jsonObject["mcpServers"]!!.jsonObject["tasks"]!!.jsonObject
        assertEquals("http", tasks["type"]!!.jsonPrimitive.content)
        assertEquals("http://127.0.0.1:8020/mcp", tasks["url"]!!.jsonPrimitive.content)
        val tok = tasks["headers"]!!.jsonObject["X-Run-Token"]!!.jsonPrimitive.content
        assertTrue(tokenLiveDuringRun)
        assertFalse(tokens.valid(tok))                                  // revoked after the run
        assertFalse(File(after("--mcp-config")).exists())               // temp config deleted

        val childEnv = launcher.envs.single()
        assertEquals(secret, childEnv["CLAUDE_CODE_OAUTH_TOKEN"])       // the fin bug: never strip it
        assertEquals(File(dir, "cfg").path, childEnv["CLAUDE_CONFIG_DIR"])
    }

    @Test
    fun idleTimeoutKillsProcess() {
        val proc = FakeProcess(listOf(Canned.init("s1")), hang = true)
        val started = System.currentTimeMillis()
        val events = collect(runner(FakeLauncher({ proc }), idleMs = 200))
        assertEquals(RunEvent.Failed("timed out waiting for Claude"), events.last())
        assertTrue(proc.killed)
        assertTrue(System.currentTimeMillis() - started < 3_000)
    }

    @Test
    fun totalTimeoutKillsProcessEvenWhileStreaming() {
        val proc = FakeProcess(List(200) { Canned.delta("x") }, hang = true, lineDelayMs = 20)
        val events = collect(runner(FakeLauncher({ proc }), idleMs = 5_000, totalMs = 300))
        assertEquals(RunEvent.Failed("timed out waiting for Claude"), events.last())
        assertTrue(events.count { it is RunEvent.Delta } < 200)
        assertTrue(proc.killed)
    }

    @Test
    fun rejectedResumeOnStderrRetriesFresh() {
        sessions.set("old")
        val launcher = FakeLauncher(
            { FakeProcess(emptyList(), exit = 1, stderrText = "No conversation found with session ID: old\n") },
            { FakeProcess(listOf(Canned.result("Hi", "new"))) },
        )
        assertEquals(listOf<RunEvent>(RunEvent.Done("Hi")), collect(runner(launcher)))
        assertEquals("old", launcher.commands[0][launcher.commands[0].indexOf("--resume") + 1])
        assertFalse("--resume" in launcher.commands[1])
        assertEquals("new", sessions.get())
    }

    @Test
    fun rejectedResumeAsErrorResultRetriesFresh() {
        sessions.set("old")
        val launcher = FakeLauncher(
            { FakeProcess(listOf(Canned.errorResult("No conversation found with session ID: old", null)), exit = 1) },
            { FakeProcess(listOf(Canned.result("Hi", "new"))) },
        )
        assertEquals(listOf<RunEvent>(RunEvent.Done("Hi")), collect(runner(launcher)))
        assertEquals(2, launcher.commands.size)
    }

    @Test
    fun nonZeroExitWithoutResultReportsLastStderrLine() {
        val launcher = FakeLauncher({ FakeProcess(emptyList(), exit = 1, stderrText = "starting\nNot logged in · Please run /login\n") })
        assertEquals(listOf<RunEvent>(RunEvent.Failed("Not logged in · Please run /login")), collect(runner(launcher)))
    }

    @Test
    fun errorResultFailsButKeepsSession() {
        val launcher = FakeLauncher({ FakeProcess(listOf(Canned.errorResult("Reached max turns", "s9")), exit = 1) })
        assertEquals(listOf<RunEvent>(RunEvent.Failed("Reached max turns")), collect(runner(launcher)))
        assertEquals("s9", sessions.get())
    }

    @Test
    fun missingBinary() {
        val launcher = ProcessLauncher { _, _, _ -> throw IOException("Cannot run program \"claude\": error=2") }
        assertEquals(listOf<RunEvent>(RunEvent.Failed("claude CLI not found")), collect(runner(launcher)))
    }

    @Test
    fun stderrIsRedacted() {   // Review Focus 1
        val launcher = FakeLauncher({ FakeProcess(emptyList(), exit = 1, stderrText = "bad token $secret\n") })
        val reason = (collect(runner(launcher)).single() as RunEvent.Failed).reason
        assertFalse(secret in reason, reason)
        assertTrue("***" in reason, reason)
    }
}
```

`SessionStoreTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import com.sagunkayastha.adhdhelper.server.ServerDb
import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class SessionStoreTest {
    @Test
    fun setGetOverwriteClearAndSurviveReopen() {
        val file = File(createTempDirectory("session").toFile(), "tasks.db")
        val store = DbSessionStore(ServerDb("jdbc:sqlite:${file.path}"))
        assertNull(store.get())
        store.set("s1"); assertEquals("s1", store.get())
        store.set("s2"); assertEquals("s2", store.get())
        assertEquals("s2", DbSessionStore(ServerDb("jdbc:sqlite:${file.path}")).get())   // persisted across restarts
        store.set(null); assertNull(store.get())
    }
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.ChatRunnerTest' --tests 'com.sagunkayastha.adhdhelper.server.assistant.SessionStoreTest'`
Expected: FAIL to compile, `Unresolved reference: RunningProcess` / `ChatRunner` / `DbSessionStore`.

- [ ] **Step 4: Write the implementation**

`Process.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import java.io.File
import java.io.InputStream
import java.io.OutputStream
import java.util.concurrent.TimeUnit

interface RunningProcess {
    val stdin: OutputStream
    val stdout: InputStream
    val stderr: InputStream
    /** Exit code, or null if still running after [timeoutMs]. */
    fun waitFor(timeoutMs: Long): Int?
    /** Kill the process and its children; closes its streams. Safe to call twice. */
    fun kill()
}

/** Seam so tests never start a real `claude`. Throws IOException when the binary is missing. */
fun interface ProcessLauncher {
    fun start(command: List<String>, env: Map<String, String>, cwd: File): RunningProcess
}

object SystemProcessLauncher : ProcessLauncher {
    override fun start(command: List<String>, env: Map<String, String>, cwd: File): RunningProcess {
        val pb = ProcessBuilder(command).directory(cwd)
        pb.environment().clear()
        pb.environment().putAll(env)
        val p = pb.start()
        return object : RunningProcess {
            override val stdin: OutputStream = p.outputStream
            override val stdout: InputStream = p.inputStream
            override val stderr: InputStream = p.errorStream
            override fun waitFor(timeoutMs: Long): Int? =
                if (p.waitFor(timeoutMs, TimeUnit.MILLISECONDS)) p.exitValue() else null
            override fun kill() {
                p.descendants().forEach { it.destroyForcibly() }
                p.destroyForcibly()
            }
        }
    }
}
```

`Setting.sq` (next to Phase 2's `Meta.sq`; generated as `ServerDatabase.settingQueries`):

```sql
CREATE TABLE setting (
  setting_key TEXT NOT NULL PRIMARY KEY,
  setting_value TEXT NOT NULL
);

getSetting:
SELECT setting_value FROM setting WHERE setting_key = ?;

putSetting:
INSERT OR REPLACE INTO setting(setting_key, setting_value) VALUES (?, ?);

deleteSetting:
DELETE FROM setting WHERE setting_key = ?;
```

`SessionStore.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import com.sagunkayastha.adhdhelper.server.ServerDb

/** The one rolling Claude conversation id. */
interface SessionStore {
    fun get(): String?
    fun set(id: String?)
}

/** Row `claude_session` of the server DB's `setting` table (survives container restarts). */
class DbSessionStore(private val db: ServerDb) : SessionStore {
    override fun get(): String? = db.tx { settingQueries.getSetting(KEY).executeAsOneOrNull() }

    override fun set(id: String?) {
        db.tx { if (id == null) settingQueries.deleteSetting(KEY) else settingQueries.putSetting(KEY, id) }
    }

    companion object { const val KEY = "claude_session" }
}
```

`ChatRunner.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions

data class RunnerConfig(
    val cli: String = "claude",
    val mcpUrl: String,
    val workDir: File,
    val configDir: File? = null,
    val idleMs: Long = 90_000,
    val totalMs: Long = 300_000,
    val maxTurns: Int = 8,
)

sealed interface RunEvent {
    data class Delta(val text: String) : RunEvent
    data class Done(val text: String) : RunEvent
    data class Failed(val reason: String) : RunEvent
}

/** Runs one chat turn through the `claude` CLI against this server's own /mcp endpoint. */
class ChatRunner(
    private val launcher: ProcessLauncher,
    private val config: RunnerConfig,
    private val tokens: RunTokens,
    private val sessions: SessionStore,
    private val env: () -> Map<String, String> = { System.getenv() },
) {
    fun run(text: String, system: String, model: String): Flow<RunEvent> = channelFlow {
        val rejected = attempt(text, system, model, sessions.get()) { send(it) }
        if (rejected) {
            sessions.set(null)
            attempt(text, system, model, null) { send(it) }
        }
    }.flowOn(Dispatchers.IO)

    fun command(system: String, model: String, mcpConfig: File, resume: String?): List<String> = buildList {
        addAll(listOf(
            config.cli, "-p",
            "--output-format", "stream-json", "--include-partial-messages", "--verbose",
            "--tools", "",
            "--mcp-config", mcpConfig.path, "--strict-mcp-config",
            "--allowedTools", ALLOWED_TOOLS.joinToString(","),
            "--setting-sources", "local",
            "--permission-mode", "bypassPermissions",
            "--system-prompt", system,
            "--model", model,
            "--max-turns", config.maxTurns.toString(),
        ))
        if (resume != null) addAll(listOf("--resume", resume))
    }

    /** Returns true when [resume] was rejected before any output (caller retries fresh). */
    private suspend fun attempt(
        text: String, system: String, model: String, resume: String?,
        emit: suspend (RunEvent) -> Unit,
    ): Boolean {
        val token = tokens.issue()
        val cfg = writeMcpConfig(token)
        var proc: RunningProcess? = null
        try {
            proc = try {
                launcher.start(command(system, model, cfg, resume), childEnv(), config.workDir)
            } catch (e: IOException) {
                emit(RunEvent.Failed("claude CLI not found"))
                return false
            }
            val p = proc
            runCatching { p.stdin.use { it.write(text.toByteArray()) } }
            return coroutineScope {
                val stderr = async(Dispatchers.IO) { runCatching { p.stderr.readBytes().decodeToString() }.getOrDefault("") }
                val lines = Channel<String>(Channel.UNLIMITED)
                launch(Dispatchers.IO) {
                    try {
                        p.stdout.bufferedReader().forEachLine { lines.trySend(it) }
                    } catch (e: IOException) {
                        // stream closed by kill()
                    } finally {
                        lines.close()
                    }
                }
                val startedAt = System.nanoTime()
                var emitted = false
                var timedOut = false
                var result: StreamEvent.Result? = null
                while (true) {
                    val left = config.totalMs - (System.nanoTime() - startedAt) / 1_000_000
                    if (left <= 0) { timedOut = true; break }
                    val next = withTimeoutOrNull(minOf(config.idleMs, left)) { lines.receiveCatching() }
                    if (next == null) { timedOut = true; break }
                    val line = next.getOrNull() ?: break
                    when (val ev = StreamJson.parse(line)) {
                        is StreamEvent.Text -> { emitted = true; emit(RunEvent.Delta(ev.text)) }
                        is StreamEvent.Result -> result = ev
                        null -> Unit
                    }
                }
                if (timedOut) {
                    p.kill()
                    emit(RunEvent.Failed("timed out waiting for Claude"))
                    return@coroutineScope false
                }
                val exit = p.waitFor(5_000) ?: run { p.kill(); -1 }
                val err = redact(stderr.await()).trim()
                val res = result
                val failureText = if (res == null || res.error != null) "${res?.error.orEmpty()}\n$err" else ""
                if (resume != null && !emitted && failureText.contains(RESUME_MISSING, ignoreCase = true)) {
                    return@coroutineScope true
                }
                res?.sessionId?.let { sessions.set(it) }
                when {
                    res != null && res.error == null -> emit(RunEvent.Done(res.text.ifBlank { "Done." }))
                    res?.error != null -> emit(RunEvent.Failed(redact(res.error).take(500)))
                    else -> emit(RunEvent.Failed(
                        err.lines().lastOrNull { it.isNotBlank() }?.take(500) ?: "claude exited with code $exit"
                    ))
                }
                false
            }
        } finally {
            proc?.kill()
            tokens.revoke(token)
            cfg.delete()
        }
    }

    private fun childEnv(): Map<String, String> {
        val base = env()
        val dir = config.configDir ?: return base
        dir.mkdirs()
        return base + ("CLAUDE_CONFIG_DIR" to dir.path)
    }

    private fun writeMcpConfig(token: String): File {
        config.workDir.mkdirs()
        val file = Files.createTempFile(
            config.workDir.toPath(), "mcp-", ".json",
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")),
        ).toFile()
        file.writeText(buildJsonObject {
            putJsonObject("mcpServers") {
                putJsonObject("tasks") {
                    put("type", "http")
                    put("url", config.mcpUrl)
                    putJsonObject("headers") { put("X-Run-Token", token) }
                }
            }
        }.toString())
        return file
    }

    /** The OAuth token must never reach logs, SSE frames or the DB. */
    private fun redact(s: String): String {
        val secret = env()["CLAUDE_CODE_OAUTH_TOKEN"]?.takeIf { it.length >= 8 } ?: return s
        return s.replace(secret, "***")
    }

    companion object {
        const val RESUME_MISSING = "no conversation found"
        val ALLOWED_TOOLS: List<String> = listOf(
            "list_lists", "find_tasks", "add_task", "update_task",
            "complete_task", "delete_task", "add_note", "note_to_task",
        ).map { "mcp__tasks__$it" }
    }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.ChatRunnerTest' --tests 'com.sagunkayastha.adhdhelper.server.assistant.SessionStoreTest'`
Expected: PASS (11 + 1 tests).

- [ ] **Step 6: Commit**

```bash
git add server/src/main/sqldelight/com/sagunkayastha/adhdhelper/server/db/Setting.sq server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/Process.kt server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/SessionStore.kt server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/ChatRunner.kt server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/FakeClaude.kt server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/ChatRunnerTest.kt server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/SessionStoreTest.kt
git commit -F - <<'EOF'
feat(server): ChatRunner driving claude CLI with timeouts, resume fallback, redaction

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 7: Real ClaudeProbe (one-token request, cached 10 min)

**Files:**
- Create: `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/CliClaudeProbe.kt`
- Test: `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/CliClaudeProbeTest.kt`

**Interfaces:**
- Consumes: Phase 2 `fun interface ClaudeProbe { fun status(): String }` (package `com.sagunkayastha.adhdhelper.server`); Task 6 `ProcessLauncher`, `RunningProcess`, test `FakeLauncher`, `FakeProcess`, `Canned`.
- Produces: `class CliClaudeProbe(launcher: ProcessLauncher, workDir: File, env: () -> Map<String, String> = { System.getenv() }, nowMs: () -> Long = { System.currentTimeMillis() }, timeoutMs: Long = 60_000, cli: String = "claude", background: (Runnable) -> Unit = { thread(isDaemon = true) { it.run() } }) : ClaudeProbe`; constants `TTL_MS = 600_000`, `PROBE_MODEL = "claude-haiku-5-5"`.
- Semantics: token env absent/blank/`YOUR_TOKEN_HERE` → `"unauthenticated"` without starting anything; launcher throws `IOException` → `"missing"`; otherwise runs `claude -p --output-format json --tools "" --strict-mcp-config --setting-sources local --model claude-haiku-5-5 --max-turns 1` with a one-word prompt on stdin; exit 0 and `"is_error": false` → `"ok"`, anything else (incl. timeout) → `"unauthenticated"`. Every result is cached for 10 minutes. Phase 2's `/health` calls `status()` on every request (Docker healthcheck every 30 s), so only the very first call runs the CLI inline; once a cached value is older than 10 min, `status()` returns it immediately and starts one background refresh (never two at once).

- [ ] **Step 1: Write the failing test**

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import java.io.IOException
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class CliClaudeProbeTest {
    private val dir = createTempDirectory("probe").toFile()
    private val withToken = mapOf("CLAUDE_CODE_OAUTH_TOKEN" to "sk-ant-oat01-abcdefgh")
    private var now = 1_000_000L

    private fun probe(launcher: ProcessLauncher, env: Map<String, String> = withToken, background: (Runnable) -> Unit = { it.run() }) =
        CliClaudeProbe(launcher, dir, env = { env }, nowMs = { now }, timeoutMs = 2_000, background = background)

    @Test
    fun noTokenOrPlaceholderIsUnauthenticatedWithoutRunning() {
        val launcher = FakeLauncher()
        assertEquals("unauthenticated", probe(launcher, emptyMap()).status())
        assertEquals("unauthenticated", probe(launcher, mapOf("CLAUDE_CODE_OAUTH_TOKEN" to "YOUR_TOKEN_HERE")).status())
        assertEquals("unauthenticated", probe(launcher, mapOf("CLAUDE_CODE_OAUTH_TOKEN" to " ")).status())
        assertTrue(launcher.commands.isEmpty())
    }

    @Test
    fun missingBinary() {
        assertEquals("missing", probe({ _, _, _ -> throw IOException("error=2") }).status())
    }

    @Test
    fun realRequestSucceeds() {
        val launcher = FakeLauncher({ FakeProcess(listOf(Canned.result("OK", "p1"))) })
        assertEquals("ok", probe(launcher).status())
        val cmd = launcher.commands.single()
        assertEquals("claude-haiku-5-5", cmd[cmd.indexOf("--model") + 1])
        assertEquals("json", cmd[cmd.indexOf("--output-format") + 1])
        assertEquals("1", cmd[cmd.indexOf("--max-turns") + 1])
        assertEquals("sk-ant-oat01-abcdefgh", launcher.envs.single()["CLAUDE_CODE_OAUTH_TOKEN"])
    }

    @Test
    fun errorOrNonZeroExitIsUnauthenticated() {
        assertEquals("unauthenticated", probe(FakeLauncher({ FakeProcess(listOf(Canned.errorResult("Invalid API key", null)), exit = 1) })).status())
        assertEquals("unauthenticated", probe(FakeLauncher({ FakeProcess(emptyList(), exit = 1, stderrText = "Not logged in") })).status())
        assertEquals("unauthenticated", probe(FakeLauncher({ FakeProcess(emptyList(), hang = true) })).status())
    }

    @Test
    fun resultIsCachedForTenMinutes() {
        val launcher = FakeLauncher(
            { FakeProcess(listOf(Canned.result("OK", "p1"))) },
            { FakeProcess(emptyList(), exit = 1, stderrText = "Not logged in") },
        )
        val p = probe(launcher)
        assertEquals("ok", p.status())
        now += 9 * 60_000
        assertEquals("ok", p.status())
        assertEquals(1, launcher.commands.size)
        now += 2 * 60_000
        assertEquals("unauthenticated", p.status())   // background runner is inline in this test
        assertEquals(2, launcher.commands.size)
    }

    @Test
    fun staleValueIsReturnedFastWhileRefreshRunsInBackground() {
        val pending = mutableListOf<Runnable>()
        val launcher = FakeLauncher(
            { FakeProcess(listOf(Canned.result("OK", "p1"))) },
            { FakeProcess(emptyList(), exit = 1, stderrText = "Not logged in") },
        )
        val p = probe(launcher, background = { pending += it })
        assertEquals("ok", p.status())                 // first call is inline
        now += 11 * 60_000
        assertEquals("ok", p.status())                 // stale value, refresh queued
        assertEquals("ok", p.status())                 // still one refresh only
        assertEquals(1, pending.size)
        pending.single().run()
        assertEquals("unauthenticated", p.status())
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.CliClaudeProbeTest'`
Expected: FAIL to compile, `Unresolved reference: CliClaudeProbe`.

- [ ] **Step 3: Write the implementation**

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import com.sagunkayastha.adhdhelper.server.ClaudeProbe
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonObject
import java.io.File
import java.io.IOException
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/** Answers /health's `claude` field by making a real, tiny request (not `claude --version`). */
class CliClaudeProbe(
    private val launcher: ProcessLauncher,
    private val workDir: File,
    private val env: () -> Map<String, String> = { System.getenv() },
    private val nowMs: () -> Long = { System.currentTimeMillis() },
    private val timeoutMs: Long = 60_000,
    private val cli: String = "claude",
    private val background: (Runnable) -> Unit = { r -> thread(isDaemon = true) { r.run() } },
) : ClaudeProbe {
    private val lock = Any()
    @Volatile private var cached: Pair<Long, String>? = null
    private val refreshing = AtomicBoolean(false)

    override fun status(): String {
        val current = cached ?: return synchronized(lock) { cached?.second ?: refresh() }
        if (nowMs() - current.first >= TTL_MS && refreshing.compareAndSet(false, true)) {
            background(Runnable {
                try { synchronized(lock) { refresh() } } finally { refreshing.set(false) }
            })
        }
        return cached!!.second
    }

    private fun refresh(): String = check().also { cached = nowMs() to it }

    private fun check(): String {
        val e = env()
        val token = e["CLAUDE_CODE_OAUTH_TOKEN"]
        if (token.isNullOrBlank() || token == PLACEHOLDER) return UNAUTHENTICATED
        workDir.mkdirs()
        val p = try {
            launcher.start(command(), e, workDir)
        } catch (ex: IOException) {
            return MISSING
        }
        try {
            runCatching { p.stdin.use { it.write(PROMPT.toByteArray()) } }
            CompletableFuture.runAsync { runCatching { p.stderr.readBytes() } }
            val out = try {
                CompletableFuture.supplyAsync { p.stdout.readBytes().decodeToString() }.get(timeoutMs, TimeUnit.MILLISECONDS)
            } catch (ex: Exception) {
                return UNAUTHENTICATED
            }
            val exit = p.waitFor(5_000) ?: return UNAUTHENTICATED
            val last = out.lines().lastOrNull { it.isNotBlank() } ?: return UNAUTHENTICATED
            val json = runCatching { Json.parseToJsonElement(last).jsonObject }.getOrNull() ?: return UNAUTHENTICATED
            val isError = (json["is_error"] as? JsonPrimitive)?.booleanOrNull
            return if (exit == 0 && isError == false) OK else UNAUTHENTICATED
        } finally {
            p.kill()
        }
    }

    private fun command() = listOf(
        cli, "-p", "--output-format", "json", "--tools", "", "--strict-mcp-config",
        "--setting-sources", "local", "--model", PROBE_MODEL, "--max-turns", "1",
    )

    companion object {
        const val TTL_MS = 10 * 60 * 1000L
        const val PROBE_MODEL = "claude-haiku-5-5"
        const val PLACEHOLDER = "YOUR_TOKEN_HERE"
        const val PROMPT = "Reply with the single word OK."
        const val OK = "ok"
        const val UNAUTHENTICATED = "unauthenticated"
        const val MISSING = "missing"
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.CliClaudeProbeTest'`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/CliClaudeProbe.kt server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/CliClaudeProbeTest.kt
git commit -F - <<'EOF'
feat(server): ClaudeProbe that makes a real one-token request, cached 10 min

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 8: ChatService and `POST /api/v1/chat` (SSE)

**Files:**
- Create: `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/ChatService.kt`
- Test: `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/ChatServiceTest.kt`

**Interfaces:**
- Consumes: Task 1 `ChatRequest`, frames, `ChatJson`, `ChatModels.resolve`, `ChatIds`, `Sse`; Task 5 `SystemPrompt.build`; Task 6 `RunEvent`; Task 4 `TestStore`; Phase 2 `SyncService`.
- Produces:
  - `typealias Runner = (text: String, system: String, model: String) -> Flow<RunEvent>`
  - `class ChatService(sync: SyncService, runner: Runner, zone: TimeZone, clock: () -> Instant = { Clock.System.now() }) { val busy: Mutex; suspend fun handle(req: ChatRequest, emit: suspend (event: String, data: String) -> Unit) }`
  - `fun Route.chatRoute(chat: ChatService, path: String = "${Api.PREFIX}/chat")`
- Semantics: bad JSON or blank text → 400. If `busy.tryLock()` fails → 409 (nothing stored). Otherwise respond `text/event-stream`:
  1. Message already ANSWERED and its reply exists → one `done` frame, Claude not run.
  2. Write (one `SyncService.write`) the note `ChatIds.noteFor(id)` **only if absent** plus the user message with status SENT (keeps the original `createdAt` if the row exists).
  3. Run Claude with the system prompt (local date/zone, list titles, note id) and `ChatModels.resolve(req.model)`; forward each `Delta` as `delta`.
  4. `Done` → write user message ANSWERED + reply `ChatIds.replyFor(id)` (role ASSISTANT, status ANSWERED), send `done`. `Failed`, an exception, or cancellation → write user message FAILED, send `failed` (best effort). The lock is always released.

- [ ] **Step 1: Write the failing test**

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import com.sagunkayastha.adhdhelper.chat.ChatDoneFrame
import com.sagunkayastha.adhdhelper.chat.ChatFailedFrame
import com.sagunkayastha.adhdhelper.chat.ChatIds
import com.sagunkayastha.adhdhelper.chat.ChatJson
import com.sagunkayastha.adhdhelper.chat.ChatRequest
import com.sagunkayastha.adhdhelper.chat.Sse
import com.sagunkayastha.adhdhelper.chat.SseFrame
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.Note
import com.sagunkayastha.adhdhelper.model.Role
import com.sagunkayastha.adhdhelper.sync.Changes
import com.sagunkayastha.adhdhelper.sync.Ids
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.server.testing.ApplicationTestBuilder
import io.ktor.server.testing.testApplication
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.datetime.TimeZone
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.time.Instant

class ChatServiceTest {
    private val store = TestStore()
    private val zone = TimeZone.of("America/Denver")
    private val now = Instant.parse("2026-10-09T16:00:00Z")
    private var calls = 0
    private var lastModel: String? = null
    private var lastSystem: String? = null

    private fun service(runner: Runner) = ChatService(store.sync, runner, zone) { now }
    private fun canned(vararg events: RunEvent) = service { _, system, model ->
        calls++; lastModel = model; lastSystem = system; flowOf(*events)
    }

    private fun body(id: String, text: String, model: String? = null) =
        ChatJson.encodeToString(ChatRequest.serializer(), ChatRequest(id, text, model))

    private suspend fun ApplicationTestBuilder.chat(body: String): HttpResponse =
        client.post("/api/v1/chat") { contentType(ContentType.Application.Json); setBody(body) }

    private fun frames(text: String): List<SseFrame> {
        val p = Sse.Parser()
        return (text.lines() + "").mapNotNull { p.feed(it) }
    }

    @Test
    fun happyPathStreamsAndStores() = testApplication {
        store.addList("Personal")
        routing { chatRoute(canned(RunEvent.Delta("Added "), RunEvent.Delta("to Personal."), RunEvent.Done("Added to Personal."))) }
        val id = Ids.newId()
        val resp = chat(body(id, "call mom tomorrow 6pm", "claude-opus-5-5"))
        assertEquals(HttpStatusCode.OK, resp.status)
        assertTrue(resp.headers["Content-Type"]!!.startsWith("text/event-stream"))
        val f = frames(resp.bodyAsText())
        assertEquals(listOf("delta", "delta", "done"), f.map { it.event })
        val done = ChatJson.decodeFromString(ChatDoneFrame.serializer(), f[2].data)
        assertEquals("Added to Personal.", done.reply.text)
        assertEquals(ChatIds.replyFor(id), done.reply.id)
        assertEquals(ChatStatus.ANSWERED, done.message.status)

        val snap = store.sync.snapshot()
        assertEquals("call mom tomorrow 6pm", snap.notes.single { it.id == ChatIds.noteFor(id) }.text)
        assertEquals(ChatStatus.ANSWERED, snap.messages.single { it.id == id }.status)
        assertEquals(Role.ASSISTANT, snap.messages.single { it.id == ChatIds.replyFor(id) }.role)
        assertEquals("claude-opus-5-5", lastModel)
        assertTrue(ChatIds.noteFor(id) in lastSystem!! && "Personal" in lastSystem!!)
    }

    @Test
    fun unknownModelFallsBackToDefault() = testApplication {
        routing { chatRoute(canned(RunEvent.Done("ok"))) }
        chat(body(Ids.newId(), "hi", "gpt-4")).bodyAsText()
        assertEquals("claude-sonnet-5-5", lastModel)
    }

    @Test
    fun failureKeepsNoteAndMarksFailedThenRetrySucceeds() = testApplication {   // Review Focus 1 / index RF4
        var fail = true
        routing {
            chatRoute(service { _, _, _ ->
                flowOf(if (fail) RunEvent.Failed("Not logged in · Please run /login") else RunEvent.Done("Kept as a note."))
            })
        }
        val id = Ids.newId()
        val f1 = frames(chat(body(id, "maybe learn piano")).bodyAsText())
        assertEquals(listOf("failed"), f1.map { it.event })
        val failed = ChatJson.decodeFromString(ChatFailedFrame.serializer(), f1[0].data)
        assertTrue("Not logged in" in failed.reason)
        assertEquals(ChatStatus.FAILED, failed.message!!.status)
        var snap = store.sync.snapshot()
        assertEquals("maybe learn piano", snap.notes.single().text)
        assertEquals(ChatStatus.FAILED, snap.messages.single().status)

        fail = false
        val f2 = frames(chat(body(id, "maybe learn piano")).bodyAsText())
        assertEquals("done", f2.last().event)
        snap = store.sync.snapshot()
        assertEquals(1, snap.notes.size)
        assertEquals(ChatStatus.ANSWERED, snap.messages.single { it.id == id }.status)
    }

    @Test
    fun answeredMessageIsNotRunAgain() = testApplication {   // Review Focus 2
        routing { chatRoute(canned(RunEvent.Done("ok"))) }
        val id = Ids.newId()
        chat(body(id, "hello")).bodyAsText()
        val again = frames(chat(body(id, "hello")).bodyAsText())
        assertEquals(1, calls)
        assertEquals(listOf("done"), again.map { it.event })
        assertEquals(ChatIds.replyFor(id), ChatJson.decodeFromString(ChatDoneFrame.serializer(), again[0].data).reply.id)
        assertEquals(2, store.sync.snapshot().messages.size)
    }

    @Test
    fun noteAlreadySyncedFromClientIsNotRewritten() = testApplication {   // Review Focus 2
        routing { chatRoute(canned(RunEvent.Done("ok"))) }
        val id = Ids.newId()
        val clientNote = Note(id = ChatIds.noteFor(id), text = "buy milk", createdAt = now, hlc = store.sync.stamp())
        store.sync.write(Changes(notes = listOf(clientNote)))
        chat(body(id, "buy milk")).bodyAsText()
        assertEquals(clientNote.hlc, store.sync.snapshot().notes.single().hlc)
    }

    @Test
    fun secondConcurrentChatGets409() = testApplication {   // Review Focus 5
        val started = CompletableDeferred<Unit>()
        val gate = CompletableDeferred<Unit>()
        routing {
            chatRoute(service { _, _, _ -> flow { started.complete(Unit); gate.await(); emit(RunEvent.Done("ok")) } })
        }
        coroutineScope {
            val first = async { chat(body(Ids.newId(), "one")).bodyAsText() }
            started.await()
            assertEquals(HttpStatusCode.Conflict, chat(body(Ids.newId(), "two")).status)
            gate.complete(Unit)
            assertTrue("event: done" in first.await())
        }
        assertEquals(1, store.sync.snapshot().messages.count { it.role == Role.USER })
        // lock released: a third chat runs
        assertEquals(HttpStatusCode.OK, chat(body(Ids.newId(), "three")).status)
    }

    @Test
    fun runnerCrashMarksFailed() = testApplication {   // Review Focus 5
        routing { chatRoute(service { _, _, _ -> flow { emit(RunEvent.Delta("par")); throw IllegalStateException("boom") } }) }
        val id = Ids.newId()
        val f = frames(chat(body(id, "x")).bodyAsText())
        assertEquals(listOf("delta", "failed"), f.map { it.event })
        assertEquals(ChatStatus.FAILED, store.sync.snapshot().messages.single { it.id == id }.status)
        assertFalse(store.sync.snapshot().messages.any { it.status == ChatStatus.SENT })
    }

    @Test
    fun badRequests() = testApplication {
        routing { chatRoute(canned(RunEvent.Done("ok"))) }
        assertEquals(HttpStatusCode.BadRequest, chat("nope").status)
        assertEquals(HttpStatusCode.BadRequest, chat(body(Ids.newId(), "   ")).status)
        assertEquals(0, calls)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.ChatServiceTest'`
Expected: FAIL to compile, `Unresolved reference: ChatService` / `chatRoute` / `Runner`.

- [ ] **Step 3: Write the implementation**

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import com.sagunkayastha.adhdhelper.chat.ChatDeltaFrame
import com.sagunkayastha.adhdhelper.chat.ChatDoneFrame
import com.sagunkayastha.adhdhelper.chat.ChatFailedFrame
import com.sagunkayastha.adhdhelper.chat.ChatIds
import com.sagunkayastha.adhdhelper.chat.ChatJson
import com.sagunkayastha.adhdhelper.chat.ChatModels
import com.sagunkayastha.adhdhelper.chat.ChatRequest
import com.sagunkayastha.adhdhelper.chat.Sse
import com.sagunkayastha.adhdhelper.core.Api
import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.Note
import com.sagunkayastha.adhdhelper.model.Role
import com.sagunkayastha.adhdhelper.server.SyncService
import com.sagunkayastha.adhdhelper.sync.Changes
import io.ktor.http.CacheControl
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.server.request.receiveText
import io.ktor.server.response.cacheControl
import io.ktor.server.response.respond
import io.ktor.server.response.respondBytesWriter
import io.ktor.server.routing.Route
import io.ktor.server.routing.post
import io.ktor.utils.io.flush
import io.ktor.utils.io.writeStringUtf8
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.withContext
import kotlinx.datetime.TimeZone
import kotlin.time.Clock
import kotlin.time.Instant

typealias Runner = (text: String, system: String, model: String) -> Flow<RunEvent>

/** One chat turn: save first, then ask Claude, then record the outcome. One turn at a time. */
class ChatService(
    private val sync: SyncService,
    private val runner: Runner,
    private val zone: TimeZone,
    private val clock: () -> Instant = { Clock.System.now() },
) {
    val busy = Mutex()

    suspend fun handle(req: ChatRequest, emit: suspend (event: String, data: String) -> Unit) {
        val snap = sync.snapshot()
        val existing = snap.messages.firstOrNull { it.id == req.messageId }
        if (existing?.status == ChatStatus.ANSWERED) {
            val reply = snap.messages.firstOrNull { it.id == ChatIds.replyFor(req.messageId) }
            if (reply != null) {
                emit("done", ChatJson.encodeToString(ChatDoneFrame.serializer(), ChatDoneFrame(existing, reply)))
                return
            }
        }

        // Capture never depends on the model: note + message are stored before Claude runs.
        val now = clock()
        val noteId = ChatIds.noteFor(req.messageId)
        val createdAt = existing?.createdAt ?: now
        val note = if (snap.notes.none { it.id == noteId }) {
            listOf(Note(id = noteId, text = req.text, createdAt = createdAt, hlc = sync.stamp()))
        } else emptyList()
        val sent = ChatMessage(req.messageId, Role.USER, req.text, createdAt, ChatStatus.SENT, sync.stamp())
        sync.write(Changes(notes = note, messages = listOf(sent)))

        val system = SystemPrompt.build(now, zone, snap.lists.sortedBy { it.sortKey }.map { it.title }, noteId)
        var outcome: RunEvent? = null
        try {
            runner(req.text, system, ChatModels.resolve(req.model)).collect { ev ->
                if (ev is RunEvent.Delta) {
                    emit("delta", ChatJson.encodeToString(ChatDeltaFrame.serializer(), ChatDeltaFrame(ev.text)))
                } else {
                    outcome = ev
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            outcome = RunEvent.Failed("assistant error: ${e.message ?: e::class.simpleName}")
        } finally {
            withContext(NonCancellable) { finish(sent, outcome, emit) }
        }
    }

    private suspend fun finish(sent: ChatMessage, outcome: RunEvent?, emit: suspend (String, String) -> Unit) {
        if (outcome is RunEvent.Done) {
            val answered = sent.copy(status = ChatStatus.ANSWERED, hlc = sync.stamp())
            val reply = ChatMessage(
                ChatIds.replyFor(sent.id), Role.ASSISTANT, outcome.text, clock(), ChatStatus.ANSWERED, sync.stamp(),
            )
            sync.write(Changes(messages = listOf(answered, reply)))
            runCatching { emit("done", ChatJson.encodeToString(ChatDoneFrame.serializer(), ChatDoneFrame(answered, reply))) }
        } else {
            val reason = (outcome as? RunEvent.Failed)?.reason ?: "interrupted"
            val failed = sent.copy(status = ChatStatus.FAILED, hlc = sync.stamp())
            sync.write(Changes(messages = listOf(failed)))
            runCatching { emit("failed", ChatJson.encodeToString(ChatFailedFrame.serializer(), ChatFailedFrame(reason, failed))) }
        }
    }
}

/** Mount inside the Bearer-auth block. If that block is already under route(Api.PREFIX), pass path = "/chat". */
fun Route.chatRoute(chat: ChatService, path: String = "${Api.PREFIX}/chat") {
    post(path) {
        val req = try {
            ChatJson.decodeFromString(ChatRequest.serializer(), call.receiveText())
        } catch (e: IllegalArgumentException) {
            call.respond(HttpStatusCode.BadRequest, "bad chat request"); return@post
        }
        if (req.text.isBlank() || req.messageId.isBlank()) {
            call.respond(HttpStatusCode.BadRequest, "empty message"); return@post
        }
        if (!chat.busy.tryLock()) {
            call.respond(HttpStatusCode.Conflict, "assistant busy"); return@post
        }
        try {
            call.response.cacheControl(CacheControl.NoCache(null))
            call.respondBytesWriter(contentType = ContentType.Text.EventStream) {
                chat.handle(req) { event, data ->
                    writeStringUtf8(Sse.encode(event, data))
                    flush()
                }
            }
        } finally {
            chat.busy.unlock()
        }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.ChatServiceTest'`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/ChatService.kt server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/ChatServiceTest.kt
git commit -F - <<'EOF'
feat(server): /api/v1/chat SSE: save note first, stream, mark answered/failed, 409 when busy

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 9: Server wiring (ServerDeps, routes, real probe, Main)

**Files:**
- Create: `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/assistant/Assistant.kt`
- Modify (Phase 2): `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/Module.kt` (`ServerDeps`, `Application.module`), `server/src/main/kotlin/com/sagunkayastha/adhdhelper/server/Cli.kt` (`serve(config)`)
- Create: `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/TestServer.kt`
- Test: `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/AssistantWiringTest.kt`

**Interfaces:**
- Consumes: Tasks 3-8; Phase 2 `ServerConfig(dataDir, port, zone)`, `ServerDb`, `SyncService`, `DeviceAuth`, `ServerDeps(config, db, sync, events, auth, claude: ClaudeProbe = ClaudeProbe { "missing" })`, `AUTH_DEVICE`, `module`, `ClaudeProbe`, `Health`.
- Produces:
  - `class Assistant(val mcp: McpServer, val tokens: RunTokens, val chat: ChatService, val probe: ClaudeProbe) { companion fun create(config: ServerConfig, db: ServerDb, sync: SyncService, launcher: ProcessLauncher = SystemProcessLauncher, env: () -> Map<String, String> = { System.getenv() }): Assistant }` — work dir `${dataDir}/chat-cwd`, Claude config dir `${dataDir}/claude-config`, MCP URL `http://127.0.0.1:${config.port}/mcp`.
  - `ServerDeps` gains `val assistant: Assistant? = null` (last parameter, default null so Phase 2/3 tests still compile).
  - `module(deps)` mounts `mcpRoute(it.mcp, it.tokens)` outside auth and `chatRoute(it.chat)` inside `authenticate(AUTH_DEVICE) { }` when `deps.assistant != null`.
  - Production `serve(config)` builds `Assistant.create(config, db, sync)` and passes `claude = assistant.probe, assistant = assistant`.
- Produces (test): `class TestServer(launcher: ProcessLauncher = FakeLauncher(), env: Map<String, String> = emptyMap())` with `store: TestStore`, `config`, `auth`, `assistant`, `fun deps(): ServerDeps`, `fun token(): String`.

- [ ] **Step 1: Write the test fixture and the failing test**

`TestServer.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import com.sagunkayastha.adhdhelper.core.PairRequest
import com.sagunkayastha.adhdhelper.server.DeviceAuth
import com.sagunkayastha.adhdhelper.server.ServerConfig
import com.sagunkayastha.adhdhelper.server.ServerDeps

/** Full server deps on a temp dir, with a fake claude. */
class TestServer(launcher: ProcessLauncher = FakeLauncher(), env: Map<String, String> = emptyMap()) {
    val store = TestStore()
    val config = ServerConfig(dataDir = store.dir.path)
    val auth = DeviceAuth(store.db)
    val assistant = Assistant.create(config, store.db, store.sync, launcher) { env }

    fun deps() = ServerDeps(
        config = config, db = store.db, sync = store.sync, events = store.events, auth = auth,
        claude = assistant.probe, assistant = assistant,
    )

    fun token(): String = auth.pair(PairRequest(auth.newPairCode(), "test"))!!.token
}
```

`AssistantWiringTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import com.sagunkayastha.adhdhelper.chat.ChatIds
import com.sagunkayastha.adhdhelper.chat.ChatJson
import com.sagunkayastha.adhdhelper.chat.ChatRequest
import com.sagunkayastha.adhdhelper.core.Health
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.server.module
import com.sagunkayastha.adhdhelper.sync.Ids
import io.ktor.client.request.bearerAuth
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.server.testing.testApplication
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class AssistantWiringTest {
    private val json = Json { ignoreUnknownKeys = true }
    private val initialize = """{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}"""

    @Test
    fun healthReportsUnauthenticatedWithoutToken() = testApplication {   // index RF4
        val ts = TestServer(env = emptyMap())
        application { module(ts.deps()) }
        val health = json.decodeFromString(Health.serializer(), client.get("/health").bodyAsText())
        assertEquals("unauthenticated", health.claude)
    }

    @Test
    fun chatRequiresBearer() = testApplication {
        val ts = TestServer()
        application { module(ts.deps()) }
        val resp = client.post("/api/v1/chat") {
            contentType(ContentType.Application.Json)
            setBody(ChatJson.encodeToString(ChatRequest.serializer(), ChatRequest(Ids.newId(), "hi")))
        }
        assertEquals(HttpStatusCode.Unauthorized, resp.status)
    }

    @Test
    fun chatEndToEndWithFakeClaude() = testApplication {
        val ts = TestServer(
            launcher = FakeLauncher({ FakeProcess(listOf(Canned.delta("Kept "), Canned.delta("as a note."), Canned.result("Kept as a note.", "s1"))) }),
            env = mapOf("CLAUDE_CODE_OAUTH_TOKEN" to "sk-ant-oat01-abcdefgh", "PATH" to "/usr/bin"),
        )
        application { module(ts.deps()) }
        val id = Ids.newId()
        val body = client.post("/api/v1/chat") {
            bearerAuth(ts.token())
            contentType(ContentType.Application.Json)
            setBody(ChatJson.encodeToString(ChatRequest.serializer(), ChatRequest(id, "maybe learn piano")))
        }.bodyAsText()
        assertTrue("event: delta" in body && "event: done" in body, body)
        val snap = ts.store.sync.snapshot()
        assertEquals("maybe learn piano", snap.notes.single { it.id == ChatIds.noteFor(id) }.text)
        assertEquals(ChatStatus.ANSWERED, snap.messages.single { it.id == id }.status)
    }

    @Test
    fun mcpNeedsRunTokenButNotBearer() = testApplication {   // Review Focus 4
        val ts = TestServer()
        application { module(ts.deps()) }
        val noToken = client.post("/mcp") { contentType(ContentType.Application.Json); setBody(initialize) }
        assertEquals(HttpStatusCode.Unauthorized, noToken.status)
        val ok = client.post("/mcp") {
            header("X-Run-Token", ts.assistant.tokens.issue())
            contentType(ContentType.Application.Json); setBody(initialize)
        }
        assertEquals(HttpStatusCode.OK, ok.status)
        assertTrue("2025-06-18" in ok.bodyAsText())
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.assistant.AssistantWiringTest'`
Expected: FAIL to compile, `Unresolved reference: Assistant` and `No parameter with name 'assistant'`.

- [ ] **Step 3: Write `Assistant.kt`**

```kotlin
package com.sagunkayastha.adhdhelper.server.assistant

import com.sagunkayastha.adhdhelper.server.ClaudeProbe
import com.sagunkayastha.adhdhelper.server.ServerConfig
import com.sagunkayastha.adhdhelper.server.ServerDb
import com.sagunkayastha.adhdhelper.server.SyncService
import kotlinx.datetime.TimeZone
import java.io.File

/** Everything Phase 6 adds to the server, built once at startup. */
class Assistant(
    val mcp: McpServer,
    val tokens: RunTokens,
    val chat: ChatService,
    val probe: ClaudeProbe,
) {
    companion object {
        /** Server-side rows are stamped with sync.stamp() (thread-safe), never with a separate Hlc. */
        fun create(
            config: ServerConfig,
            db: ServerDb,
            sync: SyncService,
            launcher: ProcessLauncher = SystemProcessLauncher,
            env: () -> Map<String, String> = { System.getenv() },
        ): Assistant {
            val workDir = File(config.dataDir, "chat-cwd").apply { mkdirs() }
            val tokens = RunTokens()
            val runner = ChatRunner(
                launcher,
                RunnerConfig(
                    mcpUrl = "http://127.0.0.1:${config.port}/mcp",
                    workDir = workDir,
                    configDir = File(config.dataDir, "claude-config"),
                ),
                tokens,
                DbSessionStore(db),
                env,
            )
            return Assistant(
                mcp = McpServer(TaskTools(sync)),
                tokens = tokens,
                chat = ChatService(sync, runner::run, TimeZone.of(config.zone)),
                probe = CliClaudeProbe(launcher, workDir, env),
            )
        }
    }
}
```

- [ ] **Step 4: Modify Phase 2's `Module.kt` and `Cli.kt`**

1. In `Module.kt`, add a last parameter to `ServerDeps` (after `claude`) and the import `com.sagunkayastha.adhdhelper.server.assistant.Assistant`:

```kotlin
data class ServerDeps(
    val config: ServerConfig,
    val db: ServerDb,
    val sync: SyncService,
    val events: EventBus,
    val auth: DeviceAuth,
    val claude: ClaudeProbe = ClaudeProbe { "missing" },
    val assistant: Assistant? = null,
)
```

2. In `Application.module`, add the two marked lines to the `routing { }` block (imports `com.sagunkayastha.adhdhelper.server.assistant.chatRoute`, `com.sagunkayastha.adhdhelper.server.assistant.mcpRoute`):

```kotlin
    routing {
        healthRoutes(deps, apk)
        pairRoutes(deps)
        deps.assistant?.let { mcpRoute(it.mcp, it.tokens) }      // loopback + run token, no Bearer
        authenticate(AUTH_DEVICE) {
            syncRoutes(deps)
            deps.assistant?.let { chatRoute(it.chat) }            // POST /api/v1/chat
        }
    }
```

(Phase 2 Task 6 also registers `eventRoutes(deps)` and `appRoutes(apk)` inside `authenticate(AUTH_DEVICE)`; keep those lines as they are.)

3. In `Cli.kt` `serve(config)`, replace the line `val deps = ServerDeps(config, db, sync, events, DeviceAuth(db))` with:

```kotlin
    val assistant = Assistant.create(config, db, sync)
    val deps = ServerDeps(config, db, sync, events, DeviceAuth(db), claude = assistant.probe, assistant = assistant)
```

and add `import com.sagunkayastha.adhdhelper.server.assistant.Assistant`.

- [ ] **Step 5: Run the new test and the whole server suite**

Run: `gradle :server:test`
Expected: PASS, including `AssistantWiringTest` (4 tests) and all Phase 2/3 server tests unchanged.

- [ ] **Step 6: Commit**

```bash
git add server/src/main/kotlin server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/TestServer.kt server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/assistant/AssistantWiringTest.kt
git commit -F - <<'EOF'
feat(server): wire assistant (MCP, chat route, real Claude probe) into the server

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 10: ChatClient.send (SSE over Ktor client)

**Files:**
- Replace (whole file; Phase 4 Task 1 created it as the stub `class ChatClient`): `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/ChatClient.kt`
- Modify: `shared/build.gradle.kts` (jvmTest dependencies)
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/ChatClientTest.kt`, `ChatTestServer.kt`

**Interfaces:**
- Consumes: Task 1 wire types; Phase 3 `AppSettings` (`serverUrl`, `token`, `model`), `TaskRepository.applyRemote(changes)`, `Api.PREFIX`, `FileAppSettings(path)`, `TestDevice` (jvmTest).
- Produces (contract, exact constructor from the index): `sealed interface ChatEvent { data class Delta(val text: String); data class Done(val reply: ChatMessage); data class Failed(val reason: String) }`; `class ChatClient(http: HttpClient, settings: AppSettings, repo: TaskRepository) { suspend fun send(message: ChatMessage): Flow<ChatEvent>; suspend fun flushQueued() /* Task 11 */; companion { const val OFFLINE = "offline"; const val BUSY = "busy" } }`.
- Semantics of `send`: POST `${serverUrl}/api/v1/chat` with Bearer token and body `ChatRequest(message.id, message.text, settings.model)` (sent as `TextContent`, so it works with or without ContentNegotiation); per-request timeout 330 s when `HttpTimeout` is installed. `delta` → `Delta`; `done` → `repo.applyRemote(Changes(messages = [message, reply]))` then `Done(reply)`; `failed` → apply the FAILED message, `Failed(reason)`; 409 → `Failed(BUSY)`; other non-2xx → `Failed("server error <code>")`; not paired / network exception / stream ends without done-or-failed → `Failed("offline: ...")` and the local message stays QUEUED.
- Produces (jvmTest): `fun chatSettings(): AppSettings`; `ChatTestServer` helpers `answered(req)`, `failedFrame(req)`, `sseBody(vararg frames)`.

- [ ] **Step 1: Confirm the stub and add test dependencies**

Run: `grep -rn "class ChatClient\|interface ChatEvent" shared/src ui/src`
Expected: exactly one hit, `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/ChatClient.kt:` with the Phase 4 stub `class ChatClient`. Step 4 overwrites that file in place (same path, package `com.sagunkayastha.adhdhelper.client`), so `AppContainer.chat: ChatClient?` (module `:ui`) now refers to the real class without any change in `:ui`.

In `shared/build.gradle.kts`, inside `sourceSets { jvmTest.dependencies { ... } }` add (Phase 3 already added `libs.ktor.client.mock`; skip lines already present):

```kotlin
            implementation(libs.ktor.server.test.host)
```

- [ ] **Step 2: Write the test helpers**

`ChatTestServer.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.chat.ChatDeltaFrame
import com.sagunkayastha.adhdhelper.chat.ChatDoneFrame
import com.sagunkayastha.adhdhelper.chat.ChatFailedFrame
import com.sagunkayastha.adhdhelper.chat.ChatIds
import com.sagunkayastha.adhdhelper.chat.ChatJson
import com.sagunkayastha.adhdhelper.chat.ChatRequest
import com.sagunkayastha.adhdhelper.chat.Sse
import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.Role
import com.sagunkayastha.adhdhelper.sync.Hlc
import kotlin.io.path.createTempDirectory
import kotlin.time.Clock

/** Server-side rows stamped well after any device clock, so they win the merge like real server writes. */
private val serverHlc = Hlc("server") { System.currentTimeMillis() + 3_600_000 }

fun chatSettings(): AppSettings = FileAppSettings(createTempDirectory("chat-settings").resolve("settings.properties")).apply {
    serverUrl = "http://localhost"
    token = "device-token"
    model = "claude-haiku-5-5"
}

fun answered(req: ChatRequest) = ChatDoneFrame(
    message = ChatMessage(req.messageId, Role.USER, req.text, Clock.System.now(), ChatStatus.ANSWERED, serverHlc.now()),
    reply = ChatMessage(ChatIds.replyFor(req.messageId), Role.ASSISTANT, "ok: ${req.text}", Clock.System.now(), ChatStatus.ANSWERED, serverHlc.now()),
)

fun failedFrame(req: ChatRequest) = ChatFailedFrame(
    reason = "Not logged in",
    message = ChatMessage(req.messageId, Role.USER, req.text, Clock.System.now(), ChatStatus.FAILED, serverHlc.now()),
)

fun deltaSse(text: String) = Sse.encode("delta", ChatJson.encodeToString(ChatDeltaFrame.serializer(), ChatDeltaFrame(text)))
fun doneSse(req: ChatRequest) = Sse.encode("done", ChatJson.encodeToString(ChatDoneFrame.serializer(), answered(req)))
fun failedSse(req: ChatRequest) = Sse.encode("failed", ChatJson.encodeToString(ChatFailedFrame.serializer(), failedFrame(req)))
```

- [ ] **Step 3: Write the failing test**

`ChatClientTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.chat.ChatIds
import com.sagunkayastha.adhdhelper.chat.ChatJson
import com.sagunkayastha.adhdhelper.chat.ChatRequest
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.Role
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.server.request.receiveText
import io.ktor.server.response.respond
import io.ktor.server.response.respondBytesWriter
import io.ktor.server.routing.post
import io.ktor.server.testing.testApplication
import io.ktor.utils.io.writeStringUtf8
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import java.io.IOException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ChatClientTest {
    @Test
    fun streamsDeltasThenDoneAndStoresReply() = testApplication {
        var auth: String? = null
        var seen: ChatRequest? = null
        routing {
            post("/api/v1/chat") {
                auth = call.request.headers[HttpHeaders.Authorization]
                val req = ChatJson.decodeFromString(ChatRequest.serializer(), call.receiveText()).also { seen = it }
                call.respondBytesWriter(ContentType.Text.EventStream) {
                    writeStringUtf8(deltaSse("Added ")); writeStringUtf8(deltaSse("to Personal.")); writeStringUtf8(doneSse(req))
                }
            }
        }
        val d = TestDevice()
        val chat = ChatClient(client, chatSettings(), d.repo)
        val msg = d.repo.queueChat("call mom")
        val events = chat.send(msg).toList()

        assertEquals(ChatEvent.Delta("Added "), events[0])
        assertEquals(ChatEvent.Delta("to Personal."), events[1])
        val done = events[2] as ChatEvent.Done
        assertEquals(ChatIds.replyFor(msg.id), done.reply.id)
        assertEquals("Bearer device-token", auth)
        assertEquals(ChatRequest(msg.id, "call mom", "claude-haiku-5-5"), seen)

        val local = d.repo.messages().first()
        assertEquals(ChatStatus.ANSWERED, local.single { it.id == msg.id }.status)
        assertEquals(Role.ASSISTANT, local.single { it.id == done.reply.id }.role)
    }

    @Test
    fun failedFrameMarksMessageFailed() = testApplication {
        routing {
            post("/api/v1/chat") {
                val req = ChatJson.decodeFromString(ChatRequest.serializer(), call.receiveText())
                call.respondBytesWriter(ContentType.Text.EventStream) { writeStringUtf8(failedSse(req)) }
            }
        }
        val d = TestDevice()
        val msg = d.repo.queueChat("x")
        val events = ChatClient(client, chatSettings(), d.repo).send(msg).toList()
        assertEquals(listOf<ChatEvent>(ChatEvent.Failed("Not logged in")), events)
        assertEquals(ChatStatus.FAILED, d.repo.messages().first().single().status)
    }

    @Test
    fun busyServerLeavesMessageQueued() = testApplication {
        routing { post("/api/v1/chat") { call.respond(HttpStatusCode.Conflict, "assistant busy") } }
        val d = TestDevice()
        val msg = d.repo.queueChat("x")
        assertEquals(listOf<ChatEvent>(ChatEvent.Failed(ChatClient.BUSY)), ChatClient(client, chatSettings(), d.repo).send(msg).toList())
        assertEquals(ChatStatus.QUEUED, d.repo.messages().first().single().status)
    }

    @Test
    fun networkFailureIsOfflineAndKeepsQueued() = runBlocking {
        val http = HttpClient(MockEngine { throw IOException("network down") })
        val d = TestDevice()
        val msg = d.repo.queueChat("x")
        val events = ChatClient(http, chatSettings(), d.repo).send(msg).toList()
        val reason = (events.single() as ChatEvent.Failed).reason
        assertTrue(reason.startsWith(ChatClient.OFFLINE), reason)
        assertEquals(ChatStatus.QUEUED, d.repo.messages().first().single().status)
    }

    @Test
    fun notPairedIsOffline() = runBlocking {
        val d = TestDevice()
        val settings = chatSettings().apply { token = null }
        val events = ChatClient(HttpClient(MockEngine { error("must not be called") }), settings, d.repo).send(d.repo.queueChat("x")).toList()
        assertTrue((events.single() as ChatEvent.Failed).reason.startsWith(ChatClient.OFFLINE))
    }
}
```

- [ ] **Step 4: Run test to verify it fails**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.ChatClientTest'`
Expected: FAIL to compile, `Unresolved reference: ChatClient` (or, with a Phase 4 placeholder, `Unresolved reference: send` / `BUSY`).

- [ ] **Step 5: Write the implementation**

`ChatClient.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.chat.ChatDeltaFrame
import com.sagunkayastha.adhdhelper.chat.ChatDoneFrame
import com.sagunkayastha.adhdhelper.chat.ChatFailedFrame
import com.sagunkayastha.adhdhelper.chat.ChatJson
import com.sagunkayastha.adhdhelper.chat.ChatRequest
import com.sagunkayastha.adhdhelper.chat.Sse
import com.sagunkayastha.adhdhelper.core.Api
import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.sync.Changes
import io.ktor.client.HttpClient
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.pluginOrNull
import io.ktor.client.plugins.timeout
import io.ktor.client.request.accept
import io.ktor.client.request.bearerAuth
import io.ktor.client.request.preparePost
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsChannel
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.isSuccess
import io.ktor.utils.io.readUTF8Line
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.sync.Mutex

sealed interface ChatEvent {
    data class Delta(val text: String) : ChatEvent
    data class Done(val reply: ChatMessage) : ChatEvent
    data class Failed(val reason: String) : ChatEvent
}

class ChatClient(
    private val http: HttpClient,
    private val settings: AppSettings,
    private val repo: TaskRepository,
) {
    private val flushLock = Mutex()

    suspend fun send(message: ChatMessage): Flow<ChatEvent> = channelFlow {
        val base = settings.serverUrl?.trimEnd('/')
        val token = settings.token
        if (base.isNullOrEmpty() || token.isNullOrEmpty()) {
            send(ChatEvent.Failed("$OFFLINE: not paired")); return@channelFlow
        }
        var finished = false
        try {
            http.preparePost(base + Api.PREFIX + "/chat") {
                bearerAuth(token)
                accept(ContentType.Text.EventStream)
                if (http.pluginOrNull(HttpTimeout) != null) {
                    timeout { requestTimeoutMillis = 330_000; socketTimeoutMillis = 120_000 }
                }
                val req = ChatRequest(message.id, message.text, settings.model)
                setBody(TextContent(ChatJson.encodeToString(ChatRequest.serializer(), req), ContentType.Application.Json))
            }.execute { resp ->
                when {
                    resp.status == HttpStatusCode.Conflict -> { send(ChatEvent.Failed(BUSY)); finished = true }
                    !resp.status.isSuccess() -> { send(ChatEvent.Failed("server error ${resp.status.value}")); finished = true }
                    else -> {
                        val body = resp.bodyAsChannel()
                        val parser = Sse.Parser()
                        while (true) {
                            val line = body.readUTF8Line() ?: break
                            val frame = parser.feed(line) ?: continue
                            when (frame.event) {
                                "delta" -> send(ChatEvent.Delta(ChatJson.decodeFromString(ChatDeltaFrame.serializer(), frame.data).text))
                                "done" -> {
                                    val d = ChatJson.decodeFromString(ChatDoneFrame.serializer(), frame.data)
                                    repo.applyRemote(Changes(messages = listOf(d.message, d.reply)))
                                    send(ChatEvent.Done(d.reply)); finished = true
                                }
                                "failed" -> {
                                    val f = ChatJson.decodeFromString(ChatFailedFrame.serializer(), frame.data)
                                    f.message?.let { repo.applyRemote(Changes(messages = listOf(it))) }
                                    send(ChatEvent.Failed(f.reason)); finished = true
                                }
                            }
                        }
                    }
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            if (!finished) { send(ChatEvent.Failed("$OFFLINE: ${e.message ?: e::class.simpleName}")); finished = true }
        }
        if (!finished) send(ChatEvent.Failed("$OFFLINE: connection closed before the reply"))
    }

    companion object {
        /** Prefix of every Failed reason caused by transport (message stays QUEUED). */
        const val OFFLINE = "offline"
        /** Server is answering another message (409); message stays QUEUED. */
        const val BUSY = "busy"
    }
}
```

(`flushLock` is used by Task 11.)

- [ ] **Step 6: Run test to verify it passes**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.ChatClientTest'`
Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add shared/build.gradle.kts shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/ChatClient.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/ChatTestServer.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/ChatClientTest.kt
git commit -F - <<'EOF'
feat(client): ChatClient.send streams SSE and applies server rows locally

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 11: Offline queue flush

**Files:**
- Modify: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/ChatClient.kt`
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/ChatFlushTest.kt`

**Interfaces:**
- Consumes: Task 10 `ChatClient.send`, `OFFLINE`, `BUSY`; Phase 3 `SyncState(online, pending, lastError)`, `TaskRepository.messages()`.
- Produces: `suspend fun flushQueued()` (contract) — sends USER messages with status QUEUED oldest first (`createdAt`, then `id`), one at a time, under a mutex; stops at the first `OFFLINE…`/`BUSY` failure (the rest stay QUEUED); a Claude failure (`failed` frame) does not stop the loop. `fun ChatClient.flushWhenOnline(state: StateFlow<SyncState>, scope: CoroutineScope): Job` — runs `flushQueued()` each time `state.online` becomes true (including the first true after start).

- [ ] **Step 1: Write the failing test**

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.chat.ChatJson
import com.sagunkayastha.adhdhelper.chat.ChatRequest
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.Role
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.http.ContentType
import io.ktor.server.request.receiveText
import io.ktor.server.response.respondBytesWriter
import io.ktor.server.routing.post
import io.ktor.server.testing.testApplication
import io.ktor.utils.io.writeStringUtf8
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import java.io.IOException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ChatFlushTest {
    @Test
    fun flushSendsQueuedOldestFirstAndOnlyOnce() = testApplication {
        val received = mutableListOf<String>()
        routing {
            post("/api/v1/chat") {
                val req = ChatJson.decodeFromString(ChatRequest.serializer(), call.receiveText())
                synchronized(received) { received += req.text }
                call.respondBytesWriter(ContentType.Text.EventStream) {
                    writeStringUtf8(if (req.text == "two") failedSse(req) else doneSse(req))
                }
            }
        }
        val d = TestDevice()
        d.repo.queueChat("one"); Thread.sleep(3)
        d.repo.queueChat("two"); Thread.sleep(3)
        d.repo.queueChat("three")
        val chat = ChatClient(client, chatSettings(), d.repo)

        chat.flushQueued()
        assertEquals(listOf("one", "two", "three"), received)   // a Claude failure on "two" does not stop the queue
        val statuses = d.repo.messages().first().filter { it.role == Role.USER }.associate { it.text to it.status }
        assertEquals(mapOf("one" to ChatStatus.ANSWERED, "two" to ChatStatus.FAILED, "three" to ChatStatus.ANSWERED), statuses)

        chat.flushQueued()
        assertEquals(3, received.size)   // nothing QUEUED any more; FAILED waits for a manual Retry
    }

    @Test
    fun flushStopsAtFirstOfflineFailure() = runBlocking {
        var calls = 0
        val http = HttpClient(MockEngine { calls++; throw IOException("network down") })
        val d = TestDevice()
        d.repo.queueChat("one"); Thread.sleep(3); d.repo.queueChat("two")
        ChatClient(http, chatSettings(), d.repo).flushQueued()
        assertEquals(1, calls)
        assertTrue(d.repo.messages().first().all { it.status == ChatStatus.QUEUED })
    }

    @Test
    fun flushWhenOnlineSendsAfterReconnect() = testApplication {
        val got = CompletableDeferred<String>()
        routing {
            post("/api/v1/chat") {
                val req = ChatJson.decodeFromString(ChatRequest.serializer(), call.receiveText())
                got.complete(req.text)
                call.respondBytesWriter(ContentType.Text.EventStream) { writeStringUtf8(doneSse(req)) }
            }
        }
        val d = TestDevice()
        d.repo.queueChat("written while offline")
        val state = MutableStateFlow(SyncState(online = false, pending = 1, lastError = null))
        coroutineScope {
            val job = ChatClient(client, chatSettings(), d.repo).flushWhenOnline(state, this)
            state.value = SyncState(online = true, pending = 0, lastError = null)
            val text = withContext(Dispatchers.Default) { withTimeout(5_000) { got.await() } }
            assertEquals("written while offline", text)
            job.cancel()
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.ChatFlushTest'`
Expected: FAIL to compile, `Unresolved reference: flushQueued` / `flushWhenOnline`.

- [ ] **Step 3: Write the implementation**

Add these imports to `ChatClient.kt`:

```kotlin
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.Role
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.lastOrNull
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.sync.withLock
```

Add inside `class ChatClient`, after `send`:

```kotlin
    /** Sends every QUEUED user message, oldest first; stops at the first transport failure. */
    suspend fun flushQueued() {
        flushLock.withLock {
            val queued = repo.messages().first()
                .filter { it.role == Role.USER && it.status == ChatStatus.QUEUED }
                .sortedWith(compareBy({ it.createdAt }, { it.id }))
            for (m in queued) {
                val last = send(m).lastOrNull()
                if (last is ChatEvent.Failed && (last.reason == BUSY || last.reason.startsWith(OFFLINE))) break
            }
        }
    }
```

Add at file level (after the class):

```kotlin
/** Flush queued chat each time sync reports the server reachable again. */
fun ChatClient.flushWhenOnline(state: StateFlow<SyncState>, scope: CoroutineScope): Job =
    state.map { it.online }
        .distinctUntilChanged()
        .filter { it }
        .onEach { runCatching { flushQueued() } }
        .launchIn(scope)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.ChatFlushTest' --tests 'com.sagunkayastha.adhdhelper.client.ChatClientTest'`
Expected: PASS (3 + 5 tests).

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/ChatClient.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/ChatFlushTest.kt
git commit -F - <<'EOF'
feat(client): flush queued chat oldest-first when sync goes online

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 12: (provided by Phase 3) chat note id, `setChatStatus`, `noteToTask`

Nothing to implement. Phase 3 Task 2 makes `queueChat` store its note with id `Ids.derived("note:${message.id}")` (identical to `ChatIds.noteFor(message.id)`, so the server's note for the same message is the same row, Review Focus 2) and adds `setChatStatus(id, status)`; Phase 3 Task 3 adds `noteToTask(noteId, listId): Task`. Their behaviour tests (`queueChatSavesQueuedMessageAndANote`, `setChatStatusRestampsAndQueuesForSync`, `noteToTaskLinksNoteAndQueuesBothForSync`) live in Phase 3. This task only pins that the two id formulas agree.

**Files:**
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/ChatNoteIdTest.kt`

- [ ] **Step 1: Write the pinning test**

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.chat.ChatIds
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals

class ChatNoteIdTest {
    @Test
    fun queueChatNoteIdMatchesServer() = runTest {   // Review Focus 2
        val d = TestDevice()
        val msg = d.repo.queueChat("buy milk")
        assertEquals(ChatIds.noteFor(msg.id), d.repo.notes().first().single().id)
    }
}
```

- [ ] **Step 2: Run it**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.ChatNoteIdTest'`
Expected: PASS (1 test) at once: Phase 3 already writes the derived id and Task 1 defines `ChatIds` with the same formula. A failure means the formulas drifted; fix `ChatIds.noteFor`, not the repository.

- [ ] **Step 3: Commit**

```bash
git add shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/ChatNoteIdTest.kt
git commit -F - <<'EOF'
test(client): chat note id matches the server's ChatIds.noteFor

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 13: AssistantController (UI state, no Compose)

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/AssistantController.kt` (Compose-free, so it lives in `shared` next to `TaskRepository` and is tested with Phase 3's `TestDevice`; the `ui` module only renders it)
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/AssistantControllerTest.kt`

**Interfaces:**
- Consumes: Phase 3 `TaskRepository` (`messages()`, `notes()`, `queueChat`, `noteToTask`, `setChatStatus`), Task 10 `ChatEvent`, `ChatClient.OFFLINE/BUSY`; jvmTest `TestDevice`.
- Produces: `class AssistantController(repo: TaskRepository, send: suspend (ChatMessage) -> Flow<ChatEvent>, scope: CoroutineScope)` with
  - `enum class Mode { CHAT, NOTES }`; `data class UiState(val mode: Mode = Mode.CHAT, val sending: Boolean = false, val streaming: String? = null, val error: String? = null)`
  - `val state: StateFlow<UiState>`; `val messages: Flow<List<ChatMessage>>` (oldest first); `val notes: Flow<List<Note>>` (newest first); `val showPrivacyNotice: Flow<Boolean>` (true until the first chat message exists)
  - `fun setMode(mode: Mode)`; `fun submit(text: String): Job?` (null for blank); `fun retry(message: ChatMessage): Job` (sets the message back to QUEUED via `setChatStatus`, then sends); `fun makeTask(note: Note, listId: String): Job`; `fun friendly(reason: String): String`
  - `const val PRIVACY_TEXT: String` (top-level in the file)

- [ ] **Step 1: Write the failing test**

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.model.ChatStatus
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class AssistantControllerTest {
    @Test
    fun submitQueuesMessageAndStreamsDeltas() = runBlocking {
        val d = TestDevice()
        val sent = mutableListOf<ChatMessage>()
        var midStream: String? = null
        lateinit var c: AssistantController
        c = AssistantController(d.repo, { m ->
            sent += m
            flow {
                emit(ChatEvent.Delta("Added "))
                emit(ChatEvent.Delta("to Inbox."))
                midStream = c.state.value.streaming
                emit(ChatEvent.Done(m.copy(id = "reply")))
            }
        }, this)

        assertTrue(c.showPrivacyNotice.first())
        c.submit("  call mom  ")!!.join()
        assertEquals("call mom", sent.single().text)
        assertEquals("call mom", d.repo.messages().first().single().text)
        assertEquals("Added to Inbox.", midStream)
        assertNull(c.state.value.streaming)
        assertFalse(c.state.value.sending)
        assertFalse(c.showPrivacyNotice.first())
    }

    @Test
    fun blankSubmitDoesNothing() = runBlocking {
        val d = TestDevice()
        val c = AssistantController(d.repo, { flowOf() }, this)
        assertNull(c.submit("   "))
        assertTrue(d.repo.messages().first().isEmpty())
    }

    @Test
    fun failureShowsFriendlyErrorAndRetryResends() = runBlocking {
        val d = TestDevice()
        val sent = mutableListOf<ChatMessage>()
        val c = AssistantController(d.repo, { m -> sent += m; flowOf(ChatEvent.Failed("${ChatClient.OFFLINE}: down")) }, this)
        c.submit("x")!!.join()
        assertEquals("Saved. It will send when the server is reachable.", c.friendly(c.state.value.error!!))
        c.retry(sent.single()).join()
        assertEquals(2, sent.size)
        assertEquals(sent[0].id, sent[1].id)
        assertEquals(ChatStatus.QUEUED, sent[1].status)
        assertEquals(ChatStatus.QUEUED, d.repo.messages().first().single().status)
        assertEquals("Not logged in", c.friendly("Not logged in"))
        assertEquals("The assistant is busy with another message; this one will send next.", c.friendly(ChatClient.BUSY))
    }

    @Test
    fun modeToggleAndMakeTask() = runBlocking {
        val d = TestDevice()
        val c = AssistantController(d.repo, { flowOf() }, this)
        c.setMode(AssistantController.Mode.NOTES)
        assertEquals(AssistantController.Mode.NOTES, c.state.value.mode)
        val list = d.repo.addList("Inbox")
        val note = d.repo.addNote("Renew passport")
        c.makeTask(note, list.id).join()
        val linked = c.notes.first().single()
        assertEquals("Renew passport", d.repo.tasks(list.id).first().single().title)
        assertEquals(d.repo.tasks(list.id).first().single().id, linked.taskId)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.AssistantControllerTest'`
Expected: FAIL to compile, `Unresolved reference: AssistantController`.

- [ ] **Step 3: Write the implementation**

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.Note
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

const val PRIVACY_TEXT =
    "Messages you send here, and the task details the assistant looks up to answer, go to Anthropic (Claude). " +
        "Every message is also saved as a note, so nothing is lost if the assistant is down."

class AssistantController(
    private val repo: TaskRepository,
    private val send: suspend (ChatMessage) -> Flow<ChatEvent>,
    private val scope: CoroutineScope,
) {
    enum class Mode { CHAT, NOTES }

    data class UiState(
        val mode: Mode = Mode.CHAT,
        val sending: Boolean = false,
        val streaming: String? = null,
        val error: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state.asStateFlow()

    val messages: Flow<List<ChatMessage>> =
        repo.messages().map { list -> list.sortedWith(compareBy({ it.createdAt }, { it.role })) }
    val notes: Flow<List<Note>> = repo.notes().map { list -> list.sortedByDescending { it.createdAt } }
    val showPrivacyNotice: Flow<Boolean> = repo.messages().map { it.isEmpty() }

    fun setMode(mode: Mode) = _state.update { it.copy(mode = mode) }

    fun submit(text: String): Job? {
        val t = text.trim()
        if (t.isEmpty()) return null
        return scope.launch { stream(repo.queueChat(t)) }
    }

    fun retry(message: ChatMessage): Job = scope.launch {
        repo.setChatStatus(message.id, ChatStatus.QUEUED)
        stream(message.copy(status = ChatStatus.QUEUED))
    }

    fun makeTask(note: Note, listId: String): Job = scope.launch { repo.noteToTask(note.id, listId) }

    fun friendly(reason: String): String = when {
        reason.startsWith(ChatClient.OFFLINE) -> "Saved. It will send when the server is reachable."
        reason == ChatClient.BUSY -> "The assistant is busy with another message; this one will send next."
        else -> reason
    }

    private suspend fun stream(message: ChatMessage) {
        _state.update { it.copy(sending = true, streaming = "", error = null) }
        try {
            send(message).collect { ev ->
                when (ev) {
                    is ChatEvent.Delta -> _state.update { it.copy(streaming = (it.streaming ?: "") + ev.text) }
                    is ChatEvent.Failed -> _state.update { it.copy(error = ev.reason) }
                    is ChatEvent.Done -> Unit
                }
            }
        } finally {
            _state.update { it.copy(sending = false, streaming = null) }
        }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.AssistantControllerTest'`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/AssistantController.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/AssistantControllerTest.kt
git commit -F - <<'EOF'
feat(ui): AssistantController with streaming state, retry, make-task, privacy flag

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 14: Assistant screen (Chat / Notes), model picker, nav slot

**Files:**
- Create: `ui/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/ui/assistant/AssistantScreen.kt`
- Modify: `ui/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/ui/AssistantSlot.kt` (Phase 4 Task 13; `AppRoot` already routes `Screen.Assistant -> AssistantSlot(container)` and shows the drawer entry only when `container.chat != null`)

**Interfaces:**
- Consumes: Task 13 `AssistantController`, `PRIVACY_TEXT`; Task 1 `ChatModels`; Phase 4 `AppContainer(repo, sync, settings, chat, pair)`; Phase 3 `AppSettings.model`, `TaskRepository.lists()`.
- Produces: `@Composable fun AssistantScreen(container: AppContainer, chat: ChatClient)`; `@Composable fun ModelPicker(settings: AppSettings)` (public so a settings screen can reuse it).
- Layout (phone width):

```
┌──────────────────────────────────────┐
│ (Chat) ( Notes )          Sonnet 5.5▾│  <- FilterChips + ModelPicker
├──────────────────────────────────────┤
│ ┌──────────────────────────────────┐ │
│ │ Messages you send here ... go to │ │  <- privacy notice until 1st message
│ │ Anthropic (Claude). ...          │ │
│ └──────────────────────────────────┘ │
│                  ┌─────────────────┐ │
│                  │ call mom 6pm    │ │  user bubble (right)
│                  └─────────────────┘ │
│                 Not answered. [Retry]│  FAILED footer
│ ┌───────────────────┐                │
│ │ Added to Personal…│                │  streaming bubble (left)
│ └───────────────────┘                │
├──────────────────────────────────────┤
│ [Tell me a task or a thought ] [Send]│
└──────────────────────────────────────┘
Notes mode: list of notes, newest first; long-press -> menu "Make task in <List>" per list;
linked notes show "Made into a task".
```

- [ ] **Step 1: Write the screen**

```kotlin
@file:OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)

package com.sagunkayastha.adhdhelper.ui.assistant

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.sagunkayastha.adhdhelper.chat.ChatModels
import com.sagunkayastha.adhdhelper.client.AppSettings
import com.sagunkayastha.adhdhelper.client.AssistantController
import com.sagunkayastha.adhdhelper.client.AssistantController.Mode
import com.sagunkayastha.adhdhelper.client.ChatClient
import com.sagunkayastha.adhdhelper.client.PRIVACY_TEXT
import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.Note
import com.sagunkayastha.adhdhelper.model.Role
import com.sagunkayastha.adhdhelper.model.TaskList
import com.sagunkayastha.adhdhelper.ui.AppContainer

@Composable
fun AssistantScreen(container: AppContainer, chat: ChatClient) {
    val scope = rememberCoroutineScope()
    val controller = remember(chat) { AssistantController(container.repo, chat::send, scope) }
    val ui by controller.state.collectAsState()
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FilterChip(selected = ui.mode == Mode.CHAT, onClick = { controller.setMode(Mode.CHAT) }, label = { Text("Chat") })
            Spacer(Modifier.width(8.dp))
            FilterChip(selected = ui.mode == Mode.NOTES, onClick = { controller.setMode(Mode.NOTES) }, label = { Text("Notes") })
            Spacer(Modifier.weight(1f))
            ModelPicker(container.settings)
        }
        when (ui.mode) {
            Mode.CHAT -> ChatPane(controller, ui, Modifier.weight(1f))
            Mode.NOTES -> NotesPane(controller, container, Modifier.weight(1f))
        }
    }
}

@Composable
fun ModelPicker(settings: AppSettings) {
    var current by remember { mutableStateOf(ChatModels.resolve(settings.model)) }
    var open by remember { mutableStateOf(false) }
    Box {
        TextButton(onClick = { open = true }) { Text(ChatModels.label(current) + " ▾") }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            ChatModels.ALL.forEach { (id, label) ->
                DropdownMenuItem(text = { Text(label) }, onClick = { settings.model = id; current = id; open = false })
            }
        }
    }
}

@Composable
private fun ChatPane(controller: AssistantController, ui: AssistantController.UiState, modifier: Modifier) {
    val messages by controller.messages.collectAsState(emptyList())
    val showNotice by controller.showPrivacyNotice.collectAsState(false)
    var input by remember { mutableStateOf("") }
    val listState = rememberLazyListState()
    LaunchedEffect(messages.size, ui.streaming) {
        val count = messages.size + (if (ui.streaming != null) 1 else 0)
        if (count > 0) listState.animateScrollToItem(count - 1)
    }
    Column(modifier.fillMaxWidth()) {
        if (showNotice) {
            Surface(
                color = MaterialTheme.colorScheme.secondaryContainer,
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp),
            ) { Text(PRIVACY_TEXT, Modifier.padding(12.dp), style = MaterialTheme.typography.bodySmall) }
        }
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            state = listState,
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(messages, key = { it.id }) { m -> MessageBubble(m, onRetry = { controller.retry(m) }) }
            ui.streaming?.let { s -> item(key = "streaming") { Bubble(text = s.ifEmpty { "…" }, mine = false) } }
        }
        ui.error?.let {
            Text(
                controller.friendly(it),
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(horizontal = 12.dp),
            )
        }
        Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = input, onValueChange = { input = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text("Tell me a task or a thought") },
            )
            TextButton(
                onClick = { controller.submit(input); input = "" },
                enabled = input.isNotBlank() && !ui.sending,
            ) { Text("Send") }
        }
    }
}

@Composable
private fun MessageBubble(m: ChatMessage, onRetry: () -> Unit) {
    Column(Modifier.fillMaxWidth(), horizontalAlignment = if (m.role == Role.USER) Alignment.End else Alignment.Start) {
        Bubble(m.text, mine = m.role == Role.USER)
        if (m.role == Role.USER) {
            when (m.status) {
                ChatStatus.QUEUED -> Text("Waiting to send", style = MaterialTheme.typography.labelSmall)
                ChatStatus.SENT -> Text("Sending…", style = MaterialTheme.typography.labelSmall)
                ChatStatus.FAILED -> Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        "Not answered. Saved as a note.",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                    TextButton(onClick = onRetry) { Text("Retry") }
                }
                ChatStatus.ANSWERED -> Unit
            }
        }
    }
}

@Composable
private fun Bubble(text: String, mine: Boolean) {
    Box(Modifier.fillMaxWidth(), contentAlignment = if (mine) Alignment.CenterEnd else Alignment.CenterStart) {
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = if (mine) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.widthIn(max = 320.dp),
        ) { Text(text, Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) }
    }
}

@Composable
private fun NotesPane(controller: AssistantController, container: AppContainer, modifier: Modifier) {
    val notes by controller.notes.collectAsState(emptyList())
    val lists by container.repo.lists().collectAsState(emptyList())
    if (notes.isEmpty()) {
        Box(modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
            Text("No notes yet. Anything you tell the assistant is kept here.")
        }
        return
    }
    LazyColumn(
        modifier.fillMaxWidth(),
        contentPadding = PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(notes, key = { it.id }) { note -> NoteRow(note, lists) { listId -> controller.makeTask(note, listId) } }
    }
}

@Composable
private fun NoteRow(note: Note, lists: List<TaskList>, onMakeTask: (String) -> Unit) {
    var menu by remember { mutableStateOf(false) }
    Box {
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.fillMaxWidth().combinedClickable(
                onClick = {},
                onLongClick = { if (note.taskId == null && lists.isNotEmpty()) menu = true },
            ),
        ) {
            Column(Modifier.padding(12.dp)) {
                Text(note.text)
                if (note.taskId != null) Text("Made into a task", style = MaterialTheme.typography.labelSmall)
            }
        }
        DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
            lists.forEach { l ->
                DropdownMenuItem(text = { Text("Make task in ${l.title}") }, onClick = { menu = false; onMakeTask(l.id) })
            }
        }
    }
}
```

- [ ] **Step 2: Fill Phase 4's assistant slot**

Replace the whole of `ui/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/ui/AssistantSlot.kt` with:

```kotlin
package com.sagunkayastha.adhdhelper.ui

import androidx.compose.runtime.Composable
import com.sagunkayastha.adhdhelper.ui.assistant.AssistantScreen

/** Navigation slot for the assistant. Only reachable when container.chat != null (drawer entry in AppRoot). */
@Composable
fun AssistantSlot(container: AppContainer) {
    container.chat?.let { chat -> AssistantScreen(container, chat) }
}
```

- [ ] **Step 3: Compile and run the shared tests**

Run: `gradle :ui:assemble :shared:jvmTest`
Expected: `BUILD SUCCESSFUL` (the `ui` module compiles for JVM and Android); all shared tests pass.

- [ ] **Step 4: Commit**

```bash
git add ui/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/ui/assistant/AssistantScreen.kt ui/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/ui/AssistantSlot.kt
git commit -F - <<'EOF'
feat(ui): Assistant screen with Chat/Notes toggle, streaming, retry, make-task, model picker

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 15: Wire ChatClient on desktop and Android

**Files:**
- Modify: `desktopApp/src/main/kotlin/com/sagunkayastha/adhdhelper/desktop/DesktopApp.kt` (Phase 5 Task 8)
- Modify: `desktopApp/src/test/kotlin/com/sagunkayastha/adhdhelper/desktop/DesktopAppWiringTest.kt`
- Modify: `androidApp/src/main/kotlin/com/sagunkayastha/adhdhelper/android/AndroidContainer.kt` (Phase 4 Tasks 15/18; builds `AppContainer` with `chat = null`)

**Interfaces:**
- Consumes: Task 10/11 `ChatClient(http, settings, repo)`, `flushWhenOnline(state, scope)`; Phase 3 `SyncClient.state`.
- Produces: `AppContainer.chat` is a real `ChatClient` on both platforms, sharing the platform's existing `HttpClient` (it has `HttpTimeout`, so chat gets its 330 s per-request timeout); queued messages flush whenever sync goes online.

- [ ] **Step 1: Update the desktop wiring test (failing first)**

In `DesktopAppWiringTest.createsPrivateFilesAndWorkingRepository`, replace `assertEquals(null, app.container.chat)` with:

```kotlin
            assertNotNull(app.container.chat)
```

and add `import kotlin.test.assertNotNull`.

Run: `gradle :desktopApp:test --tests '*DesktopAppWiringTest'`
Expected: FAIL, `Expected value to be not null.`

- [ ] **Step 2: Wire it on desktop**

In `DesktopApp.create`, after `val syncClient = ...` and `val scope = ...`, add:

```kotlin
            val chat = ChatClient(http, settings, repo)
            chat.flushWhenOnline(syncClient.state, scope)
```

replace `chat = null, // Phase 6 wires ChatClient here` with `chat = chat,`, and add imports `com.sagunkayastha.adhdhelper.client.ChatClient`, `com.sagunkayastha.adhdhelper.client.flushWhenOnline`.

Run: `gradle :desktopApp:test --tests '*DesktopAppWiringTest'`
Expected: PASS.

- [ ] **Step 3: Wire it on Android**

In `AndroidContainer` (fields `http`, `settings`, `repo`, `sync`, `scope` from Phase 4), add directly above `val app = AppContainer(`:

```kotlin
    val chat = ChatClient(http, settings, repo).also { it.flushWhenOnline(sync.state, scope) }
```

change `chat = null,` in the `AppContainer(...)` call to `chat = chat,`, and add imports `com.sagunkayastha.adhdhelper.client.ChatClient`, `com.sagunkayastha.adhdhelper.client.flushWhenOnline`. If a Phase 4 Android test asserts `container.chat == null`, flip it to `assertNotNull` as in Step 1.

- [ ] **Step 4: Build both apps and run all tests**

Run: `gradle :androidApp:assembleDebug :desktopApp:test :ui:assemble :shared:jvmTest :server:test`
Expected: `BUILD SUCCESSFUL`, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add desktopApp/src androidApp/src
git commit -F - <<'EOF'
feat(apps): wire ChatClient and queued-chat flush on desktop and Android

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

Manual end-to-end (real `claude`, real token, both devices) is Phase 7 Task 7 Step 4.

---

## Self-Review

- **Spec coverage (Assistant section):** POST /api/v1/chat + SSE (Task 8); note saved before Claude (Task 8 step 2 of semantics, test `failureKeepsNote...`); runner flags `-p --output-format stream-json --tools "" --strict-mcp-config --mcp-config --allowedTools --permission-mode bypassPermissions --max-turns 8 --resume` (Task 6 `commandConfigAndEnvAreLockedDown`); prompt with date, zone, lists (Task 5); auth only via env token, real probe, resume fallback (Tasks 6, 7); eight MCP tools with server HLC through shared merge (Tasks 3, 4); prompt behaviour rules (Task 5); Chat/Notes toggle and long-press make-task (Tasks 13-14; `noteToTask` from Phase 3); one-time privacy notice (Task 13 `showPrivacyNotice`, Task 14); failure 90 s / 300 s → FAILED, kept as note, retryable (Tasks 6, 8, 13); offline queue (Task 11); model switch default Sonnet 5.5 (Tasks 1, 14); `/health` claude field (Tasks 7, 9).
- **Placeholders:** none; Task 9 Step 4, Task 14 Step 2 and Task 15 Step 3 edit Phase 2/4 files at named places with the exact lines.
- **Written once, in Phase 3:** `Completion` (next occurrence + month anchor), `setChatStatus`, `noteToTask`, the chat note id. Tasks 2 and 12 here only confirm/pin them.
- **Type consistency:** `RunEvent` (Task 6) is consumed by `Runner` (Task 8) and `ChatRunner::run` (Task 9); `ChatIds`/`ChatModels`/frames (Task 1) used identically in Tasks 8, 10, 12; `ChatClient.OFFLINE/BUSY` (Task 10) used in Tasks 11, 13; `TestStore`/`FakeLauncher`/`FakeProcess`/`Canned` defined before use (Tasks 4, 6).
