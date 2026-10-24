# Research Council: design spec

Date: 2026-10-24 · Owner: Yash · Status: draft for review

## 1. Goal

Turn a one-line research topic in Notion into a high-quality, cited answer decided by a council of models (Claude, GPT via Codex, Gemini, optionally Muse and app-only Deep Research), with Claude writing the final synthesis. For build topics, go further: pick the best active GitHub repos, star, fork and clone them into `~/GitRepos`, then ask before coding starts.

Success looks like:
- A topic goes from "To Research" to "Resolved" with a report in its Notion page, without Yash copying or pasting anything.
- Every claim in the report has a checked source or is marked unverified.
- Each run reports tokens used per model.
- Runs use only existing ~$20 subscriptions (Claude Pro, ChatGPT plan via Codex, Google AI Pro, Muse) plus near-zero WhatsApp messaging cost. No paid LLM APIs, no paid crawlers.
- Yash approves anything consequential from WhatsApp.

## 2. Constraints and decisions (from the brainstorm)

| Topic | Decision |
|---|---|
| Topic types | Mix. The brief step classifies each as `build` (ends in repos + project) or `knowledge` (ends in report). |
| Models | Claude (`claude -p`), GPT (`codex exec`, ChatGPT login), Gemini (`gemini` CLI, Google AI Pro login). Muse, Gemini Deep Research and ChatGPT Deep Research only through the Chrome step. |
| Default depth | High. Depth comes from a new Notion `Depth` column, defaulting from Priority (High→High, Medium→Medium, Low→Low). |
| No manual paste | Chrome step (`claude --chrome`) drives the Gemini, ChatGPT and Muse web apps after a WhatsApp yes. |
| Trigger | `research next` command now; a launchd schedule (every 2 h) that checks idle + quota and asks first. |
| Approvals channel | WhatsApp: Yash's WhatsApp Business number (Cloud API) messages Yash's personal WhatsApp with Yes/No buttons. Used for every approval in this system. |
| Repos | Auto star, fork, clone. Only topic-relevant repos with a default-branch commit in the last 12 months (6 months preferred) and passing a usefulness check. Ask "ready to build?" before any coding. |
| Social sources | Every topic includes X, Reddit, HN, YouTube, GitHub issues and public forums. X/Reddit read through secondary accounts in a dedicated Chrome profile. |
| Tokens | Per-model token table in Notion and a one-line total on WhatsApp. |
| Model tiers | Cheap tier for scouting, mid tier for critique and citation check, top Claude tier only for the chairman. |
| Tools | Vetted allowlist auto-installs; anything new needs a WhatsApp yes. |
| Approach | A small Python conductor (plain code runs the steps; models only think). Rejected: Claude-as-orchestrator (burns Claude context/quota), GPT Researcher / LangGraph (need paid API keys), Notion Custom Agents (Business plan + credits). |

## 3. Run pipeline

Each step writes its output into `runs/<YYYY-MM-DD>-<slug>/` before the next step starts, so a crashed run resumes from the last completed step.

1. **Pick.** Query ResearchTopics for `Status = To Research`, order by Priority then created time. Take a lease in SQLite (`topic_id`, `lease_until`, `version`); set Notion Status to Researching and write Run ID. A topic with a live lease is never picked.
2. **Brief** (Claude, cheap tier). Input: title, Notes, Tags. Output `brief.json`: refined question, success criteria, `kind` (build|knowledge), 4–8 search angles, social queries, candidate repo search terms (build only).
3. **Scout** (parallel, cheap tier + tools). Web, Reddit, X, HN, YouTube transcripts, GitHub (repo search, issues), forums. Output `evidence.jsonl`: one item per source with `url`, `title`, `published_at`, `platform`, `excerpt`, `fetched_at`. Deduplicate by canonical URL. Hard cap on items per run (default 60) to bound tokens.
4. **Council** (parallel). Claude, GPT and Gemini each get the brief and evidence pack, may search further, and return `answer.<model>.json` with claims as a list: `{claim, source_urls[], confidence}` plus open questions. High depth: the Chrome step results (`deep.<app>.md`) are added as extra members' answers.
5. **Citation check** (mid tier, cheapest available model with spare quota). For each claim/source pair, fetch the page (Crawl4AI) and label `supported | partial | unsupported | unreachable`. Output `citations.json`.
6. **Early stop check.** If all members agree on the key conclusions and ≥90% of key claims are `supported`, skip step 7.
7. **Cross-review** (mid tier). Only disputed or unsupported claims go out. Members see them anonymised (A, B, C), argue for/against with sources, and vote. Output `review.json`. One round only (Medium/High).
8. **Chairman** (Claude top tier). Writes `report.md`: answer first, key findings with inline citations, where the council disagreed and why, unverified items, social sentiment summary, next steps. For build topics: ranked repo table.
9. **Act** (build topics only). For each chosen repo: re-verify recency via `gh api`, then `gh repo star`, `gh repo fork --clone=false`, `git clone` the fork into `~/GitRepos/<repo>`. WhatsApp "Ready to start building <topic> with <repos>? Yes/No". On yes, open a Claude Code session in the main repo with the report as context (out of scope for v1 beyond creating a `KICKOFF.md` with the plan).
10. **Report.** Write report into the Notion topic page (chunked to 2,000-char blocks), fill Tokens used and Report link, set Status Resolved. WhatsApp summary: one-line answer, link, total tokens.

### Depth matrix

| Step | Low | Medium | High |
|---|---|---|---|
| Scout | cheap, 30 sources | cheap, 45 sources | cheap, 60 sources |
| Council | 3 CLIs | 3 CLIs | 3 CLIs + Chrome Deep Research (Gemini, ChatGPT, Muse) |
| Citation check | key claims only | all claims | all claims |
| Cross-review | skipped | disputed claims | disputed claims |
| Chairman | Claude mid tier | Claude top tier | Claude top tier |

## 4. Components

All in the `research-council` repo (Python 3.12, `uv`), run on Yash's Mac.

| Unit | Does | Depends on |
|---|---|---|
| `cli.py` | `research next`, `research run <notion-url>`, `research status`, `research resume <run-id>`, `--dry-run` | conductor |
| `conductor.py` | Runs the pipeline steps in order, saves step outputs, resumes | everything below |
| `runners/{claude,codex,gemini}.py` | One function `run(prompt, tier, tools, timeout) -> Result(text, tokens_in, tokens_out, model, rate_limited)`. Uses each CLI's JSON output for tokens. Read-only sandbox flags during research. | the installed CLIs |
| `runners/chrome_deep.py` | `claude --chrome` script: open tabs, paste brief, start, later collect report text. Uses page text, not screenshots. | Claude in Chrome extension |
| `sources/` | Adapters: `agent_reach.py`, `last30days.py`, `hn.py`, `github.py`, `crawl.py` (Crawl4AI). Each returns evidence items. | those tools |
| `notion_client.py` | Read queue, update properties, write page blocks; throttled to ~2.5 req/s | Notion API token |
| `approvals.py` | `ask(question, timeout) -> yes/no/timeout` via WhatsApp; polls Supabase for replies | WhatsApp Cloud API, Supabase |
| `quota.py` | Idle check (no interactive claude/codex/gemini processes, Mac idle time) and quota check (per-model cooldown after rate-limit errors, rolling counts of our own calls, any limit info the CLIs expose) | SQLite |
| `state.py` | SQLite: leases, runs, steps, token usage, model cooldowns, approvals | — |
| `repos.py` | Repo scoring, recency check, star/fork/clone | `gh` CLI |
| `supabase/functions/wa-webhook` | Verifies Meta signature, stores button replies; `GET /pending` for the Mac (shared-secret auth) | Supabase free tier |
| `launchd/com.yash.research-council.plist` | Every 2 h: `research next --ask-first` | — |
| `prompts/` | Versioned prompt files per step | — |

Model tiers live in `config.toml` so names can change without code changes (e.g. cheap = Haiku / GPT mini / Gemini Flash; mid = Sonnet / GPT standard / Gemini Pro; top = Opus).

## 5. Notion changes

Add to ResearchTopics: `Depth` (select Low/Medium/High), `Run ID` (text), `Tokens used` (number), `Report` (URL to run folder or GitHub file), and Status option `Blocked`. Report body goes into the topic page itself.

## 6. Scheduled check (`--ask-first`)

1. Skip if any run is active, or the Mac is in use by Yash (interactive claude/codex/gemini processes, the Codex app or Google Antigravity running, or HID idle < 15 min). Antigravity and the Codex app may share the same subscription quotas.
2. Skip if any council model is in cooldown or its rolling call count is near its cap.
3. Pick the next topic, WhatsApp "Start research: <topic> (<depth>)? Yes / No". No reply in 30 min = no.
4. On yes, run. High-depth Chrome step asks a second question only if Chrome isn't open.

## 7. Errors and recovery

- Model rate-limited/timeout: continue without it, note in report, cooldown 3 h (configurable).
- Any step fails twice: Status `Blocked`, note reason in Notes, WhatsApp alert.
- Crash/sleep: lease expires (30 min heartbeat); `research resume` or the next scheduled run continues from the last saved step.
- Chrome step: login page or CAPTCHA pauses that tab and texts Yash; after 20 min it is dropped and the run continues.
- Per-run call caps per model; when hit, go straight to chairman with what exists.

## 8. Safety

- Research steps run CLIs in read-only/sandboxed modes; only `repos.py` writes, and only stars, forks and clones.
- Fetched web/social content is wrapped as untrusted data in prompts; it never changes the plan.
- Secrets in macOS Keychain (read via `security`), never in Notion, logs or the repo.
- X/Reddit only via a separate Chrome profile with secondary accounts.
- New tools/plugins: allowlist in `config.toml`; anything else needs a WhatsApp yes.

## 9. Tool allowlist (re-verified for activity at install time)

Agent-Reach (Yash's fork of Panniantong/Agent-Reach), mvanhorn/last30days-skill, unclecode/crawl4ai, `gh`, HN Algolia API, Claude in Chrome extension. Reference only: karpathy/llm-council (anonymised review), hamza-aziz-ai/codex-claude-council (Claude–Codex critique).

## 10. Testing

- Unit tests per step with fake runners and fixture evidence.
- Runner contract tests against real CLIs (one tiny prompt each) to lock JSON/token parsing.
- `--dry-run`: full pipeline, no Notion/GitHub/WhatsApp writes; prints what it would do.
- Acceptance: one real Low topic and one real High topic end to end; one forced model failure; one forced crash + resume; one "No" reply.

## 11. Open items to verify during the build

- Exact CLI flags for model choice, JSON output, web search and read-only mode in the installed versions of `claude`, `codex`, `gemini`.
- Whether any CLI exposes remaining quota; otherwise rely on cooldowns and our own call counts.
- Agent-Reach support for choosing a specific Chrome profile.
- WhatsApp Cloud API setup for the business number (coexistence) and template approval for the approval message.

## 12. Out of scope for v1

Evidence cache across topics, automatic coding after "ready to build?", ClickUp sync, model win-rate weighting.
