from __future__ import annotations

import sys
from pathlib import Path


PACKAGE = Path(__file__).resolve().parent.parent / "berryMOTE"
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))
