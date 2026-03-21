.PHONY: setup run clean

OSWORLD_DIR := osworld
OSWORLD_PYTHON := 3.10
OSWORLD_VENV := $(OSWORLD_DIR)/.venv
OSWORLD_PY := $(OSWORLD_VENV)/bin/python

setup:
	@test -d $(OSWORLD_DIR) || (echo "missing $(OSWORLD_DIR): clone OSWorld first" && exit 1)
	uv python install $(OSWORLD_PYTHON)
	uv venv --python $(OSWORLD_PYTHON) $(OSWORLD_VENV)
	cd $(OSWORLD_DIR) && uv pip install --python .venv/bin/python -r requirements.txt

run:
	@test -x $(OSWORLD_PY) || (echo "missing $(OSWORLD_VENV): run 'make setup' first" && exit 1)
	cd $(OSWORLD_DIR) && .venv/bin/python quickstart.py --provider_name ags

clean:
	rm -rf $(OSWORLD_VENV)
