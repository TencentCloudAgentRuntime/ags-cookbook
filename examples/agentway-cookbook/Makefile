.DEFAULT_GOAL := help

.PHONY: help setup run

help:
	@printf '%s\n' \
		"Available targets:" \
		"  make setup  # Check local CLI prerequisites" \
		"  make run    # List the guide entry points"

setup:
	@command -v kubectl >/dev/null || { echo "kubectl is required"; exit 1; }
	@command -v helm >/dev/null || { echo "helm 4.x is required for the full AgentWay installation path"; exit 1; }
	@echo "AgentWay Cookbook prerequisites are available."

run:
	@printf '%s\n' \
		"Choose a guide:" \
		"  openclaw-browser-on-TencentAGS/README.md" \
		"  hermes-dashboard-on-TencentAGS/README.md" \
		"  hermes-on-TKE/README.md" \
		"  agentway-monitoring-dashboard/README.md"
