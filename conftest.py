"""Root conftest — ensures the project root is on sys.path for pytest < 7."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
