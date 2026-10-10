#!/usr/bin/env python3
"""Make a small made-up run in the DUCK format. Usage: make_sample_run.py OUT_DIR [--slow]
Two games. It lets you test every stage with no private data. The text is invented."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

START = datetime(2026, 1, 1, 10, 0, 0)
# (actions, kind, seconds): kind is ok | yield | timeout
GAMES = {
    'aa11-00000001': {'state': 'gave_up', 'levels': [[(2, 'ok', 60), (0, 'yield', 120), (3, 'ok', 40)],
                                                     [(0, 'yield', 150), (0, 'yield', 130), (4, 'ok', 50)],
                                                     [(0, 'yield', 300), (0, 'yield', 280), (0, 'timeout', 900)]], 'completed': 2},
    'cd22-00000002': {'state': 'won', 'levels': [[(1, 'ok', 30), (2, 'ok', 45)], [(3, 'ok', 60)]], 'completed': 2},
}
THINK = ["The board has a blue block at the top left. I will move it right and look at the result.",
         "The last move changed nothing. Let me list the objects again: blue block, red block, a gray wall. The goal may be to reach the red block.",
         "I tried LEFT and the block moved. So LEFT works. I will plan three moves: DOWN, DOWN, RIGHT, and check the board after each one."]


def clock(t):
    return (START + timedelta(seconds=t)).strftime('%H:%M:%S')


def make(out):
    out = Path(out); (out / 'transcripts').mkdir(parents=True, exist_ok=True)
    runs = []
    for gid, g in GAMES.items():
        t, action, hist, apl, lines, n_turn = 0.0, 1, [], [], [], 0
        for lvl in g['levels']:
            apl_n = 0
            for acts, kind, secs in lvl:
                n_turn += 1
                think = ' '.join(THINK[: 1 + n_turn % 3]) + f' (turn {n_turn})'
                status = {'ok': 'message: Step executed.', 'yield': 'message: Yielded control to solver: turn_time_budget.',
                          'timeout': 'request_error: ReadTimeout: read timeout=900.0'}[kind]
                lines += ['', f'--- analysis_step={n_turn} | action={action} | {clock(t)} | tool-agent ---', '[SYSTEM PROMPT]',
                          'You are a coding agent solving a grid puzzle.', '', '[USER PROMPT]', f'Current state: step {action}.', '',
                          '[MODEL RESPONSE META]', 'finish_reason: tool_calls', f'reasoning_chars: {len(think)}', '', '[THINKING]', think, '',
                          '[TOOL CALL: python]', '<tool_call>', 'print(current_frame.level)', '</tool_call>', '', '[TOOL RESULT: python]', 'level 1', '',
                          '[ANALYZER STATUS]', 'model: Test/Model', status, '']
                t += secs
                for _ in range(acts):
                    hist.append({'action': {'id': 'ACTION6', 'data': {'x': 1, 'y': 2}}, 'generated_tokens': 200,
                                 'uncached_input_tokens': 0, 'wallclock_seconds': t})
                action += acts; apl_n += acts
            apl.append(apl_n)
        (out / 'transcripts' / f'{gid}_p0.txt').write_text('\n'.join(lines) + '\n')
        runs.append({'game_id': gid, 'number_of_levels': len(g['levels']), 'base_actions_per_level': apl, 'hint': None, 'state': g['state'],
                     'history': hist, 'actions_per_level': apl, 'levels_completed': g['completed'], 'final_score': 1.0,
                     'final_wallclock_seconds': t, 'started_at': START.isoformat()})
    (out / 'benchmark.json').write_text(json.dumps({'label': 'sample', 'n_passes': 1, 'game_runs': runs}, indent=1))
    print(f'made {out}')


if __name__ == '__main__':
    make(sys.argv[1])
