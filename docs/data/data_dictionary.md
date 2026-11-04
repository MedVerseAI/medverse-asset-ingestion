# Data Dictionary

What each input file contains: columns, keys, counts, and the pitfalls that affect the pipeline.

- Where to get the files and where they live: [`download_and_layout.md`](download_and_layout.md)

---

## 1. Project scope

The first milestone is the **central nervous system**: brain and spine.

| Region | Structures |
|---|---|
| Brain | Cortical lobes, deep gray matter, ventricular system, brainstem, cerebellum, cranial nerves |
| Spine | Spinal cord, vertebral column (cervical, thoracic, lumbar, sacral), intervertebral discs |

---

## 2. BodyParts3D metadata tables
We will define the  relational constraints, entity namespaces, and graph traversal rules for the upstream metadata tables of BodyParts3D (Release v4.0).

---

### 2.1 Identifiers & Entity Key Space
| Prefix | Name | Format  | Example | Meaning |
|---|---|---|---|---|
| FMA | Anatomical Concept ID | FMA<digits> | FMA3736 | An anatomical concept (ascending aorta) |
| BP | Representation ID | BP<digits> | BP10408 | A concept's representation within one tree |
| FJ | Element/Mesh ID| FJ<4 digits> or FJ<4 digits>M | FJ3413, FJ1456M | One mesh element, stored as <id>.obj |

- What the identifiers *mean* and how they relate: [`ontology/foundational_model.md`](../ontology/foundational_model.md)

---
### 2.2 `*isa_BP3D_4.0_obj_99.zip`
#### Polygon mesh data (Polygon reduction rate = 99% Tree)

| Field | Description |
|---|---|
| Data name | Polygon mesh data (Polygon reduction rate = 99% (IS-A Tree & PART-OF Tree)) |
| Description of data contents | BodyParts3D organ model data with the polygon reduction rate of 99%. The zip-compressed download files contain multiple files of ELEMENT file ID-specific polygon data in Wavefront OBJ format. |
| Files | `	isa_BP3D_4.0_obj_99.zip` (IS-A Tree) (136 MB) & `partof_BP3D_4.0_obj_99.zip` (PART-OF Tree) (62 MB)|

Data items are the following:

**About polygon data**
- [Description of a wavefont obj format](https://en.wikipedia.org/wiki/OBJ) (from Wikipedia)
- [Description of Polygon](https://en.wikipedia.org/wiki/Polygon_mesh#Polygons) (from Wikipedia)

---

### 2.3 `*_parts_list_e.txt`
#### Table of 3D organ model IDs and organ names

| Field | Description |
|---|---|
| Data name | Table of 3D organ model IDs and organ names (IS-A Tree & PART-OF Tree) |
| Description of data contents | List of downloadable 3D organ models in a tab-delimited text file format, describing the correspondence between 3D organ model IDs and organ names available in (IS-A Tree & PART-OF Tree). |
| Files | `isa_parts_list_e.txt` (IS-A Tree) (126 KB) & `partof_parts_list_e.txt` (PART-OF Tree) (58 KB)|

Data items are the following:

Each column is delimited by a tab character in the file.

| Data item | Description | Example |
|---|---|---|
| `concept id`| ID of the corresponding FMA (Foundational Model of Anatomy). | `FMA3736` |
| `representation id`| ID of the corresponding 3D representation. | `BP10408` |
| `en`|English name. Basically, a preferred name of FMA is assigned. | `ascending aorta` |

Every concept appears exactly once, and every concept has a unique BP within its tree.
For the same `concept id` the English name is identical in both trees, and only the `representation id` differs.

---
### 2.4 `*_inclusion_relation_list.txt`
#### Data describing the inclusion relationships between two organs 

| Field | Description |
|---|---|
| Data name | Data describing the inclusion relationships between two organs(IS-A Tree & PART-OF Tree) |
| Description of data contents | File of data describing the inclusion relationships between two organs of the downloadable 3D organ models.|
| Files | `isa_inclusion_relation_list.txt` (IS-A Tree) (203 KB) & `partof_inclusion_relation_list.txt` (PART-OF Tree) (90 KB)|

Data items are the following:

Each column is delimited by a tab character in the file.

| Column | Header text| Description | Example |
|---|---|---|---|
| 1 | `parent id`| Concept ID of parent organ | `FMA3734` |
| 2 | `parent name`|English name of parent organ | `aorta` |
| 3 | `child id`| Concept ID of an organ that is included in the parent organ| `FMA3736` |
| 4 | `child name`| English name of an organ that included in the parent organ| `ascending aorta` |

Each tree is a **strict tree**, not a general graph. Every concept has exactly one parent and each tree has one root.

| Tree | Root concept | Root ID |
|---|---|---|
| IS-A | anatomical entity | `FMA62955` |
| PART-OF | human body | `FMA20394` |

Every concept in a relation file also appears in the matching parts list.

---

### 2.5 `*_element_parts.txt`
#### Data describing the definition of compound organs

| Field | Description |
|---|---|
| Data name | Data describing the definition of compound organs (IS-A Tree & PART-OF Tree) |
| Description of data contents | In BodyParts3D, only atomic organs (ELEMENT) are constructed as polygon meshes. Compound organs (COMPOUND) defined as a sum of atomic ones are not provided in the form of the meshes. This file describes which ELEMENT parts consistute each COMPOUND organ.|
| Files | `isa_element_parts.txt ` (IS-A Tree) (1.1 MB) & `partof_element_parts.txt` (PART-OF Tree) (654  KB)|

Data items are the following:

Each column is delimited by a tab character in the file.

| Column | Header text| Description | Example |
|---|---|---|--|
| 1 | `concept id`| Concept ID of COMPOUND organ | `FMA3736` |
| 2 | `name` | Name of COMPOUND organ |`ascending aorta` |
| 3 | `element file id`| Polygon mesh file ID of ELEMENT constituting the COMPOUND organ | `FJ3413` |

The name in column 2 always equals the name in the parts list.

Pitfalls:

1. **Element lists are cumulative.** A parent concept lists every element of all its descendants. Checked on all parent concepts: 1,254 in IS-A and 499 in PART-OF, with 0 violations. The root therefore lists every element in the tree. To find the most specific concept of an element, pick the concept with the **fewest** elements. The export script does this.
2. **One row per pair .** Examples elsewhere that show `FJ1931, FJ1932, ...` on one line are illustrations of the grouped result, not the file format.
3. **Shared files across names.** Spinal cord (`FMA7647`) and central canal of spinal cord (`FMA78497`) both list the single element `FJ1737`.

### 2.6 Observed sizes (BodyParts3D v4.0 download)

| | IS-A | PART-OF |
|---|---|---|
| Concepts | 2,905 | 1,368 |
| Tree edges | 2,904 | 1,367 |
| Element rows | 29,549 | 17,943 |
| Distinct elements (`FJ`) | 2,234 | 1,258 |
| Largest concept | root, 2,234 elements | root, 1,258 elements |
| Max concepts listing one element | 20 | 38 |

Element sets across trees:

| Set | Count |
|---|---|
| Elements in both trees | 1,258 |
| Elements only in PART-OF | **0** |
| Elements only in IS-A | 976 |

So at the metadata level **every PART-OF element is also an IS-A element**, and IS-A has 976 more. This matches the archive sizes (136 MB against 62 MB). It says nothing about the OBJ files themselves.

---