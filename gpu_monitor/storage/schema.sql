PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS gpu_process_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_time TEXT NOT NULL,
    local_date TEXT NOT NULL,
    gpu_index INTEGER NOT NULL,
    gpu_uuid TEXT,
    pid INTEGER NOT NULL,
    username TEXT NOT NULL,
    process_name TEXT,
    used_memory_mb REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_samples_time
ON gpu_process_samples(sample_time);

CREATE TABLE IF NOT EXISTS gpu_device_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_time TEXT NOT NULL,
    local_date TEXT NOT NULL,
    gpu_index INTEGER NOT NULL,
    gpu_uuid TEXT,
    gpu_name TEXT,
    total_memory_mb REAL,
    gpu_util_percent REAL,
    memory_util_percent REAL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gpu_snapshot_time
ON gpu_device_snapshots(sample_time);

CREATE TABLE IF NOT EXISTS service_heartbeats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    heartbeat_time TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_heartbeat_time
ON service_heartbeats(heartbeat_time);

CREATE TABLE IF NOT EXISTS daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    generated_at TEXT,
    json_path TEXT,
    content_hash TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    status TEXT NOT NULL,
    generated_at TEXT,
    json_path TEXT,
    content_hash TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(week_start, week_end)
);

CREATE TABLE IF NOT EXISTS error_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    traceback TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_error_events_time
ON error_events(event_time);
