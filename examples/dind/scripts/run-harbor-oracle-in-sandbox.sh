#!/usr/bin/env bash
set -Eeuo pipefail

harbor_version="${HARBOR_VERSION:-0.22.0}"
tb3_ref="${TB3_REF:-v3.0.0}"
tb3_task="${TB3_TASK:-intrastat-meldung}"
base_dir="/mnt/ags-dind"
checkout_dir="${base_dir}/terminal-bench-${tb3_ref}"
run_dir="${base_dir}/harbor-oracle-${tb3_task}-${tb3_ref}"
trials_dir="${run_dir}/trials"
trial_name="${tb3_task}-oracle-$(date +%Y%m%d%H%M%S)-$$"
result_file="${trials_dir}/${trial_name}/result.json"

print_command() {
  local argument
  if [[ -z "${NO_COLOR:-}" ]]; then
    printf '\033[1;36m' >&2
  fi
  printf '$' >&2
  for argument in "$@"; do
    printf ' %q' "${argument}" >&2
  done
  if [[ -z "${NO_COLOR:-}" ]]; then
    printf '\033[0m' >&2
  fi
  printf '\n' >&2
}

run_command() {
  print_command "$@"
  "$@"
}

fail() {
  printf 'Harbor Oracle validation: FAIL: %s\n' "$*" >&2
  exit 1
}

# 该 runner 必须在 DinD Sandbox 内以 root 执行，Harbor 会直接连接内层 Docker daemon。
[[ "$(id -u)" == "0" ]] || fail "the runner must execute as root"
run_command docker info >/dev/null
run_command docker compose version

# Harbor 和 TB3 的下载、镜像构建都发生在 Sandbox 内，不依赖本机 Python 或 Docker。
printf 'Installing the tools required by Harbor\n'
run_command apk add --no-cache coreutils curl git python3
if ! command -v uv >/dev/null 2>&1; then
  print_command curl -LsSf https://astral.sh/uv/install.sh
  curl -LsSf https://astral.sh/uv/install.sh \
    | env UV_INSTALL_DIR=/usr/local/bin sh
fi
run_command uv --version

# 固定 TB3 版本并只检出当前 Compose 任务；重复运行时复用数据盘上的 checkout。
run_command mkdir -p "${base_dir}" "${trials_dir}"
if [[ ! -d "${checkout_dir}/.git" ]]; then
  run_command git clone \
    --depth 1 \
    --filter=blob:none \
    --sparse \
    --branch "${tb3_ref}" \
    https://github.com/harbor-framework/terminal-bench.git \
    "${checkout_dir}"
  run_command git -C "${checkout_dir}" sparse-checkout set "tasks/${tb3_task}"
else
  printf 'Reusing Terminal-Bench checkout at %s\n' "${checkout_dir}"
fi

task_dir="${checkout_dir}/tasks/${tb3_task}"
[[ -f "${task_dir}/task.toml" ]] || fail "task.toml is missing from ${task_dir}"
checkout_tag="$(git -C "${checkout_dir}" describe --tags --exact-match 2>/dev/null || true)"
[[ "${checkout_tag}" == "${tb3_ref}" ]] \
  || fail "checkout is at ${checkout_tag:-an unexpected revision}, expected ${tb3_ref}"

# Harbor 原生完成完整生命周期：启动原始 Compose 环境、运行 Oracle、按 task.toml
# 收集跨 service artifacts、启动 separate verifier，并在结束后清理 Compose 资源。
printf 'Running Terminal-Bench %s with Harbor %s Oracle\n' "${tb3_task}" "${harbor_version}"
run_command uvx --from "harbor==${harbor_version}" harbor trial start \
  --path "${task_dir}" \
  --agent oracle \
  --env docker \
  --trial-name "${trial_name}" \
  --trials-dir "${trials_dir}"

# 再读取 Harbor 生成的结构化结果，避免只依赖终端日志判断成功。
[[ -f "${result_file}" ]] || fail "Harbor did not write ${result_file}"
run_command python3 - "${result_file}" "${tb3_task}" <<'PY'
import json
import sys

result_path, expected_task = sys.argv[1:]
with open(result_path, encoding="utf-8") as handle:
    result = json.load(handle)

if result.get("task_name") != f"terminal-bench/{expected_task}":
    raise SystemExit(f"unexpected task: {result.get('task_name')}")
if result.get("exception_info") is not None:
    raise SystemExit(f"trial failed: {result['exception_info']}")
if result.get("verifier_environment_mode") != "separate":
    raise SystemExit("the verifier did not run in separate mode")
reward = (result.get("verifier_result") or {}).get("rewards", {}).get("reward")
if reward != 1.0:
    raise SystemExit(f"expected reward 1.0, got {reward!r}")

print(f"Harbor Oracle validation: PASS ({result_path})")
PY
