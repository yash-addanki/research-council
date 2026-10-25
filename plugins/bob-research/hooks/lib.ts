import type { Run, Snapshot } from '../types'

export const STEP_LABELS: Record<string, string> = {
  brief: 'brief', scout: 'evidence', deep_submit: 'deep research', council: 'council drafts',
  citations: 'citation check', review: 'cross-review', chairman: 'chairman', act: 'Notion write', report: 'report',
}

export const ICON: Record<Run['status'], string> = { done: '✓', running: '●', blocked: '✗', stopped: '○' }

export function tokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

export function duration(s: number): string {
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.round(s / 60)}m`
  return `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`
}

export function stepLabel(run: Run): string {
  if (run.status === 'done') return 'done'
  const step = run.blocked?.step ?? run.current_step ?? ''
  return `${STEP_LABELS[step] ?? step} (${run.steps_done}/${run.steps_total})`
}

export function statusLine(snap: Snapshot): string {
  const running = snap.runs.find(r => r.status === 'running')
  if (running) return `Council: ${stepLabel(running)} · ${tokens(running.tokens.total)} tok`
  const blocked = snap.totals.blocked ? ` · ${snap.totals.blocked} blocked` : ''
  return `Council: idle · ${snap.totals.done}/${snap.totals.runs} done${blocked}`
}

/** Alerts for runs whose status changed since the last snapshot. */
export function transitions(before: Record<string, string>, snap: Snapshot): string[] {
  const out: string[] = []
  for (const r of snap.runs) {
    const was = before[r.run_id]
    if (was === r.status) continue
    if (r.status === 'done' && was) out.push(`Research done: ${r.title} (${tokens(r.tokens.total)} tokens)`)
    if (r.status === 'blocked') out.push(`Research blocked at ${r.blocked?.step}: ${r.title}`)
    if (r.status === 'running' && was !== undefined) out.push(`Research resumed: ${r.title}`)
    if (r.status === 'running' && was === undefined) out.push(`Research started: ${r.title}`)
  }
  return out
}

export function statusText(snap: Snapshot): string {
  if (!snap.runs.length) return 'No runs yet.'
  const lines = snap.runs.slice(0, 15).map(r =>
    `${ICON[r.status]} ${r.title} | ${stepLabel(r)} | ${tokens(r.tokens.total)} tok | ${duration(r.duration_s)} | ${r.run_id}`)
  const t = snap.totals
  return [`${t.runs} runs, ${t.done} done, ${t.running} running, ${t.blocked} blocked, ${tokens(t.tokens)} tokens`, ...lines].join('\n')
}

export const HELP = [
  '/bob_research                 open the dashboard',
  '/bob_research status          list runs here',
  '/bob_research next [--dry-run]       research the top "To Research" topic',
  '/bob_research run <notion-url> [--dry-run]',
  '/bob_research resume <run-id> [--dry-run]',
].join('\n')

export type Parsed =
  | { kind: 'dashboard' } | { kind: 'status' } | { kind: 'help'; error?: string }
  | { kind: 'launch'; argv: string[] }

export function parse(args: string): Parsed {
  const words = args.trim().split(/\s+/).filter(Boolean)
  const [sub, ...rest] = words
  const flags = rest.filter(w => w === '--dry-run')
  const pos = rest.filter(w => w !== '--dry-run')
  if (!sub || sub === 'dashboard') return { kind: 'dashboard' }
  if (sub === 'status') return { kind: 'status' }
  if (sub === 'next' && pos.length === 0) return { kind: 'launch', argv: ['next', ...flags] }
  if ((sub === 'run' || sub === 'resume') && pos.length === 1) return { kind: 'launch', argv: [sub, pos[0]!, ...flags] }
  if (sub === 'help') return { kind: 'help' }
  return { kind: 'help', error: `Didn't understand "${args.trim()}".` }
}
