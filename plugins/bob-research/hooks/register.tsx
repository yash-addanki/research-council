import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Board, Run, Snapshot } from '../types'
import { HELP, ICON, STEP_LABELS, duration, parse, statusLine, statusText, stepLabel, tokens, transitions } from './lib'

const PANE = 'bob-research'
// Bump the tag when Board's fields change: it declines what an older version stored.
const board = atom({ plugin: 'bob-research', key: 'board' } as const, { snapshot: null, error: null } as Board, {
  shape: 'board-1',
})
const selected = atom({ plugin: 'bob-research', key: 'selected' } as const, null as string | null, {
  shape: 'selected-1',
})

// Runs `uv run research <args>` in the repo. `~/` is expanded by the shell; args are never interpolated.
const PRELUDE = [
  'r=$1; shift',
  'case $r in "~/"*) r="$HOME/${r#"~/"}";; esac',
  'export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"',
  'cd "$r" || { echo "research-council folder not found: $r" >&2; exit 3; }',
].join('\n')
const RUN = `${PRELUDE}\nexec uv run --quiet research "$@"`
const LAUNCH = `${PRELUDE}\nnohup uv run --quiet research "$@" >> .bob-research.log 2>&1 < /dev/null &\necho $!`

let repo = '~/GitRepos/research-council'
let last: Record<string, string> | null = null

async function refresh($: EngineInterface): Promise<Snapshot | null> {
  try {
    const res = await $.process.run(['sh', '-c', RUN, 'sh', repo, 'dashboard'], { timeoutMs: 60_000 })
    if (res.exitCode !== 0) throw new Error(res.stderr.trim().split('\n').pop() || `exit ${res.exitCode}`)
    const snap = JSON.parse(res.stdout) as Snapshot
    await update($, board, () => ({ snapshot: snap, error: null }))
    $.ui.status(statusLine(snap))
    if (last) for (const text of transitions(last, snap)) {
      $.ui.toast(text)
      if (/done|blocked/.test(text)) void $.ui.notify(text, { title: 'Research Council' })
    }
    last = Object.fromEntries(snap.runs.map(r => [r.run_id, r.status]))
    return snap
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err)
    await update($, board, b => ({ ...b, error }))
    $.ui.status('Council: dashboard unavailable')
    return null
  }
}

export const register: Register = (on, options) => {
  repo = String(options.repo ?? repo)
  const refreshMs = Math.max(5, Number(options.refreshSeconds ?? 20)) * 1000

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'bob_research', description: 'Research Council: dashboard, next, run, resume, status' })
    void refresh($)
    $.clock.every(refreshMs, () => void refresh($))
    return next(e)
  })

  on('command.run', { command: 'bob_research' }, async ($, e) => {
    const cmd = parse(e.args)
    if (cmd.kind === 'help') return { text: [cmd.error, HELP].filter(Boolean).join('\n') }
    if (cmd.kind === 'dashboard') {
      await $.ui.open({ id: PANE, title: 'Research Council' })
      void refresh($)
      return { text: 'Research Council dashboard opened.' }
    }
    if (cmd.kind === 'status') {
      const snap = await refresh($)
      return { text: snap ? statusText(snap) : `Couldn't read runs: ${(await read($, board)).error}` }
    }
    const res = await $.process.run(['sh', '-c', LAUNCH, 'sh', repo, ...cmd.argv], { timeoutMs: 15_000 })
    if (res.exitCode !== 0) return { text: `Couldn't start research: ${res.stderr.trim()}` }
    await $.ui.open({ id: PANE, title: 'Research Council' })
    $.clock.after(5_000, () => void refresh($))
    return { text: `Started research ${cmd.argv.join(' ')} (pid ${res.stdout.trim()}). Log: ${repo}/.bob-research.log` }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const { snapshot: snap, error } = await read($, board)
    const pick = await read($, selected)
    const run = snap?.runs.find(r => r.run_id === pick)

    if (!snap) {
      return (
        <Box flexDirection="column">
          <Text dimColor>{error ? `Couldn't read runs: ${error}` : 'Loading runs…'}</Text>
          <Button key="refresh" label="Refresh" onPress={() => void refresh($)} />
        </Box>
      )
    }

    if (run) return detail(run)

    const t = snap.totals
    const q = snap.quota
    const quota = Object.entries(q)
      .map(([m, v]) => `${m} ${v.cooldown ? 'cooldown' : `${v.calls_5h} calls/5h`}${v.used_percent != null ? ` ${Math.round(v.used_percent)}%` : ''}`)
      .join(' · ')
    return (
      <Box flexDirection="column" gap={1}>
        <Box flexDirection="column">
          <Text bold>{t.runs} topics · {t.done} done · {t.running} running · {t.blocked} blocked</Text>
          <Text>{tokens(t.tokens)} tokens in total</Text>
          <Text dimColor>Quota: {quota}</Text>
          {error && <Text color="warning">Last refresh failed: {error}</Text>}
        </Box>
        <Box flexDirection="column">
          {snap.runs.length === 0 && <Text dimColor>No runs yet. Try /bob_research next --dry-run</Text>}
          {snap.runs.map(r => (
            <Button key={`run:${r.run_id}`} label={`${ICON[r.status]} ${r.title} · ${stepLabel(r)} · ${tokens(r.tokens.total)} tok`}
              onPress={() => void update($, selected, () => r.run_id)} />
          ))}
        </Box>
        <Button key="refresh" label="Refresh" onPress={() => void refresh($)} />
      </Box>
    )

    function detail(run: Run) {
      const models = Object.entries(run.tokens.by_model)
      const steps = Object.entries(run.tokens.by_step)
      const cites = Object.entries(run.citations).map(([k, v]) => `${v} ${k}`).join(', ') || 'none yet'
      return (
        <Box flexDirection="column" gap={1}>
          <Button key="back" label="← All topics" onPress={() => void update($, selected, () => null)} />
          <Box flexDirection="column">
            <Text bold>{run.title}</Text>
            <Text color={run.status === 'blocked' ? 'error' : run.status === 'done' ? 'success' : 'text'}>
              {ICON[run.status]} {run.status} · {stepLabel(run)}
            </Text>
            <Text dimColor>
              Priority {run.priority ?? '–'} · Depth {run.depth ?? '–'}{run.tags.length ? ` · ${run.tags.join(', ')}` : ''}
            </Text>
            <Text dimColor>Started {new Date(run.started_at * 1000).toLocaleString()} · {duration(run.duration_s)}</Text>
            {run.blocked && <Text color="error">Blocked at {run.blocked.step}: {run.blocked.reason}</Text>}
          </Box>
          <Box flexDirection="column">
            <Text bold>Evidence and answers</Text>
            <Text>{run.evidence_items} evidence items · citations: {cites}</Text>
            <Text>Council answers: {run.answers.join(', ') || 'none yet'}</Text>
            {run.deep_apps.length > 0 && <Text>Deep Research apps: {run.deep_apps.join(', ')}</Text>}
          </Box>
          <Box flexDirection="column">
            <Text bold>Tokens: {tokens(run.tokens.total)}</Text>
            {models.length === 0 && <Text dimColor>No model calls yet.</Text>}
            {models.map(([m, u]) => (
              <Text>{m}: {u.calls} calls · {tokens(u.tokens_in)} in · {tokens(u.tokens_out)} out</Text>
            ))}
            {steps.map(([s, n]) => (
              <Text dimColor>  {STEP_LABELS[s] ?? s}: {tokens(n)}</Text>
            ))}
          </Box>
          {run.report && <Text dimColor>Report: {run.report}</Text>}
          <Text dimColor>Run id: {run.run_id}</Text>
        </Box>
      )
    }
  })
}
