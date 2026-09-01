import asyncio
import io
import json
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import httpx2
from mcp_client import AFFINITY_HEADER, AffinityState, fingerprint, text_result


class AffinityStateTests(unittest.TestCase):
    def test_fingerprint_does_not_expose_the_value(self) -> None:
        value = "sensitive-affinity-value"

        result = fingerprint(value)

        self.assertEqual(len(result), 12)
        self.assertNotIn(value, result)

    def test_save_and_load_use_owner_only_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "affinity.json"
            AffinityState(path=path, value="affinity-a").save()

            loaded = AffinityState.load(path, required=True)

            self.assertEqual(loaded.value, "affinity-a")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_request_and_response_hooks_replace_affinity_without_logging_it(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "affinity.json"
            state = AffinityState(path=path, value="affinity-a")
            request = httpx2.Request("POST", "https://example.test/mcp")
            response = httpx2.Response(
                200,
                headers={AFFINITY_HEADER: "affinity-b"},
                request=request,
            )
            output = io.StringIO()

            with redirect_stdout(output):
                asyncio.run(state.on_request(request))
                asyncio.run(state.on_response(response))

            event = json.loads(output.getvalue())
            self.assertEqual(request.headers[AFFINITY_HEADER], "affinity-a")
            self.assertEqual(state.value, "affinity-b")
            self.assertTrue(event["affinity_changed"])
            self.assertNotIn("affinity-a", output.getvalue())
            self.assertNotIn("affinity-b", output.getvalue())
            self.assertEqual(
                AffinityState.load(path, required=True).value, "affinity-b"
            )

    def test_independent_workers_do_not_share_affinity(self) -> None:
        first = AffinityState(value="affinity-a")
        second = AffinityState(value="affinity-b")
        first_request = httpx2.Request("POST", "https://example.test/mcp")
        second_request = httpx2.Request("POST", "https://example.test/mcp")

        asyncio.run(first.on_request(first_request))
        asyncio.run(second.on_request(second_request))

        self.assertEqual(first_request.headers[AFFINITY_HEADER], "affinity-a")
        self.assertEqual(second_request.headers[AFFINITY_HEADER], "affinity-b")

    def test_required_state_must_exist(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "does not exist"),
        ):
            AffinityState.load(Path(directory) / "missing.json", required=True)

    def test_tool_error_is_not_reported_as_success(self) -> None:
        result = SimpleNamespace(
            is_error=True,
            content=[SimpleNamespace(text="operation failed")],
        )

        with self.assertRaisesRegex(RuntimeError, "reported an error"):
            text_result(result)


if __name__ == "__main__":
    unittest.main()
