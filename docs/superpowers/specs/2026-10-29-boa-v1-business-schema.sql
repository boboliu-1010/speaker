-- Boa Voice v1 新业务库参考 DDL，2026-10-29。
-- 设计附件：只用于空库结构验证；不是既有生产库迁移脚本。
-- 时间统一为 UTC Unix 毫秒；ID 由服务端生成；音频不存 BLOB。
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 5000;
BEGIN IMMEDIATE;

CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL, checksum TEXT NOT NULL
);

-- 基本用户：内部 user_id 负责数据归属，google_sub 仅保存已验证身份的稳定标识。
-- 没有邀请、组织、密码或 OAuth 流程表；旧用户允许 google_sub 为空以便迁移。
CREATE TABLE accounts (
  user_id TEXT PRIMARY KEY, -- 对应原 registry.users.id，跨库不声明 FK
  google_sub TEXT UNIQUE CHECK(google_sub IS NULL OR length(google_sub) BETWEEN 1 AND 255),
  email TEXT NOT NULL UNIQUE COLLATE NOCASE
    CHECK(email=trim(email) AND length(email) BETWEEN 3 AND 254 AND instr(email,'@')>1),
  display_name TEXT NOT NULL DEFAULT '' CHECK(length(display_name)<=100),
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','disabled')),
  auth_version INTEGER NOT NULL DEFAULT 1 CHECK(auth_version>0),
  last_login_at INTEGER,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX accounts_status ON accounts(status,created_at,user_id);

CREATE TABLE browser_sessions (
  token_digest TEXT PRIMARY KEY CHECK(length(token_digest)=64),
  user_id TEXT NOT NULL REFERENCES accounts(user_id),
  auth_version INTEGER NOT NULL CHECK(auth_version>0),
  csrf_digest TEXT NOT NULL CHECK(length(csrf_digest)=64),
  created_at INTEGER NOT NULL, last_seen_at INTEGER NOT NULL,
  idle_expires_at INTEGER NOT NULL, absolute_expires_at INTEGER NOT NULL,
  revoked_at INTEGER, source_label TEXT,
  CHECK(idle_expires_at<=absolute_expires_at),
  UNIQUE(token_digest,user_id)
);
CREATE INDEX sessions_user ON browser_sessions(user_id, revoked_at, absolute_expires_at);

CREATE TABLE device_preferences (
  device_id TEXT NOT NULL, -- 原 registry device ID
  owner TEXT NOT NULL REFERENCES accounts(user_id),
  binding_id TEXT NOT NULL, epoch INTEGER NOT NULL CHECK(epoch>0),
  display_name TEXT NOT NULL,
  desired_settings_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(desired_settings_json)),
  desired_revision INTEGER NOT NULL DEFAULT 1 CHECK(desired_revision>0),
  applied_revision INTEGER, observed_at INTEGER,
  PRIMARY KEY(owner,device_id,binding_id)
);

CREATE TABLE recordings (
  id TEXT PRIMARY KEY,
  owner TEXT NOT NULL REFERENCES accounts(user_id),
  source_kind TEXT NOT NULL CHECK(source_kind IN ('clip_direct','app_upload')),
  binding_id TEXT NOT NULL, -- App 来源使用服务端隔离 namespace，不可接受用户指定
  epoch INTEGER NOT NULL CHECK(epoch>=0), device_id TEXT, source_session TEXT NOT NULL,
  title TEXT NOT NULL, title_origin TEXT NOT NULL DEFAULT 'default'
    CHECK(title_origin IN ('default','ai','manual')),
  started_at INTEGER, received_at INTEGER NOT NULL, last_received_at INTEGER NOT NULL,
  time_source TEXT NOT NULL CHECK(time_source IN ('device_unverified','server_received','client_confirmed')),
  integrity TEXT NOT NULL CHECK(integrity IN ('receiving','unknown','confirmed_complete','conflict')),
  input_revision INTEGER NOT NULL DEFAULT 1 CHECK(input_revision>0),
  deletion_epoch INTEGER NOT NULL DEFAULT 0 CHECK(deletion_epoch>=0),
  deleted_at INTEGER, purge_after INTEGER,
  current_media_run_id TEXT, current_transcript_run_id TEXT, current_summary_run_id TEXT,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  UNIQUE(source_kind,binding_id,epoch,source_session), UNIQUE(id,owner),
  FOREIGN KEY(current_media_run_id,id) REFERENCES processing_runs(id,recording_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(current_transcript_run_id,id) REFERENCES processing_runs(id,recording_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(current_summary_run_id,id) REFERENCES processing_runs(id,recording_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX recordings_owner_time ON recordings(owner,deleted_at,started_at DESC,id DESC);
CREATE INDEX recordings_received ON recordings(owner,received_at DESC,id DESC);

CREATE TABLE storage_objects (
  id TEXT PRIMARY KEY,
  owner TEXT NOT NULL REFERENCES accounts(user_id), recording_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('raw_opus','app_original','segment_wav','session_wav','playback_mp3','export_txt','export_docx')),
  relative_path TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL CHECK(state IN ('staged','ready','superseded','missing','corrupt','deleting','deleted')),
  size_bytes INTEGER CHECK(size_bytes>=0),
  sha256 TEXT CHECK(length(sha256)=64),
  mime TEXT NOT NULL, codec TEXT,
  sample_rate INTEGER CHECK(sample_rate>0), channels INTEGER CHECK(channels>0),
  sample_count INTEGER CHECK(sample_count>=0), duration_ms INTEGER CHECK(duration_ms>=0),
  profile TEXT, decoder_version TEXT, timing_origin TEXT,
  created_at INTEGER NOT NULL, verified_at INTEGER, deleted_at INTEGER,
  UNIQUE(id,owner), UNIQUE(id,recording_id),
  FOREIGN KEY(recording_id,owner) REFERENCES recordings(id,owner),
  CHECK(state NOT IN ('ready','superseded') OR
    (size_bytes IS NOT NULL AND size_bytes>0 AND sha256 IS NOT NULL AND verified_at IS NOT NULL))
);
CREATE INDEX objects_repair ON storage_objects(state,created_at);

CREATE TABLE recording_segments (
  id TEXT PRIMARY KEY, recording_id TEXT NOT NULL, owner TEXT NOT NULL,
  source_namespace TEXT NOT NULL CHECK(source_namespace IN ('registry','app')),
  source_id TEXT NOT NULL, segment_no INTEGER NOT NULL CHECK(segment_no>0),
  raw_object_id TEXT NOT NULL, raw_size INTEGER NOT NULL CHECK(raw_size>0),
  raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256)=64),
  received_at INTEGER NOT NULL,
  UNIQUE(source_namespace,source_id), UNIQUE(recording_id,segment_no), UNIQUE(id,recording_id),
  FOREIGN KEY(recording_id,owner) REFERENCES recordings(id,owner),
  FOREIGN KEY(raw_object_id,owner) REFERENCES storage_objects(id,owner),
  FOREIGN KEY(raw_object_id,recording_id) REFERENCES storage_objects(id,recording_id)
);

CREATE TABLE recording_manifests (
  id TEXT PRIMARY KEY, recording_id TEXT NOT NULL REFERENCES recordings(id),
  revision INTEGER NOT NULL CHECK(revision>0), total_segments INTEGER NOT NULL CHECK(total_segments>0),
  closed_at INTEGER, evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
  status TEXT NOT NULL CHECK(status IN ('pending','verified','conflict')),
  created_at INTEGER NOT NULL, UNIQUE(recording_id,revision)
);

CREATE TABLE source_receipts (
  event_id TEXT PRIMARY KEY,
  source_namespace TEXT NOT NULL CHECK(source_namespace IN ('registry','app')),
  source_id TEXT NOT NULL, recording_id TEXT NOT NULL REFERENCES recordings(id),
  source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64), applied_at INTEGER NOT NULL,
  UNIQUE(source_namespace,source_id)
);

CREATE TABLE processing_runs (
  id TEXT PRIMARY KEY, recording_id TEXT NOT NULL, owner TEXT NOT NULL,
  input_revision INTEGER NOT NULL CHECK(input_revision>0),
  input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint)=64),
  pipeline_version TEXT NOT NULL, decode_profile TEXT NOT NULL,
  provider_config_id TEXT, asr_model TEXT, summary_model TEXT,
  media_state TEXT NOT NULL CHECK(media_state IN ('pending','running','ready','failed')),
  transcript_state TEXT NOT NULL CHECK(transcript_state IN ('disabled','pending','running','ready','retry_wait','failed')),
  summary_state TEXT NOT NULL CHECK(summary_state IN ('disabled','pending','running','ready','retry_wait','failed')),
  deletion_epoch INTEGER NOT NULL CHECK(deletion_epoch>=0),
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  UNIQUE(id,recording_id), UNIQUE(id,owner),
  UNIQUE(recording_id,input_revision,pipeline_version),
  FOREIGN KEY(recording_id,owner) REFERENCES recordings(id,owner)
);

CREATE TABLE run_input_segments (
  run_id TEXT NOT NULL, recording_id TEXT NOT NULL, seq INTEGER NOT NULL CHECK(seq>0),
  segment_id TEXT NOT NULL,
  source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
  start_sample INTEGER CHECK(start_sample>=0), sample_count INTEGER CHECK(sample_count>=0),
  sample_rate INTEGER CHECK(sample_rate>0),
  PRIMARY KEY(run_id,seq), UNIQUE(run_id,segment_id),
  FOREIGN KEY(run_id,recording_id) REFERENCES processing_runs(id,recording_id),
  FOREIGN KEY(segment_id,recording_id) REFERENCES recording_segments(id,recording_id)
);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY, recording_id TEXT NOT NULL REFERENCES recordings(id),
  run_id TEXT, kind TEXT NOT NULL
    CHECK(kind IN ('prepare_media','transcribe','summarize','index','export','purge')),
  input_revision INTEGER NOT NULL CHECK(input_revision>0),
  deletion_epoch INTEGER NOT NULL CHECK(deletion_epoch>=0),
  dedupe_key TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL CHECK(state IN ('pending','running','retry_wait','succeeded','failed','cancelled')),
  attempt INTEGER NOT NULL DEFAULT 0 CHECK(attempt>=0),
  run_after INTEGER NOT NULL, lease_until INTEGER, lease_token TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(payload_json)),
  error_code TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  UNIQUE(id,recording_id),
  FOREIGN KEY(run_id,recording_id) REFERENCES processing_runs(id,recording_id),
  CHECK(state<>'running' OR (lease_token IS NOT NULL AND lease_until IS NOT NULL))
);
CREATE INDEX jobs_claim ON jobs(state,run_after,id);
CREATE INDEX jobs_lease ON jobs(state,lease_until);

CREATE TABLE file_publications (
  id TEXT PRIMARY KEY, object_id TEXT NOT NULL UNIQUE REFERENCES storage_objects(id),
  job_id TEXT NOT NULL, lease_token TEXT NOT NULL,
  recording_id TEXT NOT NULL, input_revision INTEGER NOT NULL CHECK(input_revision>0),
  deletion_epoch INTEGER NOT NULL CHECK(deletion_epoch>=0),
  tmp_relative_path TEXT NOT NULL UNIQUE, final_relative_path TEXT NOT NULL UNIQUE,
  expected_size INTEGER CHECK(expected_size>0), expected_sha256 TEXT CHECK(length(expected_sha256)=64),
  expected_metadata_json TEXT CHECK(expected_metadata_json IS NULL OR json_valid(expected_metadata_json)),
  state TEXT NOT NULL CHECK(state IN ('prepared','renamed','committed','abandoned')),
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  FOREIGN KEY(object_id,recording_id) REFERENCES storage_objects(id,recording_id),
  FOREIGN KEY(job_id,recording_id) REFERENCES jobs(id,recording_id),
  CHECK(state NOT IN ('renamed','committed') OR (expected_size IS NOT NULL AND expected_sha256 IS NOT NULL))
);
CREATE INDEX publications_recovery ON file_publications(state,updated_at);

CREATE TABLE media_assets (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, recording_id TEXT NOT NULL,
  object_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('segment_wav','asr_wav','playback')),
  segment_no INTEGER NOT NULL DEFAULT 0 CHECK(segment_no>=0),
  created_at INTEGER NOT NULL,
  UNIQUE(run_id,role,segment_no),
  FOREIGN KEY(run_id,recording_id) REFERENCES processing_runs(id,recording_id),
  FOREIGN KEY(object_id,recording_id) REFERENCES storage_objects(id,recording_id)
);

CREATE TABLE transcript_segments (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES processing_runs(id),
  seq INTEGER NOT NULL CHECK(seq>=0),
  start_ms INTEGER NOT NULL CHECK(start_ms>=0), end_ms INTEGER NOT NULL,
  speaker_id TEXT, text TEXT NOT NULL,
  confidence REAL CHECK(confidence BETWEEN 0 AND 1),
  UNIQUE(run_id,seq), UNIQUE(id,run_id), CHECK(end_ms>=start_ms)
);

CREATE TABLE summaries (
  run_id TEXT PRIMARY KEY REFERENCES processing_runs(id), schema_version INTEGER NOT NULL CHECK(schema_version>0),
  title TEXT, overview TEXT NOT NULL,
  conclusions_json TEXT NOT NULL CHECK(json_valid(conclusions_json)),
  chapters_json TEXT NOT NULL CHECK(json_valid(chapters_json)),
  action_items_json TEXT NOT NULL CHECK(json_valid(action_items_json)),
  created_at INTEGER NOT NULL
);
CREATE TABLE summary_references (
  run_id TEXT NOT NULL REFERENCES summaries(run_id),
  item_key TEXT NOT NULL, transcript_segment_id TEXT NOT NULL,
  PRIMARY KEY(run_id,item_key,transcript_segment_id),
  FOREIGN KEY(transcript_segment_id,run_id) REFERENCES transcript_segments(id,run_id)
);

CREATE TABLE exports (
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, recording_id TEXT NOT NULL,
  run_id TEXT, object_id TEXT,
  format TEXT NOT NULL CHECK(format IN ('txt','docx')),
  state TEXT NOT NULL CHECK(state IN ('pending','running','ready','failed','expired')),
  created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
  FOREIGN KEY(recording_id,owner) REFERENCES recordings(id,owner),
  FOREIGN KEY(run_id,recording_id) REFERENCES processing_runs(id,recording_id),
  FOREIGN KEY(object_id,recording_id) REFERENCES storage_objects(id,recording_id),
  CHECK(state<>'ready' OR object_id IS NOT NULL)
);

CREATE TABLE media_tickets (
  ticket_digest TEXT PRIMARY KEY CHECK(length(ticket_digest)=64),
  owner TEXT NOT NULL, session_digest TEXT NOT NULL,
  recording_id TEXT NOT NULL, object_id TEXT NOT NULL,
  expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL, revoked_at INTEGER,
  FOREIGN KEY(session_digest,owner) REFERENCES browser_sessions(token_digest,user_id),
  FOREIGN KEY(recording_id,owner) REFERENCES recordings(id,owner),
  FOREIGN KEY(object_id,recording_id) REFERENCES storage_objects(id,recording_id)
);

CREATE TABLE tombstones (
  source_kind TEXT NOT NULL CHECK(source_kind IN ('clip_direct','app_upload')),
  binding_id TEXT NOT NULL, epoch INTEGER NOT NULL, source_session TEXT NOT NULL,
  recording_id TEXT NOT NULL REFERENCES recordings(id),
  deletion_epoch INTEGER NOT NULL CHECK(deletion_epoch>0),
  enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
  deleted_at INTEGER NOT NULL, purge_after INTEGER NOT NULL, purged_at INTEGER,
  PRIMARY KEY(source_kind,binding_id,epoch,source_session)
);
CREATE TABLE registry_event_receipts (
  event_id TEXT PRIMARY KEY, applied_at INTEGER NOT NULL
);

CREATE TABLE idempotency_keys (
  owner TEXT NOT NULL REFERENCES accounts(user_id), route TEXT NOT NULL, key_digest TEXT NOT NULL,
  request_digest TEXT NOT NULL, resource_id TEXT NOT NULL,
  created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
  PRIMARY KEY(owner,route,key_digest)
);

CREATE TABLE audit_events (
  id TEXT PRIMARY KEY, owner TEXT REFERENCES accounts(user_id), actor TEXT NOT NULL,
  action TEXT NOT NULL, resource_id TEXT, occurred_at INTEGER NOT NULL,
  source TEXT NOT NULL, outcome TEXT NOT NULL, request_id TEXT
);
CREATE INDEX audit_owner_time ON audit_events(owner,occurred_at DESC,id DESC);

-- 检索投影由业务事务显式维护；分词后的文本不等于原始全文。
CREATE VIRTUAL TABLE recording_search USING fts5(
  recording_id UNINDEXED, owner UNINDEXED,
  title_tokens, summary_tokens, transcript_tokens,
  tokenize='unicode61'
);
-- FTS 不提供行级权限：查询必须 JOIN recordings 并限定 owner/deleted_at。

COMMIT;
