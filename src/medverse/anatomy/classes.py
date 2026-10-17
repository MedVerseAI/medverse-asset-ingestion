"""
anat_classes.py
---------------
Every CLASS used by the two pipelines, plus the shared logger state.

    Log         : console + in-memory log (with .section / .save / .reset)
    log         : the ONE shared Log instance (import it:  from anat_classes import log)
    WARNINGS    : shared list of warnings;  warn(msg) appends + logs
    Metadata    : BodyParts3D concept trees / element membership   (export)
    MeshIndex   : index of the .obj files on disk                  (export)

Pure python + anat_helpers/anat_config (no bpy needed).
"""
import os
import collections

from medverse.anatomy.config import *  # noqa: F401,F403
from medverse.anatomy.helpers import read_tsv


# ============================================================================
# LOGGING
# ============================================================================
class Log:
    """Prints every message AND keeps it, so the full report can be saved / stored in Blender."""

    def __init__(self):
        self.lines = []

    def __call__(self, msg=""):
        print(msg)
        self.lines.append(str(msg))

    def section(self, title):
        self("")
        self("=" * 78)
        self(title)
        self("=" * 78)

    def save(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.lines) + "\n")

    def reset(self):
        """Forget previous lines (Blender keeps imported modules alive between runs)."""
        self.lines.clear()


log = Log()
WARNINGS = []


def warn(msg):
    """Record + print a recoverable problem."""
    WARNINGS.append(msg)
    log(f"[WARN] {msg}")


def reset_state():
    """Call at the start of every pipeline run."""
    log.reset()
    WARNINGS.clear()


# ============================================================================
# BODYPARTS3D METADATA
# ============================================================================
class Metadata:
    """Both BodyParts3D trees ('isa' and 'partof') in one queryable object."""

    TREES = ("isa", "partof")

    def __init__(self, files):
        self.files = files
        self.name = {}                                              # concept id -> name
        self.elements = {t: collections.defaultdict(set) for t in self.TREES}
        self.children = {t: collections.defaultdict(list) for t in self.TREES}
        self.rep = {t: {} for t in self.TREES}                      # concept id -> BPxxxx
        for t in self.TREES:
            hdr, rows = read_tsv(files[f"{t}_element"], 3)
            if not hdr or hdr[0].strip().lower() != "concept id":
                log(f"[warn] unexpected header in {files[t + '_element']}: {hdr}")
            for cid, nm, fj in (r[:3] for r in rows):
                self.name[cid] = nm
                self.elements[t][cid].add(fj)
            _, rows = read_tsv(files[f"{t}_relation"], 4)
            for pid, pn, cid, cn in (r[:4] for r in rows):
                self.name[pid], self.name[cid] = pn, cn
                if cid not in self.children[t][pid]:
                    self.children[t][pid].append(cid)
            _, rows = read_tsv(files[f"{t}_parts"], 3)
            for cid, bp, nm in (r[:3] for r in rows):
                self.name.setdefault(cid, nm)
                self.rep[t][cid] = bp
        # element -> concepts (element lists are cumulative: a concept lists all descendants' files)
        self.fj_concepts = collections.defaultdict(set)             # fj -> {(tree, concept)}
        for t in self.TREES:
            for cid, fjs in self.elements[t].items():
                for fj in fjs:
                    self.fj_concepts[fj].add((t, cid))
        self.all_fjs = sorted(self.fj_concepts)

    def names_of(self, fj):
        """All (lower-case) concept names an element belongs to."""
        return {self.name[c].lower() for _, c in self.fj_concepts[fj]}

    def label_of(self, fj):
        """Friendliest name among the most specific concepts (partof first, then preferred keywords, then short)."""
        cands = [(t, self.name[c].lower()) for t, c in self.own_concepts(fj)]

        def key(tn):
            t, n = tn
            pref = next((i for i, rx in enumerate(LABEL_PREFERENCE) if rx.search(n)), len(LABEL_PREFERENCE))
            return (pref, t != "partof", len(n), n)
        return sorted(cands, key=key)[0][1]

    def own_concepts(self, fj):
        """Most specific concept(s) of an element: fewest elements, ties -> both trees kept."""
        cs = sorted(self.fj_concepts[fj],
                    key=lambda tc: (len(self.elements[tc[0]][tc[1]]), tc[0] != "partof", tc[1]))
        n0 = len(self.elements[cs[0][0]][cs[0][1]])
        return [tc for tc in cs if len(self.elements[tc[0]][tc[1]]) == n0]

    def concepts_by_name(self, exact=None, rx=None):
        """Concept ids whose name equals `exact` or matches regex `rx`."""
        out = []
        for cid, nm in self.name.items():
            n = nm.lower()
            if (exact is not None and n == exact) or (rx is not None and rx.search(n)):
                out.append(cid)
        return sorted(out, key=lambda c: (len(c), c))

    def subtree_elements(self, tree, root):
        """Elements of a concept and all its descendants."""
        seen, stack, out = set(), [root], set()
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c)
            out |= self.elements[tree].get(c, set())
            stack.extend(self.children[tree].get(c, []))
        return out


# ============================================================================
# MESH FILE INDEX
# ============================================================================
class MeshIndex:
    """Index of every .obj under a folder, keyed by file stem (FJxxxx / BPxxxx)."""

    def __init__(self, root):
        self.by_stem = collections.defaultdict(list)
        self.count = 0
        for dp, _, fns in os.walk(root):
            for fn in fns:
                if fn.lower().endswith(".obj"):
                    self.by_stem[os.path.splitext(fn)[0].lower()].append(os.path.join(dp, fn))
                    self.count += 1
        for k in self.by_stem:
            self.by_stem[k].sort(key=lambda p: (len(p), p))

    def find(self, stem, hint=""):
        """Path of the .obj for `stem` (shortest path, or the one whose path contains `hint`)."""
        c = self.by_stem.get(stem.lower(), [])
        if not c:
            return None
        if hint:
            h = [p for p in c if hint in p.lower()]
            if h:
                return h[0]
        return c[0]
