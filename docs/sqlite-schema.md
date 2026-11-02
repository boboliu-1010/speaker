# SQLite 表结构

数据库位于`${SPEAKER_DATA_ROOT}/db/business.sqlite3`，仅Web Server访问。只有用户、设备两张表；录音及job使用文件，会话保存在Web内存。

## 建表SQL

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 5000;

BEGIN IMMEDIATE;

CREATE TABLE accounts (
    user_id       TEXT PRIMARY KEY NOT NULL,
    google_sub    TEXT NOT NULL UNIQUE,                -- Google用户标识
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name  TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active', 'disabled')),
    auth_version  INTEGER NOT NULL DEFAULT 1 CHECK (auth_version > 0),
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL
);

CREATE TABLE devices (
    id                        TEXT PRIMARY KEY NOT NULL, -- API中的device_id
    device_uid                TEXT NOT NULL UNIQUE,      -- 硬件UID
    owner                     TEXT REFERENCES accounts(user_id), -- 解绑后为NULL
    display_name              TEXT NOT NULL DEFAULT '',
    binding_id                TEXT UNIQUE,
    epoch                     INTEGER NOT NULL DEFAULT 0 CHECK (epoch >= 0),
    revision                  INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    confirmed_revision        INTEGER NOT NULL DEFAULT 0
                              CHECK (confirmed_revision >= 0 AND confirmed_revision <= revision),
    state                     TEXT NOT NULL DEFAULT 'provisioning'
                              CHECK (state IN ('provisioning', 'provisioned', 'revoked')),
    verification_material_ref TEXT,                       -- 上传凭证材料的相对引用，不存明文token
    device_cleanup_pending    INTEGER NOT NULL DEFAULT 0
                              CHECK (device_cleanup_pending IN (0, 1)),
    created_at                INTEGER NOT NULL,
    updated_at                INTEGER NOT NULL,
    CHECK (state NOT IN ('provisioning', 'provisioned') OR
        (owner IS NOT NULL AND binding_id IS NOT NULL AND epoch > 0 AND revision > 0
         AND verification_material_ref IS NOT NULL)),
    CHECK (state != 'provisioned' OR confirmed_revision = revision),
    CHECK (state != 'revoked' OR owner IS NULL)
);

CREATE INDEX devices_owner ON devices(owner, id);

COMMIT;
```

## 字段约定

- 时间均为UTC毫秒；`auth_version`用于使旧会话失效。
- 校验设备持有证明后自动建档为`provisioning`，蓝牙确认后为`provisioned`；不预登记，也不新增绑定或挑战表。挑战只保存在Web内存。
- `owner`是当前用户；解绑时撤销授权、设为NULL并进入`revoked`。`device_cleanup_pending`表示设备端仍待蓝牙清理；原用户解绑且设备清理完成后才允许新用户绑定。
- `binding_id`、`epoch`标识绑定及代次；`revision`为配置版本，`confirmed_revision`为蓝牙读回确认的版本。
- 有效绑定的本人重复激活复用原行及绑定；解绑后重新认领复用设备ID，生成新binding_id，递增epoch/revision，重置confirmed_revision及清理标记。历史录音归属不变；领取归属须在同一事务内检查，不能覆盖其他用户。
- 凭证引用由服务端生成，限定在`credentials/devices/`内；不保存设备运行状态或遥测。

连接数据库时设置上述PRAGMA，业务读写使用参数化SQL；初始化、迁移由Web本机维护入口执行。
