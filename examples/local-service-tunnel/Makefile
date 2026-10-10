.PHONY: run cleanup build-images

run:
	set -a; [ ! -f .env ] || . ./.env; set +a; python3 scripts/run.py

cleanup:
	set -a; [ ! -f .env ] || . ./.env; set +a; python3 scripts/cleanup.py

build-images:
	./scripts/build-images.sh
