"""BodyParts3D adapter: FMA concept trees (isa / partof) + per-element OBJ meshes (FJxxxx.obj).

Only this module knows about the BodyParts3D file layout.  Output: SourceEntity per element file,
Ontology with both trees, MeshAsset (raw units / raw frame) on load.
"""
from __future__ import annotations

import collections
import os
import re
from pathlib import Path


from medverse.adapters.base import SourceAdapter
from medverse.core.assets import CoordinateSystem, MeshAsset, Provenance, SourceEntity, sha256_file
from medverse.core.registry import register_adapter
from medverse.geometry.meshio import read_obj

METADATA_SUFFIXES = collections.OrderedDict([
    ("isa_element", "isa_element_parts.txt"), ("partof_element", "partof_element_parts.txt"),
    ("isa_relation", "isa_inclusion_relation_list.txt"), ("partof_relation", "partof_inclusion_relation_list.txt"),
    ("isa_parts", "isa_parts_list_e.txt"), ("partof_parts", "partof_parts_list_e.txt"),
])
TREES = ("isa", "partof")
LABEL_PREFERENCE = [re.compile(p) for p in (
    r"hippocamp", r"thalamus$", r"caudate|putamen|pallidus|amygdala", r"colliculus", r"^pons$|^midbrain$|medulla",
    r"cerebellum", r"vertebra|^atlas$|^axis$|^sacrum$", r"intervertebral disk", r"spinal cord")]


def read_tsv(path, min_cols):
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        lines = [l.rstrip("\r\n") for l in fh]
    rows = []
    for l in lines[1:]:
        if not l.strip():
            continue
        p = [x.strip() for x in l.split("\t")]
        if len(p) >= min_cols:
            rows.append(p)
    return (lines[0].split("\t") if lines else []), rows


def side_from_names(names) -> str:
    left = any(re.search(r"\bleft\b", n) for n in names)
    right = any(re.search(r"\bright\b", n) for n in names)
    return "L" if left and not right else "R" if right and not left else ""


@register_adapter("bodyparts3d")
class BodyParts3DAdapter(SourceAdapter):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.root = self._dir("root", self.data_dir / "raw" / "bodyparts3d")
        self.meta_dir = self._dir("metadata_dir", self.root / "metadata")
        self.obj_dir = self._dir("obj_dir", self.data_dir / "interim" / "bodyparts3d")
        self.files: dict = {}
        self._obj_index = None
        self.rep: dict = {t: {} for t in TREES}

    # ------------------------------------------------------------------ discovery
    def _find_metadata(self) -> dict:
        found = {}
        if not self.meta_dir.is_dir():
            return found
        all_txt = [Path(dp) / fn for dp, _, fns in os.walk(self.meta_dir) for fn in fns if fn.lower().endswith(".txt")]
        for key, suffix in METADATA_SUFFIXES.items():
            c = sorted((p for p in all_txt if p.name.lower().endswith(suffix)), key=lambda p: (len(str(p)), str(p)))
            if c:
                found[key] = c[0]
        return found

    def discover(self) -> dict:
        self.files = self._find_metadata()
        missing = [k for k in METADATA_SUFFIXES if k not in self.files]
        problems = [f"metadata file '*{METADATA_SUFFIXES[k]}' not found under {self.meta_dir}" for k in missing]
        n_obj = 0
        if self.obj_dir.is_dir():
            n_obj = sum(1 for _, _, fns in os.walk(self.obj_dir) for f in fns if f.lower().endswith(".obj"))
        if n_obj == 0:
            problems.append(f"no .obj meshes under {self.obj_dir} (metadata/selection still works; geometry stages will fail)")
        return {"available": not missing, "obj_files": n_obj, "problems": problems,
                "files": [{"path": str(p), "sha256": sha256_file(str(p))} for p in self.files.values()]}

    # ------------------------------------------------------------------ metadata -> ontology + entities
    def build(self) -> None:
        if not self.files:
            self.files = self._find_metadata()
        o = self.ontology
        for t in TREES:
            hdr, rows = read_tsv(self.files[f"{t}_element"], 3)
            if not hdr or hdr[0].strip().lower() != "concept id":
                self.problems.append(f"unexpected header in {self.files[t + '_element']}: {hdr}")
            for cid, nm, fj in (r[:3] for r in rows):
                o.name[cid] = nm
                o.elements[t][cid].add(f"bodyparts3d:{fj}")
            _, rows = read_tsv(self.files[f"{t}_relation"], 4)
            for pid, pn, cid, cn in (r[:4] for r in rows):
                o.name[pid], o.name[cid] = pn, cn
                if cid not in o.children[t][pid]:
                    o.children[t][pid].append(cid)
                self.relations.add(t, pid, cid)
            _, rows = read_tsv(self.files[f"{t}_parts"], 3)
            for cid, bp, nm in (r[:3] for r in rows):
                o.name.setdefault(cid, nm)
                self.rep[t][cid] = bp
        o.finalize()
        tree_order = list(self.scfg.get("tree_priority", ["partof", "isa"]))
        tree_rank = {t: idx for idx, t in enumerate(tree_order)}
        fallback_rank = len(tree_rank)

        for eid in sorted(o.entity_concepts):
            fj = eid.split(":", 1)[1]
            cs = sorted(o.entity_concepts[eid],
                        key=lambda tc: (len(o.elements[tc[0]][tc[1]]), tree_rank.get(tc[0], fallback_rank), tc[1]))
            n0 = len(o.elements[cs[0][0]][cs[0][1]])
            own = [tc for tc in cs if len(o.elements[tc[0]][tc[1]]) == n0]
            names = frozenset(o.name[c].lower() for _, c in o.entity_concepts[eid])
            own_names = frozenset(o.name[c].lower() for _, c in own)
            cands = [(t, o.name[c].lower()) for t, c in own]

            def key(tn):
                t, n = tn
                pref = next((i for i, rx in enumerate(LABEL_PREFERENCE) if rx.search(n)), len(LABEL_PREFERENCE))
                return (pref, tree_rank.get(t, fallback_rank), len(n), n)
            label = sorted(cands, key=key)[0][1]
            self.entities[eid] = SourceEntity(
                entity_id=eid, source="bodyparts3d", label=label, names=names, own_names=own_names,
                ontology_ids=tuple(sorted({c for _, c in own})), side=side_from_names(names),
                attributes={"fj": fj, "own_concepts": sorted({c for _, c in own})},
                loader=None)
        for e in self.entities.values():
            e.loader = (lambda ent=e: self.load(ent))

    # ------------------------------------------------------------------ geometry
    def _index(self):
        if self._obj_index is None:
            idx = collections.defaultdict(list)
            if self.obj_dir.is_dir():
                for dp, _, fns in os.walk(self.obj_dir):
                    for fn in fns:
                        if fn.lower().endswith(".obj"):
                            idx[os.path.splitext(fn)[0].lower()].append(os.path.join(dp, fn))
            for k in idx:
                idx[k].sort(key=lambda p: (len(p), p))
            self._obj_index = idx
        return self._obj_index

    def find_obj(self, fj: str):
        c = self._index().get(fj.lower(), [])
        return c[0] if c else None

    def load(self, entity) -> MeshAsset:
        fj = entity.attributes["fj"]
        path = self.find_obj(fj)
        if path is None:
            raise FileNotFoundError(f"mesh file for {fj} ({entity.label}) not found under {self.obj_dir}")
        v, f = read_obj(path)
        return MeshAsset(asset_id=entity.entity_id, source=self.name, vertices=v, faces=f,
                         coordinate_system=CoordinateSystem(name="raw", units="unknown", confidence="none"),
                         provenance=Provenance(self.name, path, sha256_file(path)),
                         metadata={"fj": fj, "label": entity.label})
