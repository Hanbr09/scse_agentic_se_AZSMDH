from contextlib import ExitStack, redirect_stderr
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import run_smoke_tests as runner
from artifact_io import read_json


@unittest.skipUnless(sys.platform == "win32", "Windows-only process management")
class SmokeRunnerTests(unittest.TestCase):
    def test_opt_in_is_required(self):
        with patch.object(runner, "preflight") as check, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                runner.main([])
            check.assert_not_called()

    def test_existing_service_is_never_stopped(self):
        with patch.object(Path, "is_file", return_value=True), patch.object(runner.importlib.util, "find_spec", return_value=True), \
                patch.object(runner, "running_model_processes", return_value=["ollama.exe"]), \
                patch.object(runner.subprocess, "Popen") as launch, patch.object(runner.subprocess, "run") as stop:
            with self.assertRaisesRegex(RuntimeError, "existing model service"):
                runner.preflight(Path("ollama.exe"))
            launch.assert_not_called()
            stop.assert_not_called()

    def test_low_memory_does_not_start_service(self):
        with patch.object(Path, "is_file", return_value=True), patch.object(runner.importlib.util, "find_spec", return_value=True), \
                patch.object(runner, "running_model_processes", return_value=[]), \
                patch.object(runner, "port_in_use", return_value=False), patch.object(runner, "available_memory", return_value=2), \
                patch.object(runner.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(RuntimeError, "4.5 GiB"):
                runner.preflight(Path("ollama.exe"))
            launch.assert_not_called()

    def test_missing_model_cleans_up_only_owned_process(self):
        server = Mock(pid=12345)
        server.poll.return_value = None

        def api(route, payload=None):
            return {"version": "fixture"} if route == "/api/version" else {"models": []}

        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            stack.enter_context(patch.object(runner, "BASE_DIR", Path(temp)))
            stack.enter_context(patch.object(runner, "preflight", return_value=6))
            stack.enter_context(patch.object(runner, "running_model_processes", return_value=[]))
            stack.enter_context(patch.object(runner, "port_in_use", return_value=False))
            stack.enter_context(patch.object(runner, "local_api", side_effect=api))
            launch = stack.enter_context(patch.object(runner.subprocess, "Popen", return_value=server))
            stop = stack.enter_context(patch.object(runner.subprocess, "run"))
            with self.assertRaisesRegex(RuntimeError, "model is missing"):
                runner.main(["--allow-model"])
            self.assertEqual(stop.call_args.args[0], ["taskkill", "/PID", "12345", "/T", "/F"])
            self.assertEqual(launch.call_args.kwargs["env"]["CUDA_VISIBLE_DEVICES"], "-1")
            report = read_json(Path(temp) / "artifacts/latest_testing_run.json")
            self.assertEqual(report["status"], "failed")
            self.assertTrue(report["cleanup_confirmed"])


if __name__ == "__main__":
    unittest.main()
