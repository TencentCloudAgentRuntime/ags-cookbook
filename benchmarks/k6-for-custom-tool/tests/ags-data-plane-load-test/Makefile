# 加载 .env 文件 (仅用于腾讯云凭证)
ifneq (,$(wildcard .env))
    include .env
    export
endif

K6_BIN ?= ../../_output/bin/k6
K6_PROMETHEUS_RW_TREND_STATS ?= p(50),p(75),p(90),p(95),p(99),min,max,avg

.PHONY: local
local:
	K6_PROMETHEUS_RW_TREND_STATS="$(K6_PROMETHEUS_RW_TREND_STATS)" \
	$(K6_BIN) run ./local/script.js

.PHONY: distributed
distributed: prepare
	kubectl delete -k ./distributed/ --ignore-not-found
	kubectl apply -k ./distributed/
	rm -f ./distributed/script.js ./distributed/config.js ./distributed/.env ./distributed/config.yaml

.PHONY: clean
clean: prepare
	kubectl delete -k ./distributed/ --ignore-not-found
	rm -f ./distributed/script.js ./distributed/config.js ./distributed/.env ./distributed/config.yaml

.PHONY: prepare
prepare:
	cp ./local/script.js ./distributed/script.js
	cp ./local/config.js ./distributed/config.js
	cp .env ./distributed/.env
	cp ./distributed-config.yaml ./distributed/config.yaml
