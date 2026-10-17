# Usage: make download | export | integrate | pipeline | test
# Override Blender:  make integrate BLENDER="/path/to/blender"
PYTHON  ?= python
BLENDER ?= blender

.PHONY: install download check-bn export-bp3d export-bna export integrate pipeline test paths

install:
	$(PYTHON) -m pip install -e ".[export,dev]"

download:                       ## BodyParts3D (automatic)
	$(PYTHON) scripts/downloaders/bodyparts3d.py

check-bn:                       ## Brainnetome (manual download, then verify)
	$(PYTHON) scripts/downloaders/check_brainnetome.py

export-bp3d:                    ## step 01
	$(PYTHON) scripts/pipeline/01_export_bodyparts3d.py

export-bna:                     ## step 02 (independent of 01)
	$(PYTHON) scripts/pipeline/02_export_bna_voxels.py

export: export-bp3d export-bna

integrate:                      ## step 03 (needs 01 + 02), runs inside Blender
	$(BLENDER) --background --python scripts/pipeline/03_integrate_brainnetome_bodyparts3d.py

pipeline: export integrate

test:
	$(PYTHON) -m pytest

paths:
	$(PYTHON) -c "from medverse import paths; [print(f'{k:22s} {v}') for k, v in paths.describe().items()]"
