"""
anat_config.py
--------------
ALL settings / constants / regex rules for the two pipelines in ONE place.
Edit the two base paths below; everything else is optional.

Used by:  anat_helpers.py, anat_classes.py, export_bodyparts3d.py, integrate_brainnetome_bodyparts3d.py
(pure python, no bpy / numpy needed)
"""
import os
import re
import collections

# ============================================================================
# PATHS  (the only two things you normally have to edit)
# ============================================================================
# Project root = parent of the "scripts" folder. Override with env var ANAT_PROJECT_ROOT
# (useful when running from Blender's text editor where __file__ is not the script path).
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = os.getcwd()
PROJECT_ROOT = os.environ.get("ANAT_PROJECT_ROOT") or os.path.dirname(_HERE)

# ---- INPUTS: read-only, everything lives under data/ ----
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
BRAINNETOME_BASE_PATH = os.path.join(DATA_DIR, "HumanBrainnetome")
BODYPARTS3D_BASE_PATH = os.path.join(DATA_DIR, "BodyParts3D")
BN_NII_DIR = os.path.join(BRAINNETOME_BASE_PATH, "nii_gz_data")
BN_LUT_PATH = os.path.join(BRAINNETOME_BASE_PATH, "BN_Atlas_freesurfer", "BN_Atlas_246_LUT.txt")

# ---- OUTPUTS: everything generated is written under outputs/ ----
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
BN_PIECES_DIR = os.path.join(OUTPUTS_DIR, "voxel_export_pieces")     # Brainnetome PLY pieces
OUTPUT_DIR = os.path.join(OUTPUTS_DIR, "bp3d_export_pieces")         # BodyParts3D meshes + manifest.json
BP3D_EXPORT_DIR = OUTPUT_DIR
REPORTS_DIR = os.path.join(OUTPUTS_DIR, "reports")                   # log / report .txt files
FINAL_DIR = os.path.join(OUTPUTS_DIR, "final")                       # final .blend / exports


def ensure_output_dirs():
    """Create every output folder (call at the start of each pipeline)."""
    for d in (OUTPUTS_DIR, BN_PIECES_DIR, OUTPUT_DIR, REPORTS_DIR, FINAL_DIR):
        os.makedirs(d, exist_ok=True)


def check_inputs():
    """Return a list of missing input paths (empty list = all good)."""
    need = [BRAINNETOME_BASE_PATH, BODYPARTS3D_BASE_PATH, BN_LUT_PATH]
    return [p for p in need if not os.path.exists(p)]

# ============================================================================
# EXPORT_BODYPARTS3D  --  selection / geometry / frame inference
# ============================================================================
# Folder holding the six metadata .txt files. None -> searched recursively under the base path.
METADATA_DIR = None
# Where the .obj meshes live. None -> whole base path is scanned recursively.
OBJ_SEARCH_DIR = None

# "element": one mesh per element file (FJxxxx.obj)   <- preferred, finest control
# "concept": one mesh per concept representation (BPxxxx.obj)
# "auto"   : element if >= 50 % of the selected elements resolve to files, else concept
MESH_SOURCE = "auto"

# --- optional content -------------------------------------------------------
INCLUDE_VENTRICULAR_SYSTEM = True       # lateral/3rd/4th ventricles, aqueduct, choroid plexus
INCLUDE_CEREBRAL_WHITE_MATTER = True    # white matter, internal capsule, corpus callosum, fornix ...
INCLUDE_CRANIAL_NERVES = False          # only orbital/cranial branches exist in the metadata
AMBIGUOUS_INCLUDE_PATTERNS = [r"^(left |right )?hippocampus$"]

# --- geometry -----------------------------------------------------------------
WELD_TOLERANCE_MM = 1e-3
COMPONENT_MIN_FRACTION = 0.005
COMPONENT_MIN_FACES = 50
DEFAULT_FACE_BUDGET = 50000
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
DECIMATION_AGGRESSIVENESS = 5
MAX_BBOX_DRIFT_MM = 1.0
REFERENCE_POINT_COUNT = 30000

# --- frame inference ------------------------------------------------------------
UNIT_CANDIDATE_FACTORS = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]   # raw unit -> mm
VERTEBRAL_COLUMN_LENGTH_RANGE_MM = (350.0, 900.0)
AXIS_ORTHOGONALITY_TOLERANCE_DEG = 25.0
SPINAL_CORD_MIN_WIDTH_MM = 5.0

# --- classification rules (matched against lower-case concept names) ---------------
GROUP_ORDER = ["CEREBELLUM", "BRAINSTEM", "SUBCORTICAL_STRUCTURES", "OTHER_BRAIN_STRUCTURES",
               "CRANIAL_NERVES", "VERTEBRAE", "INTERVERTEBRAL_DISCS", "SPINAL_CORD"]

MUSCLE_ROOT_NAMES = {"muscle organ"}
MUSCLE_NAME_RX = re.compile(r"\bmuscle|muscul(?!oskeletal)|myocardi|sphincter|diaphragm")

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
# INTEGRATE_BRAINNETOME_BODYPARTS3D  --  registration / placement / scene
# ============================================================================
# --- Brainnetome ------------------------------------------------------------
BN_CORTICAL_MAX_ID = 210          # ids 1..210 cortical; 211+ subcortical
BN_REGION_GAP_SCALE = 1.0         # 0.96 = visible gaps between regions, 1.0 = watertight neighbours
BN_LANDMARK_NAME_RX = collections.OrderedDict([
    ("thalamus", r"tha_"),
    ("caudate", r"^(vca|dca)_"),
    ("putamen", r"^(vmpu|dlpu)_"),
    ("globus_pallidus", r"^gp_"),
    ("amygdala", r"amyg"),
    ("hippocampus", r"hipp"),
])
BP3D_LANDMARK_LABEL_RX = collections.OrderedDict([
    ("thalamus", r"^(left |right )?thalamus$"),
    ("caudate", r"^(left |right )?caudate nucleus$"),
    ("putamen", r"^(left |right )?putamen$"),
    ("globus_pallidus", r"^(left |right )?globus pallidus$"),
    ("amygdala", r"^(left |right )?amygdala$"),
    ("hippocampus", r"^(left |right )?hippocampus$"),
])

# --- registration -------------------------------------------------------------
REG_SCALE_MODE = "fit_inside"     # "fit_inside" | "match_mean"
REG_USE_ICP = True
REG_SAMPLE_POINTS = 6000
REG_ICP_ITERATIONS = 40
REG_ICP_TRIM_FRACTION = 0.75
REG_ICP_SCALE_BOUNDS = (0.85, 1.15)
REG_MAX_ROTATION_DEG = 20.0
REG_HARD_SCALE_LIMITS = (0.7, 1.5)
REG_MANUAL_SCALE = None
REG_MANUAL_TRANSLATION_MM = (0.0, 0.0, 0.0)
REG_MANUAL_ROTATION_DEG = (0.0, 0.0, 0.0)

# --- final placement ------------------------------------------------------------
ORIENT_MODEL_TO_ATLAS = True
CENTER_ON = "model_bbox"          # "model_bbox" | "cortex_bbox"
BLENDER_UNITS_PER_MM = 0.001
CLEAR_PREVIOUS_MODEL = True
SET_SOLID_MATERIAL_VIEWPORT = True

# --- guards -----------------------------------------------------------------------
MUSCLE_GUARD_RX = re.compile(r"\bmuscle|muscul(?!oskeletal)|myocardi|sphincter|diaphragm")
CORTEX_GUARD_RX = re.compile(r"\bgyrus\b|\bgyri\b|\blobule\b|(frontal|parietal|temporal|occipital|limbic) lobe|"
                             r"\binsula\b|^cortex of|cerebral cortex|prefrontal cortex")
CORTEX_GUARD_EXCEPT_RX = re.compile(r"hippocamp|archicortex")

# --- scene structure -----------------------------------------------------------------
ROOT_NAME = "ANATOMICAL_MODEL"
GROUP_TO_COLLECTIONS = {              # manifest group -> (system, collection)
    "CEREBELLUM": ("BRAIN", "CEREBELLUM"),
    "BRAINSTEM": ("BRAIN", "BRAINSTEM"),
    "SUBCORTICAL_STRUCTURES": ("BRAIN", "SUBCORTICAL_STRUCTURES"),
    "OTHER_BRAIN_STRUCTURES": ("BRAIN", "OTHER_BRAIN_STRUCTURES"),
    "CRANIAL_NERVES": ("BRAIN", "CRANIAL_NERVES"),
    "VERTEBRAE": ("SPINAL_SYSTEM", "VERTEBRAE"),
    "INTERVERTEBRAL_DISCS": ("SPINAL_SYSTEM", "INTERVERTEBRAL_DISCS"),
    "SPINAL_CORD": ("SPINAL_SYSTEM", "SPINAL_CORD"),
    "SPINAL_NERVES": ("SPINAL_SYSTEM", "SPINAL_NERVES"),
}
BP3D_COLORS = {
    ("VERTEBRAE", None): (0.86, 0.82, 0.70, 1.0),
    ("INTERVERTEBRAL_DISCS", None): (0.30, 0.52, 0.72, 1.0),
    ("SPINAL_CORD", None): (0.95, 0.88, 0.50, 1.0),
    ("CEREBELLUM", None): (0.72, 0.55, 0.48, 1.0),
    ("BRAINSTEM", None): (0.78, 0.66, 0.58, 1.0),
    ("SUBCORTICAL_STRUCTURES", None): (0.66, 0.48, 0.55, 1.0),
    ("OTHER_BRAIN_STRUCTURES", None): (0.85, 0.85, 0.80, 1.0),
    ("OTHER_BRAIN_STRUCTURES", "white_matter"): (0.92, 0.91, 0.86, 1.0),
    ("OTHER_BRAIN_STRUCTURES", "ventricular_system"): (0.35, 0.60, 0.90, 1.0),
    ("CRANIAL_NERVES", None): (0.95, 0.80, 0.30, 1.0),
}
MATERIAL_PREFIX = "ANAT_"