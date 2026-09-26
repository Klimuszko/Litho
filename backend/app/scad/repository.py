from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import uuid
import io
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from PIL import Image, UnidentifiedImageError

from .models import ModuleCreate, ModuleUpdate, PresetCreate
from .parser import ScadParser, validate_source_tree
from .permissions import module_permissions


DEFAULT_CATEGORIES = ["Fidgets", "Lithophane", "Storage", "Home", "Games", "Electronics", "Tools", "Plants", "Other"]
CATEGORIES = [item.strip() for item in os.getenv("LITHO_SCAD_CATEGORIES", ",".join(DEFAULT_CATEGORIES)).split(",") if item.strip()]
MAX_SOURCE_BYTES = int(os.getenv("LITHO_SCAD_MAX_SOURCE_BYTES", str(10 * 1024 * 1024)))
MAX_FILES = int(os.getenv("LITHO_SCAD_MAX_FILES", "200"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:80] or "module"


def json_dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class ScadRepository:
    def __init__(self, database: Path | None = None, storage: Path | None = None):
        self.database = database or Path(os.getenv("LITHO_AUTH_DB", "/data/auth.sqlite3"))
        self.storage = storage or Path(os.getenv("LITHO_SCAD_STORAGE", "/data/scad"))
        self._initialized_for: tuple[Path, Path] | None = None
        self._lock = RLock()
        self.parser = ScadParser()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        key = (self.database.resolve(), self.storage.resolve())
        if self._initialized_for == key and self.database.exists():
            return
        with self._lock:
            self.database.parent.mkdir(parents=True, exist_ok=True)
            self.storage.mkdir(parents=True, exist_ok=True)
            migration = Path(__file__).with_name("migrations") / "001_scad_platform.sql"
            with self._connect() as connection:
                connection.executescript(migration.read_text(encoding="utf-8"))
                now = utc_now()
                connection.execute(
                    "UPDATE scad_render_jobs SET status='failed', finished_at=?, error_code='WORKER_RESTARTED', error_message='Render przerwany przez restart serwera' WHERE status IN ('queued','running')",
                    (now,),
                )
            for folder in ("modules", "renders", "cache", "tmp"):
                (self.storage / folder).mkdir(exist_ok=True)
            self._initialized_for = key

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        item = dict(row)
        for key in ("official", "cached"):
            if key in item:
                item[key] = bool(item[key])
        for key in ("manifest_json", "parameters_json", "parser_warnings_json", "metadata_json", "command_json"):
            if key in item:
                target = key.removesuffix("_json")
                try:
                    item[target] = json.loads(item.pop(key) or ("[]" if key in {"parameters_json", "parser_warnings_json", "command_json"} else "{}"))
                except json.JSONDecodeError:
                    item[target] = [] if key in {"parameters_json", "parser_warnings_json", "command_json"} else {}
        return item

    def _decode_version(self, row: sqlite3.Row | None) -> dict | None:
        item = self._decode(row)
        if not item:
            return item
        root = Path(item["storage_path"])
        item["source_files"] = [
            {"path": path.relative_to(root).as_posix(), "size": path.stat().st_size}
            for path in sorted(root.rglob("*")) if path.is_file()
        ] if root.is_dir() else []
        return item

    def _module_query(self, connection: sqlite3.Connection, module_id: str) -> dict:
        row = connection.execute(
            "SELECT m.*, u.username owner_username, u.display_name owner_display_name FROM scad_modules m JOIN users u ON u.id=m.owner_user_id WHERE m.id=?",
            (module_id,),
        ).fetchone()
        if not row:
            raise KeyError(module_id)
        return self._decode(row) or {}

    def get_module(self, module_id: str) -> dict:
        self.initialize()
        with self._connect() as connection:
            return self._module_query(connection, module_id)

    def with_share(self, module: dict, user_id: int) -> dict:
        with self._connect() as connection:
            shared = connection.execute("SELECT 1 FROM scad_module_shares WHERE module_id=? AND user_id=?", (module["id"], user_id)).fetchone()
        module["shared_with_user"] = bool(shared)
        return module

    def version(self, version_id: str) -> dict:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM scad_module_versions WHERE id=?", (version_id,)).fetchone()
            if not row:
                raise KeyError(version_id)
            return self._decode_version(row) or {}

    def versions(self, module_id: str) -> list[dict]:
        self.initialize()
        with self._connect() as connection:
            return [self._decode_version(row) or {} for row in connection.execute(
                "SELECT * FROM scad_module_versions WHERE module_id=? ORDER BY version_number DESC", (module_id,)
            )]

    def list_modules(self, user: dict, scope: str, search: str = "", category: str = "", author: str = "", sort: str = "updated") -> list[dict]:
        self.initialize()
        order = {"updated": "m.updated_at DESC", "newest": "m.created_at DESC", "name": "m.name COLLATE NOCASE"}.get(sort, "m.updated_at DESC")
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT m.*, u.username owner_username, u.display_name owner_display_name, EXISTS(SELECT 1 FROM scad_module_shares s WHERE s.module_id=m.id AND s.user_id=?) shared_with_user FROM scad_modules m JOIN users u ON u.id=m.owner_user_id ORDER BY {order}",
                (user["id"],),
            ).fetchall()
        output = []
        for row in rows:
            module = self._decode(row) or {}
            if scope == "my" and module["owner_user_id"] != user["id"]:
                continue
            if scope == "official" and not module["official"]:
                continue
            if scope == "public" and not (
                module["visibility"] in {"public", "system"} and module["status"] == "published"
            ):
                continue
            if scope == "shared" and not module.get("shared_with_user"):
                continue
            if scope == "all" and user.get("role") != "admin":
                continue
            if scope != "all" and not module_permissions.can("read", user, module):
                continue
            haystack = f"{module['name']} {module['description']} {module['owner_username']}".lower()
            if search and search.lower() not in haystack:
                continue
            if category and module["category"].lower() != category.lower():
                continue
            if author and author.lower() not in f"{module['owner_username']} {module['owner_display_name']}".lower():
                continue
            output.append(module)
        return output

    def _unique_slug(self, connection: sqlite3.Connection, name: str) -> str:
        base = slugify(name)
        slug = base
        suffix = 2
        while connection.execute("SELECT 1 FROM scad_modules WHERE slug=?", (slug,)).fetchone():
            slug = f"{base}-{suffix}"
            suffix += 1
        return slug

    @staticmethod
    def _safe_extract(payload: bytes, target: Path) -> None:
        try:
            with ZipFile(io.BytesIO(payload)) as archive:
                members = [item for item in archive.infolist() if not item.is_dir()]
                if len(members) > MAX_FILES or sum(item.file_size for item in members) > MAX_SOURCE_BYTES:
                    raise ValueError("Archiwum modułu przekracza dozwolony limit")
                for item in members:
                    destination = (target / item.filename).resolve()
                    try:
                        destination.relative_to(target.resolve())
                    except ValueError as exc:
                        raise ValueError("Archiwum zawiera niedozwoloną ścieżkę") from exc
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as source, destination.open("wb") as output:
                        shutil.copyfileobj(source, output)
        except BadZipFile as exc:
            raise ValueError("Nieprawidłowe archiwum ZIP") from exc

    @staticmethod
    def _flatten_single_directory(root: Path) -> None:
        entries = list(root.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            nested = entries[0]
            for child in list(nested.iterdir()):
                shutil.move(str(child), root / child.name)
            nested.rmdir()

    def _prepare_payload(self, payload: bytes, filename: str, target: Path) -> tuple[str, dict]:
        if len(payload) > MAX_SOURCE_BYTES:
            raise ValueError("Źródła modułu przekraczają dozwolony limit")
        target.mkdir(parents=True, exist_ok=False)
        if filename.lower().endswith(".zip"):
            self._safe_extract(payload, target)
            self._flatten_single_directory(target)
        elif filename.lower().endswith(".scad"):
            (target / "main.scad").write_bytes(payload)
        else:
            raise ValueError("Wybierz plik .scad lub archiwum .zip")

        manifest_path = target / "module.json"
        manifest = {}
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError("module.json nie jest poprawnym plikiem JSON") from exc
        entry = str(manifest.get("entry", "main.scad"))
        entry_path = (target / entry).resolve()
        try:
            entry_path.relative_to(target.resolve())
        except ValueError as exc:
            raise ValueError("Plik wejściowy wychodzi poza katalog modułu") from exc
        if not entry_path.is_file():
            candidates = sorted(target.rglob("*.scad"))
            if len(candidates) == 1:
                entry_path = candidates[0]
                entry = entry_path.relative_to(target).as_posix()
            else:
                raise ValueError("Nie znaleziono pliku wejściowego main.scad")
        missing = validate_source_tree(target)
        if missing:
            raise ValueError("Brak lokalnych zależności: " + ", ".join(missing))
        return entry, manifest

    @staticmethod
    def _tree_hash(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def _audit(self, connection: sqlite3.Connection, actor: int, module_id: str, action: str, version_id: str | None = None, old=None, new=None, metadata=None) -> None:
        connection.execute(
            "INSERT INTO scad_module_audit_logs(id,actor_user_id,target_module_id,target_version_id,action,timestamp,old_value_json,new_value_json,metadata_json) VALUES(?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), actor, module_id, version_id, action, utc_now(), json_dump(old) if old is not None else None, json_dump(new) if new is not None else None, json_dump(metadata or {})),
        )

    def _create_version_record(self, connection: sqlite3.Connection, module_id: str, user_id: int, source_dir: Path, entry: str, manifest: dict, label: str = "", changelog: str = "") -> dict:
        number = int(connection.execute("SELECT COALESCE(MAX(version_number),0)+1 FROM scad_module_versions WHERE module_id=?", (module_id,)).fetchone()[0])
        version_id = str(uuid.uuid4())
        final_dir = self.storage / "modules" / module_id / "versions" / version_id
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_dir), final_dir)
        parsed = self.parser.parse_file(final_dir / entry)
        source_hash = self._tree_hash(final_dir)
        now = utc_now()
        connection.execute(
            "INSERT INTO scad_module_versions(id,module_id,version_number,version_label,source_hash,storage_path,entry_file,manifest_json,parameters_json,parser_warnings_json,created_by,created_at,changelog) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (version_id, module_id, number, label or f"v{number}", source_hash, str(final_dir), entry, json_dump(manifest), json_dump([p.model_dump() for p in parsed.parameters]), json_dump(parsed.warnings), user_id, now, changelog),
        )
        connection.execute("UPDATE scad_modules SET working_version_id=?, updated_at=?, updated_by=?, revision=revision+1 WHERE id=?", (version_id, now, user_id, module_id))
        self._audit(connection, user_id, module_id, "module.version_created", version_id, new={"version_number": number, "source_hash": source_hash})
        return self._decode_version(connection.execute("SELECT * FROM scad_module_versions WHERE id=?", (version_id,)).fetchone()) or {}

    def create_module(self, user: dict, data: ModuleCreate, payload: bytes, filename: str) -> dict:
        self.initialize()
        if data.visibility == "system" and user.get("role") != "admin":
            raise PermissionError("Tylko administrator może tworzyć moduły systemowe")
        module_id = str(uuid.uuid4())
        staging = self.storage / "tmp" / str(uuid.uuid4())
        try:
            entry, manifest = self._prepare_payload(payload, filename, staging)
            now = utc_now()
            with self._lock, self._connect() as connection:
                module_limit = int(os.getenv("LITHO_SCAD_MAX_MODULES_PER_USER", "100"))
                owned = int(connection.execute("SELECT COUNT(*) FROM scad_modules WHERE owner_user_id=? AND status!='deleted'", (user["id"],)).fetchone()[0])
                if owned >= module_limit:
                    raise ValueError(f"Osiągnięto limit {module_limit} modułów użytkownika")
                slug = self._unique_slug(connection, data.name)
                connection.execute(
                    "INSERT INTO scad_modules(id,owner_user_id,name,slug,description,category,visibility,status,official,created_at,updated_at,created_by,updated_by,revision) VALUES(?,?,?,?,?,?,?,?,0,?,?,?,?,1)",
                    (module_id, user["id"], data.name.strip(), slug, data.description.strip(), data.category, data.visibility, "draft", now, now, user["id"], user["id"]),
                )
                version = self._create_version_record(connection, module_id, user["id"], staging, entry, manifest)
                self._audit(connection, user["id"], module_id, "module.created", version["id"], new={"name": data.name, "visibility": data.visibility})
                return self._module_query(connection, module_id)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def seed_bundled_examples(self) -> list[str]:
        if os.getenv("LITHO_SCAD_SEED_EXAMPLES", "true").lower() in {"0", "false", "no"}:
            return []
        root = Path(os.getenv("LITHO_SCAD_EXAMPLES_DIR", "/app/examples/scad"))
        if not root.is_dir():
            development_root = Path(__file__).resolve().parents[3] / "examples" / "scad"
            root = development_root if development_root.is_dir() else root
        if not root.is_dir():
            return []
        self.initialize()
        with self._connect() as connection:
            admin = connection.execute("SELECT id,username,display_name,role,active,created_at FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1").fetchone()
        if not admin:
            return []
        actor = dict(admin)
        created: list[str] = []
        for directory in sorted(item for item in root.iterdir() if item.is_dir()):
            manifest_path = directory / "module.json"
            if not manifest_path.is_file():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            expected_slug = slugify(str(manifest.get("name", directory.name)))
            with self._connect() as connection:
                if connection.execute("SELECT 1 FROM scad_modules WHERE slug=?", (expected_slug,)).fetchone():
                    continue
            archive = io.BytesIO()
            with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
                for path in directory.rglob("*"):
                    if path.is_file(): bundle.write(path, path.relative_to(directory).as_posix())
            module = self.create_module(actor, ModuleCreate(
                name=str(manifest.get("name", directory.name)),
                description=str(manifest.get("description", "")),
                category=str(manifest.get("category", "Other")),
                visibility="private",
            ), archive.getvalue(), f"{directory.name}.zip")
            self.publish(actor, module["id"], None, "system")
            self.moderate(actor, module["id"], "official")
            created.append(module["id"])
        return created

    def update_module(self, user: dict, module_id: str, update: ModuleUpdate) -> dict:
        self.initialize()
        with self._lock, self._connect() as connection:
            module = self._module_query(connection, module_id)
            module_permissions.require("update", user, module)
            if update.visibility == "system" and user.get("role") != "admin":
                raise PermissionError("Tylko administrator może ustawić widoczność system")
            if update.revision != module["revision"]:
                raise RuntimeError("revision_conflict")
            old = {key: module[key] for key in ("name", "description", "category", "visibility")}
            now = utc_now()
            connection.execute(
                "UPDATE scad_modules SET name=?,description=?,category=?,visibility=?,updated_at=?,updated_by=?,revision=revision+1 WHERE id=?",
                (update.name.strip(), update.description.strip(), update.category, update.visibility, now, user["id"], module_id),
            )
            new = update.model_dump(exclude={"revision"})
            action = "module.visibility_changed" if old["visibility"] != update.visibility else "module.updated"
            self._audit(connection, user["id"], module_id, action, old=old, new=new, metadata={"admin_modified": user["id"] != module["owner_user_id"]})
            if user["id"] != module["owner_user_id"]:
                self._audit(connection, user["id"], module_id, "module.admin_modified", old=old, new=new)
            return self._module_query(connection, module_id)

    def add_version(self, user: dict, module_id: str, payload: bytes, filename: str, label: str = "", changelog: str = "") -> dict:
        self.initialize()
        module = self.get_module(module_id)
        module_permissions.require("version", user, module)
        staging = self.storage / "tmp" / str(uuid.uuid4())
        try:
            entry, manifest = self._prepare_payload(payload, filename, staging)
            with self._lock, self._connect() as connection:
                return self._create_version_record(connection, module_id, user["id"], staging, entry, manifest, label, changelog)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def publish(self, user: dict, module_id: str, version_id: str | None, visibility: str) -> dict:
        self.initialize()
        with self._lock, self._connect() as connection:
            module = self._module_query(connection, module_id)
            module_permissions.require("publish", user, module)
            if visibility == "system" and user.get("role") != "admin":
                raise PermissionError("Tylko administrator może publikować moduły systemowe")
            selected = version_id or module["working_version_id"]
            if not connection.execute("SELECT 1 FROM scad_module_versions WHERE id=? AND module_id=?", (selected, module_id)).fetchone():
                raise KeyError(selected)
            old = {"status": module["status"], "published_version_id": module["published_version_id"], "visibility": module["visibility"]}
            now = utc_now()
            connection.execute("UPDATE scad_modules SET published_version_id=?,status='published',visibility=?,updated_at=?,updated_by=?,revision=revision+1 WHERE id=?", (selected, visibility, now, user["id"], module_id))
            self._audit(connection, user["id"], module_id, "module.published", selected, old=old, new={"status": "published", "published_version_id": selected, "visibility": visibility})
            return self._module_query(connection, module_id)

    def unpublish(self, user: dict, module_id: str) -> dict:
        self.initialize()
        with self._lock, self._connect() as connection:
            module = self._module_query(connection, module_id)
            module_permissions.require("unpublish", user, module)
            connection.execute("UPDATE scad_modules SET status='draft',visibility='private',updated_at=?,updated_by=?,revision=revision+1 WHERE id=?", (utc_now(), user["id"], module_id))
            self._audit(connection, user["id"], module_id, "module.unpublished", old={"status": module["status"]}, new={"status": "draft"})
            return self._module_query(connection, module_id)

    def restore_version(self, user: dict, module_id: str, version_id: str) -> dict:
        source = self.version(version_id)
        module = self.get_module(module_id)
        module_permissions.require("version", user, module)
        if source["module_id"] != module_id:
            raise KeyError(version_id)
        staging = self.storage / "tmp" / str(uuid.uuid4())
        shutil.copytree(source["storage_path"], staging)
        with self._lock, self._connect() as connection:
            return self._create_version_record(connection, module_id, user["id"], staging, source["entry_file"], source["manifest"], f"Restore v{source['version_number']}", f"Przywrócono wersję {source['version_number']}")

    def duplicate(self, user: dict, module_id: str) -> dict:
        source_module = self.with_share(self.get_module(module_id), user["id"])
        module_permissions.require("duplicate", user, source_module)
        source_version_id = source_module["published_version_id"] or source_module["working_version_id"]
        source_version = self.version(source_version_id)
        new_id = str(uuid.uuid4())
        staging = self.storage / "tmp" / str(uuid.uuid4())
        shutil.copytree(source_version["storage_path"], staging)
        now = utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO scad_modules(id,owner_user_id,name,slug,description,category,visibility,status,official,forked_from_module_id,forked_from_version_id,created_at,updated_at,created_by,updated_by,revision) VALUES(?,?,?,?,?,?,?,'draft',0,?,?,?,?,?,?,1)",
                (new_id, user["id"], f"{source_module['name']} — kopia", self._unique_slug(connection, source_module["name"] + " copy"), source_module["description"], source_module["category"], "private", module_id, source_version_id, now, now, user["id"], user["id"]),
            )
            version = self._create_version_record(connection, new_id, user["id"], staging, source_version["entry_file"], source_version["manifest"], "Fork", f"Kopia modułu {module_id}")
            self._audit(connection, user["id"], new_id, "module.created", version["id"], metadata={"forked_from_module_id": module_id, "forked_from_version_id": source_version_id})
            return self._module_query(connection, new_id)

    def soft_delete(self, user: dict, module_id: str) -> None:
        self.initialize()
        with self._lock, self._connect() as connection:
            module = self._module_query(connection, module_id)
            module_permissions.require("delete", user, module)
            connection.execute("UPDATE scad_modules SET status_before_delete=status,status='deleted',deleted_at=?,deleted_by=?,updated_at=?,updated_by=?,revision=revision+1 WHERE id=?", (utc_now(), user["id"], utc_now(), user["id"], module_id))
            self._audit(connection, user["id"], module_id, "module.deleted", old={"status": module["status"]}, new={"status": "deleted"})

    def restore(self, user: dict, module_id: str) -> dict:
        self.initialize()
        with self._lock, self._connect() as connection:
            module = self._module_query(connection, module_id)
            module_permissions.require("restore", user, module)
            status = module["status_before_delete"] or "draft"
            connection.execute("UPDATE scad_modules SET status=?,status_before_delete=NULL,deleted_at=NULL,deleted_by=NULL,updated_at=?,updated_by=?,revision=revision+1 WHERE id=?", (status, utc_now(), user["id"], module_id))
            self._audit(connection, user["id"], module_id, "module.restored", new={"status": status})
            return self._module_query(connection, module_id)

    def permanent_delete(self, user: dict, module_id: str) -> None:
        module = self.get_module(module_id)
        module_permissions.require("permanent_delete", user, module)
        with self._lock, self._connect() as connection:
            output_paths = [row[0] for row in connection.execute("SELECT DISTINCT output_path FROM scad_render_jobs WHERE module_id=? AND output_path IS NOT NULL", (module_id,))]
            self._audit(connection, user["id"], module_id, "module.permanently_deleted", old=module)
            connection.execute("DELETE FROM scad_modules WHERE id=?", (module_id,))
        shutil.rmtree(self.storage / "modules" / module_id, ignore_errors=True)
        for output_path in output_paths:
            Path(output_path).unlink(missing_ok=True)

    def moderate(self, user: dict, module_id: str, action: str) -> dict:
        self.initialize()
        with self._lock, self._connect() as connection:
            module = self._module_query(connection, module_id)
            module_permissions.require("moderate", user, module)
            status, official, visibility = module["status"], module["official"], module["visibility"]
            if action == "hide": status = "hidden"
            elif action == "unhide": status = "published"
            elif action == "block": status = "blocked"
            elif action == "unblock": status = "published"
            elif action == "official": official, visibility = True, "system"
            elif action == "unofficial": official, visibility = False, "public"
            connection.execute("UPDATE scad_modules SET status=?,official=?,visibility=?,updated_at=?,updated_by=?,revision=revision+1 WHERE id=?", (status, int(official), visibility, utc_now(), user["id"], module_id))
            audit_action = {"hide": "module.hidden", "unhide": "module.unhidden", "block": "module.blocked", "unblock": "module.unblocked", "official": "module.official_changed", "unofficial": "module.official_changed"}[action]
            self._audit(connection, user["id"], module_id, audit_action, old={"status": module["status"], "official": module["official"]}, new={"status": status, "official": official})
            return self._module_query(connection, module_id)

    def presets(self, user: dict, module_id: str) -> list[dict]:
        module = self.with_share(self.get_module(module_id), user["id"])
        module_permissions.require("read", user, module)
        with self._connect() as connection:
            return [self._decode(row) or {} for row in connection.execute("SELECT * FROM scad_presets WHERE module_id=? AND user_id=? ORDER BY name COLLATE NOCASE", (module_id, user["id"]))]

    def save_preview(self, user: dict, module_id: str, payload: bytes, content_type: str) -> dict:
        module = self.get_module(module_id)
        module_permissions.require("update", user, module)
        signatures = {"image/png": (b"\x89PNG\r\n\x1a\n", ".png"), "image/jpeg": (b"\xff\xd8\xff", ".jpg")}
        signature = signatures.get(content_type)
        if not signature or not payload.startswith(signature[0]):
            raise ValueError("Podgląd musi być poprawnym plikiem PNG lub JPEG")
        if len(payload) > 5 * 1024 * 1024:
            raise ValueError("Podgląd przekracza limit 5 MB")
        try:
            with Image.open(io.BytesIO(payload)) as image:
                if image.width > 4096 or image.height > 4096:
                    raise ValueError("Podgląd może mieć maksymalnie 4096 × 4096 px")
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("Plik podglądu jest uszkodzony") from exc
        target = self.storage / "modules" / module_id / f"preview{signature[1]}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        with self._lock, self._connect() as connection:
            connection.execute("UPDATE scad_modules SET preview_path=?,updated_at=?,updated_by=?,revision=revision+1 WHERE id=?", (str(target), utc_now(), user["id"], module_id))
            self._audit(connection, user["id"], module_id, "module.updated", old={"preview_path": module.get("preview_path")}, new={"preview_path": target.name})
            return self._module_query(connection, module_id)

    def share(self, user: dict, module_id: str, username: str) -> dict:
        module = self.get_module(module_id)
        module_permissions.require("update", user, module)
        with self._lock, self._connect() as connection:
            target = connection.execute("SELECT id,username,display_name FROM users WHERE username=? COLLATE NOCASE AND active=1", (username.strip(),)).fetchone()
            if not target: raise KeyError(username)
            if target["id"] == module["owner_user_id"]: raise ValueError("Właściciel już ma dostęp")
            connection.execute("INSERT OR IGNORE INTO scad_module_shares(module_id,user_id,created_by,created_at) VALUES(?,?,?,?)", (module_id, target["id"], user["id"], utc_now()))
            self._audit(connection, user["id"], module_id, "module.shared", new={"user_id": target["id"], "username": target["username"]})
            return dict(target)

    def shares(self, user: dict, module_id: str) -> list[dict]:
        module = self.get_module(module_id)
        module_permissions.require("update", user, module)
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("SELECT u.id,u.username,u.display_name,s.created_at FROM scad_module_shares s JOIN users u ON u.id=s.user_id WHERE s.module_id=? ORDER BY u.username", (module_id,))]

    def unshare(self, user: dict, module_id: str, target_user_id: int) -> None:
        module = self.get_module(module_id)
        module_permissions.require("update", user, module)
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM scad_module_shares WHERE module_id=? AND user_id=?", (module_id, target_user_id))
            self._audit(connection, user["id"], module_id, "module.unshared", old={"user_id": target_user_id})

    def save_preset(self, user: dict, module_id: str, data: PresetCreate, preset_id: str | None = None) -> dict:
        module = self.with_share(self.get_module(module_id), user["id"])
        module_permissions.require("read", user, module)
        now = utc_now()
        with self._lock, self._connect() as connection:
            if preset_id:
                row = connection.execute("SELECT * FROM scad_presets WHERE id=? AND module_id=? AND user_id=?", (preset_id, module_id, user["id"])).fetchone()
                if not row: raise KeyError(preset_id)
                connection.execute("UPDATE scad_presets SET name=?,parameters_json=?,updated_at=? WHERE id=?", (data.name, json_dump(data.parameters), now, preset_id))
            else:
                preset_id = str(uuid.uuid4())
                connection.execute("INSERT INTO scad_presets(id,module_id,user_id,name,parameters_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (preset_id, module_id, user["id"], data.name, json_dump(data.parameters), now, now))
            return self._decode(connection.execute("SELECT * FROM scad_presets WHERE id=?", (preset_id,)).fetchone()) or {}

    def delete_preset(self, user: dict, module_id: str, preset_id: str) -> None:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM scad_presets WHERE id=? AND module_id=? AND user_id=?", (preset_id, module_id, user["id"]))
            if not cursor.rowcount: raise KeyError(preset_id)

    def audit(self, user: dict, module_id: str) -> list[dict]:
        module = self.get_module(module_id)
        if user.get("role") != "admin" and user["id"] != module["owner_user_id"]:
            module_permissions.require("audit_all", user, module)
        with self._connect() as connection:
            rows = connection.execute("SELECT a.*,u.username actor_username FROM scad_module_audit_logs a JOIN users u ON u.id=a.actor_user_id WHERE target_module_id=? ORDER BY timestamp DESC", (module_id,)).fetchall()
            output = []
            for row in rows:
                item = dict(row)
                for field in ("old_value_json", "new_value_json", "metadata_json"):
                    item[field.removesuffix("_json")] = json.loads(item.pop(field) or "null")
                output.append(item)
            return output


scad_repository = ScadRepository()
