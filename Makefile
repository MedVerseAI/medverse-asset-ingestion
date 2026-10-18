# Usage: make download | export | integrate | pipeline | build | test
# Choose what to build with MODE (default: from configs/default.toml, i.e. integrated):
#   make build MODE=brainnetome      # cerebral cortex only (Brainnetome)
#   make build MODE=bodyparts3d      # brain parts + spine + BodyParts3D cortex
#   make build MODE=integrated       # everything, registered together
#   make build PROFILE=configs/profiles/bodyparts3d.toml
# Override Blender:  make integrate BLENDER="/path/to/blender"
PYTHON  ?= python
BLENDER ?= blender
MODE    ?=
PROFILE ?=
# extra options forwarded to every step, e.g. --mode brainnetome
OPTS    := $(if $(MODE),--mode $(MODE)) $(if $(PROFILE),--config $(PROFILE))

.PHONY: install download check-bn export-bp3d export-bna export integrate pipeline build config test paths

install:
	$(PYTHON) -m pip install -e ".[export,dev]"

download:                       ## BodyParts3D (automatic)
	$(PYTHON) scripts/downloaders/bodyparts3d.py

check-bn:                       ## Brainnetome (manual download, then verify)
	$(PYTHON) scripts/downloaders/check_brainnetome.py

export-bp3d:                    ## step 01
	$(PYTHON) scripts/pipeline/01_export_bodyparts3d.py $(OPTS)

export-bna:                     ## step 02 (independent of 01)
	$(PYTHON) scripts/pipeline/02_export_bna_voxels.py $(OPTS)

export: export-bp3d export-bna

integrate:                      ## step 03 (needs 01 + 02), runs inside Blender
	$(BLENDER) --background --python scripts/pipeline/03_integrate_brainnetome_bodyparts3d.py -- $(OPTS)

pipeline: export integrate           ## every step; steps the mode does not need skip themselves

build:                          ## only the steps the chosen mode needs (scripts/run_pipeline.py)
	$(PYTHON) scripts/run_pipeline.py $(if $(filter command line environment,$(origin BLENDER)),--blender "$(BLENDER)") $(OPTS)

config:                         ## show the resolved settings
	$(PYTHON) scripts/run_pipeline.py --print-config $(OPTS)

test:
	$(PYTHON) -m pytest

paths:
	$(PYTHON) -c "from medverse import paths; [print(f'{k:22s} {v}') for k, v in paths.describe().items()]"
