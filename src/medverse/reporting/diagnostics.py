"""Failure-safe diagnostics: every message is flushed to diagnostics.log immediately, JSON reports are written
atomically (tmp + rename) so a crash can never leave a half-written or deleted report."""
from __future__ import annotations

import json
import os
import time
import traceback
from pathlib import Path


def atomic_write_json(path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, default=_default)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _default(o):
    try:
        import numpy as np
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
    except Exception:
        pass
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    return str(o)


class Diagnostics:
    def __init__(self, out_dir):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.out_dir / "diagnostics.log"
        self.warnings: list = []
        self.errors: list = []
        self._t0 = time.time()

    def _emit(self, level: str, msg: str, stage: str = "") -> None:
        line = f"{time.time() - self._t0:9.2f}s [{level:5s}]{f' [{stage}]' if stage else ''} {msg}"
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
        print(line)

    def info(self, msg, stage=""):
        self._emit("INFO", msg, stage)

    def warn(self, msg, stage=""):
        self.warnings.append({"stage": stage, "message": msg})
        self._emit("WARN", msg, stage)

    def error(self, msg, stage="", exc: BaseException = None):
        self.errors.append({"stage": stage, "message": msg})
        self._emit("ERROR", msg, stage)
        if exc is not None:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
