"""Manage one temporary Ollama server, with resource limits and guaranteed cleanup."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import httpx
import psutil

from artifact_io import write_json
from integration_model import hardware_sample


ROOT = Path(__file__).resolve().parent


def terminate_owned(process):
    if process is None or process.poll() is not None:
        return
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in reversed(children):
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        parent.terminate()
        _, alive = psutil.wait_procs(children + [parent], timeout=8)
        for child in alive:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        process.wait(timeout=10)
    except psutil.NoSuchProcess:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model", action="store_true")
    parser.add_argument("--port", type=int, default=11522)
    parser.add_argument("--backend", choices=("auto", "vulkan"), default="auto")
    parser.add_argument("--vulkan-device", default="1")
    parser.add_argument("--timeout-minutes", type=int, default=40)
    args = parser.parse_args()
    if not args.allow_model:
        parser.error("Use --allow-model to run the real local agents.")
    if not 1024 <= args.port <= 65535:
        parser.error("Use an unprivileged local port.")
    sample = hardware_sample()
    if sample["ram_gib"] < 4.5 or sample["vram_mib"] < 4500 or sample["gpu_c"] >= 75:
        raise RuntimeError(f"Not enough memory or too hot to start: {sample}")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    executable = shutil.which("ollama")
    if executable is None:
        raise RuntimeError("Install Ollama and download qwen2.5:3b before running.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "artifacts/integration_runs" / stamp
    runtime = output / "runtime"
    runtime.mkdir(parents=True)
    environment = dict(os.environ, OLLAMA_HOST=f"127.0.0.1:{args.port}",
                       OLLAMA_NO_CLOUD="1", OLLAMA_NOPRUNE="1", OLLAMA_NUM_PARALLEL="1",
                       OLLAMA_MAX_LOADED_MODELS="1", OLLAMA_CONTEXT_LENGTH="8192",
                       OLLAMA_KEEP_ALIVE="5m", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2",
                       OPENBLAS_NUM_THREADS="2", PYTHONUNBUFFERED="1", PYTHONUTF8="1")
    if args.backend == "vulkan":
        environment.update(OLLAMA_VULKAN="1", OLLAMA_LLM_LIBRARY="vulkan",
                           GGML_VK_VISIBLE_DEVICES=args.vulkan_device, CUDA_VISIBLE_DEVICES="-1")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    server = worker = None
    started = time.monotonic()
    result = {"status": "starting", "backend": args.backend, "port": args.port,
              "hardware_before": sample}
    url = f"http://127.0.0.1:{args.port}"
    try:
        with (runtime / "server.log").open("w", encoding="utf-8") as server_log, \
                (runtime / "worker.log").open("w", encoding="utf-8") as worker_log, \
                (runtime / "hardware.jsonl").open("w", encoding="utf-8") as hardware_log, \
                httpx.Client(base_url=url, trust_env=False, timeout=3) as client:
            server = subprocess.Popen([executable, "serve"], env=environment, cwd=ROOT,
                                      stdout=server_log, stderr=subprocess.STDOUT, creationflags=flags)
            for attempt in range(30):
                if server.poll() is not None:
                    raise RuntimeError("Temporary model service exited during startup.")
                try:
                    response = client.get("/api/version")
                    response.raise_for_status()
                    break
                except httpx.HTTPError:
                    time.sleep(2)
            else:
                raise RuntimeError("Temporary service did not become ready.")
            models = client.get("/api/tags").json()["models"]
            if "qwen2.5:3b" not in {model["name"] for model in models}:
                raise RuntimeError("qwen2.5:3b is not installed. No model was downloaded.")
            command = [sys.executable, "-B", "-u", str(ROOT / "main.py"), "--allow-model",
                       "--base-url", url, "--output", str(output)]
            worker = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=worker_log,
                                      stderr=subprocess.STDOUT, creationflags=flags)
            print(f"Running pipeline; records: {output}", flush=True)
            reported = time.monotonic()
            while worker.poll() is None:
                if server.poll() is not None:
                    raise RuntimeError("Temporary model service exited before the pipeline.")
                sample = hardware_sample()
                import json
                hardware_log.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), **sample}) + "\n")
                hardware_log.flush()
                if sample["ram_gib"] < 1.25 or sample["gpu_c"] >= 80:
                    raise RuntimeError(f"Runtime safety limit reached: {sample}")
                if time.monotonic() - started > args.timeout_minutes * 60:
                    raise TimeoutError("Integration run exceeded its time limit.")
                if time.monotonic() - reported >= 30:
                    print(f"Free RAM {sample['ram_gib']:.2f} GiB; GPU {sample['gpu_c']:.0f} C", flush=True)
                    reported = time.monotonic()
                time.sleep(2)
            result["returncode"] = worker.returncode
            result["status"] = "finished" if worker.returncode == 0 else "failed"
            return worker.returncode
    except Exception as error:
        result["status"], result["error"] = "error", f"{type(error).__name__}: {error}"
        raise
    finally:
        terminate_owned(worker)
        terminate_owned(server)
        result["cleanup"] = {"worker_stopped": worker is None or worker.poll() is not None,
                             "server_stopped": server is None or server.poll() is not None}
        result["elapsed_seconds"] = time.monotonic() - started
        write_json(runtime / "status.json", result)
        print(f"Temporary processes stopped. Records: {output}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
