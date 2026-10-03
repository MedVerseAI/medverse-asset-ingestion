import bpy
import os
import csv


# CONFIG
BASE_PATH = r"C:\University\Graduation Project\BodyParts3D_data"

PARTS_FILE = os.path.join(BASE_PATH, "isa_parts_list_e.txt")
ELEMENTS_FILE = os.path.join(BASE_PATH, "isa_element_parts.txt")
OBJ_DIR = os.path.join(BASE_PATH, "IS-A\isa_BP3D_4.0_obj_99")


# BRAIN
BRAIN_FMA = {
    "FMA55676": "segment of brain",
    "FMA61815": "cardinal segment of brain",

    # Cerebrum / Cerebral Hemisphere
    "FMA61820": "segment of cerebral hemisphere",
    "FMA61823": "lobe of cerebral hemisphere",
    "FMA81150": "lobule of cerebral hemisphere",
    "FMA62466": "capsule of cerebral hemisphere",

    # Cerebral Cortex / Gyri
    "FMA242193": "region of cerebral cortex",
    "FMA61857": "superior frontal gyrus",
    "FMA61859": "middle frontal gyrus",
    "FMA61860": "inferior frontal gyrus",
    "FMA61894": "precentral gyrus",
    "FMA61896": "postcentral gyrus",
    "FMA61897": "supramarginal gyrus",
    "FMA61898": "angular gyrus",
    "FMA61906": "middle temporal gyrus",
    "FMA61907": "inferior temporal gyrus",
    "FMA61908": "fusiform gyrus",
    "FMA61918": "parahippocampal gyrus",
    "FMA62434": "cingulate gyrus",
    "FMA256194": "orbital gyrus",

    # Right / Left Gyri
    "FMA72653": "right superior frontal gyrus",
    "FMA72654": "left superior frontal gyrus",
    "FMA72655": "right middle frontal gyrus",
    "FMA72656": "left middle frontal gyrus",
    "FMA72657": "right inferior frontal gyrus",
    "FMA72658": "left inferior frontal gyrus",

    "FMA72661": "right precentral gyrus",
    "FMA72662": "left precentral gyrus",
    "FMA72665": "right postcentral gyrus",
    "FMA72666": "left postcentral gyrus",

    "FMA72667": "right supramarginal gyrus",
    "FMA72668": "left supramarginal gyrus",
    "FMA72669": "right angular gyrus",
    "FMA72670": "left angular gyrus",

    "FMA72685": "right middle temporal gyrus",
    "FMA72686": "left middle temporal gyrus",
    "FMA72687": "right inferior temporal gyrus",
    "FMA72688": "left inferior temporal gyrus",

    "FMA72689": "right fusiform gyrus",
    "FMA72690": "left fusiform gyrus",

    "FMA72705": "right parahippocampal gyrus",
    "FMA72706": "left parahippocampal gyrus",

    "FMA72717": "right cingulate gyrus",
    "FMA72718": "left cingulate gyrus",

    "FMA70701": "anterior part of superior temporal gyrus",
    "FMA70703": "posterior part of superior temporal gyrus",
    "FMA72800": "anterior part of right superior temporal gyrus",
    "FMA72801": "anterior part of left superior temporal gyrus",
    "FMA72804": "posterior part of right superior temporal gyrus",
    "FMA72805": "posterior part of left superior temporal gyrus",

    # Limbic / Deep Brain Structures
    "FMA62493": "hippocampus",
    "FMA72713": "right hippocampus",
    "FMA72714": "left hippocampus",

    "FMA61841": "amygdala",
    "FMA72832": "right amygdala",
    "FMA72833": "left amygdala",

    "FMA61842": "septum of telencephalon",
    "FMA62514": "basal ganglion of telencephalon",

    "FMA61965": "fornix of forebrain",
    "FMA61970": "commissure of fornix of forebrain",
    "FMA72924": "right fornix of forebrain",
    "FMA72925": "left fornix of forebrain",

    "FMA61950": "internal capsule",
    "FMA72906": "right internal capsule",
    "FMA72907": "left internal capsule",

    "FMA86464": "corpus callosum",

    # Diencephalon
    "FMA62007": "thalamus",
    "FMA258714": "right thalamus",
    "FMA258716": "left thalamus",

    "FMA62008": "hypothalamus",

    "FMA62032": "habenula",
    "FMA62033": "pineal body",
    "FMA74877": "mammillary body",

    "FMA62209": "lateral geniculate body",
    "FMA62211": "medial geniculate body",

    "FMA73303": "right lateral geniculate body",
    "FMA73304": "left lateral geniculate body",
    "FMA73309": "right medial geniculate body",
    "FMA73310": "left medial geniculate body",

    "FMA62080": "stria medullaris of thalamus",
    "FMA73413": "right stria medullaris of thalamus",
    "FMA73414": "left stria medullaris of thalamus",

    # Brainstem
    "FMA61993": "midbrain",
    "FMA61997": "segment of midbrain",
    "FMA62394": "peduncle of midbrain",
    "FMA62398": "segment of midbrain tectum",

    "FMA67943": "pons",
    "FMA62004": "medulla oblongata",
    "FMA61998": "segment of hindbrain",

    # Colliculi
    "FMA62403": "superior colliculus",
    "FMA62404": "inferior colliculus",

    "FMA73422": "right superior colliculus",
    "FMA73423": "left superior colliculus",
    "FMA73434": "right inferior colliculus",
    "FMA73435": "left inferior colliculus",

    "FMA72417": "brachium of superior colliculus",
    "FMA71114": "brachium of inferior colliculus",

    "FMA73461": "brachium of right superior colliculus",
    "FMA73462": "brachium of left superior colliculus",
    "FMA73463": "brachium of right inferior colliculus",
    "FMA73464": "brachium of left inferior colliculus",

    # Cerebellum
    "FMA67944": "cerebellum",

    # White / Gray Matter
    "FMA241998": "cerebral white matter",
    "FMA256174": "region of cerebral white matter",
    "FMA260791": "white matter of right cerebral hemisphere",
    "FMA260794": "white matter of left cerebral hemisphere",

    "FMA67242": "gray matter of neuraxis",
    "FMA83912": "gray matter of diencephalon",
    "FMA83915": "gray matter of hypothalamus",

    "FMA83929": "white matter of neuraxis",
    "FMA83930": "white matter of telencephalon",

    # Brain Ventricular System
    "FMA78447": "region of ventricular system of brain",
    "FMA78448": "lateral ventricle",
    "FMA78449": "right lateral ventricle",
    "FMA78450": "left lateral ventricle",
    "FMA78454": "third ventricle",
    "FMA78467": "cerebral aqueduct",
    "FMA78469": "fourth ventricle",

    "FMA242770": "region of wall of ventricular system of neuraxis",
    "FMA242789": "region of ventricular system of neuraxis",
    "FMA78497": "central canal of spinal cord",

    # Choroid Plexus
    "FMA61934": "choroid plexus of cerebral hemisphere",

    # Brain / Neuraxis General Structures
    "FMA62374": "segment of telencephalon",
    "FMA61996": "segment of forebrain",
    "FMA67951": "lamina of cerebral hemisphere",
    "FMA67957": "segment of gyrus of cerebral hemisphere",

    "FMA83840": "nucleus of brain",
    "FMA83686": "nucleus of neuraxis",
    "FMA83854": "stria of neuraxis",
    "FMA83856": "lamina of neuraxis",
    "FMA83857": "brachium of neuraxis",
    "FMA83860": "peduncle of neuraxis",
    "FMA83865": "fornix of neuraxis",
    "FMA83874": "gyrus of neuraxis",
    "FMA83904": "septum of neuraxis",
    "FMA83906": "commissure of neuraxis",

    "FMA256237": "segment of neuraxis",
    "FMA83143": "cell part cluster of neuraxis",
    "FMA83153": "organ component of neuraxis",
    "FMA83465": "segment of white matter of neuraxis",
    "FMA84054": "zone of neuraxis",
    "FMA84059": "nuclear complex of neuraxis",
    "FMA84081": "circumventricular organ of neuraxis",

    # Optic System
    "FMA62045": "optic chiasm",
    "FMA62046": "optic tract",
    "FMA62382": "right optic tract",
    "FMA67936": "left optic tract",

    # Meningeal Structures
    "FMA71235": "region of dura mater",
    "FMA266054": "subdivision of cranial dura mater",
    "FMA83966": "tentorium cerebelli",
    "FMA84881": "subdivision of subarachnoid space",
}

# NERVOUS SYSTEM / NERVES / GANGLIA
NERVOUS_SYSTEM_FMA = {
    # Nervous System
    "FMA45638": "subdivision of nervous system",
    "FMA65132": "nerve",
    "FMA5913": "nerve trunk",

    # Autonomic Nervous System
    "FMA65539": "subdivision of parasympathetic nervous system",
    "FMA65551": "subdivisionof autonomic nervous system",

    # Ganglia
    "FMA5884": "ganglion",
    "FMA5889": "autonomic ganglion",
    "FMA5894": "parasympathetic ganglion",
    "FMA5895": "cranial parasympathetic ganglion",

    "FMA6964": "ciliary ganglion",
    "FMA53549": "right ciliary ganglion",
    "FMA53550": "left ciliary ganglion",

    # Cranial Nerve Structures
    "FMA5865": "cranial nerve",
    "FMA52570": "branch of cranial nerve",

    # Optic Nerve
    "FMA50863": "optic nerve",
    "FMA50875": "right optic nerve",
    "FMA50878": "left optic nerve",

    # Trochlear Nerve
    "FMA50865": "trochlear nerve",
    "FMA50881": "right trochlear nerve",
    "FMA50882": "left trochlear nerve",

    # Oculomotor Nerve
    "FMA52571": "branch of oculomotor nerve",
    "FMA52572": "superior branch of oculomotor nerve",
    "FMA52573": "inferior branch of oculomotor nerve",
    "FMA52574": "superior branch of right oculomotor nerve",
    "FMA52575": "superior branch of left oculomotor nerve",
    "FMA52576": "inferior branch of right oculomotor nerve",
    "FMA52577": "inferior branch of left oculomotor nerve",

    # Trigeminal / Ophthalmic Division
    "FMA52607": "branch of trigeminal nerve",
    "FMA52621": "ophthalmic nerve",
    "FMA52622": "right ophthalmic nerve",
    "FMA52623": "left ophthalmic nerve",

    "FMA52628": "lacrimal nerve",
    "FMA52629": "right lacrimal nerve",
    "FMA52630": "left lacrimal nerve",

    "FMA52638": "frontal nerve",
    "FMA52639": "right frontal nerve",
    "FMA52640": "left frontal nerve",

    "FMA52642": "supratrochlear nerve",
    "FMA52643": "right supratrochlear nerve",
    "FMA52644": "left supratrochlear nerve",

    "FMA52655": "supra-orbital nerve",
    "FMA52656": "right supra-orbital nerve",
    "FMA52657": "left supra-orbital nerve",

    "FMA52668": "nasociliary nerve",
    "FMA52669": "right nasociliary nerve",
    "FMA52670": "left nasociliary nerve",

    "FMA52675": "anterior ethmoidal nerve",
    "FMA52676": "right anterior ethmoidal nerve",
    "FMA52677": "left anterior ethmoidal nerve",

    "FMA52691": "long ciliary nerve",
    "FMA82734": "right long ciliary nerve",
    "FMA82735": "left long ciliary nerve",

    "FMA52693": "infratrochlear nerve",
    "FMA52698": "right infratrochlear nerve",
    "FMA52699": "left infratrochlear nerve",

    "FMA52714": "posterior ethmoidal nerve",
    "FMA52715": "right posterior ethmoidal nerve",
    "FMA52716": "left posterior ethmoidal nerve",

    # Ciliary Ganglion Connections
    "FMA7037": "branch of ciliary ganglion",
    "FMA7041": "short ciliary nerve",

    "FMA52672": "communicating branch of nasociliary nerve with ciliary ganglion",
    "FMA52673": "communicating branch of right nasociliary nerve with right ciliary ganglion",
    "FMA52674": "communicating branch of left nasociliary nerve with left ciliary ganglion",
}


# TARGET FMA
TARGET_FMA = set(BRAIN_FMA.keys()) | set(NERVOUS_SYSTEM_FMA.keys())


# CHECK PATHS
if not os.path.isfile(PARTS_FILE):
    raise FileNotFoundError(f"Missing file:\n{PARTS_FILE}")

if not os.path.isfile(ELEMENTS_FILE):
    raise FileNotFoundError(f"Missing file:\n{ELEMENTS_FILE}")

if not os.path.isdir(OBJ_DIR):
    raise FileNotFoundError(f"Missing OBJ folder:\n{OBJ_DIR}")


# READ FMA -> NAME
fma_names = {}

with open(PARTS_FILE, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f, delimiter="\t")

    for row in reader:
        fma = row["concept id"].strip()

        if fma in TARGET_FMA:
            fma_names[fma] = row["en"].strip()


# READ FMA -> ELEMENT FILE IDs
fma_elements = {}

with open(ELEMENTS_FILE, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f, delimiter="\t")

    for row in reader:
        fma = row["concept id"].strip()
        element_id = row["element file id"].strip()

        if fma in TARGET_FMA:
            fma_elements.setdefault(fma, []).append(element_id)


main_collections = {}

for main_collection_name in ["Brain", "Nervous System"]:

    if main_collection_name in bpy.data.collections:
        main_collection = bpy.data.collections[main_collection_name]
    else:
        main_collection = bpy.data.collections.new(main_collection_name)
        bpy.context.scene.collection.children.link(main_collection)

    main_collections[main_collection_name] = main_collection



def import_obj(filepath):

    before = set(bpy.context.scene.objects)

    try:
        bpy.ops.wm.obj_import(filepath=filepath)

    except Exception as e:
        print(f"[ERROR] فشل استيراد {filepath}: {e}")
        return []

    after = set(bpy.context.scene.objects)

    return list(after - before)


# IMPORT STRUCTURES
structures = []


# IMPORT BRAIN
for fma, custom_name in BRAIN_FMA.items():

    element_ids = fma_elements.get(fma, [])

    if not element_ids:
        print(f"[WARNING] مفيش ملفات OBJ لـ: {fma} - {custom_name}")
        continue

    collection_name = custom_name

    if collection_name in bpy.data.collections:
        collection = bpy.data.collections[collection_name]
    else:
        collection = bpy.data.collections.new(collection_name)
        main_collections["Brain"].children.link(collection)

    imported_objects = []

    for element_id in element_ids:

        obj_path = os.path.join(OBJ_DIR, element_id + ".obj")

        if not os.path.isfile(obj_path):
            print(f"[MISSING] {element_id}.obj")
            continue

        objects = import_obj(obj_path)

        for obj in objects:

            obj.name = f"{custom_name} | {element_id}"

            for old_collection in list(obj.users_collection):
                old_collection.objects.unlink(obj)

            collection.objects.link(obj)

            imported_objects.append(obj)

    if imported_objects:

        structures.append({
            "system": "Brain",
            "fma": fma,
            "name": custom_name,
            "objects": imported_objects
        })

        print(
            f"[OK] Brain | {custom_name} "
            f"({fma}) - {len(imported_objects)} ملف"
        )


# IMPORT NERVOUS SYSTEM / NERVES / GANGLIA
for fma, custom_name in NERVOUS_SYSTEM_FMA.items():

    element_ids = fma_elements.get(fma, [])

    if not element_ids:
        print(f"[WARNING] مفيش ملفات OBJ لـ: {fma} - {custom_name}")
        continue

    collection_name = custom_name

    if collection_name in bpy.data.collections:
        collection = bpy.data.collections[collection_name]
    else:
        collection = bpy.data.collections.new(collection_name)
        main_collections["Nervous System"].children.link(collection)

    imported_objects = []

    for element_id in element_ids:

        obj_path = os.path.join(OBJ_DIR, element_id + ".obj")

        if not os.path.isfile(obj_path):
            print(f"[MISSING] {element_id}.obj")
            continue

        objects = import_obj(obj_path)

        for obj in objects:

            obj.name = f"{custom_name} | {element_id}"

            for old_collection in list(obj.users_collection):
                old_collection.objects.unlink(obj)

            collection.objects.link(obj)

            imported_objects.append(obj)

    if imported_objects:

        structures.append({
            "system": "Nervous System",
            "fma": fma,
            "name": custom_name,
            "objects": imported_objects
        })

        print(
            f"[OK] Nervous System | {custom_name} "
            f"({fma}) - {len(imported_objects)} ملف"
        )


# SELECT ALL IMPORTED OBJECTS
for obj in bpy.context.scene.objects:
    obj.select_set(False)

for structure in structures:

    for obj in structure["objects"]:
        obj.select_set(True)

if structures and structures[0]["objects"]:
    bpy.context.view_layer.objects.active = structures[0]["objects"][0]


brain_count = sum(
    1 for s in structures
    if s["system"] == "Brain"
)

nervous_count = sum(
    1 for s in structures
    if s["system"] == "Nervous System"
)

print("\n========================================")
print("BRAIN + NERVOUS SYSTEM IMPORT COMPLETE")
print("========================================")

print(
    f"Brain structures: "
    f"{brain_count} / {len(BRAIN_FMA)}"
)

print(
    f"Nervous System structures: "
    f"{nervous_count} / {len(NERVOUS_SYSTEM_FMA)}"
)

print(
    f"Total imported structures: "
    f"{len(structures)} / {len(TARGET_FMA)}"
)

print("----------------------------------------")

for s in structures:

    print(
        f"  - [{s['system']}] "
        f"{s['name']} ({s['fma']})"
    )

print("========================================")