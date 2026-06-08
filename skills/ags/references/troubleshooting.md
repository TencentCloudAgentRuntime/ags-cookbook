# AGR Troubleshooting Reference

Load this file when an `agr` command fails, an Instance is not usable, resource cleanup fails, or docs disagree with the installed CLI.

## Diagnostic Commands

```bash
agr version -o json
agr status -o json
agr doctor -o json
agr schema -o json
agr explain <CODE> -o json
# Per-flag help
agr <command> --<flag> --help
```

Use `agr <path> --help` for exact command syntax. Treat installed CLI help/schema as authoritative for flags.

## JSON Failure Handling

Most JSON commands return an `agr.v1` envelope:

```json
{
  "SchemaVersion": "agr.v1",
  "Command": "tool.list",
  "Status": "failed",
  "Data": null,
  "Failure": {
    "Code": "MISSING_CLOUD_CREDENTIALS",
    "Kind": "auth",
    "Message": "cloud API credentials are required",
    "Hint": "Run: agr init --secret-id <id> --secret-key <key>",
    "Retryable": false
  },
  "Warnings": [],
  "Meta": {}
}
```

Check `.Failure.Code` and `.Failure.Hint` before guessing. Server-side errors now also include `RequestId` for support tickets.

## Common Issues

| Symptom | Checks |
| --- | --- |
| Missing credentials | `agr status -o json`, then configure `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY` with `agr init`. |
| Auth failure | `agr doctor -o json`, `agr explain AUTH_FAILED -o json`, verify CAM permissions, region, and STS token expiry. |
| Unknown command or flag | `agr version -o json`, `agr <command> --help`, `agr schema -o json`. Use `--<flag> --help` for per-flag details. |
| `--jq` does not work | Ensure the command also has `-o json`. |
| Streaming command fails with JSON | Use `--stream -o ndjson` or plain text, not `--stream -o json`. |
| Instance not ready | `agr instance get <id> -o json`; wait for `RUNNING`. |
| Tool delete fails | Delete active Instances created from the Tool first. |
| Network issue | Check `NetworkConfiguration`, `--region`, `--domain`, `--cloud-endpoint`, proxy, and VPC fields. |
| Mount issue | Check `StorageMounts`, `MountOptions`, RoleArn, path rules, COS bucket APPID suffix, CFS region/mount availability. |
| `instance debug` flag error | JSON flags (`--mount-options`, `--metadata`, `--custom-configuration`) support `@file` and `-` (stdin). Invalid JSON now shows `INVALID_JSON_FLAG` with a clear hint. |
| `instance login` shows a generic error | Upgrade to the latest `agr` — recent versions report the specific PTY/envd failure instead of a generic error. |

## Instance Status Values

Instance responses may include these status values. Some command help text may list only a subset of status filter values; check `agr instance list --help` / `agr schema -o json` before using status filters in automation.

| Status | Meaning |
| --- | --- |
| `STARTING` | Creation accepted, not yet ready. |
| `RUNNING` | Stable and usable. |
| `FAILED` | Terminal failed state; inspect returned failure details. |
| `STOPPING` / `STOPPED` | Ending / ended. Cannot continue the same session after stopped. |
| `STARTING_FAILED` | Creation failed before the Instance became usable. |
| `STOPPING_FAILED` | Stop failed; inspect returned failure details and retry cleanup if appropriate. |
| `PAUSED` | Paused and not currently usable for normal work; resume before operations that require a running instance. |
| `PAUSE_FAILED` | Pause operation failed; inspect returned failure details. |
| `RESUME_FAILED` | Resume operation failed; inspect returned failure details. |

Only `RUNNING` is safe for code, shell, file, browser/mobile, or port operations.

## Exit Codes

| Exit Code | Type | Description |
| ---: | --- | --- |
| 0 | `success` | Command succeeded. |
| 1 | `error` | Non-usage, non-auth CLI or API failure; check `Failure.Kind`. |
| 2 | `usage` | Invalid arguments, flags, input, or unsupported output mode. |
| 4 | `auth` | Missing credentials, auth failure, or insufficient permissions. |
| 255 | `remote_execution_failed` | Remote code execution failed. |

`instance exec` and `instance mobile adb` may also pass through downstream process exit codes (0–255).

Full list: `agr schema -o json --jq '.Data.ExitCodes'`.

## Cleanup

```bash
agr instance list --tool-id "$tool_id" -o json
agr instance list --all -o json          # All instances, paginated, with region info
agr instance delete "$instance_id" --ignore-not-found -o json
agr tool delete "$tool_id" -o json
```

If `tool delete` fails with a resource-in-use style error, list and delete related Instances first.

Deleting AGS resources does not delete external COS objects, CFS filesystems, or registry images.

## CLI Drift Rules

If cookbook docs and the installed `agr` disagree:

1. Use installed `agr --help` / `agr schema -o json` for command names and flags.
2. Use product docs for concept meaning and service constraints.
3. Mention the discrepancy in the user response if it affects reliability.
4. Prefer conservative commands that avoid creating/deleting resources until confirmed.
