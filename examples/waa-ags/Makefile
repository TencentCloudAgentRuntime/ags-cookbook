.PHONY: setup run clean

WAA_DIR := waa
WAA_PYTHON := 3.10
WAA_CLIENT_DIR := $(WAA_DIR)/src/win-arena-container/client
WAA_VENV := $(WAA_CLIENT_DIR)/.venv
WAA_PY := $(WAA_VENV)/bin/python
UV ?= $(shell command -v uv 2>/dev/null || printf '%s/.local/bin/uv' "$$HOME")
MODEL ?= gpt-4o
TEST_META ?= evaluation_examples_windows/test_small.json
SOM_ORIGIN ?= a11y
A11Y_BACKEND ?= uia
MAX_STEPS ?= 15

setup:
	@test -d $(WAA_DIR) || (echo "missing $(WAA_DIR): clone WindowsAgentArena first" && exit 1)
	$(UV) python install $(WAA_PYTHON)
	$(UV) venv --clear --python $(WAA_PYTHON) $(WAA_VENV)
	cd $(WAA_CLIENT_DIR) && $(UV) pip install --python .venv/bin/python -r requirements.txt
	cd $(WAA_CLIENT_DIR) && .venv/bin/python -m playwright install chromium

run:
	@test -x $(WAA_PY) || (echo "missing $(WAA_VENV): run 'make setup' first" && exit 1)
	cd $(WAA_CLIENT_DIR) && .venv/bin/python run_ags.py --model $(MODEL) --test_all_meta_path $(TEST_META) --som_origin $(SOM_ORIGIN) --a11y_backend $(A11Y_BACKEND) --max_steps $(MAX_STEPS)

clean:
	rm -rf $(WAA_VENV)
