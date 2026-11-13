SHELL := /bin/bash
.DEFAULT_GOAL := run
export SCENARIO

.PHONY: run setup preflight cleanup

setup:
	@test -f .env || cp .env.example .env
	@echo "Edit .env, then run make preflight SCENARIO=simple."

preflight:
	@test -f .env || { echo 'Run make setup and edit .env first.' >&2; exit 1; }
	@set -e; set -a; source .env; set +a; bash scripts/preflight.sh "$$SCENARIO"

cleanup:
	@set -e; if test -f .env; then set -a; source .env; set +a; fi; python3 scripts/resources.py cleanup "$$SCENARIO" --yes

run:
	@echo "Choose a managed harness scenario and follow its README:"
	@echo "  simple"
	@echo "  revisions"
	@echo "  connect"
	@echo "  tool-market"
	@echo "  scaling-session"
