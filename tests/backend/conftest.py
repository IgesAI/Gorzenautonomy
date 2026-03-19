"""Ensure tests always import from this project's src, not a stale editable install."""
import sys
from pathlib import Path

# Insert the local backend/src ahead of any installed package so that edits
# in this repo are always picked up without requiring `pip install -e .`.
_src = str(Path(__file__).parents[2] / "backend" / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
