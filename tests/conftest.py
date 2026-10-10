"""Pytest configuration: make the scripts under tools/ and .github/actions-scripts/ importable."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for directory in (ROOT / "tools", ROOT / ".github" / "actions-scripts"):
    sys.path.insert(0, str(directory))
