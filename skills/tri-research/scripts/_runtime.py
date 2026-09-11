"""Put ``tri_research_runtime`` on ``sys.path`` when the wheel is not installed.

Same-skill bootstrap only (this file lives next to the other scripts).
serpapi has its own sibling-src lookup (ADR-0015).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
