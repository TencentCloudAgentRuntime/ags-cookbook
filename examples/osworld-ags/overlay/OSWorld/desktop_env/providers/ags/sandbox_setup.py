"""Helpers for running OSWorld setup operations in an AGS sandbox."""

import requests


def _response_detail(response):
    text = getattr(response, "text", "")
    return text[:500] if text else "empty response"


def execute_shell(exec_url, command, *, label, timeout=120):
    """Run a shell command through OSWorld Server and require a zero exit code."""
    try:
        response = requests.post(
            exec_url,
            json={"command": command, "shell": True},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Sandbox command failed ({label}): {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"Sandbox command failed ({label}): HTTP {response.status_code} "
            f"{_response_detail(response)}"
        )

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Sandbox command failed ({label}): invalid JSON response "
            f"{_response_detail(response)}"
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError(f"Sandbox command failed ({label}): unexpected response {result!r}")

    returncode = result.get("returncode")
    if result.get("status") != "success" or returncode != 0:
        detail = result.get("error") or result.get("message") or result.get("output") or "no details"
        raise RuntimeError(
            f"Sandbox command failed ({label}): returncode={returncode!r}, "
            f"status={result.get('status')!r}, detail={str(detail)[:500]}"
        )

    return result


def upload_file(upload_url, remote_path, filename, content, *, timeout=120):
    """Upload a file through OSWorld Server and require an HTTP success response."""
    try:
        response = requests.post(
            upload_url,
            data={"file_path": remote_path},
            files={"file_data": (filename, content, "application/octet-stream")},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to upload {filename}: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to upload {filename}: HTTP {response.status_code} {_response_detail(response)}"
        )

    return response
