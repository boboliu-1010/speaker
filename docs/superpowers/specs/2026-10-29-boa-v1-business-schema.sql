-- 录音助手 v1：依据 2026-10-29 新原型精简，设计附件，不是旧库迁移脚本。
-- 单用户归属、UTC Unix 毫秒；文件保存在磁盘，不存音频 BLOB。
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA busy_timeout=5000;
BEGIN IMMEDIATE;
CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL, checksum TEXT NOT NULL
);
CREATE TABLE accounts (
  user_id TEXT PRIMARY KEY,
  google_sub TEXT UNIQUE CHECK(google_sub IS NULL OR length(google_sub) BETWEEN 1 AND 255),
  email TEXT NOT NULL UNIQUE COLLATE NOCASE
    CHECK(email=trim(email) AND length(email) BETWEEN 3 AND 254 AND instr(email,'@')>1),
  display_name TEXT NOT NULL DEFAULT '' CHECK(length(display_name)<=100),
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','disabled')),
  auth_version INTEGER NOT NULL DEFAULT 1 CHECK(auth_version>0),
  last_login_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
-- Google OAuth 临时事务与本站会话只保存在进程内存，不建会话/token 表。
-- UID、owner、epoch、设备凭证仍由既有 registry 管理；不复制一套设备身份。
CREATE TABLE device_preferences (
  owner TEXT NOT NULL REFERENCES accounts(user_id), device_id TEXT NOT NULL,
  binding_id TEXT NOT NULL, display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 1 AND 100),
  updated_at INTEGER NOT NULL, PRIMARY KEY(owner,device_id,binding_id)
);
CREATE TABLE recordings (
  id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES accounts(user_id),
  source_kind TEXT NOT NULL CHECK(source_kind IN ('clip_direct','app_upload')),
  source_namespace TEXT NOT NULL, binding_epoch INTEGER NOT NULL CHECK(binding_epoch>=0),
  source_session TEXT NOT NULL,
  recorded_at INTEGER, time_source TEXT NOT NULL CHECK(time_source IN ('device_unverified','server_received','client_confirmed')),
  received_at INTEGER NOT NULL, last_received_at INTEGER NOT NULL,
  integrity TEXT NOT NULL DEFAULT 'unknown' CHECK(integrity IN ('unknown','gap','confirmed_complete')),
  input_revision INTEGER NOT NULL DEFAULT 0 CHECK(input_revision>=0),
  audio_revision INTEGER, transcript_revision INTEGER,
  audio_state TEXT NOT NULL DEFAULT 'pending' CHECK(audio_state IN ('pending','running','ready','failed')),
  transcript_state TEXT NOT NULL DEFAULT 'pending' CHECK(transcript_state IN ('not_configured','pending','running','ready','failed')),
  wav_object_id TEXT, vtt_object_id TEXT, duration_ms INTEGER CHECK(duration_ms>=0),
  updated_at INTEGER NOT NULL,
  UNIQUE(source_kind,source_namespace,binding_epoch,source_session), UNIQUE(id,owner),
  CHECK((source_kind='clip_direct' AND binding_epoch>0) OR (source_kind='app_upload' AND binding_epoch=0)),
  CHECK(audio_revision IS NULL OR (audio_revision>0 AND audio_revision<=input_revision)),
  CHECK(transcript_revision IS NULL OR (transcript_revision>0 AND transcript_revision<=input_revision)),
  CHECK(audio_state<>'ready' OR (wav_object_id IS NOT NULL AND audio_revision IS NOT NULL)),
  CHECK(transcript_state<>'ready' OR (vtt_object_id IS NOT NULL AND transcript_revision IS NOT NULL
    AND audio_revision IS NOT NULL AND transcript_revision=audio_revision)),
  FOREIGN KEY(wav_object_id,id,owner) REFERENCES storage_objects(id,recording_id,owner) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(vtt_object_id,id,owner) REFERENCES storage_objects(id,recording_id,owner) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX recordings_owner_date ON recordings(owner,recorded_at DESC,id DESC);
CREATE INDEX recordings_owner_received ON recordings(owner,received_at DESC,id DESC);
CREATE TABLE storage_objects (
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, recording_id TEXT NOT NULL,
  input_revision INTEGER NOT NULL CHECK(input_revision>=0),
  kind TEXT NOT NULL CHECK(kind IN ('raw','wav','vtt')),
  relative_path TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL CHECK(state IN ('staged','ready','missing','failed')),
  size_bytes INTEGER CHECK(size_bytes>0), sha256 TEXT CHECK(length(sha256)=64),
  mime TEXT NOT NULL,
  sample_rate INTEGER CHECK(sample_rate>0), channels INTEGER CHECK(channels>0),
  sample_count INTEGER CHECK(sample_count>=0), created_at INTEGER NOT NULL,
  UNIQUE(id,recording_id,owner),
  FOREIGN KEY(recording_id,owner) REFERENCES recordings(id,owner),
  CHECK(state<>'ready' OR (size_bytes IS NOT NULL AND sha256 IS NOT NULL))
);
CREATE TABLE recording_segments (
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, recording_id TEXT NOT NULL,
  source_namespace TEXT NOT NULL, source_id TEXT NOT NULL,
  segment_no INTEGER NOT NULL CHECK(segment_no>0),
  size_bytes INTEGER NOT NULL CHECK(size_bytes>0), sha256 TEXT NOT NULL CHECK(length(sha256)=64),
  state TEXT NOT NULL CHECK(state IN ('receiving','ready')),
  raw_object_id TEXT, received_at INTEGER NOT NULL,
  UNIQUE(source_namespace,source_id), UNIQUE(recording_id,segment_no),
  FOREIGN KEY(recording_id,owner) REFERENCES recordings(id,owner),
  FOREIGN KEY(raw_object_id,recording_id,owner) REFERENCES storage_objects(id,recording_id,owner),
  CHECK(state<>'ready' OR raw_object_id IS NOT NULL)
);
CREATE TABLE source_receipts (
  event_id TEXT PRIMARY KEY, source_namespace TEXT NOT NULL, source_id TEXT NOT NULL,
  recording_id TEXT NOT NULL REFERENCES recordings(id),
  sha256 TEXT NOT NULL CHECK(length(sha256)=64), applied_at INTEGER NOT NULL,
  UNIQUE(source_namespace,source_id)
);
CREATE TABLE jobs (
  id TEXT PRIMARY KEY, recording_id TEXT NOT NULL REFERENCES recordings(id),
  input_revision INTEGER NOT NULL CHECK(input_revision>0),
  kind TEXT NOT NULL CHECK(kind IN ('decode','transcribe')),
  dedupe_key TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL CHECK(state IN ('pending','running','retry_wait','succeeded','failed')),
  attempt INTEGER NOT NULL DEFAULT 0 CHECK(attempt>=0), run_after INTEGER NOT NULL,
  lease_token TEXT, lease_until INTEGER,
  -- 冻结有序 source_id/hash 列表及工具配置，避免运行中读到新输入。
  input_json TEXT NOT NULL CHECK(json_valid(input_json)),
  error_code TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  UNIQUE(id,recording_id),
  CHECK(state<>'running' OR (lease_token IS NOT NULL AND lease_until IS NOT NULL))
);
CREATE INDEX jobs_claim ON jobs(state,run_after,id);
CREATE TABLE file_publications (
  object_id TEXT PRIMARY KEY, owner TEXT NOT NULL, recording_id TEXT NOT NULL,
  job_id TEXT NOT NULL, lease_token TEXT NOT NULL,
  tmp_relative_path TEXT NOT NULL UNIQUE,
  expected_size INTEGER CHECK(expected_size>0), expected_sha256 TEXT CHECK(length(expected_sha256)=64),
  state TEXT NOT NULL CHECK(state IN ('prepared','committed','abandoned')),
  updated_at INTEGER NOT NULL,
  FOREIGN KEY(object_id,recording_id,owner) REFERENCES storage_objects(id,recording_id,owner),
  FOREIGN KEY(job_id,recording_id) REFERENCES jobs(id,recording_id),
  CHECK(state<>'committed' OR (expected_size IS NOT NULL AND expected_sha256 IS NOT NULL))
);
CREATE TABLE transcript_cues (
  recording_id TEXT NOT NULL, owner TEXT NOT NULL,
  input_revision INTEGER NOT NULL CHECK(input_revision>0),
  cue_index INTEGER NOT NULL CHECK(cue_index>0),
  start_ms INTEGER NOT NULL CHECK(start_ms>=0), end_ms INTEGER NOT NULL,
  speaker TEXT, text TEXT NOT NULL CHECK(length(text)>0),
  PRIMARY KEY(recording_id,input_revision,cue_index),
  FOREIGN KEY(recording_id,owner) REFERENCES recordings(id,owner),
  CHECK(end_ms>start_ms)
);
COMMIT;
