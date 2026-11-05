#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${OUTPUT_DIR:=$root/.local}"
source "$root/tests/e2e/assertions.sh"
# Bash 3.2 on macOS has neither mapfile nor readarray.
read_lines() {
  local target="$1" value
  eval "$target=()"
  while IFS= read -r value; do
    eval "$target+=(\"\$value\")"
  done
}
sha256() { node -e 'const fs=require("node:fs"),crypto=require("node:crypto"); console.log(crypto.createHash("sha256").update(fs.readFileSync(process.argv[1])).digest("hex"))' "$1"; }
: "${KUBECONFIG:?KUBECONFIG 未设置}"
: "${NAMESPACE:=dsh-awv}"
mkdir -p "$OUTPUT_DIR"
timings="$OUTPUT_DIR/timings.csv"

k() { kubectl --kubeconfig "$KUBECONFIG" -n "$NAMESPACE" "$@"; }
state_field() {
  local field="$1"
  k get configmap pelican-workspace-state -o jsonpath='{.data.state}' \
    | node -e "let s='';process.stdin.on('data',c=>s+=c).on('end',()=>console.log(JSON.parse(s)['$field']))"
}
job_names() {
  local role="$1"
  k get jobs -l "app=dsh-awv,role=$role" -o json \
    | jq -r '.items[].metadata.name' | sort
}
new_jobs() {
  local role="$1" before="$2"
  comm -13 \
    <(printf '%s\n' "$before" | sed '/^$/d' | sort) \
    <(job_names "$role" | sed '/^$/d' | sort)
}
sort_jobs_by_creation() {
  local name
  for name in "$@"; do
    printf '%s %s\n' "$(k get job "$name" -o jsonpath='{.metadata.creationTimestamp}')" "$name"
  done | sort | awk '{print $2}'
}
site_url() {
  local host
  for _ in $(seq 1 120); do
    host="$(k get svc pelican-site -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
    [[ -n "$host" ]] || host="$(k get svc pelican-site -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
    if [[ -n "$host" ]]; then echo "http://$host"; return 0; fi
    sleep 3
  done
  return 1
}
assert_agent_job() {
  local name="$1" role="$2"
  local spec="$OUTPUT_DIR/$name.json"
  k get job "$name" -o json > "$spec"
  jq -e '.spec.template.spec.containers[0].command == ["/usr/bin/tini","--","dsh"]' "$spec" >/dev/null
  jq -e --arg patch "/opt/pelican/profiles/$role.patch.yml" \
    '.spec.template.spec.containers[0].args[3] == $patch and .spec.template.spec.containers[0].args[4] == "$(DSH_TASK)"' \
    "$spec" >/dev/null
  if grep -Eq 'apply-task|create-review|validate-review|validate-site|browser-check|/bin/sh' "$spec"; then
    fail "$name 仍依赖业务脚本或 shell 编排"
  fi
}
assert_browser_review() {
  local name="$1" expected="$2" log
  log="$OUTPUT_DIR/$name.log"
  k logs "job/$name" --timestamps=true > "$log"
  assert_matches "$log" '1440x900'
  assert_matches "$log" '390x844'
  assert_matches "$log" '截图|[Ss]creenshot'
  assert_matches "$log" 'scrollWidth'
  assert_matches "$log" 'animationPlayState|动画'
  assert_matches "$log" 'console|控制台'
  assert_matches "$log" "DSH_REVIEW_RESULT=.*\"status\"[[:space:]]*:[[:space:]]*\"$expected\""
}
run_harness() {
  local scenario="$1" prompt="$2" log
  log="$OUTPUT_DIR/$scenario.log"
  local start_seconds end_seconds
  start_seconds="$(date +%s)"
  k exec -i deployment/dsh-harness -- sh -lc \
    'cd /tmp; task="$(cat)"; dsh --profile agc-headless --patch /opt/pelican/controller/web.patch.yml "$task"' \
    < "$prompt" | tee "$log"
  end_seconds="$(date +%s)"
  ROUND_DURATION="$((end_seconds-start_seconds))"
}
record_round() {
  local scenario="$1" code_job="$2" review_job="$3" url="$4"
  local generation code_node review_node site_node
  generation="$(state_field generation)"
  code_node="$(k get pod -l job-name="$code_job" -o jsonpath='{.items[0].spec.nodeName}')"
  review_node="$(k get pod -l job-name="$review_job" -o jsonpath='{.items[0].spec.nodeName}')"
  site_node="$(k get pod -l app=pelican-site -o jsonpath='{.items[0].spec.nodeName}')"
  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$scenario" "$ROUND_DURATION" "$generation" "$code_job" "$code_node" \
    "$review_job" "$review_node" "$site_node" "$url" >> "$timings"
}
seed_mobile_overflow() {
  local name="e2e-overflow-$(date +%s)" worker_image pull_secret pull_block node_block
  worker_image="$(k get deployment dsh-harness -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="DSH_WORKER_IMAGE")].value}')"
  pull_secret="$(k get deployment dsh-harness -o jsonpath='{.spec.template.spec.imagePullSecrets[0].name}')"
  pull_block=""
  node_block=""
  if [[ -n "$pull_secret" ]]; then
    pull_block="      imagePullSecrets:\n        - name: $pull_secret"
  fi
  if [[ -n "${CODE_NODE:-}" ]]; then
    node_block="      nodeSelector:\n        kubernetes.io/hostname: $CODE_NODE"
  fi

  k scale deployment/pelican-site --replicas=0
  k wait --for=delete pod -l app=pelican-site --timeout=5m || true
  printf '%b\n' "apiVersion: batch/v1
kind: Job
metadata:
  name: $name
  labels:
    app: dsh-awv-e2e
spec:
  backoffLimit: 0
  template:
    spec:
      automountServiceAccountToken: false
      restartPolicy: Never
$pull_block
$node_block
      securityContext:
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
      containers:
        - name: seed
          image: $worker_image
          command: [\"node\"]
          args:
            - -e
            - |
              const fs = require('node:fs');
              const path = '/workspace/site/index.html';
              let html = fs.readFileSync(path, 'utf8');
              if (!html.includes('</head>')) throw new Error('index.html 缺少 </head>');
              html = html.replace('</head>', '<style id=\"e2e-mobile-overflow\">html{min-width:1200px!important}</style></head>');
              fs.writeFileSync(path, html);
          volumeMounts:
            - name: workspace
              mountPath: /workspace/site
      volumes:
        - name: workspace
          persistentVolumeClaim:
            claimName: pelican-workspace" | k apply -f -
  k wait --for=condition=complete "job/$name" --timeout=5m
  k delete job "$name" --wait=true

  local dirty
  dirty="$(k get configmap pelican-workspace-state -o jsonpath='{.data.state}' \
    | node -e 'let s="";process.stdin.on("data",c=>s+=c).on("end",()=>{const v=JSON.parse(s);v.generation+=1;v.reviewStatus="DIRTY";v.updatedAt=new Date().toISOString();process.stdout.write(JSON.stringify(v))})')"
  k create configmap pelican-workspace-state --from-literal=state="$dirty" --dry-run=client -o yaml | k apply -f -
}

printf 'scenario,duration_seconds,generation,code_job,code_node,review_job,review_node,site_node,url\n' > "$timings"
initial_generation="0"
if k get configmap pelican-workspace-state >/dev/null 2>&1; then
  initial_generation="$(state_field generation)"
fi

before_code="$(job_names code)"
before_review="$(job_names review)"
run_harness first-task "$root/examples/prompts/create-pelican.md"
read_lines first_codes < <(new_jobs code "$before_code")
read_lines first_reviews < <(new_jobs review "$before_review")
read_lines first_codes < <(sort_jobs_by_creation "${first_codes[@]}")
read_lines first_reviews < <(sort_jobs_by_creation "${first_reviews[@]}")
if (( ${#first_codes[@]} < 1 || ${#first_codes[@]} > 2 )); then
  fail "首次任务应创建 1 个 Code Job，或在首次 Review FAIL 后再创建 1 个 Fix Job"
fi
assert_eq "${#first_reviews[@]}" "${#first_codes[@]}"
assert_eq "$(state_field generation)" "$((initial_generation+${#first_codes[@]}))"
assert_eq "$(state_field reviewStatus)" "PASS"
for job in "${first_codes[@]}"; do assert_agent_job "$job" code; done
for job in "${first_reviews[@]}"; do assert_agent_job "$job" review; done
if (( ${#first_reviews[@]} == 2 )); then assert_browser_review "${first_reviews[0]}" FAIL; fi
first_code="${first_codes[$((${#first_codes[@]}-1))]}"
first_review="${first_reviews[$((${#first_reviews[@]}-1))]}"
assert_browser_review "$first_review" PASS
k rollout status deployment/pelican-site --timeout=5m
first_url="$(site_url)"
curl --fail --retry 30 --retry-delay 2 --retry-all-errors "$first_url/" -o "$OUTPUT_DIR/first-task.html"
assert_contains "$OUTPUT_DIR/first-task.html" 'data-testid="pelican-scene"'
first_hash="$(sha256 "$OUTPUT_DIR/first-task.html" | awk '{print $1}')"
record_round first-task "$first_code" "$first_review" "$first_url"

first_generation="$(state_field generation)"
seed_mobile_overflow
dirty_generation="$((first_generation+1))"
assert_eq "$(state_field generation)" "$dirty_generation"
assert_eq "$(state_field reviewStatus)" "DIRTY"
before_code="$(job_names code)"
before_review="$(job_names review)"
run_harness review-fix "$root/examples/prompts/update-pelican.md"
read_lines repair_codes < <(new_jobs code "$before_code")
read_lines repair_reviews < <(new_jobs review "$before_review")
read_lines repair_reviews < <(sort_jobs_by_creation "${repair_reviews[@]}")
assert_eq "${#repair_codes[@]}" "1"
assert_eq "${#repair_reviews[@]}" "2"
assert_eq "$(state_field generation)" "$((dirty_generation+1))"
assert_eq "$(state_field reviewStatus)" "PASS"
assert_agent_job "${repair_codes[0]}" code
assert_agent_job "${repair_reviews[0]}" review
assert_agent_job "${repair_reviews[1]}" review
assert_browser_review "${repair_reviews[0]}" FAIL
assert_browser_review "${repair_reviews[1]}" PASS
k rollout status deployment/pelican-site --timeout=5m
follow_up_url="$(site_url)"
assert_eq "$follow_up_url" "$first_url"
curl --fail --retry 30 --retry-delay 2 --retry-all-errors "$follow_up_url/" -o "$OUTPUT_DIR/review-fix.html"
assert_contains "$OUTPUT_DIR/review-fix.html" 'AWV-ROUND-2'
assert_not_contains "$OUTPUT_DIR/review-fix.html" 'e2e-mobile-overflow'
follow_up_hash="$(sha256 "$OUTPUT_DIR/review-fix.html" | awk '{print $1}')"
record_round review-fix "${repair_codes[0]}" "${repair_reviews[1]}" "$follow_up_url"

code_node="$(k get pod -l job-name="${repair_codes[0]}" -o jsonpath='{.items[0].spec.nodeName}')"
review_node="$(k get pod -l job-name="${repair_reviews[1]}" -o jsonpath='{.items[0].spec.nodeName}')"
site_node="$(k get pod -l app=pelican-site -o jsonpath='{.items[0].spec.nodeName}')"
if [[ -n "${CODE_NODE:-}" ]]; then assert_eq "$code_node" "$CODE_NODE"; fi
if [[ -n "${REVIEW_NODE:-}" ]]; then assert_eq "$review_node" "$REVIEW_NODE"; fi
if [[ -n "${SITE_NODE:-}" ]]; then assert_eq "$site_node" "$SITE_NODE"; fi
if [[ -n "${CODE_NODE:-}" && -n "${REVIEW_NODE:-}" ]]; then assert_not_eq "$code_node" "$review_node"; fi
if [[ -n "${REVIEW_NODE:-}" && -n "${SITE_NODE:-}" ]]; then assert_not_eq "$review_node" "$site_node"; fi
if [[ -n "${CODE_NODE:-}" && -n "${SITE_NODE:-}" ]]; then assert_not_eq "$code_node" "$site_node"; fi

old_pod="$(k get pod -l app=pelican-site -o jsonpath='{.items[0].metadata.name}')"
k delete pod "$old_pod" --wait=true
k rollout status deployment/pelican-site --timeout=5m
new_pod="$(k get pod -l app=pelican-site -o jsonpath='{.items[0].metadata.name}')"
assert_not_eq "$old_pod" "$new_pod"
url="$(site_url)"
curl --fail --retry 30 --retry-delay 2 --retry-all-errors "$url/" -o "$OUTPUT_DIR/after-recreate.html"
assert_contains "$OUTPUT_DIR/after-recreate.html" 'AWV-ROUND-2'
recreated_hash="$(sha256 "$OUTPUT_DIR/after-recreate.html" | awk '{print $1}')"
assert_eq "$recreated_hash" "$follow_up_hash"

printf 'first_html_sha256=%s\nreview_fix_html_sha256=%s\nafter_recreate_html_sha256=%s\nrecreated_pod=%s\n' \
  "$first_hash" "$follow_up_hash" "$recreated_hash" "$new_pod" > "$OUTPUT_DIR/result.txt"
echo "E2E PASS: 主 Agent 规划、浏览器 Review、失败修复、发布门禁、跨节点复用和展示 Pod 重建均通过"
cat "$timings"
