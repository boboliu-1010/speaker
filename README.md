# ReSpeaker Clip · Server / Web 开发设计

版本：v1 · 2026-10-29 · 状态：待实施

代码仓库：[BofAI/reSpeaker_Clip](https://github.com/BofAI/reSpeaker_Clip)。技术栈：Python / FastAPI、SQLite、原生 ES modules、Web Bluetooth、DTLS v3。

<a id="contents"></a>

[架构](#system-architecture) · [模块接口](#modules) · [表结构与 SQL](#sqlite-model) · [认证](#google-login) · [设备与 BLE](#devices) · [收件投影](#ingest) · [任务与发布](#dual-write) · [音频](#recording-decode) · [转写](#transcript-format) · [HTTP / Web](#web) · [开发任务](#implementation) · [部署与验收](#operations)

<a id="system-architecture"></a>

## 1. 运行架构

![部署与模块](docs/assets/diagrams/01-system-architecture.svg)

| 运行单元 | 入口 / 资源 | 职责 |
|---|---|---|
| FastAPI 常驻进程 | HTTPS 9529、HTTPS 9528、UDP/DTLS 9528 | 静态资源、鉴权 API、设备收件、任务调度 |
| 解码子进程 | 冻结的 raw 清单、临时输出路径 | 有界资源下生成 WAV |
| 私有 ASR | 已发布且版本固定的 WAV | 返回时间戳、speaker 与识别原文 |
| Google | OAuth 2.0 / OIDC | 验证登录身份 |
| 本机持久卷 | product.sqlite3、registry.sqlite3、音频目录 | 保存归属、原件、转写、任务和发布状态 |

浏览器访问 9529 的同源 `/api/boa/v1`。9528 HTTPS 兼容现有客户端；9528 UDP 承载设备上传。服务持数据目录排他锁，以一个 Uvicorn worker 启动。

### 1.1 线程、连接与锁

- HTTP handler 负责鉴权、参数校验和调用模块；SQLite 阻塞访问和媒体文件 I/O 放工作线程。
- 设备接收线程只负责协议、原件持久化和来源索引；decode/transcribe 由后台调度器执行。
- 每个线程在自身作用域创建、使用并关闭 SQLite connection；启用 FK、WAL、5 秒 busy timeout 和 synchronous=FULL。
- 按 recording_id 持录音锁，覆盖输入快照复核和最终发布。解码、ASR 网络请求在录音锁和数据库事务之外执行。
- 文件 rename/fsync 与数据库事务分步完成，jobs 保存恢复信息；registry 与业务库之间的写入通过来源幂等和启动对账恢复。

### 1.2 数据目录

```text
<data-root>/
  registry.sqlite3
  product.sqlite3
  clip/<binding_id>/<object_id>.bin
  clip/<binding_id>/<object_id>.partial
  clip/<binding_id>/<object_id>.checkpoint
  derived/<recording_id>/<revision>/<job_id>/<attempt>/audio.wav
  derived/<recording_id>/<revision>/<job_id>/<attempt>/transcript.vtt
  .staging/<job_id>/<attempt>/...
```

`clip/` 复用现有 ResumeStore。原件路径由 Registry.raw_path(source) 解析，业务库保存相对路径。App 来源继续通过其现有存储适配器接入。派生路径由服务端 ID 构造；发布前检查 resolve 后仍处于 data-root，临时目录与最终目录位于同一文件系统。

<a id="modules"></a>

## 2. 代码组织与模块接口

```text
server/boa/product/
  contracts.py       公共类型与 ProductContext
  db.py              连接、迁移和 user_version
  auth.py            Google 回调、内存会话、鉴权
  users.py           google_sub 与稳定 user_id 映射
  devices.py         registry 绑定与凭证适配
  recordings.py      来源投影、查询、版本快照
  jobs.py            去重、领取、续租、重试
  files.py           路径校验、fsync、发布、恢复
  decode.py          Opus 解包、解码与 WAV 校验
  transcript.py      ASR adapter、JSON、VTT、Markdown
  routes.py          /api/boa/v1 路由
  migrations/        顺序 SQL 迁移
server/web/product/
  app.mjs            初始化、会话和模块装配
  api.mjs            同源请求、CSRF、错误和取消
  devices.mjs        BLE 生命周期、设备接口适配
  recordings.mjs     日期参数、列表游标、轮询
  detail.mjs         revision、媒体请求、文字分页与导出
```

### 2.1 公共类型

| 类型 | 字段 |
|---|---|
| Actor | user_id: str、auth_version: int |
| SourceEvent | owner、source_kind、source_namespace、source_id、binding_epoch、source_session、segment_no、raw_relative_path、size_bytes、sha256、created_at_ms |
| InputSnapshot | recording_id、owner、revision、sources: tuple[SourceEvent, ...] |
| Lease | job_id、recording_id、revision、lease_token、lease_until |
| Cue | cue_index: int、start_ms: int、end_ms: int、speaker: str 或 None、text: str |

`SourceEvent` 的 ID/路径/hash 为字符串，epoch/segment/size/time 为整数；source_kind 为 clip_direct 或 app_upload。`Lease.revision` 对应 jobs.input_revision，lease_until 使用 UTC Unix 毫秒。时间戳与字节数在接入适配器中转换后再进入业务模块。新建 user_id、recording_id、segment_id、job_id 使用 uuid4().hex，历史 user_id 原样迁移；32 字符用户 ID 与既有 registry 标识规则兼容。

`ProductContext` 持有 root、Registry、BusinessDB、clock_ms、monotonic_ms、进程锁和录音锁集合。clock_ms 提供持久时间，monotonic_ms 用于内存 TTL。owner 由 Actor 或已验证的来源归属取得。所有服务接口共享这些类型。

### 2.2 主要调用接口

| 模块 | 接口 |
|---|---|
| users | sync_verified_user(sub, email, name) -> user_id |
| auth | principal(request) -> Actor；logout(request) |
| devices | activate(actor, uid, evidence)；rename(actor, device_id, name)；remove(actor, device_id) |
| recordings | import_ready(ctx, event) -> recording_id；snapshot(actor, id) -> InputSnapshot |
| jobs | enqueue(snapshot, kind) -> job_id；claim(now_ms) -> Lease 或 None |
| files | publish(lease, tmp, metadata) -> final_path；recover(ctx) -> count |
| decode | decode(snapshot, output) -> size/hash/sample_count |
| transcript | ASR.transcribe(wav, request_id) -> list[Cue]；publish_transcript(lease, cues) |

<a id="sqlite-model"></a>
<a id="sql"></a>

## 3. SQLite 表结构与迁移

![四表关系](docs/assets/diagrams/02-user-data-model.svg)

| 表 | 一条记录承载什么 |
|---|---|
| accounts | 用户资料、Google sub、账号状态与认证版本 |
| recordings | 录音状态、版本、当前文件任务指针、完整转写 JSON |
| recording_segments | 原始片段 + raw 路径/size/hash + 幂等来源收据 |
| jobs | decode/transcribe 任务 + 派生文件元数据 + 发布/恢复状态 |

registry.bindings 保存设备别名与绑定，registry.sources 保存来源和投影进度；业务库负责用户、录音、原始片段和处理任务。迁移版本通过 PRAGMA user_version 管理。

用户与录音为一对多，录音与原始片段、处理任务分别为一对多。文字保存为录音行中的版本化 JSON，最大 8 MiB UTF-8、100000 cues、每句 10000 字符。超限返回明确错误。API 按 200 cues 分页，使用 SQLite json_each 在读取快照中取页；导出按句读取。

recordings 的 wav_job_id/vtt_job_id 用 owner/录音/版本复合 FK 指向 jobs；文件发布与文件读取同时验证 job.kind、state/publication_state、size/hash；文字 API 独立读取录音当前 JSON，VTT 缺失时仍可读取已存文字。原件来源唯一约束负责幂等，条件更新 receiving→ready 与 input_revision 递增同事务。每次启动对账全部 registry ready 来源，分批 500 条异步执行，由后台对账线程执行。

迁移脚本保存在 Git，业务库通过 PRAGMA user_version 顺序升级并拒绝未知高版本；实施中同时把既有 registry.py 的 bindings/sources 位置式 INSERT 改为显式列名，防止 ALTER ADD COLUMN 后旧写入因列数变化失败；加入真实旧 schema 升级夹具。registry 增量先检查既有列，沿用其迁移所有权。每连接 foreign_keys=ON、busy_timeout=5000、synchronous=FULL；业务库 WAL。音频保存为磁盘文件。登录事务/会话仍只在内存。

<a id="business-sql"></a>

### 3.1 业务库 DDL

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

### 3.2 registry 增量 DDL

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

### 3.3 迁移与数据约束

1. 预检旧 owner 到邮箱的核验清单；旧 registry.users 只有 ID/凭证时，由维护侧补齐邮箱映射。缺少映射返回 migration_owner_mapping_required，补齐后继续。
2. 取得维护锁，读取业务库 PRAGMA user_version；未知高版本返回错误。
3. 在一个事务内执行当前版本迁移并更新 user_version；失败回滚，重跑从已提交版本继续。
4. registry 迁移先检查 table_info；已有字段跳过，新增字段与索引按现有迁移顺序执行。
5. 将 bindings/sources 的位置式 INSERT 改成显式列名；用旧 schema 和旧数据夹具验证新增列后的写入。
6. 验证外键、integrity_check、旧 user_id/绑定与原件数量、路径、size/hash。

复合 FK 保证当前 WAV/VTT 任务属于相同录音、owner 和版本。发布与读取接口再校验 kind、state、publication_state 和文件元数据。transcript_json 的字段与时间戳由 ASR 校验器验证，外层 JSON、字节上限和 ready 条件由 CHECK 约束。

<a id="user-model"></a>
<a id="google-login"></a>

## 4. Google 登录与内存会话

![登录存储](docs/assets/diagrams/09-google-memory-login.svg)

`accounts` 保留 9 个字段：`user_id`、`google_sub`、`email`、`display_name`、`status`、`auth_version`、`last_login_at`、`created_at`、`updated_at`。内部 user_id 关联所有 owner，既有用户沿用旧 ID；google_sub 唯一，旧用户迁移未核验时允许为空。邮箱设置唯一约束，身份匹配以 google_sub 为准。

状态只有 active/disabled。登录使用 Google OAuth 2.0 Authorization Code + OpenID Connect；登录临时数据和会话保存在进程内存。每个请求重新核对 accounts.status/auth_version；已有 Bearer 兼容身份也执行相同的状态检查。

内存保存一次性登录状态（5 分钟）和本站会话（闲置 24 小时、绝对 7 天）；随机 opaque Cookie 引用服务端会话。退出即删除，Server 重启全部失效、用户重新登录，设备上传凭证与后台任务不受影响。登录跳转的临时 Cookie 使用 Secure/HttpOnly/SameSite=Lax，本站会话使用 Secure/HttpOnly/SameSite=Strict，均为 host-only、Path=/。容量、清理和回调重放处理见下方参数。

所有读取按服务端身份过滤 owner，跨用户对象统一 404；写请求校验准确 Origin 与会话 CSRF。首次登录建立普通账号；维护操作沿用现有受控权限。

| SQLite | 内存 | 浏览器 |
|---|---|---|
| accounts、设备归属、录音、原文、任务 | 一次性 LoginFlow、Session、Google 公钥缓存 | HttpOnly Cookie；页面临时 CSRF token |
| 重启保留 | 退出/到期/重启清除 | 会话失效后重新 Google 登录 |

### 4.1 Google 接入

1. 配置 Google Web application client、同意屏幕和精确的 HTTPS 回调 URI。申请 `openid email profile`，采用在线登录模式。Client secret 由服务器环境变量或私密配置加载。
2. `GET /api/boa/v1/auth/google/start` 创建高熵 state、nonce、浏览器绑定值和 S256 PKCE verifier；LoginFlow 放有界内存 map。设置 5 分钟临时 `__Host-boa_oauth` Cookie，然后 302 跳 Google。使用 Authlib 处理授权码流程，启用 S256 PKCE，并将 LoginFlow 存储适配到服务端内存。
3. 回调是 `GET /api/boa/v1/auth/google/callback?code=&state=`。先匹配未过期 state 与临时 Cookie 的摘要，再原子取走 LoginFlow，随后交换 code。重复回调或 nonce/签名验证失败时，清理本次流程并要求重新登录。Google 拒绝授权时清理匹配的流程并回登录页。
4. 通过标准 Google ID token 验证库校验签名、Google issuer、本站 client_id/audience、到期时间，再比较 nonce；多 audience 时校验 azp，要求有效 sub、email 和 `email_verified=true`。身份字段取自验证通过的 ID token。公钥允许按缓存头有界缓存；网络/密钥服务不可用时拒绝本次新登录。后续请求使用本站会话鉴权。
5. 按 google_sub 同步 accounts，沿用稳定 user_id。首次登录建立用户；相同 sub 复用；同邮箱不同 sub 或邮箱更新撞已有账号时返回 `409 account_identity_conflict`，保留现有账号归属并终止本次登录。旧 sub 为空的用户只能经维护侧核实映射。禁用账号返回 403。
6. 生成新的本站随机 session token 和 CSRF token，内存登记后设置会话 Cookie，清临时 Cookie，303 到固定 `/`。登录完成后固定返回首页。Google access/id token 在校验结束后释放引用；日志和错误响应仅保留错误码与请求 ID。
7. 静态首页加载后通过同源 `GET /auth/session` 取得基本资料和 CSRF token；响应 `Cache-Control: no-store`。会话 Cookie 设置 HttpOnly；CSRF token 只保存在页面内存。退出 `DELETE /auth/session` 校验 Origin/CSRF 后删会话、清 Cookie，并通知其他标签停止播放/请求。退出操作清理本站会话，设备继续使用独立上传凭证。

### 4.2 内存结构与过期处理

| map | 键 | 值 | 生命周期 |
|---|---|---|---|
| login_flows | SHA-256(state) | binding_digest、nonce、pkce_verifier、expires_at | 5 分钟；原子消费 |
| sessions | SHA-256(随机 32 字节 token) | user_id、auth_version、csrf_token、created_at、last_seen_at | 闲置 24 小时、绝对 7 天 |

随机值使用系统 CSPRNG，比较敏感值用恒定时间。TTL 用可注入单调时钟，按实际经过时间计算过期；持久业务时间仍为 UTC Unix 毫秒。每次有效会话请求更新 last_seen，轮询也算活动；绝对有效期固定为 7 天。会话 Cookie 固定 Max-Age=604800，轮询仅更新服务端闲置时间。

- 临时 Cookie：`__Host-boa_oauth`，Secure / HttpOnly / SameSite=Lax / Path=/，无 Domain。Google 顶层 GET 跳回时可发送。
- 会话 Cookie：`__Host-boa_session`，Secure / HttpOnly / SameSite=Strict / Path=/，无 Domain。登录成功始终换新 token。
- 每浏览器同时一个登录流程；再次发起覆盖临时 Cookie，旧流程回调安全失败，过期清理；页面可重新发起。各浏览器独立保存登录绑定。
- 每 60 秒及 map 操作时删除过期项；LoginFlow 最多 1000，Session 最多 10000。满额先清过期项，仍满则 503 `auth_capacity_exceeded`，已有会话继续有效。start 每 IP 每分钟最多 30 次，超过 429；IP 来自可信连接/显式受信代理。
- Google 请求总超时 10 秒；code 交换失败后重新发起授权，返回可重新发起的登录错误。state/绑定/nonce/token 无效为 400 `login_invalid_or_expired`，Google 取消为 `login_cancelled`，端点不可达为 503 `login_unavailable`。错误响应使用固定错误码。
- `/auth/session` 会话缺失或到期为 401；每次鉴权重新查 accounts.status/auth_version，禁用返回 403 并删会话，auth_version 不匹配返回 401。写操作要求同源 Origin + `X-CSRF-Token`；业务 GET 接口用于读取；登录 start/callback 更新临时认证状态。对登录路由关闭 query/body/Cookie 的访问日志和代理追踪，回调无第三方资源，使用 `Referrer-Policy: no-referrer` 与 no-store。
- 服务单进程且持数据目录锁；多 worker 启动拒绝。重启丢会话是预期行为。设备 DTLS 凭证、jobs、来源索引和录音使用独立生命周期。

配置项：`GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`PUBLIC_WEB_ORIGIN`（精确 HTTPS origin）、由 origin 和固定路径导出的回调 URI。Google Console 登记值必须完全相同；配置缺失时接口返回 503 `login_not_configured`，Web 显示待配置状态。

官方依据：[Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)、[Web Server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)。会话 TTL 和容量按本节配置执行。

<a id="devices"></a>

## 5. 设备绑定与 BLE 适配

![BLE 与服务端职责](docs/assets/diagrams/08-wifi-configuration.svg)

### 5.1 服务端绑定

`activate(actor, uid, evidence)` 复用现有受控登记与上传凭证发放能力。evidence 是登记适配器可验证的证明，具体编码沿用已有机制。仅有 UID 时返回 enrollment_required。请求处理顺序：

1. 验证 Actor 和设备登记依据，读取当前绑定。
2. 相同 owner 且绑定有效时返回已有 binding/epoch/configuration；其他 owner 的有效绑定返回 device_owned_by_other。
3. 首次绑定按现有 registry 事务建立归属并生成上传配置；响应设置 Cache-Control: no-store。
4. Web 经 BLE 写入配置、读取 binding/epoch/revision，调用 binding/confirm。
5. Server 核对提交值与发放配置；真实上传由 receiver 的收件记录确认。

别名写 registry.bindings.display_name，WHERE 同时校验 id、owner 和 active。移除首先在 registry 事务撤销上传凭证，再执行在线设备配置清理；离线设备保留 cleanup_pending 与现有交接锁。历史 sources/recordings 的 owner 保持原值。

### 5.2 BLE adapter 接口

以下为 Web 内部接口，底层命令、UUID 与编码映射到真实固件协议。

```typescript
interface ClipAdapter {
  connect(): Promise<void>;
  readIdentity(): Promise<{ uid: string; firmware: string }>;
  capabilities(): Promise<{ wifiScan: boolean; wifiCapacity: number }>;
  writeUploadConfiguration(configuration: unknown): Promise<void>;
  readUploadConfiguration(): Promise<{ binding: string; epoch: number; revision: number }>;
  setTime(utcMs: number): Promise<void>;
  scanWifi(): Promise<Array<{ ssid: string; rssi: number; security: string }>>;
  saveWifi(selectedSsid: string, password: string): Promise<void>;
  listWifi(): Promise<Array<{ ssid: string; connected: boolean }>>;
  readWifiStatus(): Promise<{ ssid?: string; saved: boolean; connected: boolean; error?: string }>;
  deleteWifi(ssid: string): Promise<void>;
  disconnect(): Promise<void>;
}
```

同一 BLE 连接串行执行命令。连接建立后读取完整 UID 与 capability，连接断开时递增连接 generation 并丢弃旧操作结果。固件不支持的调用返回 unsupported，接口与实机测试分别记录。

### 5.3 Wi-Fi 配置实现

- `scanWifi()` 由目标 Clip 扫描，返回 SSID、信号强度和安全类型。适配器保存当前连接 generation 对应的扫描结果。
- `saveWifi()` 只接受本次结果中选择的 SSID，按原始值传递；连接变化或扫描结果失效时重新扫描。
- SSID/密码经 BLE 写入 Clip。密码仅在本次调用内保留，finally 中清空页面引用；凭证日志只记录阶段和错误码。
- `readWifiStatus()` 分别返回保存状态、实际连接状态与错误原因；扫描超时重试，密码错误重新输入。
- 网络容量以 capability 为准，上限 5 个；无线基线为 2.4 GHz WPA2。保存网络查询/删除复用现有固件能力。
- 在线、电量、待上传数同时返回采样时间和来源；来源缺失时状态为 unknown。最近收件时间单独表示。

<a id="ingest"></a>

## 6. 原件接收与来源投影

![收件持久化](docs/assets/diagrams/04-raw-ingest-outbox.svg)

保持 v3 原协议：数据 fsync → 持久检查点 → 整文件 size/hash 校验 → rename/目录 fsync。只有 raw 和可恢复归属的身份元数据持久后才回 COMPLETE，WAV、ASR 和 VTT 由后台独立处理。设备凭证撤销后拒绝上传；旧绑定的历史文件仍属原用户。

既有 registry 的 `sources` ready 行就是持久待投影项，通过 projected_at 记录投影进度。消费者在 business 单事务建立/更新 recording 与 recording_segments；同一片段行保存 raw 路径/size/hash，并以唯一 `(source_namespace,source_id)` 兼作来源收据。业务事务成功后才标 projected_at。文件已落盘但索引失败，可从既有 identity/raw 对账；业务已提交但未标记时重放，ready→ready 且 hash 相同时保留当前版本，hash 冲突拒绝。启动分批核对全部 ready 来源。

录音按 `(source_kind, source_namespace, binding_epoch, source_session)` 聚合；新 ready 片段才递增 input_revision，重复 source 保持当前版本。App 上传继续通过现有接口接入。可定期读取已有 receiving 索引创建上传中的录音元信息，片段收完整并校验后标记 ready、创建处理任务。

接收期间显示“已收到 N 个片段/完整性未知”。片段连续且静默 10 分钟后，处理当前已收内容；缺号时等待补齐。后续片段到达后递增输入版本并更新 WAV 与转写。整段完整性依据设备协议提供的闭合信息判断。

### 6.1 投影事务

registry.sources.created 的秒值在适配器转换为 UTC 毫秒。绑定 epoch、owner、source_id 和 raw 路径从已验证的来源行取得。

1. 在录音锁内定位聚合键，必要时创建 recordings。
2. business 开启 BEGIN IMMEDIATE，按 namespace/source_id 查询 recording_segments。
3. 已 ready 且 hash/size 相同则幂等返回；hash/size 冲突返回 source_identity_conflict。
4. 首次 receiving→ready 时，在同一事务保存 raw 路径、size/hash、imported_at，并将 recordings.input_revision 加 1。
5. 提交 business 后，在 registry 更新 projected_at。任务由冻结的已提交版本创建。
6. 投影前再次验证 raw 文件存在和 hash/size；启动按每批 500 条对账全部 ready 来源，恢复缺失投影。

receiving 可以先建立上传中元信息，raw_relative_path/size/hash/imported_at 在校验完成后一起变为可用。原件缺失或身份冲突保留错误与原始来源记录，交由维护恢复。

<a id="dual-write"></a>

## 7. 持久任务、租约与文件发布

![发布状态](docs/assets/diagrams/06-file-database-publication.svg)

只需 decode、transcribe 两类持久任务；VTT 随 transcribe 生成，Markdown 下载即时生成，由同组转写 JSON 生成。

| 步骤 | 操作 | 可见性 |
|---|---|---|
| 1 | jobs 一行保存输入快照、lease、临时/最终路径与 publication_state=prepared | 不可下载 |
| 2 | 事务外写临时文件，检查 size/hash，flush/fsync | 不可下载 |
| 3 | jobs 记录预期 size/hash；持录音锁检查当前 input_revision 和 lease | 不可下载 |
| 4 | 同文件系统独占 rename，相关目录 fsync | 文件存在仍不算 ready |
| 5 | DB 再检查 fence，同事务提交 jobs 成功/文件 ready、录音指针和下一阶段状态 | 当前用户可读 |

文件和数据库分步提交，恢复状态保存在 jobs。WAV rename 后 DB 提交前崩溃，重启任务用新 lease 校验文件后补提交；VTT 同时依赖 cues，若 cues 事务未提交则重跑 ASR 并重新整体发布。输入已过期则放弃本次发布。jobs 对应文件缺失则标 publication_state=missing：WAV 由 raw 重建，VTT 优先由已提交的同版本 cues 重建；原件缺失单独告警。同路径 hash 冲突时报错并保留已有文件。

每个 decode 任务只发布一份 WAV，每个 transcribe 任务只发布一份 VTT，文件 MIME 由 kind 派生。原件元数据由 recording_segments 保存。

任务 input_json 冻结原件清单和媒体/ASR 配置版本，transcribe 还固定所消费的 wav_job_id 与 WAV hash；运行环境不匹配时暂停任务并报告配置差异。需因配置变化重做时由维护流程建立新输入修订，新的修订号对应新的时间轴。

单个活动任务，60 秒 lease、15 秒续期；瞬时错误最多重试 3 次，间隔 30 秒/2 分钟/10 分钟。解码超时 10 分钟、ASR 最长 60 分钟作为可配置初值。启动先恢复来源索引/事件，再恢复文件发布和过期任务；API/接收线程不等待模型执行。

### 7.1 领取与续租

`enqueue()` 以 `(recording_id,input_revision,kind)` 幂等创建任务。领取使用 BEGIN IMMEDIATE：先恢复过期 lease，再按 run_after/id 选择可运行任务，写入新的随机 lease_token、lease_until=now+60000 和 attempt+1 后提交。jobs_single_running 索引限制一个 running。

续租每 15 秒执行条件更新：id、state=running、lease_token 相同且租约仍有效，更新 lease_until。更新行数为 0 时停止本次执行并放弃发布。新输入到达后，尚未执行的旧版本任务标记 input_superseded；已执行任务在发布前通过版本和 lease 条件退出。

| 结果 | jobs.state | 调度处理 |
|---|---|---|
| 待执行 | pending | 到 run_after 后领取 |
| 已领取 | running | 续租，受超时控制 |
| 瞬时错误 | retry_wait | 30 秒 / 2 分钟 / 10 分钟重试 |
| 成功 | succeeded | 文件与录音指针已提交 |
| 永久错误或重试用尽 | failed | 保存固定 error_code，供维护重试 |

attempt 最大 4，表示首次执行加 3 次重试。领取重做任务时要求 attempt<4。恢复阶段仅核验已落盘文件并补提交时，重新分配 lease_token，保留 attempt；需要重新解码或重新识别时才增加 attempt，达到上限后标 failed。解码超时结束子进程组，ASR 超时取消请求；输出路径包含 attempt，旧执行结果以 lease_token 和输入版本隔离。

### 7.2 发布提交条件

最终短事务同时核对 recording.input_revision、job.input_revision、lease_token、lease_until 和 job.kind。WAV 发布提交 jobs ready/succeeded、wav_job_id、audio_revision、duration_ms；新音频版本替换时将不匹配的文字状态置 pending。转写发布提交 transcript_json、vtt_job_id、transcript_revision、transcript_state 与 jobs ready/succeeded。

文件下载先在同一读取快照内验证这些关系，再打开不可变 final_relative_path。文件读取引用和任务输入引用释放后，旧派生文件可清理；raw 持续保存。

<a id="recording-decode"></a>

## 8. raw 解码与 WAV 访问

![文件与编解码](docs/assets/diagrams/05-decode-and-retain.svg)

- Clip raw 格式为 `uint16 little-endian length + raw Opus packet`；先检查包边界/时长/声道，再正确封装或用受控解码器处理。
- 校验 raw hash 后解码为 **16 kHz、mono、PCM16 little-endian WAV**。逐段临时解码，再按冻结片段顺序合为一份 `recording.wav`，记录样本数、长度和独立 hash。
- 已发布 WAV 同时用于播放、ASR 和下载。临时分段文件成功后清理；原始文件始终保留。
- 内部存储路径按 raw 来源或 job/attempt 与输入版本确定；当前播放与更新使用独立路径。当前指针只指向 jobs 中 ready 的文件；旧派生文件在任务与读取释放引用后清理，raw 持续保留。
- Ogg granule 的 48 kHz 时基与 PCM 16 kHz 区分；raw 没有 pre-skip 元数据时保留当前样本策略并标明时间来源。样本数与时间轴保持一致，解码错误返回具体原因。

单 raw 段遵守既有 8 MiB 上限，连续录音处理默认上限 8 小时。16 kHz mono PCM16 约 115.2 MB/小时，先检查磁盘预算与工具超时；超限留 raw 并给出可恢复失败。

### 8.1 解码输入校验

逐包读取 2 字节 little-endian 长度和对应 Opus payload，检查截断、长度越界、配置的采样率/声道 profile 与来源 hash。按冻结清单的 segment_no 顺序处理；从片段 1 开始连续后才合成时间轴。解码结果以 sample_count / 16000 计算时长，和 WAV 数据长度相互验证。

运行环境记录 decoder 版本、raw profile、输出参数及 ASR 配置版本。估算磁盘空间包含 raw、临时 PCM/WAV、当前 WAV 与待发布文件。失败保留 raw，并保存 packet_invalid、segment_gap、decode_timeout、disk_full 等固定错误码。

### 8.2 HTTP Range

1. 每个 GET/HEAD 先检查会话、owner、revision、job.kind=decode、publication_state=ready 和文件存在性。
2. 普通 GET 返回 200；单一合法 bytes 范围返回 206，设置 Accept-Ranges、Content-Range 和实际 Content-Length。
3. `bytes=start-end`、`bytes=start-`、`bytes=-suffix` 统一换算为闭区间；end 取 min(请求 end,size-1)，省略 end 时取 size-1；suffix>0 时 start=max(0,size-suffix)。start>=size、start>end 或零长度 suffix 返回 416 与 `Content-Range: bytes */<size>`。
4. 多范围请求按普通 GET 返回整文件 200。HEAD 返回 200、资源头和空 body，并忽略 Range。
5. WAV 使用 audio/wav，ETag 取内容 SHA-256，私有资源设置 Cache-Control: private, no-store。退出后新的媒体请求重新鉴权。

以 1000 字节文件为例：

| 请求 | 状态 | Content-Range / Content-Length |
|---|---|---|
| GET，bytes=0-99 | 206 | bytes 0-99/1000；100 |
| GET，bytes=900-2000 | 206 | bytes 900-999/1000；100 |
| GET，bytes=-200 | 206 | bytes 800-999/1000；200 |
| GET，bytes=1000- | 416 | bytes */1000 |
| HEAD，bytes=0-99 | 200 | Content-Length=1000；body 为空 |

Range 与 HEAD 依据 [RFC 9110 §14.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-14.2)。

<a id="vtt"></a>
<a id="transcript-format"></a>

## 9. ASR、转写 JSON 与导出

![转写 JSON](docs/assets/diagrams/10-transcript-format.svg)

![版本约束](docs/assets/diagrams/07-transcript-vtt.svg)

ASR 消费当前 WAV，返回 cue 的 start_ms/end_ms/text 和可空 speaker。说话人按当前录音稳定映射为 A/B/C；供应方未提供分离结果时，speaker 保存为 null。

### 9.1 生成与存储

1. 校验 JSON 片段：文本非空、毫秒为整数、`0 <= start < end`、时间不超当前 WAV 时长（允许最多 1ms 表示精度误差），起点不倒序。合法的多人重叠允许保留。
2. 准备版本化 JSON `{schema_version:1,time_unit:"ms",cues:[...]}`，在步骤 5 的最终事务中整体写入 `recordings.transcript_json`，关联 transcript_revision。识别原文保存在 SQLite，VTT 和 Markdown 均由同一批 cues 生成。采用 UTF-8 纯文本、整数毫秒和可空 speaker，完整 JSON/字段/空结果约定见[转写格式](#transcript-format)及下方 [JSON 示例](#json-example)。text 使用 UTF-8 纯文本。
3. 生成 UTF-8 `transcript.vtt`，使用 `WEBVTT` 文件头、空行、稳定 cue 编号、`HH:MM:SS.mmm --> HH:MM:SS.mmm` 和可选 voice 标签。说明依据：[W3C WebVTT 格式](https://www.w3.org/TR/webvtt1/)。
4. 用户文本的 `& < >` 转义，空白行规范化，speaker 标签只来自受控映射。
5. VTT 通过相同文件发布流程校验/持久，随后在短事务中提交 transcript_json、vtt_job_id 指针和 transcript_revision/state；中断时保留处理状态，重启后重做。若仅有已 rename 的 VTT 而 cues 事务未提交，恢复时先确认文字事务，尚未提交则废弃该次未提交的派生产物并用同版本 WAV 重跑 ASR，新的 cues/VTT 重新一起发布；raw/WAV 保留。

ASR 耗时不影响 WAV 播放。新 WAV 发布后，只展示与 audio_revision 相同的 cues/VTT；处理中展示当前状态。当前输入更新期间仍可保留上一份音频与同版本文字，标“更新中”；新音频替换时旧文字先隐藏。

<a id="vtt-example"></a>

### 9.2 VTT 示例

示例：

```vtt
WEBVTT

1
00:00:00.000 --> 00:00:02.400
<v A>我们确认一下今天的安排。</v>

2
00:00:02.400 --> 00:00:05.800
<v B>先检查设备，再核对录音文字。</v>
```

下载 MIME 为 `text/vtt; charset=utf-8`。文字接口与字幕接口共享时间戳和 speaker。

### 9.3 导出文件

导出接口提供 WAV、Markdown 和 VTT。WAV/VTT 保存为磁盘文件，元数据位于 jobs；Markdown 按当前转写 JSON 生成，内容为日期标题、说话人和原文。

| 字段 | 格式 | 示例 |
|---|---|---|
| recording_id + revision | API 录音与版本，数据库使用 id/transcript_revision | demo-recording / 1 |
| cue_index | 从 1 开始的连续整数 | 1 |
| start_ms / end_ms | 相对当前 WAV 的整数毫秒 | 0 / 2400 |
| speaker | 稳定匿名标签或 NULL | A |
| text | UTF-8 纯文本原文 | 我们确认一下今天的安排。 |

### 9.4 原文格式与校验

SQLite 在 `recordings.transcript_json` 存一份 `{schema_version:1,time_unit:"ms",cues:[...]}`，录音 owner 与 transcript_revision 在同一行。`text` 保存识别原文，输出 VTT 时再转义。统一 CRLF 为 LF，拒绝 NUL/非法编码与纯空白句；原有标点、中文和换行保留。speaker 只能为 A/B/C…稳定映射或 NULL，Web 用 textContent 渲染。运行日志仅保留请求 ID、阶段与错误码。

API 外层固定为 `schema_version:1, recording_id, revision, time_unit:"ms", cues:[], next_cursor`；`revision` 对应 recordings.transcript_revision，并须等于当前 audio_revision；input_revision 表示最新收到的输入版本，cue 字段名固定为 cue_index/start_ms/end_ms/speaker/text。owner 取自服务端会话。持久 JSON 保存 schema_version、time_unit、cues，接口补充录音、版本与分页字段。

供应方秒数在 adapter 中转为整数毫秒；校验 `0 <= start_ms < end_ms <= duration_ms`，最大 1ms 精度误差可夹到音频边界，夹后仍须 start < end。按 start_ms 与供应方稳定顺序排序后生成连续 cue_index；合法多人重叠保留。单句最多 10000 字符、每录音最多 100000 cues、持久 JSON 编码后最多 8 MiB UTF-8，超限报 `transcript_limit_exceeded`，整批结果保留失败状态。数字/类型/文本不合法则整批失败，返回校验错误。

静音时允许 **0 cues**：transcript_state=ready，JSON cues=[]，VTT 为 `WEBVTT\n\n`，Markdown 仅日期标题，Web 显示“未识别到文字”。ASR 未配置、失败与成功无文字是不同状态；用户仍可播放 WAV。

### 9.5 发布事务

1. ASR 读取冻结的同版本 WAV，校验并准备 cues；任务持有效 lease。
2. 从同组 cues 生成 UTF-8 VTT，转义 `& < >`，清理会破坏 cue 分隔的文本空行；text 原文不受影响。文件名/路径由 Server 生成。VTT 经当前 transcribe jobs 行保存的临时/最终路径、size/hash、publication_state 完成 fsync/rename 持久化。
3. 持录音锁，在**一个 SQLite 事务**内检查 lease、当前 input_revision/audio_revision，整体写入 transcript_json、更新 vtt_job_id/transcript_revision/transcript_state，并将对应 jobs 文件设 publication_state=ready、任务设 succeeded。任一失败全部回滚，读者继续读取已提交版本。
4. 相同任务重放保持幂等；失效 lease 不得覆盖新输入。针对尚未提交的同版本尝试，只在事务内替换待发布 transcript_json；已成功版本直接读取持久结果。新输入先隐藏不匹配的旧文字。

### 9.6 恢复与读取

| 中断位置 | 恢复动作 |
|---|---|
| cues 仅在内存 | 任务租约回收，重跑同版本 ASR |
| VTT rename 后、cues 提交前 | 将 jobs 内未提交的文件尝试标 abandoned，重新 ASR 并整体发布；通过 JSON 事务判断发布结果 |
| cues/VTT/ready 已提交、进程退出 | SQLite 直接读文字，VTT 直接下载；不重跑成功任务 |
| 成功后 VTT 文件缺失/损坏 | 保留已存 cues，当前 VTT 下载报暂不可用；维护侧从已提交同版本 cues 经文件发布恢复，不重新 ASR |
| 音频更新或请求版本不符 | 409 recording_revision_changed；Web 取消旧请求后重新加载 |

恢复时不删除任何 raw；废弃的派生产物只有在无当前指针/在途读取引用后才清理。当前 JSON 仅在新音频对应转写成功时整体替换；已开启的旧 SQLite 读取快照按 WAL 规则完成。

JSON 每页最多 200 cues，游标绑定录音/版本。每个请求在同一 SQLite 读取快照核对 owner、当前 audio_revision、transcript_revision 和 ready 状态；不匹配拒绝。复制全部文字要取完同版本全部页才写剪贴板。VTT 已持久保存，JSON 分页/Markdown 从同一 SQLite 快照的 transcript_json.cues 按数组顺序读取；可使用 json_each 分页或迭代，避免构造整批 Python cue 对象。Markdown 按句生成；三者使用相同 speaker 和文字。JSON/VTT/MD 为当前音频同版本，响应均标注 revision，下载附件固定 UTF-8 与安全 filename。

<a id="json-example"></a>

### 9.7 JSON 接口示例

```json
{
  "schema_version": 1,
  "recording_id": "demo-recording",
  "revision": 1,
  "time_unit": "ms",
  "cues": [
    {
      "cue_index": 1,
      "start_ms": 0,
      "end_ms": 2400,
      "speaker": "A",
      "text": "我们确认一下今天的安排。"
    },
    {
      "cue_index": 2,
      "start_ms": 2400,
      "end_ms": 5800,
      "speaker": "B",
      "text": "先检查设备，再核对录音文字。"
    }
  ],
  "next_cursor": null
}
```

持久存储只保留 schema_version、time_unit、cues；recording_id、revision、next_cursor 为接口外层字段。

### 9.8 JSON 分页读取

读取前在同一快照内核对 owner、audio_revision、transcript_revision 和 transcript_state。cue 数组保持 cue_index 连续；游标包含 recording_id、revision、last_cue_index，由服务端校验参数归属。

```sql
SELECT CAST(c.key AS INTEGER) + 1 AS cue_index, c.value AS cue
FROM recordings AS r, json_each(r.transcript_json, '$.cues') AS c
WHERE r.id = :recording_id AND r.owner = :owner
  AND r.audio_revision = :revision
  AND r.transcript_revision = :revision
  AND r.transcript_state = 'ready'
  AND CAST(c.key AS INTEGER) + 1 > :last_cue_index
ORDER BY CAST(c.key AS INTEGER)
LIMIT 201;
```

返回前 200 条，第 201 条用于判断 next_cursor。Markdown 迭代同一快照的全部 cues；JSON/VTT/Markdown 响应标注相同 revision。ASR 成功但无文字时，保存 cues=[] 和合法空 VTT，并将状态标为 ready。

<a id="web"></a>

## 10. HTTP 接口与 Web 接入

| 方法/路径（统一前缀 `/api/boa/v1`） | 内容 |
|---|---|
| GET `/auth/google/start` | 创建一次性内存登录事务，跳转 Google |
| GET `/auth/google/callback` | 消费 state、验证 Google 身份、创建本站会话后 303 回首页 |
| GET `/auth/session`；DELETE `/auth/session` | 本人基本资料和 CSRF token（no-store）；退出清 Cookie/内存会话 |
| GET `/devices` | 本人设备/能力/带时间的可信状态 |
| POST `/devices/activate` | 已验证身份、完整 UID、可信登记依据；复用/建立本人绑定 |
| POST `/devices/{id}/binding/confirm` | 设备配置读回确认；实际收件单独记录 |
| PATCH `/devices/{id}` | 仅改别名 |
| DELETE `/devices/{id}/binding` | 撤上传凭证，历史录音保留；清理失败如实返回 |
| GET `/recordings?from=&to=&cursor=&limit=` | 日期筛选、列表预览与处理状态 |
| GET `/recordings/{id}` | 时间、时长、完整性、当前音频/文字版本与状态 |
| GET/HEAD `/recordings/{id}/audio.wav?revision=` | 固定版本鉴权 WAV；GET 支持 Range，HEAD 返回资源头 |
| GET `/recordings/{id}/transcript?revision=&cursor=` | 固定版本 JSON cues，每页最多 200 条；游标绑定录音/版本 |
| GET `/recordings/{id}/transcript.vtt?revision=` | 固定音频版本的 VTT 下载 |
| GET `/recordings/{id}/transcript.md?revision=` | 固定版本 cues 生成 Markdown |
| GET `/health` | 服务状态与版本 |

### 10.1 参数、响应与错误

- 列表 from/to 为 YYYY-MM-DD；部署业务时区默认 Asia/Shanghai，结束日转换为次日零点的 UTC 半开区间。使用可信 recorded_at，缺失或不可信时回退 received_at。
- 列表默认 30 条，limit 最大 100；按有效录音时间/id 降序分页。游标同时携带日期筛选和排序位置，筛选变化时重置。
- PATCH 设备别名接收 `{name}`；绑定激活接收 `{uid,evidence}`；确认接口复用现有 binding/revision/config_hash 校验。所有写入由服务端 Actor 限定 owner。
- 详情响应包含 id、时间来源、duration_ms、integrity、input_revision、audio_revision、transcript_revision、audio_state、transcript_state 与当前媒体地址。
- 文字待处理时详情正常返回状态；文字/导出端点返回 409 transcript_not_ready，ASR 未配置返回 503 asr_not_configured。版本变化返回 409 recording_revision_changed。
- 统一错误 body 为 `{error:{code,message},request_id}`；400 参数/回调错误，401 会话失效，403 账号禁用/CSRF，404 资源不存在或跨 owner，409 状态/版本冲突，416 Range，422 字段校验，429 限流，503 依赖不可用。

**跨请求版本约束：** 详情先固定 audio_revision，WAV、JSON cues、VTT、MD 请求均必须携带 revision，cue 游标也绑定 recording/revision。Server 在同一读取快照内检查请求版本为当前音频版本，文字还须匹配 transcript_revision；不匹配返回 409 `recording_revision_changed`，未就绪返回明确处理中状态。响应标注版本。列表轮询发现新音频版本或收到 409 recording_revision_changed 时，Web 取消旧分页/复制、停止旧播放并重新载入详情；复制全部文字必须在全部同版本分页成功后才写剪贴板。在途读取完成后清理旧派生文件。

### 10.2 响应数据结构

| 接口 | 响应字段 |
|---|---|
| auth/session | user: {user_id,email,display_name}、csrf_token |
| devices | items: [{device_id,uid,binding_id,epoch,display_name,firmware,capabilities,telemetry}] |
| devices/activate | device_id、binding_id、epoch、revision、configuration；configuration 复用已有上传配置结构 |
| devices/{id}/binding/confirm | binding_id、confirmed_revision、state |
| recordings | items: [{id,time_source,recorded_at,received_at,duration_ms,audio_state,transcript_state,preview_text}]、next_cursor |
| recordings/{id} | 见下方示例 |
| recordings/{id}/transcript | schema_version、recording_id、revision、time_unit、cues、next_cursor |

telemetry 的 online、battery、pending 分别使用 `{value,sampled_at,source}` 结构；缺少有效来源时 value=null。firmware/capabilities 取自现有设备资料或已确认读回，缺失时为 null；BLE 调用以连接时实际 capability 为准。preview_text 从当前音频同版本转写的第一句提取；转写未就绪时为空字符串。无数据的列表返回 items=[]、next_cursor=null。JSON 时间统一为 UTC Unix 毫秒，duration_ms 为相对时长。

详情响应示例：

```json
{
  "id": "demo-recording",
  "time_source": "server_received",
  "recorded_at": null,
  "received_at": 0,
  "duration_ms": 5800,
  "integrity": "unknown",
  "input_revision": 1,
  "audio_revision": 1,
  "transcript_revision": 1,
  "audio_state": "ready",
  "transcript_state": "ready",
  "links": {
    "audio": "/api/boa/v1/recordings/demo-recording/audio.wav?revision=1",
    "transcript": "/api/boa/v1/recordings/demo-recording/transcript?revision=1",
    "vtt": "/api/boa/v1/recordings/demo-recording/transcript.vtt?revision=1",
    "markdown": "/api/boa/v1/recordings/demo-recording/transcript.md?revision=1"
  }
}
```

start、callback、health 允许未认证访问，其余接口通过 principal()。登录 start 使用浏览器顶层导航。失败写请求由调用方处理；401 或 account_disabled 清理会话，CSRF 错误返回 csrf_invalid，业务冲突保留原状态并返回具体 code。

### 10.3 Web 模块实现

| 模块 | 实现要求 |
|---|---|
| api.mjs | credentials=same-origin；写请求加 X-CSRF-Token；集中处理错误和 AbortSignal；401 或 account_disabled 清会话，其余 403 按 error_code 处理 |
| app.mjs | 初始化 GET auth/session；装配模块；BroadcastChannel 广播退出；释放旧账号的请求和音频 |
| devices.mjs | 串行 BLE 命令队列、连接 generation、能力映射、扫描结果校验、密码调用后清理 |
| recordings.mjs | 日期参数/游标管理；取消旧筛选请求；录音轮询可见 5 秒、隐藏 30 秒 |
| detail.mjs | 固定 audio_revision；媒体/文字都携带版本；200 cues 分页；取齐后复制；使用 textContent |

设备状态轮询可见 15 秒、隐藏 30 秒，恢复可见时立即刷新。每个模块持自己的 AbortController 与 generation，dispose() 中中断请求、取消定时器、卸载事件。请求返回前核对 generation，丢弃过期结果。

SQLite 游标在创建 connection 的线程内消费；流式导出通过有界队列交给响应，客户端断开时取消迭代并关闭游标与读取快照。

媒体 error 事件触发会话和详情复核；版本变化时释放旧 audio.src、取消旧 cue 分页后重新加载。下载 WAV 使用同源链接和 download 属性；Markdown/VTT 使用附件响应，文件名由服务端生成。

<a id="implementation"></a>

## 11. 开发任务与实施顺序

![实施里程碑](docs/assets/diagrams/12-implementation-order.svg)

依赖顺序：S01 → S02 → S03/S04；S05 → S06 → S07 → S08；S09/S10 接入录音模块；S11 完成设备能力适配；S12 集成和发布验证。

### S01：实施基线与版本化迁移

**涉及文件：** 新增 `product/{__init__,contracts,db}.py`、`product/migrations/*.sql`、`tests/product/{conftest,test_db}.py`、基线记录；修改打包文件清单。**接口：** `migrate(root: Path, dry_run: bool) -> dict`、`BusinessDB.connect() -> sqlite3.Connection`。

- [ ] 记录源码版本，建立开发分支和 `.venv-boa`，运行原 Python/Node 测试，记录基线结果与环境依赖。
- [ ] 写 `test_schema_has_four_business_tables`、`test_legacy_ids_and_time_units_survive_migration`、`test_missing_legacy_owner_email_blocks_migration`，运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_db.py -q`，记录结果。
- [ ] 参考 SQL 转为真实版本化迁移，保留旧 registry/上传库；新业务库 4 表、PRAGMA user_version 原子更新；registry 只加 bindings 别名列和 sources.projected_at。同步把 registry.py 中 bindings/sources 的位置式 INSERT 改成显式列名，验证加列后兼容；毫秒桥接与公共接口约定一次统一。
- [ ] 验证目标测试，FK/integrity、旧库夹具升级、失败重跑、未知高版本拒绝均验证；迁移先在隔离副本运行。
- [ ] 交付四表迁移、旧库升级夹具和数据库访问接口。

### S02：基本用户、会话和统一 owner 检查

**涉及文件：** `product/{auth,users}.py`、`test_users.py`、`test_google_auth.py`；修改 `web_sessions.py`、`boa_app.py`、依赖锁。**接口：** `begin_google_login(request: Request) -> Response`、`finish_google_login(request: Request) -> Response`、`sync_verified_user(sub: str, email: str, name: str) -> str`、`principal(request: Request) -> Actor`、`logout(request: Request) -> None`。登录参数、TTL、Cookie、容量和错误码以[接口约定](#google-login)为准。

- [ ] 写 `test_sub_reuses_owner`、`test_same_email_never_merges_user`、`test_invalid_state_nonce_pkce_or_id_token_denied`、`test_callback_replay_and_browser_mismatch_denied`、`test_restart_requires_login_but_keeps_device_upload`、`test_logout_keeps_recordings`、`test_disabled_user_denied`；账号 9 字段，旧 sub 可空，登录状态与会话不落盘。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_users.py server/boa/tests/product/test_google_auth.py -q`，记录结果。
- [ ] 接 Google Code/OIDC + S256 PKCE 与标准验证库，配置固定 HTTPS 回调、openid/email/profile；实现内存 LoginFlow/Session、Cookie、当前用户/退出、Origin/CSRF，旧 Bearer 统一门禁。Google token 使用后释放，登录采用 online 模式；sub 来自已验证 token，owner 来自本站会话。
- [ ] fake clock 验证 5 分钟/24 小时/7 天、单次消费、容量到顶拒绝且已有有效会话继续使用、禁用/auth_version 立即生效；同邮箱不同 sub、同 sub 邮箱冲突、Google 失败时清理本次认证状态；完成目标测试和旧接口回归，随后验证真实 Google 跳转。
- [ ] 交付 Google 登录、内存会话、当前用户和退出接口。

### S03：设备绑定、别名与凭证撤销

**涉及文件：** `product/devices.py`、`test_devices.py`；适配 `registry.py`、`device_configurations.py`。**接口：** `activate(actor: Actor, uid: str, evidence: dict) -> dict`、`rename(actor: Actor, device_id: str, name: str) -> None`、`remove(actor: Actor, device_id: str) -> dict`。

- [ ] 写 `test_activation_requires_trusted_enrollment`、`test_same_owner_activation_is_idempotent`、`test_other_owner_cannot_claim`、`test_remove_revokes_upload_but_keeps_audio`。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_devices.py -q`，记录结果。
- [ ] 把原型自动激活接到既有可信登记/发放和 binding/epoch/读回 API，凭据只给本人并 no-store。别名写既有 registry.bindings.display_name，WHERE 同时核对本人 owner、binding_id、active；移除先撤凭证，离线清理保留既有锁。验证依据使用现有受控登记与设备凭证。
- [ ] 验证绑定接口和实机激活；无有效登记依据、已属其他用户或配置读回失败时，拒绝激活并显示具体错误。
- [ ] 交付设备激活、改名、移除接口及绑定回归结果。

### S04：Web 初始化、会话与请求生命周期

**涉及文件：** `server/web/product/{index.html,app.mjs,api.mjs,devices.mjs}`、`server/web/tests/product-shell.test.mjs`；修改 `frontend.py`。**接口：** `createApi({fetcher,onLogout}) -> {request,reset}`、`createDeviceController({api,ble}) -> {connect,configure,disconnect,dispose}`。

- [ ] 添加会话初始化、CSRF 头、请求取消、旧响应丢弃、设备断开清理的单元测试。
- [ ] 运行 `node --test server/web/tests/product-shell.test.mjs`，记录结果。
- [ ] 装配同源 API client 和 BLE adapter；登录后装载会话，退出或账号变化时清空控制器；设备控制器完成连接、UID/能力读回和 S03 接口调用。
- [ ] 在 Chrome 验证 401/403、请求乱序、网络恢复、BLE 取消选择与断开事件；分别记录模拟和实机结果。
- [ ] 交付应用初始化、API client、会话管理和设备控制器。

### S05：来源投影、片段幂等和上传状态

**涉及文件：** `product/recordings.py`、`test_sources.py`；修改 `registry.py`、`receiver.py` 和 App 完成适配。**接口：** `import_ready(ctx, event: SourceEvent) -> str`、`sync_receiving(ctx) -> int`、`snapshot(actor: Actor, recording_id: str) -> InputSnapshot`。

- [ ] 写 `test_raw_ack_does_not_wait_for_business`、`test_ready_event_replay_changes_revision_once`、`test_receiving_has_no_ready_file`、`test_gap_and_new_epoch_not_merged`、`test_projected_marker_never_hides_restore_gap`、`test_same_source_hash_conflict_rejected`。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_sources.py -q`，记录结果。
- [ ] raw/identity/fsync/ACK 保持旧语义；sources ready 行本身就是待投影项；business 片段行同时存 raw 元数据与收据，唯一 namespace/source_id，条件 receiving→ready 与录音增版本同事务。先提交 business 再标 sources.projected_at；启动按 500 条分页对账全部 ready 来源。receiving 用于上传状态，校验完成后创建处理任务；App 仅兼容既有接口。
- [ ] 在 raw 后、registry 后、business 后、消费标记前故障注入并重启，确认原件完整、版本幂等，并完成原 DTLS/HTTP 回归。
- [ ] 交付来源投影、片段幂等和收件故障恢复结果。

### S06：两类持久任务与文件发布恢复

**涉及文件：** `product/jobs.py`、`files.py`、`test_jobs.py`、`test_files.py`；修改服务 lifespan。**接口：** `enqueue(snapshot: InputSnapshot, kind: str) -> str`、`claim(now_ms: int) -> Lease | None`、`publish(lease: Lease, tmp: Path, metadata: dict) -> str`、`recover(ctx) -> int`。

- [ ] 写 `test_single_active_job`、`test_expired_lease_cannot_publish`、`test_rename_before_commit_recovers`、`test_new_revision_fences_old_output`。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_jobs.py server/boa/tests/product/test_files.py -q`，记录结果。
- [ ] jobs 一行含任务、文件路径/hash/size、publication_state；decode 仅 WAV、transcribe 仅 VTT。实现按 recording/revision/kind 去重、SQL 部分唯一索引限制一个 running、60 秒 lease/15 秒续期、有界重试；prepared→临时 fsync→预期 hash→同盘独占 rename/目录 fsync→ready；WAV 可核 hash 恢复，VTT/cues 的联合提交恢复由 S08 验证。用输入版本和租约控制发布。
- [ ] 对发布边界中断、磁盘满、hash 冲突、文件缺失、双监听重复启动运行时做测试，确认恢复行为；服务退出停止领新任务，15 秒后留待重启恢复。
- [ ] 交付持久任务调度、文件发布与重启恢复模块。

### S07：raw 解码为一份 WAV，鉴权 Range 播放

**涉及文件：** `product/decode.py`、`test_decode.py`、`test_audio_http.py`；修改 `product/routes.py`、依赖/工具版本清单。**接口：** `decode(snapshot: InputSnapshot, output: Path) -> dict`、`serve_audio(actor: Actor, recording_id: str, revision: int, range_header: str | None) -> Response`。

- [ ] 写 `test_raw_packet_framing_to_16000_mono_pcm16`、`test_bad_packet_preserves_raw`、`test_gap_does_not_get_silence`、`test_range_owner_and_logout`；1 秒合成样本应得 16000 样本，GET 单范围合法 206、非法 416，HEAD 返回 200 和空 body；越界 end 截至文件末尾，后缀范围按字节数计算。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_decode.py server/boa/tests/product/test_audio_http.py -q`，记录结果。
- [ ] 按实际 raw profile 解包/封装并解码，临时分段后合一份 WAV；raw 元数据只在 recording_segments；样本数/独立 hash 随 WAV jobs 行入库；S06 发布当前音频。WAV 同时供播放、ASR、下载。Cookie/Bearer + owner 直接鉴权。
- [ ] 目标测试和授权真实样本解码/试听分别通过；验证长录音拖动、超时/体积限制、并发新片段和旧音频仍可安全读取，记录 pre-skip 时间来源限制。
- [ ] 交付 raw 解码器、WAV 文件及鉴权 Range 接口。

### S08：ASR 文字、说话人与 WebVTT

**涉及文件：** `product/transcript.py`、`test_transcript.py`、`test_vtt.py`；从本文 [VTT 示例](#vtt-example)提取人工合成测试夹具。**接口：** `ASR.transcribe(wav: Path, request_id: str) -> list[Cue]`、`validate_cues(cues: list[Cue], duration_ms: int) -> list[Cue]`、`render_vtt(cues: list[Cue]) -> bytes`、`publish_transcript(lease: Lease, cues: list[Cue]) -> None`。

- [ ] 写 `test_vtt_header_utf8_milliseconds_and_voice`、`test_invalid_time_rejected_but_valid_overlap_kept`、`test_untrusted_text_escaped`、`test_old_transcript_not_on_new_wav`；示例应解析出 2 个 cue，结尾 5800ms，speaker A/B，空白文本 cue/逆序/越界拒绝；全程静音允许 0 cues。增加 `test_plain_text_roundtrip_and_json_vtt_same_cues`、`test_restart_loads_text_without_asr`、`test_vtt_file_without_cue_commit_is_reprocessed`、`test_missing_vtt_rebuilds_from_stored_json`、`test_json_limit_never_truncates_text`。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_transcript.py server/boa/tests/product/test_vtt.py -q`，记录结果。
- [ ] 按 v1 JSON 接口约定固定 cue_index 和整数毫秒，整份 transcript_json 不超过 8 MiB UTF-8，text 为未转义原文，speaker 可空；接一套实际私有 ASR adapter，未配置明确 not_configured；校验后生成 UTF-8 VTT，按 S06 持久发布，并把 recordings.transcript_json、vtt_job_id、文字 ready 与 jobs 成功原子提交。当前 audio_revision 与 transcript_revision 一致才对外显示；说话人缺失保存为 null。
- [ ] 目标测试通过，重启后直接从 recordings.transcript_json 读文字、由同版本 cues 导出 MD；缺失 VTT 复用已存 JSON 重建；VTT 已落盘且 cues 未提交时，恢复任务重新识别并整体发布。浏览器实际解析示例 VTT；真实端点用授权样本检查时间/文本/分离质量。ASR 失败时，验证已发布 WAV 仍可播放。
- [ ] 交付 ASR 适配器、转写 JSON 持久化和 VTT 文件。

### S09：日期列表 API 与 Web

**涉及文件：** 扩展 `product/{recordings,routes}.py`、`server/web/product/recordings.mjs`；新增 `test_recording_list.py`、`product-recordings.test.mjs`。**接口：** `list_recordings(actor: Actor, from_date: str | None, to_date: str | None, cursor: str | None, limit: int=30) -> dict`。

- [ ] 写 `test_inclusive_end_date_uses_next_local_midnight`、`test_invalid_dates_and_owner_filter`；JS 验证日期筛选、文字开头预览和列表状态。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_recording_list.py -q`、`node --test server/web/tests/product-recordings.test.mjs`，记录结果。
- [ ] COALESCE 可信录音时间/收件时间后按部署时区分组，结束日转次日零点半开区间；每页 30 条稳定日期/id 游标。显示真实 receiving、处理状态和时长；可见 5 秒/隐藏 30 秒轮询、日期变化取消旧请求。
- [ ] 目标测试通过；Chrome 检查同日/跨日、清空筛选、无数据、后端离线和返回列表；跨用户访问返回 404。
- [ ] 交付日期筛选接口、录音列表和分页交互。

### S10：媒体消费、文本分页与下载

**涉及文件：** `server/web/product/detail.mjs`、`test_downloads.py`、`product-detail.test.mjs`；扩展 transcript/routes。**接口：** `get_cues(actor: Actor, recording_id: str, revision: int, cursor: str | None) -> dict`、`render_markdown(cues: list[Cue], heading: str) -> bytes`、Web `mountDetail({root,api,audio,id}) -> {dispose}`。

- [ ] 写 `test_wav_md_vtt_same_owner_and_revision`、`test_publication_between_pages_requires_reload`、`test_markdown_preserves_transcript_text`；JS 断言复制文字、播放暂停/拖动、退出清理音频。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_downloads.py -q`、`node --test server/web/tests/product-detail.test.mjs`，记录结果。
- [ ] 展示日期标题、时长、A/B 文字；cue 分页每页 200 条，复制/MD 覆盖全部当前文字而不只第一页。导出菜单提供 WAV、Markdown、VTT。详情固定 audio_revision，四类内容请求和 cue 游标都带 revision；读快照内匹配当前音频/文字版本，否则 409，Web 取消分页/播放后重新载入，版本变化时重新取齐文字。MD 即时生成。
- [ ] 目标测试通过；Chrome 试听/拖动、复制全文、下载 WAV/MD/VTT 并核对中文/时间戳和 MIME；新 WAV 就绪时隐藏不同版本文字，切换账号中断旧请求。
- [ ] 交付详情播放器、全文复制和 WAV/Markdown/VTT 下载。

### S11：BLE 能力适配与 Wi-Fi 配置

**涉及文件：** 扩展 `product/devices.py`、`server/web/product/devices.mjs` 和既有 BLE adapter；新增 `product-wifi.test.mjs`、`test_device_views.py`。**接口：** BLE adapter `capabilities()`、`scanWifi() -> {ssid,rssi,security}[]`、`listWifi()`、`saveWifi(selectedSsid,password)`、`readWifiStatus()`、`deleteWifi(ssid)`；扫描与连接状态由 Clip 真实返回，缺能力为 unsupported。

- [ ] 写 `wifi list comes from clip scan over ble`、`ssid must be selected from scan results`、`missing scan does not enable manual ssid`、`saved is not connected`、`at most five saved networks`、`password never sent to server`；后端验证别名/归属/移除保留录音，状态来源缺失时显示“未知”。
- [ ] 运行 `node --test server/web/tests/product-wifi.test.mjs`、`.venv-boa/bin/python -m pytest server/boa/tests/product/test_device_views.py -q`，记录结果。
- [ ] 设备控制器实现改名、状态读取和移除；Wi-Fi 调用顺序为连接 BLE→请求 Clip 扫描→选择返回的 SSID→输入密码→BLE 写入→读取保存/连接结果。空列表/超时重扫、密码错误重输。扫描接口不可用时显示固件能力要求；已保存网络按设备容量展示。
- [ ] 模拟边界测试通过；实机验证扫描列表确实来自目标 Clip、选网/密码写入/连接结果、删除/重连/移除；验收记录包含扫描来源、网络容量和遥测采样时间。
- [ ] 交付设备控制器、BLE Wi-Fi 适配器和实机验证结果。

### S12：整体回归、迁移恢复与候选包

**涉及文件：** `tests/product/test_end_to_end.py`；修改打包脚本/部署说明，必要时新增小型迁移/备份 CLI。**交付：** 候选包、源码/依赖/文档 SHA、分层检查记录；形成待部署候选包。

- [ ] 在隔离夹具写端到端失败用例：用户→设备→receiving→raw→WAV→文字/VTT→列表→复制/下载→移除设备，断言历史文件归属不变，Bob 请求 Alice 的录音时返回 404。
- [ ] 执行 `.venv-boa/bin/python -m pytest server/tests server/boa/tests server/storage/tests -q`、`.venv-boa/bin/python -m unittest tools.upload.tests.test_dtls_receiver -v`、`node --test server/web/tests/*.test.mjs`，修复回归；环境缺失单列。
- [ ] 真实浏览器、Google 登录及重启重登、Clip 收件、WAV 试听、ASR/VTT、Wi-Fi 实机分别验收；记录缺失的发放/固件能力，Google 配置缺失则登录未验收，固件缺项则实机闭环未验收；联调记录附真实返回数据。
- [ ] 停机整体备份并在隔离目录迁移/恢复，核对旧 user_id、设备、raw 数量/字节/hash；回退先保存新录音；测实际响应/处理时间并记录，给出实测处理能力。
- [ ] 打包排除录音/数据库/凭证，核对 manifest/哈希；交付候选包、校验清单和验收记录，列出待完成的联调项，完成上线验收后标记发布版本。

<a id="operations"></a>
<a id="self-review"></a>

## 12. 配置、运行与验收

### 12.1 配置项

| 配置 | 说明 |
|---|---|
| data-root | 由现有启动参数传入 ProductContext，进程持排他锁 |
| GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET | Google Web application 凭证，服务器侧加载 |
| PUBLIC_WEB_ORIGIN | 精确 HTTPS origin，导出固定回调地址 |
| ASR endpoint / credential | 由现有私有 ASR 配置适配器加载 |
| decode_timeout / asr_timeout | 默认 10 分钟 / 60 分钟 |
| lease / renew / retries | 60 秒 / 15 秒 / 3 次重试 |
| business_timezone | 默认 Asia/Shanghai |
| raw / duration / transcript limits | 单 raw 8 MiB、连续 8 小时、JSON 8 MiB |

### 12.2 启动和退出

启动顺序：锁定数据目录、迁移和校验库、恢复原件/来源、恢复文件发布、回收过期任务、启动接收与调度。登录会话从空 map 开始。服务退出先停止领取任务和新请求，结束或取消子进程/ASR 请求，最多等待 15 秒；未提交任务交给下次启动恢复。

### 12.3 备份与回退

停服务并取得维护锁，整体备份 registry、业务库及 WAL、clip 原件/checkpoint、现有 App 存储、配置/凭证与 derived 文件。备份权限沿用数据目录私密权限。恢复在隔离目录完成，核对 user_id、binding/epoch、原件数量、字节、hash 和任务状态，再切换运行目录。回退前单独保存上线后新增原件，恢复后通过 ready 来源全量对账补齐索引。

### 12.4 故障注入与验收

| 场景 | 检查结果 | 责任任务 |
|---|---|---|
| raw fsync / checkpoint / rename 中断 | ACK 对应已持久偏移，重启后续传 | S05/S12 |
| registry ready、business 提交、projected_at 标记之间中断 | 原件保留，投影幂等且版本只递增一次 | S05/S12 |
| lease 到期、旧任务迟到、新片段到达 | 旧执行无法覆盖新输入结果 | S06/S07 |
| WAV rename 后、数据库提交前中断 | 核对 hash 和版本后补提交 | S06/S07 |
| VTT 落盘、JSON 提交前中断 | 重跑转写并整体发布 | S06/S08 |
| VTT 成功后文件缺失 | 从已提交 JSON 重建，原文可读取 | S08 |
| JSON/VTT 时间越界、空白、重叠、静音 | 拒绝非法 cue，保留合法重叠，静音返回空数组 | S08 |
| 跨用户 API / Range / 导出请求 | 返回 404，状态/禁用统一检查 | S02/S07/S10 |
| 分页之间音频版本变化 | 返回 409，Web 重置媒体与文字请求 | S10 |
| Google 取消/重放/身份冲突/服务重启 | 清理本次状态，稳定归属，重新登录 | S02/S12 |
| BLE 断开、扫描为空、密码错误、配置读回不匹配 | 取消旧命令，返回实际错误并可重试 | S03/S04/S11 |
| 长录音、磁盘满、依赖超时、迁移回退 | 有界失败，原件保留，恢复记录可核对 | S07/S12 |

### 12.5 当前验证记录

参考 DDL 的四表建库、19 项约束拒绝检查、JSON 分页/回滚、registry 旧结构加列、外键与完整性检查已完成。JSON/VTT 示例使用相同文字、speaker 与毫秒时间戳。Google、真实 Clip、ASR 质量、实际部署和备份恢复在 S12 记录联调结果。

### 12.6 图源

技术图由 [render.py](docs/assets/diagrams/render.py) 生成；修改后核对代码接口、字段与状态，再运行：

```sh
python docs/assets/diagrams/render.py
```
