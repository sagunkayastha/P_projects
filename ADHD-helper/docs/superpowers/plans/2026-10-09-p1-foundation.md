# ADHD Helper Phase 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Docker build image, the Gradle skeleton, and a tested `shared` Kotlin Multiplatform module holding the data models, sync wire types, HLC clock, ids, merge rule, sort keys, recurrence math and reminder math that every later phase builds on.

**Architecture:** One Gradle build at the repo root (`ADHD-helper/`). This phase creates only the `shared` module (targets: `androidTarget` + `jvm`); `androidApp/`, `desktopApp/` and `server/` are added by later phases together with their `include(...)` lines. All logic is pure Kotlin in `commonMain` and tested in `commonTest`, run on the JVM target. The only platform code is a one-line SHA-1 `actual` per target.

**Tech Stack:** Kotlin 2.2.0, kotlinx-serialization 1.9.0, kotlinx-datetime 0.7.1 (with `kotlin.time.Instant`), AGP 8.11.1, Gradle 8.14.3, JDK 21 (eclipse-temurin), Android compileSdk 35 / minSdk 29. Version catalog also pins (unused until later phases) Compose Multiplatform 1.8.2, Ktor 3.2.0, SQLDelight 2.1.0, kotlinx-coroutines 1.10.2.

**Spec:** `docs/superpowers/specs/2026-10-09-adhd-helper-design.md`
**Index (binding contract):** `docs/superpowers/plans/2026-10-09-00-index.md`

## Global Constraints

- **Docker-only:** every build, test, and tool runs inside the build container (`docker/build.Dockerfile`, image `adhd-build`). Nothing is installed on the host (no JDK, Gradle, Android SDK, Node). Standard test command, run from the `ADHD-helper/` directory:
  `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle <task> --no-daemon`
- **No files in `~`** on any host.
- Package root: `com.sagunkayastha.adhdhelper`. App name: `ADHD Helper`.
- Time zone for wall-clock due times: `America/Denver`.
- Names and types in the index's Shared Interface Contract are binding: `Versioned`, `Freq`, `RepeatRule`, `TaskList`, `Task`, `Note`, `Role`, `ChatStatus`, `ChatMessage` (package `...model`); `Changes`, `SyncRequest`, `SyncResponse`, `EventPoke`, `Merge`, `Hlc`, `Ids` (package `...sync`); `SortKey`, `Recurrence`, `ReminderMath`, `Api`, `PairRequest`, `PairResponse`, `Health` (package `...core`).
- `Instant` is always `kotlin.time.Instant` (never the deprecated `kotlinx.datetime.Instant`). The `shared` module opts in to `kotlin.time.ExperimentalTime` for all source sets.
- HLC string format: `"%015d-%05d-%s"` (millis, counter, nodeId), compared as plain strings.
- If a pinned dependency version fails to resolve, use the nearest newer patch release of the same minor and note it in the commit message; never jump minors silently.
- Commits end with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
  ```
- The repo's git root is the parent folder `P_projects/`; run all commands (docker and git) from `P_projects/ADHD-helper/`.

## Review Focus

1. **Daily 18:00 reminder across DST** (index item 2): a daily task due 18:00 in `America/Denver` fires at 18:00 local on every day around 2027-03-14 (spring forward) and 2026-11-01 (fall back). Pinned in Task 7 (`dailySixPmStaysSixPmAcrossSpringForward`, `dailySixPmStaysSixPmAcrossFallBack`).
2. **Due time that does not exist or exists twice locally** (02:30 on spring-forward day, 01:30 on fall-back day): must still produce a fire time, never throw; 02:30 fires at 03:30 MDT, 01:30 fires at the first (MDT) occurrence. Pinned in Task 7 (`nonexistentLocalTimeShiftsForward`, `ambiguousLocalTimeUsesFirstOccurrence`).
3. **Two devices append to the same list offline and get the same sortKey**: a later move between those twins calls `SortKey.between(k, k)`; it must not throw and must return a key greater than `k`. Pinned in Task 5 (`equalNeighboursDoNotThrow`).
4. **Device clock jumps backwards, or another device's clock is far ahead**: the local HLC must stay strictly increasing and the next local stamp must beat any observed remote stamp, so a fresh local edit is never lost to an older one. Pinned in Task 3 (`wallClockGoingBackwardsStillIncreases`, `observeAdvancesPastRemote`, `counterOverflowRollsIntoNextMillisecond`). Device ids are UUIDs containing `-`; parsing must cope (`nodeIdWithDashesParses`).
5. **Monthly task on the 31st / yearly task on Feb 29, and `every = 0` from a bad assistant call**: next date clamps to the month end (never skips a month, never throws) and, with `anchorDay` set, returns to the anchor day when the month allows it (Jan 31 -> Feb 28 -> Mar 31; Feb 29 -> Feb 28 -> ... -> Feb 29); `every < 1` fails loudly instead of looping on the same date. Pinned in Task 6 (`monthlyOn31stClampsToMonthEnd`, `monthlyAnchorReturnsToThe31st`, `yearlyFeb29ClampsInNonLeapYear`, `yearlyFeb29AnchorReturnsInLeapYear`, `everyBelowOneIsRejected`).

---

## File Structure

```
ADHD-helper/
├── .gitignore
├── docker/build.Dockerfile                 # image adhd-build: JDK 21 + Android SDK 35 + Gradle 8.14.3
├── settings.gradle.kts                     # repos, rootProject name, include(":shared")
├── build.gradle.kts                        # all plugins declared `apply false`
├── gradle.properties
├── gradle/libs.versions.toml               # every pinned version + aliases for later phases
└── shared/
    ├── build.gradle.kts                    # KMP: androidTarget + jvm
    └── src/
        ├── commonMain/kotlin/com/sagunkayastha/adhdhelper/
        │   ├── model/Versioned.kt          # interface Versioned
        │   ├── model/RepeatRule.kt         # Freq, RepeatRule, DayCodeSerializer (MO..SU)
        │   ├── model/Entities.kt           # TaskList, Task, Note, Role, ChatStatus, ChatMessage
        │   ├── sync/Sha1.kt                # internal expect fun sha1
        │   ├── sync/Ids.kt                 # UUIDv7 + derived UUID
        │   ├── sync/Hlc.kt                 # hybrid logical clock
        │   ├── sync/Merge.kt               # LWW rule
        │   ├── sync/Wire.kt                # Changes, SyncRequest, SyncResponse, EventPoke
        │   ├── core/Api.kt                 # Api, PairRequest, PairResponse, Health
        │   ├── core/SortKey.kt             # fractional index
        │   ├── core/Recurrence.kt          # next due date
        │   └── core/ReminderMath.kt        # next fire instant
        ├── jvmMain/kotlin/com/sagunkayastha/adhdhelper/sync/Sha1.jvm.kt
        ├── androidMain/kotlin/com/sagunkayastha/adhdhelper/sync/Sha1.android.kt
        └── commonTest/kotlin/com/sagunkayastha/adhdhelper/
            ├── model/ModelSerializationTest.kt
            ├── sync/IdsTest.kt
            ├── sync/HlcTest.kt
            ├── sync/MergeAndWireTest.kt
            ├── core/SortKeyTest.kt
            ├── core/RecurrenceTest.kt
            └── core/ReminderMathTest.kt
```

---

### Task 1: Build image, Gradle skeleton, and model classes

**Files:**
- Create: `docker/build.Dockerfile`
- Create: `.gitignore`
- Create: `settings.gradle.kts`
- Create: `build.gradle.kts`
- Create: `gradle.properties`
- Create: `gradle/libs.versions.toml`
- Create: `shared/build.gradle.kts`
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/model/Versioned.kt`
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/model/RepeatRule.kt`
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/model/Entities.kt`
- Test: `shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/model/ModelSerializationTest.kt`

**Interfaces:**
- Consumes: nothing.
- Produces (exact, from the index contract):
  - `interface Versioned { val id: String; val hlc: String }`
  - `enum class Freq { DAILY, WEEKLY, MONTHLY, YEARLY }` (wire names `"daily"`, `"weekly"`, `"monthly"`, `"yearly"`, matching the spec's JSON)
  - `data class RepeatRule(val freq: Freq, val every: Int = 1, val days: List<DayOfWeek> = emptyList(), val anchorDay: Int? = null)` (days on the wire as `"MO".."SU"`; `anchorDay` = day of month a MONTHLY/YEARLY rule was created on, set by Phase 3's repository, omitted from the JSON when null)
  - `data class TaskList(id, title, sortKey, hlc, deleted = false) : Versioned`
  - `data class Task(id, listId, parentId: String? = null, title, details = "", starred = false, dueDate: LocalDate? = null, dueTime: LocalTime? = null, repeat: RepeatRule? = null, completedAt: Instant? = null, sortKey, snoozeUntil: Instant? = null, hlc, deleted = false) : Versioned`
  - `data class Note(id, text, createdAt: Instant, taskId: String? = null, hlc, deleted = false) : Versioned`
  - `enum class Role { USER, ASSISTANT }`, `enum class ChatStatus { QUEUED, SENT, ANSWERED, FAILED }`
  - `data class ChatMessage(id, role: Role, text, createdAt: Instant, status: ChatStatus, hlc) : Versioned`
  - Gradle: version catalog aliases listed in Step 3 (later phases use these, they never edit `[versions]`).
  - Docker image tag `adhd-build`, Gradle cache volume `adhd-gradle` (mounted at `/gradle`, owned by the host user; builds run with `--user "$(id -u):$(id -g)"`).

- [ ] **Step 1: Write the build image**

`docker/build.Dockerfile`:

```dockerfile
# Build environment for ADHD Helper (Android, desktop, server). Nothing here is installed on the host.
FROM eclipse-temurin:21-jdk
ARG CMDLINE_TOOLS=11076708
ARG GRADLE_VERSION=8.14.3
ENV ANDROID_HOME=/opt/android-sdk
# Builds run as the host user (docker run --user), who has no home in the image: give it a writable one.
ENV HOME=/tmp
ENV PATH=$PATH:/opt/gradle/bin:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools
RUN apt-get update && apt-get install -y --no-install-recommends unzip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/tools.zip "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip" \
    && mkdir -p "$ANDROID_HOME/cmdline-tools" \
    && unzip -q /tmp/tools.zip -d "$ANDROID_HOME/cmdline-tools" \
    && mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest" \
    && rm /tmp/tools.zip
RUN yes | sdkmanager --licenses > /dev/null \
    && sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0" > /dev/null \
    && chmod -R a+rX "$ANDROID_HOME"
RUN curl -fsSL -o /tmp/gradle.zip "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" \
    && unzip -q /tmp/gradle.zip -d /opt && mv "/opt/gradle-${GRADLE_VERSION}" /opt/gradle && rm /tmp/gradle.zip \
    && chmod -R a+rX /opt/gradle
WORKDIR /src
```

- [ ] **Step 2: Build the image, create the Gradle cache volume (one time), and check both**

Every build runs as the host user (`--user "$(id -u):$(id -g)"`) so `build/`, `.gradle/` and `.kotlin/` in the checkout stay owned by the user, never root. The Gradle cache lives in the named volume `adhd-gradle` mounted at `/gradle` (`GRADLE_USER_HOME=/gradle`); a fresh volume is root-owned, so hand it to the host user once:

Run:
```bash
docker build -t adhd-build -f docker/build.Dockerfile docker
docker volume create adhd-gradle && docker run --rm -v adhd-gradle:/gradle alpine chown "$(id -u):$(id -g)" /gradle
docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle adhd-build sh -c 'java -version 2>&1 | head -1; gradle --version | grep "^Gradle"; ls "$ANDROID_HOME/platforms" "$ANDROID_HOME/build-tools"; touch /gradle/.w && echo gradle-home-writable'
```
Expected: a line containing `openjdk version "21`, the line `Gradle 8.14.3`, `android-35` and `35.0.0` listed, and `gradle-home-writable`.

- [ ] **Step 3: Write the Gradle skeleton**

`.gitignore`:

```gitignore
.gradle/
.kotlin/
build/
local.properties
.idea/
*.iml
dist/
*.keystore
.env
```

`settings.gradle.kts`:

```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "adhd-helper"

include(":shared")
```

`build.gradle.kts`:

```kotlin
plugins {
    alias(libs.plugins.kotlinMultiplatform) apply false
    alias(libs.plugins.kotlinJvm) apply false
    alias(libs.plugins.kotlinSerialization) apply false
    alias(libs.plugins.androidApplication) apply false
    alias(libs.plugins.androidLibrary) apply false
    alias(libs.plugins.composeMultiplatform) apply false
    alias(libs.plugins.composeCompiler) apply false
    alias(libs.plugins.sqldelight) apply false
    alias(libs.plugins.ktor) apply false
}
```

`gradle.properties`:

```properties
org.gradle.jvmargs=-Xmx4g -Dfile.encoding=UTF-8
org.gradle.caching=true
kotlin.code.style=official
android.useAndroidX=true
android.nonTransitiveRClass=true
```

`gradle/libs.versions.toml` (later phases may add `[libraries]` entries for artifacts the index does not pin, such as AndroidX or Logback, with their own version refs; they must not change any value below):

```toml
[versions]
kotlin = "2.2.0"
agp = "8.11.1"
compose-multiplatform = "1.8.2"
ktor = "3.2.0"
sqldelight = "2.1.0"
kotlinx-serialization = "1.9.0"
kotlinx-coroutines = "1.10.2"
kotlinx-datetime = "0.7.1"
android-compileSdk = "35"
android-targetSdk = "35"
android-minSdk = "29"

[libraries]
kotlin-test = { module = "org.jetbrains.kotlin:kotlin-test", version.ref = "kotlin" }
kotlinx-serialization-json = { module = "org.jetbrains.kotlinx:kotlinx-serialization-json", version.ref = "kotlinx-serialization" }
kotlinx-datetime = { module = "org.jetbrains.kotlinx:kotlinx-datetime", version.ref = "kotlinx-datetime" }
kotlinx-coroutines-core = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-core", version.ref = "kotlinx-coroutines" }
kotlinx-coroutines-android = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-android", version.ref = "kotlinx-coroutines" }
kotlinx-coroutines-swing = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-swing", version.ref = "kotlinx-coroutines" }
kotlinx-coroutines-test = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-test", version.ref = "kotlinx-coroutines" }
ktor-client-core = { module = "io.ktor:ktor-client-core", version.ref = "ktor" }
ktor-client-content-negotiation = { module = "io.ktor:ktor-client-content-negotiation", version.ref = "ktor" }
ktor-client-websockets = { module = "io.ktor:ktor-client-websockets", version.ref = "ktor" }
ktor-client-okhttp = { module = "io.ktor:ktor-client-okhttp", version.ref = "ktor" }
ktor-client-cio = { module = "io.ktor:ktor-client-cio", version.ref = "ktor" }
ktor-client-mock = { module = "io.ktor:ktor-client-mock", version.ref = "ktor" }
ktor-serialization-kotlinx-json = { module = "io.ktor:ktor-serialization-kotlinx-json", version.ref = "ktor" }
ktor-server-core = { module = "io.ktor:ktor-server-core", version.ref = "ktor" }
ktor-server-netty = { module = "io.ktor:ktor-server-netty", version.ref = "ktor" }
ktor-server-content-negotiation = { module = "io.ktor:ktor-server-content-negotiation", version.ref = "ktor" }
ktor-server-auth = { module = "io.ktor:ktor-server-auth", version.ref = "ktor" }
ktor-server-websockets = { module = "io.ktor:ktor-server-websockets", version.ref = "ktor" }
ktor-server-sse = { module = "io.ktor:ktor-server-sse", version.ref = "ktor" }
ktor-server-test-host = { module = "io.ktor:ktor-server-test-host", version.ref = "ktor" }
sqldelight-android-driver = { module = "app.cash.sqldelight:android-driver", version.ref = "sqldelight" }
sqldelight-sqlite-driver = { module = "app.cash.sqldelight:sqlite-driver", version.ref = "sqldelight" }
sqldelight-coroutines = { module = "app.cash.sqldelight:coroutines-extensions", version.ref = "sqldelight" }

[plugins]
kotlinMultiplatform = { id = "org.jetbrains.kotlin.multiplatform", version.ref = "kotlin" }
kotlinJvm = { id = "org.jetbrains.kotlin.jvm", version.ref = "kotlin" }
kotlinSerialization = { id = "org.jetbrains.kotlin.plugin.serialization", version.ref = "kotlin" }
composeCompiler = { id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }
composeMultiplatform = { id = "org.jetbrains.compose", version.ref = "compose-multiplatform" }
androidApplication = { id = "com.android.application", version.ref = "agp" }
androidLibrary = { id = "com.android.library", version.ref = "agp" }
sqldelight = { id = "app.cash.sqldelight", version.ref = "sqldelight" }
ktor = { id = "io.ktor.plugin", version.ref = "ktor" }
```

`shared/build.gradle.kts`:

```kotlin
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.kotlinMultiplatform)
    alias(libs.plugins.androidLibrary)
    alias(libs.plugins.kotlinSerialization)
}

kotlin {
    androidTarget {
        compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
    }
    jvm {
        compilerOptions { jvmTarget.set(JvmTarget.JVM_21) }
    }

    sourceSets {
        all {
            languageSettings.optIn("kotlin.time.ExperimentalTime")
        }
        commonMain.dependencies {
            api(libs.kotlinx.serialization.json)
            api(libs.kotlinx.datetime)
        }
        commonTest.dependencies {
            implementation(libs.kotlin.test)
        }
    }
}

android {
    namespace = "com.sagunkayastha.adhdhelper.shared"
    compileSdk = libs.versions.android.compileSdk.get().toInt()
    defaultConfig {
        minSdk = libs.versions.android.minSdk.get().toInt()
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
```

- [ ] **Step 4: Check the build configures**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:tasks --no-daemon`
Expected: `BUILD SUCCESSFUL`, and the task list includes `jvmTest`. (First run downloads plugins; it takes a few minutes. If a version fails to resolve, apply the Global Constraints patch rule.)

- [ ] **Step 5: Write the failing model test**

`shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/model/ModelSerializationTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.model

import kotlinx.datetime.DayOfWeek
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant

class ModelSerializationTest {
    private val json = Json

    private fun <T> roundTrip(value: T, serializer: KSerializer<T>): T =
        json.decodeFromString(serializer, json.encodeToString(serializer, value))

    private val fullTask = Task(
        id = "0190a000-0000-7000-8000-000000000001",
        listId = "list-1",
        parentId = "parent-1",
        title = "Call mom",
        details = "about Sunday",
        starred = true,
        dueDate = LocalDate(2026, 10, 9),
        dueTime = LocalTime(18, 0),
        repeat = RepeatRule(Freq.WEEKLY, every = 2, days = listOf(DayOfWeek.MONDAY, DayOfWeek.FRIDAY)),
        completedAt = Instant.parse("2026-10-09T20:15:30Z"),
        sortKey = "i",
        snoozeUntil = Instant.parse("2026-10-09T18:10:00Z"),
        hlc = "000000000001000-00000-A",
        deleted = false,
    )

    @Test
    fun taskWithAllFieldsRoundTrips() {
        assertEquals(fullTask, roundTrip(fullTask, Task.serializer()))
    }

    @Test
    fun taskWithNullDatesRoundTrips() {
        val bare = Task(id = "t2", listId = "list-1", title = "x", sortKey = "i", hlc = "h")
        val back = roundTrip(bare, Task.serializer())
        assertEquals(bare, back)
        assertNull(back.dueDate)
        assertNull(back.dueTime)
        assertNull(back.repeat)
        assertNull(back.completedAt)
        assertNull(back.snoozeUntil)
        assertNull(back.parentId)
    }

    @Test
    fun minimalTaskJsonFillsDefaults() {
        val t = json.decodeFromString(
            Task.serializer(),
            """{"id":"t3","listId":"list-1","title":"x","sortKey":"i","hlc":"h"}""",
        )
        assertEquals("", t.details)
        assertEquals(false, t.starred)
        assertEquals(false, t.deleted)
        assertNull(t.dueDate)
    }

    @Test
    fun dueDateIsIsoOnTheWire() {
        val s = json.encodeToString(Task.serializer(), fullTask)
        assertTrue(s.contains("\"dueDate\":\"2026-10-09\""), s)
    }

    @Test
    fun repeatRuleUsesSpecWireForm() {
        val rule = RepeatRule(Freq.WEEKLY, every = 2, days = listOf(DayOfWeek.MONDAY, DayOfWeek.FRIDAY))
        assertEquals(
            """{"freq":"weekly","every":2,"days":["MO","FR"]}""",
            json.encodeToString(RepeatRule.serializer(), rule),
        )
        assertEquals(RepeatRule(Freq.DAILY), json.decodeFromString(RepeatRule.serializer(), """{"freq":"daily"}"""))
    }

    @Test
    fun anchorDayIsOmittedWhenNullAndRoundTripsWhenSet() {
        val rule = RepeatRule(Freq.MONTHLY, anchorDay = 31)
        val s = json.encodeToString(RepeatRule.serializer(), rule)
        assertEquals("""{"freq":"monthly","anchorDay":31}""", s)
        assertEquals(rule, roundTrip(rule, RepeatRule.serializer()))
        assertNull(json.decodeFromString(RepeatRule.serializer(), """{"freq":"monthly"}""").anchorDay)
    }

    @Test
    fun allSevenDayCodesRoundTrip() {
        val rule = RepeatRule(Freq.WEEKLY, days = (1..7).map { DayOfWeek(it) })
        val s = json.encodeToString(RepeatRule.serializer(), rule)
        assertTrue(s.contains("""["MO","TU","WE","TH","FR","SA","SU"]"""), s)
        assertEquals(rule, roundTrip(rule, RepeatRule.serializer()))
    }

    @Test
    fun unknownDayCodeIsRejected() {
        assertFailsWith<SerializationException> {
            json.decodeFromString(RepeatRule.serializer(), """{"freq":"weekly","days":["XX"]}""")
        }
    }

    @Test
    fun listNoteAndMessageRoundTrip() {
        val list = TaskList(id = "l1", title = "Inbox", sortKey = "i", hlc = "h1", deleted = true)
        val note = Note(id = "n1", text = "buy milk?", createdAt = Instant.parse("2026-10-09T12:00:00Z"), taskId = "t1", hlc = "h2")
        val msg = ChatMessage(
            id = "m1", role = Role.ASSISTANT, text = "Added to Inbox",
            createdAt = Instant.parse("2026-10-09T12:00:01Z"), status = ChatStatus.ANSWERED, hlc = "h3",
        )
        assertEquals(list, roundTrip(list, TaskList.serializer()))
        assertEquals(note, roundTrip(note, Note.serializer()))
        assertEquals(msg, roundTrip(msg, ChatMessage.serializer()))
    }

    @Test
    fun entitiesAreVersioned() {
        val all: List<Versioned> = listOf(
            fullTask,
            TaskList(id = "l1", title = "Inbox", sortKey = "i", hlc = "h1"),
        )
        assertEquals(listOf(fullTask.id, "l1"), all.map { it.id })
    }
}
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --no-daemon`
Expected: FAIL, compilation error `Unresolved reference 'Task'` (and the other model types).

- [ ] **Step 7: Write the model classes**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/model/Versioned.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.model

/** Every synced row: an id and the hybrid-logical-clock stamp of its last edit. */
interface Versioned {
    val id: String
    val hlc: String
}
```

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/model/RepeatRule.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.model

import kotlinx.datetime.DayOfWeek
import kotlinx.datetime.isoDayNumber
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder

@Serializable
enum class Freq {
    @SerialName("daily") DAILY,
    @SerialName("weekly") WEEKLY,
    @SerialName("monthly") MONTHLY,
    @SerialName("yearly") YEARLY,
}

/**
 * Spec wire form: {"freq":"weekly","every":N,"days":["MO",...],"anchorDay":D}.
 * `days` is used by WEEKLY only. `anchorDay` (MONTHLY/YEARLY only) is the day of month the rule was
 * created on, so a 31st task clamped to Feb 28 returns to the 31st in March; null = use the current due day.
 */
@Serializable
data class RepeatRule(
    val freq: Freq,
    val every: Int = 1,
    val days: List<@Serializable(with = DayCodeSerializer::class) DayOfWeek> = emptyList(),
    val anchorDay: Int? = null,
)

/** Serializes a DayOfWeek as the two-letter code MO, TU, WE, TH, FR, SA, SU. */
internal object DayCodeSerializer : KSerializer<DayOfWeek> {
    private val codes = listOf("MO", "TU", "WE", "TH", "FR", "SA", "SU")

    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("com.sagunkayastha.adhdhelper.DayCode", PrimitiveKind.STRING)

    override fun serialize(encoder: Encoder, value: DayOfWeek) {
        encoder.encodeString(codes[value.isoDayNumber - 1])
    }

    override fun deserialize(decoder: Decoder): DayOfWeek {
        val code = decoder.decodeString()
        val index = codes.indexOf(code)
        if (index < 0) throw SerializationException("Unknown day code: $code")
        return DayOfWeek(index + 1)
    }
}
```

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/model/Entities.kt`:

```kotlin
@file:UseSerializers(InstantIso8601Serializer::class)

package com.sagunkayastha.adhdhelper.model

import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime
import kotlinx.datetime.serializers.InstantIso8601Serializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.UseSerializers
import kotlin.time.Instant

@Serializable
data class TaskList(
    override val id: String,
    val title: String,
    val sortKey: String,
    override val hlc: String,
    val deleted: Boolean = false,
) : Versioned

@Serializable
data class Task(
    override val id: String,
    val listId: String,
    val parentId: String? = null,
    val title: String,
    val details: String = "",
    val starred: Boolean = false,
    val dueDate: LocalDate? = null,
    val dueTime: LocalTime? = null,
    val repeat: RepeatRule? = null,
    val completedAt: Instant? = null,
    val sortKey: String,
    val snoozeUntil: Instant? = null,
    override val hlc: String,
    val deleted: Boolean = false,
) : Versioned

@Serializable
data class Note(
    override val id: String,
    val text: String,
    val createdAt: Instant,
    val taskId: String? = null,
    override val hlc: String,
    val deleted: Boolean = false,
) : Versioned

@Serializable
enum class Role { USER, ASSISTANT }

@Serializable
enum class ChatStatus { QUEUED, SENT, ANSWERED, FAILED }

@Serializable
data class ChatMessage(
    override val id: String,
    val role: Role,
    val text: String,
    val createdAt: Instant,
    val status: ChatStatus,
    override val hlc: String,
) : Versioned
```

Note: if the compiler reports that `InstantIso8601Serializer` is a serializer for a different type than `kotlin.time.Instant`, delete the `@file:UseSerializers(...)` line and its two imports; kotlinx-serialization 1.9.0 then serializes `kotlin.time.Instant` as an ISO-8601 string by itself. The tests decide which form is right.

- [ ] **Step 8: Run the test to verify it passes**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --no-daemon`
Expected: `BUILD SUCCESSFUL`; `ModelSerializationTest` 10 tests pass (report under `shared/build/reports/tests/jvmTest/`).

- [ ] **Step 9: Commit**

```bash
git add .gitignore docker/build.Dockerfile settings.gradle.kts build.gradle.kts gradle.properties gradle/libs.versions.toml shared/build.gradle.kts shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/model shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/model
git commit -F - <<'EOF'
feat(shared): build image, Gradle skeleton, synced data models

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 2: Ids (UUIDv7 and derived ids)

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Sha1.kt`
- Create: `shared/src/jvmMain/kotlin/com/sagunkayastha/adhdhelper/sync/Sha1.jvm.kt`
- Create: `shared/src/androidMain/kotlin/com/sagunkayastha/adhdhelper/sync/Sha1.android.kt`
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Ids.kt`
- Test: `shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/sync/IdsTest.kt`

**Interfaces:**
- Consumes: nothing from Task 1 beyond the Gradle setup.
- Produces:
  - `object Ids { fun newId(): String; fun derived(name: String): String }` (contract)
  - `internal fun Ids.newId(millis: Long, random: Random): String` as an internal overload on the object (test seam; not part of the contract)
  - `internal expect fun sha1(data: ByteArray): ByteArray` in package `com.sagunkayastha.adhdhelper.sync`
  - Phase 3 relies on `Ids.derived("${id}:${nextDate}")` being identical on every device.

- [ ] **Step 1: Write the failing test**

`shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/sync/IdsTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.sync

import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

class IdsTest {
    private val v7 = Regex("^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    private val v5 = Regex("^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

    @Test
    fun newIdIsLowercaseUuidV7() {
        repeat(200) {
            val id = Ids.newId()
            assertEquals(36, id.length)
            assertTrue(v7.matches(id), id)
        }
    }

    @Test
    fun newIdsAreUnique() {
        val ids = List(1000) { Ids.newId() }
        assertEquals(1000, ids.toSet().size)
    }

    @Test
    fun timestampIsInTheFirst48Bits() {
        val id = Ids.newId(0x0123456789abL, Random(1))
        assertTrue(id.startsWith("01234567-89ab-7"), id)
    }

    @Test
    fun laterMillisSortAfterEarlierMillis() {
        val ids = (0 until 300).map { i -> Ids.newId(1_700_000_000_000L + i, Random(i)) }
        assertEquals(ids, ids.sorted())
    }

    @Test
    fun derivedMatchesKnownSha1Vector() {
        // sha1("abc") = a9993e364706816aba3e25717850c26c9cd0d89d; version nibble -> 5, variant -> 10xx
        assertEquals("a9993e36-4706-516a-ba3e-25717850c26c", Ids.derived("abc"))
    }

    @Test
    fun derivedIsDeterministicAndDistinct() {
        val a = Ids.derived("task-1:2026-10-10")
        assertEquals(a, Ids.derived("task-1:2026-10-10"))
        assertNotEquals(a, Ids.derived("task-1:2026-10-11"))
        assertTrue(v5.matches(a), a)
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests "com.sagunkayastha.adhdhelper.sync.IdsTest" --no-daemon`
Expected: FAIL, compilation error `Unresolved reference 'Ids'`.

- [ ] **Step 3: Write the implementation**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Sha1.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.sync

internal expect fun sha1(data: ByteArray): ByteArray
```

`shared/src/jvmMain/kotlin/com/sagunkayastha/adhdhelper/sync/Sha1.jvm.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.sync

import java.security.MessageDigest

internal actual fun sha1(data: ByteArray): ByteArray = MessageDigest.getInstance("SHA-1").digest(data)
```

`shared/src/androidMain/kotlin/com/sagunkayastha/adhdhelper/sync/Sha1.android.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.sync

import java.security.MessageDigest

internal actual fun sha1(data: ByteArray): ByteArray = MessageDigest.getInstance("SHA-1").digest(data)
```

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Ids.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.sync

import kotlin.random.Random
import kotlin.time.Clock

object Ids {
    /** New UUIDv7: 48-bit Unix millis, version 7, variant 10, random rest. Lowercase, 36 chars. */
    fun newId(): String = newId(Clock.System.now().toEpochMilliseconds(), Random.Default)

    internal fun newId(millis: Long, random: Random): String {
        val b = random.nextBytes(16)
        for (i in 0 until 6) b[i] = (millis ushr (8 * (5 - i))).toByte()
        b[6] = ((b[6].toInt() and 0x0f) or 0x70).toByte()
        b[8] = ((b[8].toInt() and 0x3f) or 0x80).toByte()
        return format(b)
    }

    /** Deterministic UUID (version 5 layout) from the SHA-1 of [name]; same input -> same id on every device. */
    fun derived(name: String): String {
        val b = sha1(name.encodeToByteArray()).copyOf(16)
        b[6] = ((b[6].toInt() and 0x0f) or 0x50).toByte()
        b[8] = ((b[8].toInt() and 0x3f) or 0x80).toByte()
        return format(b)
    }

    private fun format(b: ByteArray): String {
        val hex = b.joinToString("") { (it.toInt() and 0xff).toString(16).padStart(2, '0') }
        return "${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-" +
            "${hex.substring(16, 20)}-${hex.substring(20, 32)}"
    }
}
```

- [ ] **Step 4: Run the test to verify it passes, and that the Android target compiles**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests "com.sagunkayastha.adhdhelper.sync.IdsTest" :shared:compileDebugKotlinAndroid --no-daemon`
Expected: `BUILD SUCCESSFUL`; 6 tests in `IdsTest` pass; the Android compile finds the `actual` for `sha1`.

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Sha1.kt shared/src/jvmMain shared/src/androidMain shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Ids.kt shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/sync/IdsTest.kt
git commit -F - <<'EOF'
feat(shared): UUIDv7 and deterministic derived ids

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 3: Hybrid logical clock

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Hlc.kt`
- Test: `shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/sync/HlcTest.kt`

**Interfaces:**
- Consumes: nothing.
- Produces (contract): `class Hlc(private val nodeId: String, private val wallMillis: () -> Long) { fun now(): String; fun observe(remote: String) }`.
  - Format `"%015d-%05d-%s"` (millis zero-padded to 15, counter zero-padded to 5, nodeId). `nodeId` may contain `-`.
  - `now()` is strictly increasing per instance. When the counter would pass 99999 the clock moves to the next millisecond with counter 0, so the format never widens.
  - `observe(remote)` throws `IllegalArgumentException` (incl. `NumberFormatException`) on a malformed stamp; callers treat that row as rejected.
  - Not thread-safe: one instance per device, callers stamp from one writer at a time.

- [ ] **Step 1: Write the failing test**

`shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/sync/HlcTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.sync

import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class HlcTest {
    @Test
    fun formatIsZeroPaddedMillisCounterNode() {
        val hlc = Hlc("A") { 1000L }
        assertEquals("000000000001000-00000-A", hlc.now())
    }

    @Test
    fun sameMillisBumpsCounter() {
        val hlc = Hlc("A") { 1000L }
        assertEquals("000000000001000-00000-A", hlc.now())
        assertEquals("000000000001000-00001-A", hlc.now())
        assertEquals("000000000001000-00002-A", hlc.now())
    }

    @Test
    fun newMillisResetsCounter() {
        var t = 1000L
        val hlc = Hlc("A") { t }
        hlc.now()
        hlc.now()
        t = 2000L
        assertEquals("000000000002000-00000-A", hlc.now())
    }

    @Test
    fun wallClockGoingBackwardsStillIncreases() {
        var t = 5000L
        val hlc = Hlc("A") { t }
        val before = hlc.now()
        t = 1000L
        val after = hlc.now()
        assertEquals("000000000005000-00001-A", after)
        assertTrue(after > before)
    }

    @Test
    fun observeAdvancesPastRemote() {
        val hlc = Hlc("A") { 2000L }
        hlc.now()
        val remote = "000000000009000-00007-B"
        hlc.observe(remote)
        val next = hlc.now()
        assertEquals("000000000009000-00008-A", next)
        assertTrue(next > remote)
    }

    @Test
    fun observingOlderStampDoesNotGoBack() {
        val hlc = Hlc("A") { 9000L }
        hlc.now()
        hlc.observe("000000000001000-00050-B")
        assertEquals("000000000009000-00001-A", hlc.now())
    }

    @Test
    fun observeSameMillisTakesLargerCounter() {
        val hlc = Hlc("A") { 3000L }
        hlc.now()
        hlc.observe("000000000003000-00040-B")
        assertEquals("000000000003000-00041-A", hlc.now())
    }

    @Test
    fun counterOverflowRollsIntoNextMillisecond() {
        val hlc = Hlc("A") { 1000L }
        hlc.observe("000000000001000-99999-B")
        assertEquals("000000000001001-00000-A", hlc.now())
    }

    @Test
    fun nodeIdWithDashesParses() {
        val hlc = Hlc("0190a000-0000-7000-8000-000000000001") { 1L }
        hlc.observe("000000000005000-00007-0190b000-0000-7000-8000-000000000002")
        assertEquals("000000000005000-00008-0190a000-0000-7000-8000-000000000001", hlc.now())
    }

    @Test
    fun malformedStampIsRejected() {
        val hlc = Hlc("A") { 1L }
        assertFailsWith<IllegalArgumentException> { hlc.observe("garbage") }
        assertFailsWith<IllegalArgumentException> { hlc.observe("abc-00001-B") }
    }

    @Test
    fun stampsSortInGenerationOrder() {
        val rnd = Random(7)
        var t = 1_700_000_000_000L
        val hlc = Hlc("A") { t }
        val stamps = List(500) {
            t += rnd.nextLong(-3, 4) // clock jitters forwards and backwards
            hlc.now()
        }
        assertEquals(stamps, stamps.sorted())
        assertEquals(500, stamps.toSet().size)
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests "com.sagunkayastha.adhdhelper.sync.HlcTest" --no-daemon`
Expected: FAIL, compilation error `Unresolved reference 'Hlc'`.

- [ ] **Step 3: Write the implementation**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Hlc.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.sync

/**
 * Hybrid logical clock. Stamps look like "000001760000000-00003-<nodeId>" and compare correctly as strings.
 * Not thread-safe: callers stamp from one writer at a time.
 */
class Hlc(private val nodeId: String, private val wallMillis: () -> Long) {
    private var millis = 0L
    private var counter = 0

    fun now(): String {
        val wall = wallMillis()
        if (wall > millis) {
            millis = wall
            counter = 0
        } else {
            bump()
        }
        return format(millis, counter, nodeId)
    }

    fun observe(remote: String) {
        val parts = remote.split('-', limit = 3)
        require(parts.size == 3) { "Malformed hlc: $remote" }
        val remoteMillis = parts[0].toLong()
        val remoteCounter = parts[1].toInt()
        if (remoteMillis > millis) {
            millis = remoteMillis
            counter = remoteCounter
        } else if (remoteMillis == millis && remoteCounter > counter) {
            counter = remoteCounter
        }
    }

    private fun bump() {
        if (counter == MAX_COUNTER) {
            millis += 1
            counter = 0
        } else {
            counter += 1
        }
    }

    private companion object {
        const val MAX_COUNTER = 99_999

        fun format(millis: Long, counter: Int, nodeId: String): String =
            millis.toString().padStart(15, '0') + "-" + counter.toString().padStart(5, '0') + "-" + nodeId
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests "com.sagunkayastha.adhdhelper.sync.HlcTest" --no-daemon`
Expected: `BUILD SUCCESSFUL`; 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Hlc.kt shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/sync/HlcTest.kt
git commit -F - <<'EOF'
feat(shared): hybrid logical clock

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 4: Merge rule and wire types (sync DTOs, Api, pairing, health)

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Merge.kt`
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Wire.kt`
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/Api.kt`
- Test: `shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/sync/MergeAndWireTest.kt`

**Interfaces:**
- Consumes: `Versioned`, `TaskList`, `Task`, `Note`, `ChatMessage`, `Role`, `ChatStatus` from Task 1.
- Produces (contract):
  - `object Merge { fun <T : Versioned> wins(incoming: T, existing: T?): Boolean }` — `existing == null || incoming.hlc > existing.hlc`
  - `data class Changes(lists, tasks, notes, messages) { fun isEmpty(): Boolean }`
  - `data class SyncRequest(val cursor: Long, val changes: Changes)`
  - `data class SyncResponse(val cursor: Long, val changes: Changes, val rejected: List<String> = emptyList(), val fullResync: Boolean = false)`
  - `data class EventPoke(val rev: Long)`
  - `object Api { const val PREFIX = "/api/v1"; const val VERSION = 1 }`
  - `data class PairRequest(val code: String, val deviceName: String)`, `data class PairResponse(val token: String, val deviceId: String)`
  - `data class Health(val ok: Boolean, val rev: Long, val claude: String, val apkVersion: Int? = null)`

- [ ] **Step 1: Write the failing test**

`shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/sync/MergeAndWireTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.sync

import com.sagunkayastha.adhdhelper.core.Api
import com.sagunkayastha.adhdhelper.core.Health
import com.sagunkayastha.adhdhelper.core.PairRequest
import com.sagunkayastha.adhdhelper.core.PairResponse
import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.model.ChatStatus
import com.sagunkayastha.adhdhelper.model.Note
import com.sagunkayastha.adhdhelper.model.Role
import com.sagunkayastha.adhdhelper.model.Task
import com.sagunkayastha.adhdhelper.model.TaskList
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.time.Instant

class MergeAndWireTest {
    private val json = Json

    private fun <T> roundTrip(value: T, serializer: KSerializer<T>): T =
        json.decodeFromString(serializer, json.encodeToString(serializer, value))

    private fun task(hlc: String, title: String = "x", deleted: Boolean = false) =
        Task(id = "t1", listId = "l1", title = title, sortKey = "i", hlc = hlc, deleted = deleted)

    private val older = "000000000001000-00000-A"
    private val newer = "000000000002000-00000-B"

    @Test
    fun anythingWinsAgainstNothing() {
        assertTrue(Merge.wins(task(older), null))
    }

    @Test
    fun laterHlcWins() {
        assertTrue(Merge.wins(task(newer, "phone"), task(older, "pc")))
        assertFalse(Merge.wins(task(older, "pc"), task(newer, "phone")))
    }

    @Test
    fun resendingSameRowIsNoOp() {
        assertFalse(Merge.wins(task(older), task(older)))
    }

    @Test
    fun laterTombstoneBeatsLiveRow() {
        assertTrue(Merge.wins(task(newer, deleted = true), task(older)))
    }

    @Test
    fun olderLiveEditDoesNotResurrectTombstone() {
        assertFalse(Merge.wins(task(older, "edited offline"), task(newer, deleted = true)))
    }

    @Test
    fun sameMillisTieBreaksOnCounterThenNode() {
        assertTrue(Merge.wins(task("000000000001000-00001-A"), task("000000000001000-00000-B")))
        assertTrue(Merge.wins(task("000000000001000-00000-B"), task("000000000001000-00000-A")))
    }

    @Test
    fun changesIsEmptyOnlyWhenAllFourAreEmpty() {
        assertTrue(Changes().isEmpty())
        assertFalse(Changes(lists = listOf(TaskList("l1", "Inbox", "i", older))).isEmpty())
        assertFalse(Changes(tasks = listOf(task(older))).isEmpty())
        assertFalse(Changes(notes = listOf(Note("n1", "hi", Instant.parse("2026-10-09T12:00:00Z"), hlc = older))).isEmpty())
        assertFalse(
            Changes(messages = listOf(ChatMessage("m1", Role.USER, "hi", Instant.parse("2026-10-09T12:00:00Z"), ChatStatus.QUEUED, older)))
                .isEmpty(),
        )
    }

    @Test
    fun syncRequestAndResponseRoundTrip() {
        val changes = Changes(
            lists = listOf(TaskList("l1", "Inbox", "i", older)),
            tasks = listOf(task(newer, deleted = true)),
            notes = listOf(Note("n1", "hi", Instant.parse("2026-10-09T12:00:00Z"), hlc = older)),
            messages = listOf(ChatMessage("m1", Role.USER, "hi", Instant.parse("2026-10-09T12:00:00Z"), ChatStatus.QUEUED, older)),
        )
        val req = SyncRequest(cursor = 41, changes = changes)
        assertEquals(req, roundTrip(req, SyncRequest.serializer()))
        val resp = SyncResponse(cursor = 57, changes = changes, rejected = listOf("t9"), fullResync = true)
        assertEquals(resp, roundTrip(resp, SyncResponse.serializer()))
    }

    @Test
    fun syncResponseDefaultsWhenFieldsMissing() {
        val resp = json.decodeFromString(SyncResponse.serializer(), """{"cursor":3,"changes":{}}""")
        assertEquals(SyncResponse(cursor = 3, changes = Changes()), resp)
        assertEquals(emptyList<String>(), resp.rejected)
        assertFalse(resp.fullResync)
    }

    @Test
    fun eventPokeIsJustRev() {
        assertEquals("""{"rev":12}""", json.encodeToString(EventPoke.serializer(), EventPoke(12)))
    }

    @Test
    fun apiConstants() {
        assertEquals("/api/v1", Api.PREFIX)
        assertEquals(1, Api.VERSION)
    }

    @Test
    fun pairingAndHealthRoundTrip() {
        val req = PairRequest(code = "AB12CD34", deviceName = "Pixel")
        assertEquals(req, roundTrip(req, PairRequest.serializer()))
        val resp = PairResponse(token = "tok", deviceId = "dev-1")
        assertEquals(resp, roundTrip(resp, PairResponse.serializer()))
        val health = Health(ok = true, rev = 9, claude = "ok", apkVersion = 3)
        assertEquals(health, roundTrip(health, Health.serializer()))
        val noApk = json.decodeFromString(Health.serializer(), """{"ok":true,"rev":0,"claude":"missing"}""")
        assertNull(noApk.apkVersion)
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests "com.sagunkayastha.adhdhelper.sync.MergeAndWireTest" --no-daemon`
Expected: FAIL, compilation errors `Unresolved reference 'Merge'`, `'Changes'`, `'Api'`.

- [ ] **Step 3: Write the implementation**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Merge.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.sync

import com.sagunkayastha.adhdhelper.model.Versioned

/** Whole-row last-writer-wins by hlc. Tombstones are ordinary rows. Equal hlc = no-op (idempotent resend). */
object Merge {
    fun <T : Versioned> wins(incoming: T, existing: T?): Boolean =
        existing == null || incoming.hlc > existing.hlc
}
```

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Wire.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.sync

import com.sagunkayastha.adhdhelper.model.ChatMessage
import com.sagunkayastha.adhdhelper.model.Note
import com.sagunkayastha.adhdhelper.model.Task
import com.sagunkayastha.adhdhelper.model.TaskList
import kotlinx.serialization.Serializable

@Serializable
data class Changes(
    val lists: List<TaskList> = emptyList(),
    val tasks: List<Task> = emptyList(),
    val notes: List<Note> = emptyList(),
    val messages: List<ChatMessage> = emptyList(),
) {
    fun isEmpty(): Boolean = lists.isEmpty() && tasks.isEmpty() && notes.isEmpty() && messages.isEmpty()
}

@Serializable
data class SyncRequest(val cursor: Long, val changes: Changes)

@Serializable
data class SyncResponse(
    val cursor: Long,
    val changes: Changes,
    val rejected: List<String> = emptyList(),
    val fullResync: Boolean = false,
)

@Serializable
data class EventPoke(val rev: Long)
```

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/Api.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.core

import kotlinx.serialization.Serializable

object Api {
    const val PREFIX = "/api/v1"
    const val VERSION = 1
}

@Serializable
data class PairRequest(val code: String, val deviceName: String)

@Serializable
data class PairResponse(val token: String, val deviceId: String)

/** `claude` is one of "ok", "unauthenticated", "missing". */
@Serializable
data class Health(val ok: Boolean, val rev: Long, val claude: String, val apkVersion: Int? = null)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests "com.sagunkayastha.adhdhelper.sync.MergeAndWireTest" --no-daemon`
Expected: `BUILD SUCCESSFUL`; 12 tests pass.

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Merge.kt shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/sync/Wire.kt shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/Api.kt shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/sync/MergeAndWireTest.kt
git commit -F - <<'EOF'
feat(shared): LWW merge rule, sync/pair/health wire types

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 5: SortKey (fractional index)

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/SortKey.kt`
- Test: `shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/SortKeyTest.kt`

**Interfaces:**
- Consumes: nothing.
- Produces (contract): `object SortKey { fun between(before: String?, after: String?): String }`.
  - Keys use digits `0-9a-z` (ASCII order = string order, also SQLite BINARY collation) and never end in `0`.
  - `null` means open end; `between(null, null) == "i"`.
  - When `before >= after` (twin keys from two devices), returns `before + "i"`: greater than `before`, does not throw. Phase 3 should sort by `(sortKey, id)` so twins have a stable order.

- [ ] **Step 1: Write the failing test**

`shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/SortKeyTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.core

import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class SortKeyTest {
    @Test
    fun firstKeyInEmptyList() {
        assertEquals("i", SortKey.between(null, null))
    }

    @Test
    fun openEnds() {
        assertEquals("9", SortKey.between(null, "i"))
        assertEquals("r", SortKey.between("i", null))
    }

    @Test
    fun adjacentKeysGoOneLevelDeeper() {
        assertEquals("ai", SortKey.between("a", "b"))
        assertEquals("a0i", SortKey.between("a", "a1"))
        val k = SortKey.between("a", "b")
        assertTrue("a" < k && k < "b")
    }

    @Test
    fun equalNeighboursDoNotThrow() {
        val k = SortKey.between("k", "k")
        assertTrue(k > "k", k)
    }

    @Test
    fun thousandRandomInsertsStayOrdered() {
        val rnd = Random(42)
        val keys = mutableListOf<String>()
        repeat(1000) {
            val i = rnd.nextInt(keys.size + 1)
            val before = keys.getOrNull(i - 1)
            val after = keys.getOrNull(i)
            val k = SortKey.between(before, after)
            assertTrue(before == null || before < k, "$before !< $k")
            assertTrue(after == null || k < after, "$k !< $after")
            assertTrue(!k.endsWith('0'), "key ends in 0: $k")
            keys.add(i, k)
        }
        assertEquals(keys.sorted(), keys)
        assertEquals(1000, keys.toSet().size)
    }

    @Test
    fun repeatedPrependAndAppendStayOrdered() {
        val keys = mutableListOf(SortKey.between(null, null))
        repeat(200) { keys.add(0, SortKey.between(null, keys.first())) }
        repeat(200) { keys.add(SortKey.between(keys.last(), null)) }
        assertEquals(keys.sorted(), keys)
        assertTrue(keys.all { it.length <= 64 }, "keys grew too long")
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests "com.sagunkayastha.adhdhelper.core.SortKeyTest" --no-daemon`
Expected: FAIL, compilation error `Unresolved reference 'SortKey'`.

- [ ] **Step 3: Write the implementation**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/SortKey.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.core

/**
 * Fractional index keys: base-36 fractions written as strings, so reordering rewrites one row.
 * Keys never end in '0', which guarantees a key always exists between two different keys.
 */
object SortKey {
    private const val DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"

    fun between(before: String?, after: String?): String {
        if (before != null && after != null && before >= after) {
            // Twin keys (two devices appended offline): place just after `before` instead of failing.
            return before + midpoint("", null)
        }
        return midpoint(before ?: "", after)
    }

    private fun midpoint(a: String, b: String?): String {
        if (b != null) {
            var n = 0
            while (n < b.length && (if (n < a.length) a[n] else '0') == b[n]) n++
            if (n > 0) return b.substring(0, n) + midpoint(a.drop(n), b.substring(n))
        }
        val digitA = if (a.isNotEmpty()) DIGITS.indexOf(a[0]) else 0
        val digitB = if (b != null) DIGITS.indexOf(b[0]) else DIGITS.length
        if (digitB - digitA > 1) return DIGITS[(digitA + digitB + 1) / 2].toString()
        if (b != null && b.length > 1) return b.substring(0, 1)
        return DIGITS[digitA].toString() + midpoint(a.drop(1), null)
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests "com.sagunkayastha.adhdhelper.core.SortKeyTest" --no-daemon`
Expected: `BUILD SUCCESSFUL`; 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/SortKey.kt shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/SortKeyTest.kt
git commit -F - <<'EOF'
feat(shared): fractional-index sort keys

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 6: Recurrence

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/Recurrence.kt`
- Test: `shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/RecurrenceTest.kt`

**Interfaces:**
- Consumes: `RepeatRule`, `Freq` from Task 1.
- Produces (contract): `object Recurrence { fun next(rule: RepeatRule, from: LocalDate): LocalDate }` — first occurrence strictly after `from`.
  - DAILY: `from + every` days.
  - WEEKLY with no `days`: `from + 7*every` days. With `days`: the next chosen weekday later in `from`'s Monday-start week; otherwise the first chosen weekday of the week `every` weeks later.
  - MONTHLY / YEARLY: the month `every` months / `12*every` months after `from`'s month, on day `rule.anchorDay ?: from.day`, clamped to the last day of that month. With `anchorDay = 31`: Jan 31 -> Feb 28 -> Mar 31. With `anchorDay = 29` yearly: Feb 29 2028 -> Feb 28 2029 -> ... -> Feb 29 2032.
  - `every < 1` throws `IllegalArgumentException`.

- [ ] **Step 1: Write the failing test**

`shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/RecurrenceTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.core

import com.sagunkayastha.adhdhelper.model.Freq
import com.sagunkayastha.adhdhelper.model.RepeatRule
import kotlinx.datetime.DayOfWeek
import kotlinx.datetime.LocalDate
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class RecurrenceTest {
    private fun d(y: Int, m: Int, day: Int) = LocalDate(y, m, day)

    // 2026-10-07 is a Wednesday, 2026-10-09 a Friday.

    @Test
    fun dailyEveryDay() {
        assertEquals(d(2026, 10, 10), Recurrence.next(RepeatRule(Freq.DAILY), d(2026, 10, 9)))
    }

    @Test
    fun dailyEveryThreeCrossesMonthEnd() {
        assertEquals(d(2026, 11, 2), Recurrence.next(RepeatRule(Freq.DAILY, every = 3), d(2026, 10, 30)))
    }

    @Test
    fun weeklyWithoutDaysIsSevenTimesEvery() {
        assertEquals(d(2026, 10, 16), Recurrence.next(RepeatRule(Freq.WEEKLY), d(2026, 10, 9)))
        assertEquals(d(2026, 10, 23), Recurrence.next(RepeatRule(Freq.WEEKLY, every = 2), d(2026, 10, 9)))
    }

    @Test
    fun weeklyPicksLaterDaySameWeek() {
        val rule = RepeatRule(Freq.WEEKLY, days = listOf(DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY, DayOfWeek.FRIDAY))
        assertEquals(d(2026, 10, 9), Recurrence.next(rule, d(2026, 10, 7)))
    }

    @Test
    fun weeklyWrapsToNextWeek() {
        val rule = RepeatRule(Freq.WEEKLY, days = listOf(DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY, DayOfWeek.FRIDAY))
        assertEquals(d(2026, 10, 12), Recurrence.next(rule, d(2026, 10, 9)))
    }

    @Test
    fun weeklyEveryTwoWrapsTwoWeeksAhead() {
        val rule = RepeatRule(Freq.WEEKLY, every = 2, days = listOf(DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY, DayOfWeek.FRIDAY))
        assertEquals(d(2026, 10, 9), Recurrence.next(rule, d(2026, 10, 7)))
        assertEquals(d(2026, 10, 19), Recurrence.next(rule, d(2026, 10, 9)))
    }

    @Test
    fun weeklyFromADayNotInTheSet() {
        val rule = RepeatRule(Freq.WEEKLY, days = listOf(DayOfWeek.TUESDAY))
        assertEquals(d(2026, 10, 13), Recurrence.next(rule, d(2026, 10, 9)))
    }

    @Test
    fun weeklySingleDaySameWeekdayGoesAWeekAhead() {
        val rule = RepeatRule(Freq.WEEKLY, days = listOf(DayOfWeek.FRIDAY))
        assertEquals(d(2026, 10, 16), Recurrence.next(rule, d(2026, 10, 9)))
    }

    @Test
    fun weeklyWrapAcrossYearEnd() {
        // 2026-12-31 is a Thursday; next Monday is 2027-01-04.
        val rule = RepeatRule(Freq.WEEKLY, days = listOf(DayOfWeek.MONDAY))
        assertEquals(d(2027, 1, 4), Recurrence.next(rule, d(2026, 12, 31)))
    }

    @Test
    fun monthlySameDay() {
        assertEquals(d(2026, 11, 9), Recurrence.next(RepeatRule(Freq.MONTHLY), d(2026, 10, 9)))
    }

    @Test
    fun monthlyOn31stClampsToMonthEnd() {
        assertEquals(d(2027, 2, 28), Recurrence.next(RepeatRule(Freq.MONTHLY), d(2027, 1, 31)))
        assertEquals(d(2028, 2, 29), Recurrence.next(RepeatRule(Freq.MONTHLY), d(2028, 1, 31)))
        assertEquals(d(2026, 11, 30), Recurrence.next(RepeatRule(Freq.MONTHLY), d(2026, 10, 31)))
        assertEquals(d(2027, 2, 28), Recurrence.next(RepeatRule(Freq.MONTHLY, every = 3), d(2026, 11, 30)))
    }

    @Test
    fun monthlyAnchorReturnsToThe31st() {
        val rule = RepeatRule(Freq.MONTHLY, anchorDay = 31)
        val feb = Recurrence.next(rule, d(2027, 1, 31))
        assertEquals(d(2027, 2, 28), feb)
        val mar = Recurrence.next(rule, feb)
        assertEquals(d(2027, 3, 31), mar)
        assertEquals(d(2027, 4, 30), Recurrence.next(rule, mar))
        // Without an anchor the clamped day sticks (legacy rows).
        assertEquals(d(2027, 3, 28), Recurrence.next(RepeatRule(Freq.MONTHLY), feb))
    }

    @Test
    fun yearlySameDate() {
        assertEquals(d(2028, 10, 9), Recurrence.next(RepeatRule(Freq.YEARLY, every = 2), d(2026, 10, 9)))
    }

    @Test
    fun yearlyFeb29ClampsInNonLeapYear() {
        assertEquals(d(2029, 2, 28), Recurrence.next(RepeatRule(Freq.YEARLY), d(2028, 2, 29)))
        assertEquals(d(2032, 2, 29), Recurrence.next(RepeatRule(Freq.YEARLY, every = 4), d(2028, 2, 29)))
    }

    @Test
    fun yearlyFeb29AnchorReturnsInLeapYear() {
        val rule = RepeatRule(Freq.YEARLY, anchorDay = 29)
        var date = d(2028, 2, 29)
        val seen = List(4) { date = Recurrence.next(rule, date); date }
        assertEquals(listOf(d(2029, 2, 28), d(2030, 2, 28), d(2031, 2, 28), d(2032, 2, 29)), seen)
    }

    @Test
    fun everyBelowOneIsRejected() {
        assertFailsWith<IllegalArgumentException> { Recurrence.next(RepeatRule(Freq.DAILY, every = 0), d(2026, 10, 9)) }
        assertFailsWith<IllegalArgumentException> { Recurrence.next(RepeatRule(Freq.WEEKLY, every = -1), d(2026, 10, 9)) }
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests "com.sagunkayastha.adhdhelper.core.RecurrenceTest" --no-daemon`
Expected: FAIL, compilation error `Unresolved reference 'Recurrence'`.

- [ ] **Step 3: Write the implementation**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/Recurrence.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.core

import com.sagunkayastha.adhdhelper.model.Freq
import com.sagunkayastha.adhdhelper.model.RepeatRule
import kotlinx.datetime.DateTimeUnit
import kotlinx.datetime.LocalDate
import kotlinx.datetime.isoDayNumber
import kotlinx.datetime.minus
import kotlinx.datetime.plus

object Recurrence {
    /**
     * First occurrence strictly after [from]. Month/year steps land on `rule.anchorDay` (or `from`'s day when
     * there is no anchor), clamped to the last day of the target month.
     */
    fun next(rule: RepeatRule, from: LocalDate): LocalDate {
        require(rule.every >= 1) { "every must be >= 1, was ${rule.every}" }
        return when (rule.freq) {
            Freq.DAILY -> from.plus(rule.every, DateTimeUnit.DAY)
            Freq.WEEKLY -> nextWeekly(rule, from)
            Freq.MONTHLY -> stepMonths(from, rule.every, rule.anchorDay)
            Freq.YEARLY -> stepMonths(from, rule.every * 12, rule.anchorDay)
        }
    }

    private fun stepMonths(from: LocalDate, months: Int, anchorDay: Int?): LocalDate {
        val firstOfTarget = LocalDate(from.year, from.month, 1).plus(months, DateTimeUnit.MONTH)
        val lastDay = firstOfTarget.plus(1, DateTimeUnit.MONTH).minus(1, DateTimeUnit.DAY).day
        val wanted = anchorDay ?: from.day
        return LocalDate(firstOfTarget.year, firstOfTarget.month, minOf(wanted, lastDay))
    }

    private fun nextWeekly(rule: RepeatRule, from: LocalDate): LocalDate {
        if (rule.days.isEmpty()) return from.plus(rule.every * 7, DateTimeUnit.DAY)
        val today = from.dayOfWeek.isoDayNumber
        val chosen = rule.days.map { it.isoDayNumber }
        val laterThisWeek = chosen.filter { it > today }.minOrNull()
        if (laterThisWeek != null) return from.plus(laterThisWeek - today, DateTimeUnit.DAY)
        val monday = from.minus(today - 1, DateTimeUnit.DAY)
        return monday.plus(rule.every * 7 + chosen.min() - 1, DateTimeUnit.DAY)
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests "com.sagunkayastha.adhdhelper.core.RecurrenceTest" --no-daemon`
Expected: `BUILD SUCCESSFUL`; 16 tests pass.

- [ ] **Step 5: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/Recurrence.kt shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/RecurrenceTest.kt
git commit -F - <<'EOF'
feat(shared): recurrence next-date math

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

### Task 7: ReminderMath (next fire time, DST-safe)

**Files:**
- Create: `shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/ReminderMath.kt`
- Test: `shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/ReminderMathTest.kt`

**Interfaces:**
- Consumes: `Task`, `RepeatRule`, `Freq` (Task 1); `Recurrence.next` (Task 6).
- Produces (contract): `object ReminderMath { fun nextFire(task: Task, zone: TimeZone, now: Instant): Instant? }`.
  - `null` if `deleted`, `completedAt != null`, `dueDate == null`, or `dueTime == null`.
  - Otherwise `due = LocalDateTime(dueDate, dueTime).toInstant(zone)`; returns `snoozeUntil` if it is non-null and strictly after `due`, else `due`. Nonexistent local times shift forward by the gap; ambiguous ones use the earlier offset.
  - `now` stays in the signature but does not affect the result. The result may be in the past: callers compare it with `now` themselves (fire at once, or skip).
  - Phase 4 (Android `ReminderScheduler`) and Phase 5 (desktop timer) call this with `TimeZone.of(settings.zone)`.

- [ ] **Step 1: Write the failing test**

`shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/ReminderMathTest.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.core

import com.sagunkayastha.adhdhelper.model.Freq
import com.sagunkayastha.adhdhelper.model.RepeatRule
import com.sagunkayastha.adhdhelper.model.Task
import kotlinx.datetime.LocalDate
import kotlinx.datetime.LocalTime
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.time.Instant

class ReminderMathTest {
    private val denver = TimeZone.of("America/Denver")
    private val now = Instant.parse("2026-10-01T00:00:00Z")
    private val sixPm = LocalTime(18, 0)

    private fun task(
        date: LocalDate?,
        time: LocalTime? = sixPm,
        snoozeUntil: Instant? = null,
        completedAt: Instant? = null,
        deleted: Boolean = false,
    ) = Task(
        id = "t1", listId = "l1", title = "Take meds", sortKey = "i", hlc = "h",
        dueDate = date, dueTime = time, repeat = RepeatRule(Freq.DAILY),
        snoozeUntil = snoozeUntil, completedAt = completedAt, deleted = deleted,
    )

    private fun firesForDailyRun(start: LocalDate, days: Int): List<Instant> {
        val rule = RepeatRule(Freq.DAILY)
        var date = start
        return List(days) {
            val fire = ReminderMath.nextFire(task(date), denver, now)!!
            date = Recurrence.next(rule, date)
            fire
        }
    }

    @Test
    fun dailySixPmStaysSixPmAcrossSpringForward() {
        // 2027-03-14 02:00 MST -> 03:00 MDT (UTC-7 -> UTC-6).
        val fires = firesForDailyRun(LocalDate(2027, 3, 12), 4)
        assertEquals(
            listOf("2027-03-13T01:00:00Z", "2027-03-14T01:00:00Z", "2027-03-15T00:00:00Z", "2027-03-16T00:00:00Z")
                .map { Instant.parse(it) },
            fires,
        )
        fires.forEach { assertEquals(sixPm, it.toLocalDateTime(denver).time) }
    }

    @Test
    fun dailySixPmStaysSixPmAcrossFallBack() {
        // 2026-11-01 02:00 MDT -> 01:00 MST (UTC-6 -> UTC-7).
        val fires = firesForDailyRun(LocalDate(2026, 10, 30), 4)
        assertEquals(
            listOf("2026-10-31T00:00:00Z", "2026-11-01T00:00:00Z", "2026-11-02T01:00:00Z", "2026-11-03T01:00:00Z")
                .map { Instant.parse(it) },
            fires,
        )
        fires.forEach { assertEquals(sixPm, it.toLocalDateTime(denver).time) }
    }

    @Test
    fun nonexistentLocalTimeShiftsForward() {
        // 02:30 does not exist on 2027-03-14 in Denver; fires at 03:30 MDT.
        val fire = ReminderMath.nextFire(task(LocalDate(2027, 3, 14), LocalTime(2, 30)), denver, now)
        assertEquals(Instant.parse("2027-03-14T09:30:00Z"), fire)
    }

    @Test
    fun ambiguousLocalTimeUsesFirstOccurrence() {
        // 01:30 happens twice on 2026-11-01; the first one is MDT (UTC-6).
        val fire = ReminderMath.nextFire(task(LocalDate(2026, 11, 1), LocalTime(1, 30)), denver, now)
        assertEquals(Instant.parse("2026-11-01T07:30:00Z"), fire)
    }

    // 2026-10-09 18:00 MDT == 2026-10-10T00:00:00Z.

    @Test
    fun snoozeAfterDueWins() {
        val snooze = Instant.parse("2026-10-10T00:10:00Z")
        val t = task(LocalDate(2026, 10, 9), snoozeUntil = snooze)
        assertEquals(snooze, ReminderMath.nextFire(t, denver, Instant.parse("2026-10-10T00:01:00Z")))
    }

    @Test
    fun snoozeBeforeDueIsIgnored() {
        val t = task(LocalDate(2026, 10, 9), snoozeUntil = Instant.parse("2026-10-09T23:10:00Z"))
        assertEquals(Instant.parse("2026-10-10T00:00:00Z"), ReminderMath.nextFire(t, denver, now))
    }

    @Test
    fun nowDoesNotChangeTheResult() {
        val snooze = Instant.parse("2026-10-10T00:10:00Z")
        val t = task(LocalDate(2026, 10, 9), snoozeUntil = snooze)
        // Long after the snooze has passed: still the snooze instant (in the past; the caller decides).
        assertEquals(snooze, ReminderMath.nextFire(t, denver, Instant.parse("2026-10-12T00:00:00Z")))
        assertEquals(snooze, ReminderMath.nextFire(t, denver, Instant.parse("2020-01-01T00:00:00Z")))
    }

    @Test
    fun pastDueTimeIsStillReturned() {
        val t = task(LocalDate(2026, 9, 1))
        assertEquals(Instant.parse("2026-09-02T00:00:00Z"), ReminderMath.nextFire(t, denver, now))
    }

    @Test
    fun completedTaskHasNoFire() {
        val t = task(LocalDate(2026, 10, 9), completedAt = Instant.parse("2026-10-09T12:00:00Z"))
        assertNull(ReminderMath.nextFire(t, denver, now))
    }

    @Test
    fun deletedTaskHasNoFire() {
        assertNull(ReminderMath.nextFire(task(LocalDate(2026, 10, 9), deleted = true), denver, now))
    }

    @Test
    fun allDayTaskHasNoFire() {
        assertNull(ReminderMath.nextFire(task(LocalDate(2026, 10, 9), time = null), denver, now))
    }

    @Test
    fun timeWithoutDateHasNoFire() {
        assertNull(ReminderMath.nextFire(task(null), denver, now))
    }

    @Test
    fun snoozeDoesNotRescueAnUntimedTask() {
        val t = task(LocalDate(2026, 10, 9), time = null, snoozeUntil = Instant.parse("2026-10-09T23:10:00Z"))
        assertNull(ReminderMath.nextFire(t, denver, now))
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests "com.sagunkayastha.adhdhelper.core.ReminderMathTest" --no-daemon`
Expected: FAIL, compilation error `Unresolved reference 'ReminderMath'`.

- [ ] **Step 3: Write the implementation**

`shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/ReminderMath.kt`:

```kotlin
package com.sagunkayastha.adhdhelper.core

import com.sagunkayastha.adhdhelper.model.Task
import kotlinx.datetime.LocalDateTime
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toInstant
import kotlin.time.Instant

object ReminderMath {
    /**
     * When this task's reminder should ring, or null if it never should.
     * Due date+time are wall-clock in [zone], so 18:00 stays 18:00 across DST.
     * A snooze later than the due instant replaces it. [now] does not affect the result (kept for the
     * contract); the result may be in the past and callers compare it with now to fire at once or skip.
     */
    @Suppress("UNUSED_PARAMETER")
    fun nextFire(task: Task, zone: TimeZone, now: Instant): Instant? {
        if (task.deleted || task.completedAt != null) return null
        val date = task.dueDate ?: return null
        val time = task.dueTime ?: return null
        val due = LocalDateTime(date, time).toInstant(zone)
        val snooze = task.snoozeUntil
        return if (snooze != null && snooze > due) snooze else due
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest --tests "com.sagunkayastha.adhdhelper.core.ReminderMathTest" --no-daemon`
Expected: `BUILD SUCCESSFUL`; 13 tests pass.

- [ ] **Step 5: Run the whole phase suite and the Android compile**

Run: `docker run --rm --user "$(id -u):$(id -g)" -e GRADLE_USER_HOME=/gradle -v adhd-gradle:/gradle -v "$PWD":/src -w /src adhd-build gradle :shared:jvmTest :shared:compileDebugKotlinAndroid --no-daemon`
Expected: `BUILD SUCCESSFUL`; 74 tests pass across `ModelSerializationTest` (10), `IdsTest` (6), `HlcTest` (11), `MergeAndWireTest` (12), `SortKeyTest` (6), `RecurrenceTest` (16), `ReminderMathTest` (13).

- [ ] **Step 6: Commit**

```bash
git add shared/src/commonMain/kotlin/com/sagunkayastha/adhdhelper/core/ReminderMath.kt shared/src/commonTest/kotlin/com/sagunkayastha/adhdhelper/core/ReminderMathTest.kt
git commit -F - <<'EOF'
feat(shared): DST-safe reminder next-fire math

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0143tpSGVgH2wyDhkxyE99yr
EOF
```

---

## Self-review notes (done while writing)

- **Spec coverage (Phase 1 scope):** build container (Task 1), Gradle skeleton with only `shared` (Task 1), models incl. `RepeatRule` spec JSON (Task 1), HLC (Task 3), UUIDv7 + derived ids (Task 2), LWW merge incl. tombstones and idempotent resend (Task 4), sync / events / pair / health DTOs (Task 4), fractional index (Task 5), recurrence around month ends and leap years (Task 6), reminder next-fire incl. DST and snooze (Task 7), `RepeatRule.anchorDay` month-end return (Tasks 1, 6). Everything else in the spec belongs to Phases 2-7.
- **Contract check:** every name and type in the index's Phase 1 contract is defined with the same signature. Added beyond the contract, all `internal`: `DayCodeSerializer`, `sha1`, `Ids.newId(millis, random)`.
- **Test counts** in Task 7 Step 5 match the `@Test` functions in each file.
