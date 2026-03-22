.DEFAULT_GOAL := help

EXAMPLES := $(shell find examples -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)
EXAMPLE ?=

.PHONY: help examples-list example-setup example-run

help:
	@echo "Available targets:"
	@echo "  make examples-list               # List example directories"
	@echo "  make example-setup EXAMPLE=name  # Run make setup in one example"
	@echo "  make example-run EXAMPLE=name    # Run make run in one example"

examples-list:
	@printf '%s\n' $(EXAMPLES)

example-setup:
	@test -n "$(EXAMPLE)" || { echo "EXAMPLE=name is required"; exit 1; }
	@test -d "examples/$(EXAMPLE)" || { echo "unknown example: $(EXAMPLE)"; exit 1; }
	@$(MAKE) -C examples/$(EXAMPLE) setup

example-run:
	@test -n "$(EXAMPLE)" || { echo "EXAMPLE=name is required"; exit 1; }
	@test -d "examples/$(EXAMPLE)" || { echo "unknown example: $(EXAMPLE)"; exit 1; }
	@$(MAKE) -C examples/$(EXAMPLE) run
