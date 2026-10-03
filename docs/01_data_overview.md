# 01. BodyParts3D Dataset Overview

> **Project Target:** Central Nervous System (Brain & Spine) VR Pipeline (As an inital step)  
> **Source Repository:** `MedVerseAI/medverse-asset-ingestion`  
> **Upstream Provider:** Database Center for Life Science (DBCLS), Japan

---

## 1. Introduction & Source Origin

MedVerse utilizes the **BodyParts3D** anatomical dictionary and geometry library as its primary morphological base. Developed by the **Database Center for Life Science (DBCLS)**, the repository correlates clinical ontological standards with standardized 3D surface polygon meshes derived from whole-body medical imaging.

| Resource | Direct Link | Description |
| :--- | :--- | :--- |
| **Download Portal** | [LSDB Archive: BodyParts3D](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html) | Official archive listing terms, releases, and tables |
| **LATEST HTTP Directory** | [BodyParts3D Data Directory](https://dbarchive.biosciencedbc.jp/data/bodyparts3d/LATEST/) | Direct access to raw table schemas and geometry archives |

---

## 2. Upstream Release Artifacts (BP3D v4.0)

The upstream distribution separates relational taxonomy tables from raw polygonal geometry packages. The table below lists all downloadable assets available from the official release and their assigned role within the MedVerse asset pipeline:

| # | Artifact Name | Filename | Size | Pipeline Role |
| :-: | :--- | :--- | :-: | :--- |
| **1** | Release Documentation | `README_e.html` | — | Upstream metadata and release specifications |
| **2** | Organ Models & Labels (IS-A) | `isa_parts_list_e.txt` | 126 KB | Taxonomic concept nomenclature & labels |
| **3** | Organ Models & Labels (PART-OF) | `partof_parts_list_e.txt` | 58 KB | Structural concept-to-BP mapping |
| **4** | Inclusion Graph (PART-OF) | `partof_inclusion_relation_list.txt` | 90 KB | **Core Hierarchy:** Parent-child traversal edges |
| **5** | Inclusion Graph (IS-A) | `isa_inclusion_relation_list.txt` | 203 KB | Taxonomic classification edges |
| **6** | Compound Organ Elements (IS-A) | `isa_element_parts.txt` | 1.1 MB | Taxonomic compound-to-element mapping |
| **7** | Compound Organ Elements (PART-OF) | `partof_element_parts.txt` | 654 KB | **Core Ingestion:** Maps concepts to `FJ...` mesh files |
| **8** | Polygon Meshes (IS-A Tree) | `isa_BP3D_4.0_obj_99.zip` | 136 MB | Complete raw 3D mesh OBJ archive (99% reduced) |
| **9** | Polygon Meshes (PART-OF Tree) | `partof_BP3D_4.0_obj_99.zip` | 62 MB | 3D geometry archive associated with the PART-OF representation |

---

## 3. Dataset Distribution Schema

### A. Semantic Metadata Tables

The semantic tables fall into three structural tiers:

* **Parts List:** Maps concept IDs to anatomical names and representation entries.
* **Inclusion Lists:** Defines directed graph edges tracking parental hierarchy (`parent_id` $\rightarrow$ `child_id`).
* **Element Parts:** Directly references compound anatomical concepts to physical 3D mesh identifiers.

| File Designation | Core Responsibility | Primary Usage in MedVerse |
| :--- | :--- | :--- |
| `isa_parts_list_e.txt`<br>`partof_parts_list_e.txt` | Defines concept IDs, representation IDs, and English medical nomenclature. | Verification of anatomical nomenclature and dictionary lookup. |
| `isa_inclusion_relation_list.txt`<br>`partof_inclusion_relation_list.txt` | Graph edges tracking parental hierarchy (`parent_id -> child_id`). | Recursive hierarchy traversal to discover sub-organs. |
| `isa_element_parts.txt`<br>`partof_element_parts.txt` | Explicit resolution of anatomical concepts into concrete mesh files. | **Core Ingestion Asset:** Direct lookup of geometry files (`FJ...`). |

### B. 3D Polygon Archives (`.obj`)

Geometric models are packaged as Wavefront `.obj` files inside compressed archives:

* **Geometric Decimation:** Distributed in `99%` reduced packages (e.g., `partof_BP3D_4.0_obj_99.zip`), optimizing file transfer while retaining critical anatomical contours.
* **OBJ Asset Parity:** Every `.obj` file indexed under `PART-OF` exists identically in the `IS-A` archive. The underlying geometry files remain invariant; only the relational hierarchy graph changes.

---

## 4. Scope of MedVerse — Central Nervous System MVP

The MVP targets the **Central Nervous System (CNS)** to establish the interactive foundation before whole-body expansion:

* **Brain Structures:**
  * Cortical Lobes (Frontal, Parietal, Occipital, Temporal)
  * Deep Gray Matter & Ventricular System
  * Brainstem & Cerebellum
  * Cranial Nerves
* **Spine Structures:**
  * Spinal Cord Segments
  * Vertebral Column (Cervical, Thoracic, Lumbar, Sacral)

---

## 5. Engineering Performance Budgets

| Parameter | Specification | Engineering Rationale |
| :--- | :--- | :--- |
| **Target Runtime** | Meta Quest 3 (Standalone XR) | Requires low draw-call overhead and strict geometry budgeting. |
| **Framerate SLA** | 72+ FPS (Targeting 90 FPS) | Prevents simulation sickness and ensures comfortable VR immersion. |
| **Polygon Cap** | **< 180,000 Triangles** (Combined) | Ensures smooth rendering alongside real-time lighting and shaders. |
| **Interactivity Tier** | Discrete Node Selection | Each structure must exist as an independent node for grabbing & isolation. |

---
