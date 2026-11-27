"""Dependency-free test runner (pytest is optional):  python tests/run_all.py"""
import importlib
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import conftest  # noqa: E402,F401

fails = 0
n = 0
for f in sorted(Path(__file__).parent.glob("test_*.py")):
    mod = importlib.import_module(f.stem)
    for name in sorted(dir(mod)):
        if name.startswith("test_") and callable(getattr(mod, name)):
            n += 1
            t0 = time.time()
            try:
                getattr(mod, name)()
                print(f"PASS {f.stem}::{name} ({time.time() - t0:.1f}s)")
            except Exception:
                fails += 1
                print(f"FAIL {f.stem}::{name}")
                traceback.print_exc()
print(f"\n{n - fails}/{n} passed")
sys.exit(1 if fails else 0)
