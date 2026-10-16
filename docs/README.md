# MedVerse Asset Ingestion: Documentation

This folder documents the data that the MedVerse asset ingestion pipeline consumes: where it comes from, how to download it, where it is stored, what it contains, and how its identifiers relate to each other.

The documentation currently covers **raw and intermediate data only** (BodyParts3D and the Human Brainnetome Atlas). Downstream processing outputs are not documented here yet.

---

## Contents

```text
docs/
├── README.md                          ← you are here
├── data/
│   ├── sources_and_licensing.md       Upstream sources, licenses, attribution, citations
│   ├── download_and_layout.md         How to get the files, where they go, how to verify them
│   └── data_dictionary.md             Columns, keys, counts and pitfalls of the input tables
└── ontology/
    └── foundational_model.md          How FMA, BP and FJ identifiers relate to each other
```

| Document | Read it when you need to... |
|---|---|
| [`data/sources_and_licensing.md`](data/sources_and_licensing.md) | Check whether you may use or redistribute a dataset, find the required attribution text, or copy a citation. |
| [`data/download_and_layout.md`](data/download_and_layout.md) | Download the datasets, find where files live on disk, run the downloader or checker scripts, or verify checksums. |
| [`data/data_dictionary.md`](data/data_dictionary.md) | Look up the columns, keys, observed sizes and known pitfalls of the BodyParts3D metadata tables. |
| [`ontology/foundational_model.md`](ontology/foundational_model.md) | Understand how anatomical concepts (`FMA`), representations (`BP`) and mesh elements (`FJ`) connect, and how that maps to the files. |

---

## Suggested reading order

1. **[Sources & licensing](data/sources_and_licensing.md):** confirm the terms before downloading or using any data.
2. **[Download & layout](data/download_and_layout.md):** obtain the files and put them in the right place.
3. **[Data dictionary](data/data_dictionary.md):** learn what is in each table.
4. **[Foundational model](ontology/foundational_model.md):** understand the identifier model before writing code that joins the tables (For BodyParts3D).

---

## Quick start

BodyParts3D is downloaded automatically:

```bash
python scripts/downloaders/bodyparts3d.py
```

The Human Brainnetome Atlas is downloaded **manually** from its web portal, saved into `data/raw/brainnetome/`, and then checked:

```bash
python scripts/downloaders/check_brainnetome.py
```

Both scripts write a `checksums.sha256` file into the dataset's raw folder. See [Download & layout](data/download_and_layout.md) for the full steps.

Scripts should never hard-code paths. Use the constants and helpers in `src/medverse/paths.py` (for example `paths.bp3d_obj_dir("isa")`). The root and data directory can be overridden with the `MEDVERSE_ROOT` and `MEDVERSE_DATA_DIR` environment variables.

---

## Key facts at a glance

| | BodyParts3D v4.0 | Human Brainnetome Atlas |
|---|---|---|
| Content | 3D anatomical meshes (`.obj`) plus metadata tables | 246-region brain parcellation (NIfTI volumes, labels) |
| Provider | Database Center for Life Science (DBCLS), Japan | Brainnetome Center, CASIA |
| Download | Automated script | Manual, then checked by script |
| License | CC BY 4.0 | Non-commercial with attribution; separate license needed for commercial use |

The licensing summary above is a convenience. In case of conflict, the current upstream license terms take precedence (see [Sources & licensing](data/sources_and_licensing.md)).

---

## Conventions

- **`raw/` is read-only.** Original downloads are never modified or renamed. Extracted or intermediate files go in `data/interim/`.
- **Data is not committed.** Everything under `data/` is git-ignored, apart from the `.gitkeep` placeholders that preserve the folder structure.
- **Checksums identify your copy.** They are generated from your own download and do not prove authenticity unless compared with a trusted upstream value.

---

## Clinical & regulatory notice

The data and assets in this project are intended for educational use, scientific research, anatomical simulation and algorithm testing. They are not intended for medical diagnosis, treatment recommendations, surgical guidance or patient-specific clinical decision support. No clinical warranties are implied.

---

## Maintaining these docs

1. When `bodyparts3d.py` or `check_brainnetome.py` changes, update the file tables in `download_and_layout.md`.
2. When `src/medverse/paths.py` changes, update the paths in `download_and_layout.md` and the references in `foundational_model.md`.
3. Keep `download_and_layout.md` and `sources_and_licensing.md` consistent with each other.
4. Update the identifier formats in `foundational_model.md` whenever `data_dictionary.md` changes.
5. When adding a new dataset, add it to the contents table, the key facts table and the licensing document together.