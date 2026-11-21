import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from make_synthetic_data import ellipsoid, main as make_data  # noqa: E402,F401
