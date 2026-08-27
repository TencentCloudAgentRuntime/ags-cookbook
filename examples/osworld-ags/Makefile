.PHONY: clone verify-source setup run check lock clean

OSWORLD_DIR := osworld
OSWORLD_REPOSITORY := https://github.com/xlang-ai/OSWorld.git
OSWORLD_COMMIT := 84aee655c2afb6b77ecf39884432615ba345c031
OSWORLD_PYTHON := 3.12.12
OSWORLD_VENV := $(OSWORLD_DIR)/.venv
OSWORLD_PY := $(OSWORLD_VENV)/bin/python
AGS_LOCK := overlay/OSWorld/requirements-ags.lock

clone:
	@test ! -e $(OSWORLD_DIR) || (echo "$(OSWORLD_DIR) already exists; remove it before cloning" && exit 1)
	git clone $(OSWORLD_REPOSITORY) $(OSWORLD_DIR)
	git -C $(OSWORLD_DIR) checkout --detach $(OSWORLD_COMMIT)
	git -C $(OSWORLD_DIR) -c url.https://github.com/.insteadOf=git@github.com: \
		submodule update --init mm_agents/surferH/agp_client

verify-source:
	@test -d $(OSWORLD_DIR) || (echo "missing $(OSWORLD_DIR): clone OSWorld first" && exit 1)
	@actual=$$(git -C $(OSWORLD_DIR) rev-parse HEAD); \
		test "$$actual" = "$(OSWORLD_COMMIT)" || \
		(echo "unexpected OSWorld commit: $$actual (expected $(OSWORLD_COMMIT))" && exit 1)
	@test -f $(OSWORLD_DIR)/mm_agents/surferH/agp_client/pyproject.toml || \
		(echo "missing OSWorld agp_client submodule: run 'make clone' again" && exit 1)
	@expected=$$(git -C $(OSWORLD_DIR) rev-parse HEAD:mm_agents/surferH/agp_client); \
		actual=$$(git -C $(OSWORLD_DIR)/mm_agents/surferH/agp_client rev-parse HEAD); \
		test "$$actual" = "$$expected" || \
		(echo "unexpected agp_client commit: $$actual (expected $$expected)" && exit 1)

setup: verify-source
	uv python install $(OSWORLD_PYTHON)
	cd $(OSWORLD_DIR) && uv sync --frozen --no-dev --python $(OSWORLD_PYTHON)
	cd $(OSWORLD_DIR) && uv pip install --python .venv/bin/python -r requirements-ags.lock

run:
	@test -x $(OSWORLD_PY) || (echo "missing $(OSWORLD_VENV): run 'make setup' first" && exit 1)
	cd $(OSWORLD_DIR) && .venv/bin/python quickstart.py --provider_name ags

check:
	uv run --no-project --python $(OSWORLD_PYTHON) --with requests python -m py_compile \
		overlay/OSWorld/run_multienv.py \
		overlay/OSWorld/desktop_env/providers/ags/provider.py \
		overlay/OSWorld/desktop_env/providers/ags/cdp_proxy.py \
		overlay/OSWorld/desktop_env/providers/ags/sandbox_setup.py
	bash -n overlay/OSWorld/desktop_env/providers/ags/socat_wrapper.sh
	uv run --no-project --python $(OSWORLD_PYTHON) --with requests python -m unittest discover -s tests -v

lock: verify-source
	@constraints=$$(mktemp); \
		trap 'rm -f "$$constraints"' EXIT; \
		uv export --directory $(OSWORLD_DIR) --frozen --no-dev \
			--no-emit-project --no-emit-local --no-hashes --no-annotate \
			--no-header --output-file "$$constraints"; \
		printf '%s\n' 'e2b-code-interpreter>=2.4.1' 'aiohttp>=3.9.0' | uv pip compile \
		--python-version $(OSWORLD_PYTHON) \
		--universal \
		--default-index https://pypi.org/simple \
		--constraints "$$constraints" \
		--no-annotate \
		--custom-compile-command "make lock" \
		--output-file $(AGS_LOCK) -

clean:
	rm -rf $(OSWORLD_VENV)
