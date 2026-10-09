"""Build the paper's vector figures into overleaf/figures/.

    python3 tools/figures/build.py              # all paper figures
    python3 tools/figures/build.py sharing      # only the named ones
    python3 tools/figures/build.py --out /tmp/x # somewhere else, for previews
    python3 tools/figures/build.py --deck       # the report deck's three figures, into tools/deck/figures/

Each figure is written twice: <name>.pdf for the English paper and
<name>-zh.pdf for the bilingual build.
"""
import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402

FIGURES = {'running-example': 'example', 'architecture': 'architecture', 'replay-outcomes': 'replay_outcomes',
           'maintenance-cost': 'maintenance_cost', 'scenario-changes': 'scenario_changes'}
DECK = {'overview': 'overview', 'lookup': 'lookup', 'lifecycle': 'lifecycle'}   # report deck only
DECK_OUT = style.ROOT / 'tools/deck/figures'


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('names', nargs='*', metavar='name',
                        help=f'figures to build: {", ".join(FIGURES)} (default: all)')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--deck', action='store_true',
                        help=f'build the report deck\'s figures ({", ".join(DECK)}) into {DECK_OUT}')
    args = parser.parse_args()
    known = DECK if args.deck else FIGURES
    unknown = set(args.names) - set(known)
    if unknown:
        parser.error(f'unknown figure: {", ".join(sorted(unknown))}')
    out = args.out or (DECK_OUT if args.deck else style.OUT)
    out.mkdir(parents=True, exist_ok=True)
    for name in args.names or known:
        for path in style.build(importlib.import_module(known[name]), out):
            print(path)


if __name__ == '__main__':
    main()
