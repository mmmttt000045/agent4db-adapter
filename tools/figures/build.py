"""Build the paper's vector figures into overleaf/figures/.

    python3 tools/figures/build.py              # all figures
    python3 tools/figures/build.py sharing      # only the named ones
    python3 tools/figures/build.py --out /tmp/x # somewhere else, for previews

Each figure is written twice: <name>.pdf for the English paper and
<name>-zh.pdf for the bilingual build.
"""
import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402

FIGURES = {'sharing': 'sharing', 'architecture': 'architecture', 'replay-outcomes': 'replay_outcomes',
           'maintenance-cost': 'maintenance_cost', 'scenario-groups': 'scenario_groups',
           'scenario-changes': 'scenario_changes'}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('names', nargs='*', metavar='name',
                        help=f'figures to build: {", ".join(FIGURES)} (default: all)')
    parser.add_argument('--out', type=Path, default=style.OUT)
    args = parser.parse_args()
    unknown = set(args.names) - set(FIGURES)
    if unknown:
        parser.error(f'unknown figure: {", ".join(sorted(unknown))}')
    for name in args.names or FIGURES:
        for path in style.build(importlib.import_module(FIGURES[name]), args.out):
            print(path)


if __name__ == '__main__':
    main()
