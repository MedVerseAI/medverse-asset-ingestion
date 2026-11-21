test:
	python tests/run_all.py
parity:
	python tools/parity_selection.py
run:
	python -m medverse.cli run --profile brain_spine
