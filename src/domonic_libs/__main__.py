"""``python -m domonic_libs`` -- same entry point as the ``dlx`` console script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
