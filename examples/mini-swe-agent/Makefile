REPO_DIR := mini-swe-agent
SWEREX_DIR := $(REPO_DIR)/SWE-ReX
RESULTS_DIR := $(CURDIR)/results
WORKERS ?= 4
PYTHON_VERSION ?= 3.12

MINI_SWE_AGENT_REPO := https://github.com/SWE-agent/mini-SWE-agent.git
SWEREX_REPO := https://github.com/SWE-agent/SWE-ReX.git

.PHONY: setup run run-full logs tail clean

setup:
	@echo "Setting up mini-swe-agent with AGS support (overlay mode)..."
	@command -v uv >/dev/null 2>&1 || { echo "Error: uv is required. Install from https://github.com/astral-sh/uv"; exit 1; }
	@test -d $(REPO_DIR) || git clone --depth 1 $(MINI_SWE_AGENT_REPO) $(REPO_DIR)
	@test -d $(SWEREX_DIR) || git clone --depth 1 $(SWEREX_REPO) $(SWEREX_DIR)
	@echo "Applying AGS overlay to mini-swe-agent..."
	cp -R overlay/mini-swe-agent/. $(REPO_DIR)/
	@echo "Applying AGS overlay to SWE-ReX..."
	cp -R overlay/SWE-ReX/. $(SWEREX_DIR)/
	@test -d $(REPO_DIR)/.venv || (cd $(REPO_DIR) && uv venv --python $(PYTHON_VERSION))
	cd $(REPO_DIR) && \
		uv pip install -e "./SWE-ReX[ags]" && \
		uv pip install -e ".[full,ags]"
	@echo ""
	@echo "Setup complete."
	@echo "  1. Copy .env.example to .env and fill in your Tencent Cloud credentials."
	@echo "  2. Create my_config.yaml with your tool_id and LLM settings (see README)."

run:
	@test -d $(REPO_DIR)/.venv || { echo "Error: run 'make setup' first."; exit 1; }
	@test -f my_config.yaml || { echo "Error: my_config.yaml not found. See README.md for setup instructions."; exit 1; }
	@mkdir -p $(RESULTS_DIR)
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	cd $(REPO_DIR) && \
		uv run mini-extra swebench-single \
		-c swebench_ags \
		-c $(CURDIR)/my_config.yaml \
		-o $(RESULTS_DIR)/interactive.traj.json \
		--subset verified \
		--split test \
		-i 0 -y
	@echo "Run complete. Trajectory saved to $(RESULTS_DIR)/interactive.traj.json"

run-full:
	@test -d $(REPO_DIR)/.venv || { echo "Error: run 'make setup' first."; exit 1; }
	@test -f my_config.yaml || { echo "Error: my_config.yaml not found. See README.md for setup instructions."; exit 1; }
	@mkdir -p $(RESULTS_DIR)
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	cd $(REPO_DIR) && \
		uv run mini-extra swebench \
		-c swebench_ags \
		-c $(CURDIR)/my_config.yaml \
		-o $(RESULTS_DIR) \
		--subset verified \
		--split test \
		-w $(WORKERS)

logs:
	@test -f $(RESULTS_DIR)/minisweagent.log || { echo "No log file found. Run 'make run-full' first."; exit 1; }
	@tail -f $(RESULTS_DIR)/minisweagent.log

tail:
	@if stat --version >/dev/null 2>&1; then \
		file="$$(find $(RESULTS_DIR) -name "*.traj.json" -exec stat -c '%Y %n' {} \; 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"; \
		else \
		file="$$(find $(RESULTS_DIR) -name "*.traj.json" -exec stat -f '%m %N' {} \; 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"; \
	fi; \
	if [ -n "$$file" ]; then \
		echo "Latest trajectory: $$file"; \
		jq . "$$file"; \
	else \
		echo "No trajectory files found"; \
	fi

clean:
	rm -rf $(REPO_DIR) $(RESULTS_DIR)
