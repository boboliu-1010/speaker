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
    google_sub    TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name  TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active', 'disabled')),
    auth_version  INTEGER NOT NULL DEFAULT 1 CHECK (auth_version > 0),
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL
);

CREATE TABLE devices (
    id                 TEXT PRIMARY KEY NOT NULL,     -- 硬件UID，API中的device_id/device_uid
    owner              TEXT REFERENCES accounts(user_id),
    display_name       TEXT NOT NULL DEFAULT '',
    state              TEXT NOT NULL DEFAULT 'bound'
                       CHECK (state IN ('bound', 'revoked')),
    token_hash         TEXT UNIQUE CHECK (token_hash IS NULL OR length(token_hash) = 64),
    token_material_ref TEXT,                          -- 当前token私有配置文件的相对引用
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL,
    CHECK (
        (state = 'bound' AND owner IS NOT NULL AND token_hash IS NOT NULL AND token_material_ref IS NOT NULL)
        OR
        (state = 'revoked' AND owner IS NULL AND token_hash IS NULL AND token_material_ref IS NULL)
    )
);

CREATE INDEX devices_owner ON devices(owner, id);

COMMIT;
```

## 字段约定

- 时间为UTC毫秒；auth_version用于使旧登录会话失效。
- id直接使用硬件UID，不重复保存device_uid列；Server在同一事务内核对当前owner，拒绝覆盖其他用户。
- 首次绑定自动建档为bound；本人重复激活复用当前token。bound只表示Server归属有效，不表示设备已配置或在线。
- 解绑先撤销授权，清空owner、token_hash及token_material_ref并标记revoked；旧token及已有上传连接不能继续提交文件。
- 重新绑定复用设备ID，但生成新随机token。token_hash为token的SHA-256十六进制；当前配置仅保存在credentials/devices/私有文件中，供本人重试，不存数据库明文；读取配置时核对hash，不一致则拒绝返回。
- 历史录音owner保留在文件中；转交前由用户上传完旧录音或明确确认删除，避免新token上传旧录音。

初始化、迁移由Web本机维护入口执行；连接时设置上述PRAGMA，业务使用参数化SQL。
