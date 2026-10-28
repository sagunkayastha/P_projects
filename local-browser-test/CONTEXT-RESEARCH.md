# Context handling for our local agents (llama.cpp + opencode + web UI)

Date: 2026-10-28. Research by an Opus subagent with Claude web search + Gemini (agy-box). Research only; nothing was changed on the PC.
Saved by Rem from the agent's reply (subagents cannot write report files). Source copies: /data/scratch/ctx-research/dl/.
Gemini: only queries 3 and 4 returned (gemini-3.md, gemini-4.md); 1, 2, 5 hit quota (429, resets in ~72 h).

## Key fact
Ornith-1.5-35B-A3B and Qwen3.6-35B-A3B are HYBRID models (Qwen3.6: 40 layers = 10 x (3 Gated DeltaNet -> 1 Gated Attention)).
Qwen3.8-27B probably too (not checked). Ornith = Qwen3.5-35B-A3B fine-tune (third-party source, vast.ai).
1. KV cache only ~1.3 GB at 128k q8_0 (~2.7 GB f16): big -c is cheap. (Gemini's 8-17 GB used a dense formula: wrong.)
2. Recurrent state cannot roll back: the server resumes only from the exact end of the last request or a saved context checkpoint;
   else full re-process ("forcing full prompt re-processing due to lack of cache data", visible at -lv 4). --cache-reuse does not help.
   Likely cause of today's 11-16k re-processing.
3. gpt-oss-20b (SWA) has the same checkpoint issue; --swa-full avoids it.

## Top 10, ranked by expected gain
1. Cut tool output at the source (LARGE). opencode "tool_output": {"max_lines":300,"max_bytes":8192} (default 2000 lines / 50 KiB,
   rest saved to a file). chrome-devtools-mcp: filePath for evaluate_script/take_snapshot, includeSnapshot false, verbose:false;
   lean-local prompt: return <=50 rows of JSON. (One measured snapshot 10,220 tokens vs 1,866 for a screenshot; single post.)
2. Diagnose misses first: -lv 4 --log-prompts-dir DIR; look for "restored context checkpoint" / "forcing full prompt re-processing";
   diff consecutive prompts; read timings.cache_n.
3. Denser context checkpoints (MEDIUM-LARGE): -cms 1024 (default 8192), -ctxcp 32-48, --cache-ram 8192 (~60-210 MiB each,
   32 x ~150 MiB = ~4.7 GB host RAM). PR #22929 (2026-05-25) adds a checkpoint before the latest user message. Evidence: issues +
   blogs; one user found a stable client prefix was the real fix. Test it.
4. preserve_thinking: --chat-template-kwargs '{"preserve_thinking":true}' or --reasoning-preserve; web UI: keep "Exclude reasoning
   from context" off. History stays append-only -> cache hits (Qwen3.6 card). Without it tool calls became {} after 2-3 turns
   (pi #3325). Context grows faster: pair with 5 and 6. Check Ornith's template supports it.
5. Cap thinking: --reasoning-budget 2048 --reasoning-budget-message "Enough thinking; act now." (tune 1024-4096). Do not switch
   thinking fully off without an A/B (JetBrains: Qwen3-32B 23% with vs 17% without; no browser data).
6. Keep -c 131072; give opencode less: limit.context ~65536 (compaction near 49k), "compaction":{"keep":{"tokens":8000}}
   (default 15000 = likely source of the 11-16k re-reads). Length degrades accuracy (Chroma context rot, Du et al. 2025).
7. Trim the MCP tool list: chrome-devtools-mcp --categoryPerformance=false --categoryNetwork=false --categoryDebugging=false
   --categoryEmulation=false --categoryMemory=false, or --slim (3 tools). Never change tools mid-session.
8. Stable prefix: no date / dir listing in the system prompt, no toggling MCP/model/mode mid-task. opencode puts the date in its
   system prompt (rollover = full re-process; PR #14203 on a mirror only). Web UI fine (date is a tool).
9. gpt-oss-20b: --swa-full (PR #15293).
10. Keep q8_0 KV + flash attention + layer split; never -sm row/tensor over the x1 link. Optional test -ub 1024 -b 2048 (weak).

## Per question (short)
Q1 caching: cache_prompt on by default, exact prefix; --cache-reuse shifts KV for full-attention models only (inference, #18497);
  checkpoints -ctxcp/-cms/--cache-ram; issue #24714 still shows full re-processing on Qwen3.5/3.6 in some patterns (closed stale).
  Slot save/restore only for a fixed prefix across restarts. Keep --context-shift off for agents. Cache breakers: compaction,
  dropped earlier thinking, date/env in system prompt, changed tool list/MCP, per-step masking, re-formatted tool-call JSON,
  model switch. Timing: 590 s / 44 steps -> output tokens are the main cost, then 9-13 s misses.
Q2 thinking: -rea on|off|auto, --reasoning-budget(-message), --reasoning-effort, --reasoning-format, --reasoning-preserve,
  --chat-template-kwargs; per request chat_template_kwargs {"enable_thinking":false}, reasoning_effort "none",
  /v1/chat/completions/control. Qwen3.6 thinks by default; /think /no_think not official. Off for simple steps/plain chat; on with
  a budget for planning. Check /props chat_template_caps.
Q3 tool output: JetBrains Complexity Trap (arXiv 2508.21433): masking observations older than 10 turns ~50% cheaper, matched or
  beat summarisation; summaries made runs ~15% longer. Masking rewrites old messages -> breaks prefix cache: mask in batches
  (opencode prune 20k/40k). browser-use rebuilds one state message per step (no old page dumps), compacts every 25 steps.
  OpenHands condenser max_size=240 keep_first=2. Snapshot = right default for text models but >10k on busy pages; small JSON from
  evaluate_script cheapest; screenshots need vision and should be dropped after use.
Q4 compaction/size: fewer, larger compactions with smaller kept tail; context shift bad for agents; on hybrids shrink the harness
  budget, not -c. No model-specific 32k/64k/128k numbers found.
Q5 KV: q8_0 near-lossless on Qwen 3.6; q4_0 KL ~0.09-0.12 (worse on Gemma); KV small on hybrids so q4 not worth it; keep -fa on;
  layer split right.
Q6 web UI (tools/ui constants): agentic loop on, max 100 turns; MCP timeout setting; built-in compaction keeps 10 steps;
  "Exclude reasoning" off by default; "Pre-fill KV cache after response" off (helps chat). MCP via browser (--ui-mcp-proxy) or
  server stdio (--mcp-servers-config, PR #26062, 30 s per call). No tool-approval or output-cap setting found.
Q7 RAG vs long context: RAG for a growing vault; long context only for a small fixed set (<=~30k) with a fixed prefix.
  Tools: llama-server --embeddings + Open WebUI knowledge, AnythingLLM, Khoj, Obsidian Smart Connections.

## Claude vs Gemini
Agreed: layer split over x1; q8_0 + FA; masking ~ summarisation; long-context degradation; snapshot/script over screenshot.
Gemini wrong: missed hybrid models (KV math, 32k/q4 advice, missed checkpoints); masking "preserves" cache (it breaks it);
-sm row default (it is layer); OpenHands max_size 10 (240); package @chromenav/... (it is chrome-devtools-mcp); snapshot 800-3,500
tokens (one measure 10,220); "always 32k" (no evidence).

## Sources
Checked: llama.cpp server README; web UI constants; PRs #22929, #15293, issue #24714; particula.tech blog; mykolaaleksandrov.dev
blog; Qwen3.6 HF card; pi #3325; opencode source + docs; chrome-devtools-mcp README/configuration.md/tool-reference.md;
browser-use views.py; OpenHands llm_summarizing_condenser.py; arXiv 2508.21433v3, 2510.05381v1.
Weak (snippets only): dev.to snapshot post, localbench, sanmai KV report, vast.ai Ornith page, Reddit mirrors, opencode PR #14203,
llama.cpp #18497 #22384 #22746 #20837.
Gemini links valid: arXiv 2404.06654 (RULER), 2502.05167 (NoLiMa), 2508.21433, trychroma context-rot, llama.cpp PR #5021,
docs/multi-gpu.md, mnismt repo. Dropped: "PR #8684" (unrelated), @chromenav package name.
