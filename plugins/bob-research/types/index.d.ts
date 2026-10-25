export type ModelTokens = { calls: number; tokens_in: number; tokens_out: number }

export type RunStatus = 'done' | 'running' | 'blocked' | 'stopped'

export type Run = {
  run_id: string
  title: string
  page_id: string
  priority: string | null
  depth: string | null
  tags: string[]
  status: RunStatus
  current_step: string | null
  steps_done: number
  steps_total: number
  blocked: { step: string; reason: string; at: number } | null
  started_at: number
  updated_at: number
  duration_s: number
  evidence_items: number
  citations: Record<string, number>
  answers: string[]
  deep_apps: string[]
  tokens: { total: number; by_model: Record<string, ModelTokens>; by_step: Record<string, number> }
  report: string | null
}

export type Snapshot = {
  generated_at: number
  totals: { runs: number; done: number; running: number; blocked: number; tokens: number }
  quota: Record<string, { calls_5h: number; cooldown: boolean; used_percent?: number | null }>
  runs: Run[]
}

export type Board = { snapshot: Snapshot | null; error: string | null }

declare module 'claude-code' {
  interface PluginState {
    'bob-research': { board: Shaped<Board>; selected: Shaped<string | null> }
  }
}
