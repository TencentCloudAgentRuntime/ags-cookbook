.DEFAULT_GOAL := run

.PHONY: run check

run:
	@echo "Follow README.md (English) or README_zh.md (Chinese) for the complete Brain and Hands Session integration tutorial."

check:
	python3 -m py_compile session_demo.py
	$(MAKE) -C brain check
	$(MAKE) -C hands check
