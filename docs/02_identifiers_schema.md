# 2. Identifiers and Schema

## 1. Purpose

BodyParts3D uses several identifiers to describe anatomical structures and their 3D representations.

The most important identifiers are:

- **FMA** — Anatomical concept identifier
- **BP** — Representation identifier
- **FJ** — 3D mesh element identifier

These identifiers should not be treated as a simple one-to-one chain. Instead, they form a connected data model in which anatomical concepts, representation contexts, relationships, and 3D mesh elements are linked together.

---

## 2. Identifier Types

| Identifier | Meaning | Example | Represents |
|---|---|---|---|
| `FMA...` | Anatomical Concept ID | `FMA3736` | An anatomical structure/concept |
| `BP...` | Representation ID | `BP10408` | A representation of an anatomical concept in a specific context |
| `FJ...` | Element/Mesh ID | `FJ3413` | An actual 3D mesh element |

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

An FMA concept may have different BP representations and may be associated with one or more FJ mesh elements.

---

# 3. FMA — Anatomical Concept Identifier

## 3.1 What is FMA?

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

---

## 3.2 FMA in the Dataset

FMA identifiers appear throughout the CSV files.

For example, the PART-OF relationship file contains:

```text
parent_id | parent_name | child_id | child_name

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

# 4. BP — Representation Identifier

## 4.1 What is BP?

`BP` identifies a representation of an anatomical concept within a particular representation structure or context.

For example, the same anatomical concept can have different BP identifiers in different datasets:

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

---

## 4.2 Example: FMA3736

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

# 5. FJ — 3D Element / Mesh Identifier

## 5.1 What is FJ?

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

---

## 5.2 FJ Is the Actual Mesh Layer

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

---

# 6. Relationship Between FMA, BP, and FJ

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

- One FMA can have multiple BP representations.
- One FMA can be associated with multiple FJ elements.
- One FJ element can be referenced by multiple FMA concepts.
- IS-A and PART-OF provide different relationship contexts.

Therefore, the data should be treated as a **graph of related entities** rather than a simple linear hierarchy.

---

# 7. Dataset Files Related to the Identifiers

The main CSV files used in this analysis are:

## 7.1 IS-A Parts List

```text
bodyparts3d_isa_parts_list_e.csv
```

In the converted dataset, the columns are:

```text
concept_id | name | element_file_id
```

Example:

```text
FMA3710 | vascular tree | FJ2925, FJ2933, FJ2944, ...
FMA3711 | segment of artery | FJ2055, FJ2073, FJ2216, ...
FMA3714 | variant artery | FJ3418
```

This provides a mapping between an anatomical concept and its associated mesh elements in the IS-A dataset.

---

## 7.2 IS-A Element Mapping

```text
bodyparts3d_isa_element_parts.csv
```

In the converted dataset, the columns are:

```text
concept_id | name | element_file_id
```

Example:

```text
FMA3710 | vascular tree | FJ2925
FMA3710 | vascular tree | FJ2933
FMA3710 | vascular tree | FJ2944
```

Each row represents one mapping between an anatomical concept and one FJ mesh element.

For example, the anatomical concept:

```text
FMA3736
ascending aorta
```

is associated with:

```text
FJ3413.obj
```

---

## 7.3 PART-OF Parts List

```text
bodyparts3d_partof_parts_list_e.csv
```

The columns are:

```text
concept_id | representation_id | en
```

Example:

```text
FMA3734 | BP10374 | aorta
FMA3736 | BP10408 | ascending aorta
FMA3768 | BP10404 | arch of aorta
FMA3784 | BP10373 | descending aorta
```

This provides the relationship between an FMA concept and its BP representation in the PART-OF structure.

---

## 7.4 PART-OF Element Mapping

```text
bodyparts3d_partof_element_parts.csv
```

The columns are:

```text
concept_id | name | element_file_id
```

Example:

```text
FMA3734 | aorta | FJ1931, FJ1932, FJ3411, FJ3413, FJ3427
FMA3736 | ascending aorta | FJ3413
FMA3768 | arch of aorta | FJ3411
FMA3784 | descending aorta | FJ1931, FJ1932, FJ3427
```

This connects anatomical concepts to their actual FJ mesh elements.

---

# 8. Relationship Structures

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

# 9. One FMA Can Map to Multiple FJ Elements

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

---

# 10. One FJ Can Be Referenced by Multiple Concepts

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

Therefore, FJ should be treated as a reusable mesh asset identifier rather than assuming that:

```text
1 FMA = 1 FJ
```

---

# 11. IS-A and PART-OF Can Reference the Same FJ

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

# 12. OBJ Asset Consistency Check

The OBJ collections were compared between the local IS-A and PART-OF datasets.

The comparison found:

```text
OBJ files present in PART-OF but missing from IS-A: 0
```

This indicates that no OBJ file was found exclusively in the PART-OF collection during this comparison.

This supports treating FJ identifiers as a shared and reusable mesh-asset layer.

However, this specific test only proves that the tested difference:

```text
PART-OF − IS-A
```

was empty.

It does not by itself prove that:

```text
IS-A − PART-OF
```

is also empty.

---

# 13. Geometry Verification Example

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

---

# 14. Concept vs Representation vs Geometry

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

# 15. Recommended Internal Data Model

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

---

# 16. Complete Identifier Architecture

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

# 17. Example: Ascending Aorta

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

# 18. Key Takeaway

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
│ Mesh Element              │
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