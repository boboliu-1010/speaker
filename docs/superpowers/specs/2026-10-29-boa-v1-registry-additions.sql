-- 录音助手 v1：既有 registry 的最小增量。不是生产迁移脚本。
-- sources 表由既有代码维护；删除/回收站不是新版原型功能，不建立相关屏障表。
PRAGMA foreign_keys=ON;
PRAGMA synchronous=FULL;
PRAGMA busy_timeout=5000;
BEGIN IMMEDIATE;
CREATE TABLE source_outbox (
  event_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL UNIQUE REFERENCES sources(id),
  sha256 TEXT NOT NULL CHECK(length(sha256)=64),
  created_at INTEGER NOT NULL, consumed_at INTEGER
);
CREATE INDEX source_outbox_pending ON source_outbox(consumed_at,created_at,event_id);
-- 完整 raw 持久并校验后，sources ready 更新与 outbox 插入须同库事务完成。
-- App 原上传索引采用相同完成通知/收据契约；不伪造 Clip binding。
COMMIT;
