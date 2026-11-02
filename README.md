# ReSpeaker Clip · Server / Web 开发设计

v3 · 2026-11-02

## 1. 整体架构与主要模块

Server / Web 负责用户和设备管理、录音处理、播放与导出。原始文件及其归属信息由接入组件提供，文件就绪后导入业务库。设备传输协议不在本文范围内。

### 1.1 架构总览

![整体架构：客户端、Server 模块、外部服务与存储](docs/assets/diagrams/01-system-architecture.svg)

- **Web**：通过同源 HTTPS 调用用户、设备和录音接口，通过 BLE 配置设备。
- **Server**：使用 Python / FastAPI 单进程部署。一个后台工作者持有独占锁，顺序处理解码、识别和恢复；解码在受资源限制的子进程中执行。多 Uvicorn worker 和多机共享数据目录暂不支持。
- **外部服务**：Google 验证登录身份，Server 管理本站会话。ASR 接收每段 WAV，返回文字、时间戳和说话人标识；未配置 ASR 时仍可解码和播放音频。
- **存储**：设备与上传 SQLite（registry）保存绑定、凭证和来源记录；业务 SQLite 保存用户、录音、片段及处理结果。两个库分别提交事务，在线数据库位于主盘。raw 原件和片段 WAV 在主盘、副本盘各保存一份；副本盘另存 SQLite 一致性检查点。VTT 和 Markdown 从 JSON 快照生成。登录临时状态和会话只保存在内存。

Web 服务端口为 9529，对外使用 HTTPS。Google 回调地址须与部署配置一致。当前为设计稿，尚未完成实现和实机验收。

### 1.2 主要模块

- Web：提供登录、设备与录音列表、播放和导出页面，通过 BLE 写入并读回设备配置。[Web API](#web-api)、[设备规则](#ble)
- 用户与会话：处理 Google 登录、会话、本人资料和账号状态，校验 CSRF。[用户接口](#users-api)、[登录与会话](#oauth)
- 设备与绑定：校验 UID 登记，处理激活、配置确认、改名和解绑。[设备规则](#ble)
- 原件导入：读取 registry 的 ready 来源，校验文件及归属，按录音会话导入业务库并更新 content_revision。[原件导入](docs/audio-processing.md#ingest)
- 后台调度：按片段状态安排解码、识别、重试及 WAV 修复。[提交与恢复](docs/audio-processing.md#publication)
- 音频解码：将每份原件独立、流式解码为一个 WAV。[音频存储与解码](docs/audio-processing.md#storage)
- 转写与汇总：逐片段识别并保存结果，换算全局时间后生成录音快照；VTT 和 Markdown 在下载时生成。[转写设计](docs/audio-processing.md#transcript)
- 录音与媒体接口：按用户查询录音和快照，校验权限后读取音频、文字及导出内容，音频支持 Range。[Web API](#web-api)、[媒体 API](docs/audio-processing.md#media-api)
- 存储与备份：管理两个 SQLite 库、双盘文件副本、数据库检查点和版本备份，保证文件与索引的提交顺序。[数据模型](#data-model)、[存储安全](docs/audio-processing.md#security)

<a id="data-model"></a>

## 2. 对象与数据表

业务库有三张表：accounts 保存用户，recordings 保存一次录音，recording_segments 保存各个原始文件。每份原件的 WAV 信息、识别状态和 transcript_json 直接保存在 recording_segments，整条录音的播放清单、覆盖状态和文字保存在 recordings.result_json 快照中。owner 引用 accounts.user_id。设备绑定及来源记录仍保存在 registry。

设备每 5 分钟生成一个 segment，末段可不足 5 分钟。Server 每段解码为一个 WAV，并直接识别这一段，不做二次切块或重叠上下文。失败只重试对应片段，已有成功结果保留。播放器按片段 WAV 清单播放，字幕按实际样本数汇总。字段、缺号及恢复规则见[音频处理设计](docs/audio-processing.md#tables)。

字段示例使用 JSONC，实际请求和响应使用标准 JSON。时间统一为 UTC Unix 毫秒，示例中的 hash 和凭证不是真实数据。

### accounts 用户对象

```jsonc
{
  // TEXT；主键；必填。本地用户 ID，历史 ID 沿用；其他表通过 owner 引用。
  "user_id": "demo-user",
  // TEXT；唯一。验证通过的 Google 身份标识；待核验的历史用户可空。
  "google_sub": "google-sub-example",
  // TEXT；必填；唯一；大小写不敏感。用户邮箱；账号同步时检查身份冲突。
  "email": "user@example.com",
  // TEXT；必填；默认空字符串；≤100 字符。用户名称，可为空字符串。
  "display_name": "示例用户",
  // TEXT；必填；默认 active。active / disabled；请求鉴权检查账号状态。
  "status": "active",
  // INTEGER；必填；默认 1；>0。认证版本；变更后使旧会话失效。
  "auth_version": 1,
  // INTEGER；可空。最近登录时间。
  "last_login_at": 1793318400000,
  // INTEGER；必填。用户建立时间。
  "created_at": 1793318400000,
  // INTEGER；必填。用户资料更新时间。
  "updated_at": 1793318400000
}
```

新用户 ID 使用 uuid4().hex，历史 user_id 原样迁移。相同 sub 复用用户；邮箱与其他 sub 冲突时返回 account_identity_conflict，保留原归属。

设备别名保存到 bindings.display_name，配置确认保存到 binding_profiles.confirmed_revision；UID 映射由 device_uids 维护。音频相关两张表的[字段说明](docs/audio-processing.md#tables)在音频文档，完整 DDL 见[本页 SQL](#sql)。

<a id="web-api"></a>

## 3. Web 前后端 API

路径前缀 `/api/boa/v1`。除登录入口、回调和 health，其余接口验证会话；写请求携带 Origin、X-CSRF-Token；Server 精确匹配 PUBLIC_WEB_ORIGIN 和当前会话 CSRF，缺失或不匹配返回 403。owner 由 Server 确定。

- GET `/users/me`：读取会话对应的当前用户；200：用户资料对象
- PATCH `/users/me`：`{display_name}`；修改本人显示名称；200：更新后的用户资料对象
- GET `/devices`：无；200：`{items:[设备对象]}`
- POST `/devices/activate`：`{device_uid}`；查询受控登记和本人归属；200：device_id、device_uid、binding_id、epoch、revision、configuration；no-store
- POST `/devices/{id}/binding/confirm`：`{device_uid,binding_id,revision,saved:true}`；200：`{binding_id,revision,state:"provisioned"}`
- PATCH `/devices/{id}`：`{display_name}`；1–100 字符；200：device_id、display_name
- DELETE `/devices/{id}/binding`：无；200：`{state:"revoked",device_cleanup_pending}`
- GET `/recordings`：from、to、cursor、limit；200：`{items:[录音列表对象],next_cursor}`
- GET `/recordings/{id}`：id；200：录音详情对象
- GET `/health`：无；200：服务状态与版本

<a id="users-api"></a>

### 当前用户接口

用户首次通过 Google 登录时由 Server 自动建立 accounts 记录，HTTP 接口使用 `/users/me` 表示当前会话用户。两项接口均返回 `Cache-Control: private, no-store`；会话失效返回 401，账号禁用返回 403 account_disabled。

GET `/users/me` 和 PATCH `/users/me` 的成功响应使用相同结构：

```jsonc
{
  // string；accounts.user_id；只读，由会话确定。
  "user_id": "demo-user",
  // string；accounts.email，由登录身份同步；只读。
  "email": "user@example.com",
  // string；本站显示名称，允许空字符串，最多 100 字符。
  "display_name": "示例用户"
}
```

PATCH `/users/me` 请求：

```jsonc
{
  // string；必填，最多 100 字符；空字符串用于清空显示名称。
  "display_name": "我的名字"
}
```

PATCH 请求须通过 Origin 和 CSRF 检查，且只能包含 display_name。缺少字段、类型错误、超过 100 字符或包含其他字段，均返回 422。Server 使用参数化 SQL 更新本人记录的 display_name、updated_at，并返回最新资料。user_id、email、google_sub、status、auth_version 和 owner 均不可由此接口修改。

`GET /auth/session` 返回登录状态和 CSRF，其中的 user 与 `/users/me` 都读取 accounts 当前记录。首次 Google 登录可初始化名称，后续登录保留本站名称。用户接口仅管理本人资料；管理员操作和账号删除不在本版范围内。

### 设备写入请求与响应

POST `/devices/activate` 请求，200 响应使用下一节的身份与 configuration 字段：

```jsonc
{
  // string；从 Clip 读到的硬件 UID；Server 查询受控登记及本人归属。
  "device_uid": "0011223344556677"
}
```

POST `/devices/{id}/binding/confirm` 请求：

```jsonc
{
  // string；读回的硬件 UID。
  "device_uid": "0011223344556677",
  // string；BLE 读回的绑定 ID，须与当前用户设备一致。
  "binding_id": "demo-binding",
  // integer；读回的上传配置版本。
  "revision": 1,
  // boolean；固定 true，表示配置已写入并读回确认。
  "saved": true
}
```

确认成功响应：

```jsonc
{
  // string；确认完成的绑定 ID。
  "binding_id": "demo-binding",
  // integer；确认完成的配置版本。
  "revision": 1,
  // string；固定 provisioned。
  "state": "provisioned"
}
```

PATCH `/devices/{id}` 请求；200 返回同一 display_name 和路径对应的 device_id：

```jsonc
{
  // string；本人当前设备的别名，1–100 字符。
  "display_name": "我的 Clip"
}
```

DELETE `/devices/{id}/binding` 无 body，成功响应：

```jsonc
{
  // string；固定 revoked，设备上传凭证已撤销。
  "state": "revoked",
  // boolean；是否仍待设备侧清理确认，沿用现有维护状态。
  "device_cleanup_pending": true
}
```

### 设备与上传配置

GET `/devices` 返回 `{items:[设备对象]}`；POST `/devices/activate` 返回相同身份字段及 configuration。device_id、binding_id、device_uid 分别来自 registry.bindings.device、bindings.id、device_uids.uid。

```jsonc
{
  // string；registry.bindings.device；API 路径 {id} 使用此值。
  "device_id": "demo-device",
  // string；registry.device_uids.uid；设备硬件 UID。
  "device_uid": "0011223344556677",
  // string；registry.bindings.id；本次绑定 ID。
  "binding_id": "demo-binding",
  // integer >0；绑定代次。
  "epoch": 1,
  // string；bindings.display_name，未设置时使用既有设备名称/ID。
  "display_name": "我的 Clip",
  // integer；binding_profiles.revision，上传配置版本。
  "revision": 1,
  // 已验证固件信息；无可信来源时 null。
  "firmware": null,
  // 已验证设备能力；无可信来源时 null。
  "capabilities": null,
  // 遥测；value 缺少有效来源时为 null，sampled_at/source 同时为 null。
  "telemetry": {
    // value 为 boolean|null；在线状态。
    "online": {
      // boolean|null；在线状态。
      "value": null,
      // integer|null；遥测采样时间，UTC Unix 毫秒。
      "sampled_at": null,
      // string|null；可信数据来源标识，缺失时为 null。
      "source": null
    },
    // value 为 integer 0–100|null；电量百分比。
    "battery": {
      // integer 0–100|null；电量百分比。
      "value": null,
      // integer|null；遥测采样时间，UTC Unix 毫秒。
      "sampled_at": null,
      // string|null；可信数据来源标识，缺失时为 null。
      "source": null
    },
    // value 为非负 integer|null；待上传片段数。
    "pending": {
      // 非负 integer|null；待上传片段数。
      "value": null,
      // integer|null；遥测采样时间，UTC Unix 毫秒。
      "sampled_at": null,
      // string|null；可信数据来源标识，缺失时为 null。
      "source": null
    }
  },
  // 仅激活响应返回；列表不返回配置/凭证，响应 no-store。
  "configuration": {
    // string；与外层 device_id 相同。
    "device_id": "demo-device",
    // string；与外层 device_uid 相同。
    "device_uid": "0011223344556677",
    // string；configuration.owner_id = accounts.user_id，由 Server 确定。
    "owner_id": "demo-user",
    // string；与外层 binding_id 相同。
    "binding_id": "demo-binding",
    // integer；与外层绑定代次相同。
    "epoch": 1,
    // integer；与外层配置版本相同。
    "revision": 1,
    // string；由既有接入组件提供的设备上传地址，host:port；本文不定义传输细节。
    "endpoint": "upload.example.com:9528",
    // string；设备上传凭证，仅经受控 BLE 配置写入设备。
    "device_token": "example-device-token"
  }
}
```

列表外层结构：

```jsonc
{
  // array；GET /devices 的设备对象数组；示例为空列表。
  "items": []
}
```

### 录音详情与列表

详情对象如下；列表 items 返回 id、time_source、recorded_at、received_at、duration_ms、audio_state、transcript_state、preview_text、partial、result_stale。列表外层为 `{items:[...],next_cursor:null}`，next_cursor 为不透明字符串或 null。

```jsonc
{
  // string；recordings.id。
  "id": "demo-recording",
  // enum；device_unverified / server_received / client_confirmed。
  "time_source": "server_received",
  // integer|null；录音时间，仅 client_confirmed 时用于日期筛选。
  "recorded_at": null,
  // integer；首次收件时间，UTC Unix 毫秒。
  "received_at": 1793318400000,
  // integer|null；当前可定位连续音频前缀的时长，毫秒。
  "duration_ms": 5800,
  // enum；pending / partial / ready / failed，表示当前已收输入的音频进度。
  "audio_state": "ready",
  // enum；not_configured / pending / partial / ready / failed。
  "transcript_state": "ready",
  // string；已发布快照的第一句；快照无成功文字或静音时为空字符串。
  "preview_text": "我们确认一下今天的安排。",
  // enum；unknown / gap / confirmed_complete，由接入侧可信元数据确定。
  "integrity": "unknown",
  // integer >=0；原件、可见片段结果/文件状态或完整性变化时增加。
  "content_revision": 1,
  // integer；已发布快照对应的 content_revision；允许跳号，未发布为 0。
  "result_revision": 1,
  // boolean；content_revision > result_revision，新内容尚未进入当前快照。
  "result_stale": false,
  // boolean；快照存在缺口或未获录音闭合确认；没有快照时为 true。
  "partial": true,
  // string|null；按段号取首个 decode_error_code；wav_state=missing 且无该错误码时使用 audio_unavailable。
  "audio_error_code": null,
  // string|null；按段号取首个 asr_error_code，再取当前内容版本 merge_error_json.code；返回字符串或 null。
  "transcript_error_code": null,
  // object；链接共用 result_revision；无可用结果时对应值为 null。
  "links": {
    // 有已发布的可定位音频清单时提供；返回片段播放清单。
    "audio": "/api/boa/v1/recordings/demo-recording/audio?revision=1",
    // 有已发布的成功文字结果时提供；允许明确标记的 partial 或成功静音。
    "transcript": "/api/boa/v1/recordings/demo-recording/transcript?revision=1",
    // 同版本文字可读时提供；按请求生成，不检查字幕文件。
    "vtt": "/api/boa/v1/recordings/demo-recording/transcript.vtt?revision=1",
    // 文字可读时提供，从同版本 JSON 生成。
    "markdown": "/api/boa/v1/recordings/demo-recording/transcript.md?revision=1"
  }
}
```

录音分页外层结构：

```jsonc
{
  // array；录音列表对象数组；字段为详情对象中注明的列表字段。
  "items": [],
  // string|null；Server 生成的不透明游标，末页或空列表为 null。
  "next_cursor": null
}
```

Server 在同一读事务中根据 segment 计算当前进度；duration、preview、partial 和 links 则读取已提交快照。result_stale 表示有新内容待汇总。ready 只表示已收到的内容处理完成，录音是否完整由 integrity 表示。导出失败不改变识别结果，错误字段没有对应错误时返回 null。

from/to 为 YYYY-MM-DD，默认时区 Asia/Shanghai，结束日包含当天。列表按有效录音时间/id 降序：recorded_at 非空且 time_source=client_confirmed 时使用 recorded_at，其余使用 received_at。默认 30 条、上限 100；筛选改变时重置游标，空列表返回 items=[]、next_cursor=null。

音频、JSON、VTT 和 Markdown 的请求、返回格式与错误码见[音频接口](docs/audio-processing.md#media-api)。错误对象如下；401 会话失效、403 权限/CSRF、404 不存在或跨 owner、409 状态冲突、422 参数错误、503 依赖不可用。

```jsonc
{
  // object；错误类型与可展示说明，不包含文件路径、凭证或堆栈。
  "error": {
    // string；稳定错误码，供 Web 判断。
    "code": "recording_revision_changed",
    // string；可展示说明。
    "message": "录音版本已更新，请重新读取。"
  },
  // string；本次请求标识，用于服务端日志定位。
  "request_id": "example-request"
}
```

### 播放与导出接口

以下接口均使用录音详情返回的 result_revision；详细请求、响应和错误规则见[媒体 API](docs/audio-processing.md#media-api)。

| 方法与路径 | 返回内容 |
|---|---|
| GET `/recordings/{id}/audio?revision=N` | 按 segment 排序的播放清单 |
| GET / HEAD `/recordings/{id}/segments/{segment_id}.wav?revision=N` | 清单引用的片段 WAV，支持单范围 Range |
| GET `/recordings/{id}/transcript?revision=N` | schema_version=3 的汇总文字与 coverage |
| GET / HEAD `/recordings/{id}/transcript.vtt?revision=N` | 从同版本快照生成的 VTT |
| GET / HEAD `/recordings/{id}/transcript.md?revision=N` | 从同版本快照生成的 Markdown |

音频清单使用 segment_id 标识片段，不直接暴露磁盘路径。state=missing 时 url 为 null。若服务端已切换快照版本，返回 409 recording_revision_changed，Web 重新获取详情及链接。

<a id="oauth"></a>

## 4. 登录与会话

Web 通过顶层导航发起 Google 登录。Google 授权后回调 Server，Server 校验本次 state 和 Google ID token，按 google_sub 找到或建立 accounts 用户，再创建本站 session、设置 Cookie，303 返回 `/`。后续请求使用本站 Cookie。

- GET `/auth/google/start`：302 跳 Google；scope 为 openid email profile，使用 Code / OIDC + S256 PKCE
- GET `/auth/google/callback`：Google 成功返回 code、state，取消时返回 error、state；校验后设置会话 Cookie 并 303 到 `/`；取消授权返回 `/?login_error=login_cancelled`
- GET `/auth/session`：200 返回下方用户与 CSRF 对象；失效返回 401 session_expired
- DELETE `/auth/session`：校验 Origin/CSRF，删除当前会话、清 Cookie，返回 204；已失效返回 401，Web 同样清理本地状态

- 登录临时状态：Server 内存，5 分钟、一次消费；临时 Cookie 为 Secure/HttpOnly/SameSite=Lax
- 本站 session：Server 内存，闲置 24 小时、最长 7 天；Cookie 为 Secure/HttpOnly/SameSite=Strict、Path=/、host-only、Max-Age=604800
- 退出、到期、Server 重启：会话失效，重新 Google 登录；账号和业务数据继续保留

GET `/auth/session` 成功响应：

```jsonc
{
  // object；从 accounts 读取的本站用户。
  "user": {
    // string；accounts.user_id。
    "user_id": "demo-user",
    // string；accounts.email。
    "email": "user@example.com",
    // string；accounts.display_name，允许空字符串。
    "display_name": "示例用户"
  },
  // string；当前会话的 CSRF token，写请求放入 X-CSRF-Token。
  "csrf_token": "example-csrf-token"
}
```

本站会话仅在 Server 内存保存，以下字段不返回客户端：

```jsonc
{
  // string；随机会话 token 的摘要，Cookie 仅持有原 token。
  "token_hash": "example-token-hash",
  // string；对应 accounts.user_id。
  "user_id": "demo-user",
  // integer；登录时 accounts.auth_version，请求时须与账号当前值一致。
  "auth_version": 1,
  // string；与客户端写请求比对的 CSRF token。
  "csrf_token": "example-csrf-token",
  // integer；最近活动时间，用于 24 小时闲置到期。
  "last_seen_at": 1793318400000,
  // integer；首次创建时间 + 7 天，活动不会延长此时间。
  "absolute_expires_at": 1793923200000
}
```

账号禁用返回 403 account_disabled，身份映射冲突返回 409 account_identity_conflict；回调错误返回 400 login_invalid_or_expired，Google 不可用返回 503 login_unavailable。登录响应和会话接口设置 no-store，日志使用脱敏格式。

服务器配置 GOOGLE_CLIENT_ID、GOOGLE_CLIENT_SECRET、PUBLIC_WEB_ORIGIN。Google Console 回调登记为 `PUBLIC_WEB_ORIGIN/api/boa/v1/auth/google/callback`，与请求保持完全一致。协议使用 [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect)。

<a id="ble"></a>

## 5. 设备与请求规则

- 绑定：验证登记与 owner；本人重复激活复用绑定，未登记到当前用户的 device_uid 返回 409 enrollment_required
- 配置确认：Web 经 BLE 写入后读回 binding/epoch/revision，再提交 device_uid、binding_id、revision、saved
- 改名：更新本人 active binding 的 display_name；设备身份和上传凭证保持原值
- 移除：撤销上传凭证；device_cleanup_pending 沿用现有维护确认；已上传录音保留原 owner
- Wi-Fi：Clip 扫描 `{ssid,rssi,security}[]`，选择结果后经 BLE 写入密码，读取 saved/connected/error；密码在调用结束后清空
- 设备能力：以真实 capability 为准；已保存网络最多 5 个，基线为 2.4 GHz WPA2
- 请求管理：切换用户/数据时取消旧请求，退出清理音频和定时器；409 recording_revision_changed 时重新取版本
- 轮询：录音可见 5 秒、设备可见 15 秒；隐藏后 30 秒，恢复可见立即刷新

Clip Wi-Fi 扫描结果由 Web 的 BLE 适配层读取：

```jsonc
[
  {
    // string；Clip 扫描到的网络 SSID，Web 从此列表选择。
    "ssid": "Example-WiFi",
    // integer；信号强度 dBm。
    "rssi": -55,
    // string；设备返回的安全类型，当前基线 WPA2。
    "security": "WPA2"
  }
]
```

迁移沿用旧 user_id，先核验 owner/邮箱映射；缺项返回 migration_owner_mapping_required。迁移与 user_version 更新同事务；registry 增量检查字段后执行，INSERT 使用显式列名。

<a id="sql"></a>

## 6. 数据库 DDL

<a id="business-sql"></a>

### 6.1 业务 SQLite

运行时每个数据库连接都设置 foreign_keys=ON、synchronous=FULL、busy_timeout=5000；两个库分别提交，跨库顺序见音频文档。

```sql
-- v3 按五分钟片段处理的新库参考：三张业务表；此段不是旧库迁移脚本。
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA busy_timeout=5000;
BEGIN IMMEDIATE;
CREATE TABLE accounts (
  user_id TEXT PRIMARY KEY NOT NULL,
  google_sub TEXT UNIQUE CHECK(google_sub IS NULL OR length(google_sub) BETWEEN 1 AND 255),
  email TEXT NOT NULL UNIQUE COLLATE NOCASE
    CHECK(email=trim(email) AND length(email) BETWEEN 3 AND 254 AND instr(email,'@')>1),
  display_name TEXT NOT NULL DEFAULT '' CHECK(length(display_name)<=100),
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','disabled')),
  auth_version INTEGER NOT NULL DEFAULT 1 CHECK(auth_version>0),
  last_login_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE recordings (
  id TEXT PRIMARY KEY NOT NULL, owner TEXT NOT NULL REFERENCES accounts(user_id),
  source_namespace TEXT NOT NULL, binding_epoch INTEGER NOT NULL CHECK(binding_epoch>0),
  source_session TEXT NOT NULL,
  recorded_at INTEGER, time_source TEXT NOT NULL CHECK(time_source IN ('device_unverified','server_received','client_confirmed')),
  received_at INTEGER NOT NULL, last_received_at INTEGER NOT NULL,
  integrity TEXT NOT NULL DEFAULT 'unknown' CHECK(integrity IN ('unknown','gap','confirmed_complete')),
  content_revision INTEGER NOT NULL DEFAULT 0 CHECK(content_revision>=0),
  result_revision INTEGER NOT NULL DEFAULT 0 CHECK(result_revision>=0 AND result_revision<=content_revision),
  result_json TEXT, merge_error_json TEXT,
  updated_at INTEGER NOT NULL,
  UNIQUE(source_namespace,binding_epoch,source_session), UNIQUE(id,owner),
  CHECK((result_revision=0 AND result_json IS NULL) OR (result_revision>0 AND result_json IS NOT NULL)),
  CHECK(result_json IS NULL OR CASE WHEN json_valid(result_json) THEN
    json_type(result_json)='object' AND length(CAST(result_json AS BLOB))<=16777216
    AND COALESCE(json_type(result_json,'$.revision')='integer'
      AND json_extract(result_json,'$.revision')=result_revision,0) ELSE 0 END),
  CHECK(merge_error_json IS NULL OR CASE WHEN json_valid(merge_error_json) THEN
    json_type(merge_error_json)='object' AND length(CAST(merge_error_json AS BLOB))<=65536 ELSE 0 END)
);
CREATE INDEX recordings_owner_date ON recordings(owner,recorded_at DESC,id DESC);
CREATE INDEX recordings_owner_received ON recordings(owner,received_at DESC,id DESC);
CREATE INDEX recordings_pending_merge ON recordings(updated_at,id) WHERE content_revision>result_revision;
CREATE TABLE recording_segments (
  id TEXT PRIMARY KEY NOT NULL, owner TEXT NOT NULL, recording_id TEXT NOT NULL,
  source_namespace TEXT NOT NULL, source_id TEXT NOT NULL,
  segment_no INTEGER NOT NULL CHECK(segment_no>0),
  -- 业务库只导入 ready 原件，接收状态由来源组件管理。
  raw_relative_path TEXT NOT NULL UNIQUE,
  size_bytes INTEGER NOT NULL CHECK(size_bytes>0),
  sha256 TEXT NOT NULL CHECK(length(sha256)=64),
  received_at INTEGER NOT NULL, imported_at INTEGER NOT NULL,
  sample_count INTEGER CHECK(sample_count>0 AND sample_count<=4800000),
  process_config_json TEXT,
  decode_state TEXT NOT NULL DEFAULT 'pending' CHECK(decode_state IN ('pending','running','retry_wait','ready','failed')),
  decode_attempt INTEGER NOT NULL DEFAULT 0 CHECK(decode_attempt BETWEEN 0 AND 4),
  decode_run_after INTEGER NOT NULL, decode_error_code TEXT,
  wav_state TEXT NOT NULL DEFAULT 'none' CHECK(wav_state IN ('none','ready','missing')),
  wav_relative_path TEXT UNIQUE, wav_size_bytes INTEGER CHECK(wav_size_bytes>0),
  wav_sha256 TEXT CHECK(length(wav_sha256)=64),
  -- 导入器须根据 ASR 是否可用显式写入 pending 或 not_configured。
  asr_state TEXT NOT NULL DEFAULT 'pending' CHECK(asr_state IN ('not_configured','pending','running','retry_wait','ready','failed')),
  asr_attempt INTEGER NOT NULL DEFAULT 0 CHECK(asr_attempt BETWEEN 0 AND 4),
  asr_run_after INTEGER NOT NULL, asr_error_code TEXT,
  transcript_json TEXT,
  updated_at INTEGER NOT NULL,
  UNIQUE(source_namespace,source_id), UNIQUE(recording_id,segment_no),
  FOREIGN KEY(recording_id,owner) REFERENCES recordings(id,owner),
  CHECK(wav_state='none' OR (sample_count IS NOT NULL AND wav_relative_path IS NOT NULL
    AND wav_size_bytes IS NOT NULL AND wav_sha256 IS NOT NULL)),
  CHECK(decode_state<>'ready' OR (wav_state='ready' AND process_config_json IS NOT NULL)),
  CHECK(asr_state<>'ready' OR transcript_json IS NOT NULL),
  CHECK(process_config_json IS NULL OR CASE WHEN json_valid(process_config_json) THEN
    json_type(process_config_json)='object' AND length(CAST(process_config_json AS BLOB))<=65536 ELSE 0 END),
  CHECK(transcript_json IS NULL OR CASE WHEN json_valid(transcript_json) THEN
    json_type(transcript_json)='object' AND length(CAST(transcript_json AS BLOB))<=8388608
    AND COALESCE(json_type(transcript_json,'$.schema_version')='integer'
      AND json_extract(transcript_json,'$.schema_version')=3
      AND json_extract(transcript_json,'$.time_unit')='ms'
      AND json_type(transcript_json,'$.cues')='array',0) ELSE 0 END)
);
CREATE INDEX segments_decode ON recording_segments(decode_state,decode_run_after);
CREATE INDEX segments_asr ON recording_segments(asr_state,asr_run_after);
-- 每段保存一份 WAV 和识别结果；cue 时间范围等由应用层校验。
-- 单工作者持操作系统独占锁，解码和 ASR 各自保存执行次数。
PRAGMA user_version=3;
COMMIT;
```

<a id="registry-sql"></a>

### 6.2 设备与上传 SQLite（registry）增量

```sql
-- 复用既有设备与上传 SQLite（registry）中的表：新增 0 张表。设计参考，真实迁移先检查 table_info。
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


## 7. 设置与启动配置

Server 使用以下环境变量。启动程序尚未实现，ExecStart 命令待实现时补充。

### 7.1 数据库与文件地址

配置文件为 `/etc/speaker/server.env`，由启动项加载。主盘和副本盘必须是独立磁盘或独立存储卷；同一磁盘的两个目录不能提供坏盘保护。DB 地址填写主盘 SQLite 文件的绝对路径，音频和备份填写目录绝对路径。

```dotenv
# 两个独立磁盘的挂载目录，启动时须确认均已挂载。
SPEAKER_PRIMARY_ROOT=/mnt/speaker-primary
SPEAKER_REPLICA_ROOT=/mnt/speaker-replica
# 在线数据库仅在主盘打开；副本通过 SQLite backup API 生成。
SPEAKER_REGISTRY_DB_PATH=/mnt/speaker-primary/db/registry.sqlite3
# 业务 SQLite：账号、录音、原始片段、片段处理状态及转写 JSON。
SPEAKER_BUSINESS_DB_PATH=/mnt/speaker-primary/db/business.sqlite3
# 私有音频目录：raw 原件、每段 WAV 和处理临时文件；字幕不落盘。
SPEAKER_STORAGE_ROOT=/mnt/speaker-primary/audio
# 副本中的相对目录相同，例如 /mnt/speaker-replica/audio/derived/...。
# 数据库检查点保存在副本盘 checkpoints/；默认每 60 秒检查一次是否需要更新。
SPEAKER_DB_REPLICA_INTERVAL_SECONDS=60
# 每日保留完整版本备份，避免误修改直接影响所有恢复点。
SPEAKER_BACKUP_ROOT=/mnt/speaker-replica/backups

# 设备每段最多 5 分钟，Server 直接识别整段；超时按 ASR 服务性能调整。
SPEAKER_ASR_TIMEOUT_SECONDS=600
# ASR 端点、模型、输入上限、凭证及版本另由服务端部署配置登记。
# 未登记有效 ASR 配置时仍解码并播放，文字状态为 not_configured。

# Web 对外 HTTPS 地址及 Google 登录配置。
PUBLIC_WEB_ORIGIN=https://speaker.example.com
GOOGLE_CLIENT_ID=replace-with-google-client-id
GOOGLE_CLIENT_SECRET=replace-with-google-client-secret
```

- `SPEAKER_REGISTRY_DB_PATH` 与 `SPEAKER_BUSINESS_DB_PATH` 指向两个不同的文件；`registry.sources` 是 registry 库中的表引用，不是文件名。
- 数据库和音频目录必须位于 SPEAKER_PRIMARY_ROOT 下，副本按相对路径写入 SPEAKER_REPLICA_ROOT。数据库副本写入 checkpoints/，不会作为另一组在线数据库同时打开。数据库连接使用第 6 节的 PRAGMA。
- 两个挂载点须可读写并启用存储加密，数据库目录允许服务账号创建 WAL/SHM。启动检查挂载标识以排除同一文件系统，并在部署时确认两者具有独立故障域；不能在挂载缺失时创建普通目录继续运行。
- 数据目录权限为 0700，数据库及 WAL/SHM、音频和配置文件权限为 0600。配置文件由服务端受控保存，真实凭证不提交到仓库。

### 7.2 启动项加载配置

Linux 使用 systemd 时，在 Server 服务单元的 `[Service]` 中加载同一份配置文件：

```ini
[Service]
EnvironmentFile=/etc/speaker/server.env
```

将以上配置加入 Server 的 systemd 服务单元，ExecStart 填写实际启动命令。EnvironmentFile 路径不加 `-` 前缀，文件缺失时启动失败。所有数据路径从环境变量读取，与启动目录无关。

修改配置或启动项后，重启对应 Server 服务；修改 systemd 单元时先执行 `systemctl daemon-reload`。磁盘或数据库地址变更须先停写，按[双盘恢复流程](docs/audio-processing.md#disk-recovery)校验并迁移两个库和关联文件，再修改路径；仅修改环境变量不会复制或修复数据。

### 7.3 启动检查

- 检查绝对路径、主盘/副本盘挂载与独立性、加密卷及权限，两个在线数据库不得指向同一文件。任一盘不可写时拒绝启动；运行中失效则暂停新增持久写入并告警，主盘仍完好时可继续已有结果读取。
- 首次部署按第 6 节初始化数据库；已有部署检查数据库版本并执行迁移。配置指向的既有数据库缺失时应报错，避免误建空库后继续运行。
- 校验备份目录、加密密钥与用户额度配置；要求与[音频存储及恢复设计](docs/audio-processing.md#security)一致，未满足时拒绝启动。
- 配置 ASR 时确认服务支持 300 秒、16 kHz 单声道 PCM16 WAV（PCM 为 9,600,000 字节，另加文件头）；能力不足时拒绝启用该配置，不自动细分片段。首次识别前固定配置，失败重试沿用原模型。
- 在业务 DB 同目录对 speaker.worker.lock 取得排他 flock 并持有至后台退出；第二实例启动失败。只运行一个应用进程和一个工作者，不使用多 worker 或热重载重叠实例。
- 持锁后恢复遗留 running（保留已执行次数）、对账来源和 WAV；开放 HTTP API、原件导入与开始新处理前完成派生/临时目录孤儿清理，运行期间不做孤儿删除。随后按内容/结果版本差更新快照。原件导入与后台循环分离，子进程或网络调用不能阻塞 Web 事件循环。
