"""Generic ontology container + scope membership.  Adapters fill it; the selection engine only queries it.

trees: {tree_name: {"elements": {concept: {element ids}}, "children": {concept: [concept]}}}
Element lists are cumulative in BodyParts3D (a concept lists all descendants' files) -> subtree == elements.
"""
from __future__ import annotations

import collections
import re


class Ontology:
    def __init__(self):
        self.name: dict = {}                                                    # concept id -> name
        self.elements = collections.defaultdict(lambda: collections.defaultdict(set))   # tree -> concept -> {entity local id}
        self.children = collections.defaultdict(lambda: collections.defaultdict(list))  # tree -> concept -> [concept]
        self.entity_concepts = collections.defaultdict(set)                     # local id -> {(tree, concept)}

    def finalize(self):
        for tree, m in self.elements.items():
            for cid, ids in m.items():
                for i in ids:
                    self.entity_concepts[i].add((tree, cid))

    def concepts_by_name(self, exact: str):
        e = exact.lower()
        return sorted((c for c, n in self.name.items() if n.lower() == e), key=lambda c: (len(c), c))

    def subtree_elements(self, tree: str, root: str) -> set:
        seen, stack, out = set(), [root], set()
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c)
            out |= self.elements[tree].get(c, set())
            stack.extend(self.children[tree].get(c, []))
        return out


class ScopeIndex:
    """Resolves the configured scopes of a source to sets of entity ids (local ids)."""

    def __init__(self, ontology: Ontology, entities: dict):
        self.o = ontology
        self.entities = entities                      # entity_id -> SourceEntity

    def _member(self, m: dict) -> set:
        kind = m["kind"]
        if kind == "all":
            return set(self.entities)
        if kind in ("ontology_subtree", "ontology_elements"):
            ids = set()
            tree = m["tree"]
            for name in m["concepts"]:
                for cid in self.o.concepts_by_name(name):
                    ids |= (self.o.subtree_elements(tree, cid) if kind == "ontology_subtree"
                            else set(self.o.elements[tree].get(cid, set())))
            return {i for i in ids if i in self.entities}
        if kind == "name_regex":
            rx = re.compile(m["regex"])
            ex = re.compile(m["exclude_own_regex"]) if m.get("exclude_own_regex") else None
            out = set()
            for eid, e in self.entities.items():
                if any(rx.search(n) for n in e.names) and not (ex and any(ex.search(n) for n in e.own_names)):
                    out.add(eid)
            return out
        if kind == "attribute_range":
            a = m["attribute"]
            return {eid for eid, e in self.entities.items()
                    if m.get("min", float("-inf")) <= e.attributes.get(a, float("nan")) <= m.get("max", float("inf"))}
        raise ValueError(f"unknown scope member kind: {kind}")

    def resolve(self, scope_cfgs: list, priority: list) -> dict:
        """-> {entity_id: scope_name}  (first scope in `priority` that contains the entity and is not excluded)."""
        sets = {}
        by_name = {s["name"]: s for s in scope_cfgs}
        for s in scope_cfgs:
            u = set()
            for m in s["members"]:
                u |= self._member(m)
            sets[s["name"]] = u
        assigned = {}
        for eid in self.entities:
            for name in priority:
                s = by_name[name]
                if eid in sets[name] and not any(eid in sets[x] for x in s.get("exclude_scopes", [])):
                    assigned[eid] = name
                    break
        return assigned
