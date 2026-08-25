# httpbin Deployment Examples

This directory uses one pinned httpbin image and separates Deployment behavior into four independent notebooks:

1. [simple](./simple/httpbin-simple_en.ipynb): the shortest complete workflow and two access paths.
2. [scaling](./scaling/httpbin-scaling_en.ipynb): on-demand startup, warm instances, and request-concurrency leases.
3. [lifecycle](./lifecycle/httpbin-lifecycle_en.ipynb): stopping and pausing idle instances.
4. [affinity](./affinity/httpbin-affinity_en.ipynb): the three session-affinity strategies.

Every notebook creates and deletes its own Sandbox Tool and Deployments. They share only the image and do not share live cloud resources.

The image is pinned to `ccr.ccs.tencentyun.com/ags.dev/go-httpbin:v2.25.0`. Build assets and publication instructions are in [dockerfiles](./dockerfiles/README.md).
