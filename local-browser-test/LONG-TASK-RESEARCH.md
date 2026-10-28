# Long tasks for local agents: compaction, turn limits, prompts (research 2026-10-28, opus subagent, Claude + gemini-api --search)
Saved by Rem from the agent's reply.

## Summary
1. llama.cpp web UI cannot compact mid-run: compaction only via /compact or the context gauge, refused while the agentic loop runs.
   A 150-step single run will hit 128k and fail. Fix: model stops every ~3 items (progress report), user/agent /compact, "continue".
2. Web UI settings: browser localStorage "LlamaUi.config": agenticMaxTurns (100; at the limit it ASKS continue?, yes resets),
   compactionPreservedSteps (10), compactionPrompt, excludeReasoningFromContext (false), systemMessage, preEncodeConversation.
   Server defaults: --ui-config JSON / --ui-config-file PATH (alias --webui-config[-file]); applied only on first visit or Reset to Default.
3. opencode compacts automatically (dev source keys compaction.auto, compaction.keep.tokens 15k, compaction.buffer; fires ~109k of 128k).
   Released docs still show older keys auto/prune/reserved: check our version. Custom prompt via experimental.session.compacting hook.
4. Tool output size matters most: at 16k chars/result ~25 steps fill 128k. Use extracted text 4-6k chars, chrome-devtools-mcp --slim
   (3 tools) or trimmed tool list.
5. Design: notes appended in chat + running done/left line + one structured summary at batch boundaries that copies notes exactly.
   Masking (JetBrains 2508.21433) cheapest but per-turn rewrites force re-processing on hybrid models.
6. Cache (server-context.cpp): a change restores the newest checkpoint before it; full re-process only if none fits (Gemini wrong).

## Web UI recommended
1. Bridge cap 4-6k chars; evaluate_script returning extracted text; take_snapshot filePath/verbose:false; or --slim.
2. System prompt below; stop every 3 items; /compact at ~50-60% gauge; "continue".
3. compactionPreservedSteps=2; compactionPrompt below.  4. excludeReasoningFromContext=true for long runs.
5. agenticMaxTurns 40-60 per batch (continue? = stall alarm).  6. Ship via --ui-config-file; reset browsers once.
Example: {"agenticMaxTurns":60,"compactionPreservedSteps":2,"excludeReasoningFromContext":true,"compactionPrompt":"...","systemMessage":"..."}

## opencode recommended
1. Same tool limits + prompt; todowrite tool as done/left list (append-only, cache-safe).  2. limit.context 131072 (+limit.output).
3. compaction.auto true, compaction.buffer ~40000 (~70%, ~90k).  4. compaction.keep.tokens 8000-10000.
5. Custom prompt via compacting hook.  6. experimental.background_compaction off; prune off on hybrid models.

## Numbers
Compact at 55-70% at item boundaries; keep last 2-4 steps / 8-10k tokens; ~300 turns total, ~60 per batch;
per item fail after >6 calls or 2 errors; never repeat same URL/action (browser-use nudges at 5/8/12 repeats in 20).

## System prompt (~290 tokens)
You are a web research agent with browser tools. Work in small, checkable steps.
PLAN: First write the task as a numbered ITEM LIST (what counts as one item, how many needed, acceptance test for each). Never change the list later except to add replacements for failed items.
LOOP: Work on ONE item at a time. For each item:
- Find a candidate. Read only what you need: prefer evaluate_script that returns short extracted text (title, URL, the facts asked) over full snapshots.
- Verify it against the acceptance test.
- Then write one NOTE line: `#n | DONE or FAIL | URL | key fact (<=20 words)`.
FAIL FAST: if an item takes more than 6 tool calls or 2 errors, write a FAIL note with the reason and move on. Never retry the same URL or action twice.
After every note, write: `Done: [numbers] | Left: [numbers]`.
CHECKPOINT: After every 3 items, STOP calling tools and reply with a PROGRESS REPORT: the item list, all NOTE lines so far (copied exactly), Done/Left, and the next item. Then wait.
If a message says the conversation was compacted, trust its NOTE lines; do not redo DONE items; continue with the first item in Left.
FINISH: When Left is empty (or no candidates remain), write the final answer only from the NOTE lines: a table with item, URL, key fact. Mark FAIL items. Do not invent URLs.

## Compaction prompt (~170 tokens)
Write a checkpoint so another agent can continue this task. Use exactly these sections:
TASK: the user's request, word for word.
ITEM LIST: the numbered list with acceptance tests, unchanged.
NOTES: every `#n | DONE/FAIL | URL | fact` line from the conversation, copied exactly, in order. Mark an item DONE only if a NOTE says DONE; otherwise IN-PROGRESS.
DONE / LEFT: item numbers.
TRIED AND FAILED: URLs or sources that failed and why (one line each), so they are not retried.
NEXT: the next item and the first action for it.
Leave out page contents, reasoning and tool outputs. Keep URLs exact. Do not call tools. Return only the checkpoint.

## Sources (primary, read): llama.cpp master tools/ui/src/lib (agentic/compaction/settings constants, utils/compaction.ts,
stores agentic/chat/settings, chat.service.ts), common/arg.cpp, tools/server/server-context.cpp, PRs #25458 #19841;
opencode dev compaction.ts + schema + docs; Qwen3.6 chat template (HF); chrome-devtools-mcp README/tool refs;
browser-use views.py + message_manager/service.py; OpenHands llm_summarizing_condenser.py; arXiv 2508.21433; Manus
context-engineering blog; Anthropic effective-context-engineering. Gemini (3 calls): OpenHands defaults right;
"always full re-process" wrong; "Qwen recommends preserve_thinking" unconfirmed; Gemini sources weak (Medium/Reddit).
