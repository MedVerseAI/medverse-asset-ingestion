"""
export_bodyparts3d.py
---------------------
BodyParts3D  ->  clean, optimized, Blender-ready PLY pieces + manifest.

Same philosophy as export_bna_voxels.py (one PLY per anatomical piece, binary,
deterministic, verbose log), but the *selection* is driven entirely by the
BodyParts3D metadata you supplied:

    isa_element_parts.txt / partof_element_parts.txt          (concept -> element file FJxxxx)
    isa_inclusion_relation_list.txt / partof_inclusion_...    (concept tree)
    isa_parts_list_e.txt / partof_parts_list_e.txt            (concept -> representation BPxxxx)

Division of labour (see integrate_brainnetome_bodyparts3d.py):
    Human Brainnetome -> cerebral cortex
    BodyParts3D       -> everything else (this script)

What this script does
  1. Reads the metadata, builds the concept trees and element->concept membership.
  2. Tags every element that is a MUSCLE (isa "muscle organ" subtree + name rules).
  3. Selects vertebrae, sacrum, intervertebral discs, spinal cord, cerebellum, brainstem,
     subcortical / deep structures, deep white matter, ventricles ... by name-based rules
     evaluated on the real metadata (no hard-coded FMA / FJ ids).
  4. Excludes cerebral-cortex duplicates (gyri, lobes, insula, ...).  They are NOT written
     as meshes; only a sub-sampled point cloud is stored as a registration reference.
  5. Loads the OBJ meshes, infers units (-> mm) and the anatomical axes (-> RAS, like the
     Brainnetome/MNI space) from the data itself, cleans + optimizes the geometry.
  6. Writes  <OUTPUT_DIR>/meshes/<GROUP>/*.ply, manifest.json, reference/*.npz, report.txt

Requirements:  pip install numpy scipy fast-simplification
               (fast-simplification is optional: without it no decimation is done)
"""
import os
import re
import sys
import json
import collections
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

try:
    import fast_simplification
except ImportError:                       # decimation is optional
    fast_simplification = None

# ============================================================================
# CONFIGURATION
# ============================================================================
BODYPARTS3D_BASE_PATH = r"C:\University\Graduation Project\BodyParts3D_data"

# Folder holding the six metadata .txt files. None -> searched recursively under the base path.
METADATA_DIR = None
# Where the .obj meshes live. None -> whole base path is scanned recursively.
OBJ_SEARCH_DIR = None
OUTPUT_DIR = os.path.join(BODYPARTS3D_BASE_PATH, "bp3d_export_pieces")

# "element": one mesh per element file (FJxxxx.obj)   <- preferred, finest control
# "concept": one mesh per concept representation (BPxxxx.obj)
# "auto"   : element if >= 50 % of the selected elements resolve to files, else concept
MESH_SOURCE = "auto"

# --- optional content -------------------------------------------------------
INCLUDE_VENTRICULAR_SYSTEM = True       # lateral/3rd/4th ventricles, aqueduct, choroid plexus
INCLUDE_CEREBRAL_WHITE_MATTER = True    # white matter, internal capsule, corpus callosum, fornix ...
INCLUDE_CRANIAL_NERVES = False          # only orbital/cranial branches exist in the metadata
# Ambiguous structures are EXCLUDED and reported, unless their (lower-case) concept name
# matches one of these patterns.  Hippocampus: BodyParts3D files it under "region of cerebral
# cortex", Brainnetome treats it as subcortical (ids > BN_CORTICAL_MAX_ID) -> no duplicate.
AMBIGUOUS_INCLUDE_PATTERNS = [r"^(left |right )?hippocampus$"]

# --- geometry -----------------------------------------------------------------
WELD_TOLERANCE_MM = 1e-3                # vertices closer than this are merged
COMPONENT_MIN_FRACTION = 0.005          # drop disconnected islands smaller than this fraction ...
COMPONENT_MIN_FACES = 50                # ... AND smaller than this many faces
DEFAULT_FACE_BUDGET = 50000             # decimate only when a piece exceeds its budget
FACE_BUDGET = {
    "VERTEBRAE": 80000,
    "INTERVERTEBRAL_DISCS": 12000,
    "SPINAL_CORD": 60000,
    "CEREBELLUM": 120000,
    "BRAINSTEM": 80000,
    "SUBCORTICAL_STRUCTURES": 40000,
    "OTHER_BRAIN_STRUCTURES": 40000,
    "CRANIAL_NERVES": 20000,
}
DECIMATION_AGGRESSIVENESS = 5           # fast_simplification agg (lower = higher quality)
MAX_BBOX_DRIFT_MM = 1.0                 # reject a decimation that moves the bbox more than this
REFERENCE_POINT_COUNT = 30000           # cortex reference cloud size (registration only)

# --- frame inference ------------------------------------------------------------
UNIT_CANDIDATE_FACTORS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]   # raw unit -> mm
VERTEBRAL_COLUMN_LENGTH_RANGE_MM = (350.0, 900.0)   # atlas..sacrum of an adult
AXIS_ORTHOGONALITY_TOLERANCE_DEG = 25.0
SPINAL_CORD_MIN_WIDTH_MM = 5.0          # warn if the "spinal cord" mesh is thinner than this

# ============================================================================
# RULES  (regular expressions are matched against lower-case concept names)
# ============================================================================
GROUP_ORDER = ["CEREBELLUM", "BRAINSTEM", "SUBCORTICAL_STRUCTURES", "OTHER_BRAIN_STRUCTURES",
               "CRANIAL_NERVES", "VERTEBRAE", "INTERVERTEBRAL_DISCS", "SPINAL_CORD"]

MUSCLE_ROOT_NAMES = {"muscle organ"}
MUSCLE_NAME_RX = re.compile(r"\bmuscle|muscul(?!oskeletal)|myocardi|sphincter|diaphragm")   # NB: "musculoskeletal system" is not a muscle

VESSEL_RX = re.compile(r"arter|\bvein|venous|vascular|\bsinus|vessel|lymph")
BRAIN_SCOPE_RX = re.compile(r"neuraxis|\bbrain\b|forebrain|midbrain|hindbrain|telencephalon|"
                            r"diencephalon|cerebral hemisphere")
ADJACENT_RX = re.compile(r"^optic chiasm$|^pituitary gland$|tentorium cerebelli")

HIPPOCAMPUS_RX = re.compile(r"^(left |right )?hippocamp(us|al formation)$")
CORTEX_RX = re.compile(r"\bgyrus\b|\bgyri\b|\blobule\b|^(left |right )?(frontal|parietal|temporal|"
                       r"occipital|limbic) lobe$|lobe of cerebral hemisphere|^cortex of|cerebral cortex|"
                       r"^(left |right )?insula$|prefrontal cortex")
VENTRICLE_RX = re.compile(r"ventricle|aqueduct|choroid plexus|ventricular system|interventricular")
CEREBELLUM_RX = re.compile(r"^cerebellum$")
BRAINSTEM_RX = re.compile(r"^medulla oblongata$|^pons$|^midbrain$|midbrain tectum|colliculus|"
                          r"peduncle of midbrain|^brainstem$")
SUBCORTICAL_RX = re.compile(r"thalamus|hypothalamus|epithalamus|habenula|pineal|mammillary|tuber cinereum|"
                            r"geniculate|caudate nucleus|putamen|globus pallidus|amygdala|basal ganglion|"
                            r"nucleus of brain|hippocamp")
WHITE_MATTER_RX = re.compile(r"white matter|internal capsule|corpus callosum|commissure|fornix|"
                             r"stria (medullaris|terminalis)|lamina terminalis|septum of|^capsule|"
                             r"brachium")
DISC_RX = re.compile(r"intervertebral disk|intervertebral disc")
CERVICAL_RX = re.compile(r"cervical vertebra|^atlas$|^axis$")
THORACIC_RX = re.compile(r"thoracic vertebra")
LUMBAR_RX = re.compile(r"lumbar vertebra")
SACRUM_RX = re.compile(r"^sacrum$")
COCCYX_RX = re.compile(r"coccyx|coccygeal vertebra")
NERVE_RX = re.compile(r"\bnerve\b")
SPINAL_NERVE_SEARCH_RX = re.compile(r"spinal nerve|nerve root|cauda equina|conus medullaris|"
                                    r"dorsal root|ventral root|spinal ganglion|ramus of spinal")

LANDMARK_RX = collections.OrderedDict([
    ("thalamus", re.compile(r"^(left |right )?thalamus$")),
    ("caudate", re.compile(r"^(left |right )?caudate nucleus$")),
    ("putamen", re.compile(r"^(left |right )?putamen$")),
    ("globus_pallidus", re.compile(r"^(left |right )?globus pallidus$")),
    ("amygdala", re.compile(r"^(left |right )?amygdala$")),
    ("hippocampus", re.compile(r"^(left |right )?hippocampus$")),
])

# preferred display labels when an element has several equally specific concept names
LABEL_PREFERENCE = [re.compile(p) for p in (
    r"hippocamp", r"thalamus$", r"caudate|putamen|pallidus|amygdala", r"colliculus", r"^pons$|^midbrain$|medulla",
    r"cerebellum", r"vertebra|^atlas$|^axis$|^sacrum$", r"intervertebral disk", r"spinal cord",
)]

ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
            "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12}

METADATA_SUFFIXES = collections.OrderedDict([
    ("isa_element", "isa_element_parts.txt"),
    ("partof_element", "partof_element_parts.txt"),
    ("isa_relation", "isa_inclusion_relation_list.txt"),
    ("partof_relation", "partof_inclusion_relation_list.txt"),
    ("isa_parts", "isa_parts_list_e.txt"),
    ("partof_parts", "partof_parts_list_e.txt"),
])


# ============================================================================
# LOGGING
# ============================================================================
class Log:
    # -----------------------------------------------------------------------------
    # Initialize the logging helper used by the integration pipeline.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Stores the output path and prepares the in-memory log buffer.
    # -----------------------------------------------------------------------------
    def __init__(self):
        """Initialize the logging helper used by the integration pipeline.

Stores the output path and prepares the in-memory log buffer."""
        self.lines = []

    # -----------------------------------------------------------------------------
    # Record and print one integration-stage log message.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Accepts a message and severity, formats it consistently, stores it, and emits it to the console.
    # -----------------------------------------------------------------------------
    def __call__(self, msg=""):
        """Record and print one integration-stage log message.

Accepts a message and severity, formats it consistently, stores it, and emits it to the console."""
        print(msg)
        self.lines.append(str(msg))

    # -----------------------------------------------------------------------------
    # Write a separated integration-stage log section.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Creates a consistent heading for a major pipeline stage.
    # -----------------------------------------------------------------------------
    def section(self, title):
        """Write a separated integration-stage log section.

Creates a consistent heading for a major pipeline stage."""
        self("")
        self("=" * 78)
        self(title)
        self("=" * 78)

    # -----------------------------------------------------------------------------
    # Persist the accumulated log messages to disk.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Writes the collected log entries to the requested text file.
    # -----------------------------------------------------------------------------
    def save(self, path):
        """Persist the accumulated log messages to disk.

Writes the collected log entries to the requested text file."""
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.lines) + "\n")


log = Log()


# ============================================================================
# METADATA
# ============================================================================
# -----------------------------------------------------------------------------
# Locate the BodyParts3D metadata files required by the pipeline.
# Parameters / return behavior: see the unchanged function signature and body.
# Searches the configured dataset locations and returns the metadata-file mapping used by the exporter.
# -----------------------------------------------------------------------------
def find_metadata_files(base, override_dir):
    """Locate the BodyParts3D metadata files required by the pipeline.

Searches the configured dataset locations and returns the metadata-file mapping used by the exporter."""
    root = override_dir or base
    found = {}
    if not os.path.isdir(root):
        raise FileNotFoundError(f"metadata search folder does not exist: {root}")
    all_files = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn.lower().endswith(".txt"):
                all_files.append(os.path.join(dp, fn))
    for key, suffix in METADATA_SUFFIXES.items():
        cands = sorted((p for p in all_files if os.path.basename(p).lower().endswith(suffix)),
                       key=lambda p: (len(p), p))
        if not cands:
            raise FileNotFoundError(f"metadata file '*{suffix}' not found under {root}")
        found[key] = cands[0]
    return found


# -----------------------------------------------------------------------------
# Read a tab-separated metadata file into normalized rows.
# Parameters / return behavior: see the unchanged function signature and body.
# Opens the requested file, parses tab-separated fields, and returns the resulting records.
# -----------------------------------------------------------------------------
def read_tsv(path, min_cols):
    """Read a tab-separated metadata file into normalized rows.

Opens the requested file, parses tab-separated fields, and returns the resulting records."""
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        lines = [l.rstrip("\r\n") for l in fh]
    rows = []
    for l in lines[1:]:
        if not l.strip():
            continue
        p = [x.strip() for x in l.split("\t")]
        if len(p) >= min_cols:
            rows.append(p)
    return lines[0].split("\t") if lines else [], rows


class Metadata:
    """Both BodyParts3D trees ('isa' and 'partof') in one queryable object."""

    TREES = ("isa", "partof")

    # -----------------------------------------------------------------------------
    # Load and index the BodyParts3D concept, relationship, element, and representation metadata.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Builds the in-memory lookup tables that connect concepts, elements, names, parent/child relationships, and mesh representations.
    # -----------------------------------------------------------------------------
    def __init__(self, files):
        """Load and index the BodyParts3D concept, relationship, element, and representation metadata.

Builds the in-memory lookup tables that connect concepts, elements, names, parent/child relationships, and mesh representations."""
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

    # -----------------------------------------------------------------------------
    # Return the human-readable names associated with a concept.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Looks up a concept identifier and returns its available English labels.
    # -----------------------------------------------------------------------------
    def names_of(self, fj):
        """Return the human-readable names associated with a concept.

Looks up a concept identifier and returns its available English labels."""
        return {self.name[c].lower() for _, c in self.fj_concepts[fj]}

    # -----------------------------------------------------------------------------
    # Return the preferred display label for a concept.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Resolves a concept identifier to the label selected by the metadata indexing rules.
    # -----------------------------------------------------------------------------                       ة
    def label_of(self, fj):
        """Friendliest name among the most specific concepts (partof first, then preferred keywords, then short)."""
        cands = [(t, self.name[c].lower()) for t, c in self.own_concepts(fj)]

        def key(tn):
            t, n = tn
            pref = next((i for i, rx in enumerate(LABEL_PREFERENCE) if rx.search(n)), len(LABEL_PREFERENCE))
            return (pref, t != "partof", len(n), n)
        return sorted(cands, key=key)[0][1]

    # -----------------------------------------------------------------------------
    # Return concepts directly associated with an element.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Uses the element-to-concept membership index without expanding descendant concepts.
    # -----------------------------------------------------------------------------
    def own_concepts(self, fj):
        """Most specific concept(s) of an element: fewest elements, ties -> both trees kept."""
        cs = sorted(self.fj_concepts[fj],
                    key=lambda tc: (len(self.elements[tc[0]][tc[1]]), tc[0] != "partof", tc[1]))
        n0 = len(self.elements[cs[0][0]][cs[0][1]])
        return [tc for tc in cs if len(self.elements[tc[0]][tc[1]]) == n0]

    # -----------------------------------------------------------------------------
    # Find concepts whose indexed names match the requested text.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Normalizes the search name and queries the metadata name index.
    # -----------------------------------------------------------------------------
    def concepts_by_name(self, exact=None, rx=None):
        """Find concepts whose indexed names match the requested text.

Normalizes the search name and queries the metadata name index."""
        out = []
        for cid, nm in self.name.items():
            n = nm.lower()
            if (exact is not None and n == exact) or (rx is not None and rx.search(n)):
                out.append(cid)
        return sorted(out, key=lambda c: (len(c), c))

    # -----------------------------------------------------------------------------
    # Collect elements belonging to a concept subtree.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Traverses the concept hierarchy and gathers the represented BodyParts3D elements for the requested concept.
    # -----------------------------------------------------------------------------
    def subtree_elements(self, tree, root):
        """Collect elements belonging to a concept subtree.

Traverses the concept hierarchy and gathers the represented BodyParts3D elements for the requested concept."""
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
# CLASSIFICATION
# ============================================================================
# -----------------------------------------------------------------------------
# Convert a label into a filesystem-safe identifier.
# Parameters / return behavior: see the unchanged function signature and body.
# Normalizes characters so labels can safely be used in generated filenames and paths.
# -----------------------------------------------------------------------------
def sanitize(s):
    """Convert a label into a filesystem-safe identifier.

Normalizes characters so labels can safely be used in generated filenames and paths."""
    return "".join(c if (c.isalnum() or c in "_-") else "_" for c in s.strip().replace(" ", "_")).strip("_")


# -----------------------------------------------------------------------------
# Infer anatomical side information from a set of names.
# Parameters / return behavior: see the unchanged function signature and body.
# Detects left/right/bilateral or unspecified side markers from the supplied labels.
# -----------------------------------------------------------------------------
def side_from_names(names):
    """Infer anatomical side information from a set of names.

Detects left/right/bilateral or unspecified side markers from the supplied labels."""
    left = any(re.search(r"\bleft\b", n) for n in names)
    right = any(re.search(r"\bright\b", n) for n in names)
    if left and not right:
        return "L"
    if right and not left:
        return "R"
    return ""


# -----------------------------------------------------------------------------
# Extract the spinal-region code from an anatomical label.
# Parameters / return behavior: see the unchanged function signature and body.
# Classifies vertebral region naming such as cervical, thoracic, lumbar, sacral, or coccygeal.
# -----------------------------------------------------------------------------
def spine_code(label):
    """'tenth thoracic vertebra' -> ('T10', 10*)  |  'atlas' -> 'C1' | 'axis' -> 'C2' ; '' if unknown."""
    l = label.lower()
    if l == "atlas":
        return "C1"
    if l == "axis" or l.endswith(" of axis"):
        return "C2"
    for word, n in ORDINALS.items():
        if re.search(rf"\b{word}\b", l):
            if "cervical" in l:
                return f"C{n}"
            if "thoracic" in l:
                return f"T{n}"
            if "lumbar" in l:
                return f"L{n}"
    if l == "sacrum":
        return "S"
    return ""


# -----------------------------------------------------------------------------
# Convert an anatomical ordering code into a sortable value.
# Parameters / return behavior: see the unchanged function signature and body.
# Provides deterministic ordering for vertebral and related structures.
# -----------------------------------------------------------------------------
def code_order(code):
    """Convert an anatomical ordering code into a sortable value.

Provides deterministic ordering for vertebral and related structures."""
    if not code:
        return (9, 0)
    return ({"C": 0, "T": 1, "L": 2, "S": 3}[code[0]], int(code[1:] or 0))


# -----------------------------------------------------------------------------
# Identify BodyParts3D elements that represent muscles.
# Parameters / return behavior: see the unchanged function signature and body.
# Combines concept-tree membership and name-based rules to build the muscle exclusion set.
# -----------------------------------------------------------------------------
def compute_muscle_elements(meta):
    """Union of (a) all elements of the isa 'muscle organ' subtree, (b) name-rule hits."""
    muscle = set()
    for cid in meta.concepts_by_name(exact="muscle organ"):
        muscle |= meta.subtree_elements("isa", cid)
        muscle |= meta.elements["isa"].get(cid, set())
    n_tree = len(muscle)
    for fj in meta.all_fjs:
        if fj in muscle:
            continue
        if any(MUSCLE_NAME_RX.search(n) for n in meta.names_of(fj)):
            muscle.add(fj)
    return muscle, n_tree


# -----------------------------------------------------------------------------
# Classify BodyParts3D elements into the anatomical groups exported by the pipeline.
# Parameters / return behavior: see the unchanged function signature and body.
# Applies the metadata-driven inclusion and exclusion rules and returns the selected structures grouped by anatomical category.
# -----------------------------------------------------------------------------
def classify_all(meta, muscle):
    """Return dict fj -> decision record for every element that is in a requested scope."""
    cord_fj = set()
    for cid in meta.concepts_by_name(exact="spinal cord"):
        cord_fj |= meta.elements["partof"].get(cid, set())
    spine_fj = set()
    for cid in meta.concepts_by_name(exact="vertebral column"):
        spine_fj |= meta.subtree_elements("partof", cid) | meta.elements["partof"].get(cid, set())
    brain_fj = set()
    for cid in meta.concepts_by_name(exact="brain"):
        brain_fj |= meta.elements["partof"].get(cid, set())
    for fj in meta.all_fjs:
        names = meta.names_of(fj)
        own = {meta.name[c].lower() for _, c in meta.own_concepts(fj)}
        if any(BRAIN_SCOPE_RX.search(n) for n in names) and not any(VESSEL_RX.search(n) for n in own):
            brain_fj.add(fj)
    adjacent_fj = {fj for fj in meta.all_fjs if any(ADJACENT_RX.search(n) for n in meta.names_of(fj))}

    out = {}
    for fj in sorted(cord_fj | spine_fj | brain_fj | adjacent_fj):
        names = meta.names_of(fj)
        own_c = meta.own_concepts(fj)
        own = sorted({meta.name[c].lower() for _, c in own_c})
        label = meta.label_of(fj)
        rec = {"fj": fj, "names": sorted(names), "own_names": own, "label": label,
               "concepts": sorted({c for _, c in own_c}), "decision": "exclude", "group": None,
               "subgroup": "", "reason": "", "notes": []}
        out[fj] = rec

        if fj in muscle:
            rec["reason"] = "muscle"
            continue
        if fj in cord_fj:
            rec.update(decision="include", group="SPINAL_CORD", subgroup="spinal_cord",
                       label="spinal cord", reason="concept 'spinal cord' element")
            if any("central canal" in n for n in names):
                rec["notes"].append("same element file is also registered as 'central canal of spinal cord' "
                                    "in the metadata; verified by geometry in the report")
            continue
        if fj in spine_fj:
            if any(DISC_RX.search(n) for n in names):
                rec.update(decision="include", group="INTERVERTEBRAL_DISCS", subgroup="disc",
                           reason="intervertebral disk concept")
                rec["label"] = next((n for n in own if DISC_RX.search(n)), label)
            elif any(SACRUM_RX.search(n) for n in names):
                rec.update(decision="include", group="VERTEBRAE", subgroup="sacral", label="sacrum",
                           reason="sacrum")
            elif any(COCCYX_RX.search(n) for n in names):
                rec.update(decision="include", group="VERTEBRAE", subgroup="coccygeal", reason="coccyx")
            elif any(CERVICAL_RX.search(n) for n in names):
                rec.update(decision="include", group="VERTEBRAE", subgroup="cervical", reason="cervical vertebra")
            elif any(THORACIC_RX.search(n) for n in names):
                rec.update(decision="include", group="VERTEBRAE", subgroup="thoracic", reason="thoracic vertebra")
            elif any(LUMBAR_RX.search(n) for n in names):
                rec.update(decision="include", group="VERTEBRAE", subgroup="lumbar", reason="lumbar vertebra")
            else:
                rec.update(decision="ambiguous", reason="element of vertebral column not recognised by name rules")
            continue
        if fj in adjacent_fj and fj not in brain_fj:
            rec.update(decision="ambiguous", reason="non-CNS structure attached to the brain "
                       "(optic chiasm / pituitary / tentorium); excluded unless whitelisted")
            if _whitelisted(names):
                rec["decision"] = "include"
                rec.update(group="OTHER_BRAIN_STRUCTURES", subgroup="adjacent")
            continue
        # ---------------- brain scope ----------------
        if any(HIPPOCAMPUS_RX.search(n) for n in own):
            rec.update(decision="ambiguous", reason="hippocampus: filed by BodyParts3D under 'region of "
                       "cerebral cortex' but Brainnetome treats it as subcortical")
            if _whitelisted(own):
                rec.update(decision="include", group="SUBCORTICAL_STRUCTURES", subgroup="hippocampus")
            continue
        if any(CORTEX_RX.search(n) for n in names):
            rec.update(decision="exclude", group="CORTEX_DUPLICATE", reason="cerebral cortex -> Brainnetome")
            continue
        if any(VENTRICLE_RX.search(n) for n in names):
            rec.update(decision="include" if INCLUDE_VENTRICULAR_SYSTEM else "exclude",
                       group="OTHER_BRAIN_STRUCTURES", subgroup="ventricular_system",
                       reason="ventricular system" + ("" if INCLUDE_VENTRICULAR_SYSTEM else " (disabled)"))
            continue
        if any(CEREBELLUM_RX.search(n) for n in names):
            rec.update(decision="include", group="CEREBELLUM", subgroup="cerebellum", reason="cerebellum")
            continue
        if any(BRAINSTEM_RX.search(n) for n in names):
            sub = "midbrain"
            if any(n in ("pons",) for n in names):
                sub = "pons"
            elif any(n == "medulla oblongata" for n in names):
                sub = "medulla_oblongata"
            rec.update(decision="include", group="BRAINSTEM", subgroup=sub, reason="brainstem part")
            continue
        if any(SUBCORTICAL_RX.search(n) for n in names):
            rec.update(decision="include", group="SUBCORTICAL_STRUCTURES", subgroup="deep_gray_matter",
                       reason="diencephalon / basal ganglia / amygdala")
            continue
        if any(WHITE_MATTER_RX.search(n) for n in names):
            rec.update(decision="include" if INCLUDE_CEREBRAL_WHITE_MATTER else "exclude",
                       group="OTHER_BRAIN_STRUCTURES", subgroup="white_matter",
                       reason="deep white matter" + ("" if INCLUDE_CEREBRAL_WHITE_MATTER else " (disabled)"))
            continue
        rec.update(decision="ambiguous", reason="in brain scope but matches no rule")

    if INCLUDE_CRANIAL_NERVES:
        for fj in meta.all_fjs:
            if fj in out or fj in muscle:
                continue
            if any(NERVE_RX.search(n) for n in meta.names_of(fj)):
                own = sorted({meta.name[c].lower() for _, c in meta.own_concepts(fj)})
                out[fj] = {"fj": fj, "names": sorted(meta.names_of(fj)), "own_names": own, "label": meta.label_of(fj),
                           "concepts": sorted({c for _, c in meta.own_concepts(fj)}), "decision": "include",
                           "group": "CRANIAL_NERVES", "subgroup": "cranial_nerve",
                           "reason": "nerve (INCLUDE_CRANIAL_NERVES)", "notes": []}
    return out


# -----------------------------------------------------------------------------
# Check whether an element is explicitly allowed by the configured inclusion rules.
# Parameters / return behavior: see the unchanged function signature and body.
# Evaluates the configured exception patterns for otherwise ambiguous anatomical structures.
# -----------------------------------------------------------------------------
def _whitelisted(names):
    """Check whether an element is explicitly allowed by the configured inclusion rules.

Evaluates the configured exception patterns for otherwise ambiguous anatomical structures."""
    return any(re.search(p, n) for p in AMBIGUOUS_INCLUDE_PATTERNS for n in names)


# ============================================================================
# MESH I/O
# ============================================================================
class MeshIndex:
    # -----------------------------------------------------------------------------
    # Initialize an index over available BodyParts3D mesh files.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Stores the mesh search configuration and prepares the filename/code lookup used during mesh loading.
    # -----------------------------------------------------------------------------
    def __init__(self, root):
        """Initialize an index over available BodyParts3D mesh files.

Stores the mesh search configuration and prepares the filename/code lookup used during mesh loading."""
        self.by_stem = collections.defaultdict(list)
        self.count = 0
        for dp, _, fns in os.walk(root):
            for fn in fns:
                if fn.lower().endswith(".obj"):
                    self.by_stem[os.path.splitext(fn)[0].lower()].append(os.path.join(dp, fn))
                    self.count += 1
        for k in self.by_stem:
            self.by_stem[k].sort(key=lambda p: (len(p), p))

    # -----------------------------------------------------------------------------
    # Find the mesh file associated with a BodyParts3D element code.
    # Parameters / return behavior: see the unchanged function signature and body.
    # Searches the indexed OBJ sources and returns the matching mesh path when available.
    # -----------------------------------------------------------------------------
    def find(self, stem, hint=""):
        """Find the mesh file associated with a BodyParts3D element code.

Searches the indexed OBJ sources and returns the matching mesh path when available."""
        c = self.by_stem.get(stem.lower(), [])
        if not c:
            return None
        if hint:
            h = [p for p in c if hint in p.lower()]
            if h:
                return h[0]
        return c[0]


# -----------------------------------------------------------------------------
# Read a BodyParts3D OBJ mesh into numeric vertex and face arrays.
# Parameters / return behavior: see the unchanged function signature and body.
# Parses OBJ geometry and returns vertices and triangular face indices in the source coordinate system.
# -----------------------------------------------------------------------------
def read_obj(path):
    """Read a BodyParts3D OBJ mesh into numeric vertex and face arrays.

Parses OBJ geometry and returns vertices and triangular face indices in the source coordinate system."""
    verts, faces = [], []
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    i = int(tok.split("/")[0])
                    idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):                 # fan-triangulate quads / n-gons
                    faces.append((idx[0], idx[k], idx[k + 1]))
    v = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
    f = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if len(f) and (f.min() < 0 or f.max() >= len(v)):
        raise ValueError(f"face index out of range in {path}")
    return v, f


# -----------------------------------------------------------------------------
# Write an anatomical mesh to binary PLY format.
# Parameters / return behavior: see the unchanged function signature and body.
# Serializes vertices and faces into the compact PLY representation consumed by the integration stage.
# -----------------------------------------------------------------------------
def write_ply_binary(path, verts, faces):
    """Write an anatomical mesh to binary PLY format.

Serializes vertices and faces into the compact PLY representation consumed by the integration stage."""
    v = np.empty(len(verts), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4")])
    v["x"], v["y"], v["z"] = verts[:, 0], verts[:, 1], verts[:, 2]
    f = np.empty(len(faces), dtype=[("n", "u1"), ("idx", "<i4", (3,))])
    f["n"] = 3
    f["idx"] = faces
    header = ("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {len(v)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              f"element face {len(f)}\n"
              "property list uchar int vertex_indices\nend_header\n")
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(v.tobytes())
        fh.write(f.tobytes())


# ============================================================================
# GEOMETRY
# ============================================================================
# -----------------------------------------------------------------------------
# Clean and optimize raw mesh geometry.
# Parameters / return behavior: see the unchanged function signature and body.
# Removes invalid geometry, welds nearby vertices, filters disconnected components, and applies the configured mesh-cleaning rules.
# -----------------------------------------------------------------------------
def clean_mesh(verts, faces, weld_tol):
    """Weld, drop degenerate/duplicate faces, drop tiny islands, fix inverted closed meshes."""
    stats = {"raw_verts": len(verts), "raw_faces": len(faces)}
    q = np.round(verts / weld_tol).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    verts = verts[first]
    faces = inv.reshape(-1)[faces]
    ok = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    stats["degenerate"] = int((~ok).sum())
    faces = faces[ok]
    key = np.sort(faces, axis=1)
    _, keep = np.unique(key, axis=0, return_index=True)
    stats["duplicate"] = int(len(faces) - len(keep))
    faces = faces[np.sort(keep)]
    # islands
    n = len(verts)
    if len(faces):
        a = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2]])
        b = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0]])
        g = coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n))
        ncomp, lab = connected_components(g, directed=False)
        fcount = np.bincount(lab[faces[:, 0]], minlength=ncomp)
        tot = fcount.sum()
        small = (fcount < COMPONENT_MIN_FACES) & (fcount < COMPONENT_MIN_FRACTION * tot)
        if small.all():
            small[np.argmax(fcount)] = False
        stats["components"] = int(ncomp)
        stats["islands_removed"] = int(small.sum())
        faces = faces[~small[lab[faces[:, 0]]]]
    else:
        stats["components"], stats["islands_removed"] = 0, 0
    used = np.unique(faces)
    remap = -np.ones(len(verts), dtype=np.int64)
    remap[used] = np.arange(len(used))
    verts, faces = verts[used], remap[faces]
    vol = signed_volume(verts, faces)
    stats["closed"] = is_closed(faces)
    stats["flipped"] = False
    if stats["closed"] and vol < 0:
        faces = faces[:, ::-1].copy()
        stats["flipped"] = True
        vol = -vol
    stats["volume_raw"] = float(vol)
    return verts, faces, stats


# -----------------------------------------------------------------------------
# Compute the signed volume of a closed triangular mesh.
# Parameters / return behavior: see the unchanged function signature and body.
# Uses triangle geometry to determine the mesh orientation and signed enclosed volume.
# -----------------------------------------------------------------------------
def signed_volume(v, f):
    """Compute the signed volume of a closed triangular mesh.

Uses triangle geometry to determine the mesh orientation and signed enclosed volume."""
    if len(f) == 0:
        return 0.0
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


# -----------------------------------------------------------------------------
# Determine whether a triangular mesh is topologically closed.
# Parameters / return behavior: see the unchanged function signature and body.
# Checks edge usage to identify boundary edges and therefore whether the surface is watertight.
# -----------------------------------------------------------------------------
def is_closed(f):
    """Determine whether a triangular mesh is topologically closed.

Checks edge usage to identify boundary edges and therefore whether the surface is watertight."""
    if len(f) == 0:
        return False
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    e.sort(axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return bool((cnt == 2).all())


# -----------------------------------------------------------------------------
# Reduce mesh face count while preserving the configured geometric constraints.
# Parameters / return behavior: see the unchanged function signature and body.
# Applies optional fast-simplification decimation when available and returns the simplified geometry.
# -----------------------------------------------------------------------------
def decimate(verts, faces, budget):
    """Reduce mesh face count while preserving the configured geometric constraints.

Applies optional fast-simplification decimation when available and returns the simplified geometry."""
    if fast_simplification is None or len(faces) <= budget:
        return verts, faces, False, ""
    red = 1.0 - budget / float(len(faces))
    try:
        v2, f2 = fast_simplification.simplify(verts.astype(np.float64), faces.astype(np.int64),
                                              target_reduction=red, agg=DECIMATION_AGGRESSIVENESS)
    except Exception as exc:                                     # pragma: no cover
        return verts, faces, False, f"decimation failed ({exc})"
    drift = max(np.abs(v2.min(0) - verts.min(0)).max(), np.abs(v2.max(0) - verts.max(0)).max())
    if drift > MAX_BBOX_DRIFT_MM:                     # geometry is already in millimetres here
        return verts, faces, False, f"decimation rejected (bbox drift {drift:.2f})"
    return v2, f2.astype(np.int64), True, ""


# ============================================================================
# FRAME INFERENCE (units + axes)
# ============================================================================
# -----------------------------------------------------------------------------
# Return a unit-length vector for a numeric vector.
# Parameters / return behavior: see the unchanged function signature and body.
# Normalizes the vector while handling the zero-length case safely.
# -----------------------------------------------------------------------------
def _unit(v):
    """Return a unit-length vector for a numeric vector.

Normalizes the vector while handling the zero-length case safely."""
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError("degenerate direction")
    return v / n


# -----------------------------------------------------------------------------
# Compute the angle between two vectors in degrees.
# Parameters / return behavior: see the unchanged function signature and body.
# Normalizes the vectors and evaluates their angular separation.
# -----------------------------------------------------------------------------
def _angle(a, b):
    """Compute the angle between two vectors in degrees.

Normalizes the vectors and evaluates their angular separation."""
    return float(np.degrees(np.arccos(np.clip(np.dot(_unit(a), _unit(b)), -1, 1))))


# -----------------------------------------------------------------------------
# Infer physical units and anatomical RAS orientation from the exported geometry.
# Parameters / return behavior: see the unchanged function signature and body.
# Uses anatomical landmarks and geometric constraints to determine scale and axis directions.
# -----------------------------------------------------------------------------
def infer_frame(units):
    """
    units: list of dict(points=Nx3 raw, group, subgroup, side, names, cortex(bool)).
    Returns dict describing raw->RAS(mm) transform, with diagnostics.
    """
    info = {"applied": False, "confidence": "none", "messages": []}

    def pts(sel):
        arr = [u["points"] for u in units if sel(u)]
        return np.concatenate(arr) if arr else np.empty((0, 3))

    # --- units from the vertebral column length (raw principal axis) ---------------
    vert = pts(lambda u: u["group"] == "VERTEBRAE")
    factor = 1.0
    if len(vert) > 100:
        c = vert.mean(0)
        _, _, vt = np.linalg.svd(vert - c, full_matrices=False)
        proj = (vert - c) @ vt[0]
        length = float(proj.max() - proj.min())
        lo, hi = VERTEBRAL_COLUMN_LENGTH_RANGE_MM
        fits = [f for f in UNIT_CANDIDATE_FACTORS if lo <= length * f <= hi]
        info["vertebral_length_raw"] = length
        if len(fits) == 1:
            factor = fits[0]
        else:
            info["messages"].append(f"unit factor ambiguous/undetermined (length {length:.3f}, candidates {fits}); "
                                    "assuming 1.0 (millimetres)")
    else:
        info["messages"].append("no vertebrae available to infer units; assuming millimetres")
    info["unit_factor_to_mm"] = factor

    # --- axes ---------------------------------------------------------------------------
    brain_all = pts(lambda u: u["group"] in ("CEREBELLUM", "BRAINSTEM", "SUBCORTICAL_STRUCTURES",
                                              "OTHER_BRAIN_STRUCTURES") or u["cortex"])
    low_spine = pts(lambda u: u["group"] == "VERTEBRAE" and u["subgroup"] in ("lumbar", "sacral"))
    cord = pts(lambda u: u["group"] == "SPINAL_CORD")
    left = pts(lambda u: u["side"] == "L" and (u["cortex"] or u["group"] in ("SUBCORTICAL_STRUCTURES",)))
    right = pts(lambda u: u["side"] == "R" and (u["cortex"] or u["group"] in ("SUBCORTICAL_STRUCTURES",)))
    frontal = pts(lambda u: u["cortex"] and any(re.search(r"frontal", n) and not re.search(r"nerve", n)
                                                 for n in u["names"]))
    occip = pts(lambda u: u["cortex"] and any("occipital" in n for n in u["names"]))
    cereb = pts(lambda u: u["group"] == "CEREBELLUM")
    bstem = pts(lambda u: u["group"] == "BRAINSTEM")

    try:
        if len(brain_all) == 0:
            raise ValueError("no brain geometry")
        lower = low_spine if len(low_spine) else cord
        if len(lower) == 0:
            raise ValueError("no spine / cord geometry for the superior-inferior axis")
        S = _unit(brain_all.mean(0) - lower.mean(0))
        if len(left) == 0 or len(right) == 0:
            raise ValueError("no left/right hemisphere landmarks")
        R = _unit(right.mean(0) - left.mean(0))
        A_cands = []
        if len(frontal) and len(occip):
            A_cands.append(_unit(frontal.mean(0) - occip.mean(0)))
        if len(cereb) and len(bstem):
            A_cands.append(_unit(bstem.mean(0) - cereb.mean(0)))
        if not A_cands:
            raise ValueError("no anterior-posterior landmarks")
        A = _unit(np.sum(A_cands, axis=0))
        angs = {"R-S": _angle(R, S), "A-S": _angle(A, S), "R-A": _angle(R, A)}
        info["raw_axis_angles_deg"] = angs
        worst = max(abs(90.0 - a) for a in angs.values())
        Rn = _unit(R - S * np.dot(R, S))
        An = _unit(A - S * np.dot(A, S) - Rn * np.dot(A, Rn))
        M = np.vstack([Rn, An, S])                            # rows = R, A, S directions in raw space
        info["matrix_raw_to_ras"] = M.tolist()
        info["determinant"] = float(np.linalg.det(M))
        info["applied"] = True
        info["confidence"] = "ok" if worst <= AXIS_ORTHOGONALITY_TOLERANCE_DEG else "low"
        info["worst_orthogonality_error_deg"] = worst
        if len(A_cands) == 2:
            info["ap_landmark_disagreement_deg"] = _angle(A_cands[0], A_cands[1])
        if info["determinant"] < 0:
            info["messages"].append("raw frame is mirrored with respect to the anatomical labels "
                                    "(left/right); faces will be flipped")
        if info["confidence"] == "low":
            info["messages"].append(f"axes are only {90 - worst:.0f}..90 deg orthogonal: LOW confidence")
    except ValueError as exc:
        info["messages"].append(f"axis inference failed: {exc}; raw orientation kept")
        info["matrix_raw_to_ras"] = np.eye(3).tolist()
        info["determinant"] = 1.0
    return info


# ============================================================================
# MAIN PIPELINE
# ============================================================================
# -----------------------------------------------------------------------------
# Provide the build units operation used by this pipeline.
# Parameters / return behavior: see the unchanged function signature and body.
# This helper performs the operation implemented by the original function body and returns its existing result.
# -----------------------------------------------------------------------------
def build_units(meta, fj_records, mesh_mode):
    """Group elements into mesh 'units' (1 element or 1 concept representation)."""
    units = []
    if mesh_mode == "element":
        for rec in fj_records:
            units.append({"key": rec["fj"], "fjs": [rec["fj"]], "stems": [rec["fj"]], "hint": "",
                          "recs": [rec], "concept": rec["concepts"][0] if rec["concepts"] else ""})
        return units, []
    chosen = {}
    problems = []
    sel = {r["fj"] for r in fj_records}
    for rec in fj_records:
        tc = meta.own_concepts(rec["fj"])[0]
        chosen.setdefault(tc, []).append(rec)
    for (tree, cid), recs in sorted(chosen.items(), key=lambda kv: kv[0][1]):
        elems = meta.elements[tree][cid]
        bp = meta.rep[tree].get(cid)
        if not bp:
            problems.append(f"{cid} {meta.name[cid]}: no representation id (BP) in {tree}_parts_list_e.txt")
            continue
        if not elems <= sel:
            problems.append(f"{cid} {meta.name[cid]}: concept mesh also contains unselected elements "
                            f"({len(elems - sel)}); skipped to avoid importing excluded anatomy")
            continue
        units.append({"key": bp, "fjs": sorted(elems), "stems": [bp], "hint": tree, "recs": recs,
                      "concept": cid})
    return units, problems


# -----------------------------------------------------------------------------
# Run the complete Brainnetome + BodyParts3D integration pipeline.
# Parameters / return behavior: see the unchanged function signature and body.
# Loads both anatomical sources, registers them, builds the Blender scene, audits the result, and writes the final report.
# -----------------------------------------------------------------------------
def main():
    """Run the complete Brainnetome + BodyParts3D integration pipeline.

Loads both anatomical sources, registers them, builds the Blender scene, audits the result, and writes the final report."""
    log.section("BodyParts3D export pipeline")
    log(f"BODYPARTS3D_BASE_PATH : {BODYPARTS3D_BASE_PATH}")
    log(f"OUTPUT_DIR            : {OUTPUT_DIR}")
    if not os.path.isdir(BODYPARTS3D_BASE_PATH):
        log("[error] BODYPARTS3D_BASE_PATH does not exist")
        return 2
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ------------------------------------------------------------------ metadata
    files = find_metadata_files(BODYPARTS3D_BASE_PATH, METADATA_DIR)
    for k, p in files.items():
        log(f"metadata {k:15s}: {p}")
    meta = Metadata(files)
    log(f"concepts: {len(meta.name)} | element files (FJ): {len(meta.all_fjs)} | "
        f"isa concepts with elements: {len(meta.elements['isa'])} | partof: {len(meta.elements['partof'])}")

    # ------------------------------------------------------------------ muscles
    log.section("Muscle detection")
    muscle, n_tree = compute_muscle_elements(meta)
    log(f"elements tagged as muscle: {len(muscle)} (isa 'muscle organ' subtree: {n_tree}, "
        f"additional by name rules: {len(muscle) - n_tree})")
    muscle_by_region = collections.Counter()
    for fj in muscle:
        for n in meta.names_of(fj):
            if n.startswith("muscle of "):
                muscle_by_region[n] += 1
    for n, c in sorted(muscle_by_region.items()):
        log(f"   {n:40s} {c}")

    # ------------------------------------------------------------------ classification
    log.section("Structure discovery / classification")
    cls = classify_all(meta, muscle)
    inc = [r for r in cls.values() if r["decision"] == "include"]
    amb = [r for r in cls.values() if r["decision"] == "ambiguous"]
    exc_cortex = [r for r in cls.values() if r["group"] == "CORTEX_DUPLICATE"]
    exc_muscle = [r for r in cls.values() if r["reason"] == "muscle"]
    exc_other = [r for r in cls.values() if r["decision"] == "exclude" and r["group"] != "CORTEX_DUPLICATE"
                 and r["reason"] != "muscle"]
    out_of_scope = len(meta.all_fjs) - len(cls)
    log(f"elements in requested scope   : {len(cls)}")
    log(f"elements out of scope (body)  : {out_of_scope}   [limbs, organs, vessels, ... never loaded]")
    log(f"selected                      : {len(inc)}")
    log(f"excluded - cerebral cortex    : {len(exc_cortex)}  (Brainnetome is the source)")
    log(f"excluded - muscle in scope    : {len(exc_muscle)}")
    log(f"excluded - other / disabled   : {len(exc_other)}")
    log(f"AMBIGUOUS (excluded, reported): {len(amb)}")
    for r in exc_muscle:
        log(f"   [muscle excluded] {r['fj']} {r['label']}")
    for r in exc_other:
        log(f"   [excluded] {r['fj']} {r['label']} -> {r['reason']}")
    for r in amb:
        log(f"   [AMBIGUOUS] {r['fj']} {r['label']} -> {r['reason']}")

    # ------------------------------------------------------------------ mesh files
    log.section("Mesh files")
    obj_root = OBJ_SEARCH_DIR or BODYPARTS3D_BASE_PATH
    index = MeshIndex(obj_root)
    log(f"{index.count} .obj files under {obj_root}")
    dups = sum(1 for v in index.by_stem.values() if len(v) > 1)
    if dups:
        log(f"[info] {dups} file names exist in several folders; shortest path (or matching isa/partof hint) wins")
    need = inc + exc_cortex
    resolved = sum(1 for r in need if index.find(r["fj"]))
    mode = MESH_SOURCE
    if mode == "auto":
        mode = "element" if need and resolved >= 0.5 * len(need) else "concept"
    log(f"element files resolvable: {resolved}/{len(need)} -> mesh source mode: {mode}")

    units_inc, prob1 = build_units(meta, inc, mode)
    units_cx, prob2 = build_units(meta, exc_cortex, mode)
    for p in prob1 + prob2:
        log(f"[warn] {p}")

    missing_files = []

    def load_units(units):
        loaded = []
        for u in units:
            paths = [index.find(s, u["hint"]) for s in u["stems"]]
            if any(p is None for p in paths):
                missing_files.append(u)
                continue
            vs, fs, off = [], [], 0
            for p in paths:
                v, f = read_obj(p)
                vs.append(v)
                fs.append(f + off)
                off += len(v)
            u["paths"] = paths
            u["verts"] = np.concatenate(vs)
            u["faces"] = np.concatenate(fs)
            loaded.append(u)
        return loaded

    loaded = load_units(units_inc)
    loaded_cx = load_units(units_cx)
    for u in missing_files:
        log(f"[MISSING FILE] {u['stems']} ({', '.join(r['label'] for r in u['recs'])})")
    if not loaded:
        log("[error] no meshes could be loaded. Check BODYPARTS3D_BASE_PATH / OBJ_SEARCH_DIR / MESH_SOURCE.")
        log.save(os.path.join(OUTPUT_DIR, "report.txt"))
        return 3

    # attach classification info used by the frame inference
    def annotate(u):
        names = set()
        for r in u["recs"]:
            names |= set(r["names"])
        u["names"] = sorted(names)
        u["side"] = side_from_names(names)
        u["group"] = u["recs"][0]["group"]
        u["subgroup"] = u["recs"][0]["subgroup"]
        u["points"] = u["verts"]
    for u in loaded:
        annotate(u)
        u["cortex"] = False
    for u in loaded_cx:
        annotate(u)
        u["cortex"] = True

    # ------------------------------------------------------------------ frame
    log.section("Units and anatomical frame (BodyParts3D raw -> mm, RAS)")
    frame = infer_frame(loaded + loaded_cx)
    for m in frame["messages"]:
        log(f"[warn] {m}")
    factor = frame["unit_factor_to_mm"]
    M = np.asarray(frame["matrix_raw_to_ras"])
    flip = frame["determinant"] < 0
    log(f"unit factor raw->mm : {factor}")
    if "vertebral_length_raw" in frame:
        log(f"vertebral column raw length {frame['vertebral_length_raw']:.3f} -> "
            f"{frame['vertebral_length_raw'] * factor:.1f} mm")
    log(f"frame applied       : {frame['applied']} (confidence: {frame['confidence']})")
    if frame["applied"]:
        log("rows (raw-space directions of Right, Anterior, Superior):")
        for r, nm in zip(M, "RAS"):
            log(f"   {nm}: [{r[0]:+.4f} {r[1]:+.4f} {r[2]:+.4f}]")
        log(f"raw axis angles (deg): {frame['raw_axis_angles_deg']}  det={frame['determinant']:+.3f}")

    def to_ras(v):
        return (v @ M.T) * factor

    # ------------------------------------------------------------------ geometry
    log.section("Geometry cleaning / optimization")
    weld_raw = WELD_TOLERANCE_MM / factor
    structures = []
    tot_before = tot_after = 0
    for u in loaded:
        v, f, st = clean_mesh(u["verts"], u["faces"], weld_raw)
        if flip:
            f = f[:, ::-1].copy()
        v = to_ras(v)
        budget = FACE_BUDGET.get(u["group"], DEFAULT_FACE_BUDGET)
        v, f, dec, why = decimate(v, f, budget)
        u.update(cv=v, cf=f, stats=st, decimated=dec, dec_note=why)
        tot_before += st["raw_faces"]
        tot_after += len(f)

    # names + deterministic ordering
    def sort_key(u):
        code = spine_code(u["recs"][0]["label"])
        return (GROUP_ORDER.index(u["group"]), code_order(code), u["recs"][0]["label"], u["key"])
    loaded.sort(key=sort_key)
    label_count = collections.Counter(u["recs"][0]["label"] for u in loaded)
    lab_seen = collections.defaultdict(int)
    for i, u in enumerate(loaded, 1):
        lab = u["recs"][0]["label"] if len(u["recs"]) == 1 else u["recs"][0]["label"] + "_x%d" % len(u["recs"])
        code = spine_code(u["recs"][0]["label"])
        cen = u["cv"].mean(0)
        side = u["side"]
        if not side and label_count[u["recs"][0]["label"]] > 1 and abs(cen[0]) > 1.0:
            side = "R" if cen[0] > 0 else "L"
        u["display_side"] = side
        base = sanitize(lab)
        if code and u["group"] in ("VERTEBRAE", "INTERVERTEBRAL_DISCS") and not base.startswith(code):
            base = f"{code}_{base}" if u["group"] == "VERTEBRAE" else f"{base}"
        if side and not re.search(r"(^|_)(left|right)(_|$)", base.lower()):
            base = f"{base}_{side}"
        u["name"] = f"{base}__{u['key']}"
        u["index"] = i

    # geometry statistics + writing
    mesh_dir = os.path.join(OUTPUT_DIR, "meshes")
    for g in GROUP_ORDER:
        os.makedirs(os.path.join(mesh_dir, g), exist_ok=True)
    manifest_structs = []
    for u in loaded:
        v, f = u["cv"], u["cf"]
        rel = os.path.join("meshes", u["group"], f"{u['index']:03d}_{u['name']}.ply")
        write_ply_binary(os.path.join(OUTPUT_DIR, rel), v, f)
        bb = [v.min(0).tolist(), v.max(0).tolist()]
        ext = (v.max(0) - v.min(0))
        st = u["stats"]
        log(f"{u['index']:03d} {u['group']:24s} {u['name'][:44]:44s} faces {st['raw_faces']:>7d} -> {len(f):>7d} "
            f"| closed={st['closed']} islands-={st['islands_removed']} dup-={st['duplicate']} "
            f"deg-={st['degenerate']}{' flipped' if st['flipped'] else ''}"
            f"{' DECIMATED' if u['decimated'] else ''} ext[mm]=({ext[0]:.1f},{ext[1]:.1f},{ext[2]:.1f})"
            f"{'  ' + u['dec_note'] if u['dec_note'] else ''}")
        manifest_structs.append({
            "index": u["index"], "name": u["name"], "label": u["recs"][0]["label"], "group": u["group"],
            "subgroup": u["subgroup"], "side": u["display_side"], "file": rel.replace("\\", "/"),
            "elements": u["fjs"], "concepts": sorted({c for r in u["recs"] for c in r["concepts"]}),
            "vertices": int(len(v)), "faces": int(len(f)), "raw_faces": int(st["raw_faces"]),
            "closed": bool(st["closed"]), "decimated": bool(u["decimated"]),
            "bbox_mm": bb, "centroid_mm": v.mean(0).tolist(), "is_muscle": False,
            "notes": sorted({n for r in u["recs"] for n in r["notes"]}),
        })
    log(f"\nfaces total (raw -> optimized): {tot_before} -> {tot_after}")
    if fast_simplification is None:
        log("[info] fast_simplification not installed: no decimation applied (pip install fast-simplification)")

    # ------------------------------------------------------------------ reference cloud (NOT a mesh)
    ref_pts = []
    for u in sorted(loaded_cx, key=lambda x: x["key"]):
        v, _, _ = clean_mesh(u["verts"], u["faces"], weld_raw)
        ref_pts.append(to_ras(v))
    ref_info = {"file": None, "points": 0, "elements": len(loaded_cx)}
    if ref_pts:
        allp = np.concatenate(ref_pts)
        sel = np.linspace(0, len(allp) - 1, min(REFERENCE_POINT_COUNT, len(allp))).astype(np.int64)
        os.makedirs(os.path.join(OUTPUT_DIR, "reference"), exist_ok=True)
        rp = os.path.join("reference", "cortex_reference_points.npz")
        np.savez_compressed(os.path.join(OUTPUT_DIR, rp), points=allp[sel].astype(np.float32))
        ref_info = {"file": rp.replace("\\", "/"), "points": int(len(sel)), "elements": len(loaded_cx),
                    "bbox_mm": [allp.min(0).tolist(), allp.max(0).tolist()]}
        log(f"\ncortex reference (registration only, not a model mesh): {len(loaded_cx)} elements, "
            f"{len(sel)} points, bbox {np.round(allp.min(0), 1).tolist()} .. {np.round(allp.max(0), 1).tolist()}")
    else:
        log("\n[warn] no cortex reference geometry could be loaded; the Blender script will fall back "
            "to landmarks / bounding boxes")

    # ------------------------------------------------------------------ landmarks + consistency checks
    landmarks = {}
    for u in loaded:
        for key, rx in LANDMARK_RX.items():
            if any(rx.search(n) for n in u["recs"][0]["own_names"]):
                s = u["display_side"] or "M"
                landmarks[f"{key}_{s}"] = u["cv"].mean(0).tolist()
    log(f"landmarks for registration: {sorted(landmarks)}")

    log.section("Anatomical sanity checks")
    by_group = collections.defaultdict(list)
    for u in loaded:
        by_group[u["group"]].append(u)
    cord = by_group.get("SPINAL_CORD", [])
    if cord:
        e = cord[0]["cv"].max(0) - cord[0]["cv"].min(0)
        log(f"spinal cord element extents [mm]: ({e[0]:.1f}, {e[1]:.1f}, {e[2]:.1f})")
        if min(e) < SPINAL_CORD_MIN_WIDTH_MM and sorted(e)[1] < SPINAL_CORD_MIN_WIDTH_MM:
            log(f"[WARN] the spinal-cord element is thinner than {SPINAL_CORD_MIN_WIDTH_MM} mm in two axes: "
                "it looks like a central-canal tube rather than a solid cord "
                "(the metadata registers the same file under both names).")
        bs = by_group.get("BRAINSTEM", [])
        if bs:
            zb = min(u["cv"][:, 2].min() for u in bs)
            zc = cord[0]["cv"][:, 2].max()
            log(f"brainstem lowest z = {zb:.1f} mm | spinal cord highest z = {zc:.1f} mm | "
                f"gap = {zb - zc:+.1f} mm  ({'overlap' if zb - zc < 0 else 'gap'})")
    verts_g = sorted(by_group.get("VERTEBRAE", []), key=lambda u: u["cv"][:, 2].mean(), reverse=True)
    discs = by_group.get("INTERVERTEBRAL_DISCS", [])
    if cord and verts_g:
        zc0, zc1 = cord[0]["cv"][:, 2].min(), cord[0]["cv"][:, 2].max()
        log(f"spinal cord z-range {zc0:.1f}..{zc1:.1f} mm vs vertebral column z-range "
            f"{min(u['cv'][:, 2].min() for u in verts_g):.1f}..{max(u['cv'][:, 2].max() for u in verts_g):.1f} mm")
    for d in discs:
        if not spine_code(d["recs"][0]["label"]):
            zc = d["cv"][:, 2].mean()
            above = [u for u in verts_g if u["cv"][:, 2].mean() > zc]
            below = [u for u in verts_g if u["cv"][:, 2].mean() <= zc]
            ua = spine_code(above[-1]["recs"][0]["label"]) if above else "?"
            ub = spine_code(below[0]["recs"][0]["label"]) if below else "?"
            note = (f"disc '{d['recs'][0]['label']}' ({d['key']}) has no level in the metadata; by geometry it lies "
                    f"between {ua} and {ub} (derived, not metadata)")
            log(f"[info] {note}")
            for ms in manifest_structs:
                if ms["index"] == d["index"]:
                    ms["notes"].append(note)

    # ------------------------------------------------------------------ requested-anatomy checklist
    log.section("Requested anatomy: found / missing")
    cnt = collections.Counter((u["group"], u["subgroup"]) for u in loaded)
    missing = []

    def check(label, got, expected=None):
        ok = got >= (expected if expected else 1)
        log(f"   [{'ok' if ok else 'MISSING'}] {label}: {got}" + (f" / {expected}" if expected else ""))
        if not ok:
            missing.append(label)
    check("cervical vertebrae (atlas, axis, C3-C7)", cnt[("VERTEBRAE", "cervical")], 7)
    check("thoracic vertebrae", cnt[("VERTEBRAE", "thoracic")], 12)
    check("lumbar vertebrae", cnt[("VERTEBRAE", "lumbar")], 5)
    check("sacrum", cnt[("VERTEBRAE", "sacral")], 1)
    n_coccyx = len([c for c, n in meta.name.items() if COCCYX_RX.search(n.lower())
                    and meta.elements["partof"].get(c)])
    check("coccyx (present in metadata)", n_coccyx, 1)
    check("intervertebral discs (C2-C3 ... L5-S1 = 23 expected)", len(discs), 23)
    check("spinal cord", len(cord), 1)
    n_sn = len([c for c, n in meta.name.items() if SPINAL_NERVE_SEARCH_RX.search(n.lower())])
    check("spinal nerves / roots / cauda equina (concepts in metadata)", n_sn, 1)
    log("   [info] spinal-associated cartilage: only the intervertebral discs (articular disk of symphysis) "
        "exist in the metadata; costal/nasal/laryngeal cartilage belongs to unrelated anatomy and is not exported")
    check("cerebellum", cnt[("CEREBELLUM", "cerebellum")])
    check("midbrain", cnt[("BRAINSTEM", "midbrain")])
    check("pons", cnt[("BRAINSTEM", "pons")])
    check("medulla oblongata", cnt[("BRAINSTEM", "medulla_oblongata")])
    for key in LANDMARK_RX:
        check(f"{key} (deep structure)", sum(1 for k in landmarks if k.startswith(key + "_")), 2)
    check("hypothalamus / diencephalon pieces", cnt[("SUBCORTICAL_STRUCTURES", "deep_gray_matter")])
    if cnt[("OTHER_BRAIN_STRUCTURES", "ventricular_system")] == 0 and INCLUDE_VENTRICULAR_SYSTEM:
        missing.append("ventricular system")
    for r in amb:
        log(f"   [ambiguous - not exported] {r['fj']} {r['label']}: {r['reason']}")
    for u in missing_files:
        missing.append("mesh file for " + ", ".join(r["label"] for r in u["recs"]))

    # ------------------------------------------------------------------ manifest
    manifest = {
        "schema": 1,
        "dataset": {"base_path": BODYPARTS3D_BASE_PATH, "metadata_files": files, "mesh_source": mode,
                    "obj_files_found": index.count, "elements_in_dataset": len(meta.all_fjs)},
        "frame": {"unit_factor_raw_to_mm": factor, "applied": frame["applied"],
                  "confidence": frame["confidence"], "matrix_raw_to_ras": frame["matrix_raw_to_ras"],
                  "determinant": frame["determinant"], "messages": frame["messages"],
                  "output_space": "RAS, millimetres (x=Right, y=Anterior, z=Superior)"},
        "structures": manifest_structs,
        "reference": ref_info,
        "landmarks_mm": landmarks,
        "excluded": {
            "muscle_elements_in_dataset": len(muscle),
            "muscle_elements_in_scope": [r["fj"] for r in exc_muscle],
            "cortex_duplicates": [{"element": r["fj"], "label": r["label"]} for r in exc_cortex],
            "other": [{"element": r["fj"], "label": r["label"], "reason": r["reason"]} for r in exc_other],
        },
        "ambiguous": [{"element": r["fj"], "label": r["label"], "reason": r["reason"]} for r in amb],
        "missing": missing,
        "options": {"ventricles": INCLUDE_VENTRICULAR_SYSTEM, "white_matter": INCLUDE_CEREBRAL_WHITE_MATTER,
                    "cranial_nerves": INCLUDE_CRANIAL_NERVES},
    }
    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)

    log.section("Summary")
    log(f"exported pieces        : {len(loaded)}")
    for g in GROUP_ORDER:
        n = sum(1 for u in loaded if u["group"] == g)
        if n:
            log(f"   {g:26s}{n}")
    log(f"muscle structures      : excluded ({len(muscle)} muscle elements in dataset, "
        f"{len(exc_muscle)} inside requested scope); exported muscle pieces: 0")
    log(f"missing / not available: {missing if missing else 'none'}")
    log(f"ambiguous (excluded)   : {len(amb)}")
    log(f"output location        : {OUTPUT_DIR}")
    log.save(os.path.join(OUTPUT_DIR, "report.txt"))
    return 0


if __name__ == "__main__":
    sys.exit(main())