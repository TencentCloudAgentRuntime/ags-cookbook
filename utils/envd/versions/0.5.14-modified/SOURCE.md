# envd 0.5.14-modified source provenance

This distribution is based on the public `e2b-dev/infra` envd source at
revision `a3fb26eb4344bbaf66c0d2478c086623b560ef41`. It applies the changes
listed below and packages the result as `0.5.14-modified`.

The source changes:

- capture envd's startup identity and environment as command defaults;
- preserve the effective UID, GID, and supplementary groups when commands and
  filesystem operations run as envd's startup user;
- allow requests without an explicit username to use that startup identity;
- run requested commands directly so an unprivileged envd does not require
  privileges for nice, OOM score, or redundant credential changes;
- consistently use the no-op cgroup manager;
- default to standalone logging mode;
- avoid creating runtime marker files; and
- disable envd-managed port scanning and forwarding.

The distribution makes these packaging changes:

- `shared/` contains only the public shared packages imported by envd, and its
  module metadata is reduced to those dependencies.
- `src/go.mod` resolves the matching `shared/` module locally.
- Selected public source files, tests, and build metadata required by this
  distribution are included.
- The source Makefile provides a local binary build; distribution-level builds
  use the Makefile in `utils/envd`.
- Focused tests cover startup identity, environment, permissions, process
  execution, and filesystem identity defaults.

The source is distributed under Apache License 2.0. See `LICENSE`.
