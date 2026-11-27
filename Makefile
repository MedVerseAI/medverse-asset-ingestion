.PHONY: test lint run quest3

test:
	pytest -v

lint:
	ruff check src scripts tests
	python -m compileall -q src scripts

run:
	python -m medverse.cli run --profile brain_spine

quest3:
	python -m medverse.cli run --profile quest3_lod0
