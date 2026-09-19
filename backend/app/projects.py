import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import BaseModel, Field

from .models import Crop, LithophaneParams


PROJECT_ID_PATTERN = re.compile(r"^LTH-[0-9]{8}-[A-F0-9]{8}$")
PROJECTS_DIR = Path(os.getenv("LITHO_PROJECTS_DIR", "/data/projects"))
_write_lock = RLock()


class CustomerProjectConfig(BaseModel):
    size: Literal["100x150", "130x180", "150x200"] = "100x150"
    orientation: Literal["landscape", "portrait"] = "landscape"
    housing_type: Literal["frame", "box"] = "frame"
    housing_color: str = Field("black-matte", min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    power_source: Literal["wired", "battery"] = "wired"
    light_temperature: Literal["warm", "neutral", "cool"] = "warm"
    crop: Crop = Field(default_factory=Crop)
    rotation_degrees: float = Field(0, ge=-360, le=360)
    brightness: float = Field(1, ge=0.25, le=2)
    contrast: float = Field(1.25, ge=0.25, le=3)
    gamma: float = Field(1, ge=0.1, le=5)

    @property
    def dimensions_mm(self) -> tuple[float, float]:
        short, long = (int(value) for value in self.size.split("x"))
        return (long, short) if self.orientation == "landscape" else (short, long)

    def lithophane_params(self) -> LithophaneParams:
        width, height = self.dimensions_mm
        return LithophaneParams(
            width_mm=width,
            height_mm=height,
            orientation=self.orientation,
            min_thickness_mm=0.6,
            max_thickness_mm=4.0,
            gamma=self.gamma,
            brightness=self.brightness,
            contrast=self.contrast,
            nozzle_diameter_mm=0.4,
            quality_profile="maximum",
            mounting_flange=True,
            removable_support=False,
            invert=False,
            mirror=False,
            rotation_degrees=self.rotation_degrees,
            crop=self.crop,
        )


class OrderReference(BaseModel):
    order_id: str = Field(min_length=1, max_length=100)


class ProjectStore:
    def __init__(self, root: Path = PROJECTS_DIR):
        self.root = root

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _directory(self, project_id: str) -> Path:
        if not PROJECT_ID_PATTERN.fullmatch(project_id):
            raise FileNotFoundError(project_id)
        root = self.root.resolve()
        candidate = (root / project_id).resolve()
        if not candidate.is_relative_to(root):
            raise FileNotFoundError(project_id)
        return candidate

    def create(self, config: CustomerProjectConfig) -> tuple[dict, str]:
        self.root.mkdir(parents=True, exist_ok=True)
        while True:
            project_id = f"LTH-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(4).upper()}"
            directory = self._directory(project_id)
            try:
                directory.mkdir(parents=False)
                break
            except FileExistsError:
                continue
        token = secrets.token_urlsafe(32)
        now = self._now()
        metadata = {
            "project_id": project_id,
            "status": "awaiting_image",
            "created_at": now,
            "updated_at": now,
            "config": config.model_dump(mode="json"),
            "image": None,
            "artifacts": {},
            "generation_error": None,
            "generation_id": None,
            "housing_generation": "pending_component_specification",
            "customer_ref": None,
            "token_hash": self._token_hash(token),
        }
        self.save(metadata)
        return metadata, token

    def load(self, project_id: str) -> dict:
        path = self._directory(project_id) / "project.json"
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, metadata: dict) -> None:
        directory = self._directory(metadata["project_id"])
        directory.mkdir(parents=True, exist_ok=True)
        metadata["updated_at"] = self._now()
        target = directory / "project.json"
        temporary = directory / f".project-{secrets.token_hex(4)}.tmp"
        with _write_lock:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(metadata, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)

    def authorize(self, metadata: dict, token: str | None) -> bool:
        return bool(token) and secrets.compare_digest(metadata["token_hash"], self._token_hash(token))

    def begin_generation(self, project_id: str, generation_id: str) -> dict:
        with _write_lock:
            metadata = self.load(project_id)
            if metadata["status"] == "generating":
                raise RuntimeError("already_generating")
            if not metadata.get("image"):
                raise RuntimeError("image_required")
            metadata["status"] = "generating"
            metadata["generation_id"] = generation_id
            metadata["generation_error"] = None
            self.save(metadata)
            return metadata

    def replace_config(self, project_id: str, config: CustomerProjectConfig) -> dict:
        with _write_lock:
            metadata = self.load(project_id)
            if metadata["status"] == "generating":
                raise RuntimeError("generating")
            metadata["config"] = config.model_dump(mode="json")
            metadata["artifacts"] = {}
            metadata["generation_error"] = None
            metadata["generation_id"] = None
            metadata["status"] = "ready" if metadata.get("image") else "awaiting_image"
            self.save(metadata)
            return metadata

    def replace_image(self, project_id: str, filename: str, raw: bytes, image_metadata: dict) -> dict:
        with _write_lock:
            metadata = self.load(project_id)
            if metadata["status"] == "generating":
                raise RuntimeError("generating")
            previous_filename = metadata.get("image", {}).get("filename") if metadata.get("image") else None
            target = self.path(project_id, filename)
            temporary = self.path(project_id, f".{filename}.tmp")
            temporary.write_bytes(raw)
            os.replace(temporary, target)
            metadata["image"] = image_metadata
            metadata["artifacts"] = {}
            metadata["generation_error"] = None
            metadata["generation_id"] = None
            metadata["status"] = "ready"
            self.save(metadata)
            if previous_filename and previous_filename != filename:
                self.path(project_id, previous_filename).unlink(missing_ok=True)
            return metadata

    def finish_generation(self, project_id: str, generation_id: str, payload: bytes, artifact: dict) -> bool:
        with _write_lock:
            metadata = self.load(project_id)
            if metadata.get("generation_id") != generation_id or metadata["status"] != "generating":
                return False
            filename = artifact["filename"]
            target = self.path(project_id, filename)
            temporary = self.path(project_id, f".{filename}.tmp")
            temporary.write_bytes(payload)
            os.replace(temporary, target)
            metadata["artifacts"] = {"lithophane_stl": artifact}
            metadata["status"] = "completed"
            metadata["generation_id"] = None
            self.save(metadata)
            return True

    def fail_generation(self, project_id: str, generation_id: str) -> None:
        with _write_lock:
            metadata = self.load(project_id)
            if metadata.get("generation_id") != generation_id or metadata["status"] != "generating":
                return
            metadata["status"] = "failed"
            metadata["generation_id"] = None
            metadata["generation_error"] = "Generowanie modelu nie powiodło się."
            self.save(metadata)

    def attach_order(self, project_id: str, order_id: str) -> dict:
        with _write_lock:
            metadata = self.load(project_id)
            metadata["customer_ref"] = order_id
            self.save(metadata)
            return metadata

    def public(self, metadata: dict) -> dict:
        return {key: value for key, value in metadata.items() if key != "token_hash"}

    def path(self, project_id: str, filename: str) -> Path:
        if Path(filename).name != filename:
            raise FileNotFoundError(filename)
        directory = self._directory(project_id)
        candidate = (directory / filename).resolve()
        if not candidate.is_relative_to(directory):
            raise FileNotFoundError(filename)
        return candidate

    def delete(self, project_id: str) -> None:
        import shutil

        with _write_lock:
            directory = self._directory(project_id)
            if not directory.is_dir():
                raise FileNotFoundError(project_id)
            shutil.rmtree(directory)

    def list(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        projects = []
        for directory in self.root.iterdir():
            if not directory.is_dir() or not PROJECT_ID_PATTERN.fullmatch(directory.name):
                continue
            try:
                projects.append(self.public(self.load(directory.name)))
            except (OSError, ValueError, KeyError):
                continue
        return sorted(projects, key=lambda project: project["created_at"], reverse=True)


project_store = ProjectStore()
