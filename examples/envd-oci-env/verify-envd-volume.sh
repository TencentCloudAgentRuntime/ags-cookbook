#!/usr/bin/env bash
# Verify the envd Image Volume artifact's file metadata from its exported layer.
#
# The requirement is that /usr/bin/envd is owned by 0:0 with mode 4755 *in the
# image layer*, because an Image Volume mount is read-only: a runtime chmod is not
# an option. Reading the metadata out of the layer archive checks the artifact
# itself rather than the behavior of whatever container happens to run it.
#
# `docker save` emits either the legacy layout (a directory per layer containing
# layer.tar) or the OCI layout (layers as blobs under blobs/sha256/, possibly
# gzipped). Both are handled, and every blob is probed rather than assuming which
# one holds the binary.
#
# Usage: ./verify-envd-volume.sh <image-reference>
set -Eeuo pipefail

image="${1:?usage: verify-envd-volume.sh <image-reference>}"

workdir="$(mktemp -d)"
cleanup() { rm -rf "${workdir}"; }
trap cleanup EXIT

echo "== verifying ${image}"

docker save "${image}" -o "${workdir}/image.tar"
mkdir -p "${workdir}/unpacked"
tar -xf "${workdir}/image.tar" -C "${workdir}/unpacked"

# List every candidate layer archive: legacy layer.tar files, and OCI blobs (which
# have no extension and may be gzipped or plain tar).
mapfile -t candidates < <(
  find "${workdir}/unpacked" -type f \( -name 'layer.tar' -o -path '*/blobs/sha256/*' -o -name '*.tar' -o -name '*.tar.gz' \) | sort
)

if [[ "${#candidates[@]}" -eq 0 ]]; then
  echo "FAIL: no layer archives found in the export of ${image}" >&2
  exit 1
fi

# tar reads gzip transparently with -z; try plain first, then gzipped.
list_entry() {
  local archive="$1"
  tar -tvf "${archive}" --numeric-owner 2>/dev/null \
    | awk '$NF == "usr/bin/envd" || $NF == "./usr/bin/envd"' \
    || true
}

found=""
entry=""

for candidate in "${candidates[@]}"; do
  entry="$(list_entry "${candidate}")"
  if [[ -n "${entry}" ]]; then
    found="${candidate}"
    break
  fi
done

if [[ -z "${found}" ]]; then
  echo "FAIL: usr/bin/envd not found in any of the ${#candidates[@]} layer archives of ${image}" >&2
  exit 1
fi

# tar -tv prints e.g. "-rwsr-xr-x 0/0 10387604 2026-08-11 01:08 usr/bin/envd"
mode="$(printf '%s' "${entry}" | awk '{print $1}')"
owner_field="$(printf '%s' "${entry}" | awk '{print $2}')"
uid="${owner_field%%/*}"
gid="${owner_field##*/}"

echo "   layer:      ${found#"${workdir}/unpacked/"}"
echo "   tar mode:   ${mode}"
echo "   tar owner:  ${uid}:${gid}"

status=0

if [[ "${uid}" != "0" || "${gid}" != "0" ]]; then
  echo "FAIL: /usr/bin/envd owner is ${uid}:${gid}, expected 0:0" >&2
  status=1
else
  echo "   OK: owner is 0:0"
fi

# `s` in the owner-execute position is the setuid bit; the rest must be rwxr-xr-x.
if [[ "${mode}" != "-rwsr-xr-x" ]]; then
  echo "FAIL: /usr/bin/envd mode is ${mode}, expected -rwsr-xr-x (4755)" >&2
  status=1
else
  echo "   OK: mode is -rwsr-xr-x (4755), setuid bit present"
fi

# Cross-check by extracting the file and stat-ing it. tar preserves the setuid bit
# only for a privileged extractor, so a mismatch here when the listing was correct
# means the extractor lacked privileges, not that the artifact is wrong.
extract_dir="${workdir}/extracted"
mkdir -p "${extract_dir}"

extracted=false
for member in usr/bin/envd ./usr/bin/envd; do
  if tar -xf "${found}" -C "${extract_dir}" --numeric-owner -p "${member}" 2>/dev/null; then
    extracted=true
    break
  fi
done

if [[ "${extracted}" == true ]]; then
  numeric_mode="$(stat -c '%04a' "${extract_dir}/usr/bin/envd")"
  numeric_owner="$(stat -c '%u:%g' "${extract_dir}/usr/bin/envd")"
  binary_sha="$(sha256sum "${extract_dir}/usr/bin/envd" | awk '{print $1}')"
  binary_size="$(stat -c '%s' "${extract_dir}/usr/bin/envd")"

  echo "   stat mode:  ${numeric_mode}"
  echo "   stat owner: ${numeric_owner}"
  echo "   size:       ${binary_size}"
  echo "   sha256:     ${binary_sha}"

  if [[ "${numeric_mode}" != "4755" ]]; then
    echo "FAIL: extracted mode is ${numeric_mode}, expected 4755" >&2
    status=1
  fi

  if [[ "${numeric_owner}" != "0:0" ]]; then
    echo "FAIL: extracted owner is ${numeric_owner}, expected 0:0" >&2
    status=1
  fi
else
  echo "   note: could not extract for a stat cross-check; the tar listing above stands"
fi

if [[ "${status}" -ne 0 ]]; then
  echo
  echo "VERIFY FAILED: ${image} must not be used for AGS testing" >&2
  exit 1
fi

echo
echo "VERIFY OK: ${image} carries /usr/bin/envd as 0:0 mode 4755"
