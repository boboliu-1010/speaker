-- Boa Voice v1 既有 registry.sqlite3 的增量设计，2026-10-29。
-- 假定原库有 users / bindings / sources；不重建、不迁移这些旧表。
-- 验证时可建最小父表；正式迁移必须先核对实际 schema_version 与字段。
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
PRAGMA synchronous=FULL;
BEGIN IMMEDIATE;

CREATE TABLE source_outbox (
  event_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL UNIQUE REFERENCES sources(id),
  event_kind TEXT NOT NULL CHECK(event_kind='source_ready'),
  source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
  created_at INTEGER NOT NULL, consumed_at INTEGER,
  attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts>=0), last_error_code TEXT
);
CREATE INDEX source_outbox_pending ON source_outbox(consumed_at,created_at,event_id);

CREATE TABLE session_tombstones (
  source_kind TEXT NOT NULL CHECK(source_kind IN ('clip_direct','app_upload')),
  binding_id TEXT NOT NULL, -- Clip binding ID 或 app:<原 user_id> 隔离 namespace
  clip_binding_id TEXT REFERENCES bindings(id),
  epoch INTEGER NOT NULL CHECK(epoch>=0), source_session TEXT NOT NULL,
  owner TEXT NOT NULL REFERENCES users(id),
  deletion_epoch INTEGER NOT NULL CHECK(deletion_epoch>0),
  enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
  deleted_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  purge_after INTEGER NOT NULL, purged_at INTEGER,
  PRIMARY KEY(source_kind,binding_id,epoch,source_session),
  CHECK((source_kind='clip_direct' AND clip_binding_id IS NOT NULL
      AND clip_binding_id=binding_id AND epoch>0)
    OR (source_kind='app_upload' AND clip_binding_id IS NULL AND epoch=0))
);
CREATE TABLE deletion_outbox (
  event_id TEXT PRIMARY KEY, source_kind TEXT NOT NULL,
  binding_id TEXT NOT NULL, epoch INTEGER NOT NULL,
  source_session TEXT NOT NULL, deletion_epoch INTEGER NOT NULL CHECK(deletion_epoch>0),
  action TEXT NOT NULL CHECK(action IN ('delete','restore','purge')),
  created_at INTEGER NOT NULL, consumed_at INTEGER,
  UNIQUE(source_kind,binding_id,epoch,source_session,deletion_epoch,action),
  FOREIGN KEY(source_kind,binding_id,epoch,source_session)
    REFERENCES session_tombstones(source_kind,binding_id,epoch,source_session)
);
CREATE INDEX deletion_outbox_pending ON deletion_outbox(consumed_at,created_at,event_id);

-- source 状态更新与 source_ready 插入在同一显式事务完成；本脚本不加触发器，
-- 因旧源表状态枚举须在实施迁移时核对。事件必须只在完整文件校验后产生。
-- App 上传不属于 registry sources：在其自己的接收索引中应用相同 outbox 契约，
-- 或保留持久文件/身份索引对账；不得伪造 clip binding。
COMMIT;
