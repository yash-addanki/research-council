# CLI notes (captured 2026-10-24 on Yash's Mac)

Fixtures live in `tests/fixtures/cli/`; exit codes are in `exit_codes.txt`.

## Versions

| Tool   | Version | Notes |
|--------|---------|-------|
| claude | 2.1.126 (Claude Code) | `~/.local/bin/claude`, subscription auth |
| codex  | codex-cli 0.164.0 | installed today via `npm i -g @openai/codex`; already logged in ("Logged in using ChatGPT", plan_type `promax`) |
| gemini | 0.65.0 | installed today via `npm i -g @google/gemini-cli`; **not authenticated yet** |
| gh     | 2.101.0 | |
| uv     | 0.13.5 | installed 2026-10-24 with the standalone installer (astral.sh) into `~/.local/bin` |
| node   | v26.3.1 (npm 11.16.0) | |
| python3 | 3.9.6 (system) | too old for Agent-Reach (requires >=3.10) |

General: always pass `</dev/null` as stdin. Both claude and codex otherwise wait/warn about stdin
(claude: "no stdin data received in 3s"; codex: "Reading additional input from stdin...").

---

## Claude Code

**OK prompt (works, exit 0):**
```
claude -p "Reply with the single word OK" --output-format json --model haiku </dev/null
```
**Web search (works, exit 0):**
```
claude -p "<prompt>" --output-format json --model haiku --allowedTools WebSearch </dev/null
```

Output: a single JSON object.
- Answer text: `.result`
- Success/failure: `.is_error` (bool), `.subtype` ("success"), `.api_error_status` (null on success), `.terminal_reason`
- Tokens (last API iteration only): `.usage.input_tokens`, `.usage.output_tokens`, `.usage.cache_read_input_tokens`, `.usage.cache_creation_input_tokens`
- **Tokens (whole run, per model; use this):** `.modelUsage["<model-id>"].inputTokens / outputTokens / cacheReadInputTokens / cacheCreationInputTokens / webSearchRequests / costUSD`
- Cost: `.total_cost_usd` (notional on subscription)
- Gotcha: in the web run `.usage.server_tool_use.web_search_requests` was **0** while `.modelUsage.*.webSearchRequests` was **1** (2 turns). `.usage` only reflects the final turn.
- `haiku` resolved to `claude-haiku-4-5-20251001`.

Read-only / sandbox: no sandbox flag. Restrict tools with `--tools "WebSearch,WebFetch"` (or `--tools ""` for none) and/or `--permission-mode plan`. In `-p` mode, any tool not in `--allowedTools` is denied and appears in `.permission_denials`.
Web search flag: `--allowedTools WebSearch` (add `WebFetch` to read pages).
Effort: `--effort low|medium|high|xhigh|max`.

Models (aliases): cheap `haiku`, mid `sonnet`, top `opus`. Full IDs also accepted.

Usage/quota: `claude -p "/usage" --output-format json` returns immediately (0 tokens) with only
`.result = "You are currently using your subscription to power your Claude Code usage"`. **No remaining-quota numbers in headless mode.** (Fixture `claude_usage_cmd.json`.)

Rate-limit / auth error shape: not observed. Expected (unverified): `.is_error=true`, `.api_error_status=429` (or 401) and a message in `.result`. Detect by `is_error` + `api_error_status`.

---

## Codex CLI

**OK prompt (works, exit 0):**
```
codex exec --json --sandbox read-only --skip-git-repo-check --ephemeral \
  -m gpt-6-luna -c model_reasoning_effort='"low"' "Reply with the single word OK" </dev/null
```
**Web search (works, exit 0):** web search is enabled via config *inside* exec:
```
codex exec --json --sandbox read-only --skip-git-repo-check --ephemeral \
  -c web_search='"live"' -m gpt-6-luna -c model_reasoning_effort='"low"' "<prompt>" </dev/null
```
- `codex exec --search ...` → **error**: `--search` is a top-level flag only.
- `codex --search exec ...` → parses, but every request got **401 Unauthorized** against `api.openai.com/v1/responses` (5 WebSocket retries, then HTTPS fallback, then 5 more retries), exit 1. Fixture `codex_web_toplevel_search_401.jsonl`. Don't use it.

Output: JSONL event stream (`--json`).
- Answer text: the last line with `.type=="item.completed"` and `.item.type=="agent_message"` → `.item.text`
  (alternative: `-o <file>` / `--output-last-message <file>` writes only the final message)
- Tokens: line with `.type=="turn.completed"` → `.usage.input_tokens`, `.usage.cached_input_tokens`, `.usage.output_tokens`, `.usage.reasoning_output_tokens`
- Web searches: `.item.type=="web_search"` items, with `.item.action.query` and `.item.results[]` (`title`, `url`, `snippet`, `domain`)
- Failure: `.type=="turn.failed"` → `.error.message` (a JSON string with status/code); also `.type=="error"` lines (retries)
- Non-fatal warnings show up as `item.completed` with `.item.type=="error"`
- Exit code 1 on turn failure, 2 on CLI arg error.

Read-only flag: `--sandbox read-only` (other values: workspace-write, danger-full-access). `--ephemeral` keeps sessions off disk. `--skip-git-repo-check` lets it run outside a repo. `--output-schema <file>` forces a JSON-shaped final answer (useful for the council).

Models (from `~/.codex/models_cache.json`, ChatGPT account; `codex debug models` dumps the raw catalog):
- cheap: `gpt-6-luna` ("Fast and affordable"); older `gpt-5.6-luna`
- mid: `gpt-6.1-sol` (config default, "Latest workhorse"); also `gpt-6-sol`, `gpt-5.6-terra`
- top: `gpt-6-astra` ("Frontier intelligence")
- Effort: `-c model_reasoning_effort='"low|medium|high|xhigh|max|ultra"'` (luna tops out at max)
- `gpt-5.4-mini` is rejected: HTTP 400 `model_not_found`, "The 'gpt-5.4-mini' model is not supported when using Codex with a ChatGPT account." (fixture `codex_model_error.jsonl`)

Usage/quota: **not in `exec --json` output.** It is written to non-ephemeral session rollouts under
`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` as events with `.type=="event_msg"`, `.payload.type=="token_count"`, containing `.payload.rate_limits`:
```
{"limit_id":"codex","primary":{"used_percent":56.0,"window_minutes":10080,"resets_at":1793383647},
 "secondary":null,"credits":{"has_credits":true,"unlimited":false,"balance":"..."},
 "plan_type":"promax","rate_limit_reached_type":null,"spend_control_reached":null}
```
To track quota, drop `--ephemeral` and read the newest rollout's last `token_count` event (match on thread_id from `thread.started`).
Rate-limit hit: expect `rate_limit_reached_type` non-null and a `turn.failed` (likely HTTP 429, `usage_limit_reached`; unverified).
Auth failure shape (observed with top-level --search): `turn.failed.error.message = "unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, url: ..."`.

---

## Gemini CLI

**Status: not authenticated.** Yash must run `gemini` once interactively and choose "Login with Google" (Google AI Pro account).
After that, rerun:
```
gemini -p "Reply with the single word OK" --output-format json -m gemini-2.5-flash </dev/null
gemini -p "Search the web: ..." --output-format json -m gemini-2.5-flash </dev/null   # google_web_search is built-in
```

Observed auth error (exit **41**, on **stderr**, stdout empty; fixture `gemini_auth_error.json`):
```
{"session_id":"...","error":{"type":"Error","message":"Please set an Auth method in your ~/.gemini/settings.json or specify one of the following environment variables before running: GEMINI_API_KEY, GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_GENAI_USE_GCA","code":41}}
```
→ In JSON mode errors go to stderr. Parse stderr when stdout is empty.

Output (from the 0.65 bundle and docs; verify after login): one JSON object
- Answer text: `.response`
- Tokens: `.stats.models["<model>"].tokens.{input,prompt,candidates,total,cached,thoughts,tool}` (input = promptTokenCount, candidates = output)
- Tool calls (web search): `.stats.tools` (totalCalls, byName.google_web_search)
- Error: `.error.{type,message,code}`

Read-only flag: `--approval-mode plan` (read-only mode). `-s/--sandbox` is a container sandbox. Avoid `-y/--yolo`.
Web search flag: none needed. `google_web_search` is a built-in tool. Restricting tools now goes through `--policy` (`--allowed-tools` is deprecated).
Also `-o stream-json` for an event stream.

Models (constants in bundle): cheap `gemini-2.5-flash-lite` / `gemini-2.5-flash` (bundle also references `gemini-3-flash-preview`, `gemini-3.5-flash`, `gemini-3.1-flash-lite`); mid `gemini-2.5-flash` / `gemini-3-flash-preview`; top `gemini-2.5-pro` (DEFAULT_GEMINI_MODEL) or `gemini-3-pro-preview` / `gemini-3.1-pro-preview`. Auto routers: `auto-gemini-2.5`, `auto-gemini-3`. Confirm which ones the AI Pro account can use with `/model` after login.
Usage/quota: interactive `/stats` only. Headless JSON has per-run `.stats` but no remaining quota. Quota errors surface as `RESOURCE_EXHAUSTED` / HTTP 429 (string present in bundle; shape unverified).

---

## Agent-Reach (`~/GitRepos/Agent-Reach`, v1.6.0, commit beabda7)

- **Installed** 2026-10-24: `uv tool install --python 3.12 ~/GitRepos/Agent-Reach` (from the local checkout; uv fetched Python 3.12, so system 3.9 doesn't matter). `agent-reach version` → `{"version":"1.6.0","install_method":"uv"}`. Official install path is `uv tool install https://github.com/Panniantong/Agent-Reach/releases/latest/download/agent-reach.zip`. Don't use the PyPI package named `agent-reach`; it's a different project.
- `agent-reach channels` (fixture `agent_reach_channels.json`) returns JSON `{schema_version, ok, commands, channels[]}`, where each channel has `{name, description, level, login, actions[{name, usage, params, backends, public_web}]}`:
  - default: github (search/read via gh or github-api), youtube (read/search/subtitle via yt-dlp, transcribe via whisper), v2ex, bilibili, web (search via exa, read via jina/exa)
  - optional (need login): reddit, linkedin (jobs/read), xiaohongshu, boss, xueqiu; xiaoyuzhou (groq-whisper)
  - experimental (need login): twitter, facebook, instagram
  - Every login-based channel uses the `opencli` backend.
- `agent-reach doctor` (no network): github and youtube are "unverified" (ready; check with `agent-reach check <ch>`), bilibili is "needs_setup", and the rest are "not_added" (`agent-reach add <ch>` installs Node + OpenCLI).
- `agent-reach browser profiles` currently → `NEED_SETUP: Run agent-reach add CHANNEL to install Node and OpenCLI`.
- Output envelope for management commands: `{schema_version, ok, action, result, error{code,message,hint}}`.
- **Chrome profile:** there is no flag that takes a Chrome profile *path*. The model is:
  - One Reach-owned headless browser profile at `~/.agent-reach/browser/profile` (`--user-data-dir`), shared by all channels.
  - Logins can be reused from your real browser via the **OpenCLI Browser Bridge** extension: `agent-reach browser profiles` lists the connected browser profiles (contextIds where the extension is connected), and `agent-reach browser use <ID>` pins one as the cookie source (`local_browser_source` in state). Cookies are copied per site, only for the requested site. If several profiles have cookies for a site, it raises NEED_SETUP and asks you to choose.
  - So to target a specific Chrome profile: install the OpenCLI extension in that profile, then `browser profiles` → `browser use <ID>`.

## last30days skill

Not installed: not in `~/.claude/skills` and not in the installed plugins (only superpowers, engineering, productivity). Nothing in `~/.codex/skills` either.

## andrej-karpathy-skills

`~/GitRepos/andrej-karpathy-skills` already existed as an empty, never-checked-out git dir (no fetch refspec). I added the refspec, fetched, and checked out `main` at 2c60614 ("Sync Chinese README with English version…"). Contents: CLAUDE.md, CURSOR.md, EXAMPLES.md, README.md, README.zh.md, skills/.
