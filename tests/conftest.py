"""Test-suite-wide setup."""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to path so imports like `from demo import ...` work
repo_root = Path(__file__).parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
