FROM docker.io/library/golang:1.25-alpine3.23 AS builder

RUN apk add --no-cache git make

RUN go install go.k6.io/xk6/cmd/xk6@latest

WORKDIR /build
COPY pkg/xk6-ags ./pkg/xk6-ags
COPY Makefile ./Makefile

RUN make build

FROM docker.io/library/alpine:3.23

RUN apk add --no-cache ca-certificates

COPY --from=builder /build/_output/bin/k6 /usr/local/bin/k6

ENTRYPOINT ["k6"]
