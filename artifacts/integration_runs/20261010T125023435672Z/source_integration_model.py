"""Configurable local Qwen requests for the integration run."""

from contextlib import contextmanager
from datetime import datetime, timezone
import importlib
from pathlib import Path
import subprocess
import time
from urllib.parse import urlparse

from artifact_io import write_json


def hardware_sample():
    import psutil
    result = subprocess.run(
        ["nvidia-smi", "--id=0", "--query-gpu=temperature.gpu,memory.free",
         "--format=csv,noheader,nounits"], capture_output=True, text=True,
        timeout=10, check=True)
    temperature, free_vram = (float(part.strip()) for part in result.stdout.strip().split(","))
    return {"ram_gib": psutil.virtual_memory().available / 1024 ** 3,
            "gpu_c": temperature, "vram_mib": free_vram}


def wait_until_cool():
    sample = hardware_sample()
    if sample["ram_gib"] < 1.25 or sample["gpu_c"] >= 80:
        raise RuntimeError("Hardware safety limit reached.")
    if sample["gpu_c"] < 72:
        return sample
    deadline = time.monotonic() + 180
    while sample["gpu_c"] > 65:
        if time.monotonic() > deadline:
            raise RuntimeError("GPU did not cool within three minutes.")
        time.sleep(5)
        sample = hardware_sample()
        if sample["ram_gib"] < 1.25 or sample["gpu_c"] >= 80:
            raise RuntimeError("Hardware safety limit reached while cooling.")
    return sample


class LocalModel:
    def __init__(self, base_url="http://127.0.0.1:11522", model="qwen2.5:3b",
                 *, num_gpu=99, guard=True):
        import ollama
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost"):
            raise ValueError("Use a local Ollama service.")
        self.client = ollama.Client(host=base_url, timeout=180, trust_env=False)
        self.model, self.num_gpu, self.guard = model, num_gpu, guard

    def ask(self, system_prompt, text, json_output=False, *, response_schema=None, trace_dir=None):
        if trace_dir is None:
            raise ValueError("A trace directory is required for real integration requests.")
        before = wait_until_cool() if self.guard else None
        request = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt},
                         {"role": "user", "content": text}],
            "format": response_schema if response_schema is not None else ("json" if json_output else None),
            "options": {"temperature": 0, "seed": 48391, "num_gpu": self.num_gpu,
                        "num_thread": 2, "num_ctx": 8192, "num_predict": 2048},
            "keep_alive": "5m", "stream": False,
        }
        started = datetime.now(timezone.utc)
        path = Path(trace_dir) / (started.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        record = {"started_at": started.isoformat(), "request": request, "hardware_before": before}
        try:
            response = self.client.chat(**request)
            record["response"] = response.model_dump(mode="json")
            record["loaded_models"] = self.client.ps().model_dump(mode="json")
            if self.num_gpu != 0:
                loaded = [item for item in record["loaded_models"]["models"] if item["name"] == self.model]
                if (not loaded or not loaded[0].get("size")
                        or loaded[0].get("size_vram", 0) < loaded[0]["size"] * 0.99):
                    raise RuntimeError("Full GPU loading was requested but not confirmed.")
            if response.done is not True or response.done_reason == "length":
                raise ValueError("Model response was incomplete.")
            content = response.message.content
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Model response was empty.")
            if self.guard:
                record["hardware_after"] = wait_until_cool()
            return content
        except Exception as error:
            record["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            record["finished_at"] = datetime.now(timezone.utc).isoformat()
            write_json(path, record)

    @contextmanager
    def bind_original_agents(self):
        # Keep the earlier source files intact; replace their transport only for this run.
        modules = [importlib.import_module(name) for name in
                   ("analyst_agent", "planner_agent", "developer_agent")]
        previous = [module.ask_qwen for module in modules]
        try:
            for module in modules:
                module.ask_qwen = self.ask
            yield
        finally:
            for module, function in zip(modules, previous):
                module.ask_qwen = function

    def close(self):
        self.client.generate(model=self.model, prompt="", keep_alive=0)
