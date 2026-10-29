-- 复用既有 registry 表：新增 0 张表。设计参考，真实迁移先检查 table_info。
-- 不删改旧 users/凭证/绑定/清理锁；旧 users 仅兼容 Bearer，不扩展为第二份 Google 资料。
PRAGMA foreign_keys=ON;
PRAGMA synchronous=FULL;
PRAGMA busy_timeout=5000;
BEGIN IMMEDIATE;
ALTER TABLE bindings ADD COLUMN display_name TEXT
  CHECK(display_name IS NULL OR length(display_name) BETWEEN 1 AND 100);
ALTER TABLE bindings ADD COLUMN name_updated_at INTEGER;
ALTER TABLE sources ADD COLUMN projected_at INTEGER;
CREATE INDEX sources_projection_pending ON sources(projected_at,created,id) WHERE state='ready';
COMMIT;
-- sources ready 行本身就是持久待投影项，不再另建 source_outbox。
-- 业务 segments/recordings 先提交，之后才标 projected_at；重放由 namespace/source_id 去重。
-- 启动时分批对账全部 ready 来源，不只相信 projected_at，确保备份恢复后可补投影。
-- 改名仅更新本人当前 bindings.display_name；不改 UID、凭证或历史 owner。
