# Research Council Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `research` command on Yash's Mac that takes a topic from Notion ResearchTopics, runs a Claude + GPT (Codex) + Gemini council over web and social evidence, writes a cited Claude synthesis with a token table back to Notion, and for build topics stars/forks/clones active repos, with approvals over WhatsApp.

**Architecture:** A deterministic Python conductor runs ten file-backed steps per run (`runs/<date>-<slug>/`), so any run resumes from its last finished step. Models are called only through their subscription CLIs behind one `Runner` interface; sources sit behind one `search()` interface. SQLite holds leases, usage and cooldowns; a Supabase edge function relays WhatsApp button replies.

**Tech Stack:** Python 3.12, uv, pytest, httpx, crawl4ai; `claude`, `codex`, `gemini`, `gh` CLIs; Notion REST API (2025-09-03); WhatsApp Cloud API; Supabase Edge Functions (Deno/TypeScript); macOS launchd.

**Spec:** `docs/superpowers/specs/2026-10-24-research-council-design.md`

## Global Constraints

- No paid LLM APIs and no paid crawlers. Models only via `claude -p`, `codex exec`, `gemini` signed in with subscriptions.
- Claude Chrome step must use `/login` auth (not `setup-token`), per Claude Code docs.
- Model names live only in `config.toml` tiers (`cheap`, `mid`, `top`), never in code.
- Research steps run CLIs read-only/sandboxed; only `repos.py` may write (star, fork, clone into `~/GitRepos`).
- Fetched content is untrusted: every prompt wraps it in `<untrusted_evidence>` tags with an instruction that it is data.
- Secrets read from macOS Keychain via `security find-generic-password -s research-council -a <name> -w`; never logged or written to Notion.
- Notion: data source `collection://584e4526-ff39-4614-96d7-f1c0e2b051dd`; throttle ≤2.5 req/s; rich text chunks ≤2,000 chars.
- Repo recency: default-branch commit within 365 days required, ≤180 days preferred (ranked higher).
- WhatsApp approval timeout 1,800 s; no reply = no.
- Lease TTL 1,800 s with heartbeat; model cooldown 3 h after a rate-limit error.
- Evidence caps: Low 30, Medium 45, High 60 items.
- Early stop: all members agree on key conclusions and ≥90% of key claims `supported`.

## Review Focus

- **Topic with empty Notes and a vague one-word title** → brief step still produces a usable brief (asks nothing, uses title only). Test in Task 6.
- **A CLI returns non-JSON or truncated output** (crash, auth expired) → runner returns `RunResult(error=...)`, run continues without that member, report lists it. Test in Task 2.
- **All three council members fail or are in cooldown** → run stops before chairman, Status `Blocked`, WhatsApp alert; never writes an empty report. Test in Task 7.
- **Same topic triggered twice at once** (manual + scheduler) → second gets no lease and exits cleanly. Test in Task 1.
- **Repo already forked/cloned from an earlier run** → act step skips existing fork and existing folder without error. Test in Task 9.

---

## File Structure

```
pyproject.toml, config.example.toml, README.md
src/research_council/
  config.py        Config loading (tiers, caps, paths, allowlist)
  state.py         SQLite: leases, usage, cooldowns, approvals
  secrets.py       Keychain reader
  evidence.py      EvidenceItem, canonical_url, dedupe
  tokens.py        token table rendering
  runners/base.py  RunResult, Runner protocol, FakeRunner
  runners/claude.py, codex.py, gemini.py
  runners/chrome_deep.py
  sources/hn.py, github.py, agent_reach.py, last30days.py, crawl.py
  steps/context.py RunContext
  steps/brief.py, scout.py, council.py, citations.py, review.py, chairman.py, act.py, report.py
  prompts/*.md     one prompt file per step
  conductor.py     step order, resume, failure policy
  notion.py        Notion client
  approvals.py     WhatsApp send + reply polling
  quota.py         idle + quota checks
  repos.py         candidate filtering, star/fork/clone
  cli.py           research next|run|status|resume, --dry-run, --ask-first
supabase/functions/wa-webhook/index.ts
launchd/com.yash.research-council.plist
tests/...          mirrors src; tests/fixtures/cli/*.json captured in Task 0
```

---

### Task 0: Spike — capture real CLI behaviour on the Mac (throwaway, no product code)

Run via Remote Control on the Mac in `~/GitRepos/research-council`.

- [ ] **Step 1:** Record versions: `claude --version; codex --version; gemini --version; gh --version`. Install missing: `npm i -g @openai/codex @google/gemini-cli`; `codex login`; `gemini` (sign in with Google AI Pro account).
- [ ] **Step 2:** For each CLI run one tiny prompt ("Reply with the word OK") with JSON output and a chosen model; save raw stdout to `tests/fixtures/cli/{claude,codex,gemini}_ok.json(l)`. Candidate commands: `claude -p "..." --output-format json --model <m>`; `codex exec --json -m <m> --sandbox read-only "..."`; `gemini -p "..." -m <m> --output-format json`.
- [ ] **Step 3:** Confirm per CLI: flag for web search, flag for read-only, JSON path of answer text and token counts, exit code and output on auth failure (`*_autherr.json`), and whether any command reports remaining quota. Write findings to `docs/cli-notes.md`.
- [ ] **Step 4:** Confirm `agent-reach channels` output and how it selects a Chrome profile; confirm last30days invocation from `claude -p`. Append to `docs/cli-notes.md`.
- [ ] **Step 5:** Commit `docs/cli-notes.md` and fixtures: `git commit -m "docs: capture CLI contracts"`.

### Task 1: Project skeleton, config, state

**Files:** Create `pyproject.toml`, `config.example.toml`, `src/research_council/{config,state,secrets}.py`. Test `tests/test_config.py`, `tests/test_state.py`.

**Interfaces — Produces:**
- `load_config(path: Path) -> Config`; `Config.tiers: dict[str, dict[str, str]]` (model→tier→name), `Config.caps: dict[str, int]` (`evidence_low/medium/high`, `calls_per_model_per_run`), `Config.paths.runs_dir`, `Config.paths.gitrepos`, `Config.notion_data_source_id`, `Config.allowlist: list[str]`.
- `State(db_path: Path)` with `acquire_lease(topic_id: str, now: float, ttl_s=1800) -> int | None`, `heartbeat(topic_id, version, now) -> bool`, `release(topic_id, version)`, `record_usage(run_id, step, model, tokens_in, tokens_out)`, `usage_for_run(run_id) -> list[UsageRow]`, `set_cooldown(model, until: float)`, `in_cooldown(model, now) -> bool`, `calls_since(model, since: float) -> int`.
- `get_secret(name: str) -> str` (raises `MissingSecret`).

- [ ] **Step 1: Tests:** `test_load_config_reads_tiers` (`cfg.tiers["claude"]["top"]` equals value in fixture toml); `test_second_lease_denied_while_live` (first returns 1, second returns None); `test_lease_reacquired_after_ttl` (now+1801 → returns 2); `test_stale_version_heartbeat_fails`; `test_cooldown_expires`; `test_usage_rows_roundtrip`.
- [ ] **Step 2:** `uv run pytest tests/test_config.py tests/test_state.py -v` → FAIL (import errors).
- [ ] **Step 3:** Implement with `tomllib` and `sqlite3`; lease acquire is a single `INSERT ... ON CONFLICT DO UPDATE ... WHERE lease_until < :now` then read version.
- [ ] **Step 4:** Tests PASS.
- [ ] **Step 5:** Commit `feat: config, sqlite state, keychain secrets`.

### Task 2: Runners (Claude, Codex, Gemini)

**Files:** `runners/base.py`, `runners/claude.py`, `runners/codex.py`, `runners/gemini.py`; tests `tests/runners/test_*.py` using Task 0 fixtures.

**Interfaces — Produces:**
- `@dataclass RunResult(text: str, tokens_in: int, tokens_out: int, model: str, rate_limited: bool = False, error: str | None = None)`; `ok` property = `error is None`.
- `class Runner(Protocol): name: str; def run(self, prompt: str, tier: str, *, web: bool = False, timeout_s: int = 900) -> RunResult`.
- `FakeRunner(name, responses: list[RunResult])` for all later tests.
- Each real runner: `build_argv(prompt, model, web) -> list[str]` and `parse(stdout: str, returncode: int) -> RunResult` (pure, tested), plus `run()` using `subprocess.run(..., timeout=timeout_s)`.

- [ ] **Step 1: Tests per CLI:** `test_parse_ok_fixture` (text contains "OK", tokens_in>0, tokens_out>0); `test_parse_autherr_fixture` (error set, ok False); `test_parse_garbage_returns_error` (stdout `"<html>"` → error, no exception); `test_rate_limit_detected` (fixture/message containing the CLI's limit wording from `docs/cli-notes.md` → `rate_limited=True`); `test_build_argv_readonly_flag_present`; `test_timeout_returns_error` (monkeypatched `subprocess.run` raising `TimeoutExpired`).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement using JSON paths recorded in `docs/cli-notes.md`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: subscription CLI runners with token parsing`.

### Task 3: Evidence model and sources

**Files:** `evidence.py`, `sources/{hn,github,agent_reach,last30days,crawl}.py`; tests `tests/test_evidence.py`, `tests/sources/test_*.py` (recorded HTTP/subprocess fixtures, no network).

**Interfaces — Produces:**
- `@dataclass EvidenceItem(url, title, platform, excerpt, published_at: str | None, fetched_at: str)`; `canonical_url(url) -> str` (lowercase host, strip `utm_*`, fragments, trailing slash); `dedupe(items) -> list[EvidenceItem]` (keeps first by canonical URL).
- Each source module: `search(query: str, limit: int) -> list[EvidenceItem]`; source failures return `[]` and log, never raise.
- `crawl.fetch_text(url: str, max_chars: int = 20000) -> str | None`.
- `hn` uses `https://hn.algolia.com/api/v1/search?query=...&tags=story`; `github` uses `gh search repos <q> --json fullName,stargazersCount,pushedAt,description,url --limit N`; `agent_reach` and `last30days` use commands from `docs/cli-notes.md` (last30days via `ClaudeRunner` cheap tier).

- [ ] **Step 1: Tests:** `test_canonical_url_strips_tracking` (`https://Example.com/a/?utm_source=x#h` → `https://example.com/a`); `test_dedupe_keeps_first`; per source `test_search_parses_fixture` (count and first url); `test_search_failure_returns_empty` (subprocess non-zero / HTTP 500 → `[]`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: evidence model and source adapters`.

### Task 4: Notion client

**Files:** `notion.py`; test `tests/test_notion.py` (httpx `MockTransport`).

**Interfaces — Produces:**
- `@dataclass Topic(page_id, title, notes, priority, tags: list[str], depth: str)`; depth = `Depth` property or derived from Priority (High→High, Medium→Medium, Low/empty→Low).
- `NotionClient(token, data_source_id, rate_per_s=2.5)`: `next_topic() -> Topic | None` (Status = To Research, sort Priority High>Medium>Low then created_time asc), `set_status(page_id, status: str)`, `set_props(page_id, *, run_id=None, tokens_used=None, report_url=None, notes_append=None)`, `append_markdown(page_id, md: str)`.
- `chunk_text(s: str, limit=2000) -> list[str]` (splits on paragraph, then hard-splits).
- `ensure_schema()` adds Depth, Run ID, Tokens used, Report, and Status option Blocked if missing.

- [ ] **Step 1: Tests:** `test_next_topic_orders_by_priority`; `test_depth_defaults_from_priority`; `test_chunk_text_never_exceeds_limit` (5,000-char single paragraph → all chunks ≤2000, joined equals input); `test_429_retries_after_header` (first 429 `Retry-After: 1`, then 200 → one retry); `test_ensure_schema_idempotent` (second call sends no PATCH).
- [ ] **Step 2–4:** FAIL → implement with httpx, `Notion-Version: 2025-09-03` → PASS.
- [ ] **Step 5:** Commit `feat: notion client`.

### Task 5: Prompts and run context

**Files:** `steps/context.py`, `prompts/{brief,scout,council,citation,review,chairman}.md`; test `tests/test_prompts.py`.

**Interfaces — Produces:**
- `@dataclass RunContext(run_id, run_dir: Path, topic: Topic, depth: str, runners: dict[str, Runner], state: State, cfg: Config, dry_run: bool)`; `ctx.call(runner_name, prompt, tier, step, web=False) -> RunResult` records usage, sets 3 h cooldown when `rate_limited`, and refuses (returns error result) once `calls_per_model_per_run` is reached or model is in cooldown.
- `render(name: str, **vars) -> str` loads `prompts/<name>.md`; evidence always inserted inside `<untrusted_evidence>...</untrusted_evidence>`.
- Each prompt asks for strict JSON matching the step's schema (below) and nothing else.

- [ ] **Step 1: Tests:** `test_render_wraps_evidence_untrusted`; `test_call_records_usage`; `test_call_sets_cooldown_on_rate_limit`; `test_call_refuses_after_cap`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat: run context and prompts`.

### Task 6: Research steps (brief → chairman)

**Files:** `steps/{brief,scout,council,citations,review,chairman}.py`; tests `tests/steps/test_*.py` with `FakeRunner`.

Every step: `run(ctx: RunContext) -> Path`, reads earlier step files from `ctx.run_dir`, writes its own file, returns its path.

| Step | Writes | Schema / rule |
|---|---|---|
| brief | `brief.json` | `{question, success_criteria[], kind: "build"|"knowledge", angles[4..8], social_queries[], repo_queries[]}`; Claude cheap |
| scout | `evidence.jsonl` | angles → web search via cheap runners with `web=True`; social_queries → agent_reach (reddit, twitter, youtube), last30days, hn; repo_queries → github; `dedupe`; cap by depth |
| council | `answer.<model>.json` | `{claims:[{id, claim, source_urls[], confidence}], conclusion, open_questions[]}`; Claude/Codex/Gemini mid tier, `web=True`, run in a `ThreadPoolExecutor(3)`; High also loads `deep.*.md` if present |
| citations | `citations.json` | per (claim, url): `supported|partial|unsupported|unreachable`; `fetch_text` then cheapest runner not in cooldown; Low checks only claims with confidence ≥0.7 |
| review | `review.json` | `should_skip_review(answers, citations) -> bool` per Global Constraints; else only disputed/unsupported claims, members labelled A/B/C (shuffled), one round; Low always skips |
| chairman | `report.md` | Claude `top` (Low: `mid`); sections: Answer, Key findings (inline citations), Where the council disagreed, Unverified, What people are saying (social), Repos (build only), Next steps |

- [ ] **Step 1: Tests:** `test_brief_with_empty_notes_and_one_word_title` (Review Focus); `test_scout_caps_by_depth` (High → ≤60 items from 100 fake); `test_scout_survives_source_failure`; `test_council_continues_when_one_member_errors` (2 answers written, `missing.json` lists the third); `test_should_skip_review_true_when_agree_and_90pct`; `test_review_sends_only_disputed_claims` (prompt passed to fake contains disputed claim id, not agreed one); `test_review_anonymises_members` (prompt contains no "claude"/"codex"/"gemini"); `test_chairman_marks_unverified` (claim with only `unsupported` sources appears under Unverified).
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat: council research steps`.

### Task 7: Conductor, report step, token table, CLI (milestone: usable manually)

**Files:** `conductor.py`, `steps/report.py`, `tokens.py`, `cli.py`; tests `tests/test_conductor.py`, `tests/test_tokens.py`, `tests/test_cli.py`.

**Interfaces — Produces:**
- `STEPS = ["brief", "scout", "deep_submit", "council", "citations", "review", "chairman", "act", "report"]` (`deep_submit` and `act` are no-ops until Tasks 9 and 11).
- `run_pipeline(ctx) -> Path`: skips a step whose output file exists; heartbeats lease between steps; a step raising twice → `Blocked`; fewer than 1 successful council answer → `Blocked` before chairman.
- `token_table(rows: list[UsageRow]) -> str` markdown with columns Model, Step count, Tokens in, Tokens out, Total; final row Total; app-run members shown as "app run, not metered".
- `report.run(ctx)`: Notion `append_markdown(report.md + token table)`, `set_props(run_id, tokens_used, report_url)`, `set_status("Resolved")`; in dry run prints instead.
- CLI: `research next [--dry-run] [--ask-first]`, `research run <notion-page-url> [--dry-run]`, `research status`, `research resume <run-id>`.

- [ ] **Step 1: Tests:** `test_resume_skips_completed_steps` (pre-created `brief.json` → brief runner not called); `test_all_members_failed_blocks_before_chairman` (Review Focus; chairman fake never called; status Blocked); `test_step_failing_twice_blocks`; `test_token_table_totals`; `test_dry_run_makes_no_notion_writes`; `test_cli_next_exits_when_no_lease` (Review Focus duplicate trigger).
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Live check on Mac (Remote Control):** `uv run research run <a Low topic URL> --dry-run` then without `--dry-run`; expect Notion page has report + token table, Status Resolved.
- [ ] **Step 6:** Commit `feat: conductor, report and research CLI`.

### Task 8: WhatsApp approvals + Supabase relay

**Files:** `approvals.py`, `supabase/functions/wa-webhook/index.ts`, `docs/whatsapp-setup.md`; tests `tests/test_approvals.py`, `supabase/functions/wa-webhook/index.test.ts`.

**Interfaces — Produces:**
- Edge function: `GET` verify (`hub.mode=subscribe`, `hub.verify_token`), `POST` verifies `X-Hub-Signature-256` HMAC of raw body with app secret, stores `{approval_id, answer, received_at}` from interactive `button_reply.id` (`<approval_id>:yes|no`) into table `approvals`; `GET /pending?since=` with `Authorization: Bearer <relay secret>` returns rows.
- `WhatsApp(cfg)`: `ask(question: str, timeout_s=1800, poll_s=20) -> Literal["yes","no","timeout"]` sends an interactive button message (template `research_approval` when outside 24 h window), polls relay; `notify(text: str)`.
- `docs/whatsapp-setup.md`: Meta app + business number (coexistence), template `research_approval` submission, Keychain entries `wa_token`, `wa_phone_id`, `wa_to`, `relay_url`, `relay_secret`.

- [ ] **Step 1: Tests:** `test_ask_returns_yes_on_matching_reply`; `test_ask_ignores_other_approval_ids`; `test_ask_timeout_is_no_reply` (returns "timeout"); Deno: `rejects bad signature (401)`, `stores button reply`, `pending requires bearer`.
- [ ] **Step 2–4:** FAIL → implement → PASS (`deno test`, `uv run pytest`).
- [ ] **Step 5:** Deploy with Supabase MCP `deploy_edge_function`; apply migration for `approvals` table. Yash completes Meta setup per doc; live test: `uv run python -m research_council.approvals --test` → tap Yes on phone → prints `yes`.
- [ ] **Step 6:** Commit `feat: whatsapp approvals via supabase relay`.

### Task 9: Repo act step

**Files:** `repos.py`, `steps/act.py`; tests `tests/test_repos.py`.

**Interfaces — Produces:**
- `@dataclass RepoCandidate(full_name, url, stars: int, pushed_at: datetime, description: str, relevance: float)` (relevance from chairman's repo table).
- `filter_and_rank(cands, now, max_age_days=365, prefer_days=180, top_n=3) -> list[RepoCandidate]`: drop older than 365 d or relevance < 0.6; rank by (pushed within 180 d, relevance, stars).
- `act_on(cands, gitrepos: Path, dry_run) -> list[Path]`: `gh repo star`, `gh repo fork <repo> --clone=false` (skip if `gh repo view yash-addanki/<name>` exists), `git clone <fork> <gitrepos>/<name>` (skip if folder exists); writes `KICKOFF.md` into the first clone with the report link; then `WhatsApp.ask("Ready to start building <topic> with <repos>?")` and records answer in `act.json`.
- `steps/act.py`: no-op when `brief.kind == "knowledge"`.

- [ ] **Step 1: Tests:** `test_filter_drops_older_than_365_days`; `test_filter_prefers_recent_over_stars`; `test_act_skips_existing_fork_and_folder` (Review Focus); `test_knowledge_topic_skips_act`; `test_dry_run_runs_no_gh_commands`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit `feat: star, fork and clone chosen repos`.

### Task 10: Quota/idle check and scheduler

**Files:** `quota.py`, `launchd/com.yash.research-council.plist`, `cli.py` (`--ask-first`); tests `tests/test_quota.py`.

**Interfaces — Produces:**
- `user_busy(process_names: list[str], hid_idle_s: float) -> bool`: True if idle < 900 s or any of `claude` (interactive, i.e. without `-p`), `codex` (without `exec`), `gemini` (without `-p`), `Codex`, `Antigravity` running.
- `hid_idle_seconds() -> float` from `ioreg -c IOHIDSystem` `HIDIdleTime` / 1e9; `list_processes() -> list[str]` from `ps -axo command`.
- `models_available(state, models, now, cap) -> list[str]`: not in cooldown and `calls_since(model, now-5h) < cap`.
- `research next --ask-first`: exit if busy or fewer than 2 models available; else `ask("Start research: <title> (<depth>)?")`; run only on "yes".
- plist runs `research next --ask-first` every 7,200 s, logs to `~/Library/Logs/research-council.log`.

- [ ] **Step 1: Tests:** `test_busy_when_recent_input`; `test_busy_when_antigravity_open`; `test_not_busy_for_headless_claude_p`; `test_models_available_excludes_cooldown`; `test_ask_first_no_reply_does_not_run`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** On Mac: `launchctl bootstrap gui/$(id -u) launchd/com.yash.research-council.plist`; `launchctl print gui/$(id -u)/com.yash.research-council` shows loaded.
- [ ] **Step 6:** Commit `feat: idle and quota aware scheduler`.

### Task 11: Chrome Deep Research step (High only)

**Files:** `runners/chrome_deep.py`, `prompts/chrome_submit.md`, `prompts/chrome_collect.md`; tests `tests/runners/test_chrome_deep.py`.

**Interfaces — Produces:**
- `submit(ctx) -> Path` (step `deep_submit`): only when depth High; `ask("Send '<title>' to Gemini/ChatGPT Deep Research and Muse?")`; on yes runs `claude -p --chrome` (cheap tier) with `chrome_submit.md`: open gemini.google.com Deep Research, chatgpt.com Deep Research, meta.ai Muse in new tabs, paste brief, start (click Gemini's "Start research"), return JSON `{app: tab_url | "blocked: <reason>"}` → `deep_submit.json`. Use page text tools, no screenshots.
- `collect(ctx) -> list[Path]` called by council when `deep_submit.json` exists: waits until 30 min after submit (max 60), runs `chrome_collect.md` to read each tab's finished report text → `deep.<app>.md`; unfinished/blocked apps are listed in `missing.json`; usage recorded as "app run, not metered" for the apps and normal tokens for the Claude driver.

- [ ] **Step 1: Tests:** `test_submit_skipped_below_high`; `test_submit_skipped_on_no`; `test_collect_blocked_app_goes_to_missing`; `test_argv_includes_chrome_flag`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Live High run on Mac with Chrome open; expect three `deep.*.md` files or explicit `missing.json` entries.
- [ ] **Step 6:** Commit `feat: chrome deep research handoff`.

### Task 12: Tool setup and acceptance

**Files:** `README.md`, `scripts/setup.sh`.

- [ ] **Step 1:** `scripts/setup.sh`: checks/installs allowlisted tools only (`uv`, `gh`, codex CLI, gemini CLI, `crawl4ai-setup`, Agent-Reach from `~/GitRepos/Agent-Reach`, last30days skill); before each install re-checks repo activity via `gh api repos/<r> --jq .pushed_at` (≤365 d). Anything not on `config.allowlist` triggers `WhatsApp.ask("Install <tool> (<repo>, <stars>★, last commit <date>)?")`; on yes it is installed and appended to the allowlist, otherwise skipped.
- [ ] **Step 2:** Yash creates the secondary X/Reddit Chrome profile; run `agent-reach` login for that profile.
- [ ] **Step 3:** Acceptance on Mac: one real Low topic end to end; one real High topic end to end; forced failure (`codex` logged out) → report lists missing member; kill mid-run then `research resume <id>` → completes without repeating finished steps; reply No to an ask → nothing runs.
- [ ] **Step 4:** Commit `docs: setup and acceptance` and open PR.
