"""Build the paper's vector figures into overleaf/figures/.

    python3 tools/figures/build.py              # all paper figures
    python3 tools/figures/build.py sharing      # only the named ones
    python3 tools/figures/build.py --out /tmp/x # somewhere else, for previews
    python3 tools/figures/build.py --drafts --out /tmp/x   # the split system-figure drafts

Each figure is written twice: <name>.pdf for the English paper and
<name>-zh.pdf for the bilingual build.
"""
import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402

FIGURES = {'architecture': 'architecture', 'replay-outcomes': 'replay_outcomes',
           'maintenance-cost': 'maintenance_cost', 'scenario-changes': 'scenario_changes'}
DRAFTS = {'overview': 'overview', 'lookup': 'lookup', 'lifecycle': 'lifecycle'}  # not in the paper yet


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('names', nargs='*', metavar='name',
                        help=f'figures to build: {", ".join(FIGURES)} (default: all)')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--drafts', action='store_true',
                        help=f'build the system-figure drafts ({", ".join(DRAFTS)}); needs --out')
    args = parser.parse_args()
    if args.drafts and not args.out:
        parser.error('--drafts needs --out: the drafts are not paper figures')
    known = DRAFTS if args.drafts else FIGURES
    unknown = set(args.names) - set(known)
    if unknown:
        parser.error(f'unknown figure: {", ".join(sorted(unknown))}')
    out = args.out or style.OUT
    out.mkdir(parents=True, exist_ok=True)
    for name in args.names or known:
        for path in style.build(importlib.import_module(known[name]), out):
            print(path)


if __name__ == '__main__':
    main()
