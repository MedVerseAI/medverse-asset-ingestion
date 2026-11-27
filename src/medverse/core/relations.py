"""Relation graph between assets / entities (parent-child per relation type)."""
from __future__ import annotations

import collections


class RelationGraph:
    def __init__(self):
        self.children = collections.defaultdict(lambda: collections.defaultdict(list))   # rel -> parent -> [child]
        self.parents = collections.defaultdict(lambda: collections.defaultdict(list))

    def add(self, rel: str, parent: str, child: str) -> None:
        if child not in self.children[rel][parent]:
            self.children[rel][parent].append(child)
            self.parents[rel][child].append(parent)

    def descendants(self, rel: str, root: str) -> set:
        seen, stack = set(), [root]
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c)
            stack.extend(self.children[rel].get(c, []))
        return seen

    def relations(self):
        return sorted(self.children)
