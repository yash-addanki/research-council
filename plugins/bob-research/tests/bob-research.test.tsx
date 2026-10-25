import { expect, test } from 'claude-code/testing'

import type { Snapshot } from '../types'

const SNAP: Snapshot = {
  generated_at: 2000,
  totals: { runs: 1, done: 0, running: 1, blocked: 0, tokens: 12_500 },
  quota: { claude: { calls_5h: 3, cooldown: false }, codex: { calls_5h: 1, cooldown: false, used_percent: 40 },
           gemini: { calls_5h: 0, cooldown: true } },
  runs: [{
    run_id: 'r1', title: 'Optimise the council', page_id: 'p1', priority: 'High', depth: 'Low', tags: ['ai'],
    status: 'running', current_step: 'council', steps_done: 3, steps_total: 9, blocked: null,
    started_at: 1000, updated_at: 1600, duration_s: 600, evidence_items: 14, citations: {},
    answers: ['claude'], deep_apps: [],
    tokens: { total: 12_500, by_model: { claude: { calls: 2, tokens_in: 10_000, tokens_out: 2_500 } },
              by_step: { council: 12_500 } },
    report: null,
  }],
}

const PANE = {
  plugin: 'bob-research', component: 'Pane', requestId: 'bob-research',
  props: { title: 'Research Council', isFocused: false, bodyColumns: 60, placement: 'dock',
           scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

const cmd = (args: string) => ({
  command: 'bob_research', args, origin: { kind: 'composer' as const },
  presentation: { isFullscreen: false, columns: 100 },
})

function engine(on: any, argvs: string[][]) {
  on('command.register', () => ({ value: { command: 'bob_research' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    argvs.push(e.argv)
    const isLaunch = e.argv[2]?.includes('nohup')
    return { value: { exitCode: 0, stdout: isLaunch ? '4242\n' : JSON.stringify(SNAP), stderr: '' } }
  })
}

test('the dashboard lists topics and opens one with its token usage', async ($, on) => {
  engine(on, [])
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.command.run(cmd('status'))

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect((await ui.find({ type: 'Text', text: /1 topics/ }))?.text).toBe('1 topics · 0 done · 1 running · 0 blocked')
    await ui.press({ key: 'run:r1' })
    expect((await ui.find({ type: 'Text', text: /^Tokens/ }))?.text).toBe('Tokens: 12.5k')
    expect(await ui.find({ type: 'Text', text: /claude: 2 calls · 10.0k in · 2.5k out/ })).toBeDefined()
    await ui.press({ key: 'back' })
    await ui.unmount()
  }
})

test('/bob_research run launches the CLI in the background', async ($, on) => {
  const argvs: string[][] = []
  engine(on, argvs)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const out = await $.command.run(cmd('run https://notion.so/x --dry-run'))
  expect(out.text).toContain('pid 4242')
  const launch = argvs.find(a => a[2]?.includes('nohup'))!
  expect(launch.slice(3)).toEqual(['sh', '~/GitRepos/research-council', 'run', 'https://notion.so/x', '--dry-run'])
})

test('unknown arguments get the help text', async ($, on) => {
  engine(on, [])
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const out = await $.command.run(cmd('frobnicate'))
  expect(out.text).toContain("Didn't understand")
  expect(out.text).toContain('/bob_research next')
})
