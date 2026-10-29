# ReSpeaker Clip · Server / Web 开发设计

v1 · 2026-10-29

## 关键点

1. Web 和 Server 自研，使用同源 HTTPS API；Google OAuth 负责登录身份验证。
2. 用户资料存 SQLite，登录临时状态和本站会话存内存；Server 重启后重新登录。
3. 所有查询、更新、下载和后台处理都限定 owner，每个用户只处理自己的数据。
4. 业务库四张表；设备绑定和来源索引复用现有 registry。
5. Wi-Fi 列表由 Clip 扫描，通过 BLE 配置；Server 管理设备归属和上传凭证。
6. 音频、识别原文与 VTT 的存储和处理见[音频处理设计](docs/audio-processing.md)。

[架构](#architecture) · [对象与表](#data-model) · [OAuth](#oauth) · [Web API](#web-api) · [设备通信](#ble) · [SQL](#sql)

<a id="architecture"></a>

## 1. 架构

![部署架构](docs/assets/diagrams/01-system-architecture.svg)

Python / FastAPI 单进程，SQLite 保存业务数据，Web 使用原生 ES modules。后台顺序处理录音，来源去重、版本更新和发布结果使用 SQLite 短事务。

| 入口 | 用途 |
|---|---|
| HTTPS 9529 | Web、同源 `/api/boa/v1`、Google 回调 |
| HTTPS 9528 | 现有客户端接口 |
| UDP / DTLS 9528 | Clip 原件上传 |

<a id="data-model"></a>

## 2. 对象与数据表

| 对象 | 保存位置 | 关键字段与关系 |
|---|---|---|
| 用户 | accounts | user_id 为稳定身份，其他业务数据通过 owner 关联 |
| 设备绑定 | registry.bindings | device、owner、binding_id、epoch、active、display_name |
| 录音 | recordings | owner、来源、时间、版本、WAV/VTT 任务指针、转写 JSON |
| 原始片段 | recording_segments | 所属录音、来源唯一键、片段号、raw 路径、size/hash |
| 后台处理 | jobs | 所属录音和 owner、输入版本、decode/transcribe、状态、文件发布信息 |
| 登录会话 | Server 内存 | user_id、auth_version、CSRF token、创建和过期时间 |

### accounts 字段

| 字段 | 类型 | 约束 / 默认 | 含义 |
|---|---|---|---|
| user_id | TEXT | 主键 | 本地用户 ID，历史 ID 沿用；其他表通过 owner 引用。 |
| google_sub | TEXT | 唯一 | 验证通过的 Google 身份标识；待核验的历史用户可空。 |
| email | TEXT | 必填；唯一；大小写不敏感 | 用户邮箱；账号同步时检查身份冲突。 |
| display_name | TEXT | 必填；默认空字符串；≤100 字符 | 用户名称，可为空字符串。 |
| status | TEXT | 必填；默认 active | active / disabled；请求鉴权检查账号状态。 |
| auth_version | INTEGER | 必填；默认 1；>0 | 认证版本；变更后使旧会话失效。 |
| last_login_at | INTEGER | 可空 | 最近登录时间，可空。 |
| created_at | INTEGER | 必填 | 用户建立时间。 |
| updated_at | INTEGER | 必填 | 用户资料更新时间。 |

新用户 ID 使用 uuid4().hex，历史 user_id 原样迁移。google_sub 唯一；邮箱设置大小写不敏感的唯一约束。相同 sub 复用用户；邮箱与其他 sub 冲突时返回 account_identity_conflict，保留原归属。每次鉴权检查 status 和 auth_version。

| registry 数据 | 作用 |
|---|---|
| bindings.display_name / name_updated_at | 设备别名；更新时限定本人有效绑定 |
| binding_profiles.revision / confirmed_revision / cleanup_pending | 配置读回和解绑后的清理状态 |
| sources 及 projected_at | 原件身份与业务投影进度，详见音频文档 |

recordings、recording_segments、jobs 的[字段说明](docs/audio-processing.md#tables)集中在音频文档；完整 DDL 见[本页 SQL](#sql)。业务时间统一为 UTC Unix 毫秒，duration_ms 为时长，size_bytes 为字节数。

<a id="oauth"></a>

## 3. Google OAuth 与本站会话

### 3.1 我们提供的接口

以下路径统一加前缀 `/api/boa/v1`。

| 接口 | 调用方 / 请求 | 成功响应 |
|---|---|---|
| GET `/auth/google/start` | Web 顶层导航，无业务参数 | 302 跳转 Google；设置 5 分钟临时绑定 Cookie |
| GET `/auth/google/callback` | Google 经浏览器回跳；code、state，失败时 error、state | 校验后 303 到 `/`；设置本站会话 Cookie，清临时 Cookie |
| GET `/auth/session` | Web，携带本站 Cookie | 200：`{user:{user_id,email,display_name},csrf_token}` |
| DELETE `/auth/session` | Web，携带 Cookie、Origin、X-CSRF-Token | 204：删除内存会话并清 Cookie |

**Google Console 登记的回调地址：** `PUBLIC_WEB_ORIGIN + /api/boa/v1/auth/google/callback`。例如 `https://clip.example.com/api/boa/v1/auth/google/callback`；部署时替换为实际 HTTPS 域名。

### 3.2 授权参数与 code 交换

| 参数 | 值 |
|---|---|
| client_id | GOOGLE_CLIENT_ID |
| redirect_uri | 上方固定回调地址，授权与 token 请求使用相同值 |
| response_type / scope | code / openid email profile |
| access_type | online |
| state / nonce | 每次登录独立生成的随机值 |
| code_challenge | BASE64URL(SHA-256(code_verifier))，去掉末尾 `=` |
| code_challenge_method | S256 |

回调先核对 state、临时 Cookie 和 5 分钟有效期，再消费本次状态。Server 将 code、原始 code_verifier、client_id、client_secret、redirect_uri、grant_type=authorization_code 以 form-urlencoded 提交给 Google token 接口。

ID token 校验签名、Google issuer、audience、exp、nonce、sub 和 email_verified；多 audience 时校验 azp，回调包含 iss 时核对 Discovery issuer。验证通过后同步 accounts，建立新的本站会话。Google token 校验后释放引用。

| Google 接口 | 方法 / 地址 |
|---|---|
| Discovery | GET `https://accounts.google.com/.well-known/openid-configuration` |
| 授权 | GET `https://accounts.google.com/o/oauth2/v2/auth` |
| token | POST `https://oauth2.googleapis.com/token` |
| JWKS | GET `https://www.googleapis.com/oauth2/v3/certs` |

端点与 RS256 签名算法来自 [Google Discovery](https://accounts.google.com/.well-known/openid-configuration)，协议依据 [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect)。请求总超时 10 秒，公钥按缓存头缓存。

### 3.3 内存与 Cookie

| 数据 | 内容 / 生命周期 |
|---|---|
| LoginFlow | state 摘要、浏览器绑定摘要、nonce、code_verifier；5 分钟，一次消费 |
| Session | session token 摘要、user_id、auth_version、CSRF token、创建/最近访问时间；闲置 24 小时、最长 7 天 |
| 临时 Cookie | `__Host-boa_oauth`；Secure、HttpOnly、SameSite=Lax、Path=/、host-only、Max-Age=300 |
| 会话 Cookie | `__Host-boa_session`；Secure、HttpOnly、SameSite=Strict、Path=/、host-only、Max-Age=604800 |

随机值使用系统 CSPRNG；token 为 32 随机字节，敏感值使用恒定时间比较。state 和 session token 以 SHA-256 摘要索引，TTL 使用单调时钟。每 60 秒及访问时清理过期项，LoginFlow 上限 1000、Session 上限 10000；容量满返回 auth_capacity_exceeded。登录入口每 IP 每分钟最多 30 次，IP 取自可信连接/配置的代理。

登录成功设置新会话 Cookie，303 返回固定 `/`。授权取消且 state 有效时，清临时状态，303 返回 `/?login_error=login_cancelled`。其他失败按下表返回统一错误 body，并清理本次 LoginFlow。

| HTTP / code | 条件 | Web 处理 |
|---|---|---|
| 400 login_invalid_or_expired | state/绑定缺失、过期、重放、nonce/token 校验失败或 invalid_grant | 重新登录 |
| 401 session_expired | 会话缺失、到期、Server 重启或 auth_version 变化 | 清当前状态，重新登录 |
| 403 account_disabled / csrf_invalid | 账号禁用 / Origin 或 CSRF 校验失败 | 禁用时清会话，其余按错误提示处理 |
| 409 account_identity_conflict | Google sub 与既有邮箱映射冲突 | 提示维护核验 |
| 429 auth_rate_limited | 登录入口限流 | 等待后重试 |
| 503 login_not_configured / login_unavailable | 配置缺失或 invalid_client / Google 网络、5xx 或公钥获取失败 | 展示配置状态或重试 |
| 503 auth_capacity_exceeded | 内存容量已满 | 等待后重试 |

退出时校验 Origin/CSRF 后删除当前会话。已过期会话返回 401，Web 对 204/401 均清理音频、请求和当前账号数据，并广播退出事件。会话接口和回调设置 no-store；回调设置 Referrer-Policy: no-referrer。认证接口单独配置脱敏访问日志，仅记录 request_id、路由名、状态和错误码。

| 服务器配置 | 值 |
|---|---|
| GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET | Google Web application 凭证，服务器侧加载 |
| PUBLIC_WEB_ORIGIN | 实际 HTTPS origin；Google Console 回调与此配置完全一致 |

<a id="web-api"></a>

## 4. Web 前后端 API

路径前缀 `/api/boa/v1`。除登录入口、回调和 health，其余接口校验本站会话；写请求携带 Origin 与 X-CSRF-Token，owner 从会话取得。

| 接口 | 请求参数 | 成功响应 |
|---|---|---|
| GET `/devices` | 无 | 200：`{items:[设备对象]}` |
| POST `/devices/activate` | `{uid}`；Server 查询既有受控登记和本人归属 | 200：device_id、binding_id、epoch、revision、configuration；no-store |
| POST `/devices/{id}/binding/confirm` | `{device_uid,binding_id,revision,saved:true}` | 200：`{binding_id,revision,state:"provisioned"}` |
| PATCH `/devices/{id}` | `{name}`；1–100 字符 | 200：device_id、display_name |
| DELETE `/devices/{id}/binding` | 无 | 200：`{state:"revoked",device_cleanup_pending}` |
| GET `/recordings` | from、to、cursor、limit | 200：`{items:[录音对象],next_cursor}` |
| GET `/recordings/{id}` | id | 200：录音时间、完整性、时长、输入/音频/文字版本、处理状态及媒体链接 |
| GET `/health` | 无 | 200：服务状态与版本 |

**设备对象：** device_id、uid、binding_id、epoch、display_name、firmware、capabilities、telemetry。online/battery/pending 分别使用 `{value,sampled_at,source}`；来源缺失时 value=null。

**录音列表对象：** id、time_source、recorded_at、received_at、duration_ms、audio_state、transcript_state、preview_text。from/to 为 YYYY-MM-DD，默认时区 Asia/Shanghai；结束日含当天，按次日零点转换 UTC 半开区间。默认 30 条，上限 100，按有效录音时间/id 降序；筛选变化重置游标。

音频、JSON、VTT 和 Markdown 的接口、响应格式与版本规则见[音频接口](docs/audio-processing.md#media-api)。列表无结果返回 items=[]、next_cursor=null。

统一错误格式为 `{error:{code,message},request_id}`。常用状态：401 会话失效，403 权限/CSRF，404 不存在或跨 owner，409 状态冲突，422 参数校验，503 依赖不可用。前端按 error.code 处理。

<a id="ble"></a>

## 5. 设备与 Web 数据处理

| 处理项 | 规则 |
|---|---|
| 绑定 | 验证服务端登记与归属；本人重复激活复用绑定，其他 owner 拒绝；未登记到当前用户的 UID 返回 enrollment_required |
| 配置确认 | BLE 写入后读回 binding/epoch/revision，Server 按 device_uid、binding_id、revision、saved 校验 |
| 改名 | 更新本人 active binding 的 display_name；UID 和上传凭证保持原值 |
| 移除 | 撤销上传凭证；返回 device_cleanup_pending，清理确认沿用现有维护机制；已上传录音保留原 owner |
| Wi-Fi | Clip 扫描 `{ssid,rssi,security}[]`；选择扫描结果后经 BLE 写入 SSID/密码，读取 saved/connected/error |
| 设备能力 | 连接时读取真实 capability；已保存网络上限按固件容量、最多 5 个；无线基线 2.4 GHz WPA2 |
| 密码 | 仅在本次 BLE 调用保留引用，完成后清空 |
| 请求生命周期 | 取消旧请求，核对 generation；账号切换/退出时清理旧请求、音频和定时器 |
| 轮询 | 录音可见 5 秒、设备可见 15 秒；隐藏后 30 秒，恢复可见立即刷新 |

旧 user_id 沿用；迁移前核验 owner/邮箱映射，缺项返回 migration_owner_mapping_required。迁移与 PRAGMA user_version 更新同事务；registry 增量先检查现有字段，bindings/sources 使用显式列名 INSERT。

<a id="sql"></a>

## 6. 数据库 DDL

<a id="business-sql"></a>

### 6.1 业务库

```sql
-- 录音助手 v1：四张业务表初始 DDL。
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
-- 迁移与 PRAGMA user_version 更新同事务执行，未知更高版本返回启动错误。
PRAGMA user_version=1;
COMMIT;
```

<a id="registry-sql"></a>

### 6.2 registry 增量

```sql
-- 复用既有 registry 表：新增 0 张表。设计参考，真实迁移先检查 table_info。
-- users 保留 Bearer 凭证映射，bindings 保留设备归属和上传凭证。
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
-- sources ready 行作为持久待投影项。
-- 业务 segments/recordings 先提交，之后才标 projected_at；重放由 namespace/source_id 去重。
-- 启动时分批对账全部 ready 来源，不只相信 projected_at，确保备份恢复后可补投影。
-- 改名仅更新本人当前 bindings.display_name；保留原 UID、凭证和历史 owner。
```
