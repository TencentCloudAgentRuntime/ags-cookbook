#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
production_template="$script_dir/manifests/cube-cri-load-pod.yaml"
simple_template="$script_dir/manifests/cube-cri-load-simple-pod.yaml"
template=""
runtime_class="$script_dir/manifests/cube-cri-load-runtimeclass.yaml"
runtime_class_name=cube-load
system_namespace=cube-cri-load-system
generator_service_account=cube-cri-load-generator
generator_role=cube-cri-load-generator
managed_label_key="app.kubernetes.io/managed-by"
managed_label_value="cube-cri-performance-test"
generator_owner_label="cube-cri-load-generator-owner"

stage=""
generator_node=""
run_id=""
output=""
count=""
namespace_count=""
qps=""
workers=""
timeout_seconds=""
stable_seconds=""
target_node=""
target_node_selector=""
expected_target_nodes=0
target_node_csv=""
snapshotter_profile=""
load_image=""
cube_template_mode=""
workload_profile=""
image_state=""
ready_p99_slo_ms=""
allowed_image_identities="${CUBE_LOAD_ALLOWED_IMAGE_IDENTITIES:-}"
kubelet_registry_pull_qps=0
kubelet_registry_burst=0
generator_image="${CUBE_LOAD_GENERATOR_IMAGE:-}"
generator_image_pull_policy="${CUBE_LOAD_GENERATOR_IMAGE_PULL_POLICY:-IfNotPresent}"
generator_max_schedule_delay_ms="${CUBE_LOAD_GENERATOR_MAX_SCHEDULE_DELAY_MS:-20}"
generator_max_watch_handler_ms="${CUBE_LOAD_GENERATOR_MAX_WATCH_HANDLER_MS:-5}"

erox_load_image="${CUBE_LOAD_EROX_IMAGE:-}"
erox_equivalent_image_identities="sha256:b116e155074440ffd9e449559433feb4cd2341eb3554b1da1c638c976e56451d,sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662"
overlayfs_simple_load_image="mirror.ccs.tencentyun.com/library/ubuntu:24.04"
overlayfs_production_load_image="mirror.ccs.tencentyun.com/library/node@sha256:48e4b67d85f87bd551df43704e24d252f56cc5f8e9718841aace50f19948f0f9"

usage() {
  cat >&2 <<EOF
Usage: $0 --stage S0|S1|S2|capacity --generator-node NODE [--target-node NODE] [--run-id ID] [--output DIR]

Workload template options:
  --workload-profile production|simple
      production: Production-like template with init containers, multiple containers, volumes, and probes
      simple:     Single long-running container without init containers, volumes, probes, or ServiceAccount token mounts (default)

Image and snapshotter options:
  --snapshotter-profile erox|overlayfs
      erox:      Use the official EROX workload image and set agc.cloud.tencent.com/cube-template-mode=auto
      overlayfs: Use a regular overlayfs image and remove the cube-template-mode annotation
  --load-image IMAGE
      Override the profile's default image for every init container and container
  --cube-template-mode auto|none
      Override the profile's template mode
  --image-state cold|pre-pulled
      Record the controlled image state on target nodes; required for the capacity stage
  --allowed-image-identities DIGEST[,DIGEST...]
      Optional equivalent image digests for diagnostics; identity differences do not affect acceptance
  --ready-p99-slo-ms MILLISECONDS
      Strict P99 limit from Create start to first Ready observation; capacity default: 2000
  --generator-image IMAGE
      Go load-generator image supplied by the product team (required)
  --generator-image-pull-policy IfNotPresent|Never|Always
  --generator-max-schedule-delay-ms MILLISECONDS
      P99 gate for generator submission scheduling delay (default: 20ms)
  --generator-max-watch-handler-ms MILLISECONDS
      Gate for processing one watch event (default: 5ms)
  --target-node-selector KEY=VALUE
      Exact selector for multi-node tests; written to Pod nodeSelector and used to validate node coverage
  --expected-target-nodes COUNT
      Number of Ready Cube nodes that the selector must resolve

Capacity preflight gate:
  Target-node kubelets must have effective registryPullQPS=150 and registryBurst=200.
  The script validates configz and refuses to run when values are missing or inconsistent.
EOF
}

while (($#)); do
  case "$1" in
    --stage) stage="$2"; shift 2 ;;
    --generator-node) generator_node="$2"; shift 2 ;;
    --run-id) run_id="$2"; shift 2 ;;
    --output) output="$2"; shift 2 ;;
    --count) count="$2"; shift 2 ;;
    --namespaces) namespace_count="$2"; shift 2 ;;
    --qps) qps="$2"; shift 2 ;;
    --workers) workers="$2"; shift 2 ;;
    --timeout) timeout_seconds="$2"; shift 2 ;;
    --stable-seconds) stable_seconds="$2"; shift 2 ;;
    --target-node) target_node="$2"; shift 2 ;;
    --target-node-selector) target_node_selector="$2"; shift 2 ;;
    --expected-target-nodes) expected_target_nodes="$2"; shift 2 ;;
    --snapshotter-profile) snapshotter_profile="$2"; shift 2 ;;
    --load-image) load_image="$2"; shift 2 ;;
    --cube-template-mode) cube_template_mode="$2"; shift 2 ;;
    --workload-profile) workload_profile="$2"; shift 2 ;;
    --image-state) image_state="$2"; shift 2 ;;
    --allowed-image-identities) allowed_image_identities="$2"; shift 2 ;;
    --ready-p99-slo-ms) ready_p99_slo_ms="$2"; shift 2 ;;
    --generator-image) generator_image="$2"; shift 2 ;;
    --generator-image-pull-policy) generator_image_pull_policy="$2"; shift 2 ;;
    --generator-max-schedule-delay-ms) generator_max_schedule_delay_ms="$2"; shift 2 ;;
    --generator-max-watch-handler-ms) generator_max_watch_handler_ms="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

[[ -n "$stage" && -n "$generator_node" ]] || { usage; exit 2; }
[[ -n "${KUBECONFIG:-}" && -r "$KUBECONFIG" ]] || { echo "KUBECONFIG must be explicitly set to a readable file" >&2; exit 2; }
[[ -r "$runtime_class" ]] || { echo "RuntimeClass manifest not found: $runtime_class" >&2; exit 2; }

workload_profile="${workload_profile:-simple}"
case "$workload_profile" in
  production) template="$production_template" ;;
  simple) template="$simple_template" ;;
  *) echo "workload-profile must be production or simple" >&2; exit 2 ;;
esac
[[ -r "$template" ]] || { echo "Workload template not found: $template" >&2; exit 2; }

case "$stage" in
  S0) defaults=(1 1 1 1 600 0) ;;
  S1) defaults=(2000 1 1000 200 1800 180) ;;
  S2) defaults=(5000 5 1000 400 1800 600) ;;
  capacity) defaults=(50 1 50 50 1800 60) ;;
  *) echo "stage must be S0, S1, S2, or capacity" >&2; exit 2 ;;
esac
count="${count:-${defaults[0]}}"
namespace_count="${namespace_count:-${defaults[1]}}"
qps="${qps:-${defaults[2]}}"
workers="${workers:-${defaults[3]}}"
timeout_seconds="${timeout_seconds:-${defaults[4]}}"
stable_seconds="${stable_seconds:-${defaults[5]}}"
ready_p99_slo_ms="${ready_p99_slo_ms:-$([[ "$stage" == capacity ]] && echo 2000 || echo 0)}"
snapshotter_profile="${snapshotter_profile:-overlayfs}"
case "$snapshotter_profile" in
  erox)
    load_image="${load_image:-$erox_load_image}"
    cube_template_mode="${cube_template_mode:-auto}"
    ;;
  overlayfs)
    if [[ -z "$load_image" ]]; then
      case "$workload_profile" in
        simple) load_image="$overlayfs_simple_load_image" ;;
        production) load_image="$overlayfs_production_load_image" ;;
      esac
    fi
    cube_template_mode="${cube_template_mode:-none}"
    ;;
  *) echo "snapshotter-profile must be erox or overlayfs" >&2; exit 2 ;;
esac
case "$cube_template_mode" in
  auto|none) ;;
  *) echo "cube-template-mode must be auto or none" >&2; exit 2 ;;
esac
if [[ -n "$erox_load_image" && "$load_image" == "$erox_load_image" && -z "$allowed_image_identities" ]]; then
  allowed_image_identities="$erox_equivalent_image_identities"
fi
if [[ "$stage" == capacity ]]; then
  [[ -n "$target_node" ]] || { echo "--target-node is required for the capacity stage" >&2; exit 2; }
  case "$image_state" in
    cold|pre-pulled) ;;
    *) echo "--image-state must be cold or pre-pulled for the capacity stage" >&2; exit 2 ;;
  esac
else
  image_state="${image_state:-uncontrolled}"
  case "$image_state" in cold|pre-pulled|uncontrolled) ;; *) echo "image-state must be cold, pre-pulled, or uncontrolled" >&2; exit 2 ;; esac
fi
[[ -n "$load_image" ]] || { echo "load-image must not be empty" >&2; exit 2; }
[[ -n "$generator_image" ]] || { echo "generator-image must not be empty" >&2; exit 2; }
case "$generator_image_pull_policy" in IfNotPresent|Never|Always) ;; *) echo "generator-image-pull-policy must be IfNotPresent, Never, or Always" >&2; exit 2 ;; esac
run_id="${run_id:-$(tr '[:upper:]' '[:lower:]' <<<"$stage")-$(date -u +%Y%m%dT%H%M%SZ)}"
run_id="$(printf '%s' "$run_id" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+|-+$//g' | cut -c1-32)"
[[ -n "$run_id" ]] || { echo "run-id is empty after normalization" >&2; exit 2; }
output="${output:-$script_dir/_output/cube-cri-scale/$run_id}"

for value in "$count" "$namespace_count" "$qps" "$workers" "$timeout_seconds" "$stable_seconds" "$ready_p99_slo_ms" "$expected_target_nodes"; do
  [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric argument: $value" >&2; exit 2; }
done
if [[ -n "$target_node" && -n "$target_node_selector" ]]; then
  echo "--target-node and --target-node-selector are mutually exclusive" >&2
  exit 2
fi
if [[ -n "$target_node_selector" ]]; then
  [[ "$target_node_selector" =~ ^[^=]+=[^=]+$ ]] || { echo "target-node-selector must use KEY=VALUE format" >&2; exit 2; }
  target_selector_key="${target_node_selector%%=*}"
  target_selector_value="${target_node_selector#*=}"
  target_nodes_json="$(kubectl get nodes -l "$target_node_selector" -o json)"
  actual_target_nodes="$(jq '.items | length' <<<"$target_nodes_json")"
  ((actual_target_nodes > 0)) || { echo "Node selector matched no nodes: $target_node_selector" >&2; exit 1; }
  if ((expected_target_nodes > 0 && actual_target_nodes != expected_target_nodes)); then
    echo "Node selector expected $expected_target_nodes nodes but matched $actual_target_nodes" >&2
    exit 1
  fi
  invalid_target_nodes="$(jq -r '.items[] | select(([.status.conditions[] | select(.type=="Ready") | .status][0] != "True") or (.metadata.labels["agc.cloud.tencent.com/cube-ready"] != "true")) | .metadata.name' <<<"$target_nodes_json")"
  [[ -z "$invalid_target_nodes" ]] || { echo "Target nodes are not Ready Cube nodes: $invalid_target_nodes" >&2; exit 1; }
  target_node_csv="$(jq -r '[.items[].metadata.name] | sort | join(",")' <<<"$target_nodes_json")"
else
  target_selector_key=""
  target_selector_value=""
  [[ -z "$target_node" ]] || target_node_csv="$target_node"
fi
for value in "$generator_max_schedule_delay_ms" "$generator_max_watch_handler_ms"; do
  [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo "Invalid generator gate value: $value" >&2; exit 2; }
done
if [[ "$stage" == capacity ]] && ((ready_p99_slo_ms != 2000)); then
  echo "The capacity stage requires the strict P99 < 2000ms gate" >&2
  exit 2
fi
((count > 0 && namespace_count > 0 && qps > 0 && workers > 0 && timeout_seconds > 0)) || {
  echo "count, namespaces, qps, workers, and timeout must be greater than zero" >&2
  exit 2
}

node_json="$(kubectl get node "$generator_node" -o json)"
[[ "$(jq -r '.status.conditions[] | select(.type=="Ready") | .status' <<<"$node_json")" == True ]] || {
  echo "Generator node is not Ready: $generator_node" >&2
  exit 1
}
if [[ -n "$target_node" ]]; then
  [[ "$target_node" != "$generator_node" ]] || { echo "Target node must differ from the generator node" >&2; exit 1; }
  target_node_json="$(kubectl get node "$target_node" -o json)"
  [[ "$(jq -r '.status.conditions[] | select(.type=="Ready") | .status' <<<"$target_node_json")" == True ]] || {
    echo "Target node is not Ready: $target_node" >&2
    exit 1
  }
  [[ "$(jq -r '.metadata.labels["agc.cloud.tencent.com/cube-ready"] // ""' <<<"$target_node_json")" == true ]] || {
    echo "Target node is not a Cube node: $target_node" >&2
    exit 1
  }
fi
if [[ "$stage" == capacity ]]; then
  kubelet_config_json="$(kubectl get --raw "/api/v1/nodes/$target_node/proxy/configz")"
  kubelet_registry_pull_qps="$(jq -er '.kubeletconfig.registryPullQPS' <<<"$kubelet_config_json")"
  kubelet_registry_burst="$(jq -er '.kubeletconfig.registryBurst' <<<"$kubelet_config_json")"
  [[ "$kubelet_registry_pull_qps" == 150 && "$kubelet_registry_burst" == 200 ]] || {
    echo "The capacity stage requires kubelet registryPullQPS=150 and registryBurst=200; current values: $kubelet_registry_pull_qps/$kubelet_registry_burst" >&2
    exit 1
  }
fi

assert_managed_or_absent() {
  local kind="$1"
  local name="$2"
  local actual
  if kubectl get "$kind" "$name" >/dev/null 2>&1; then
    actual="$(kubectl get "$kind" "$name" -o json | jq -r \
      --arg key "$managed_label_key" '.metadata.labels[$key] // ""')"
    [[ "$actual" == "$managed_label_value" ]] || {
      echo "Fixed-name resource exists but is not managed by this tool: $kind/$name" >&2
      exit 1
    }
  fi
}

assert_managed_or_absent namespace "$system_namespace"
assert_managed_or_absent runtimeclass "$runtime_class_name"
assert_managed_or_absent clusterrole "$generator_role"

if kubectl get namespace "$system_namespace" >/dev/null 2>&1; then
  active_generators="$(kubectl get pods -n "$system_namespace" \
    -l app=cube-cri-load-generator -o json | jq '.items | length')"
  ((active_generators == 0)) || {
    echo "Uncleaned load-generator Pods found; refusing to start another test" >&2
    exit 1
  }
fi
active_load_pods="$(kubectl get pods -A -l load-test-batch -o json | jq '.items | length')"
((active_load_pods == 0)) || {
  echo "Uncleaned workload Pods found; refusing to start a new test: $active_load_pods" >&2
  exit 1
}

generator_node_marked="$(jq -r '
  ((.metadata.labels["cube-cri-load-generator"] // "") != "")
  or ([.spec.taints[]? | select(.key == "cube-cri-load-generator")] | length > 0)
' <<<"$node_json")"
generator_node_owner="$(jq -r --arg key "$generator_owner_label" \
  '.metadata.labels[$key] // ""' <<<"$node_json")"
if [[ "$generator_node_marked" == true && "$generator_node_owner" != "$managed_label_value" ]]; then
  echo "Generator node has labels or taints not managed by this tool: $generator_node" >&2
  exit 1
fi
if [[ -n "$generator_node_owner" && "$generator_node_owner" != "$managed_label_value" ]]; then
  echo "Generator node owner label conflicts with this tool: $generator_node_owner" >&2
  exit 1
fi

owned_artifacts=(
  artifacts.sha256 batch-summary.json done exit-code generator-events.json
  generator-pod.json generator.log pod-template.json pods.jsonl run-config.json
  cleanup.sh manifests README.md run.sh SHA256SUMS sop-functions.sh VERSION
  runtimeclass.yaml source-pod-template.yaml warning-events.json
)
for artifact in "${owned_artifacts[@]}"; do
  if [[ -e "$output/$artifact" ]]; then
    echo "Output directory already contains test artifacts; refusing to mix results: $output/$artifact" >&2
    exit 1
  fi
done
mkdir -p "$output"
cp "$script_dir/README.md" "$output/README.md"
cp "$script_dir/SHA256SUMS" "$output/SHA256SUMS"
cp "$script_dir/VERSION" "$output/VERSION"
cp "$script_dir/cleanup.sh" "$output/cleanup.sh"
cp "$0" "$output/run.sh"
cp "$script_dir/sop-functions.sh" "$output/sop-functions.sh"
cp -a "$script_dir/manifests" "$output/manifests"
cp "$template" "$output/source-pod-template.yaml"
cp "$runtime_class" "$output/runtimeclass.yaml"
kubectl label node "$generator_node" \
  cube-cri-load-generator=true \
  "$generator_owner_label=$managed_label_value" \
  --overwrite >/dev/null
kubectl taint node "$generator_node" cube-cri-load-generator=true:NoSchedule --overwrite >/dev/null
kubectl apply -f "$runtime_class" >/dev/null

kubectl create namespace "$system_namespace" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl label namespace "$system_namespace" \
  "$managed_label_key=$managed_label_value" --overwrite >/dev/null
kubectl create serviceaccount "$generator_service_account" -n "$system_namespace" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl apply -f - >/dev/null <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: $generator_role
  labels:
    $managed_label_key: $managed_label_value
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["create", "get", "list", "watch", "delete"]
EOF

target_namespaces=()
for ((index=0; index<namespace_count; index++)); do
  namespace="cube-cri-load-${run_id}-${index}"
  target_namespaces+=("$namespace")
  kubectl apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: $namespace
  labels:
    cube-cri-load-owned: "true"
    load-test-run: "$run_id"
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: cube-cri-load
  namespace: $namespace
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: $generator_role
  namespace: $namespace
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: $generator_role
subjects:
  - kind: ServiceAccount
    name: $generator_service_account
    namespace: $system_namespace
EOF
done
namespace_csv="$(IFS=,; echo "${target_namespaces[*]}")"

yq -o=json '.' "$template" \
  | jq \
      --arg image "$load_image" \
      --arg profile "$snapshotter_profile" \
      --arg workloadProfile "$workload_profile" \
      --arg templateMode "$cube_template_mode" \
      --arg targetSelectorKey "$target_selector_key" \
      --arg targetSelectorValue "$target_selector_value" '
        def set_images($image):
          .spec.containers = ((.spec.containers // []) | map(.image = $image))
          | if (.spec.initContainers? // null) == null then .
            else .spec.initContainers |= map(.image = $image)
            end;
        def prune_empty_annotations:
          if ((.metadata.annotations // {}) | length) == 0 then del(.metadata.annotations) else . end;

        set_images($image)
        | .metadata.labels = (.metadata.labels // {})
        | .metadata.labels["load-test-snapshotter-profile"] = $profile
        | .metadata.labels["load-test-workload-profile"] = $workloadProfile
        | if $workloadProfile == "simple" then
            .spec.serviceAccountName = "default"
          else . end
        | if $targetSelectorKey != "" then
            .spec.nodeSelector = (.spec.nodeSelector // {})
            | .spec.nodeSelector[$targetSelectorKey] = $targetSelectorValue
          else . end
        | if $templateMode == "auto" then
            .metadata.annotations = (.metadata.annotations // {})
            | .metadata.annotations["agc.cloud.tencent.com/cube-template-mode"] = "auto"
          elif $templateMode == "none" then
            del(.metadata.annotations["agc.cloud.tencent.com/cube-template-mode"])
            | prune_empty_annotations
          else .
          end
      ' > "$output/pod-template.json"
jq -n \
  --arg runId "$run_id" --arg stage "$stage" --arg generatorNode "$generator_node" \
  --arg namespaces "$namespace_csv" --argjson count "$count" --argjson qps "$qps" \
  --argjson workers "$workers" --argjson timeout "$timeout_seconds" \
  --argjson stable "$stable_seconds" --arg targetNode "$target_node" \
  --arg snapshotterProfile "$snapshotter_profile" --arg loadImage "$load_image" \
  --arg cubeTemplateMode "$cube_template_mode" --arg workloadProfile "$workload_profile" \
  --arg imageState "$image_state" --argjson readyP99SLOMs "$ready_p99_slo_ms" \
  --arg allowedImageIdentities "$allowed_image_identities" \
  --arg generatorImage "$generator_image" --arg generatorImagePullPolicy "$generator_image_pull_policy" \
  --arg targetNodeSelector "$target_node_selector" --arg targetNodes "$target_node_csv" \
  --argjson generatorMaxScheduleDelayMs "$generator_max_schedule_delay_ms" \
  --argjson generatorMaxWatchHandlerMs "$generator_max_watch_handler_ms" \
  --argjson kubeletRegistryPullQPS "$kubelet_registry_pull_qps" --argjson kubeletRegistryBurst "$kubelet_registry_burst" \
  '{runId:$runId,stage:$stage,generatorNode:$generatorNode,targetNode:$targetNode,targetNodeSelector:$targetNodeSelector,targetNodes:($targetNodes|if length == 0 then [] else split(",") end),targetNamespaces:($namespaces|split(",")),podCount:$count,createQPS:$qps,createWorkers:$workers,timeoutSeconds:$timeout,stableSeconds:$stable,workloadProfile:$workloadProfile,snapshotterProfile:$snapshotterProfile,loadImage:$loadImage,allowedImageIdentities:($allowedImageIdentities|if length == 0 then [] else split(",") end),cubeTemplateMode:$cubeTemplateMode,imageState:$imageState,readyP99SLOMs:$readyP99SLOMs,generator:{implementation:"go",image:$generatorImage,imagePullPolicy:$generatorImagePullPolicy,maxScheduleDelayMs:$generatorMaxScheduleDelayMs,maxWatchHandlerMs:$generatorMaxWatchHandlerMs},kubeletConfig:{registryPullQPS:$kubeletRegistryPullQPS,registryBurst:$kubeletRegistryBurst}}' \
  > "$output/run-config.json"
config_map="cube-cri-load-${run_id}"
generator_pod="cube-cri-load-generator-${run_id}"
kubectl create configmap "$config_map" -n "$system_namespace" \
  --from-file=pod-template.json="$output/pod-template.json" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
jq --arg namespace "${target_namespaces[0]}" '.metadata.namespace = $namespace' "$output/pod-template.json" \
  | kubectl apply --server-side --dry-run=server -f - >/dev/null

kubectl apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $generator_pod
  namespace: $system_namespace
  labels:
    app: cube-cri-load-generator
    load-test-run: "$run_id"
spec:
  serviceAccountName: $generator_service_account
  restartPolicy: Never
  terminationGracePeriodSeconds: 0
  securityContext:
    fsGroup: 65532
    fsGroupChangePolicy: OnRootMismatch
  nodeSelector:
    kubernetes.io/hostname: "$generator_node"
    cube-cri-load-generator: "true"
  tolerations:
    - key: cube-cri-load-generator
      operator: Equal
      value: "true"
      effect: NoSchedule
  containers:
    - name: generator
      image: "$generator_image"
      imagePullPolicy: $generator_image_pull_policy
      env:
        - {name: GOMAXPROCS, value: "16"}
        - {name: RUN_ID, value: "$run_id"}
        - {name: TARGET_NAMESPACES, value: "$namespace_csv"}
        - {name: POD_COUNT, value: "$count"}
        - {name: CREATE_QPS, value: "$qps"}
        - {name: CREATE_WORKERS, value: "$workers"}
        - {name: TIMEOUT_SECONDS, value: "$timeout_seconds"}
        - {name: STABLE_SECONDS, value: "$stable_seconds"}
        - {name: TARGET_NODE, value: "$target_node"}
        - {name: TARGET_NODES, value: "$target_node_csv"}
        - {name: WORKLOAD_PROFILE, value: "$workload_profile"}
        - {name: STAGE, value: "$stage"}
        - {name: SNAPSHOTTER_PROFILE, value: "$snapshotter_profile"}
        - {name: LOAD_IMAGE, value: "$load_image"}
        - {name: ALLOWED_IMAGE_IDENTITIES, value: "$allowed_image_identities"}
        - {name: CUBE_TEMPLATE_MODE, value: "$cube_template_mode"}
        - {name: IMAGE_STATE, value: "$image_state"}
        - {name: READY_P99_SLO_MS, value: "$ready_p99_slo_ms"}
        - {name: KUBELET_REGISTRY_PULL_QPS, value: "$kubelet_registry_pull_qps"}
        - {name: KUBELET_REGISTRY_BURST, value: "$kubelet_registry_burst"}
        - {name: GENERATOR_MAX_SCHEDULE_DELAY_MS, value: "$generator_max_schedule_delay_ms"}
        - {name: GENERATOR_MAX_WATCH_HANDLER_MS, value: "$generator_max_watch_handler_ms"}
        - {name: TEMPLATE_PATH, value: /config/pod-template.json}
        - {name: OUTPUT_DIR, value: /output}
      resources:
        requests: {cpu: "16", memory: 4Gi}
        limits: {cpu: "16", memory: 4Gi}
      volumeMounts:
        - {name: config, mountPath: /config, readOnly: true}
        - {name: output, mountPath: /output}
    - name: artifact-holder
      image: mirror.ccs.tencentyun.com/library/node@sha256:48e4b67d85f87bd551df43704e24d252f56cc5f8e9718841aace50f19948f0f9
      imagePullPolicy: IfNotPresent
      command: ["node", "-e"]
      args: ["setInterval(() => {}, 86400000);"]
      resources:
        requests: {cpu: 100m, memory: 64Mi}
        limits: {cpu: 100m, memory: 64Mi}
      volumeMounts:
        - {name: output, mountPath: /output, readOnly: true}
  volumes:
    - name: config
      configMap:
        name: $config_map
    - name: output
      emptyDir: {}
EOF

startup_deadline=$((SECONDS + 300))
while ((SECONDS < startup_deadline)); do
  container_started="$(kubectl get pod -n "$system_namespace" "$generator_pod" -o jsonpath='{.status.containerStatuses[?(@.name=="generator")].state.running.startedAt}' 2>/dev/null || true)"
  container_terminated="$(kubectl get pod -n "$system_namespace" "$generator_pod" -o jsonpath='{.status.containerStatuses[?(@.name=="generator")].state.terminated.exitCode}' 2>/dev/null || true)"
  [[ -n "$container_started" || -n "$container_terminated" ]] && break
  sleep 1
done
[[ -n "$container_started" || -n "$container_terminated" ]] || { kubectl describe pod -n "$system_namespace" "$generator_pod" > "$output/generator-describe.txt"; exit 1; }
deadline=$((SECONDS + timeout_seconds + stable_seconds + 300))
while ((SECONDS < deadline)); do
  state="$(kubectl get pod -n "$system_namespace" "$generator_pod" -o jsonpath='{.status.containerStatuses[?(@.name=="generator")].state.terminated.exitCode}' 2>/dev/null || true)"
  [[ -n "$state" ]] && break
  sleep 2
done
[[ -n "$state" ]] || { kubectl describe pod -n "$system_namespace" "$generator_pod" > "$output/generator-describe.txt"; exit 1; }
kubectl logs -n "$system_namespace" "$generator_pod" -c generator > "$output/generator.log" 2>&1 || true
kubectl cp -n "$system_namespace" -c artifact-holder "$generator_pod:/output/." "$output" >/dev/null
kubectl get pod -n "$system_namespace" "$generator_pod" -o json > "$output/generator-pod.json"
kubectl get events -n "$system_namespace" --field-selector "involvedObject.name=$generator_pod" -o json > "$output/generator-events.json"
warning_events='{"apiVersion":"v1","kind":"List","items":[]}'
warning_collection_errors=()
for namespace in "${target_namespaces[@]}"; do
  if namespace_events="$(kubectl get events -n "$namespace" --field-selector type=Warning -o json)"; then
    warning_events="$(jq --argjson events "$namespace_events" '.items += $events.items' <<<"$warning_events")"
  else
    warning_collection_errors+=("$namespace")
  fi
done
printf '%s\n' "$warning_events" > "$output/warning-events.json"
warning_count="$(jq '.items | length' "$output/warning-events.json")"
jq \
  --argjson warningCount "$warning_count" \
  --arg warningCollectionErrors "$(IFS=,; echo "${warning_collection_errors[*]}")" \
  --slurpfile warningEvents "$output/warning-events.json" '
    ($warningEvents[0].items // []) as $items
    | .workloadWarnings = {
        count: $warningCount,
        affectedPods: ([$items[].involvedObject.name // empty] | unique),
        reasons: ([$items[].reason // empty] | sort | group_by(.) | map({reason: .[0], count: length})),
        collectionErrors: ($warningCollectionErrors | if length == 0 then [] else split(",") end)
      }
    | if ($warningCollectionErrors | length) > 0 then
        .success = false
        | .errors += ["failed to collect Warning events from: \($warningCollectionErrors)"]
      else . end
    | .accepted = (.success and (.slo.passed != false))
  ' "$output/batch-summary.json" > "$output/batch-summary.json.tmp"
mv "$output/batch-summary.json.tmp" "$output/batch-summary.json"
if ((${#warning_collection_errors[@]} > 0)); then
  state=1
fi
printf '%s\n' "$state" > "$output/exit-code"
printf 'FINAL_SUMMARY_JSON=%s\n' "$(jq -c . "$output/batch-summary.json")" >> "$output/generator.log"
(
  cd "$output"
  find . -type f ! -name artifacts.sha256 -print0 | sort -z | xargs -0 sha256sum > artifacts.sha256
)
printf 'run_id=%s generator_exit=%s output=%s\n' "$run_id" "$state" "$output"
printf 'cleanup: %s/cleanup.sh --run-id %s\n' "$script_dir" "$run_id"
exit "$state"
