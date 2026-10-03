# Brainnetome Atlas: Data and Divisions Explained
 
## 1. What is this data?
 
The **Brainnetome Atlas** is a digital map of the human brain. It splits the brain into **246 small regions (subregions)**:
 
- **210 cortical** regions (the outer surface of the brain)
- **36 subcortical** regions (deep structures like the thalamus and hippocampus)
Older atlases (like Brodmann's) were drawn from dead brain tissue. This atlas is built from **living brain MRI scans**, and the regions are defined by **how they connect to the rest of the brain** (their "connectional fingerprint"), not just by how they look.
 
**Core idea:** voxels (tiny 3D pixels) that connect to the same places in the brain probably belong to the same functional region.
 
---
 
## 2. Where the data comes from
 
| Dataset | Subjects | Scanner | Purpose |
|---|---|---|---|
| **Human Connectome Project (HCP)** | 40 healthy adults, age 22-35 (17 males) | 3T Siemens Skyra | Main data used to build the atlas |
| **Independent dataset** | 40 healthy adults, age 17-20 (20 males) | 3T GE | Validation: checks results are repeatable |
 
Three types of MRI were used:
 
1. **Structural MRI (T1):** brain anatomy.
2. **Diffusion MRI (dMRI):** tracks white-matter fibers, used to measure structural connections.
3. **Resting-state functional MRI (rfMRI):** brain activity at rest, used to measure functional connections.
---
 
## 3. How the brain was divided (step by step)
 
1. **Start with a coarse map.** The Desikan-Killiany (DK) atlas splits each brain into big regions (e.g., Middle Frontal Gyrus).
2. **Trace connections.** Probabilistic tractography samples 5000 fibers from every voxel to build its whole-brain connectivity profile. Very weak connections (noise) are removed.
3. **Compare voxels.** A similarity matrix shows which voxels in a region have similar connectivity.
4. **Cluster.** Spectral clustering groups similar voxels into 2 to 12 clusters per region.
5. **Align across subjects.** Cluster labels are random per person, so they are matched using the Munkres algorithm.
6. **Build the final map.** A **Maximum Probability Map (MPM)** assigns each voxel to the cluster most subjects agree on.
7. **Pick the best number of clusters (K)** using two tests:
   - **Cramer's V:** do two random halves of the subjects give the same result? (higher = better)
   - **Topological Distance (TpD):** do the left and right hemispheres look similar? (0 = identical, 1 = completely different)
---
 
## 4. The main structure: lobes and gyri
 
Every region is organized as **Lobe → Gyrus → Subregion**.
 
| Lobe | Gyri included | Subregions per hemisphere | Total (both sides) |
|---|---|---|---|
| **Frontal** | SFG 7, MFG 7, IFG 6, OrG 6, PrG 6, PCL 2 | 34 | 68 |
| **Temporal** | STG 6, MTG 4, ITG 7, FuG 3, PhG 6, pSTS 2 | 28 | 56 |
| **Parietal** | SPL 5, IPL 6, Precuneus 4, PoG 4 | 19 | 38 |
| **Insular** | INS 6 | 6 | 12 |
| **Limbic** | Cingulate gyrus (CG) 7 | 7 | 14 |
| **Occipital** | MVOcC 5, LOcC 6 | 11 | 22 |
| **Subcortical** | Amygdala 2, Hippocampus 2, Basal ganglia 6, Thalamus 8 | 18 | 36 |
| **Total** | | **123** | **246** |
 
Cortical: 105 per hemisphere = **210**. Subcortical: 18 per hemisphere = **36**.
 
### Gyrus abbreviations
 
| Abbreviation | Full name |
|---|---|
| SFG / MFG / IFG | Superior / Middle / Inferior Frontal Gyrus |
| OrG | Orbital Gyrus |
| PrG | Precentral Gyrus (motor) |
| PCL | Paracentral Lobule |
| STG / MTG / ITG | Superior / Middle / Inferior Temporal Gyrus |
| FuG | Fusiform Gyrus |
| PhG | Parahippocampal Gyrus |
| pSTS | Posterior Superior Temporal Sulcus |
| SPL / IPL | Superior / Inferior Parietal Lobule |
| PCun | Precuneus |
| PoG | Postcentral Gyrus (sensory) |
| INS | Insular Gyrus |
| CG | Cingulate Gyrus |
| MVOcC | MedioVentral Occipital Cortex |
| LOcC | Lateral Occipital Cortex |
| Amyg / Hipp / BG / Tha | Amygdala / Hippocampus / Basal Ganglia / Thalamus |
 
---
 
## 5. How to read a region's name and ID
 
Take this example row:
 
| Field | Value |
|---|---|
| Name code | `MFG_L(R)_7_5` |
| Label ID (left / right) | 23 / 24 |
| Brodmann-style name | A8vl (ventrolateral area 8) |
| MNI center (left) | (-33, 23, 45) |
| MNI center (right) | (42, 27, 39) |
 
How to decode it:
 
- `MFG` is the gyrus (Middle Frontal Gyrus).
- `L(R)` means the same name is used for the left and right versions.
- `7` is how many subregions this gyrus has.
- `5` is this subregion's index (the 5th of 7).
- **Label IDs:** odd numbers are **left**, even numbers are **right**. Left and right pairs are always next to each other (23 and 24).
- **MNI coordinates (X, Y, Z):** the center of the region in a standard brain space. X is left-right, Y is back-front, Z is down-up.
---
 
## 6. Two naming systems
 
1. **DK-based name:** gyrus plus a number (e.g., `MFG_7_5`). It is neutral and makes no claim about old brain maps, but it is harder to remember.
2. **Brodmann-style name:** a familiar cytoarchitectonic name (e.g., `A8vl`, `A46`, `IFJ`). It is easier to compare with other papers.
The occipital lobe keeps simple anatomical names (e.g., `cLinG`, `V5/MT+`), because no good matching architectonic maps exist for it.
 
---
 
## 7. What data exists for each of the 246 regions
 
| Data type | What it tells you | How it was made |
|---|---|---|
| **Region mask (MPM)** | Where the region is in the brain | Clustering of tractography profiles |
| **Structural connectivity** | Which regions are physically wired together by white-matter fibers | Probabilistic tractography on dMRI |
| **Functional connectivity** | Which regions have activity that rises and falls together | Pearson correlation of rfMRI signals |
| **Functional decoding** | What mental tasks activate the region | BrainMap database (behavioral domains and paradigms) |
 
### Structural connectivity details
 
- Tractography thresholded at 2 or more streamlines to remove noise.
- Group fiber maps thresholded at 50% probability.
- A **246 x 246 connectivity matrix** (the structural connectome) was built.
- Significant connections were found using a sign test with Bonferroni correction over 30,135 region pairs (P < 0.001).
### Functional connectivity details
 
- Average time series per region, correlated with every voxel in the brain.
- Fisher z-transform, then group-level t-test (FDR P < 0.05).
### Functional decoding details
 
- **Forward inference:** given a task, how likely is this region to activate?
- **Reverse inference:** given activation here, which mental process is likely happening?
---
 
## 8. Example regions
 
| Region | Where | Connects to | Linked functions |
|---|---|---|---|
| **A8vl** (MFG-5) | Right middle frontal gyrus | Frontal areas, cingulate 24rv, parietal areas, thalamus, basal ganglia | Reasoning, working memory, explicit memory, inhibition (flanker, n-back tasks) |
| **dIa** (INS-3) | Right insula | Insular and related networks | Pain perception, inhibition, reward, cognition |
 
---
 
## 9. Tools released with the atlas
 
| Tool | What it does |
|---|---|
| **Website** (atlas.brainnetome.org) | Browse regions in a tree, view slices, see connectograms, search |
| **Atlas Viewer** (MATLAB GUI) | View MPMs in 2D and 3D, generate ROI masks at chosen probability thresholds |
| **ATPP pipeline** | Run your own tractography-based parcellation on any brain region (GUI or command line) |
 
The atlas is available in MNI volume space, FreeSurfer surface space, and the Caret template.
 
---
 
## 10. Limitations
 
- It is a **group-level** atlas, so it does not capture individual differences.
- Using cross-subject consistency as the quality test may disfavor highly variable regions.
- The starting DK boundaries come from anatomy and may not match true connectivity borders.
- Tractography mainly captures **direct** connections, not multi-step pathways.
- Registration uses brain shape (MNI), because connectivity-based registration is still experimental.
---
 
## 11. Using this data in an AI/ML project
 
| Atlas element | ML equivalent |
|---|---|
| 246 regions | **Nodes** of a graph |
| 246 x 246 structural connectome | **Adjacency matrix** (edges) |
| Functional connectivity values | **Edge weights** or node feature vectors |
| Functional decoding labels | Region-level **semantic labels** |
| Left/right pairs and lobes | Useful **grouping** or hierarchy for models |
 
This makes the atlas a natural fit for **graph neural networks (GNNs)** and brain-network classification tasks (for example, healthy vs. patient).
 
---
 
## 12. Quick summary
 
- **246 regions** = 210 cortical + 36 subcortical, defined by **connectivity**.
- Organized as **Lobe → Gyrus → Subregion**, with left/right pairs (odd ID = left, even ID = right).
- Each region has a **mask, structural connections, functional connections, and task labels**.
- Built from **40 HCP subjects**, validated on **40 independent subjects**.
- Free to download at **atlas.brainnetome.org**.
---
 
## 13. BodyParts3D Export and Integration
 
### `export_bodyparts3d.py`
 
BodyParts3D → clean, optimized, Blender-ready PLY pieces + manifest.
 
Same philosophy as `export_bna_voxels.py` (one PLY per anatomical piece, binary, deterministic, verbose log), but the selection is driven entirely by the supplied BodyParts3D metadata:
 
- `isa_element_parts.txt` / `partof_element_parts.txt` → concept -> element file `FJxxxx`
- `isa_inclusion_relation_list.txt` / `partof_inclusion_...` → concept tree
- `isa_parts_list_e.txt` / `partof_parts_list_e.txt` → concept -> representation `BPxxxx`
Division of labour (see `integrate_brainnetome_bodyparts3d.py`):
 
- Human Brainnetome → cerebral cortex
- BodyParts3D → everything else (this script)
What the script does:
 
1. Reads the metadata, builds the concept trees and element->concept membership.
2. Tags every element that is a MUSCLE (isa "muscle organ" subtree + name rules).
3. Selects vertebrae, sacrum, intervertebral discs, spinal cord, cerebellum, brainstem, subcortical / deep structures, deep white matter, ventricles ... by name-based rules evaluated on the real metadata (no hard-coded FMA / FJ ids).
4. Excludes cerebral-cortex duplicates (gyri, lobes, insula, ...). They are NOT written as meshes; only a sub-sampled point cloud is stored as a registration reference.
5. Loads the OBJ meshes, infers units (→ mm) and anatomical axes (→ RAS, like the Brainnetome/MNI space) from the data itself, cleans + optimizes the geometry.
6. Writes `<OUTPUT_DIR>/meshes/<GROUP>/*.ply`, `manifest.json`, `reference/*.npz`, `report.txt`
Requirements:
 
```bash
pip install numpy scipy fast-simplification
```