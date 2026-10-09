"""Stage 1: counted time metrics. No model call.
Usage: python3 metrics.py --run RUN_DIR --out OUT_DIR [--base BASE_DIR] [--time-limit-s 7920]
A turn is one transcript record. Its duration is the start of the next record minus its start
(last record: run start + final_wallclock_seconds). Header `action=A` is the 1-based index of the next
action, so the actions in a turn = A(next) - A(this). Category of a turn:
  request_timeout (read timeout), action_turn, no_action_turn_budget_yield, final_stop_requested, no_action_other."""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from lib import clock_to_seconds, find_transcript, load_benchmark, parse_turns

CATS = ['action_turn', 'no_action_turn_budget_yield', 'request_timeout', 'final_stop_requested', 'no_action_other']


def analyse_game(run, game, B):
    path, _ = find_transcript(run, game)
    turns = parse_turns(path)
    start = datetime.fromisoformat(B['started_at'])
    end_s = B['final_wallclock_seconds']
    hist, apl = B['history'], B['actions_per_level']
    bounds, c = [], 0
    for a in apl:
        c += a; bounds.append(c)

    def level_of(idx):
        for i, bnd in enumerate(bounds):
            if idx <= bnd and apl[i] > 0:
                return i + 1
        return B['levels_completed'] + 1

    for i, r in enumerate(turns):
        t0 = clock_to_seconds(r['clock'], start)
        t1 = clock_to_seconds(turns[i + 1]['clock'], start) if i + 1 < len(turns) else end_s
        n_act = (turns[i + 1]['action_hdr'] - r['action_hdr']) if i + 1 < len(turns) else len(hist) + 1 - r['action_hdr']
        if r['request_error']:
            cat = 'request_timeout'
        elif n_act > 0:
            cat = 'action_turn'
        elif r['message'] and 'turn_time_budget' in r['message']:
            cat = 'no_action_turn_budget_yield'
        elif r['message'] and 'stop_requested' in r['message']:
            cat = 'final_stop_requested'
        else:
            cat = 'no_action_other'
        r.update(game=game, t_start=t0, duration_s=t1 - t0, actions=n_act, category=cat, level=level_of(r['action_hdr']))
    cats = {}
    for r in turns:
        d = cats.setdefault(r['category'], {'turns': 0, 'seconds': 0.0, 'actions': 0})
        d['turns'] += 1; d['seconds'] += r['duration_s']; d['actions'] += r['actions']
    levels, prev = [], 0.0
    for i, bnd in enumerate(bounds):
        if apl[i] == 0:
            continue
        t_end = hist[bnd - 1]['wallclock_seconds']
        levels.append({'level': i + 1, 'actions': apl[i], 'wall_s': round(t_end - prev, 1),
                       's_per_action': round((t_end - prev) / apl[i], 1), 'cleared': (i + 1) <= B['levels_completed']})
        prev = t_end
    tokens = sum(h.get('generated_tokens') or 0 for h in hist)
    summary = {'state': B['state'], 'levels_completed': B['levels_completed'], 'n_levels': B['number_of_levels'],
               'final_wallclock_s': round(end_s, 1), 'actions': len(hist), 'turns': len(turns),
               'categories': {k: {'turns': v['turns'], 'seconds': round(v['seconds'], 1), 'share': round(v['seconds'] / end_s, 3),
                                  'actions': v['actions']} for k, v in sorted(cats.items())},
               'generated_tokens': tokens, 'generated_tokens_per_wall_s': round(tokens / end_s, 2),
               'tail_after_last_action_s': round(end_s - (hist[-1]['wallclock_seconds'] if hist else 0), 1),
               'read_timeouts': [{'level': r['level'], 'read_timeout_s': r['read_timeout_s'],
                                  'turn_duration_s': round(r['duration_s'], 1)} for r in turns if r['request_error']],
               'per_level': levels, 'actions_per_level': apl}
    return summary, turns


def analyse_run(run, limit):
    bench = load_benchmark(run)
    games, rows = {}, []
    for g in sorted(bench):
        s, t = analyse_game(run, g, bench[g])
        s['hit_time_limit'] = s['final_wallclock_s'] >= 0.95 * limit
        games[g] = s; rows += t
    total = sum(s['final_wallclock_s'] for s in games.values())
    agg = {}
    for s in games.values():
        for k, v in s['categories'].items():
            d = agg.setdefault(k, {'turns': 0, 'seconds': 0.0}); d['turns'] += v['turns']; d['seconds'] += v['seconds']
    agg = {k: {'turns': v['turns'], 'seconds': round(v['seconds']), 'share': round(v['seconds'] / total, 3)} for k, v in agg.items()}
    return {'games': games, 'total_wall_s': round(total), 'categories': agg}, rows


def paired(run_games, base_games):
    """Levels that both runs cleared with a known action count (benchmark levels_completed is authoritative)."""
    out = []
    for g in sorted(set(run_games) & set(base_games)):
        a, b = run_games[g], base_games[g]
        for lv in range(1, min(a['levels_completed'], b['levels_completed']) + 1):
            x, y = a['actions_per_level'][lv - 1], b['actions_per_level'][lv - 1]
            if x and y:
                out.append({'game': g, 'level': lv, 'run_actions': x, 'base_actions': y, 'delta': x - y})
    return out


def pct(x):
    return f'{x:.1%}'


def render(res, base_res, pairs, limit, run, base):
    L = [f'# Stage 1: counted time metrics', '', f'Run: `{run}`' + (f'  Base: `{base}`' if base else ''), '',
         f'Games: {len(res["games"])}. Wall-clock: {res["total_wall_s"]:,} s. Time limit used for the flag: {limit} s.', '',
         '## Where the time goes', '', '| Category | Turns | Seconds | Share |' + (' Base turns | Base seconds | Base share |' if base_res else ''),
         '|---|---|---|---|' + ('---|---|---|' if base_res else '')]
    for k in CATS:
        a = res['categories'].get(k, {'turns': 0, 'seconds': 0, 'share': 0})
        row = f'| {k} | {a["turns"]} | {a["seconds"]:,} | {pct(a["share"])} |'
        if base_res:
            b = base_res['categories'].get(k, {'turns': 0, 'seconds': 0, 'share': 0})
            row += f' {b["turns"]} | {b["seconds"]:,} | {pct(b["share"])} |'
        L.append(row)
    L += ['', 'No-action time = budget yields + read timeouts + other no-action turns.', '',
          '## Games that used the time limit', '', '| Game | Levels | Wall s | Action turns s | Yield s | Timeout s | Tail s |', '|---|---|---|---|---|---|---|']
    for g, s in res['games'].items():
        if s['hit_time_limit']:
            c = s['categories']; sec = lambda k: c.get(k, {'seconds': 0})['seconds']
            L.append(f'| {g} | {s["levels_completed"]}/{s["n_levels"]} | {s["final_wallclock_s"]:,} | {sec("action_turn"):,} | '
                     f'{sec("no_action_turn_budget_yield"):,} | {sec("request_timeout"):,} | {s["tail_after_last_action_s"]:,} |')
    L += ['', '## All games', '', '| Game | State | Levels | Wall s | No-action share | Yields | Timeouts | Tokens/s |', '|---|---|---|---|---|---|---|---|']
    for g, s in res['games'].items():
        c = s['categories']; na = sum(c.get(k, {'seconds': 0})['seconds'] for k in CATS if k != 'action_turn')
        L.append(f'| {g} | {s["state"]} | {s["levels_completed"]}/{s["n_levels"]} | {s["final_wallclock_s"]:,} | '
                 f'{pct(na / s["final_wallclock_s"])} | {c.get("no_action_turn_budget_yield", {"turns": 0})["turns"]} | '
                 f'{c.get("request_timeout", {"turns": 0})["turns"]} | {s["generated_tokens_per_wall_s"]} |')
    if pairs is not None:
        n = len(pairs); tr = sum(p['run_actions'] for p in pairs); tb = sum(p['base_actions'] for p in pairs)
        L += ['', '## Paired levels (both runs cleared the level)', '',
              f'- Paired levels: {n}. Run actions: {tr}. Base actions: {tb}. Net: {tr - tb:+d}.',
              f'- Levels where the run used fewer or equal actions: {sum(p["delta"] <= 0 for p in pairs)}.',
              f'- Games only in one run: run-only {sorted(set(res["games"]) - set(base_res["games"]))}, '
              f'base-only {sorted(set(base_res["games"]) - set(res["games"]))}.', '',
              '| Game | Paired levels | Run actions | Base actions | Net |', '|---|---|---|---|---|']
        for g in sorted({p['game'] for p in pairs}):
            ps = [p for p in pairs if p['game'] == g]
            x = sum(p['run_actions'] for p in ps); y = sum(p['base_actions'] for p in ps)
            L.append(f'| {g} | {len(ps)} | {x} | {y} | {x - y:+d} |')
    return '\n'.join(L) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--run', required=True); ap.add_argument('--base'); ap.add_argument('--out', required=True)
    ap.add_argument('--time-limit-s', type=float, default=7920.0, help='per-game time limit (default 7920)')
    a = ap.parse_args(argv)
    res, rows = analyse_run(a.run, a.time_limit_s)
    base_res = pairs = None
    if a.base:
        base_res, _ = analyse_run(a.base, a.time_limit_s)
        pairs = paired(res['games'], base_res['games'])
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / 'metrics.json').write_text(json.dumps({'run': res, 'base': base_res, 'paired': pairs}, indent=1))
    cols = ['game', 'level', 'analysis_step', 'action_hdr', 'clock', 't_start', 'duration_s', 'actions', 'category',
            'model_responses', 'tool_calls', 'reasoning_chars_reported', 'message', 'request_error', 'read_timeout_s']
    with open(out / 'turns.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    md = render(res, base_res, pairs, a.time_limit_s, a.run, a.base)
    (out / 'STAGE1.md').write_text(md)
    print(md)


if __name__ == '__main__':
    main()
