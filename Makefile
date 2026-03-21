.DEFAULT_GOAL := help

EXAMPLES := $(shell find examples -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
EXAMPLE ?=

.PHONY: help bootstrap examples-list report-status contract-check docs-check python-check go-check check example-setup example-run smoke

help:
	@echo "Available targets:"
	@echo "  make bootstrap              # Check required local tools"
	@echo "  make examples-list          # List example directories"
	@echo "  make check                  # Run local repository checks"
	@echo "  make contract-check         # Validate example/readme/makefile contracts"
	@echo "  make python-check           # Syntax-check tracked Python files"
	@echo "  make go-check               # Build Go examples"
	@echo "  make report-status          # Summarize local example run reports"
	@echo "  make example-setup EXAMPLE=name  # Run make setup in one example"
	@echo "  make example-run EXAMPLE=name    # Run make run in one example"
	@echo "  make smoke EXAMPLE=name          # Run make smoke if present, else make run"

bootstrap:
	@command -v uv >/dev/null || { echo "uv is required"; exit 1; }
	@command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
	@command -v go >/dev/null || { echo "go is required for Go examples"; exit 1; }
	@command -v git >/dev/null || { echo "git is required"; exit 1; }
	@echo "Tooling looks good."

examples-list:
	@printf '%s\n' $(EXAMPLES)

contract-check docs-check:
	@python3 scripts/check_repo_contracts.py

python-check:
	@python3 scripts/python_syntax_check.py

go-check:
	@set -e; \
	for dir in examples/*; do \
		if [ -f "$$dir/go.mod" ]; then \
			echo "==> go build ./... in $$dir"; \
			( cd "$$dir" && go build ./... ); \
		fi; \
	done

check: bootstrap docs-check python-check go-check
	@echo "Local checks passed."


report-status:
	@python3 -c "from pathlib import Path; root=Path('reports/example-runs'); \
print('No reports/example-runs directory yet.') if not root.exists() else [print(f'{f.stem:24} status={next((line.split(\": \",1)[1] for line in f.read_text(encoding=\"utf-8\").splitlines() if line.startswith(\"- Status:\")), \"?\"):12} result={next((line.split(\": \",1)[1] for line in f.read_text(encoding=\"utf-8\").splitlines() if line.startswith(\"- Result:\")), \"?\")}') for f in sorted(root.glob('*.md')) if f.name != 'README.md']"

example-setup:
	@test -n "$(EXAMPLE)" || { echo "EXAMPLE=name is required"; exit 1; }
	@test -d "examples/$(EXAMPLE)" || { echo "unknown example: $(EXAMPLE)"; exit 1; }
	@$(MAKE) -C examples/$(EXAMPLE) setup

example-run:
	@test -n "$(EXAMPLE)" || { echo "EXAMPLE=name is required"; exit 1; }
	@test -d "examples/$(EXAMPLE)" || { echo "unknown example: $(EXAMPLE)"; exit 1; }
	@$(MAKE) -C examples/$(EXAMPLE) run

smoke:
	@test -n "$(EXAMPLE)" || { echo "EXAMPLE=name is required"; exit 1; }
	@test -d "examples/$(EXAMPLE)" || { echo "unknown example: $(EXAMPLE)"; exit 1; }
	@if $(MAKE) -C examples/$(EXAMPLE) -n smoke >/dev/null 2>&1; then \
		$(MAKE) -C examples/$(EXAMPLE) smoke; \
	else \
		$(MAKE) -C examples/$(EXAMPLE) run; \
	fi
