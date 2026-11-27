"""Selection engine -- no decision without evidence.

Priority:  explicit exclusion > explicit inclusion > ontology/semantic resolution > configured name fallback
           > unknown (-> review, never automatic inclusion).
Every decision is a `Decision` record (written to selection_review.csv).
"""
from __future__ import annotations

import collections
import re

from medverse.selection.ontology import Ontology, ScopeIndex
from medverse.selection.rules import Decision, compile_semantic, compile_targets, target_enabled


def _prepare_rules(raw_rules: list[dict]) -> list[dict]:
    """Pre-compile regexes and ID sets once so inner per-entity loops never recompile."""
    prepared = []
    for r in raw_rules:
        item = dict(r)
        if item.get("kind") == "name_regex" or ("regex" in item and "kind" not in item):
            item["_rx"] = re.compile(item["regex"])
        if item.get("kind") == "entity_ids":
            item["_ids"] = frozenset(item["ids"])
        prepared.append(item)
    return prepared


class SelectionEngine:
    def __init__(self, cfg: dict, sources: dict):
        """sources: {source_name: (entities {entity_id: SourceEntity}, Ontology)} for ENABLED sources only."""
        self.cfg = cfg
        self.sources = sources
        self.enabled = set(sources)
        self.targets = compile_targets(cfg)
        self.sel = cfg["selection"]
        self._by_category = {}
        for t in self.targets:
            for c in t.categories:
                self._by_category.setdefault(c, []).append(t)
        self._target_by_name = {t.name: t for t in self.targets}
        self._exclusions = _prepare_rules(self.sel.get("exclusions", []))
        self._inclusions = _prepare_rules(self.sel.get("inclusions", []))
        self._name_fallback = _prepare_rules(self.sel.get("name_fallback", []))

    # ------------------------------------------------------------------ helpers
    def _matches(self, rule: dict, e, index: ScopeIndex, cache: dict) -> bool:
        kind = rule["kind"]
        if kind in ("ontology_subtree", "ontology_elements"):
            key = (rule["id"], e.source)
            if key not in cache:
                cache[key] = index._member(rule)
            return e.entity_id in cache[key]
        if kind == "name_regex":
            rx = rule["_rx"]
            names = e.own_names if rule.get("match") == "own_names" else e.names
            return any(rx.search(n) for n in names)
        if kind == "entity_ids":
            return e.entity_id in rule["_ids"]
        raise ValueError(f"unknown rule kind {kind}")

    def _semantic(self, source: str, entities: dict, ontology: Ontology):
        scfg = self.cfg.get("semantic", {}).get(source)
        if not scfg:
            return {}, {}
        index = ScopeIndex(ontology, entities)
        assigned = index.resolve(scfg.get("scopes", []), scfg.get("scope_priority", []))
        rules = compile_semantic(scfg)
        out = {}
        for eid, scope in assigned.items():
            for r in rules:
                if r.scope == scope and r.matches(entities[eid]):
                    out[eid] = (r.category, r.subcategory)
                    break
        return assigned, out

    def _place(self, d: Decision, target, source: str, rule_prefix: str = "", fallback=False):
        """Apply target ownership / enablement / policy to a classified entity."""
        owner = target.effective_owner(self.enabled)
        d.matched_target = target.name
        d.fallback_used = fallback
        pre = rule_prefix
        if not owner:
            d.decision, d.rule = "excluded", pre + "owner_source_disabled"
            d.reason = f"target '{target.name}' is owned by '{target.owner}' which is not enabled"
            return
        if owner != source:
            d.rule = pre + "owned_by_other_source"
            d.reason = f"category '{d.semantic_category}' is owned by '{owner}' (overlap policy owner_only)"
            d.decision = "reference" if target.reference_for_registration else "excluded"
            return
        if not target_enabled(self.cfg, target):
            d.decision, d.rule = "excluded", pre + "target_disabled"
            d.reason = f"disabled by {target.enabled_by}"
            return
        d.group, d.system, d.collection = target.group, target.system, target.collection
        if target.policy == "review":
            d.decision, d.rule = "review", pre + "target_policy_review"
            d.reason = "profile marks this target as review-only"
        elif target.policy == "reference":
            d.decision, d.rule, d.reason = "reference", pre + "reference_only", "registration landmark only"
        else:
            d.decision, d.rule = "included", pre + "include_semantic_target"

    # ------------------------------------------------------------------ main
    def run(self) -> list:
        decisions = []
        for source, (entities, ontology) in self.sources.items():
            assigned, classified = self._semantic(source, entities, ontology)
            index = ScopeIndex(ontology, entities)
            cache = {}
            excl = [r for r in self._exclusions if r.get("source", source) == source]
            incl = [r for r in self._inclusions if r.get("source", source) == source]
            fb = [r for r in self._name_fallback if r.get("source", source) == source]
            for eid in sorted(entities):
                e = entities[eid]
                cat, sub = classified.get(eid, ("", ""))
                d = Decision(entity_id=eid, source=source, label=e.label, side=e.side, semantic_category=cat,
                             semantic_subcategory=sub, scope=assigned.get(eid, ""), ontology_ids=tuple(e.ontology_ids))
                decisions.append(d)
                # 1. explicit exclusion (highest priority)
                hit = next((r for r in excl if self._matches(r, e, index, cache)), None)
                if hit:
                    d.decision, d.rule, d.reason = "excluded", f"explicit_exclusion:{hit['id']}", hit.get("reason", "")
                    continue
                # 2. explicit inclusion
                hit = next((r for r in incl if self._matches(r, e, index, cache)), None)
                if hit:
                    tgt = self._target_by_name.get(hit.get("target", "")) or (self._by_category.get(cat) or [None])[0]
                    if tgt is None or tgt.policy != "include":
                        d.decision, d.rule = "review", f"explicit_inclusion:{hit['id']}"
                        d.reason = "explicit inclusion has no includable target"
                        continue
                    d.matched_target, d.group, d.system, d.collection = tgt.name, tgt.group, tgt.system, tgt.collection
                    d.decision, d.rule = "included", f"explicit_inclusion:{hit['id']}"
                    if not target_enabled(self.cfg, tgt):
                        d.decision, d.rule, d.reason = "excluded", "target_disabled", f"disabled by {tgt.enabled_by}"
                    continue
                # 3. ontology / semantic resolution
                fallback = False
                if not cat:
                    # 4. configured name fallback (pre-compiled regex)
                    for r in fb:
                        rx = r["_rx"]
                        if any(rx.search(n) for n in e.names):
                            cat, sub, fallback = r["category"], r.get("subcategory", ""), True
                            d.semantic_category, d.semantic_subcategory = cat, sub
                            break
                if cat:
                    cands = self._by_category.get(cat, [])
                    if not cands:
                        d.decision, d.rule = "excluded", "no_target_in_profile"
                        d.reason = f"category '{cat}' is not part of profile '{self.cfg['profile']['name']}'"
                        continue
                    # a target owned by this source wins over one owned by another source
                    own = [t for t in cands if t.effective_owner(self.enabled) == source]
                    self._place(d, (own or cands)[0], source, "fallback:" if fallback else "", fallback)
                    continue
                # 5. unknown
                if d.scope:
                    if self.sel["unknown_policy"] == "review":
                        d.decision, d.rule = "review", "unknown_policy_review"
                        d.reason = f"in scope '{d.scope}' but no semantic rule matched"
                    else:
                        d.decision, d.rule = "excluded", "unknown_policy_exclude"
                else:
                    d.decision, d.rule, d.reason = "excluded", "out_of_scope", "not in any configured anatomical scope"
        return decisions


def summarize(decisions) -> dict:
    c = collections.Counter(d.decision for d in decisions)
    by_source = collections.defaultdict(collections.Counter)
    by_rule = collections.Counter()
    for d in decisions:
        by_source[d.source][d.decision] += 1
        by_rule[d.rule.split(":")[0]] += 1
    return {"total": len(decisions), "by_decision": dict(c),
            "by_source": {k: dict(v) for k, v in by_source.items()}, "by_rule": dict(by_rule)}
