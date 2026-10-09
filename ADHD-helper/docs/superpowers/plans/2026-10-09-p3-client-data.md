# Phase 3: Client Data & Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give both clients a local SQLite database, a `TaskRepository` that writes every edit together with an outbox entry, a `SyncClient` that pushes the outbox and merges server changes, a live `EventsSocket`, and `AppSettings`; prove with a two-device test against the real Ktor server that offline edits converge.

**Architecture:** Everything lives in `shared/` under package `com.sagunkayastha.adhdhelper.client` (SQLDelight schema in `shared/src/commonMain/sqldelight`, platform drivers and settings in `androidMain` / `jvmMain`). Every local write runs in one SQLDelight transaction that upserts the row (with a fresh HLC) and upserts `outbox(kind, id, hlc)`. Sync drains the outbox, posts it, applies the reply with `Merge.wins`, and clears only outbox rows whose `hlc` still matches what was sent, so an edit made during a sync is sent next time. The convergence test lives in `server/src/test` and drives two `TaskRepository` instances through the server's real routes via Ktor `testApplication`.

**Tech Stack:** Kotlin 2.2.0 Multiplatform, SQLDelight 2.1.0 (android-driver, sqlite-driver, coroutines-extensions), Ktor client 3.2.0 (OkHttp on Android, CIO on JVM, WebSockets, ContentNegotiation, MockEngine for tests), kotlinx-serialization 1.9.0, kotlinx-coroutines 1.10.2 (+ `kotlinx-coroutines-test`), kotlinx-datetime 0.7.1, Android Keystore (no extra dependency) for the token.

**Spec:** `docs/superpowers/specs/2026-10-09-adhd-helper-design.md` (sections Data model, Sync, Server/auth "Pairing", Error handling). Index with the binding Shared Interface Contract: `docs/superpowers/plans/2026-10-09-00-index.md`.

## Global Constraints

- **Docker-only:** every build and test runs in the build container. Test command template (run from the repo root `ADHD-helper/`):
  `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle <task> --no-daemon`
- Nothing installed on the host (no JDK, Gradle, Android SDK). No files in `~`.
- Package root `com.sagunkayastha.adhdhelper`; this phase's code is in `com.sagunkayastha.adhdhelper.client` (generated DB code in `com.sagunkayastha.adhdhelper.client.db`).
- Names and signatures in the index's **Shared Interface Contract** are binding; this plan adds only `internal`/`private` code plus the public helpers listed in each task's **Produces** block.
- Default zone setting `America/Denver`; default model `claude-sonnet-5-5`; nag on by default.
- Device tokens are never logged or printed (not in exceptions, not in `toString`).
- Desktop settings file is created with permissions `0600`.
- If a pinned dependency version fails to resolve, use the nearest newer patch release of the same minor and note it in the commit message; never jump minors silently.
- Commits end with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
  ```

## Review Focus

1. **Same task edited offline on phone and PC, then both sync** (index RF1): both devices end with identical state equal to the later-HLC version, no duplicates, a later delete is not resurrected. Pinned in Task 10 (`offlineEditsOnBothDevicesConverge`, `laterDeleteBeatsEarlierEditAndStaysDeleted`).
2. **Repeating task completed twice quickly or on both devices** (index RF3): exactly one next occurrence, id `Ids.derived("${id}:${nextDate}")`. Pinned in Task 4 (local) and Task 10 (`repeatCompletedOnBothDevicesYieldsOneNextOccurrence`).
3. **Server unreachable for days, cursor older than the tombstone purge** (index RF5, client part): `fullResync` reply replaces local state, offline edits survive, rows purged on the server disappear locally, pending count returns to 0. Pinned in Task 8 (`cursorOlderThanPurgeDoesFullResyncAndKeepsOfflineEdits`) and Task 10 (`longOfflineBacklogSyncsInOneGo`).
4. **User edits a row while a sync request is in flight**: the edit is not dropped from the outbox and goes out on the next sync. Pinned in Task 2 (`clearOutboxKeepsRowsEditedAfterDrain`) and Task 8 (`editMadeDuringSyncIsSentNextTime`).
5. **Token revoked or server rejects rows**: a 401 clears the token, sets `lastError = "unauthorized"`, keeps local data and outbox; rejected rows leave the outbox so sync never sticks; a remote row that beats a pending local edit does not leave a stuck outbox entry. Pinned in Task 8 (`unauthorizedClearsTokenAndKeepsOutbox`, `rejectedRowsLeaveOutbox`) and Task 5 (`remoteWinOverPendingEditDropsOutboxEntry`).
6. **UI, notification-action receivers and WorkManager write at the same moment (one Android process, one `TaskRepository`)**: every HLC stamp and write happens behind one `Mutex`, so stamps never repeat or go backwards. Pinned in Task 3 (`parallelAddTaskCallsGetDistinctOrderedHlcs`).
7. **Monthly task on the 31st**: the rule is anchored to the 31st when it is set, so completing it walks Jan 31 -> Feb 28 -> Mar 31 instead of sticking at the 28th. Pinned in Task 4 (`monthly31stWalksBackToThe31st`).

---

## File Structure

| File | Responsibility |
|---|---|
| `shared/build.gradle.kts` | apply SQLDelight plugin, client deps, opt-ins (Task 1) |
| `server/build.gradle.kts` | test deps for the convergence test (Task 10) |
| `shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/TaskList.sq` | `task_list` table + queries |
| `shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/Task.sq` | `task` table + queries |
| `shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/Note.sq` | `note` table + queries |
| `shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/ChatMessage.sq` | `chat_message` table + queries |
| `shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/Outbox.sq` | `outbox(kind, id, hlc)` PK `(kind, id)` |
| `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/ClientDb.kt` | column adapters, `createClientDatabase`, `expect class DriverFactory`, `expect val DbDispatcher` |
| `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/Mappers.kt` | DB row <-> model conversion |
| `shared/src/androidMain/kotlin/com/sagunkayastha/adhdhelper/client/ClientDb.android.kt` | `AndroidSqliteDriver` factory |
| `shared/src/jvmMain/kotlin/com/sagunkayastha/adhdhelper/client/ClientDb.jvm.kt` | `JdbcSqliteDriver` file factory |
| `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/TaskRepository.kt` | all local reads/writes, outbox, remote apply |
| `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/Completion.kt` | `Completion.nextOccurrence`, `Completion.anchored` (shared with Phase 6 server tools) |
| `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/AppSettings.kt` | `AppSettings` interface + `SettingsDefaults` |
| `shared/src/jvmMain/kotlin/com/sagunkayastha/adhdhelper/client/FileAppSettings.kt` | properties file, `0600` |
| `shared/src/androidMain/kotlin/com/sagunkayastha/adhdhelper/client/AndroidAppSettings.kt` | SharedPreferences + Keystore-encrypted token |
| `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/Http.kt` | `ClientJson`, `createHttpClient()`, `UnauthorizedException`, `ServerException` |
| `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/SyncApi.kt` | `SyncApi`, `KtorSyncApi` |
| `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/SyncClient.kt` | `SyncState`, `SyncClient` |
| `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/EventsSocket.kt` | WebSocket poke listener with backoff |
| `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/*.kt` | unit tests, `TestDevice`, `FakeSyncServer` |
| `shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/CompletionTest.kt` | next occurrence + anchor tests |
| `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/ConvergenceTest.kt` | two devices + real server |

All jvmTest test commands below use the template; for brevity a step writes only the Gradle part, e.g. `gradle :shared:jvmTest --tests '...'`, meaning:
`docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests '...' --no-daemon`

---

### Task 1: Client database schema, adapters, driver factory

**Files:**
- Modify: `shared/build.gradle.kts`
- Create: `shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/TaskList.sq`
- Create: `shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/Task.sq`
- Create: `shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/Note.sq`
- Create: `shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/ChatMessage.sq`
- Create: `shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/Outbox.sq`
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/ClientDb.kt`
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/Mappers.kt`
- Create: `shared/src/androidMain/kotlin/com/sagunkayastha/adhdhelper/client/ClientDb.android.kt`
- Create: `shared/src/jvmMain/kotlin/com/sagunkayastha/adhdhelper/client/ClientDb.jvm.kt`
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/ClientDbTest.kt`

**Interfaces:**
- Consumes (Phase 1): `TaskList`, `Task`, `Note`, `ChatMessage`, `RepeatRule`, `Freq`, `Role`, `ChatStatus` from `com.sagunkayastha.adhdhelper.model`.
- Produces:
  - `com.sagunkayastha.adhdhelper.client.db.ClientDatabase` (generated) with `taskListQueries`, `taskQueries`, `noteQueries`, `chatMessageQueries`, `outboxQueries`.
  - Query names: `TaskList.sq`: `upsert(Task_list)`, `byId(id)`, `visible()`, `allIds()`, `hardDelete(id)`. `Task.sq`: `upsert(Task)`, `byId(id)`, `byList(listId)`, `starred()`, `children(parentId)`, `openTimed()`, `allIds()`, `hardDelete(id)`. `Note.sq` and `ChatMessage.sq`: `upsert`, `byId`, `visible()`, `allIds()`, `hardDelete`. `Outbox.sq`: `put(kind, id, hlc)`, `all()`, `clearIfMatch(kind, id, hlc)`, `remove(kind, id)`, `count(): Query<Long>`.
  - `fun createClientDatabase(driver: SqlDriver): ClientDatabase` (public; used by apps and by the server test).
  - `expect class DriverFactory { fun createDriver(): SqlDriver }`; Android `DriverFactory(context: Context)`, JVM `DriverFactory(path: String)`.
  - `internal expect val DbDispatcher: CoroutineDispatcher` (`Dispatchers.IO` on both platforms).
  - `internal` mappers: `Task_list.toModel()`, `TaskList.toRow()`, `db.Task.toModel()`, `model.Task.toRow()`, same for `Note`, `Chat_message`/`ChatMessage`.

- [ ] **Step 1: Check the catalog entries this phase uses**

Phase 1's `gradle/libs.versions.toml` already declares every alias used below (`libs.plugins.sqldelight`; `libs.sqldelight.android.driver`, `libs.sqldelight.sqlite.driver`, `libs.sqldelight.coroutines`, `libs.ktor.client.core`, `libs.ktor.client.okhttp`, `libs.ktor.client.cio`, `libs.ktor.client.websockets`, `libs.ktor.client.content.negotiation`, `libs.ktor.serialization.kotlinx.json`, `libs.ktor.client.mock`, `libs.ktor.server.test.host`, `libs.kotlinx.coroutines.test`), and its root `build.gradle.kts` declares `alias(libs.plugins.sqldelight) apply false`. Do not add or rename catalog keys.

Run: `grep -cE '^(sqldelight-coroutines|ktor-client-okhttp|ktor-client-cio|ktor-client-mock|kotlinx-coroutines-test) =' gradle/libs.versions.toml`
Expected: `5`.

- [ ] **Step 2: Wire SQLDelight and client dependencies into `shared/build.gradle.kts`**

Merge these into the existing file (do not remove anything Phase 1 put there):

```kotlin
plugins {
    // keep existing entries, add:
    alias(libs.plugins.sqldelight)
}

kotlin {
    // keep existing targets (androidTarget(), jvm()) and settings, add:
    compilerOptions {
        freeCompilerArgs.add("-Xexpect-actual-classes")
    }
    sourceSets.all {
        languageSettings.optIn("kotlin.time.ExperimentalTime")
    }
    sourceSets {
        commonMain.dependencies {
            implementation(libs.sqldelight.coroutines)
            api(libs.ktor.client.core)
            implementation(libs.ktor.client.websockets)
            implementation(libs.ktor.client.content.negotiation)
            implementation(libs.ktor.serialization.kotlinx.json)
        }
        androidMain.dependencies {
            implementation(libs.sqldelight.android.driver)
            implementation(libs.ktor.client.okhttp)
        }
        jvmMain.dependencies {
            implementation(libs.sqldelight.sqlite.driver)
            implementation(libs.ktor.client.cio)
        }
        jvmTest.dependencies {
            implementation(kotlin("test"))
            implementation(libs.kotlinx.coroutines.test)
            implementation(libs.ktor.client.mock)
        }
    }
}

sqldelight {
    databases {
        create("ClientDatabase") {
            packageName.set("com.sagunkayastha.adhdhelper.client.db")
        }
    }
}
```

If Phase 1 already declared `commonMain.dependencies { ... }` etc., add the lines into those existing blocks instead of creating second blocks. If `sourceSets.all { languageSettings.optIn("kotlin.time.ExperimentalTime") }` already exists, do not duplicate it. Make `libs.sqldelight.sqlite.driver` an `api` dependency of `jvmMain` instead of `implementation` **only if** `server` does not already have it (it normally does, through `ServerDb`).

- [ ] **Step 3: Write the schema files**

`shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/TaskList.sq`:

```sql
import kotlin.Boolean;

CREATE TABLE task_list (
  id TEXT NOT NULL PRIMARY KEY,
  title TEXT NOT NULL,
  sort_key TEXT NOT NULL,
  hlc TEXT NOT NULL,
  deleted INTEGER AS Boolean NOT NULL DEFAULT 0
);

upsert:
INSERT OR REPLACE INTO task_list VALUES ?;

byId:
SELECT * FROM task_list WHERE id = ?;

visible:
SELECT * FROM task_list WHERE deleted = 0 ORDER BY sort_key, id;

allIds:
SELECT id FROM task_list;

hardDelete:
DELETE FROM task_list WHERE id = ?;
```

`shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/Task.sq`:

```sql
import com.sagunkayastha.adhdhelper.model.RepeatRule;
import kotlin.Boolean;
import kotlin.time.Instant;
import kotlinx.datetime.LocalDate;
import kotlinx.datetime.LocalTime;

CREATE TABLE task (
  id TEXT NOT NULL PRIMARY KEY,
  list_id TEXT NOT NULL,
  parent_id TEXT,
  title TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '',
  starred INTEGER AS Boolean NOT NULL DEFAULT 0,
  due_date TEXT AS LocalDate,
  due_time TEXT AS LocalTime,
  repeat_rule TEXT AS RepeatRule,
  completed_at INTEGER AS Instant,
  sort_key TEXT NOT NULL,
  snooze_until INTEGER AS Instant,
  hlc TEXT NOT NULL,
  deleted INTEGER AS Boolean NOT NULL DEFAULT 0
);

CREATE INDEX task_list_id ON task(list_id);
CREATE INDEX task_parent_id ON task(parent_id);

upsert:
INSERT OR REPLACE INTO task VALUES ?;

byId:
SELECT * FROM task WHERE id = ?;

byList:
SELECT * FROM task WHERE list_id = ? AND deleted = 0 ORDER BY sort_key, id;

starred:
SELECT * FROM task WHERE starred = 1 AND deleted = 0 ORDER BY sort_key, id;

children:
SELECT * FROM task WHERE parent_id = ? AND deleted = 0 ORDER BY sort_key, id;

openTimed:
SELECT * FROM task
WHERE deleted = 0 AND completed_at IS NULL AND due_date IS NOT NULL AND due_time IS NOT NULL;

allIds:
SELECT id FROM task;

hardDelete:
DELETE FROM task WHERE id = ?;
```

`shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/Note.sq`:

```sql
import kotlin.Boolean;
import kotlin.time.Instant;

CREATE TABLE note (
  id TEXT NOT NULL PRIMARY KEY,
  text TEXT NOT NULL,
  created_at INTEGER AS Instant NOT NULL,
  task_id TEXT,
  hlc TEXT NOT NULL,
  deleted INTEGER AS Boolean NOT NULL DEFAULT 0
);

upsert:
INSERT OR REPLACE INTO note VALUES ?;

byId:
SELECT * FROM note WHERE id = ?;

visible:
SELECT * FROM note WHERE deleted = 0 ORDER BY created_at DESC, id DESC;

allIds:
SELECT id FROM note;

hardDelete:
DELETE FROM note WHERE id = ?;
```

`shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/ChatMessage.sq`:

```sql
import com.sagunkayastha.adhdhelper.model.ChatStatus;
import com.sagunkayastha.adhdhelper.model.Role;
import kotlin.time.Instant;

CREATE TABLE chat_message (
  id TEXT NOT NULL PRIMARY KEY,
  role TEXT AS Role NOT NULL,
  text TEXT NOT NULL,
  created_at INTEGER AS Instant NOT NULL,
  status TEXT AS ChatStatus NOT NULL,
  hlc TEXT NOT NULL
);

upsert:
INSERT OR REPLACE INTO chat_message VALUES ?;

byId:
SELECT * FROM chat_message WHERE id = ?;

visible:
SELECT * FROM chat_message ORDER BY created_at, id;

allIds:
SELECT id FROM chat_message;

hardDelete:
DELETE FROM chat_message WHERE id = ?;
```

`shared/src/commonMain/sqldelight/com/sagunkayastha/adhdhelper/client/db/Outbox.sq`:

```sql
CREATE TABLE outbox (
  kind TEXT NOT NULL,
  id TEXT NOT NULL,
  hlc TEXT NOT NULL,
  PRIMARY KEY (kind, id)
);

put:
INSERT OR REPLACE INTO outbox(kind, id, hlc) VALUES (?, ?, ?);

all:
SELECT * FROM outbox;

clearIfMatch:
DELETE FROM outbox WHERE kind = ? AND id = ? AND hlc = ?;

remove:
DELETE FROM outbox WHERE kind = ? AND id = ?;

count:
SELECT COUNT(*) FROM outbox;
```

Note: `repeat_rule` (not `repeat`) is the column name, to stay clear of SQL keywords; the model field is still `repeat`. Instants are stored as epoch milliseconds; the repository truncates new instants to milliseconds so a written row reads back equal.

- [ ] **Step 4: Write the failing test**

`shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/ClientDbTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.sagunkayastha.adhdhelper.client.db.ClientDatabase
import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.Freq
import com.sagunkayastha.adhdhelper.model.Note
import com.sagunkayastha.adhdhelper.model.RepeatRule
import com.sagunkayastha.adhdhelper.model.Role
import com.sagunkayastha.adhdhelper.model.Task
import com.sagunkayastha.adhdhelper.model.TaskList
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.time.Instant
import kotlinx.datetime.DayOfWeek
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime

class ClientDbTest {
    private fun memoryDb(): ClientDatabase =
        createClientDatabase(JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY).also { ClientDatabase.Schema.create(it) })

    @Test
    fun everyTaskFieldRoundTrips() {
        val db = memoryDb()
        val task = Task(
            id = "t1", listId = "l1", parentId = "p1", title = "Pay rent", details = "online",
            starred = true, dueDate = LocalDate(2026, 10, 31), dueTime = LocalTime(18, 0),
            repeat = RepeatRule(Freq.WEEKLY, 2, listOf(DayOfWeek.MONDAY, DayOfWeek.THURSDAY)),
            completedAt = Instant.fromEpochMilliseconds(1_760_000_000_123),
            sortKey = "a0", snoozeUntil = Instant.fromEpochMilliseconds(1_760_000_600_000),
            hlc = "000001760000000-00000-dev", deleted = true,
        )
        db.taskQueries.upsert(task.toRow())
        assertEquals(task, db.taskQueries.byId("t1").executeAsOne().toModel())
    }

    @Test
    fun listNoteAndMessageRoundTrip() {
        val db = memoryDb()
        val list = TaskList("l1", "Inbox", "a0", "h1", deleted = false)
        val note = Note("n1", "idea", Instant.fromEpochMilliseconds(5), taskId = "t1", hlc = "h2", deleted = false)
        val msg = ChatMessage("m1", Role.USER, "hi", Instant.fromEpochMilliseconds(6), ChatStatus.QUEUED, "h3")
        db.taskListQueries.upsert(list.toRow())
        db.noteQueries.upsert(note.toRow())
        db.chatMessageQueries.upsert(msg.toRow())
        assertEquals(list, db.taskListQueries.byId("l1").executeAsOne().toModel())
        assertEquals(note, db.noteQueries.byId("n1").executeAsOne().toModel())
        assertEquals(msg, db.chatMessageQueries.byId("m1").executeAsOne().toModel())
    }

    @Test
    fun outboxPrimaryKeyIsKindAndId() {
        val db = memoryDb()
        db.outboxQueries.put("task", "x", "h1")
        db.outboxQueries.put("task", "x", "h2")
        db.outboxQueries.put("note", "x", "h1")
        assertEquals(2L, db.outboxQueries.count().executeAsOne())
        db.outboxQueries.clearIfMatch("task", "x", "h1")   // stale hlc: no-op
        assertEquals(2L, db.outboxQueries.count().executeAsOne())
        db.outboxQueries.clearIfMatch("task", "x", "h2")
        assertEquals(1L, db.outboxQueries.count().executeAsOne())
    }

    @Test
    fun jvmFileDatabaseSurvivesReopen() {
        val path = Files.createTempDirectory("clientdb").resolve("sub/adhd-helper.db").toString()
        val first = DriverFactory(path).createDriver()
        createClientDatabase(first).taskListQueries.upsert(TaskList("l1", "Inbox", "a0", "h1").toRow())
        first.close()
        val second = DriverFactory(path).createDriver()
        assertEquals("Inbox", createClientDatabase(second).taskListQueries.byId("l1").executeAsOne().title)
        second.close()
    }
}
```

- [ ] **Step 5: Run test to verify it fails**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.ClientDbTest'`
Expected: FAIL to compile with `Unresolved reference: createClientDatabase` / `toRow` / `DriverFactory`.

- [ ] **Step 6: Write the adapters, database factory and mappers**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/ClientDb.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import app.cash.sqldelight.ColumnAdapter
import app.cash.sqldelight.db.SqlDriver
import com.sagunkayastha.adhdhelper.client.db.Chat_message
import com.sagunkayastha.adhdhelper.client.db.ClientDatabase
import com.sagunkayastha.adhdhelper.client.db.Note
import com.sagunkayastha.adhdhelper.client.db.Task
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.RepeatRule
import com.sagunkayastha.adhdhelper.model.Role
import kotlin.time.Instant
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime
import kotlinx.serialization.json.Json

/** Opens the platform SQLite file. Android: `DriverFactory(context)`; desktop: `DriverFactory(path)`. */
expect class DriverFactory {
    fun createDriver(): SqlDriver
}

/** Dispatcher for blocking SQLite work (Dispatchers.IO on both platforms). */
internal expect val DbDispatcher: CoroutineDispatcher

internal object LocalDateAdapter : ColumnAdapter<LocalDate, String> {
    override fun decode(databaseValue: String) = LocalDate.parse(databaseValue)
    override fun encode(value: LocalDate) = value.toString()
}

internal object LocalTimeAdapter : ColumnAdapter<LocalTime, String> {
    override fun decode(databaseValue: String) = LocalTime.parse(databaseValue)
    override fun encode(value: LocalTime) = value.toString()
}

internal object InstantAdapter : ColumnAdapter<Instant, Long> {
    override fun decode(databaseValue: Long) = Instant.fromEpochMilliseconds(databaseValue)
    override fun encode(value: Instant) = value.toEpochMilliseconds()
}

private val ruleJson = Json { ignoreUnknownKeys = true }

internal object RepeatRuleAdapter : ColumnAdapter<RepeatRule, String> {
    override fun decode(databaseValue: String) = ruleJson.decodeFromString(RepeatRule.serializer(), databaseValue)
    override fun encode(value: RepeatRule) = ruleJson.encodeToString(RepeatRule.serializer(), value)
}

internal object RoleAdapter : ColumnAdapter<Role, String> {
    override fun decode(databaseValue: String) = Role.valueOf(databaseValue)
    override fun encode(value: Role) = value.name
}

internal object ChatStatusAdapter : ColumnAdapter<ChatStatus, String> {
    override fun decode(databaseValue: String) = ChatStatus.valueOf(databaseValue)
    override fun encode(value: ChatStatus) = value.name
}

fun createClientDatabase(driver: SqlDriver): ClientDatabase = ClientDatabase(
    driver = driver,
    chat_messageAdapter = Chat_message.Adapter(
        roleAdapter = RoleAdapter,
        created_atAdapter = InstantAdapter,
        statusAdapter = ChatStatusAdapter,
    ),
    noteAdapter = Note.Adapter(created_atAdapter = InstantAdapter),
    taskAdapter = Task.Adapter(
        due_dateAdapter = LocalDateAdapter,
        due_timeAdapter = LocalTimeAdapter,
        repeat_ruleAdapter = RepeatRuleAdapter,
        completed_atAdapter = InstantAdapter,
        snooze_untilAdapter = InstantAdapter,
    ),
)
```

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/Mappers.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.client.db.Chat_message
import com.sagunkayastha.adhdhelper.client.db.Task_list
import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.model.Note
import com.sagunkayastha.adhdhelper.model.Task
import com.sagunkayastha.adhdhelper.model.TaskList
import com.sagunkayastha.adhdhelper.client.db.Note as NoteRow
import com.sagunkayastha.adhdhelper.client.db.Task as TaskRow

internal fun Task_list.toModel() = TaskList(id = id, title = title, sortKey = sort_key, hlc = hlc, deleted = deleted)
internal fun TaskList.toRow() = Task_list(id = id, title = title, sort_key = sortKey, hlc = hlc, deleted = deleted)

internal fun TaskRow.toModel() = Task(
    id = id, listId = list_id, parentId = parent_id, title = title, details = details, starred = starred,
    dueDate = due_date, dueTime = due_time, repeat = repeat_rule, completedAt = completed_at,
    sortKey = sort_key, snoozeUntil = snooze_until, hlc = hlc, deleted = deleted,
)
internal fun Task.toRow() = TaskRow(
    id = id, list_id = listId, parent_id = parentId, title = title, details = details, starred = starred,
    due_date = dueDate, due_time = dueTime, repeat_rule = repeat, completed_at = completedAt,
    sort_key = sortKey, snooze_until = snoozeUntil, hlc = hlc, deleted = deleted,
)

internal fun NoteRow.toModel() = Note(id = id, text = text, createdAt = created_at, taskId = task_id, hlc = hlc, deleted = deleted)
internal fun Note.toRow() = NoteRow(id = id, text = text, created_at = createdAt, task_id = taskId, hlc = hlc, deleted = deleted)

internal fun Chat_message.toModel() = ChatMessage(id = id, role = role, text = text, createdAt = created_at, status = status, hlc = hlc)
internal fun ChatMessage.toRow() = Chat_message(id = id, role = role, text = text, created_at = createdAt, status = status, hlc = hlc)
```

`shared/src/jvmMain/kotlin/com/sagunkayastha/adhdhelper/client/ClientDb.jvm.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.sagunkayastha.adhdhelper.client.db.ClientDatabase
import java.io.File
import java.util.Properties
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers

actual class DriverFactory(private val path: String) {
    actual fun createDriver(): SqlDriver {
        File(path).absoluteFile.parentFile?.mkdirs()
        // Creates the schema on first open, migrates by user_version afterwards.
        return JdbcSqliteDriver("jdbc:sqlite:$path", Properties(), ClientDatabase.Schema)
    }
}

internal actual val DbDispatcher: CoroutineDispatcher = Dispatchers.IO
```

`shared/src/androidMain/kotlin/com/sagunkayastha/adhdhelper/client/ClientDb.android.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import android.content.Context
import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.android.AndroidSqliteDriver
import com.sagunkayastha.adhdhelper.client.db.ClientDatabase
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers

actual class DriverFactory(private val context: Context) {
    actual fun createDriver(): SqlDriver =
        AndroidSqliteDriver(ClientDatabase.Schema, context.applicationContext, "adhd-helper.db")
}

internal actual val DbDispatcher: CoroutineDispatcher = Dispatchers.IO
```

- [ ] **Step 7: Run tests to verify they pass, and that Android compiles**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.ClientDbTest'`
Expected: PASS (4 tests).

Run: `gradle :shared:compileDebugKotlinAndroid`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 8: Commit**

```bash
git add shared/build.gradle.kts shared/src/commonMain/sqldelight shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client shared/src/androidMain/kotlin/com/sagunkayastha/adhdhelper/client shared/src/jvmMain/kotlin/com/sagunkayastha/adhdhelper/client shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client
git commit -m "feat(client): SQLDelight client schema, adapters, driver factory

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr"
```

---

### Task 2: TaskRepository core: write path, outbox, lists, notes, chat queue

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/TaskRepository.kt`
- Create: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/TestDevice.kt`
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryCoreTest.kt`

**Interfaces:**
- Consumes: Task 1 (`createClientDatabase`, query names, mappers, `DbDispatcher`); Phase 1 `Hlc(nodeId, wallMillis)`, `Hlc.now()`, `Ids.newId()`, `SortKey.between(before, after)`, `Changes`.
- Produces (contract): `TaskRepository(db: ClientDatabase, hlc: Hlc, onLocalChange: () -> Unit)` with `lists()`, `notes()`, `messages()`, `addList`, `renameList`, `addNote`, `queueChat`, `setChatStatus(id, status)`, `drainOutbox()`, `clearOutbox(changes)`.
- Concurrency (binding for Phases 4-6): `Hlc` is not thread-safe, and on Android the UI, notification-action receivers and WorkManager share one `TaskRepository` in one process. So every method that calls `hlc.now()` or `hlc.observe()` or writes the DB (`write {}`, `applyRemote`, `applyFullSnapshot`, `clearOutbox`) runs inside the single private `Mutex` `lock`; nothing outside the repository touches the `Hlc` instance. Apps create exactly one `TaskRepository` per process.
- `queueChat(text)` stores its note with id `Ids.derived("note:${message.id}")`, so the server's note for the same message (Phase 6) is the same row.
- `setChatStatus(id, status)` restamps the message with a fresh HLC and queues it in the outbox (Phase 6 Retry puts FAILED back to QUEUED). Unknown id -> `IllegalArgumentException`.
- Produces (internal, used by Tasks 3-5): `KIND_LIST = "list"`, `KIND_TASK = "task"`, `KIND_NOTE = "note"`, `KIND_MESSAGE = "message"`; private helpers `write {}`, `now()`, `listRow/taskRow/noteRow/messageRow(id)`, `requireList(id)`, `requireTask(id)`, `putList/putTask/putNote/putMessage(row)`.
- Produces (jvmTest): `class TestDevice(name: String = "dev", start: Long = 1_000_000L)` with `var clock: Long`, `var localChanges: Int`, `val db: ClientDatabase`, `val repo: TaskRepository`.

- [ ] **Step 1: Write the test fixture**

`shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/TestDevice.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.sagunkayastha.adhdhelper.client.db.ClientDatabase
import com.sagunkayastha.adhdhelper.sync.Hlc

/** One simulated device: in-memory DB, controllable wall clock, counts onLocalChange calls. */
class TestDevice(name: String = "dev", start: Long = 1_000_000L) {
    var clock: Long = start
    var localChanges: Int = 0
    val db: ClientDatabase =
        createClientDatabase(JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY).also { ClientDatabase.Schema.create(it) })
    val repo = TaskRepository(db, Hlc(name) { clock }) { localChanges++ }
}
```

- [ ] **Step 2: Write the failing test**

`shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryCoreTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.Role
import com.sagunkayastha.adhdhelper.sync.Ids
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest

class RepositoryCoreTest {
    @Test
    fun addListWritesRowAndOutboxAndNotifies() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("Inbox")
        assertEquals(listOf(list), d.repo.lists().first())
        val outbox = d.db.outboxQueries.all().executeAsList()
        assertEquals(1, outbox.size)
        assertEquals(KIND_LIST, outbox[0].kind)
        assertEquals(list.id, outbox[0].id)
        assertEquals(list.hlc, outbox[0].hlc)
        assertEquals(1, d.localChanges)
    }

    @Test
    fun everyWriteGetsAStrictlyLaterHlc() = runTest {
        val d = TestDevice()   // clock never moves: the HLC counter must still increase
        val a = d.repo.addList("A")
        d.repo.renameList(a.id, "A2")
        val renamed = d.repo.lists().first().single()
        assertEquals("A2", renamed.title)
        assertTrue(renamed.hlc > a.hlc)
        assertEquals(renamed.hlc, d.db.outboxQueries.all().executeAsList().single().hlc)
    }

    @Test
    fun newListsAppendAtTheEnd() = runTest {
        val d = TestDevice()
        d.repo.addList("first")
        d.repo.addList("second")
        d.repo.addList("third")
        assertEquals(listOf("first", "second", "third"), d.repo.lists().first().map { it.title })
    }

    @Test
    fun addNoteListsNewestFirst() = runTest {
        val d = TestDevice()
        val n1 = d.repo.addNote("one")
        Thread.sleep(5)   // createdAt is real time in ms
        val n2 = d.repo.addNote("two")
        assertEquals(listOf(n2, n1), d.repo.notes().first())
    }

    @Test
    fun queueChatSavesQueuedMessageAndANote() = runTest {
        val d = TestDevice()
        val msg = d.repo.queueChat("remind me to call mom")
        assertEquals(Role.USER, msg.role)
        assertEquals(ChatStatus.QUEUED, msg.status)
        assertEquals(listOf(msg), d.repo.messages().first())
        val note = d.repo.notes().first().single()
        assertEquals("remind me to call mom", note.text)
        assertEquals(Ids.derived("note:${msg.id}"), note.id)   // same row the server writes for this message
        val kinds = d.db.outboxQueries.all().executeAsList().map { it.kind }.toSet()
        assertEquals(setOf(KIND_MESSAGE, KIND_NOTE), kinds)
        assertEquals(1, d.localChanges)   // one transaction, one notification
    }

    @Test
    fun setChatStatusRestampsAndQueuesForSync() = runTest {
        val d = TestDevice()
        val msg = d.repo.queueChat("hi")
        d.repo.clearOutbox(d.repo.drainOutbox())
        d.repo.setChatStatus(msg.id, ChatStatus.FAILED)
        val stored = d.repo.messages().first().single()
        assertEquals(ChatStatus.FAILED, stored.status)
        assertTrue(stored.hlc > msg.hlc)
        assertEquals(listOf(stored), d.repo.drainOutbox().messages)
        assertFailsWith<IllegalArgumentException> { d.repo.setChatStatus("missing", ChatStatus.QUEUED) }
    }

    @Test
    fun drainOutboxReturnsCurrentRowsOfEveryKind() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        d.repo.queueChat("hi")
        val drained = d.repo.drainOutbox()
        assertEquals(listOf(list), drained.lists)
        assertEquals(1, drained.notes.size)
        assertEquals(1, drained.messages.size)
        assertTrue(drained.tasks.isEmpty())
    }

    @Test
    fun clearOutboxRemovesSentRows() = runTest {
        val d = TestDevice()
        d.repo.addList("L")
        d.repo.clearOutbox(d.repo.drainOutbox())
        assertTrue(d.repo.drainOutbox().isEmpty())
    }

    @Test
    fun clearOutboxKeepsRowsEditedAfterDrain() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("old")
        val sent = d.repo.drainOutbox()
        d.repo.renameList(list.id, "new")   // edit while the sync request is in flight
        d.repo.clearOutbox(sent)
        assertEquals("new", d.repo.drainOutbox().lists.single().title)
    }
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.RepositoryCoreTest'`
Expected: FAIL to compile with `Unresolved reference: TaskRepository`.

- [ ] **Step 4: Write the repository core**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/TaskRepository.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import app.cash.sqldelight.coroutines.asFlow
import app.cash.sqldelight.coroutines.mapToList
import com.sagunkayastha.adhdhelper.client.db.ClientDatabase
import com.sagunkayastha.adhdhelper.core.SortKey
import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.Note
import com.sagunkayastha.adhdhelper.model.Role
import com.sagunkayastha.adhdhelper.model.Task
import com.sagunkayastha.adhdhelper.model.TaskList
import com.sagunkayastha.adhdhelper.sync.Changes
import com.sagunkayastha.adhdhelper.sync.Hlc
import com.sagunkayastha.adhdhelper.sync.Ids
import kotlin.time.Clock
import kotlin.time.Instant
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

internal const val KIND_LIST = "list"
internal const val KIND_TASK = "task"
internal const val KIND_NOTE = "note"
internal const val KIND_MESSAGE = "message"

/**
 * The only writer of the client DB. Every local write stamps a fresh HLC and writes
 * the row plus its outbox entry in one transaction, then calls [onLocalChange].
 * Thread-safe: all HLC use and all writes run under [lock] (Hlc itself is not thread-safe);
 * create one instance per process.
 */
class TaskRepository(
    private val db: ClientDatabase,
    private val hlc: Hlc,
    private val onLocalChange: () -> Unit,
) {
    private val lock = Mutex()

    // ---------- reads ----------

    fun lists(): Flow<List<TaskList>> =
        db.taskListQueries.visible().asFlow().mapToList(DbDispatcher).map { rows -> rows.map { it.toModel() } }

    fun notes(): Flow<List<Note>> =
        db.noteQueries.visible().asFlow().mapToList(DbDispatcher).map { rows -> rows.map { it.toModel() } }

    fun messages(): Flow<List<ChatMessage>> =
        db.chatMessageQueries.visible().asFlow().mapToList(DbDispatcher).map { rows -> rows.map { it.toModel() } }

    // ---------- list writes ----------

    suspend fun addList(title: String): TaskList = write {
        val last = db.taskListQueries.visible().executeAsList().lastOrNull()?.sort_key
        TaskList(id = Ids.newId(), title = title, sortKey = SortKey.between(last, null), hlc = hlc.now())
            .also { putList(it) }
    }

    suspend fun renameList(id: String, title: String) {
        write { putList(requireList(id).copy(title = title, hlc = hlc.now())) }
    }

    // ---------- notes and chat ----------

    suspend fun addNote(text: String): Note = write {
        Note(id = Ids.newId(), text = text, createdAt = now(), hlc = hlc.now()).also { putNote(it) }
    }

    suspend fun queueChat(text: String): ChatMessage = write {
        val at = now()
        val msg = ChatMessage(
            id = Ids.newId(), role = Role.USER, text = text, createdAt = at,
            status = ChatStatus.QUEUED, hlc = hlc.now(),
        )
        putMessage(msg)
        // Deterministic note id: the server's note for this message (Phase 6) is the same row.
        putNote(Note(id = Ids.derived("note:${msg.id}"), text = text, createdAt = at, hlc = hlc.now()))
        msg
    }

    /** Local status change (e.g. Retry: FAILED -> QUEUED); syncs like any edit. */
    suspend fun setChatStatus(id: String, status: ChatStatus) {
        write {
            val msg = messageRow(id) ?: throw IllegalArgumentException("no message $id")
            putMessage(msg.copy(status = status, hlc = hlc.now()))
        }
    }

    // ---------- outbox ----------

    suspend fun drainOutbox(): Changes = withContext(DbDispatcher) {
        db.transactionWithResult {
            val entries = db.outboxQueries.all().executeAsList()
            fun ids(kind: String) = entries.filter { it.kind == kind }.map { it.id }
            Changes(
                lists = ids(KIND_LIST).mapNotNull { listRow(it) },
                tasks = ids(KIND_TASK).mapNotNull { taskRow(it) },
                notes = ids(KIND_NOTE).mapNotNull { noteRow(it) },
                messages = ids(KIND_MESSAGE).mapNotNull { messageRow(it) },
            )
        }
    }

    /** Removes only outbox rows whose hlc still equals the sent row's hlc. */
    suspend fun clearOutbox(changes: Changes) {
        lock.withLock {
            withContext(DbDispatcher) {
                db.transaction {
                    changes.lists.forEach { db.outboxQueries.clearIfMatch(KIND_LIST, it.id, it.hlc) }
                    changes.tasks.forEach { db.outboxQueries.clearIfMatch(KIND_TASK, it.id, it.hlc) }
                    changes.notes.forEach { db.outboxQueries.clearIfMatch(KIND_NOTE, it.id, it.hlc) }
                    changes.messages.forEach { db.outboxQueries.clearIfMatch(KIND_MESSAGE, it.id, it.hlc) }
                }
            }
        }
    }

    // ---------- internals ----------

    private suspend fun <T> write(block: () -> T): T {
        val result = lock.withLock {
            withContext(DbDispatcher) { db.transactionWithResult { block() } }
        }
        onLocalChange()
        return result
    }

    /** Millisecond precision, so a value read back from the DB equals the one written. */
    private fun now(): Instant = Instant.fromEpochMilliseconds(Clock.System.now().toEpochMilliseconds())

    private fun listRow(id: String): TaskList? = db.taskListQueries.byId(id).executeAsOneOrNull()?.toModel()
    private fun taskRow(id: String): Task? = db.taskQueries.byId(id).executeAsOneOrNull()?.toModel()
    private fun noteRow(id: String): Note? = db.noteQueries.byId(id).executeAsOneOrNull()?.toModel()
    private fun messageRow(id: String): ChatMessage? = db.chatMessageQueries.byId(id).executeAsOneOrNull()?.toModel()

    private fun requireList(id: String): TaskList =
        listRow(id)?.takeIf { !it.deleted } ?: throw IllegalArgumentException("no list $id")

    private fun requireTask(id: String): Task =
        taskRow(id)?.takeIf { !it.deleted } ?: throw IllegalArgumentException("no task $id")

    private fun putList(row: TaskList) {
        db.taskListQueries.upsert(row.toRow())
        db.outboxQueries.put(KIND_LIST, row.id, row.hlc)
    }

    private fun putTask(row: Task) {
        db.taskQueries.upsert(row.toRow())
        db.outboxQueries.put(KIND_TASK, row.id, row.hlc)
    }

    private fun putNote(row: Note) {
        db.noteQueries.upsert(row.toRow())
        db.outboxQueries.put(KIND_NOTE, row.id, row.hlc)
    }

    private fun putMessage(row: ChatMessage) {
        db.chatMessageQueries.upsert(row.toRow())
        db.outboxQueries.put(KIND_MESSAGE, row.id, row.hlc)
    }
}
```

(`requireTask` and `putTask` are used from Task 3 on; an "unused" warning until then is expected.)

- [ ] **Step 5: Run test to verify it passes**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.RepositoryCoreTest'`
Expected: PASS (9 tests).

- [ ] **Step 6: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/TaskRepository.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/TestDevice.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryCoreTest.kt
git commit -m "feat(client): TaskRepository write path with outbox, lists, notes, chat queue, chat status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr"
```

---

### Task 3: TaskRepository task operations (add, update, subtasks, delete, move, snooze, star, timed)

**Files:**
- Modify: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/TaskRepository.kt`
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryTasksTest.kt`

**Interfaces:**
- Consumes: Task 2 private helpers (`write`, `requireList`, `requireTask`, `taskRow`, `putList`, `putTask`), `TestDevice`.
- Produces (contract): `tasks(listId)`, `starred()`, `addTask(listId, title, parentId = null, dueDate = null, dueTime = null): Task`, `updateTask(task)`, `deleteTask(id)`, `deleteList(id)`, `move(id, beforeId, afterId)`, `snooze(id, until)`, `openTimedTasks(): List<Task>`, `noteToTask(noteId, listId): Task`.
- `noteToTask(noteId, listId)`: one transaction: a new top-of-list task titled with the note's first non-blank line (max 200 chars), and the note restamped with `taskId`; both rows go to the outbox. `IllegalArgumentException` if the note is missing/deleted/empty, already a task, or the list is missing. (Used by Phase 6's Notes view.)
- Produces (private, used by Task 4): `firstSiblingKey(listId: String, parentId: String?): String?`.
- Semantics: new tasks go to the top of their siblings (same list, same parent). `move(id, beforeId, afterId)`: `beforeId` is the task that should end up directly above, `afterId` directly below (either may be null). A subtask's parent must be a live top-level task in the same list, else `IllegalArgumentException`. `updateTask` also rejects making a task that has subtasks into a subtask.

- [ ] **Step 1: Write the failing test**

`shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryTasksTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlin.time.Instant
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime

class RepositoryTasksTest {
    @Test
    fun addTaskStampsHlcWritesOutboxAndGoesToTop() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("Inbox")
        val a = d.repo.addTask(list.id, "a")
        val b = d.repo.addTask(list.id, "b", dueDate = LocalDate(2026, 10, 9), dueTime = LocalTime(18, 0))
        assertEquals(listOf("b", "a"), d.repo.tasks(list.id).first().map { it.title })
        assertEquals(LocalTime(18, 0), b.dueTime)
        assertTrue(b.hlc > a.hlc)
        val outboxTask = d.db.outboxQueries.all().executeAsList().single { it.id == b.id }
        assertEquals(KIND_TASK, outboxTask.kind)
        assertEquals(b.hlc, outboxTask.hlc)
        assertEquals(3, d.localChanges)
    }

    @Test
    fun addTaskToUnknownListFails() = runTest {
        val d = TestDevice()
        assertFailsWith<IllegalArgumentException> { d.repo.addTask("nope", "x") }
    }

    @Test
    fun subtasksAreOneLevelOnly() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        val parent = d.repo.addTask(list.id, "parent")
        val child = d.repo.addTask(list.id, "child", parentId = parent.id)
        assertEquals(parent.id, child.parentId)
        assertFailsWith<IllegalArgumentException> { d.repo.addTask(list.id, "grandchild", parentId = child.id) }
        val other = d.repo.addTask(list.id, "other")
        // a task that has subtasks cannot become a subtask itself
        assertFailsWith<IllegalArgumentException> { d.repo.updateTask(parent.copy(parentId = other.id)) }
        // a subtask's parent must be in the same list
        val list2 = d.repo.addList("L2")
        assertFailsWith<IllegalArgumentException> { d.repo.addTask(list2.id, "x", parentId = parent.id) }
    }

    @Test
    fun updateTaskRestampsHlc() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        val t = d.repo.addTask(list.id, "draft")
        d.repo.updateTask(t.copy(title = "final", details = "more", starred = true))
        val stored = d.repo.tasks(list.id).first().single()
        assertEquals("final", stored.title)
        assertEquals("more", stored.details)
        assertTrue(stored.hlc > t.hlc)
        assertEquals(listOf(stored), d.repo.starred().first())
    }

    @Test
    fun deleteTaskTombstonesSubtasks() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        val parent = d.repo.addTask(list.id, "parent")
        val child = d.repo.addTask(list.id, "child", parentId = parent.id)
        d.repo.deleteTask(parent.id)
        assertTrue(d.repo.tasks(list.id).first().isEmpty())
        val sent = d.repo.drainOutbox().tasks.associateBy { it.id }
        assertTrue(sent.getValue(parent.id).deleted)
        assertTrue(sent.getValue(child.id).deleted)
    }

    @Test
    fun deleteListTombstonesItsTasks() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        val keep = d.repo.addList("Keep")
        val t = d.repo.addTask(list.id, "t")
        val k = d.repo.addTask(keep.id, "k")
        d.repo.deleteList(list.id)
        assertEquals(listOf(keep), d.repo.lists().first())
        val sent = d.repo.drainOutbox()
        assertTrue(sent.lists.single { it.id == list.id }.deleted)
        assertTrue(sent.tasks.single { it.id == t.id }.deleted)
        assertTrue(!sent.tasks.single { it.id == k.id }.deleted)
    }

    @Test
    fun moveUsesSortKeyBetweenNeighbours() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        val a = d.repo.addTask(list.id, "a")
        val b = d.repo.addTask(list.id, "b")
        val c = d.repo.addTask(list.id, "c")   // order now c, b, a
        d.repo.move(a.id, beforeId = c.id, afterId = b.id)
        assertEquals(listOf("c", "a", "b"), d.repo.tasks(list.id).first().map { it.title })
        d.repo.move(c.id, beforeId = b.id, afterId = null)
        assertEquals(listOf("a", "b", "c"), d.repo.tasks(list.id).first().map { it.title })
    }

    @Test
    fun snoozeSetsSnoozeUntil() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        val t = d.repo.addTask(list.id, "t")
        val until = Instant.fromEpochMilliseconds(1_760_000_000_000)
        d.repo.snooze(t.id, until)
        val stored = d.repo.tasks(list.id).first().single()
        assertEquals(until, stored.snoozeUntil)
        assertTrue(stored.hlc > t.hlc)
    }

    @Test
    fun parallelAddTaskCallsGetDistinctOrderedHlcs() = runBlocking {
        // Android: UI, notification receivers and WorkManager share one repository on different threads.
        val d = TestDevice()   // wall clock frozen: only the counter can order the stamps
        val list = d.repo.addList("L")   // counter 0
        val added = (1..200).map { i ->
            async(Dispatchers.Default) { d.repo.addTask(list.id, "t$i") }
        }.awaitAll()
        val stamps = added.map { it.hlc }
        assertEquals(200, stamps.toSet().size)
        // No lost or repeated counter values: exactly 1..200 after the list's 0.
        assertEquals((1..200).toList(), stamps.sorted().map { it.split('-')[1].toInt() })
        assertEquals(200, d.repo.tasks(list.id).first().size)
        assertEquals(201, d.db.outboxQueries.all().executeAsList().size)
    }

    @Test
    fun noteToTaskLinksNoteAndQueuesBothForSync() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("Inbox")
        val note = d.repo.addNote("\n  Renew passport \nneeds photo")
        d.repo.clearOutbox(d.repo.drainOutbox())

        val task = d.repo.noteToTask(note.id, list.id)
        assertEquals("Renew passport", task.title)
        assertEquals(list.id, task.listId)
        assertEquals(task.id, d.repo.notes().first().single().taskId)
        assertEquals(listOf(task.id), d.repo.tasks(list.id).first().map { it.id })

        val out = d.repo.drainOutbox()
        assertTrue(out.tasks.any { it.id == task.id })
        assertTrue(out.notes.any { it.id == note.id && it.taskId == task.id })

        assertFailsWith<IllegalArgumentException> { d.repo.noteToTask(note.id, list.id) }
        assertFailsWith<IllegalArgumentException> { d.repo.noteToTask("missing", list.id) }
    }

    @Test
    fun openTimedTasksSkipsAllDayCompletedAndDeleted() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        val day = LocalDate(2026, 10, 9)
        val timed = d.repo.addTask(list.id, "timed", dueDate = day, dueTime = LocalTime(9, 0))
        d.repo.addTask(list.id, "all day", dueDate = day)
        val done = d.repo.addTask(list.id, "done", dueDate = day, dueTime = LocalTime(10, 0))
        d.repo.updateTask(done.copy(completedAt = Instant.fromEpochMilliseconds(1)))
        val gone = d.repo.addTask(list.id, "gone", dueDate = day, dueTime = LocalTime(11, 0))
        d.repo.deleteTask(gone.id)
        assertEquals(listOf(timed.id), d.repo.openTimedTasks().map { it.id })
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.RepositoryTasksTest'`
Expected: FAIL to compile with `Unresolved reference: addTask`.

- [ ] **Step 3: Add the task operations to `TaskRepository`**

Add these imports to `TaskRepository.kt`:

```kotlin
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime
```

Add to the `// ---------- reads ----------` section:

```kotlin
    /** Non-deleted tasks of a list, top-level and subtasks, ordered by sortKey. */
    fun tasks(listId: String): Flow<List<Task>> =
        db.taskQueries.byList(listId).asFlow().mapToList(DbDispatcher).map { rows -> rows.map { it.toModel() } }

    fun starred(): Flow<List<Task>> =
        db.taskQueries.starred().asFlow().mapToList(DbDispatcher).map { rows -> rows.map { it.toModel() } }

    suspend fun openTimedTasks(): List<Task> = withContext(DbDispatcher) {
        db.taskQueries.openTimed().executeAsList().map { it.toModel() }
    }
```

Add after `renameList`:

```kotlin
    suspend fun deleteList(id: String) {
        write {
            putList(requireList(id).copy(deleted = true, hlc = hlc.now()))
            db.taskQueries.byList(id).executeAsList().forEach { row ->
                putTask(row.toModel().copy(deleted = true, hlc = hlc.now()))
            }
        }
    }

    // ---------- task writes ----------

    suspend fun addTask(
        listId: String,
        title: String,
        parentId: String? = null,
        dueDate: LocalDate? = null,
        dueTime: LocalTime? = null,
    ): Task = write {
        requireList(listId)
        if (parentId != null) checkParent(parentId, listId)
        Task(
            id = Ids.newId(), listId = listId, parentId = parentId, title = title,
            dueDate = dueDate, dueTime = dueTime,
            sortKey = SortKey.between(null, firstSiblingKey(listId, parentId)),
            hlc = hlc.now(),
        ).also { putTask(it) }
    }

    /** Caller passes an edited copy; the repository restamps hlc. */
    suspend fun updateTask(task: Task) {
        write {
            requireTask(task.id)
            if (task.parentId != null) {
                checkParent(task.parentId, task.listId)
                require(db.taskQueries.children(task.id).executeAsList().isEmpty()) {
                    "a task with subtasks cannot become a subtask"
                }
            }
            putTask(task.copy(hlc = hlc.now()))
        }
    }

    /** Tombstones the task and its subtasks. */
    suspend fun deleteTask(id: String) {
        write {
            putTask(requireTask(id).copy(deleted = true, hlc = hlc.now()))
            db.taskQueries.children(id).executeAsList().forEach { row ->
                putTask(row.toModel().copy(deleted = true, hlc = hlc.now()))
            }
        }
    }

    /** [beforeId] ends up directly above the task, [afterId] directly below; null = open end. */
    suspend fun move(id: String, beforeId: String?, afterId: String?) {
        write {
            val task = requireTask(id)
            val before = beforeId?.let { requireTask(it).sortKey }
            val after = afterId?.let { requireTask(it).sortKey }
            putTask(task.copy(sortKey = SortKey.between(before, after), hlc = hlc.now()))
        }
    }

    suspend fun snooze(id: String, until: Instant) {
        write { putTask(requireTask(id).copy(snoozeUntil = until, hlc = hlc.now())) }
    }

    /** "Make task" from the Notes view: adds the task and links the note, in one transaction. */
    suspend fun noteToTask(noteId: String, listId: String): Task = write {
        val note = noteRow(noteId)?.takeIf { !it.deleted } ?: throw IllegalArgumentException("no note $noteId")
        require(note.taskId == null) { "note $noteId is already a task" }
        requireList(listId)
        val title = note.text.lineSequence().map { it.trim() }.firstOrNull { it.isNotEmpty() }?.take(200)
            ?: throw IllegalArgumentException("note $noteId is empty")
        val task = Task(
            id = Ids.newId(), listId = listId, title = title,
            sortKey = SortKey.between(null, firstSiblingKey(listId, null)),
            hlc = hlc.now(),
        )
        putTask(task)
        putNote(note.copy(taskId = task.id, hlc = hlc.now()))
        task
    }
```

Add to the `// ---------- internals ----------` section:

```kotlin
    private fun checkParent(parentId: String, listId: String) {
        val parent = taskRow(parentId)?.takeIf { !it.deleted }
            ?: throw IllegalArgumentException("no parent task $parentId")
        require(parent.parentId == null) { "subtasks are one level only" }
        require(parent.listId == listId) { "subtask must be in its parent's list" }
    }

    private fun firstSiblingKey(listId: String, parentId: String?): String? =
        db.taskQueries.byList(listId).executeAsList()
            .filter { it.parent_id == parentId }
            .minOfOrNull { it.sort_key }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.RepositoryTasksTest'`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/TaskRepository.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryTasksTest.kt
git commit -m "feat(client): task add/update/delete/move/snooze/noteToTask with one-level subtasks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr"
```

---

### Task 4: Complete / uncomplete with repeat (shared `Completion`, deterministic next occurrence, month anchor)

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/Completion.kt`
- Modify: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/TaskRepository.kt`
- Test: `shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/CompletionTest.kt`
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryCompleteTest.kt`

**Interfaces:**
- Consumes: Phase 1 `Recurrence.next(rule: RepeatRule, from: LocalDate): LocalDate`, `RepeatRule.anchorDay`, `Ids.derived(name: String): String`; Task 3 `firstSiblingKey`, `updateTask`.
- Produces (contract, package `com.sagunkayastha.adhdhelper.core`, so Phase 6's server tools reuse it):
  - `object Completion { fun nextOccurrence(task: Task, sortKey: String, hlc: String): Task?; fun anchored(task: Task): Task }`
  - `nextOccurrence`: null when `task.repeat` or `task.dueDate` is null; otherwise a new row with id `Ids.derived("${task.id}:${nextDate}")`, `dueDate = Recurrence.next(rule, dueDate)`, same `listId`/`parentId`/`title`/`details`/`starred`/`dueTime`/`repeat` (incl. `anchorDay`), `completedAt = null`, `snoozeUntil = null`, the given `sortKey` and `hlc`.
  - `anchored`: if `task.repeat` is MONTHLY or YEARLY with `anchorDay == null` and `task.dueDate != null`, returns the task with `repeat.anchorDay = dueDate.day`; otherwise returns `task` unchanged.
- Produces (contract): `complete(id)`, `uncomplete(id)`; `updateTask` now stores `Completion.anchored(task)` (`addTask` takes no rule, so `updateTask` is where rules are set).
- Semantics: `complete` on an already-completed task is a no-op. For a task with `repeat != null` and `dueDate != null`, it also inserts `Completion.nextOccurrence(task, sortKey = top of its siblings, hlc)` unless a row with that id already exists locally (live or tombstoned). A repeating task without `dueDate` gets no next occurrence (there is no date to step from). `uncomplete` clears `completedAt` and leaves any next occurrence alone.

- [ ] **Step 1: Write the failing tests**

`shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/CompletionTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.core

import com.sagunkayastha.adhdhelper.model.Freq
import com.sagunkayastha.adhdhelper.model.RepeatRule
import com.sagunkayastha.adhdhelper.model.Task
import com.sagunkayastha.adhdhelper.sync.Ids
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.time.Instant
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime

class CompletionTest {
    private val base = Task(
        id = "t1", listId = "l1", title = "Water plants", details = "balcony", starred = true,
        dueDate = LocalDate(2026, 10, 9), dueTime = LocalTime(18, 0),
        repeat = RepeatRule(Freq.DAILY), sortKey = "m", hlc = "h0",
        snoozeUntil = Instant.parse("2026-10-09T23:00:00Z"),
    )

    @Test
    fun nonRepeatingOrUndatedHasNoNext() {
        assertNull(Completion.nextOccurrence(base.copy(repeat = null), "a", "h1"))
        assertNull(Completion.nextOccurrence(base.copy(dueDate = null, dueTime = null), "a", "h1"))
    }

    @Test
    fun dailyNextHasDerivedIdAndFreshState() {
        val next = Completion.nextOccurrence(base, "a", "h1")!!
        assertEquals(Ids.derived("t1:2026-10-10"), next.id)
        assertEquals(LocalDate(2026, 10, 10), next.dueDate)
        assertEquals(LocalTime(18, 0), next.dueTime)
        assertEquals("Water plants", next.title)
        assertEquals("balcony", next.details)
        assertEquals(true, next.starred)
        assertEquals(base.repeat, next.repeat)
        assertNull(next.completedAt)
        assertNull(next.snoozeUntil)
        assertEquals("a", next.sortKey)
        assertEquals("h1", next.hlc)
    }

    @Test
    fun sameTaskAlwaysGivesSameNextId() {
        assertEquals(
            Completion.nextOccurrence(base, "a", "h1")!!.id,
            Completion.nextOccurrence(base, "b", "h9")!!.id,
        )
    }

    @Test
    fun anchoredSetsAnchorDayForMonthlyAndYearlyOnly() {
        val jan31 = base.copy(dueDate = LocalDate(2027, 1, 31))
        assertEquals(31, Completion.anchored(jan31.copy(repeat = RepeatRule(Freq.MONTHLY))).repeat!!.anchorDay)
        assertEquals(31, Completion.anchored(jan31.copy(repeat = RepeatRule(Freq.YEARLY))).repeat!!.anchorDay)
        assertNull(Completion.anchored(jan31).repeat!!.anchorDay)   // DAILY: no anchor
        val kept = jan31.copy(repeat = RepeatRule(Freq.MONTHLY, anchorDay = 15))
        assertEquals(kept, Completion.anchored(kept))   // existing anchor is kept
        val undated = base.copy(dueDate = null, repeat = RepeatRule(Freq.MONTHLY))
        assertEquals(undated, Completion.anchored(undated))
    }

    @Test
    fun nextOccurrenceKeepsTheAnchor() {
        val rule = RepeatRule(Freq.MONTHLY, anchorDay = 31)
        val feb = Completion.nextOccurrence(base.copy(dueDate = LocalDate(2027, 1, 31), repeat = rule), "a", "h1")!!
        assertEquals(LocalDate(2027, 2, 28), feb.dueDate)
        assertEquals(rule, feb.repeat)
        assertEquals(LocalDate(2027, 3, 31), Completion.nextOccurrence(feb, "a", "h2")!!.dueDate)
    }
}
```

`shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryCompleteTest.kt`:

`shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryCompleteTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.model.Freq
import com.sagunkayastha.adhdhelper.model.RepeatRule
import com.sagunkayastha.adhdhelper.sync.Ids
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime

class RepositoryCompleteTest {
    private val day = LocalDate(2026, 10, 9)

    @Test
    fun completingPlainTaskOnlySetsCompletedAt() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        val t = d.repo.addTask(list.id, "once")
        d.repo.complete(t.id)
        val rows = d.repo.tasks(list.id).first()
        assertEquals(1, rows.size)
        assertNotNull(rows.single().completedAt)
        d.repo.uncomplete(t.id)
        assertNull(d.repo.tasks(list.id).first().single().completedAt)
    }

    @Test
    fun completingRepeatingTaskInsertsDerivedNextOccurrence() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        val t = d.repo.addTask(list.id, "water plants", dueDate = day, dueTime = LocalTime(18, 0))
        d.repo.updateTask(t.copy(details = "balcony", starred = true, repeat = RepeatRule(Freq.DAILY)))
        d.repo.complete(t.id)

        val rows = d.repo.tasks(list.id).first()
        assertEquals(2, rows.size)
        val original = rows.single { it.id == t.id }
        val next = rows.single { it.id != t.id }
        assertNotNull(original.completedAt)
        assertEquals(Ids.derived("${t.id}:2026-10-10"), next.id)
        assertEquals(LocalDate(2026, 10, 10), next.dueDate)
        assertEquals(LocalTime(18, 0), next.dueTime)
        assertEquals("water plants", next.title)
        assertEquals("balcony", next.details)
        assertEquals(true, next.starred)
        assertEquals(RepeatRule(Freq.DAILY), next.repeat)
        assertEquals(list.id, next.listId)
        assertNull(next.completedAt)
        assertNotEquals(original.sortKey, next.sortKey)
        assertEquals(next.hlc, d.db.outboxQueries.all().executeAsList().single { it.id == next.id }.hlc)
    }

    @Test
    fun completingTwiceQuicklyGivesOneNextOccurrence() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        val t = d.repo.addTask(list.id, "daily", dueDate = day)
        d.repo.updateTask(t.copy(repeat = RepeatRule(Freq.DAILY)))
        d.repo.complete(t.id)
        d.repo.complete(t.id)
        d.repo.uncomplete(t.id)
        d.repo.complete(t.id)
        assertEquals(2, d.repo.tasks(list.id).first().size)
    }

    @Test
    fun monthly31stWalksBackToThe31st() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        val t = d.repo.addTask(list.id, "pay rent", dueDate = LocalDate(2027, 1, 31))
        d.repo.updateTask(t.copy(repeat = RepeatRule(Freq.MONTHLY)))
        assertEquals(31, d.repo.tasks(list.id).first().single().repeat!!.anchorDay)   // anchored on set

        d.repo.complete(t.id)
        val feb = d.repo.tasks(list.id).first().single { it.completedAt == null }
        assertEquals(LocalDate(2027, 2, 28), feb.dueDate)
        d.repo.complete(feb.id)
        val mar = d.repo.tasks(list.id).first().single { it.completedAt == null }
        assertEquals(LocalDate(2027, 3, 31), mar.dueDate)
    }

    @Test
    fun repeatingTaskWithoutDueDateGetsNoNextOccurrence() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("L")
        val t = d.repo.addTask(list.id, "undated")
        d.repo.updateTask(t.copy(repeat = RepeatRule(Freq.WEEKLY)))
        d.repo.complete(t.id)
        assertEquals(1, d.repo.tasks(list.id).first().size)
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.core.CompletionTest' --tests 'com.sagunkayastha.adhdhelper.client.RepositoryCompleteTest'`
Expected: FAIL to compile with `Unresolved reference: Completion` / `complete`.

- [ ] **Step 3: Write `Completion` and `complete` / `uncomplete`**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/Completion.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.core

import com.sagunkayastha.adhdhelper.model.Freq
import com.sagunkayastha.adhdhelper.model.Task
import com.sagunkayastha.adhdhelper.sync.Ids

/** One recurrence path for every writer: client repository (Phase 3) and server tools (Phase 6). */
object Completion {
    /**
     * The row to insert when [task] is completed, or null if it does not repeat or has no due date.
     * The id is derived from task id + next date, so every device (and the server) makes the same row.
     */
    fun nextOccurrence(task: Task, sortKey: String, hlc: String): Task? {
        val rule = task.repeat ?: return null
        val due = task.dueDate ?: return null
        val nextDate = Recurrence.next(rule, due)
        return Task(
            id = Ids.derived("${task.id}:${nextDate}"), listId = task.listId, parentId = task.parentId,
            title = task.title, details = task.details, starred = task.starred,
            dueDate = nextDate, dueTime = task.dueTime, repeat = rule,
            sortKey = sortKey, hlc = hlc,
        )
    }

    /** Pins a MONTHLY/YEARLY rule to its due day when the rule is set, so the 31st survives a short month. */
    fun anchored(task: Task): Task {
        val rule = task.repeat ?: return task
        val due = task.dueDate ?: return task
        if (rule.anchorDay != null || (rule.freq != Freq.MONTHLY && rule.freq != Freq.YEARLY)) return task
        return task.copy(repeat = rule.copy(anchorDay = due.day))
    }
}
```

Add the import to `TaskRepository.kt`:

```kotlin
import com.sagunkayastha.adhdhelper.core.Completion
```

In `updateTask` (Task 3), change the last line of the `write { }` block from `putTask(task.copy(hlc = hlc.now()))` to:

```kotlin
            putTask(Completion.anchored(task).copy(hlc = hlc.now()))
```

Add after `noteToTask` in the task-writes section:

```kotlin
    /** Marks done; for a repeating dated task also inserts the next occurrence (deterministic id). */
    suspend fun complete(id: String) {
        write {
            val task = requireTask(id)
            if (task.completedAt == null) {
                putTask(task.copy(completedAt = now(), hlc = hlc.now()))
                Completion.nextOccurrence(
                    task,
                    sortKey = SortKey.between(null, firstSiblingKey(task.listId, task.parentId)),
                    hlc = hlc.now(),
                )?.takeIf { taskRow(it.id) == null }?.let { putTask(it) }
            }
        }
    }

    suspend fun uncomplete(id: String) {
        write { putTask(requireTask(id).copy(completedAt = null, hlc = hlc.now())) }
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.core.CompletionTest' --tests 'com.sagunkayastha.adhdhelper.client.RepositoryCompleteTest'`
Expected: PASS (5 + 5 tests).

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/Completion.kt shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/CompletionTest.kt shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/TaskRepository.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryCompleteTest.kt
git commit -m "feat(client): complete/uncomplete via shared Completion, month-end anchor

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr"
```

---

### Task 5: applyRemote, full snapshot, pending count

**Files:**
- Modify: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/TaskRepository.kt`
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryRemoteTest.kt`

**Interfaces:**
- Consumes: Phase 1 `Merge.wins(incoming, existing)`, `Hlc.observe(remote)`.
- Produces (contract): `applyRemote(changes: Changes)`: each row goes through `hlc.observe(row.hlc)`, then is upserted only if `Merge.wins(row, local)`; when it wins, any outbox entry for that `(kind, id)` is removed (the local edit lost, so there is nothing left to send). No outbox writes, no `onLocalChange`.
- Produces (internal, used by `SyncClient` in Task 8):
  - `internal suspend fun applyFullSnapshot(changes: Changes)`: `applyRemote` rules, then hard-deletes every local row of each kind whose id is neither in `changes` nor in the outbox.
  - `internal suspend fun pendingCount(): Int`: outbox row count.

- [ ] **Step 1: Write the failing test**

`shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryRemoteTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.model.TaskList
import com.sagunkayastha.adhdhelper.sync.Changes
import com.sagunkayastha.adhdhelper.sync.Hlc
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest

class RepositoryRemoteTest {
    @Test
    fun newerRemoteRowWinsWithoutOutboxOrNotification() = runTest {
        val d = TestDevice()
        val local = d.repo.addList("local")
        d.repo.clearOutbox(d.repo.drainOutbox())
        val before = d.localChanges
        val remote = local.copy(title = "remote", hlc = Hlc("other") { 5_000_000L }.now())
        d.repo.applyRemote(Changes(lists = listOf(remote)))
        assertEquals(listOf(remote), d.repo.lists().first())
        assertTrue(d.repo.drainOutbox().isEmpty())
        assertEquals(before, d.localChanges)
    }

    @Test
    fun olderRemoteRowIsIgnoredAndSameHlcIsANoOp() = runTest {
        val d = TestDevice()
        val local = d.repo.addList("local")
        d.repo.applyRemote(Changes(lists = listOf(local.copy(title = "stale", hlc = Hlc("other") { 1L }.now()))))
        d.repo.applyRemote(Changes(lists = listOf(local.copy(title = "same hlc"))))
        assertEquals("local", d.repo.lists().first().single().title)
    }

    @Test
    fun applyRemoteAdvancesLocalClockPastRemoteHlc() = runTest {
        val d = TestDevice()   // local wall clock 1_000_000
        val remoteHlc = Hlc("other") { 99_000_000L }.now()
        d.repo.applyRemote(Changes(lists = listOf(TaskList("r1", "remote", "a0", remoteHlc))))
        val mine = d.repo.addList("mine")
        assertTrue(mine.hlc > remoteHlc)
    }

    @Test
    fun remoteWinOverPendingEditDropsOutboxEntry() = runTest {
        val d = TestDevice()
        val local = d.repo.addList("pending edit")
        val remote = local.copy(title = "remote", hlc = Hlc("other") { 5_000_000L }.now())
        d.repo.applyRemote(Changes(lists = listOf(remote)))
        assertEquals(0, d.repo.pendingCount())
    }

    @Test
    fun fullSnapshotRemovesRowsMissingFromServerButKeepsPendingOnes() = runTest {
        val d = TestDevice()
        val synced = d.repo.addList("synced, later purged on server")
        val keptOnServer = d.repo.addList("still on server")
        d.repo.clearOutbox(d.repo.drainOutbox())
        val pending = d.repo.addList("made offline")
        val fromServer = TaskList("s1", "from server", "b0", Hlc("other") { 2_000_000L }.now())

        d.repo.applyFullSnapshot(Changes(lists = listOf(keptOnServer, fromServer)))

        val titles = d.repo.lists().first().map { it.title }.toSet()
        assertEquals(setOf("still on server", "from server", "made offline"), titles)
        assertTrue(d.db.taskListQueries.byId(synced.id).executeAsOneOrNull() == null)
        assertEquals(listOf(pending.id), d.repo.drainOutbox().lists.map { it.id })
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.RepositoryRemoteTest'`
Expected: FAIL to compile with `Unresolved reference: applyRemote`.

- [ ] **Step 3: Implement remote apply**

Add the import to `TaskRepository.kt`:

```kotlin
import com.sagunkayastha.adhdhelper.sync.Merge
```

Add a new section before `// ---------- internals ----------`:

```kotlin
    // ---------- remote ----------

    /** Merge rule (LWW by hlc); never writes the outbox, never calls onLocalChange. */
    suspend fun applyRemote(changes: Changes) {
        lock.withLock {
            withContext(DbDispatcher) { db.transaction { applyRows(changes) } }
        }
    }

    /** Server sent a full snapshot (our cursor was older than its purge horizon). */
    internal suspend fun applyFullSnapshot(changes: Changes) {
        lock.withLock {
            withContext(DbDispatcher) {
                db.transaction {
                    applyRows(changes)
                    val pending = db.outboxQueries.all().executeAsList().map { it.kind to it.id }.toSet()
                    fun stale(kind: String, localIds: List<String>, keep: Set<String>) =
                        localIds.filter { it !in keep && (kind to it) !in pending }
                    stale(KIND_LIST, db.taskListQueries.allIds().executeAsList(), changes.lists.map { it.id }.toSet())
                        .forEach { db.taskListQueries.hardDelete(it) }
                    stale(KIND_TASK, db.taskQueries.allIds().executeAsList(), changes.tasks.map { it.id }.toSet())
                        .forEach { db.taskQueries.hardDelete(it) }
                    stale(KIND_NOTE, db.noteQueries.allIds().executeAsList(), changes.notes.map { it.id }.toSet())
                        .forEach { db.noteQueries.hardDelete(it) }
                    stale(KIND_MESSAGE, db.chatMessageQueries.allIds().executeAsList(), changes.messages.map { it.id }.toSet())
                        .forEach { db.chatMessageQueries.hardDelete(it) }
                }
            }
        }
    }

    internal suspend fun pendingCount(): Int = withContext(DbDispatcher) {
        db.outboxQueries.count().executeAsOne().toInt()
    }
```

Add to the internals section:

```kotlin
    private fun applyRows(changes: Changes) {
        changes.lists.forEach { row ->
            hlc.observe(row.hlc)
            if (Merge.wins(row, listRow(row.id))) {
                db.taskListQueries.upsert(row.toRow())
                db.outboxQueries.remove(KIND_LIST, row.id)
            }
        }
        changes.tasks.forEach { row ->
            hlc.observe(row.hlc)
            if (Merge.wins(row, taskRow(row.id))) {
                db.taskQueries.upsert(row.toRow())
                db.outboxQueries.remove(KIND_TASK, row.id)
            }
        }
        changes.notes.forEach { row ->
            hlc.observe(row.hlc)
            if (Merge.wins(row, noteRow(row.id))) {
                db.noteQueries.upsert(row.toRow())
                db.outboxQueries.remove(KIND_NOTE, row.id)
            }
        }
        changes.messages.forEach { row ->
            hlc.observe(row.hlc)
            if (Merge.wins(row, messageRow(row.id))) {
                db.chatMessageQueries.upsert(row.toRow())
                db.outboxQueries.remove(KIND_MESSAGE, row.id)
            }
        }
    }
```

- [ ] **Step 4: Run test to verify it passes, then the whole repository suite**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.RepositoryRemoteTest'`
Expected: PASS (5 tests).

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.*'`
Expected: PASS (all client tests so far).

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/TaskRepository.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/RepositoryRemoteTest.kt
git commit -m "feat(client): applyRemote via Merge.wins/Hlc.observe, full-snapshot apply

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr"
```

---

### Task 6: AppSettings (interface, JVM file 0600, Android prefs + Keystore token)

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/AppSettings.kt`
- Create: `shared/src/jvmMain/kotlin/com/sagunkayastha/adhdhelper/client/FileAppSettings.kt`
- Create: `shared/src/androidMain/kotlin/com/sagunkayastha/adhdhelper/client/AndroidAppSettings.kt`
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/FileAppSettingsTest.kt`

**Interfaces:**
- Produces (contract): `interface AppSettings { var serverUrl: String?; var token: String?; var cursor: Long; var deviceId: String; var zone: String; var nagEnabled: Boolean; var model: String }`.
- Produces (public): `object SettingsDefaults { const val ZONE = "America/Denver"; const val MODEL = "claude-sonnet-5-5"; const val NAG_ENABLED = true }`; `class FileAppSettings(path: java.nio.file.Path) : AppSettings` (jvmMain; desktop passes e.g. `dist/data/settings.properties`); `class AndroidAppSettings(context: Context) : AppSettings` (androidMain).
- Semantics: `deviceId` is generated with `Ids.newId()` on first read and persisted. Defaults: `cursor = 0`, `zone = SettingsDefaults.ZONE`, `nagEnabled = true`, `model = SettingsDefaults.MODEL`. Setting `token = null` removes it.
- Token storage choice (Android): AES-256-GCM key held in `AndroidKeyStore`, ciphertext in SharedPreferences. No extra dependency (the `androidx.security:security-crypto` library is deprecated, so it is not used). The Keystore cannot run under Robolectric/JVM, so Android settings are verified here by compilation only; Phase 4 exercises them on device.

- [ ] **Step 1: Write the failing test**

`shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/FileAppSettingsTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class FileAppSettingsTest {
    private val path = Files.createTempDirectory("settings").resolve("nested/settings.properties")

    @Test
    fun defaultsWhenFileMissing() {
        val s = FileAppSettings(path)
        assertNull(s.serverUrl)
        assertNull(s.token)
        assertEquals(0L, s.cursor)
        assertEquals("America/Denver", s.zone)
        assertEquals(true, s.nagEnabled)
        assertEquals("claude-sonnet-5-5", s.model)
    }

    @Test
    fun valuesPersistAcrossInstances() {
        val s = FileAppSettings(path)
        s.serverUrl = "https://tasks.sagunkayastha.com"
        s.token = "secret-token"
        s.cursor = 42
        s.nagEnabled = false
        s.model = "claude-haiku-4-5"
        s.zone = "Asia/Kathmandu"
        val again = FileAppSettings(path)
        assertEquals("https://tasks.sagunkayastha.com", again.serverUrl)
        assertEquals("secret-token", again.token)
        assertEquals(42L, again.cursor)
        assertEquals(false, again.nagEnabled)
        assertEquals("claude-haiku-4-5", again.model)
        assertEquals("Asia/Kathmandu", again.zone)
    }

    @Test
    fun deviceIdIsGeneratedOnceAndKept() {
        val id = FileAppSettings(path).deviceId
        assertEquals(36, id.length)
        assertEquals(id, FileAppSettings(path).deviceId)
    }

    @Test
    fun clearingTokenRemovesIt() {
        val s = FileAppSettings(path)
        s.token = "t"
        s.token = null
        assertNull(FileAppSettings(path).token)
    }

    @Test
    fun fileIsOwnerReadWriteOnly() {
        FileAppSettings(path).token = "t"
        assertEquals(PosixFilePermissions.fromString("rw-------"), Files.getPosixFilePermissions(path))
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.FileAppSettingsTest'`
Expected: FAIL to compile with `Unresolved reference: FileAppSettings`.

- [ ] **Step 3: Write the interface and both implementations**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/AppSettings.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

interface AppSettings {
    var serverUrl: String?
    var token: String?
    var cursor: Long
    var deviceId: String
    var zone: String
    var nagEnabled: Boolean
    var model: String
}

object SettingsDefaults {
    const val ZONE = "America/Denver"
    const val MODEL = "claude-sonnet-5-5"
    const val NAG_ENABLED = true
}
```

`shared/src/jvmMain/kotlin/com/sagunkayastha/adhdhelper/client/FileAppSettings.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.sync.Ids
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.attribute.PosixFilePermissions
import java.util.Properties

/** Desktop settings in a Java properties file; every save writes a fresh 0600 file atomically. */
class FileAppSettings(private val path: Path) : AppSettings {
    private val props = Properties().apply {
        if (Files.exists(path)) Files.newInputStream(path).use { load(it) }
    }

    private fun read(key: String): String? = synchronized(props) { props.getProperty(key) }

    private fun put(key: String, value: String?) = synchronized(props) {
        if (value == null) props.remove(key) else props.setProperty(key, value)
        save()
    }

    private fun save() {
        path.toAbsolutePath().parent?.let { Files.createDirectories(it) }
        val tmp = path.resolveSibling("${path.fileName}.tmp")
        Files.deleteIfExists(tmp)
        Files.createFile(tmp, PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")))
        Files.newOutputStream(tmp).use { props.store(it, null) }
        Files.move(tmp, path, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
    }

    override var serverUrl: String?
        get() = read("serverUrl")
        set(value) = put("serverUrl", value)

    override var token: String?
        get() = read("token")
        set(value) = put("token", value)

    override var cursor: Long
        get() = read("cursor")?.toLongOrNull() ?: 0L
        set(value) = put("cursor", value.toString())

    override var deviceId: String
        get() = read("deviceId") ?: Ids.newId().also { put("deviceId", it) }
        set(value) = put("deviceId", value)

    override var zone: String
        get() = read("zone") ?: SettingsDefaults.ZONE
        set(value) = put("zone", value)

    override var nagEnabled: Boolean
        get() = read("nagEnabled")?.toBooleanStrictOrNull() ?: SettingsDefaults.NAG_ENABLED
        set(value) = put("nagEnabled", value.toString())

    override var model: String
        get() = read("model") ?: SettingsDefaults.MODEL
        set(value) = put("model", value)
}
```

`shared/src/androidMain/kotlin/com/sagunkayastha/adhdhelper/client/AndroidAppSettings.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.sagunkayastha.adhdhelper.sync.Ids
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** SharedPreferences for plain settings; the device token is AES-GCM encrypted with an Android Keystore key. */
class AndroidAppSettings(context: Context) : AppSettings {
    private val prefs = context.applicationContext.getSharedPreferences("adhd_settings", Context.MODE_PRIVATE)

    override var serverUrl: String?
        get() = prefs.getString("serverUrl", null)
        set(value) = prefs.edit().putString("serverUrl", value).apply()

    override var token: String?
        get() = prefs.getString("tokenEnc", null)?.let { TokenCipher.decrypt(it) }
        set(value) {
            val edit = prefs.edit()
            if (value == null) edit.remove("tokenEnc") else edit.putString("tokenEnc", TokenCipher.encrypt(value))
            edit.apply()
        }

    override var cursor: Long
        get() = prefs.getLong("cursor", 0L)
        set(value) = prefs.edit().putLong("cursor", value).apply()

    override var deviceId: String
        get() = prefs.getString("deviceId", null) ?: Ids.newId().also { deviceId = it }
        set(value) = prefs.edit().putString("deviceId", value).apply()

    override var zone: String
        get() = prefs.getString("zone", null) ?: SettingsDefaults.ZONE
        set(value) = prefs.edit().putString("zone", value).apply()

    override var nagEnabled: Boolean
        get() = prefs.getBoolean("nagEnabled", SettingsDefaults.NAG_ENABLED)
        set(value) = prefs.edit().putBoolean("nagEnabled", value).apply()

    override var model: String
        get() = prefs.getString("model", null) ?: SettingsDefaults.MODEL
        set(value) = prefs.edit().putString("model", value).apply()
}

internal object TokenCipher {
    private const val ALIAS = "adhd_helper_token"
    private const val TRANSFORM = "AES/GCM/NoPadding"
    private const val IV_BYTES = 12

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as SecretKey?)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return gen.generateKey()
    }

    fun encrypt(plain: String): String {
        val cipher = Cipher.getInstance(TRANSFORM).apply { init(Cipher.ENCRYPT_MODE, key()) }
        val out = cipher.iv + cipher.doFinal(plain.encodeToByteArray())
        return Base64.encodeToString(out, Base64.NO_WRAP)
    }

    /** Null if the key is gone (e.g. app data restored to another phone): the app re-pairs. */
    fun decrypt(encoded: String): String? = runCatching {
        val bytes = Base64.decode(encoded, Base64.NO_WRAP)
        val cipher = Cipher.getInstance(TRANSFORM).apply {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes, 0, IV_BYTES))
        }
        cipher.doFinal(bytes, IV_BYTES, bytes.size - IV_BYTES).decodeToString()
    }.getOrNull()
}
```

- [ ] **Step 4: Run test to verify it passes, and Android compiles**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.FileAppSettingsTest'`
Expected: PASS (5 tests).

Run: `gradle :shared:compileDebugKotlinAndroid`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/AppSettings.kt shared/src/jvmMain/kotlin/com/sagunkayastha/adhdhelper/client/FileAppSettings.kt shared/src/androidMain/kotlin/com/sagunkayastha/adhdhelper/client/AndroidAppSettings.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/FileAppSettingsTest.kt
git commit -m "feat(client): AppSettings with 0600 desktop file and Keystore-encrypted Android token

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr"
```

---

### Task 7: HTTP client and KtorSyncApi

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/Http.kt`
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/SyncApi.kt`
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/KtorSyncApiTest.kt`

**Interfaces:**
- Consumes: Phase 1 `SyncRequest`, `SyncResponse`, `Changes`, `Api.PREFIX`; Task 6 `AppSettings`.
- Produces (contract): `interface SyncApi { suspend fun sync(req: SyncRequest): SyncResponse }`, `class KtorSyncApi(http: HttpClient, settings: AppSettings) : SyncApi`.
- Produces (public, also for Phase 4/6):
  - `val ClientJson: Json` (`ignoreUnknownKeys = true`).
  - `fun createHttpClient(): HttpClient`: platform default engine (OkHttp on Android, CIO on JVM), ContentNegotiation with `ClientJson`, WebSockets, 10 s connect timeout.
  - `class UnauthorizedException : Exception` (HTTP 401 or no token) and `class ServerException(val status: Int) : Exception` (any other non-2xx).
- Semantics: `KtorSyncApi.sync` posts JSON to `${serverUrl without trailing slash}/api/v1/sync` with `Authorization: Bearer <token>`. Connection failures propagate as the engine's exception (SyncClient treats them as offline). The `HttpClient` passed in must have ContentNegotiation installed (true for `createHttpClient()` and for the test clients).

- [ ] **Step 1: Write the failing test**

`shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/KtorSyncApiTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.model.TaskList
import com.sagunkayastha.adhdhelper.sync.Changes
import com.sagunkayastha.adhdhelper.sync.SyncRequest
import com.sagunkayastha.adhdhelper.sync.SyncResponse
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.toByteArray
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlinx.coroutines.test.runTest

class KtorSyncApiTest {
    private fun settings(url: String = "https://tasks.example.com/") =
        FileAppSettings(Files.createTempDirectory("s").resolve("settings.properties")).apply {
            serverUrl = url
            token = "tok-123"
        }

    private fun client(status: HttpStatusCode, body: String, check: suspend (io.ktor.client.request.HttpRequestData) -> Unit = {}) =
        HttpClient(MockEngine { request ->
            check(request)
            respond(body, status, headersOf(HttpHeaders.ContentType, "application/json"))
        }) { install(ContentNegotiation) { json(ClientJson) } }

    @Test
    fun postsBearerJsonAndDecodesReply() = runTest {
        val reply = SyncResponse(cursor = 7, changes = Changes(lists = listOf(TaskList("l1", "Inbox", "a0", "h"))))
        val sent = SyncRequest(cursor = 3, changes = Changes(lists = listOf(TaskList("l2", "Work", "a1", "h2"))))
        var seen: SyncRequest? = null
        val http = client(HttpStatusCode.OK, ClientJson.encodeToString(SyncResponse.serializer(), reply)) { req ->
            assertEquals(HttpMethod.Post, req.method)
            assertEquals("https://tasks.example.com/api/v1/sync", req.url.toString())
            assertEquals("Bearer tok-123", req.headers[HttpHeaders.Authorization])
            seen = ClientJson.decodeFromString(SyncRequest.serializer(), req.body.toByteArray().decodeToString())
        }
        assertEquals(reply, KtorSyncApi(http, settings()).sync(sent))
        assertEquals(sent, seen)
    }

    @Test
    fun unauthorizedBecomesUnauthorizedException() = runTest {
        val http = client(HttpStatusCode.Unauthorized, "{}")
        assertFailsWith<UnauthorizedException> { KtorSyncApi(http, settings()).sync(SyncRequest(0, Changes())) }
    }

    @Test
    fun missingTokenIsUnauthorizedWithoutARequest() = runTest {
        var calls = 0
        val http = client(HttpStatusCode.OK, "{}") { calls++ }
        val s = settings().apply { token = null }
        assertFailsWith<UnauthorizedException> { KtorSyncApi(http, s).sync(SyncRequest(0, Changes())) }
        assertEquals(0, calls)
    }

    @Test
    fun serverErrorBecomesServerException() = runTest {
        val http = client(HttpStatusCode.InternalServerError, "{}")
        val e = assertFailsWith<ServerException> { KtorSyncApi(http, settings("http://h:8020")).sync(SyncRequest(0, Changes())) }
        assertEquals(500, e.status)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.KtorSyncApiTest'`
Expected: FAIL to compile with `Unresolved reference: KtorSyncApi` / `ClientJson`.

- [ ] **Step 3: Implement**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/Http.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import io.ktor.client.HttpClient
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

val ClientJson: Json = Json { ignoreUnknownKeys = true }

/** Default engine from the classpath: OkHttp on Android, CIO on desktop. */
fun createHttpClient(): HttpClient = HttpClient {
    install(ContentNegotiation) { json(ClientJson) }
    install(WebSockets)
    install(HttpTimeout) { connectTimeoutMillis = 10_000 }
}

/** HTTP 401, or no token stored. Never carries the token. */
class UnauthorizedException : Exception("unauthorized")

/** Any other non-2xx reply. */
class ServerException(val status: Int) : Exception("server returned $status")
```

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/SyncApi.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.core.Api
import com.sagunkayastha.adhdhelper.sync.SyncRequest
import com.sagunkayastha.adhdhelper.sync.SyncResponse
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.bearerAuth
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.isSuccess

interface SyncApi {
    suspend fun sync(req: SyncRequest): SyncResponse
}

class KtorSyncApi(private val http: HttpClient, private val settings: AppSettings) : SyncApi {
    override suspend fun sync(req: SyncRequest): SyncResponse {
        val base = settings.serverUrl ?: throw IllegalStateException("not paired")
        val token = settings.token ?: throw UnauthorizedException()
        val response = http.post(base.trimEnd('/') + Api.PREFIX + "/sync") {
            bearerAuth(token)
            contentType(ContentType.Application.Json)
            setBody(req)
        }
        when {
            response.status == HttpStatusCode.Unauthorized -> throw UnauthorizedException()
            !response.status.isSuccess() -> throw ServerException(response.status.value)
        }
        return response.body()
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.KtorSyncApiTest'`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/Http.kt shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/SyncApi.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/KtorSyncApiTest.kt
git commit -m "feat(client): KtorSyncApi with bearer auth and typed 401/5xx errors

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr"
```

---

### Task 8: SyncClient

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/SyncClient.kt`
- Create: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/FakeSyncServer.kt`
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/SyncClientTest.kt`

**Interfaces:**
- Consumes: Task 5 `applyRemote`, `applyFullSnapshot`, `pendingCount`; Task 2 `drainOutbox`, `clearOutbox`; Task 7 `SyncApi`, `UnauthorizedException`, `ServerException`; Task 6 `AppSettings`.
- Produces (contract): `data class SyncState(val online: Boolean, val pending: Int, val lastError: String?)`; `class SyncClient(api: SyncApi, repo: TaskRepository, settings: AppSettings) { val state: StateFlow<SyncState>; suspend fun syncOnce(): Boolean }`.
- Semantics of `syncOnce()` (serialised by a mutex; returns `true` only on a completed sync):
  1. No `serverUrl` or no `token` -> `state = (online=false, pending, lastError="not paired")`, `false`.
  2. `sent = repo.drainOutbox()`; `api.sync(SyncRequest(settings.cursor, sent))`.
  3. `UnauthorizedException` -> `settings.token = null`, `state = (online=true, pending, "unauthorized")`, `false`. Outbox and local data kept.
  4. `ServerException(s)` -> `state = (online=true, pending, "server error s")`, `false`.
  5. Any other exception (network) -> `state = (online=false, pending, lastError=null)`, `false`. Outbox kept. (Offline is normal, not an error.)
  6. Success: `fullResync` -> `repo.applyFullSnapshot(changes)` else `repo.applyRemote(changes)`; then `repo.clearOutbox(sent)` (rejected rows are part of `sent`, so they leave the outbox; their ids are printed once); `settings.cursor = response.cursor`; `state = (online=true, pending, null)`; `true`.
  `pending` is always the outbox count after the attempt. Phase 4 wires `TaskRepository.onLocalChange` to a debounced `syncOnce()`, which keeps `pending` current while offline.
- Produces (jvmTest): `class FakeSyncServer : SyncApi` with `var failWith: Exception?`, `var duringSync: suspend () -> Unit`, `var reject: Set<String>`, `val requests: MutableList<SyncRequest>`, `var lastResponse: SyncResponse?`, `rev: Long` (read-only outside), `fun push(req: SyncRequest): SyncResponse` (server logic without hooks), `fun purgeTombstones()`.

- [ ] **Step 1: Write the fake server**

`shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/FakeSyncServer.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.model.Note
import com.sagunkayastha.adhdhelper.model.Task
import com.sagunkayastha.adhdhelper.model.TaskList
import com.sagunkayastha.adhdhelper.model.Versioned
import com.sagunkayastha.adhdhelper.sync.Changes
import com.sagunkayastha.adhdhelper.sync.Merge
import com.sagunkayastha.adhdhelper.sync.SyncRequest
import com.sagunkayastha.adhdhelper.sync.SyncResponse

/** In-memory server with the protocol's rules: LWW merge, rev log, tombstone purge -> fullResync. */
class FakeSyncServer : SyncApi {
    var failWith: Exception? = null
    var duringSync: suspend () -> Unit = {}
    var reject: Set<String> = emptySet()
    val requests = mutableListOf<SyncRequest>()
    var lastResponse: SyncResponse? = null
    var rev = 0L
        private set
    private var purgedThrough = 0L
    private val lists = mutableMapOf<String, Pair<Long, TaskList>>()
    private val tasks = mutableMapOf<String, Pair<Long, Task>>()
    private val notes = mutableMapOf<String, Pair<Long, Note>>()
    private val messages = mutableMapOf<String, Pair<Long, ChatMessage>>()

    override suspend fun sync(req: SyncRequest): SyncResponse {
        failWith?.let { throw it }
        requests += req
        duringSync()
        return push(req).also { lastResponse = it }
    }

    fun push(req: SyncRequest): SyncResponse {
        val rejected = mutableListOf<String>()
        fun <T : Versioned> MutableMap<String, Pair<Long, T>>.accept(row: T) {
            if (row.id in reject) { rejected += row.id; return }
            if (Merge.wins(row, this[row.id]?.second)) { rev++; this[row.id] = rev to row }
        }
        req.changes.lists.forEach { lists.accept(it) }
        req.changes.tasks.forEach { tasks.accept(it) }
        req.changes.notes.forEach { notes.accept(it) }
        req.changes.messages.forEach { messages.accept(it) }
        if (req.cursor < purgedThrough) {
            val all = Changes(lists.rows { true }, tasks.rows { true }, notes.rows { true }, messages.rows { true })
            return SyncResponse(cursor = rev, changes = all, rejected = rejected, fullResync = true)
        }
        val since = Changes(
            lists.rows { it > req.cursor }, tasks.rows { it > req.cursor },
            notes.rows { it > req.cursor }, messages.rows { it > req.cursor },
        )
        return SyncResponse(cursor = rev, changes = since, rejected = rejected)
    }

    fun purgeTombstones() {
        lists.values.removeAll { it.second.deleted }
        tasks.values.removeAll { it.second.deleted }
        notes.values.removeAll { it.second.deleted }
        purgedThrough = rev
    }

    private fun <T> Map<String, Pair<Long, T>>.rows(keep: (Long) -> Boolean): List<T> =
        values.filter { keep(it.first) }.map { it.second }
}
```

- [ ] **Step 2: Write the failing test**

`shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/SyncClientTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.sync.Changes
import com.sagunkayastha.adhdhelper.sync.SyncRequest
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest

class SyncClientTest {
    private fun pairedSettings() =
        FileAppSettings(Files.createTempDirectory("s").resolve("settings.properties")).apply {
            serverUrl = "http://localhost"
            token = "tok"
        }

    @Test
    fun pushesOutboxStoresCursorAndClearsPending() = runTest {
        val d = TestDevice()
        val server = FakeSyncServer()
        val settings = pairedSettings()
        val client = SyncClient(server, d.repo, settings)
        val list = d.repo.addList("Inbox")
        assertTrue(client.syncOnce())
        assertEquals(listOf(list), server.requests.single().changes.lists)
        assertEquals(1L, settings.cursor)
        assertEquals(SyncState(online = true, pending = 0, lastError = null), client.state.value)
        assertTrue(client.syncOnce())
        assertEquals(1L, server.requests.last().cursor)
        assertTrue(server.requests.last().changes.isEmpty())
    }

    @Test
    fun remoteChangesAreApplied() = runTest {
        val other = TestDevice("pc", start = 2_000_000L)
        val list = other.repo.addList("from pc")
        val server = FakeSyncServer()
        server.push(SyncRequest(0, other.repo.drainOutbox()))
        val d = TestDevice("phone")
        assertTrue(SyncClient(server, d.repo, pairedSettings()).syncOnce())
        assertEquals(listOf(list), d.repo.lists().first())
    }

    @Test
    fun notPairedDoesNothing() = runTest {
        val d = TestDevice()
        val server = FakeSyncServer()
        val settings = pairedSettings().apply { serverUrl = null }
        val client = SyncClient(server, d.repo, settings)
        d.repo.addList("x")
        assertFalse(client.syncOnce())
        assertTrue(server.requests.isEmpty())
        assertEquals(SyncState(online = false, pending = 1, lastError = "not paired"), client.state.value)
    }

    @Test
    fun networkFailureGoesOfflineAndKeepsOutbox() = runTest {
        val d = TestDevice()
        val server = FakeSyncServer().apply { failWith = java.net.ConnectException("refused") }
        val client = SyncClient(server, d.repo, pairedSettings())
        d.repo.addList("offline edit")
        assertFalse(client.syncOnce())
        assertEquals(SyncState(online = false, pending = 1, lastError = null), client.state.value)
        server.failWith = null
        assertTrue(client.syncOnce())
        assertEquals("offline edit", server.requests.single().changes.lists.single().title)
        assertEquals(0, client.state.value.pending)
    }

    @Test
    fun unauthorizedClearsTokenAndKeepsOutbox() = runTest {
        val d = TestDevice()
        val server = FakeSyncServer().apply { failWith = UnauthorizedException() }
        val settings = pairedSettings()
        val client = SyncClient(server, d.repo, settings)
        d.repo.addList("keep me")
        assertFalse(client.syncOnce())
        assertNull(settings.token)
        assertEquals(SyncState(online = true, pending = 1, lastError = "unauthorized"), client.state.value)
        assertEquals("keep me", d.repo.lists().first().single().title)
    }

    @Test
    fun serverErrorKeepsOutboxAndReportsStatus() = runTest {
        val d = TestDevice()
        val server = FakeSyncServer().apply { failWith = ServerException(503) }
        val client = SyncClient(server, d.repo, pairedSettings())
        d.repo.addList("x")
        assertFalse(client.syncOnce())
        assertEquals(SyncState(online = true, pending = 1, lastError = "server error 503"), client.state.value)
    }

    @Test
    fun editMadeDuringSyncIsSentNextTime() = runTest {
        val d = TestDevice()
        val server = FakeSyncServer()
        val client = SyncClient(server, d.repo, pairedSettings())
        val list = d.repo.addList("A")
        server.duringSync = {
            server.duringSync = {}
            d.clock += 10
            d.repo.renameList(list.id, "B")
        }
        assertTrue(client.syncOnce())
        assertEquals(1, client.state.value.pending)
        assertEquals("B", d.repo.lists().first().single().title)
        assertTrue(client.syncOnce())
        assertEquals("B", server.requests.last().changes.lists.single().title)
        assertEquals(0, client.state.value.pending)
    }

    @Test
    fun rejectedRowsLeaveOutbox() = runTest {
        val d = TestDevice()
        val list = d.repo.addList("bad row")
        val server = FakeSyncServer().apply { reject = setOf(list.id) }
        val client = SyncClient(server, d.repo, pairedSettings())
        assertTrue(client.syncOnce())
        assertEquals(listOf(list.id), server.lastResponse!!.rejected)
        assertEquals(0, client.state.value.pending)
    }

    @Test
    fun cursorOlderThanPurgeDoesFullResyncAndKeepsOfflineEdits() = runTest {
        val server = FakeSyncServer()
        val phone = TestDevice("phone")
        val settings = pairedSettings()
        val client = SyncClient(server, phone.repo, settings)
        val list = phone.repo.addList("Inbox")
        val old = phone.repo.addTask(list.id, "old task")
        assertTrue(client.syncOnce())

        // While the phone is away, the PC deletes "old task", adds one, and the server purges tombstones.
        val pc = TestDevice("pc", start = 2_000_000L)
        pc.repo.applyRemote(server.push(SyncRequest(0, Changes())).changes)
        pc.repo.deleteTask(old.id)
        pc.repo.addTask(list.id, "from pc")
        server.push(SyncRequest(server.rev, pc.repo.drainOutbox()))
        server.purgeTombstones()

        // Phone was offline for three days and wrote a task.
        phone.clock += 3L * 24 * 3600 * 1000
        phone.repo.addTask(list.id, "written offline")

        assertTrue(client.syncOnce())
        assertTrue(server.lastResponse!!.fullResync)
        assertEquals(setOf("from pc", "written offline"), phone.repo.tasks(list.id).first().map { it.title }.toSet())
        assertEquals(server.rev, settings.cursor)
        assertEquals(SyncState(online = true, pending = 0, lastError = null), client.state.value)

        // The next sync is incremental again.
        assertTrue(client.syncOnce())
        assertFalse(server.lastResponse!!.fullResync)
    }
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.SyncClientTest'`
Expected: FAIL to compile with `Unresolved reference: SyncClient` / `SyncState`.

- [ ] **Step 4: Implement**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/SyncClient.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.sync.SyncRequest
import com.sagunkayastha.adhdhelper.sync.SyncResponse
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class SyncState(val online: Boolean, val pending: Int, val lastError: String?)

class SyncClient(
    private val api: SyncApi,
    private val repo: TaskRepository,
    private val settings: AppSettings,
) {
    private val _state = MutableStateFlow(SyncState(online = false, pending = 0, lastError = null))
    val state: StateFlow<SyncState> = _state.asStateFlow()
    private val mutex = Mutex()

    /** One push/pull round. True only when the server replied and the reply was applied. */
    suspend fun syncOnce(): Boolean = mutex.withLock { runOnce() }

    private suspend fun runOnce(): Boolean {
        if (settings.serverUrl == null || settings.token == null) {
            return finish(online = false, error = "not paired")
        }
        val sent = repo.drainOutbox()
        val response: SyncResponse = try {
            api.sync(SyncRequest(settings.cursor, sent))
        } catch (e: CancellationException) {
            throw e
        } catch (e: UnauthorizedException) {
            settings.token = null
            return finish(online = true, error = "unauthorized")
        } catch (e: ServerException) {
            return finish(online = true, error = "server error ${e.status}")
        } catch (e: Exception) {
            return finish(online = false, error = null)
        }
        if (response.fullResync) repo.applyFullSnapshot(response.changes) else repo.applyRemote(response.changes)
        repo.clearOutbox(sent)
        if (response.rejected.isNotEmpty()) {
            println("sync: server rejected ${response.rejected.size} row(s): ${response.rejected}")
        }
        settings.cursor = response.cursor
        return finish(online = true, error = null, ok = true)
    }

    private suspend fun finish(online: Boolean, error: String?, ok: Boolean = false): Boolean {
        _state.value = SyncState(online = online, pending = repo.pendingCount(), lastError = error)
        return ok
    }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.SyncClientTest'`
Expected: PASS (9 tests).

- [ ] **Step 6: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/SyncClient.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/FakeSyncServer.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/SyncClientTest.kt
git commit -m "feat(client): SyncClient with offline/401/full-resync handling

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr"
```

---

### Task 9: EventsSocket

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/EventsSocket.kt`
- Test: `shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/EventsSocketTest.kt`

**Interfaces:**
- Consumes: Phase 1 `EventPoke(rev: Long)`, `Api.PREFIX`; Task 7 `ClientJson`; Task 6 `AppSettings`.
- Produces (contract): `class EventsSocket(http: HttpClient, settings: AppSettings, onPoke: suspend () -> Unit) { fun start(scope: CoroutineScope); fun stop() }`.
- Produces (internal, tested): `fun eventsUrl(serverUrl: String): String` (`https` -> `wss`, `http` -> `ws`, + `/api/v1/events`), `fun nextBackoff(currentMs: Long): Long` (doubles, capped at 60 000), `fun parsePoke(text: String): EventPoke?`; constants `EventsSocket.MIN_BACKOFF_MS = 1_000`, `EventsSocket.MAX_BACKOFF_MS = 60_000`.
- Semantics: `start` is idempotent. The loop reads `serverUrl`/`token` fresh on each attempt (so it picks up a new pairing); with no pairing it just waits. On connect it resets the backoff to 1 s and calls `onPoke()` once (catch up on anything missed while disconnected), then calls `onPoke()` for every text frame that parses as `EventPoke`. Any failure or close waits the current backoff (1 s, 2 s, 4 s ... 60 s) and reconnects. `stop()` cancels the loop. The `HttpClient` must have the WebSockets plugin (`createHttpClient()` does). The live-server behaviour is tested in Task 10 (`pokeOverWebSocketTriggersSync`).

- [ ] **Step 1: Write the failing test**

`shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/EventsSocketTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.sync.EventPoke
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class EventsSocketTest {
    @Test
    fun backoffDoublesFromOneSecondUpToSixty() {
        val seq = generateSequence(EventsSocket.MIN_BACKOFF_MS) { nextBackoff(it) }.take(9).toList()
        assertEquals(listOf(1_000L, 2_000L, 4_000L, 8_000L, 16_000L, 32_000L, 60_000L, 60_000L, 60_000L), seq)
    }

    @Test
    fun eventsUrlSwitchesSchemeAndAppendsPath() {
        assertEquals("wss://tasks.sagunkayastha.com/api/v1/events", eventsUrl("https://tasks.sagunkayastha.com/"))
        assertEquals("ws://192.168.0.162:8020/api/v1/events", eventsUrl("http://192.168.0.162:8020"))
    }

    @Test
    fun parsePokeAcceptsRevAndIgnoresJunk() {
        assertEquals(EventPoke(5), parsePoke("""{"rev":5}"""))
        assertNull(parsePoke("not json"))
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.EventsSocketTest'`
Expected: FAIL to compile with `Unresolved reference: EventsSocket` / `nextBackoff`.

- [ ] **Step 3: Implement**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/EventsSocket.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.client

import com.sagunkayastha.adhdhelper.core.Api
import com.sagunkayastha.adhdhelper.sync.EventPoke
import io.ktor.client.HttpClient
import io.ktor.client.plugins.websocket.webSocket
import io.ktor.client.request.header
import io.ktor.http.HttpHeaders
import io.ktor.websocket.Frame
import io.ktor.websocket.readText
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/** Holds `WS /api/v1/events` open while the app runs; every poke (and every reconnect) calls [onPoke]. */
class EventsSocket(
    private val http: HttpClient,
    private val settings: AppSettings,
    private val onPoke: suspend () -> Unit,
) {
    private var job: Job? = null

    fun start(scope: CoroutineScope) {
        if (job?.isActive == true) return
        job = scope.launch { loop() }
    }

    fun stop() {
        job?.cancel()
        job = null
    }

    private suspend fun loop() {
        var backoff = MIN_BACKOFF_MS
        while (currentCoroutineContext().isActive) {
            val url = settings.serverUrl
            val token = settings.token
            if (url != null && token != null) {
                try {
                    http.webSocket(
                        urlString = eventsUrl(url),
                        request = { header(HttpHeaders.Authorization, "Bearer $token") },
                    ) {
                        backoff = MIN_BACKOFF_MS
                        onPoke()
                        for (frame in incoming) {
                            if (frame is Frame.Text && parsePoke(frame.readText()) != null) onPoke()
                        }
                    }
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    // offline, refused or 401: retry after backoff; SyncClient reports the real state
                }
            }
            delay(backoff)
            backoff = nextBackoff(backoff)
        }
    }

    companion object {
        const val MIN_BACKOFF_MS = 1_000L
        const val MAX_BACKOFF_MS = 60_000L
    }
}

internal fun nextBackoff(currentMs: Long): Long = (currentMs * 2).coerceAtMost(EventsSocket.MAX_BACKOFF_MS)

internal fun eventsUrl(serverUrl: String): String {
    val base = serverUrl.trimEnd('/')
    val ws = when {
        base.startsWith("https://") -> "wss://" + base.removePrefix("https://")
        base.startsWith("http://") -> "ws://" + base.removePrefix("http://")
        else -> base
    }
    return ws + Api.PREFIX + "/events"
}

internal fun parsePoke(text: String): EventPoke? =
    runCatching { ClientJson.decodeFromString(EventPoke.serializer(), text) }.getOrNull()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `gradle :shared:jvmTest --tests 'com.sagunkayastha.adhdhelper.client.EventsSocketTest'`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/client/EventsSocket.kt shared/src/jvmTest/kotlin/com/sagunkayastha/adhdhelper/client/EventsSocketTest.kt
git commit -m "feat(client): EventsSocket with 1s..60s reconnect backoff

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr"
```

---

### Task 10: Two-device convergence test against the real server

**Files:**
- Modify: `server/build.gradle.kts`
- Test: `server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/ConvergenceTest.kt`

**Interfaces:**
- Consumes (Phase 2, contract): `ServerDb(jdbcUrl)`, `EventBus()`, `SyncService(db, hlc, events)`, `DeviceAuth(db)` with `newPairCode()` and `pair(PairRequest): PairResponse?`, `ServerConfig(dataDir)`, `Application.module(deps: ServerDeps)`. Phase 2 Task 5 defines `data class ServerDeps(val config: ServerConfig, val db: ServerDb, val sync: SyncService, val events: EventBus, val auth: DeviceAuth, val claude: ClaudeProbe = ClaudeProbe { "missing" })` (Phase 6 appends `assistant: Assistant? = null`); the named-argument call below matches it.
- Consumes (this phase): `createClientDatabase`, `TaskRepository`, `FileAppSettings`, `KtorSyncApi`, `SyncClient`, `EventsSocket`.
- Produces: nothing new; this test is the Phase 3 exit gate.
- Device clocks: both devices start at wall clock `1_000_000` ms and the test moves them by hand, so which edit has the later HLC is decided by the test, not by timing.

- [ ] **Step 1: Add the test dependencies to `server/build.gradle.kts`**

Add inside the existing `dependencies { }` block (skip lines already present):

```kotlin
    testImplementation(kotlin("test"))
    testImplementation(libs.ktor.server.test.host)
    testImplementation(libs.ktor.client.content.negotiation)
    testImplementation(libs.ktor.client.websockets)
    testImplementation(libs.sqldelight.sqlite.driver)
```

(`libs.ktor.server.test.host` is Phase 1's catalog alias for `io.ktor:ktor-server-test-host`. The server already depends on `project(":shared")`.)

- [ ] **Step 2: Write the test**

`server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/ConvergenceTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.server

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import com.sagunkayastha.adhdhelper.client.EventsSocket
import com.sagunkayastha.adhdhelper.client.FileAppSettings
import com.sagunkayastha.adhdhelper.client.KtorSyncApi
import com.sagunkayastha.adhdhelper.client.SyncClient
import com.sagunkayastha.adhdhelper.client.TaskRepository
import com.sagunkayastha.adhdhelper.client.createClientDatabase
import com.sagunkayastha.adhdhelper.client.db.ClientDatabase
import com.sagunkayastha.adhdhelper.core.PairRequest
import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.model.Freq
import com.sagunkayastha.adhdhelper.model.Note
import com.sagunkayastha.adhdhelper.model.RepeatRule
import com.sagunkayastha.adhdhelper.model.Task
import com.sagunkayastha.adhdhelper.model.TaskList
import com.sagunkayastha.adhdhelper.sync.Hlc
import com.sagunkayastha.adhdhelper.sync.Ids
import io.ktor.client.HttpClient
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.serialization.kotlinx.json.json
import io.ktor.server.testing.testApplication
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime
import kotlinx.serialization.json.Json

class ConvergenceTest {

    private class Device(val name: String, http: HttpClient, token: String, dir: Path) {
        var clock = 1_000_000L
        val settings = FileAppSettings(dir.resolve("$name.properties")).apply {
            serverUrl = "http://localhost"
            this.token = token
        }
        val repo = TaskRepository(
            createClientDatabase(JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY).also { ClientDatabase.Schema.create(it) }),
            Hlc(name) { clock },
        ) {}
        val sync = SyncClient(KtorSyncApi(http, settings), repo, settings)

        suspend fun syncOk() = assertTrue(sync.syncOnce(), "$name sync failed: ${sync.state.value}")

        suspend fun snapshot(): Snapshot {
            val lists = repo.lists().first()
            return Snapshot(
                lists = lists.sortedBy { it.id },
                tasks = lists.flatMap { repo.tasks(it.id).first() }.sortedBy { it.id },
                notes = repo.notes().first().sortedBy { it.id },
                messages = repo.messages().first().sortedBy { it.id },
            )
        }
    }

    private data class Snapshot(
        val lists: List<TaskList>, val tasks: List<Task>, val notes: List<Note>, val messages: List<ChatMessage>,
    )

    private class Harness(val http: HttpClient, val phone: Device, val pc: Device)

    private fun withServer(block: suspend Harness.() -> Unit) = testApplication {
        val dir = Files.createTempDirectory("convergence")
        val db = ServerDb("jdbc:sqlite:${dir.resolve("tasks.db")}")
        val events = EventBus()
        val auth = DeviceAuth(db)
        val sync = SyncService(db, Hlc("server") { System.currentTimeMillis() }, events)
        application {
            module(ServerDeps(config = ServerConfig(dataDir = dir.toString()), db = db, sync = sync, events = events, auth = auth))
        }
        val http = createClient {
            install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
            install(WebSockets)
        }
        fun token(name: String) = assertNotNull(auth.pair(PairRequest(auth.newPairCode(), name))).token
        Harness(http, Device("phone", http, token("phone"), dir), Device("pc", http, token("pc"), dir)).block()
    }

    private suspend fun Harness.syncBothTwice() {
        repeat(2) {
            phone.syncOk()
            pc.syncOk()
        }
    }

    @Test
    fun offlineEditsOnBothDevicesConverge() = withServer {
        val list = phone.repo.addList("Inbox")
        val task = phone.repo.addTask(list.id, "buy milk")
        phone.syncOk(); pc.syncOk()

        // Both offline. Phone edits first; the PC edit carries the later HLC.
        phone.clock += 1_000
        phone.repo.updateTask(task.copy(title = "buy oat milk"))
        phone.repo.addTask(list.id, "phone only")
        phone.repo.addNote("phone note")
        pc.clock += 5_000
        val pcCopy = pc.repo.tasks(list.id).first().single { it.id == task.id }
        pc.repo.updateTask(pcCopy.copy(title = "buy almond milk", starred = true))
        pc.repo.addTask(list.id, "pc only")
        pc.repo.queueChat("pc chat")

        syncBothTwice()

        val a = phone.snapshot()
        assertEquals(a, pc.snapshot())
        assertEquals(listOf("buy almond milk", "pc only", "phone only"), a.tasks.map { it.title }.sorted())
        assertTrue(a.tasks.single { it.id == task.id }.starred)
        assertEquals(setOf("phone note", "pc chat"), a.notes.map { it.text }.toSet())
        assertEquals(1, a.messages.size)
        assertEquals(0, phone.sync.state.value.pending)
        assertEquals(0, pc.sync.state.value.pending)
    }

    @Test
    fun laterDeleteBeatsEarlierEditAndStaysDeleted() = withServer {
        val list = phone.repo.addList("Home")
        val parent = phone.repo.addTask(list.id, "clean")
        val child = phone.repo.addTask(list.id, "kitchen", parentId = parent.id)
        phone.syncOk(); pc.syncOk()

        pc.clock += 1_000
        val pcChild = pc.repo.tasks(list.id).first().single { it.id == child.id }
        pc.repo.updateTask(pcChild.copy(title = "kitchen + fridge"))
        phone.clock += 2_000
        phone.repo.deleteTask(parent.id)   // tombstones the child with a later HLC

        // The older edit reaches the server first, then the delete.
        pc.syncOk()
        phone.syncOk()
        syncBothTwice()

        assertEquals(phone.snapshot(), pc.snapshot())
        assertTrue(phone.repo.tasks(list.id).first().isEmpty())
        assertTrue(pc.repo.tasks(list.id).first().isEmpty())
    }

    @Test
    fun repeatCompletedOnBothDevicesYieldsOneNextOccurrence() = withServer {
        val list = phone.repo.addList("Home")
        val t = phone.repo.addTask(list.id, "water plants", dueDate = LocalDate(2026, 10, 9), dueTime = LocalTime(18, 0))
        phone.repo.updateTask(t.copy(repeat = RepeatRule(Freq.DAILY)))
        phone.syncOk(); pc.syncOk()

        phone.clock += 1_000
        phone.repo.complete(t.id)
        phone.repo.complete(t.id)   // double tap
        pc.clock += 2_000
        pc.repo.complete(t.id)

        syncBothTwice()

        val a = phone.snapshot()
        assertEquals(a, pc.snapshot())
        val rows = a.tasks.filter { it.title == "water plants" }
        assertEquals(2, rows.size)
        assertNotNull(rows.single { it.id == t.id }.completedAt)
        val next = rows.single { it.id != t.id }
        assertEquals(Ids.derived("${t.id}:2026-10-10"), next.id)
        assertEquals(LocalDate(2026, 10, 10), next.dueDate)
        assertNull(next.completedAt)
    }

    @Test
    fun longOfflineBacklogSyncsInOneGo() = withServer {
        val list = phone.repo.addList("Inbox")
        phone.syncOk(); pc.syncOk()

        // Phone offline for three days with a stack of edits; PC keeps working.
        repeat(30) { i ->
            phone.clock += 3L * 24 * 3600 * 1000 / 30
            phone.repo.addTask(list.id, "phone $i")
        }
        pc.clock += 1_000
        repeat(5) { i -> pc.repo.addTask(list.id, "pc $i") }
        pc.syncOk()

        phone.syncOk()
        pc.syncOk()

        val a = phone.snapshot()
        assertEquals(a, pc.snapshot())
        assertEquals(35, a.tasks.size)
        assertEquals(0, phone.sync.state.value.pending)
    }

    @Test
    fun pokeOverWebSocketTriggersSync() = withServer {
        val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
        val connected = CompletableDeferred<Unit>()
        val socket = EventsSocket(http, pc.settings) {
            connected.complete(Unit)
            pc.sync.syncOnce()
        }
        socket.start(scope)
        try {
            withContext(Dispatchers.Default) { withTimeout(10_000) { connected.await() } }
            val list = phone.repo.addList("Work")
            phone.syncOk()
            withContext(Dispatchers.Default) {
                withTimeout(10_000) {
                    while (pc.repo.lists().first().none { it.id == list.id }) delay(50)
                }
            }
        } finally {
            socket.stop()
            scope.cancel()
        }
    }
}
```

- [ ] **Step 3: Run the test**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :server:test --tests 'com.sagunkayastha.adhdhelper.server.ConvergenceTest' --no-daemon`
Expected: PASS (5 tests). The code under test already exists (Tasks 1-9 and Phase 2), so this is an integration gate, not a red/green step. If a test fails, do not change the assertions: it is a real bug. Debug with superpowers:systematic-debugging, fix the code in the owning task's file, rerun that task's unit tests, then rerun this.



- [ ] **Step 4: Run the whole phase suite**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest :shared:compileDebugKotlinAndroid :server:test --no-daemon`
Expected: BUILD SUCCESSFUL, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add server/build.gradle.kts server/src/test/kotlin/com/sagunkayastha/adhdhelper/server/ConvergenceTest.kt
git commit -m "test: two-device convergence against the real server (offline edits, delete, repeat, backlog, poke)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr"
```

---

## Notes for later phases

- Device id: `AppSettings.deviceId` is generated locally on first read (`Ids.newId()`) and is the `Hlc` nodeId. `PairResponse.deviceId` is the server's own label for the pairing (used by `tasks devices` / `tasks revoke`); clients do not store it and never overwrite `settings.deviceId` with it.
- Phase 4 wiring: `Hlc(settings.deviceId) { Clock.System.now().toEpochMilliseconds() }`; `TaskRepository(createClientDatabase(DriverFactory(context).createDriver()), hlc, onLocalChange = { debounced 2 s syncOnce })`; `SyncClient(KtorSyncApi(http, settings), repo, settings)`; `EventsSocket(http, settings) { sync.syncOnce() }` started in the app's foreground scope. `lastError == "unauthorized"` means go to the setup screen (local data kept).
- Full resync is detected by the server (Phase 2) and only applied here; the end-to-end purge path is covered by Phase 2's purge test plus Task 8's fake-server test.
