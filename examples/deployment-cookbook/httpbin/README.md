# httpbin Deployment Examples

This directory uses one pinned httpbin image and separates Deployment behavior into four independent Markdown tutorials:

1. [simple](./simple/README.md): the shortest complete workflow and two access paths.
2. [scaling](./scaling/README.md): on-demand startup, warm instances, and request-concurrency leases.
3. [lifecycle](./lifecycle/README.md): stopping and pausing idle instances.
4. [affinity](./affinity/README.md): the three session-affinity strategies.

Every tutorial uses `agr` and `curl` directly in a terminal and creates and deletes its own Sandbox Tool and Deployments. They share only the image and do not share live cloud resources.

The image is pinned to `ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0`. Build assets and publication instructions are in [dockerfiles](./dockerfiles/README.md).
