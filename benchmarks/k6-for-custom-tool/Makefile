# 镜像配置
IMAGE_REPO ?= ccr.ccs.tencentyun.com/finofliu/xk6-ags
IMAGE_TAG ?= latest
IMAGE = $(IMAGE_REPO):$(IMAGE_TAG)

# 构建 k6 with xk6-ags 到 _output/bin 目录
.PHONY: build
build:
	mkdir -p ./_output/bin ./_output/go-cache ./_output/go-tmp
	GOPROXY=https://goproxy.cn \
	GOCACHE=$(CURDIR)/_output/go-cache \
	GOTMPDIR=$(CURDIR)/_output/go-tmp \
	xk6 build -v --with xk6-ags=./pkg/xk6-ags --output ./_output/bin/k6

# 自动检测容器构建工具
CONTAINER_BUILDER := $(shell command -v buildah 2>/dev/null || command -v docker 2>/dev/null)

# 构建 Docker 镜像
.PHONY: docker-build
docker-build:
ifeq ($(findstring buildah,$(CONTAINER_BUILDER)),buildah)
	buildah bud --isolation chroot -t $(IMAGE) .
else
	docker build -t $(IMAGE) .
endif

# 推送 Docker 镜像
.PHONY: docker-push
docker-push:
ifeq ($(findstring buildah,$(CONTAINER_BUILDER)),buildah)
	buildah push $(IMAGE)
else
	docker push $(IMAGE)
endif

# 构建并推送镜像
.PHONY: docker
docker: docker-build docker-push

.PHONY: clean
clean:
	rm -rf ./_output
