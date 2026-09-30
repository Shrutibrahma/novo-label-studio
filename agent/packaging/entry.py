"""PyInstaller entry point: `labelstudio-agent.exe run` (and the other CLI commands)."""

import sys

from agent.main import main

if __name__ == "__main__":
    sys.exit(main())
