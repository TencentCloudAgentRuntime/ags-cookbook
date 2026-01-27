# 加载 .env 文件
ifneq (,$(wildcard .env))
    include .env
    export
endif

# 默认值
TENCENTCLOUD_REGION ?= ap-guangzhou
AGS_HOST ?= ags.tencentcloudapi.com
AGS_DATA_PLANE_DOMAIN_SUFFIX ?= tencentags.com

# 构建 k6 with xk6-ags
.PHONY: build
build:
	xk6 build --with xk6-ags=.

# 运行测试脚本
.PHONY: run
run:
	./k6 run $(SCRIPT)

# 示例: make run SCRIPT=test.js

.PHONY: clean
clean:
	rm -rf ./k6

.PHONY: lint
lint:
	golangci-lint run --fix .
