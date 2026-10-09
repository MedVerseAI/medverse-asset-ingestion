# Download & Layout

How to obtain the upstream datasets, where each file goes, and how to verify it.

This page covers **raw and intermediate data only**. Licensing and attribution are documented in [`sources_and_licensing.md`](./sources_and_licensing.md). Read the applicable license terms before downloading or using any dataset.

| Dataset | Method | Command / section |
|---|---|---|
| BodyParts3D v4.0 | Automated | `python scripts/downloaders/bodyparts3d.py` (section 2) |
| Human Brainnetome Atlas | **Manual** | Browser download, then `python scripts/downloaders/check_brainnetome.py` (section 3) |

> Brainnetome has no downloader script. The upstream portal is a web form, so the files are
> downloaded by hand and then checked by a script. Do not assume a script fetches them.

---
## 1. Data Directory Structure

This page documents the raw and intermediate data locations relevant to dataset downloading, extraction, and verification. It does not represent the complete repository structure or all downstream processing outputs.

```text
data/
├── raw/                         Original downloaded files
│   ├── bodyparts3d/
│   │   ├── README_e.html
|   |   |
│   │   ├── metadata/
|   |   |     └── *.txt
│   │   ├── archives/
|   |   |     └── *.zip
│   │   └── checksums.sha256
|   |   
│   └── brainnetome/
│       ├── atlas/
|       |     ├── *.zip
|       |     └── *.nii.gz
|       |
│       ├── labels/
|       |    ├── BN_Atlas_246_LUT.txt
|       |    └── BNA_subregions.xlsx
|       |
│       └── checksums.sha256
└── interim/                     Extracted or intermediate data
    ├── bodyparts3d/
    │   ├── obj_isa/
    |   |     └── *.obj
    │   └── obj_partof/
    |         └── *.obj
    └── brainnetome/
```

- **`raw/`** contains downloaded source files. Keep original downloads unchanged; extract archives into the appropriate intermediate directory.
- **`interim/`** contains extracted or transformed files that are still required by later processing steps.

The directory names above describe the documented layout. Confirm the actual files and subdirectories against the downloader scripts and `paths.py`; do not assume that an empty directory or an undocumented output is created automatically.

---

## 2. BodyParts3D (BP3D v4.0) — automated download

**Official page:** [BodyParts3D Downloads](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html)

### 2.1 Source files

| # | File | Size (approx.) | Contents | Location |
|--:|---|--:|---|---|
| 1 | `README_e.html` | n/a | Upstream release notes | `raw/bodyparts3d/` |
| 2 | `isa_parts_list_e.txt` | 126 KB | IS-A concepts and names | `raw/bodyparts3d/metadata/` |
| 3 | `partof_parts_list_e.txt` | 58 KB | PART-OF concepts and names | `raw/bodyparts3d/metadata/` |
| 4 | `partof_inclusion_relation_list.txt` | 90 KB | PART-OF parent → child edges | `raw/bodyparts3d/metadata/` |
| 5 | `isa_inclusion_relation_list.txt` | 203 KB | IS-A parent → child edges | `raw/bodyparts3d/metadata/` |
| 6 | `isa_element_parts.txt` | 1.1 MB | IS-A concept → mesh elements (`FJ…`) | `raw/bodyparts3d/metadata/` |
| 7 | `partof_element_parts.txt` | 654 KB | PART-OF concept → mesh elements (`FJ…`) | `raw/bodyparts3d/metadata/` |
| 8 | `isa_BP3D_4.0_obj_99.zip` | 136 MB | OBJ meshes, IS-A, 99 % polygon reduction | `raw/bodyparts3d/archives/` |
| 9 | `partof_BP3D_4.0_obj_99.zip` | 62 MB | OBJ meshes, PART-OF, 99 % polygon reduction | `raw/bodyparts3d/archives/` |

Sizes are approximate and may differ from the current upstream listing.

### 2.2 What the files are

- **Parts lists** describe concepts and names.
- **Inclusion relation lists** describe the hierarchy.
- **Element parts** link concepts to the mesh elements that represent them.
- **Mesh archives** hold Wavefront OBJ files named by element ID (for example `FJ3413.obj`).

IS-A classifies (*what kind of thing*); PART-OF describes structure (*what it belongs to*).
See [`foundational_model.md`](../ontology/foundational_model.md) for the identifier model.

### 2.3 Run the downloader

```bash
python scripts/downloaders/bodyparts3d.py
```

It performs these steps, in order:

1. Downloads the README, the six metadata tables and the two ZIPs. Existing files are skipped, and a failed download leaves no partial file.
2. **Tests both ZIPs** (opens them and checks every entry). If one is corrupt the script stops before extracting anything.
3. Writes `data/raw/bodyparts3d/checksums.sha256` (SHA-256 of every raw file).
4. Extracts the IS-A archive to `interim/bodyparts3d/obj_isa/` and the PART-OF archive to `interim/bodyparts3d/obj_partof/`.

Each ZIP extracts into a nested folder (`isa_BP3D_4.0_obj_99/`, `partof_BP3D_4.0_obj_99/`).
Code should call `paths.bp3d_obj_dir("isa")` or `paths.bp3d_obj_dir("partof")` rather than build the path itself.

---

## 3. Human Brainnetome Atlas — manual download

**Official page:** [Brainnetome Atlas Downloads](https://atlas.brainnetome.org/download.html)

Brainnetome terms are **non-commercial with attribution**. Check
[`sources_and_licensing.md`](./sources_and_licensing.md) before using the files.

### 3.1 Steps

1. Open the download page above and accept any terms it shows.
2. Download the files from the table.
3. Save each file into the folder listed for it (create the folders if needed):
   `data/raw/brainnetome/atlas/` and `data/raw/brainnetome/labels/`.
4. Do not rename or unzip files in `raw/`. If a ZIP must be extracted, extract it into `data/interim/brainnetome/`.
5. Run the checker:

   ```bash
   python scripts/downloaders/check_brainnetome.py
   ```

   It reports each expected file as `ok`, `MISSING` or `CORRUPT` (ZIPs are tested), writes
   `data/raw/brainnetome/checksums.sha256`, and exits with a non-zero code if a **required** file is absent.

### 3.2 Files

| File | Description | Folder | 
|---|---|---|
| `BN_Atlas_246_LUT.txt` | Region ID → name / colour lookup table | `raw/brainnetome/labels/` | 
| `BN_Atlas_freesurfer.zip` | FreeSurfer resource | `raw/brainnetome/atlas/` | 
| `BN_Atlas_246_1mm.nii.gz` | 246-region volume, 1 mm | `raw/brainnetome/atlas/` |
| `BN_Atlas_246_2mm.nii.gz` | 246-region volume, 2 mm | `raw/brainnetome/atlas/` | 
| `BN_Atlas_246_3mm.nii.gz` | 246-region volume, 3 mm | `raw/brainnetome/atlas/` | 
| `BNA_MPM_thr25_1.25mm.nii.gz` | Maximum-probability map, threshold 25 | `raw/brainnetome/atlas/` |
| `BNA_PM_3D_246.zip` | 3D atlas resource; inspect contents first | `raw/brainnetome/atlas/` | 
| `BNA_subregions.xlsx` | Subregion information | `raw/brainnetome/labels/` | 

Descriptions come from filenames and the upstream resource categories. Confirm actual contents,
resolution and coordinate space against the downloaded files before relying on them.

---

## 4. Verification

Verification shows the files are **complete and readable**. It does not show that they are
scientifically suitable for a step or that their license permits your use.

### 4.1 Checksums

- BodyParts3D: the downloader writes `data/raw/bodyparts3d/checksums.sha256`.
- Brainnetome: the checker writes `data/raw/brainnetome/checksums.sha256`.

These checksums come from your own download. They identify your copy for later comparison; they
do not prove authenticity unless compared with a trusted upstream value.

### 4.2 Archive integrity

ZIPs are tested before extraction. If an archive is corrupt, stop and re-download it. Integrity
checks say nothing about whether the anatomy inside is correct.

---

## 5. Provenance

For each downloaded file, keep: dataset name and version, source URL or page, original filename,
download date, SHA-256, applicable license, and any extraction or conversion applied.

Today the project records only the SHA-256 checksums above. Source URLs for BodyParts3D are in the
downloader's `BASE_URL`; for Brainnetome they are the pages linked in section 3. When a newer upstream
release replaces a file, keep enough information to tell old inputs from new ones.

---

## 6. Where scripts read and write

| Data | Location | Python constant |
|---|---|---|
| BP3D metadata tables | `data/raw/bodyparts3d/metadata/` | `paths.BP3D_METADATA` |
| BP3D ZIP archives | `data/raw/bodyparts3d/archives/` | `paths.BP3D_ARCHIVES` |
| IS-A meshes | `data/interim/bodyparts3d/obj_isa/…` | `paths.bp3d_obj_dir("isa")` |
| PART-OF meshes | `data/interim/bodyparts3d/obj_partof/…` | `paths.bp3d_obj_dir("partof")` |
| Brainnetome atlas files | `data/raw/brainnetome/atlas/` | `paths.BN_ATLAS` |
| Brainnetome LUT | `data/raw/brainnetome/labels/BN_Atlas_246_LUT.txt` | `paths.BN_LUT` |
---

## 7. Maintenance

1. Update the file tables when `bodyparts3d.py` or `check_brainnetome.py` changes.
2. Update paths here whenever `paths.py` changes.
3. Keep this page in step with `sources_and_licensing.md`.
4. Document a feature as implemented only after testing it.