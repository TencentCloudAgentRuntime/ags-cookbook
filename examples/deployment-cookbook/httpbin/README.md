# httpbin Deployment Examples

This directory uses one published httpbin image and separates Deployment behavior into four independent Markdown tutorials:

1. [simple](./simple/README.md): the shortest complete workflow and two access paths.
2. [scaling](./scaling/README.md): on-demand startup, warm instances, and per-instance request concurrency.
3. [lifecycle](./lifecycle/README.md): stopping and pausing idle instances.
4. [affinity](./affinity/README.md): shared and exclusive session affinity.

Every tutorial uses `agr` and `curl` directly in a terminal and creates and deletes its own Sandbox Tool and Deployments. They share only the image and do not share live cloud resources.

The published image is `ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0`. Build and publication instructions are in [dockerfiles](./dockerfiles/README.md).

## Prerequisites

- Complete the shared [Deployment Cookbook prerequisites](../README.md#prerequisites).
- Install `curl` and keep local port `18080` free when a tutorial uses the local proxy.
- Run every example in `ap-shanghai`; each command sets the region explicitly.
