PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS scad_modules (
    id TEXT PRIMARY KEY,
    owner_user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'Other',
    working_version_id TEXT,
    published_version_id TEXT,
    visibility TEXT NOT NULL DEFAULT 'private' CHECK(visibility IN ('private','public','unlisted','system')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','hidden','blocked','deleted')),
    status_before_delete TEXT,
    official INTEGER NOT NULL DEFAULT 0,
    preview_path TEXT,
    forked_from_module_id TEXT REFERENCES scad_modules(id),
    forked_from_version_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    updated_by INTEGER NOT NULL REFERENCES users(id),
    deleted_at TEXT,
    deleted_by INTEGER REFERENCES users(id),
    revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS scad_module_versions (
    id TEXT PRIMARY KEY,
    module_id TEXT NOT NULL REFERENCES scad_modules(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    version_label TEXT NOT NULL DEFAULT '',
    source_hash TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    entry_file TEXT NOT NULL DEFAULT 'main.scad',
    manifest_json TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    parser_warnings_json TEXT NOT NULL DEFAULT '[]',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    changelog TEXT NOT NULL DEFAULT '',
    UNIQUE(module_id, version_number)
);

CREATE TABLE IF NOT EXISTS scad_presets (
    id TEXT PRIMARY KEY,
    module_id TEXT NOT NULL REFERENCES scad_modules(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(module_id, user_id, name)
);

CREATE TABLE IF NOT EXISTS scad_module_shares (
    module_id TEXT NOT NULL REFERENCES scad_modules(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    PRIMARY KEY(module_id, user_id)
);

CREATE TABLE IF NOT EXISTS scad_render_jobs (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    module_id TEXT NOT NULL REFERENCES scad_modules(id) ON DELETE CASCADE,
    version_id TEXT NOT NULL REFERENCES scad_module_versions(id) ON DELETE CASCADE,
    parameters_json TEXT NOT NULL,
    parameters_hash TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    openscad_version TEXT NOT NULL DEFAULT '',
    output_format TEXT NOT NULL CHECK(output_format IN ('stl','3mf')),
    mode TEXT NOT NULL DEFAULT 'model' CHECK(mode IN ('model','metadata')),
    cache_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed','cancelled','timed_out')),
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    duration_seconds REAL,
    output_path TEXT,
    output_size INTEGER,
    stdout TEXT NOT NULL DEFAULT '',
    stderr TEXT NOT NULL DEFAULT '',
    command_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    error_code TEXT,
    error_message TEXT,
    cached INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scad_module_audit_logs (
    id TEXT PRIMARY KEY,
    actor_user_id INTEGER NOT NULL REFERENCES users(id),
    target_module_id TEXT NOT NULL,
    target_version_id TEXT,
    action TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    old_value_json TEXT,
    new_value_json TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS scad_modules_owner_idx ON scad_modules(owner_user_id, updated_at);
CREATE INDEX IF NOT EXISTS scad_modules_catalog_idx ON scad_modules(status, visibility, official, updated_at);
CREATE INDEX IF NOT EXISTS scad_versions_module_idx ON scad_module_versions(module_id, version_number DESC);
CREATE INDEX IF NOT EXISTS scad_presets_owner_idx ON scad_presets(module_id, user_id);
CREATE INDEX IF NOT EXISTS scad_shares_user_idx ON scad_module_shares(user_id, module_id);
CREATE INDEX IF NOT EXISTS scad_jobs_owner_idx ON scad_render_jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS scad_jobs_cache_idx ON scad_render_jobs(cache_key, status);
CREATE INDEX IF NOT EXISTS scad_audit_target_idx ON scad_module_audit_logs(target_module_id, timestamp DESC);
