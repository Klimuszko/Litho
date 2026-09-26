from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, RLock

from .engine import ScadEngine, scad_engine
from .repository import ScadRepository, json_dump, scad_repository, utc_now


class ScadRenderService:
    def __init__(self, repository: ScadRepository = scad_repository, engine: ScadEngine = scad_engine):
        self.repository = repository
        self.engine = engine
        self.executor = ThreadPoolExecutor(max_workers=int(os.getenv("LITHO_SCAD_MAX_CONCURRENT_RENDERS", "2")), thread_name_prefix="scad-render")
        self._cancel: dict[str, Event] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = RLock()

    @staticmethod
    def _parameters_hash(parameters: dict) -> str:
        return hashlib.sha256(json_dump(parameters).encode()).hexdigest()

    @staticmethod
    def _cache_key(version: dict, parameters_hash: str, engine_version: str, output_format: str, mode: str) -> str:
        raw = "\0".join((version["module_id"], version["id"], version["source_hash"], parameters_hash, engine_version, output_format, mode))
        return hashlib.sha256(raw.encode()).hexdigest()

    def create(self, user: dict, module: dict, version: dict, parameters: dict, output_format: str, mode: str) -> dict:
        self.repository.initialize()
        validated = self.engine.validate_parameters(version["parameters"], parameters)
        engine_version = self.engine.version()
        parameters_hash = self._parameters_hash(validated)
        cache_key = self._cache_key(version, parameters_hash, engine_version, output_format, mode)
        job_id = str(uuid.uuid4())
        now = utc_now()
        with self.repository._lock, self.repository._connect() as connection:
            per_user_limit = int(os.getenv("LITHO_SCAD_MAX_CONCURRENT_PER_USER", "1"))
            active = int(connection.execute("SELECT COUNT(*) FROM scad_render_jobs WHERE user_id=? AND status IN ('queued','running')", (user["id"],)).fetchone()[0])
            if active >= per_user_limit:
                raise ValueError(f"Masz już {active} aktywnych renderów; limit wynosi {per_user_limit}")
            cached = connection.execute(
                "SELECT output_path,output_size,metadata_json FROM scad_render_jobs WHERE cache_key=? AND status='completed' AND output_path IS NOT NULL ORDER BY finished_at DESC LIMIT 1",
                (cache_key,),
            ).fetchone()
            cached_path = Path(cached["output_path"]) if cached else None
            if cached_path and cached_path.is_file():
                connection.execute(
                    "INSERT INTO scad_render_jobs(id,user_id,module_id,version_id,parameters_json,parameters_hash,source_hash,openscad_version,output_format,mode,cache_key,status,created_at,started_at,finished_at,duration_seconds,output_path,output_size,metadata_json,cached) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                    (job_id, user["id"], module["id"], version["id"], json_dump(validated), parameters_hash, version["source_hash"], engine_version, output_format, mode, cache_key, "completed", now, now, now, 0.0, str(cached_path), cached["output_size"], cached["metadata_json"]),
                )
                return self.get(job_id)
            connection.execute(
                "INSERT INTO scad_render_jobs(id,user_id,module_id,version_id,parameters_json,parameters_hash,source_hash,openscad_version,output_format,mode,cache_key,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, user["id"], module["id"], version["id"], json_dump(validated), parameters_hash, version["source_hash"], engine_version, output_format, mode, cache_key, "queued", now),
            )
        cancel = Event()
        with self._lock:
            self._cancel[job_id] = cancel
        self.executor.submit(self._run, job_id, version, validated, output_format, mode, cache_key, cancel)
        return self.get(job_id)

    def _run(self, job_id: str, version: dict, parameters: dict, output_format: str, mode: str, cache_key: str, cancel: Event) -> None:
        work = self.repository.storage / "tmp" / f"render-{job_id}"
        source = work / "module"
        output = work / ("metadata.echo" if mode == "metadata" else f"output.{output_format}")
        work.mkdir(parents=True, exist_ok=False)
        shutil.copytree(version["storage_path"], source)
        if cancel.is_set():
            with self.repository._connect() as connection:
                connection.execute("UPDATE scad_render_jobs SET status='cancelled',finished_at=?,error_code='RENDER_CANCELLED',error_message='Render anulowany.' WHERE id=?", (utc_now(), job_id))
            shutil.rmtree(work, ignore_errors=True)
            with self._lock: self._cancel.pop(job_id, None)
            return
        with self.repository._connect() as connection:
            connection.execute("UPDATE scad_render_jobs SET status='running',started_at=? WHERE id=?", (utc_now(), job_id))
        def track(process: subprocess.Popen):
            with self._lock: self._processes[job_id] = process
        try:
            result = self.engine.render(source, version["entry_file"], version["parameters"], parameters, output, mode, cancel, track)
            final_path = None
            size = None
            if result.status == "completed" and result.output_path:
                final_path = self.repository.storage / "cache" / f"{cache_key}.{'echo' if mode == 'metadata' else output_format}"
                if not final_path.exists():
                    shutil.move(result.output_path, final_path)
                size = final_path.stat().st_size
            with self.repository._connect() as connection:
                connection.execute(
                    "UPDATE scad_render_jobs SET status=?,finished_at=?,duration_seconds=?,output_path=?,output_size=?,stdout=?,stderr=?,command_json=?,metadata_json=?,error_code=?,error_message=? WHERE id=?",
                    (result.status, utc_now(), result.duration, str(final_path) if final_path else None, size, result.stdout, result.stderr, json_dump(result.command), json_dump(result.metadata), result.error_code, result.error_message, job_id),
                )
        except Exception as exc:
            with self.repository._connect() as connection:
                connection.execute("UPDATE scad_render_jobs SET status='failed',finished_at=?,error_code='WORKER_ERROR',error_message=? WHERE id=?", (utc_now(), str(exc)[:1000], job_id))
        finally:
            shutil.rmtree(work, ignore_errors=True)
            with self._lock:
                self._cancel.pop(job_id, None)
                self._processes.pop(job_id, None)

    def get(self, job_id: str) -> dict:
        self.repository.initialize()
        with self.repository._connect() as connection:
            row = connection.execute("SELECT * FROM scad_render_jobs WHERE id=?", (job_id,)).fetchone()
            if not row: raise KeyError(job_id)
            return self.repository._decode(row) or {}

    def list(self, user: dict, limit: int = 50) -> list[dict]:
        self.repository.initialize()
        with self.repository._connect() as connection:
            if user.get("role") == "admin":
                rows = connection.execute("SELECT * FROM scad_render_jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = connection.execute("SELECT * FROM scad_render_jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user["id"], limit)).fetchall()
            return [self.repository._decode(row) or {} for row in rows]

    def cancel(self, job_id: str) -> dict:
        job = self.get(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        with self._lock:
            event = self._cancel.get(job_id)
            if event: event.set()
            process = self._processes.get(job_id)
        if process:
            self.engine._terminate(process)
        return self.get(job_id)


scad_render_service = ScadRenderService()
