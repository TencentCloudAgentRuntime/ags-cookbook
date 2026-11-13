#!/usr/bin/env python3
"""Run agr create commands, remember their IDs, and clean up one scenario."""

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ("simple", "revisions", "connect", "tool-market", "scaling-session")
RESOURCES = {
    "model-provider": (["model-provider"], "ModelProvider", "ModelProviderId"),
    "harness": (["harness"], "Harness", "HarnessId"),
    "session-space": (["session", "space"], "SessionSpace", "SpaceId"),
    "credential-provider": (["credential", "provider"], None, "ProviderId"),
}


def missing(reply):
    code = (reply.get("Failure") or {}).get("Code", "")
    return code.startswith("ResourceNotFound") or code in ("TOOL_NOT_FOUND", "PROVIDER_NOT_FOUND")


def execute(region, args):
    result = subprocess.run(["agr", *args, "--region", region, "-o", "json", "--non-interactive"],
                            text=True, stdout=subprocess.PIPE)
    try:
        reply = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError("agr did not return a JSON envelope; check the preview CLI and run agr doctor.") from None
    return result.returncode, reply


def call(region, args, allow_missing=False):
    code, reply = execute(region, args)
    if allow_missing and missing(reply):
        return None
    if code or reply.get("Status") != "succeeded":
        failure = reply.get("Failure") or {}
        raise RuntimeError(f"agr failed: {failure.get('Code', 'UNKNOWN')}. {failure.get('Hint', '')}")
    return reply.get("Data") or {}


def save(path, state):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        json.dump(state, stream, indent=2)
        stream.write("\n")
    os.replace(stream.name, path)


@contextmanager
def state_file(scenario):
    directory = ROOT / ".state"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / f"{scenario}.json"
    with (directory / f"{scenario}.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f"Another command is using {scenario}; wait for it to finish.") from None
        state = json.loads(path.read_text()) if path.exists() else {}
        yield path, state


def bindings(region, state, path):
    if not state.get("HarnessId"):
        return
    data = call(region, ["harness", "get", state["HarnessId"]], allow_missing=True)
    if data is not None:
        info = data["Harness"].get("ResourceInfo") or {}
        for key in ("ToolId", "DeploymentId"):
            if info.get(key):
                state[key] = info[key]
        save(path, state)


def create(args, path, state):
    region = os.environ.get("AGR_REGION", "")
    if not region:
        raise RuntimeError("Load managed-harness-cookbook/.env before creating resources.")
    if state.get("Cleaned"):
        state.clear()
    if state.get("Region", region) != region:
        raise RuntimeError("This scenario already has resources in another region; clean it up first.")
    prefix, container, field = RESOURCES[args.resource]
    if state.get(field):
        raise RuntimeError(f"{field} is already recorded. Use get to continue, or cleanup before starting again.")
    if state.get("Pending"):
        raise RuntimeError("A create result is unknown. Inspect the recorded name before creating more resources.")
    if any(flag.split("=", 1)[0] in ("--dry-run", "--jq", "-o", "--output", "--region")
           or flag.startswith("-o") and not flag.startswith("--") for flag in args.flags):
        raise RuntimeError("Use agr directly for dry-run; the helper supplies region and JSON output.")
    state["Region"] = region
    name = next((args.flags[index + 1] for index, flag in enumerate(args.flags[:-1]) if flag == "--name"),
                "<inspect agr list>")
    state["Pending"] = {"Resource": args.resource, "Name": name}
    save(path, state)
    print(f"Creating {args.resource} in {region}...", file=sys.stderr)
    code, reply = execute(region, [*prefix, "create", *args.flags])
    data = reply.get("Data") or {}
    resource = data.get(container, {}) if container else data
    resource_id = resource.get(field)
    if args.resource == "harness" and not resource_id:
        resource_id = ((reply.get("Failure") or {}).get("Details") or {}).get("HarnessId")
    if resource_id:
        state[field] = resource_id
        state.pop("Pending", None)
        save(path, state)
        if args.resource == "harness":
            bindings(region, state, path)
    if code or reply.get("Status") != "succeeded":
        failure = reply.get("Failure") or {}
        if failure.get("Kind") == "usage" and not resource_id:
            state.pop("Pending", None)
            save(path, state)
        raise RuntimeError(f"agr create failed: {failure.get('Code', 'UNKNOWN')}. {failure.get('Hint', '')}")
    if not resource_id:
        raise RuntimeError(f"Create returned no {field}; inspect agr {' '.join(prefix)} list before trying again.")
    print(f"Saved {field}: {resource_id} in {path}", file=sys.stderr)
    print(resource_id)


def remove(region, args, get_args):
    if call(region, get_args, allow_missing=True) is None:
        return
    call(region, args, allow_missing=True)
    if call(region, get_args, allow_missing=True) is not None:
        raise RuntimeError("Deletion has not completed; keep the state file and retry cleanup.")


def cleanup(args, path, state):
    if not state:
        print(f"Nothing recorded for {args.scenario}.")
        return
    if not args.yes and not args.dry_run:
        raise RuntimeError("Use cleanup <scenario> --dry-run to inspect, or --yes to delete the recorded resources.")
    region = state["Region"]
    bindings(region, state, path)
    if args.dry_run:
        print(json.dumps(state, indent=2))
        return
    print(f"Cleaning {args.scenario} in {region}.", flush=True)
    if state.get("HarnessId"):
        h = state["HarnessId"]
        remove(region, ["harness", "delete", h, "--yes", "--wait"], ["harness", "get", h])
    if state.get("DeploymentId"):
        d = state["DeploymentId"]
        remove(region, ["deployment", "delete", d, "--wait"], ["deployment", "get", d])
    if state.get("ToolId"):
        tool = state["ToolId"]
        deadline = time.monotonic() + 180
        while True:
            items = call(region, ["instance", "list", "--tool-id", tool, "--all"])["Items"]
            if any(item.get("ToolId") != tool for item in items):
                raise RuntimeError("Instance results do not match the recorded ToolId; cleanup stopped.")
            active = [item for item in items if item["Status"] != "STOPPED"]
            if not active:
                break
            for item in active:
                if item["Status"] == "FAILED" or item["Status"].endswith("_FAILED"):
                    raise RuntimeError(f"Instance {item['InstanceId']} is {item['Status']}; inspect it with agr instance get before retrying cleanup.")
                if item["Status"] in ("RUNNING", "PAUSED"):
                    call(region, ["instance", "delete", item["InstanceId"], "--yes", "--wait"], allow_missing=True)
            if time.monotonic() >= deadline:
                raise RuntimeError("Instances are still changing state; retry cleanup after they settle.")
            time.sleep(3)
        remove(region, ["tool", "delete", tool, "--yes", "--wait"], ["tool", "get", tool])
    if state.get("ModelProviderId"):
        mp = state["ModelProviderId"]
        remove(region, ["model-provider", "delete", mp, "--yes"], ["model-provider", "get", mp])
    if state.get("SpaceId"):
        space = state["SpaceId"]
        if call(region, ["session", "space", "get", "--space-id", space], allow_missing=True) is not None:
            if state.get("HarnessId"):
                deadline = time.monotonic() + 180
                while True:
                    sessions = call(region, ["session", "list", "--space-id", space,
                                             "--user-ids", state["HarnessId"]]).get("Sessions") or []
                    if not sessions:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Sessions are still present; retry cleanup after they settle.")
                    for session in sessions:
                        call(region, ["session", "delete", "--space-id", space, "--user-id",
                                      state["HarnessId"], "--session-id", session["SessionId"]], allow_missing=True)
            remove(region, ["session", "space", "delete", "--space-id", space],
                   ["session", "space", "get", "--space-id", space])
    if state.get("ProviderId"):
        provider = state["ProviderId"]
        if call(region, ["credential", "provider", "get", provider], allow_missing=True) is not None:
            metadata = call(region, ["credential", "secret", "list", "--credential-provider-id", provider,
                                     "--user-ids", "harness-market", "--filter", "scope=github"])
            if "TotalCount" not in metadata:
                raise RuntimeError("Secret metadata is incomplete; keep the provider and retry cleanup.")
            if metadata["TotalCount"]:
                call(region, ["credential", "secret", "delete", "--credential-provider-id", provider,
                              "--user-id", "harness-market", "--scope", "github"], allow_missing=True)
            call(region, ["credential", "provider", "update", provider, "--status", "DISABLED"])
            remove(region, ["credential", "provider", "delete", provider], ["credential", "provider", "get", provider])
    if state.get("Pending"):
        pending = state["Pending"]
        raise RuntimeError(f"Create result unknown for {pending['Resource']} named {pending['Name']}. "
                           "Check agr list/get and clean it up manually before removing the state file.")
    state["Cleaned"] = True
    save(path, state)
    print("Cleanup complete; all recorded resources are absent.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="Example: python3 scripts/resources.py cleanup simple --dry-run")
    sub = parser.add_subparsers(dest="command", required=True)
    examples = {
        "create": "Example: python3 scripts/resources.py create simple model-provider --name my-demo --tokenhub-api-key-id ak-example --model hy3",
        "get": "Example: python3 scripts/resources.py get simple HarnessId",
        "cleanup": "Example: python3 scripts/resources.py cleanup simple --dry-run",
    }
    for command in ("create", "get", "cleanup"):
        child = sub.add_parser(command, epilog=examples[command])
        child.add_argument("scenario", choices=SCENARIOS)
        if command == "create":
            child.add_argument("resource", choices=RESOURCES)
            child.add_argument("flags", nargs=argparse.REMAINDER)
        elif command == "get":
            child.add_argument("field", choices=("HarnessId", "ModelProviderId", "ToolId", "DeploymentId", "SpaceId", "ProviderId"))
        else:
            mode = child.add_mutually_exclusive_group()
            mode.add_argument("--yes", action="store_true")
            mode.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with state_file(args.scenario) as (path, state):
        if args.command == "create":
            create(args, path, state)
        elif args.command == "cleanup":
            cleanup(args, path, state)
        else:
            if args.field in ("ToolId", "DeploymentId") and state.get("HarnessId") and not state.get(args.field) and not state.get("Cleaned"):
                bindings(state["Region"], state, path)
            if state.get("Cleaned") or not state.get(args.field):
                raise RuntimeError(f"No saved {args.field} for {args.scenario}; inspect the state file or create the resource first.")
            print(state[args.field])


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
