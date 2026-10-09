"""Stages 0 and 1 in one command. Stage 1 runs only if stage 0 passes.
Usage: python3 stage01.py --run RUN_DIR [--base BASE_DIR] --out OUT_DIR [--time-limit-s 7920]
Writes OUT_DIR/preflight.json, metrics.json, turns.csv, STAGE1.md. Exit 1 if stage 0 fails."""
import argparse
import sys

import metrics
import preflight


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--run', required=True); ap.add_argument('--base'); ap.add_argument('--out', required=True)
    ap.add_argument('--time-limit-s', default='7920')
    a = ap.parse_args()
    for d in [a.run] + ([a.base] if a.base else []):
        print(f'== stage 0: {d}')
        if preflight.main(['--run', d, '--out', a.out + ('/base' if d == a.base else '')]) != 0:
            print('Stage 0 failed. Stage 1 did not run.'); return 1
    print('== stage 1')
    args = ['--run', a.run, '--out', a.out, '--time-limit-s', a.time_limit_s] + (['--base', a.base] if a.base else [])
    metrics.main(args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
