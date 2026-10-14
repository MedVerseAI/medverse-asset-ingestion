# Foundational Model: Identifiers and Schema

How the BodyParts3D identifiers (`FMA`, `BP`, `FJ`) relate to each other, and how they map to the files in this repository.

- Where to get the files and where they live: [`download_and_layout.md`](../data/download_and_layout.md)
- Columns, keys, counts and pitfalls of every input table: [`data_dictionary.md`](../data/data_dictionary.md)
- Licensing and attribution: [`sources_and_licensing.md`](../data/sources_and_licensing.md)

---

## 1. Purpose

BodyParts3D uses several identifiers to describe anatomical structures and their 3D representations.

The most important identifiers are:

- **FMA**: Anatomical concept identifier
- **BP**: Representation identifier
- **FJ**: 3D mesh element identifier

These identifiers should not be treated as a simple one-to-one chain. Instead, they form a connected data model in which anatomical concepts, representation contexts, relationships, and 3D mesh elements are linked together.

---

## 2. Identifier Types

| Identifier | Meaning | Example | Represents |
|---|---|---|---|
| `FMA<digits>` | Anatomical Concept ID | `FMA3736` | An anatomical structure/concept |
| `BP<digits>` | Representation ID | `BP10408` | A representation of an anatomical concept within one tree (IS-A or PART-OF) |
| `FJ<4 digits>` or `FJ<4 digits>M` | Element/Mesh ID | `FJ3413`, `FJ1456M` | An actual 3D mesh element, stored as `<id>.obj` |

A simplified view is:

```text
FMA
 │
 │ anatomical concept
 ▼
BP
 │
 │ representation/context
 ▼
FJ
 │
 │ mesh file
 ▼
OBJ
```

However, this should not be interpreted as a strict one-to-one relationship.

An FMA concept has one BP representation **per tree** (so up to two: one IS-A, one PART-OF) and may be associated with one or more FJ mesh elements.

---

## 3. FMA: Anatomical Concept Identifier

### 3.1 What is FMA?

`FMA` identifies an anatomical concept.

For example:

```text
FMA3736 → ascending aorta
FMA3734 → aorta
FMA3784 → descending aorta
FMA3932 → brachiocephalic artery
```

The FMA identifier represents the **identity and meaning of the anatomical structure**, rather than its actual geometry.

For example:

```text
FMA3736
   │
   └── Ascending aorta
```

The same FMA concept can participate in different anatomical relationship structures.

### 3.2 FMA in the Dataset

FMA identifiers appear throughout the metadata tables.

For example, the PART-OF inclusion relation file contains:

```text
parent id | parent name | child id | child name

FMA3734 | aorta | FMA3736 | ascending aorta
```

This means:

```text
Aorta
 │
 └── Ascending aorta
```

Here:

- `FMA3734` identifies the aorta concept.
- `FMA3736` identifies the ascending aorta concept.

The relationship between them is represented separately from the mesh itself.

---

## 4. BP: Representation Identifier

### 4.1 What is BP?

`BP` identifies a representation of an anatomical concept within a particular representation structure (tree).

For example, the same anatomical concept has different BP identifiers in the two trees:

```text
FMA3736
   │
   ├── IS-A representation
   │      └── BP10329
   │
   └── PART-OF representation
          └── BP10408
```

Both representations refer to:

```text
FMA3736 → ascending aorta
```

but they belong to different representation contexts.

Within one tree, every concept appears exactly once in the parts list and has a unique BP.

### 4.2 Example: FMA3736

For the ascending aorta:

```text
FMA3736 → ascending aorta
```

The corresponding representations in the local dataset are:

```text
IS-A:
FMA3736 → BP10329

PART-OF:
FMA3736 → BP10408
```

Therefore:

```text
             FMA3736
          Ascending Aorta
               │
        ┌──────┴──────┐
        │             │
      IS-A         PART-OF
        │             │
    BP10329        BP10408
```

The BP identifiers provide the representation context, while FMA identifies the underlying anatomical concept.

---

## 5. FJ: 3D Element / Mesh Identifier

### 5.1 What is FJ?

`FJ` identifies an actual 3D element used by BodyParts3D.

For example:

```text
FJ3413
```

corresponds to:

```text
FJ3413.obj
```

This file contains the actual 3D geometry that can be imported into Blender, Unity, or another 3D application.

Therefore:

```text
FJ3413
   │
   └── FJ3413.obj
          │
          └── 3D geometry
```

### 5.2 FJ Is the Actual Mesh Layer

Unlike FMA and BP, the FJ identifier is directly associated with the 3D mesh asset.

For example:

```text
FMA3736
   │
   └── FJ3413
          │
          └── FJ3413.obj
```

The FMA tells us **what the structure is**.

The FJ tells us **which 3D element represents it**.

### 5.3 Elements vs. Compounds

In BodyParts3D only **atomic organs (ELEMENT)** are built as polygon meshes. **Compound organs (COMPOUND)** are defined as the sum of several elements and have no mesh of their own. The `*_element_parts.txt` tables list which elements make up each compound concept.

```text
COMPOUND concept (FMA)   →   no mesh of its own
        │
        └── sum of ELEMENTs (FJ)   →   one .obj each
```

---

## 6. Relationship Between FMA, BP, and FJ

The three identifiers can be understood as different layers:

```text
┌───────────────────────────┐
│          FMA              │
│   Anatomical Concept      │
│                           │
│   FMA3736                 │
│   Ascending Aorta         │
└─────────────┬─────────────┘
              │
              │ representation
              ▼
┌───────────────────────────┐
│           BP              │
│    Representation ID      │
│                           │
│   BP10329 / BP10408       │
└─────────────┬─────────────┘
              │
              │ element mapping
              ▼
┌───────────────────────────┐
│           FJ              │
│     Mesh Element ID       │
│                           │
│        FJ3413             │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│        FJ3413.obj         │
│       3D Geometry         │
└───────────────────────────┘
```

However, the actual dataset is not simply:

```text
FMA → BP → FJ
```

because:

- One FMA has a different BP in each tree (IS-A and PART-OF), so it has up to two BP representations.
- One FMA can be associated with multiple FJ elements.
- One FJ element can be referenced by multiple FMA concepts.
- IS-A and PART-OF provide different relationship contexts.

Therefore, the identifiers should be treated as **related entities linked by lookup tables** rather than a simple linear chain. Within each tree, the concept hierarchy itself is a strict tree: every concept has exactly one parent and each tree has one root (see section 8).

---

## 7. Dataset Files Related to the Identifiers

The six metadata tables are tab-delimited text files stored in `data/raw/bodyparts3d/metadata/` (`paths.BP3D_METADATA`). See [`data_dictionary.md`](../data/data_dictionary.md) for the full column definitions.

| Role | IS-A file | PART-OF file |
|---|---|---|
| Parts list (concept → BP → name) | `isa_parts_list_e.txt` | `partof_parts_list_e.txt` |
| Inclusion relations (parent → child) | `isa_inclusion_relation_list.txt` | `partof_inclusion_relation_list.txt` |
| Element parts (concept → FJ) | `isa_element_parts.txt` | `partof_element_parts.txt` |

### 7.1 Parts List

```text
isa_parts_list_e.txt
partof_parts_list_e.txt
```

The columns are:

```text
concept id | representation id | en
```

Example (PART-OF):

```text
FMA3734 | BP10374 | aorta
FMA3736 | BP10408 | ascending aorta
FMA3768 | BP10404 | arch of aorta
FMA3784 | BP10373 | descending aorta
```

This provides the relationship between an FMA concept and its BP representation in that tree.

For the same `concept id` the English name is identical in both trees, and only the `representation id` differs.

### 7.2 Inclusion Relations

```text
isa_inclusion_relation_list.txt
partof_inclusion_relation_list.txt
```

The columns are:

```text
parent id | parent name | child id | child name
```

Example (PART-OF):

```text
FMA3734 | aorta | FMA3736 | ascending aorta
```

Each file is a strict tree with one root:

| Tree | Root concept | Root ID |
|---|---|---|
| IS-A | anatomical entity | `FMA62955` |
| PART-OF | human body | `FMA20394` |

### 7.3 Element Parts (Concept → Mesh Elements)

```text
isa_element_parts.txt
partof_element_parts.txt
```

The columns are:

```text
concept id | name | element file id
```

**File format: one row per (concept, element) pair.** For example, in the IS-A file:

```text
FMA3710 | vascular tree | FJ2925
FMA3710 | vascular tree | FJ2933
FMA3710 | vascular tree | FJ2944
```

Each row represents one mapping between an anatomical concept and one FJ mesh element.

Grouped for readability (this is an illustration of the grouped result, not the file format):

```text
FMA3710 | vascular tree    | FJ2925, FJ2933, FJ2944, ...
FMA3711 | segment of artery | FJ2055, FJ2073, FJ2216, ...
FMA3714 | variant artery    | FJ3418
```

PART-OF example, grouped:

```text
FMA3734 | aorta            | FJ1931, FJ1932, FJ3411, FJ3413, FJ3427
FMA3736 | ascending aorta  | FJ3413
FMA3768 | arch of aorta    | FJ3411
FMA3784 | descending aorta | FJ1931, FJ1932, FJ3427
```

For example, the anatomical concept:

```text
FMA3736
ascending aorta
```

is associated with:

```text
FJ3413.obj
```

The name in column 2 always equals the name in the parts list.

### 7.4 Mesh Archives

```text
isa_BP3D_4.0_obj_99.zip      (IS-A,    136 MB)
partof_BP3D_4.0_obj_99.zip   (PART-OF,  62 MB)
```

Both archives hold Wavefront OBJ files named by element ID (for example `FJ3413.obj`) at 99 % polygon reduction. Each extracts into a nested folder; code should call `paths.bp3d_obj_dir("isa")` or `paths.bp3d_obj_dir("partof")` instead of building the path itself.

---

## 8. Relationship Structures

BodyParts3D contains two important relationship structures:

```text
IS-A
PART-OF
```

They answer different questions.

### IS-A

Answers:

> What type or category of anatomical structure is this?

Example:

```text
Anastomosis
     │
     └── Vascular anastomosis
          │
          ├── Arterial anastomosis
          └── Venous anastomosis
```

### PART-OF

Answers:

> What larger anatomical structure is this structure a part of?

Example:

```text
Aorta
 │
 ├── Ascending aorta
 ├── Arch of aorta
 └── Descending aorta
       │
       ├── Abdominal aorta
       └── Descending thoracic aorta
```

The two structures therefore describe different types of anatomical information.

---

## 9. One FMA Can Map to Multiple FJ Elements

An anatomical concept does not necessarily correspond to a single mesh file.

For example:

```text
FMA3734 → aorta
```

is associated with:

```text
FJ1931
FJ1932
FJ3411
FJ3413
FJ3427
```

Therefore:

```text
             FMA3734
                │
        ┌───────┼────────┬────────┐
        ▼       ▼        ▼        ▼
      FJ1931  FJ1932   FJ3411   FJ3413
                                   │
                                  FJ3427
```

The complete anatomical structure may therefore need to be assembled from multiple mesh elements.

This is important for the later mesh aggregation stage.

### 9.1 Element Lists Are Cumulative

A parent concept lists **every element of all its descendants**. This was checked on all parent concepts (1,254 in IS-A and 499 in PART-OF) with 0 violations. The root therefore lists every element in its tree.

```text
FMA3734 aorta            → FJ1931, FJ1932, FJ3411, FJ3413, FJ3427
 ├── FMA3736 ascending   → FJ3413
 ├── FMA3768 arch        → FJ3411
 └── FMA3784 descending  → FJ1931, FJ1932, FJ3427
```

To find the **most specific** concept of an element, pick the concept with the **fewest** elements. The export script does this.

---

## 10. One FJ Can Be Referenced by Multiple Concepts

The relationship can also work in the opposite direction.

For example:

```text
FMA3734 → FJ3413
FMA3736 → FJ3413
```

Here:

```text
             ┌── FMA3734
             │
FJ3413 ──────┤
             │
             └── FMA3736
```

This means that the same mesh element can participate in the representation of multiple anatomical concepts.

There are two reasons this happens:

1. **Cumulative lists** (section 9.1): an ancestor lists the elements of its descendants, as `FMA3734` does with `FJ3413` above.
2. **Shared files across names**: the spinal cord (`FMA7647`) and the central canal of the spinal cord (`FMA78497`) both list the single element `FJ1737`.

Observed upper bound in BodyParts3D v4.0: one element is listed by up to **20** concepts in IS-A and **38** in PART-OF.

Therefore, FJ should be treated as a reusable mesh asset identifier rather than assuming that:

```text
1 FMA = 1 FJ
```

---

## 11. IS-A and PART-OF Can Reference the Same FJ

The same FJ element may appear in both relationship structures.

For example:

```text
FMA3736
Ascending Aorta
      │
      ├───────────────┐
      │               │
     IS-A           PART-OF
      │               │
   BP10329         BP10408
      │               │
      └───────┬───────┘
              │
           FJ3413
              │
        FJ3413.obj
```

In the local dataset:

```text
IS-A:
FMA3736 → BP10329
FMA3736 → FJ3413

PART-OF:
FMA3736 → BP10408
FMA3736 → FJ3413
```

The relationship context is different, but both contexts can reference the same FJ mesh element.

---

## 12. Element Coverage Across the Two Trees

### 12.1 Metadata level

Element sets, taken from the `*_element_parts.txt` tables:

| Set | Count |
|---|---|
| Elements in both trees | 1,258 |
| Elements only in PART-OF | **0** |
| Elements only in IS-A | 976 |

So at the metadata level **every PART-OF element is also an IS-A element**, and IS-A has 976 more. This is consistent with the archive sizes (136 MB against 62 MB).

The comparison is directional. `PART-OF − IS-A` is empty, but `IS-A − PART-OF` is **not** empty (976 elements).

### 12.2 OBJ file level

An earlier comparison of the extracted OBJ collections also found:

```text
OBJ files present in PART-OF but missing from IS-A: 0
```

This indicates that no OBJ file was found exclusively in the PART-OF collection.

This supports treating FJ identifiers as a shared and reusable mesh-asset layer.

However, this test only proves that the tested difference:

```text
PART-OF − IS-A
```

was empty. It does not say anything about:

```text
IS-A − PART-OF
```

which is non-empty at the metadata level (section 12.1).

---

## 13. Geometry Verification Example

The mesh:

```text
FJ3413.obj
```

was tested in both datasets:

```text
IS-A/FJ3413.obj
PART-OF/FJ3413.obj
```

The files had different SHA-256 hashes:

```text
IS-A:
764F23E432A9308E0780C586F9D1638DB1FBCC52A5019AE61817B4B1DE323870

PART-OF:
F4D566821C5EE6347147631B4D1B1E5C5CB3465E05EC23FADFFA161C268C7BB2
```

However, after parsing and comparing the geometry:

```text
Vertices: 229
Faces:    396

Different vertices: 0
Different faces:    0
```

The dimensions were also identical:

```text
X = 35.765180
Y = 30.777000
Z = 47.840000
```

Therefore:

```text
GEOMETRY IS IDENTICAL
```

This demonstrates that different archive files or file representations do not necessarily imply different anatomical geometry.

For the Unity pipeline, geometry should therefore be validated by content when deduplication is required, rather than relying only on file hashes.

> **Scope:** this is a verification of one mesh (`FJ3413`). It is an example, not a proof for all 1,258 shared elements.

---

## 14. Concept vs Representation vs Geometry

The three main levels can be summarized as:

```text
FMA
│
├── Meaning / anatomical identity
│
│   "Ascending Aorta"
│
▼
BP
│
├── Representation / relationship context
│
│   IS-A or PART-OF
│
▼
FJ
│
├── Mesh element
│
▼
OBJ
│
└── Actual 3D geometry
```

Each level has a different responsibility.

| Level | Main Question |
|---|---|
| FMA | What anatomical concept is this? |
| BP | How is this concept represented in this context? |
| FJ | Which mesh element represents it? |
| OBJ | What is the actual 3D geometry? |

---

## 15. Recommended Internal Data Model

For the MedVerse / Unity pipeline, the data can be represented internally using the following logical structure:

```text
AnatomicalConcept
-----------------
FMA_ID
Name


Representation
--------------
BP_ID
FMA_ID
StructureType
    ├── IS-A
    └── PART-OF


MeshElement
-----------
FJ_ID
OBJ_Path


ConceptElement
--------------
FMA_ID
FJ_ID
StructureType


Relationship
------------
Parent_FMA_ID
Child_FMA_ID
RelationshipType
    ├── IS-A
    └── PART-OF
```

This separates:

1. Anatomical identity
2. Relationship/representation context
3. Mesh assets
4. Anatomical relationships

This separation is useful because the same 3D mesh may be reused across different anatomical contexts.

Key constraints from the source tables:

| Entity | Key / constraint |
|---|---|
| `AnatomicalConcept` | `FMA_ID` is unique; the name is the same in both trees |
| `Representation` | One row per (`FMA_ID`, `StructureType`); `BP_ID` is unique within its tree |
| `ConceptElement` | Many-to-many between `FMA_ID` and `FJ_ID`; one row per pair; lists are cumulative |
| `Relationship` | Per tree, every concept has exactly one parent (strict tree) |

---

## 16. Complete Identifier Architecture

A simplified representation of the complete architecture is:

```text
                         ┌───────────────────┐
                         │ Anatomical Concept│
                         │      FMA...       │
                         └─────────┬─────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼                             ▼
               ┌─────────┐                   ┌────────────┐
               │  IS-A   │                   │  PART-OF   │
               └────┬────┘                   └─────┬──────┘
                    │                              │
                    ▼                              ▼
               ┌─────────┐                   ┌─────────┐
               │  BP...  │                   │  BP...  │
               └────┬────┘                   └────┬────┘
                    │                              │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                         ┌──────────────────┐
                         │ Element Mapping  │
                         └────────┬─────────┘
                                  │
                         ┌────────┴────────┐
                         ▼                 ▼
                      FJ...             FJ...
                         │                 │
                         ▼                 ▼
                      .obj              .obj
                         │                 │
                         └────────┬────────┘
                                  ▼
                               Unity
```

---

## 17. Example: Ascending Aorta

The complete example can be represented as:

```text
                         ┌─────────────────────┐
                         │      FMA3736        │
                         │  Ascending Aorta    │
                         └──────────┬──────────┘
                                    │
                  ┌─────────────────┴─────────────────┐
                  │                                   │
                  ▼                                   ▼
             ┌─────────┐                         ┌─────────┐
             │  IS-A   │                         │ PART-OF │
             └────┬────┘                         └────┬────┘
                  │                                   │
                  ▼                                   ▼
             ┌─────────┐                         ┌─────────┐
             │ BP10329 │                         │ BP10408 │
             └────┬────┘                         └────┬────┘
                  │                                   │
                  └────────────────┬──────────────────┘
                                   │
                                   ▼
                              ┌─────────┐
                              │ FJ3413  │
                              └────┬────┘
                                   │
                                   ▼
                             ┌──────────┐
                             │FJ3413.obj│
                             └────┬─────┘
                                  │
                                  ▼
                             ┌──────────┐
                             │  Unity   │
                             │   Mesh   │
                             └──────────┘
```

The important point is that:

```text
FMA3736
```

identifies the anatomical concept,

while:

```text
BP10329 / BP10408
```

identify its representation in different contexts,

and:

```text
FJ3413
```

identifies the actual reusable 3D mesh element.

---

## 18. Key Takeaway

The BodyParts3D data should be understood as four connected layers:

```text
┌──────────────────────────┐
│ FMA                      │
│ Anatomical Concept       │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│ BP                       │
│ Representation Context   │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│ FJ                       │
│ Mesh Element             │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│ OBJ                      │
│ Actual 3D Geometry       │
└──────────────────────────┘
```

The most important distinction is:

> **FMA describes what the anatomical structure is, BP describes how the concept is represented within a relationship context, and FJ identifies the actual 3D mesh element.**

For the MedVerse pipeline, FJ should be treated as the reusable 3D asset layer, while FMA, BP, IS-A, and PART-OF metadata should remain separate from the actual Unity mesh assets.

This allows the same mesh elements to be reused while preserving the different anatomical relationship structures required by the BodyParts3D dataset.

---

## 19. Maintenance

1. Update the identifier formats here when [`data_dictionary.md`](../data/data_dictionary.md) changes.
2. Keep file names and locations in step with [`download_and_layout.md`](../data/download_and_layout.md) and `paths.py`.
3. Document a finding as verified only after testing it. Examples (such as `FJ3413`) illustrate the model; they are not proofs for the whole dataset.