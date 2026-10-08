# Cube CRI Performance Test Tools

This standalone bundle accompanies [performance-test-sop.md](../performance-test-sop.md). It does not require a CubeSandbox source checkout.

```text
performance-test-tools/
├── run.sh
├── cleanup.sh
├── sop-functions.sh
├── VERSION
├── SHA256SUMS
└── manifests/
    ├── cube-cri-load-pod.yaml
    ├── cube-cri-load-simple-pod.yaml
    └── cube-cri-load-runtimeclass.yaml
```

`sop-functions.sh` provides the warmup, serial, parallel, and cleanup commands. `run.sh` and `cleanup.sh` are their underlying entry points. Follow the guide, including resource ownership and cleanup checks. The remaining files fix the workload definitions and bundle checksums; users do not need to edit them. The load generator is delivered as a container image, without its source or build files in this bundle.

The helpers default to a pinned generator image. To use another version, set `GENERATOR_IMAGE` before sourcing `sop-functions.sh`. Basic tests use overlayfs by default; EROX tests require separate enablement. Image identity differences are diagnostic only and do not affect acceptance.

From this directory, verify the bundle:

```bash
chmod +x run.sh cleanup.sh
bash -n run.sh cleanup.sh sop-functions.sh
sha256sum -c SHA256SUMS
test -r manifests/cube-cri-load-simple-pod.yaml
test -r manifests/cube-cri-load-runtimeclass.yaml
```

See the guide in the parent directory for prerequisites, parameters, execution, and cleanup.
