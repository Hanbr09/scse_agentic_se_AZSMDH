"""Run the requested real-agent tests using an owned, CPU-only Ollama service."""

import argparse
import csv
import ctypes
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener

from analyst_agent import MODEL
from artifact_io import write_json, write_text


BASE_DIR = Path(__file__).resolve().parent


def available_memory():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
                    ("page_total", ctypes.c_ulonglong), ("page_available", ctypes.c_ulonglong),
                    ("virtual_total", ctypes.c_ulonglong), ("virtual_available", ctypes.c_ulonglong),
                    ("extended", ctypes.c_ulonglong)]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise RuntimeError("Available memory could not be checked.")
    return status.available / 1024 ** 3


def running_model_processes():
    listing = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], check=True, capture_output=True,
                             text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return [row[0] for row in csv.reader(io.StringIO(listing.stdout))
            if row and ("ollama" in row[0].lower() or "llama" in row[0].lower())]


def port_in_use():
    with socket.socket() as client:
        client.settimeout(1)
        return client.connect_ex(("127.0.0.1", 11434)) == 0


def local_api(route, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request("http://127.0.0.1:11434" + route, data=body,
                      headers={"Content-Type": "application/json"})
    with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
        return json.load(response)


def require_unloaded():
    until = time.monotonic() + 15
    while local_api("/api/ps").get("models"):
        if time.monotonic() >= until:
            raise RuntimeError("A model is still loaded. No further stage will run.")
        time.sleep(0.5)


def preflight(executable):
    if sys.platform != "win32":
        raise RuntimeError("This owned-service helper is Windows-only; offline tests are portable.")
    if not executable.is_file():
        raise RuntimeError("Ollama is not installed. No software or model will be downloaded.")
    if importlib.util.find_spec("ollama") is None:
        raise RuntimeError("Use the project's Python environment after installing requirements.txt.")
    if running_model_processes() or port_in_use():
        raise RuntimeError("An existing model service is present. It has not been changed or stopped.")
    free = available_memory()
    if free < 4.5:
        raise RuntimeError(f"Only {free:.2f} GiB is available; 4.5 GiB is required before startup.")
    return free


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model", action="store_true")
    parser.add_argument("--only", choices=("all", "analyst", "planner", "developer"), default="all")
    parser.add_argument("--ollama", type=Path,
                        default=Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe")
    args = parser.parse_args(argv)
    if not args.allow_model:
        parser.error("No model was started. Supply --allow-model for real inference.")
    free = preflight(args.ollama)
    stages = ("analyst", "planner", "developer") if args.only == "all" else (args.only,)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = BASE_DIR / "artifacts" / "testing_runs" / stamp
    folder.mkdir(parents=True)
    summary = {"started_utc": datetime.now(timezone.utc).isoformat(), "status": "failed",
               "model": MODEL, "free_memory_gib": round(free, 2), "threads": 2, "gpu_layers": 0,
               "requested_stages": list(stages), "completed_stages": [], "automatic_retries": 0,
               "scripts": {}, "output_logs": {}}
    environment = dict(os.environ, CUDA_VISIBLE_DEVICES="-1", GGML_VK_VISIBLE_DEVICES="-1",
                       OLLAMA_VULKAN="0", OLLAMA_HOST="127.0.0.1:11434", OLLAMA_CONTEXT_LENGTH="2048",
                       OLLAMA_NUM_PARALLEL="1", OLLAMA_MAX_LOADED_MODELS="1", OLLAMA_KEEP_ALIVE="0",
                       OLLAMA_NO_CLOUD="1", OLLAMA_NOPRUNE="1", OLLAMA_MODEL=MODEL,
                       NO_PROXY="localhost,127.0.0.1", PYTHONIOENCODING="utf-8")
    server = None
    with (folder / "server.log").open("wb") as server_log:
        try:
            server = subprocess.Popen([str(args.ollama), "serve"], env=environment,
                                      stdout=server_log, stderr=subprocess.STDOUT,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 25
            while True:
                if server.poll() is not None:
                    raise RuntimeError("The owned server exited during startup.")
                try:
                    summary["ollama_version"] = local_api("/api/version")["version"]
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Local server startup timed out.")
                    time.sleep(0.5)
            installed = next((item for item in local_api("/api/tags")["models"] if item["name"] == MODEL), None)
            if installed is None:
                raise RuntimeError("The required local model is missing. No download was attempted.")
            summary["installed_model"] = {key: installed[key] for key in ("name", "digest", "size")}
            for stage in stages:
                require_unloaded()
                if available_memory() < 3:
                    raise RuntimeError("Less than 3 GiB is available before a model request.")
                script = "test_" + stage + ".py"
                summary["scripts"][stage] = script
                print(f"Running {script}: one CPU-only request, two threads.", flush=True)
                result = subprocess.run([sys.executable, "-B", str(BASE_DIR / script), "--allow-model"],
                                        cwd=BASE_DIR, env=environment, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=150,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                log_path = folder / (stage + ".log")
                write_text(log_path, result.stdout + result.stderr)
                summary["output_logs"][stage] = log_path.relative_to(BASE_DIR).as_posix()
                print(result.stdout + result.stderr, end="", flush=True)
                result.check_returncode()
                require_unloaded()
                summary["completed_stages"].append(stage)
            if "developer" in stages:
                from verify_pipeline import verify
                summary["checked_sensor_states"] = verify()["scenario_count"]
            summary["status"] = "passed"
        except BaseException as error:
            summary["failure"] = type(error).__name__ + ": " + str(error)
            raise
        finally:
            try:
                if server is not None and server.poll() is None:
                    try:
                        local_api("/api/generate", {"model": MODEL, "keep_alive": 0})
                    except (OSError, ValueError):
                        pass
                    # Stop only the process tree identified by our live Popen handle.
                    if server.poll() is None:
                        subprocess.run(["taskkill", "/PID", str(server.pid), "/T", "/F"], check=True,
                                       capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                        server.wait(timeout=10)
            except (OSError, subprocess.SubprocessError) as error:
                summary["cleanup_error"] = str(error)
            summary["remaining_model_processes"] = running_model_processes()
            summary["port_still_listening"] = port_in_use()
            summary["cleanup_confirmed"] = not summary["remaining_model_processes"] and not summary["port_still_listening"]
            summary["finished_utc"] = datetime.now(timezone.utc).isoformat()
            write_json(folder / "session.json", summary)
            write_json(BASE_DIR / "artifacts" / "latest_testing_run.json", summary)
    if not summary["cleanup_confirmed"]:
        raise RuntimeError("Service cleanup could not be confirmed; do not launch another run.")
    print("Real-agent tests finished; the owned model service is closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
