"""Validation helpers: every validator returns {'status': pass|warn|fail, 'checks': [...]}."""


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
