"""Validation helpers: every validator returns {'status': pass|warn|fail, 'checks': [...]}.

Also re-exports file/archive checksum helpers so `from medverse.validation import sha256_of, ...`
continues to work alongside `medverse.validation.{geometry,registration,selection}`.
"""
from __future__ import annotations

from medverse.validation.files import (
    CHUNK_SIZE_64KB,
    sha256_of,
    verify_checksums,
    verify_file,
    verify_zip,
    write_checksums,
)


class Checks:
    def __init__(self):
        self.items = []

    def add(self, name, status, detail=""):
        assert status in ("pass", "warn", "fail")
        self.items.append({"name": name, "status": status, "detail": detail})

    def check(self, name, ok, detail_fail="", level="fail", detail_ok=""):
        self.add(name, "pass" if ok else level, detail_ok if ok else detail_fail)

    def result(self) -> dict:
        st = "fail" if any(i["status"] == "fail" for i in self.items) else \
             "warn" if any(i["status"] == "warn" for i in self.items) else "pass"
        return {"status": st, "checks": self.items}


__all__ = [
    "CHUNK_SIZE_64KB",
    "Checks",
    "sha256_of",
    "verify_checksums",
    "verify_file",
    "verify_zip",
    "write_checksums",
]
