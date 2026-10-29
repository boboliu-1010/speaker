-- 录音助手 v1：4 张新增业务表。设计附件，不是生产迁移脚本。
-- 原始音频/派生文件在磁盘；转写 JSON 在 recordings；会话只在内存。
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA busy_timeout=5000;
BEGIN IMMEDIATE;
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
  wav_job_id TEXT, vtt_job_id TEXT, duration_ms INTEGER CHECK(duration_ms>=0),
  -- 唯一文字主源：{"schema_version":1,"time_unit":"ms","cues":[...]}。
  -- cue 结构/时间/speaker 校验由应用负责；数据库保证外层结构与体积。
  transcript_json TEXT,
  updated_at INTEGER NOT NULL,
  UNIQUE(source_kind,source_namespace,binding_epoch,source_session), UNIQUE(id,owner),
  CHECK((source_kind='clip_direct' AND binding_epoch>0) OR (source_kind='app_upload' AND binding_epoch=0)),
  CHECK(audio_revision IS NULL OR (audio_revision>0 AND audio_revision<=input_revision)),
  CHECK(transcript_revision IS NULL OR (transcript_revision>0 AND transcript_revision<=input_revision)),
  CHECK(audio_state<>'ready' OR (wav_job_id IS NOT NULL AND audio_revision IS NOT NULL)),
  CHECK(transcript_json IS NULL OR CASE WHEN json_valid(transcript_json) THEN
    length(CAST(transcript_json AS BLOB))<=8388608
    AND COALESCE(json_type(transcript_json)='object'
      AND json_type(transcript_json,'$.schema_version')='integer'
      AND json_extract(transcript_json,'$.schema_version')=1
      AND json_extract(transcript_json,'$.time_unit')='ms'
      AND json_type(transcript_json,'$.cues')='array',0)
    ELSE 0 END),
  CHECK(transcript_state<>'ready' OR (vtt_job_id IS NOT NULL AND transcript_json IS NOT NULL
    AND transcript_revision IS NOT NULL AND audio_revision IS NOT NULL AND transcript_revision=audio_revision)),
  FOREIGN KEY(wav_job_id,id,owner,audio_revision) REFERENCES jobs(id,recording_id,owner,input_revision) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(vtt_job_id,id,owner,transcript_revision) REFERENCES jobs(id,recording_id,owner,input_revision) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX recordings_owner_date ON recordings(owner,recorded_at DESC,id DESC);
CREATE INDEX recordings_owner_received ON recordings(owner,received_at DESC,id DESC);
CREATE TABLE recording_segments (
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, recording_id TEXT NOT NULL,
  source_namespace TEXT NOT NULL, source_id TEXT NOT NULL,
  segment_no INTEGER NOT NULL CHECK(segment_no>0),
  state TEXT NOT NULL CHECK(state IN ('receiving','ready')),
  -- 同一行兼作 raw 文件索引与来源幂等收据，未收完整时允许为空。
  raw_relative_path TEXT UNIQUE,
  size_bytes INTEGER CHECK(size_bytes>0), sha256 TEXT CHECK(length(sha256)=64),
  received_at INTEGER NOT NULL, imported_at INTEGER,
  UNIQUE(source_namespace,source_id), UNIQUE(recording_id,segment_no),
  FOREIGN KEY(recording_id,owner) REFERENCES recordings(id,owner),
  CHECK(state<>'ready' OR (raw_relative_path IS NOT NULL AND size_bytes IS NOT NULL
    AND sha256 IS NOT NULL AND imported_at IS NOT NULL))
);
CREATE TABLE jobs (
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, recording_id TEXT NOT NULL,
  input_revision INTEGER NOT NULL CHECK(input_revision>0),
  kind TEXT NOT NULL CHECK(kind IN ('decode','transcribe')),
  state TEXT NOT NULL CHECK(state IN ('pending','running','retry_wait','succeeded','failed')),
  attempt INTEGER NOT NULL DEFAULT 0 CHECK(attempt BETWEEN 0 AND 4), run_after INTEGER NOT NULL,
  lease_token TEXT, lease_until INTEGER,
  input_json TEXT NOT NULL CHECK(json_valid(input_json)),
  -- 一个 decode 只产出 WAV，一个 transcribe 只产出 VTT；原文同时提交到 recordings。
  -- 文件索引与发布记录并入本行，路径按 job/attempt 生成，重试不覆盖旧文件。
  publication_state TEXT NOT NULL DEFAULT 'none' CHECK(publication_state IN ('none','prepared','ready','missing','abandoned')),
  tmp_relative_path TEXT UNIQUE, final_relative_path TEXT UNIQUE,
  size_bytes INTEGER CHECK(size_bytes>0), sha256 TEXT CHECK(length(sha256)=64),
  sample_count INTEGER CHECK(sample_count>=0),
  error_code TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  UNIQUE(recording_id,input_revision,kind), UNIQUE(id,recording_id,owner,input_revision),
  FOREIGN KEY(recording_id,owner) REFERENCES recordings(id,owner),
  CHECK(state<>'running' OR (lease_token IS NOT NULL AND lease_until IS NOT NULL)),
  CHECK(publication_state<>'prepared' OR (tmp_relative_path IS NOT NULL AND final_relative_path IS NOT NULL)),
  CHECK(publication_state<>'ready' OR (state='succeeded' AND final_relative_path IS NOT NULL
    AND size_bytes IS NOT NULL AND sha256 IS NOT NULL)),
  CHECK(state<>'succeeded' OR publication_state IN ('ready','missing'))
);
CREATE INDEX jobs_claim ON jobs(state,run_after,id);
CREATE UNIQUE INDEX jobs_single_running ON jobs((1)) WHERE state='running';
-- 用户/归属/版本由 FK 与 CHECK 约束；指针对应任务 kind、ready/hash 由发布和读取接口核验。
-- 迁移在同一事务内设置版本，不再建 schema_migrations 表。未知更高版本必须拒绝启动。
PRAGMA user_version=1;
COMMIT;
