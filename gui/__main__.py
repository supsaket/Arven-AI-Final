"""Launch the ARVEN GUI (``python -m gui``)."""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())