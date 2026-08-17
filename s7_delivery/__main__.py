"""`python -m s7_delivery` — the CLI surface. See cli.py."""

import sys

from s7_delivery.cli import main

if __name__ == "__main__":
    sys.exit(main())
