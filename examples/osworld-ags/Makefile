.PHONY: setup run check clean

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

check:
	python3 -m py_compile \
		overlay/OSWorld/run_multienv.py \
		overlay/OSWorld/desktop_env/providers/ags/provider.py \
		overlay/OSWorld/desktop_env/providers/ags/cdp_proxy.py
	python3 -m unittest discover -s tests -v

clean:
	rm -rf $(OSWORLD_VENV)
