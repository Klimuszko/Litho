from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import re
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from .output import parse_openscad_output
from .parser import validate_source_tree


@dataclass
class EngineResult:
    status: str
    exit_code: int | None
    duration: float
    stdout: str
    stderr: str
    command: list[str]
    output_path: Path | None
    metadata: dict
    error_code: str | None = None
    error_message: str | None = None


class ScadEngine:
    def __init__(self, binary: str | None = None):
        self.binary = binary or os.getenv("OPENSCAD_BINARY", "openscad")
        self.timeout_seconds = int(os.getenv("LITHO_SCAD_RENDER_TIMEOUT", "120"))
        self.memory_mb = int(os.getenv("LITHO_SCAD_MEMORY_MB", "2048"))
        self.max_output_bytes = int(os.getenv("LITHO_SCAD_MAX_OUTPUT_BYTES", str(250 * 1024 * 1024)))
        self.max_log_chars = int(os.getenv("LITHO_SCAD_MAX_LOG_CHARS", "200000"))

    def executable(self) -> str | None:
        if Path(self.binary).is_file():
            return str(Path(self.binary).resolve())
        return shutil.which(self.binary)

    def version(self) -> str:
        executable = self.executable()
        if not executable:
            return "unavailable"
        try:
            completed = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5, check=False)
            return (completed.stdout or completed.stderr).strip().splitlines()[0][:120]
        except (OSError, subprocess.SubprocessError):
            return "unknown"

    def status(self) -> dict:
        executable = self.executable()
        version = self.version()
        return {"available": bool(executable), "binary": executable or self.binary, "version": version, "supported": self.version_supported(version)}

    @staticmethod
    def version_supported(version: str) -> bool:
        if version in {"unknown", "unavailable"}:
            return version == "unknown"
        match = re.search(r"(\d{4})\.(\d{2})", version)
        return bool(match and (int(match.group(1)), int(match.group(2))) >= (2021, 1))

    @staticmethod
    def serialize(value, kind: str) -> str:
        if kind == "boolean":
            if not isinstance(value, bool):
                raise ValueError("Oczekiwano wartości true/false")
            return "true" if value else "false"
        if kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("Oczekiwano liczby całkowitej")
            return str(value)
        if kind == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("Oczekiwano liczby")
            return format(float(value), ".15g")
        if kind in {"string", "enum"}:
            if not isinstance(value, str):
                raise ValueError("Oczekiwano tekstu")
            return json.dumps(value, ensure_ascii=False)
        raise ValueError(f"Nieobsługiwany typ parametru: {kind}")

    def validate_parameters(self, definitions: list[dict], supplied: dict) -> dict:
        known = {item["name"]: item for item in definitions}
        unknown = sorted(set(supplied) - set(known))
        if unknown:
            raise ValueError("Nieznane parametry: " + ", ".join(unknown))
        output = {}
        for name, definition in known.items():
            value = supplied.get(name, definition["defaultValue"])
            kind = definition["type"]
            self.serialize(value, kind)
            if kind in {"integer", "float"}:
                numeric = float(value)
                if definition.get("min") is not None and numeric < float(definition["min"]):
                    raise ValueError(f"{name} jest mniejsze niż minimum")
                if definition.get("max") is not None and numeric > float(definition["max"]):
                    raise ValueError(f"{name} jest większe niż maksimum")
                step = definition.get("step")
                if step and definition.get("min") is not None:
                    offset = (numeric - float(definition["min"])) / float(step)
                    if abs(offset - round(offset)) > 1e-7:
                        raise ValueError(f"{name} nie pasuje do kroku {step}")
            if kind == "enum" and value not in definition.get("options", []):
                raise ValueError(f"{name} ma niedozwoloną wartość")
            output[name] = value
        return output

    def command(self, source: Path, output: Path, definitions: list[dict], parameters: dict, mode: str) -> list[str]:
        executable = self.executable()
        if not executable:
            raise FileNotFoundError("OpenSCAD nie jest zainstalowany lub OPENSCAD_BINARY wskazuje nieprawidłową ścieżkę")
        args = [executable, "-o", str(output)]
        effective = dict(parameters)
        if any(item["name"] == "mode" for item in definitions):
            effective["mode"] = mode
        for name in sorted(effective):
            definition = next(item for item in definitions if item["name"] == name)
            args.extend(["-D", f"{name}={self.serialize(effective[name], definition['type'])}"])
        if "mode" not in effective:
            args.extend(["-D", f'mode={json.dumps(mode)}'])
        args.append(str(source))
        return args

    def _limits(self):
        if os.name != "posix":
            return None
        memory = self.memory_mb * 1024 * 1024
        max_output = self.max_output_bytes
        timeout = self.timeout_seconds

        def apply_limits():
            import resource
            os.setsid()
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            resource.setrlimit(resource.RLIMIT_CPU, (timeout + 2, timeout + 5))
            resource.setrlimit(resource.RLIMIT_FSIZE, (max_output, max_output))
            if hasattr(resource, "RLIMIT_NPROC"):
                resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
        return apply_limits

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                if os.name == "posix": os.killpg(process.pid, signal.SIGKILL)
                else: process.kill()
            except OSError:
                pass

    @staticmethod
    def _friendly_error(stderr: str, stdout: str) -> tuple[str, str]:
        text = (stderr + "\n" + stdout).lower()
        if "can't open include file" in text or "can't open library" in text:
            return "MISSING_INCLUDE", "Brakuje biblioteki wymaganej przez moduł."
        if "parser error" in text or "syntax error" in text:
            return "INVALID_SCAD", "Plik SCAD zawiera błąd składni."
        if "assert" in text:
            return "ASSERT_FAILED", "Wybrane parametry tworzą nieprawidłową geometrię."
        return "RENDER_FAILED", "Model nie mógł zostać wygenerowany dla wybranych parametrów."

    def render(self, source_dir: Path, entry_file: str, definitions: list[dict], parameters: dict, output_path: Path, mode: str = "model", cancel: Event | None = None, on_process: Callable[[subprocess.Popen], None] | None = None) -> EngineResult:
        started = time.monotonic()
        cancel = cancel or Event()
        missing = validate_source_tree(source_dir)
        if missing:
            return EngineResult("failed", None, 0, "", "", [], None, {}, "MISSING_INCLUDE", "Brak zależności: " + ", ".join(missing))
        validated = self.validate_parameters(definitions, parameters)
        if not self.executable():
            return EngineResult("failed", None, 0, "", "", [], None, {}, "OPENSCAD_NOT_INSTALLED", "OpenSCAD nie jest zainstalowany lub ścieżka jest nieprawidłowa.")
        version = self.version()
        if not self.version_supported(version):
            return EngineResult("failed", None, 0, "", version, [], None, {}, "OPENSCAD_UNSUPPORTED", "Wymagany jest OpenSCAD 2021.01 lub nowszy.")
        try:
            command = self.command(source_dir / entry_file, output_path, definitions, validated, mode)
        except FileNotFoundError as exc:
            return EngineResult("failed", None, 0, "", str(exc), [], None, {}, "OPENSCAD_NOT_INSTALLED", "OpenSCAD nie jest zainstalowany lub ścieżka jest nieprawidłowa.")
        env = os.environ.copy()
        env.update({"QT_QPA_PLATFORM": "offscreen", "OPENSCADPATH": str(source_dir)})
        try:
            process = subprocess.Popen(
                command, cwd=source_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", shell=False, env=env,
                preexec_fn=self._limits(), creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
        except OSError as exc:
            return EngineResult("failed", None, time.monotonic() - started, "", str(exc), command, None, {}, "ENGINE_START_FAILED", "Nie udało się uruchomić OpenSCAD.")
        if on_process:
            on_process(process)
        status = "running"
        stdout = stderr = ""
        while True:
            if cancel.is_set():
                status = "cancelled"
                self._terminate(process)
                break
            if time.monotonic() - started > self.timeout_seconds:
                status = "timed_out"
                self._terminate(process)
                break
            try:
                stdout, stderr = process.communicate(timeout=.25)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.poll() is None:
            self._terminate(process)
        if not stdout and process.stdout and not process.stdout.closed:
            stdout = process.stdout.read()
        if not stderr and process.stderr and not process.stderr.closed:
            stderr = process.stderr.read()
        stdout, stderr = stdout[-self.max_log_chars:], stderr[-self.max_log_chars:]
        duration = time.monotonic() - started
        metadata = parse_openscad_output(stdout, stderr)
        if status == "cancelled":
            return EngineResult(status, process.returncode, duration, stdout, stderr, command, None, metadata, "RENDER_CANCELLED", "Render anulowany.")
        if status == "timed_out":
            return EngineResult(status, process.returncode, duration, stdout, stderr, command, None, metadata, "RENDER_TIMEOUT", "Przekroczono limit czasu renderowania.")
        if process.returncode != 0:
            code, message = self._friendly_error(stderr, stdout)
            return EngineResult("failed", process.returncode, duration, stdout, stderr, command, None, metadata, code, message)
        if not output_path.is_file():
            return EngineResult("failed", process.returncode, duration, stdout, stderr, command, None, metadata, "OUTPUT_MISSING", "OpenSCAD nie utworzył pliku wynikowego.")
        if mode == "metadata" and output_path.suffix == ".echo":
            echo_output = output_path.read_text(encoding="utf-8", errors="replace")[-self.max_log_chars:]
            stdout = (stdout + "\n" + echo_output)[-self.max_log_chars:]
            metadata = parse_openscad_output(stdout, stderr)
        if output_path.stat().st_size > self.max_output_bytes:
            output_path.unlink(missing_ok=True)
            return EngineResult("failed", process.returncode, duration, stdout, stderr, command, None, metadata, "OUTPUT_TOO_LARGE", "Plik wynikowy przekracza limit rozmiaru.")
        return EngineResult("completed", process.returncode, duration, stdout, stderr, command, output_path, metadata)


scad_engine = ScadEngine()
