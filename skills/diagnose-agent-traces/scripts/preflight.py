"""Stage 0: preflight. Checks that a run can be analysed. Exit code 1 if any check FAILS.
Usage: python3 preflight.py --run RUN_DIR [--out OUT_DIR] [--min-text-share 0.5]
Checks per game: transcript found; turn headers parse; action index consistent with benchmark;
no annotation-cut marker in the transcript (harness tool-output cuts are only counted); reasoning text present (visibility)."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from lib import clock_to_seconds, find_transcript, load_benchmark, parse_turns


def check_game(run, game, B, min_text_share):
    res = {'game': game, 'fail': [], 'warn': []}
    path, n = find_transcript(run, game)
    if path is None:
        res['fail'].append(f'transcript: found {n} files for {game}-*_p0.txt, expected 1')
        return res
    turns = parse_turns(path)
    res['turns'] = len(turns)
    if not turns:
        res['fail'].append('transcript: no turn headers')
        return res
    hist, apl = B['history'], B['actions_per_level']
    if sum(apl) != len(hist):
        res['fail'].append(f'benchmark: sum(actions_per_level)={sum(apl)} but len(history)={len(hist)}')
    acts = [t['action_hdr'] for t in turns]
    if any(b < a for a, b in zip(acts, acts[1:])):
        res['fail'].append('transcript: action index goes down')
    if max(acts) > len(hist) + 1:
        res['fail'].append(f'transcript: action index {max(acts)} is beyond history ({len(hist)} actions)')
    start = datetime.fromisoformat(B['started_at'])
    first = clock_to_seconds(turns[0]['clock'], start)
    if abs(first) > 120:
        res['warn'].append(f'first turn starts {first:.0f} s after started_at')
    cut = sum(t['truncation_markers'] for t in turns)
    res['truncation_markers'] = cut
    res['harness_tool_output_cuts'] = sum(t['harness_tool_output_cuts'] for t in turns)
    if cut:
        res['fail'].append(f'text: {cut} annotation-cut markers in the transcript')
    rep = sum(t['reasoning_chars_reported'] for t in turns)
    txt = sum(t['thinking_chars_in_text'] for t in turns)
    with_text = sum(1 for t in turns if t['thinking_chars_in_text'] > 0)
    res.update(reasoning_chars_reported=rep, thinking_chars_in_text=txt, turns_with_text=with_text,
               text_share=round(txt / rep, 3) if rep else None)
    if rep and txt / rep < min_text_share:
        res['fail'].append(f'text: only {txt / rep:.0%} of the reported reasoning characters are in the transcript')
    elif rep == 0:
        res['warn'].append('text: no reasoning characters reported')
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--run', required=True, help='run directory with benchmark.json and transcripts/')
    ap.add_argument('--out', help='write preflight.json here')
    ap.add_argument('--min-text-share', type=float, default=0.5,
                    help='FAIL if THINKING text / reported reasoning chars is below this (default 0.5)')
    a = ap.parse_args(argv)
    run = Path(a.run)
    if not (run / 'benchmark.json').exists():
        print(f'FAIL: {run}/benchmark.json not found'); return 1
    bench = load_benchmark(run)
    rows = [check_game(run, g, B, a.min_text_share) for g, B in sorted(bench.items())]
    nfail = sum(bool(r['fail']) for r in rows)
    print(f'{"game":6} {"turns":>5} {"text/reported":>14} {"cut":>4} {"tool-cut":>8}  status')
    for r in rows:
        st = 'FAIL' if r['fail'] else ('WARN' if r['warn'] else 'ok')
        ts = f"{r['text_share']:.2f}" if r.get('text_share') is not None else 'n/a'
        print(f"{r['game']:6} {r.get('turns', 0):>5} {ts:>14} {r.get('truncation_markers', 0):>4} {r.get('harness_tool_output_cuts', 0):>8}  {st}")
        for m in r['fail'] + r['warn']:
            print(f'         - {m}')
    print(f'{len(rows)} games, {nfail} with FAIL')
    if a.out:
        Path(a.out).mkdir(parents=True, exist_ok=True)
        (Path(a.out) / 'preflight.json').write_text(json.dumps({'run': str(run), 'games': rows, 'failed': nfail}, indent=1))
    return 1 if nfail else 0


if __name__ == '__main__':
    sys.exit(main())
