.DEFAULT_GOAL := run

.PHONY: setup run register smoke test check cleanup

setup:
	pnpm install --frozen-lockfile
	pnpm --dir plugins/dsh-agent-registry install --frozen-lockfile
	pnpm --dir plugins/dsh-collaboration-stage install --frozen-lockfile

run:
	@test -f .env || { echo "Copy .env.example to .env and fill in the values first."; exit 1; }
	pnpm start

register:
	@test -f .env || { echo "Copy .env.example to .env and fill in the values first."; exit 1; }
	pnpm run register

smoke:
	@test -f .env || { echo "Copy .env.example to .env and fill in the values first."; exit 1; }
	pnpm run smoke

test:
	pnpm test
	pnpm test:plugins

check: test
	python3 ../../.repo/check_repo_contracts.py

cleanup:
	@test -f .env || { echo "Copy .env.example to .env and fill in the values first."; exit 1; }
	@echo "This deletes only the five records matching DEMO_RECORD_PREFIX."
	CONFIRM_DELETE=yes pnpm run cleanup
