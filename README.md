# research-council

Turns a topic in the Notion **Bob / ResearchTopics** database into a cited report decided by a council of models (Claude, GPT via Codex, Gemini, plus Gemini/ChatGPT Deep Research and Muse through Chrome on High depth). Claude writes the final synthesis. Build topics also star, fork and clone the best active repos into `~/GitRepos` and ask before coding starts.

It only uses the subscription CLIs you already pay for (`claude`, `codex`, and `agy`, the Antigravity CLI, for Gemini). No paid APIs. Design: `docs/superpowers/specs/2026-10-24-research-council-design.md`.

## Commands

```sh
uv run research next              # research the top "To Research" topic
uv run research next --dry-run    # same, but no Notion/GitHub/WhatsApp writes
uv run research next --ask-first  # what the 2-hourly schedule runs: idle + quota check, WhatsApp yes/no
uv run research run <notion-url>  # one specific topic
uv run research resume <run-id>   # continue a stopped run from its last finished step
uv run research status            # recent runs
uv run research setup             # install the allowlisted tools
uv run research install <name> <owner/repo> --check "<cmd>" -- <install cmd...>
                                  # a new tool: asks on WhatsApp unless the repo is allowlisted
```

Each run writes its steps to `runs/<date>-<slug>/` (`brief.json`, `evidence.jsonl`, `answer.*.json`, `deep.*.md`, `citations.json`, `review.json`, `report.md`, `final_report.md` with the token table), and the final report goes into the Notion page.

## One-time setup (Yash)

Run `scripts/setup.sh` from this folder; it creates `config.toml`, installs the tools and lists what is still missing. The steps only you can do:

1. **Notion token.** Create an internal integration at notion.so/profile/integrations, share the ResearchTopics database with it (••• → Connections), then
   `security add-generic-password -s research-council -a notion_token -w '<secret>'`
2. **Gemini via Antigravity.** Google retired Gemini CLI sign-in for AI Pro accounts, so the Gemini member runs on `agy`: `curl -fsSL https://antigravity.google/cli/install.sh | bash`, then run `agy` once and sign in with your AI Pro Google account. (Done on the Mac 2026-10-25.)
3. **Claude in Chrome** (High depth only). Install the Claude in Chrome extension, run `claude` then `/login` (not `setup-token`), and stay signed in to gemini.google.com, chatgpt.com and Muse in that Chrome.
4. **WhatsApp approvals.** Follow `docs/whatsapp-setup.md` (Meta app, templates, Keychain entries). It needs a free Supabase project for the webhook relay; tell Claude when it's OK to create one.
5. **Social sources.** Make a separate Chrome profile signed in to your secondary X and Reddit accounts, then `agent-reach add twitter` and `agent-reach add reddit` from that profile.
6. **Schedule.** `scripts/setup.sh --schedule` loads the every-2-hours check (logs: `~/Library/Logs/research-council.log`).

## Safety

- Research steps run the CLIs read-only (`--tools ""` or web tools only for Claude, `--sandbox read-only` for Codex, `--approval-mode plan` for Gemini). Only the act step writes, and only stars, forks and clones.
- Web and social text is passed to models inside `<untrusted_evidence>` and never changes the plan.
- Secrets live in the macOS Keychain under service `research-council`.
- Tools outside `allowlist` in `config.toml` need a WhatsApp yes before install.

## Development

```sh
uv run pytest -q
node --experimental-strip-types --test supabase/functions/wa-webhook/handler.test.ts
```

Agent rules for Claude, Codex and Gemini are in `CLAUDE.md`, `AGENTS.md` and `GEMINI.md` (includes the Karpathy coding guidelines).
