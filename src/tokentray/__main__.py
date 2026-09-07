"""Allow ``python -m tokentray`` to start the tray app."""

from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
