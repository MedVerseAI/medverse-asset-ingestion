# Data Sources & Licensing

This document provides a centralized reference for the external datasets, anatomical models, and neuroimaging atlases used by the MedVerse asset ingestion pipeline. It records their sources, versions, access points, licensing terms, redistribution requirements, and required citations.

Licensing information in this document is based on the terms published by the respective upstream providers. In case of conflict, the current upstream license or legal agreement takes precedence.

---

## 1. Upstream Data Sources

### 1.1 BodyParts3D (BP3D v4.0)

BodyParts3D is a dictionary-type anatomical database that provides 3D human models representing the shapes and positions of anatomical structures.

* **Data Provider / Attribution:** Database Center for Life Science (DBCLS), Research Organization of Information and Systems, Japan.
* **Integrated Release:** BodyParts3D 4.0.
* **Official Archive:** [BodyParts3D Download Portal](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html)
* **Future Updates:** The legacy BodyParts3D website is no longer being updated and refers users to the JST Bioscience Database Center for future updates.

### 1.2 Human Brainnetome Atlas (BNA)

The Brainnetome Atlas is a fine-grained, in vivo connectivity-based parcellation of the human brain, comprising 246 distinct subregions across both hemispheres, including 210 cortical subregions across 6 lobes and 36 subcortical structures.


* **Data Provider / Research Center**: Brainnetome Center, Institute of Automation, Chinese Academy of Sciences (CASIA).
* **Official Web Portal:** [Brainnetome Atlas Download Portal](https://atlas.brainnetome.org/download.html)
* **Additional Distribution / Resources:** [Brainnetome Atlas README](https://github.com/BrainnetomeAtlas/HUMAN-BRAINNETOME-ATLAS)
* **Available / Relevant Artifact Types:**
  * Cortical and subcortical brain region meshes used for anatomical integration and registration workflows.
  * Volumetric atlas/parcellation files in NIfTI format.
  * Region labels, lookup tables, and metadata.
  * Structural and functional connectivity data and related matrices.

---

## 2. Licensing Frameworks & Redistribution Terms

Each integrated dataset is governed by its upstream copyright and distribution terms. Downstream contributors, pipeline operators, and deployment workflows must comply with the applicable terms published by the respective data provider.

### 2.1 BodyParts3D Terms

* **License:** [**Creative Commons Attribution 4.0 International (`CC BY 4.0`)**](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html).

**Permissions:**

* Sharing, copying, and redistributing the material in any medium or format.
* Adapting, transforming, and building upon the material, subject to the terms of the applicable license.

**Requirements:**

* **Attribution:** Appropriate credit must be given to the Database Center for Life Science (DBCLS), with a link to the applicable license and an indication of whether changes were made.
* **Required Attribution:**
  `BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International`

> **Note:** Earlier BodyParts3D releases were distributed under different licensing terms, including CC BY-SA 2.1 JP. The integrated BodyParts3D 4.0 data is documented according to the current licensing information published by the upstream provider.

### 2.2 Brainnetome Atlas Terms

* **Use Terms:** The information, images, and data are made available for non-commercial purposes, subject to proper attribution and an agreement to share alike.

**Commercial Use:**

- Commercial use is not covered by the non-commercial terms above. The Brainnetome Center may consider granting a separate license for commercial use upon request.

**Attribution:**

* Proper attribution is required when using the Brainnetome information, images, and data.

---

## 3. Citations & Attribution

Research publications, demonstrations, and other outputs that use these datasets should acknowledge the corresponding upstream resources and cite the relevant primary publications.

### 3.1 BodyParts3D Primary Citation

```bibtex
@article{mitsuhashi2009bodyparts3d,
  author    = {Nobuhiko Mitsuhashi and Kaoru Fujieda and Takako Tamura and Shoko Kawamoto and Toshihisa Takagi and Kousaku Okubo},
  title     = {BodyParts3D: 3D structure database for anatomical concepts},
  journal   = {Nucleic Acids Research},
  volume    = {37},
  number    = {suppl_1},
  pages     = {D782--D785},
  year      = {2009},
  publisher = {Oxford University Press}
}
```

### 3.2 Brainnetome Atlas Primary Citation

```bibtex
@article{fan2016human,
  author    = {Lingzhong Fan and Hai Li and Junjie Zhuo and Yu Zhang and Jiaojian Wang and Liangfu Chen and Zhengyi Yang and Congying Chu and Sangma Xie and Lisheng Li and others},
  title     = {The Human Brainnetome Atlas: A New Brain Atlas Based on Connectional Architecture},
  journal   = {Cerebral Cortex},
  volume    = {26},
  number    = {8},
  pages     = {3508--3526},
  year      = {2016},
  publisher = {Oxford University Press}
}
```

---

## 4. Compliance Matrix

| **Asset Source** | **Asset Category**                        | **License / Terms**                        | **Commercial Use**                           | **Derivative / Redistribution Requirements**          | **Attribution Requirement** |
| ---------------- | ----------------------------------------- | ------------------------------------------ | -------------------------------------------- | ----------------------------------------------------- | --------------------------- |
| **BodyParts3D**  | Polygons / Meshes (`.obj`)                | CC BY 4.0                                  | Permitted under the applicable license terms | Must comply with CC BY 4.0 terms                      | Required         |
| **Brainnetome**  | Volumetric MPM Masks (`.nii`, `.nii.gz`)  | Non-commercial use under Brainnetome terms | Separate license required for commercial use | Subject to the applicable Brainnetome legal agreement | Required                    |
---

## 5. Clinical & Regulatory Notice

The data and assets ingested by this repository are intended for educational, scientific research, anatomical simulation, and algorithm testing within the MedVerse project.

They are not intended to provide medical diagnosis, treatment recommendations, surgical guidance, or patient-specific clinical decision support.

No clinical warranties are implied.
