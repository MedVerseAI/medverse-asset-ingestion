"""Compiled rule objects: explicit exclusions / inclusions, semantic rules, targets.  All data comes from config."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from medverse.config import dotted


@dataclass
class Decision:
    entity_id: str
    source: str
    label: str
    side: str = ""
    semantic_category: str = ""
    semantic_subcategory: str = ""
    scope: str = ""
    decision: str = "excluded"        # included | excluded | reference | review
    rule: str = ""
    matched_target: str = ""
    group: str = ""
    fallback_used: bool = False
    reason: str = ""
    ontology_ids: tuple = ()
    system: str = ""
    collection: str = ""

    def to_dict(self):
        return dict(self.__dict__)


@dataclass
class SemanticRule:
    scope: str
    category: str
    subcategory: str = ""
    regex: re.Pattern = None
    match: str = "all_names"
    attr: dict = field(default_factory=dict)

    def matches(self, entity) -> bool:
        for k, v in self.attr.items():
            if entity.attributes.get(k) != v:
                return False
        if self.regex is None:
            return True
        names = entity.own_names if self.match == "own_names" else entity.names
        return any(self.regex.search(n) for n in names)


def compile_semantic(cfg_source: dict) -> list:
    out = []
    for r in cfg_source.get("rules", []):
        out.append(SemanticRule(scope=r["scope"], category=r["category"], subcategory=r.get("subcategory", ""),
                                regex=re.compile(r["regex"]) if r.get("regex") else None,
                                match=r.get("match", "all_names"), attr=dict(r.get("attr", {}))))
    return out


@dataclass
class Target:
    name: str
    categories: list
    owner: str
    policy: str = "include"
    group: str = ""
    system: str = ""
    collection: str = ""
    enabled_by: str = ""
    fallback_owner: str = ""
    reference_for_registration: bool = False

    def effective_owner(self, enabled_sources: set) -> str:
        if self.owner in enabled_sources:
            return self.owner
        return self.fallback_owner if self.fallback_owner in enabled_sources else ""


def compile_targets(cfg: dict) -> list:
    return [Target(name=t["name"], categories=list(t["categories"]), owner=t["owner"], policy=t.get("policy", "include"),
                   group=t.get("group", ""), system=t.get("system", ""), collection=t.get("collection", ""),
                   enabled_by=t.get("enabled_by", ""), fallback_owner=t.get("fallback_owner", ""),
                   reference_for_registration=bool(t.get("reference_for_registration", False)))
            for t in cfg.get("profile", {}).get("targets", [])]


def target_enabled(cfg: dict, t: Target) -> bool:
    return True if not t.enabled_by else bool(dotted(cfg, t.enabled_by, False))
