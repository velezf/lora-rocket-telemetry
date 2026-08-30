"""Put the repo root on sys.path so tests import `ground.*` and `handheld.*`.

Same convention as the ground suite: the project is unpackaged by design and
runs from the repo checkout (see the repo-root pyproject note — that env is
the portfolio renderer, not this runtime).
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
