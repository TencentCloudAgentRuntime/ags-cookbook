BUILD_REVISION ?= a3fb26e-modified
LDFLAGS := -ldflags "-X=main.commitSHA=$(BUILD_REVISION)"

.PHONY: build clean
build:
	@mkdir -p bin
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -a -o bin/envd $(LDFLAGS)

clean:
	rm -rf bin
