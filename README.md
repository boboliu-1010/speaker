# 录音助手 · Server + Web 完整设计与开发计划

版本：v1 · 2026-10-29 · 状态：开发设计

**一个服务、两个页面、四张业务表。** Google 登录与会话留内存；识别原文存 SQLite；保留 raw + WAV，支持 Markdown / VTT。

参考：[产品原型](https://comfy-faloodeh-ec9b57.netlify.app/) · [代码仓库](https://github.com/BofAI/reSpeaker_Clip)。设计覆盖 Web、Server、数据存储、设备接入和开发验收。

<a id="contents"></a>

[产品功能](#scope) · [架构](#system-architecture) · [Google 登录](#google-login) · [设备与 Wi-Fi](#devices) · [录音处理](#ingest) · [转写格式](#transcript-format) · [Web/API](#web) · [四表设计](#sqlite-model) · [开发任务](#implementation) · [SQL](#sql) · [评审与验收](#self-review)

<a id="scope"></a>

## 1. 产品功能

![产品功能](docs/assets/diagrams/00-product-overview.svg)

<details>
<summary>展开实现细则</summary>

| 页面或模块 | 开发内容 |
|---|---|
| 登录/账号 | Google OAuth 2.0 / OIDC 登录；基本用户落库，临时状态与本站会话只在内存。账号菜单显示邮箱和退出 |
| 录音列表 | 按日期分组、开始/结束日期筛选、时长、转写开头预览、真实上传/处理状态 |
| 录音详情 | 日期时间标题、文字和 A/B 等说话人标签、基础播放/暂停/进度、复制文字 |
| 下载 | WAV 音频、Markdown 文字和 WebVTT 字幕文件 |
| 添加设备 | 准备 → BLE 连接 → 自动激活/凭证配置/校时 → Wi-Fi → 完成 |
| 设备卡片 | 名称、版本、可信的状态/电量/待上传信息、Wi-Fi 添加/删除、改名、移除 |
| Server 内部 | 原始文件与 WAV 双保留、SQLite 入库、ASR/VTT、持久任务和文件恢复、同用户鉴权 |

设备维护复用现有固件工具。Server 持续保存上传原件和已生成的录音文件。

</details>

<a id="system-architecture"></a>

## 2. 架构与模块

![部署架构](docs/assets/diagrams/01-system-architecture.svg)


<details>
<summary>展开实现细则</summary>

沿用 Python/FastAPI 单个常驻进程、静态 HTML/CSS/ES modules、SQLite、本机持久目录。Web HTTPS 9529 与 HTTPS API 9528 共享后台，Clip 使用 UDP/DTLS 9528。媒体工具是有超时/资源限制的子进程；ASR 使用配置的私有端点。数据目录由单进程持锁使用，解码在受控子进程执行。

模块只按职责拆：`auth`（Google 登录/内存会话）、`users`（基本资料）、`devices`（既有绑定适配）、`recordings`（来源/列表）、`jobs`（一个活动处理任务）、`files`（持久发布/恢复）、`decode`（WAV）、`transcript`（ASR/cues/VTT）、`routes`（同源 API）。

Web 的 `/api/boa/v1` 在 9529 同源转交同进程处理；浏览器通过 9529 同源入口调用 API。旧 9528 接口继续服务原有客户端。Google 回调也固定在 9529 的公开 HTTPS origin；反向代理场景只信任显式配置的代理，回调地址取自固定配置。

浏览器可见时每 5 秒更新活动录音、每 15 秒更新设备；隐藏后降到 30 秒，恢复时立即更新。页面数据通过轮询更新。

</details>

<a id="user-model"></a>
<a id="google-login"></a>

## 3. 基本用户与会话

![Google 登录与内存会话](docs/assets/diagrams/09-google-memory-login.svg)


<details>
<summary>展开实现细则</summary>

`accounts` 保留 9 个字段：`user_id`、`google_sub`、`email`、`display_name`、`status`、`auth_version`、`last_login_at`、`created_at`、`updated_at`。内部 user_id 关联所有 owner，既有用户沿用旧 ID；google_sub 唯一，旧用户迁移未核验时允许为空。邮箱设置唯一约束，身份匹配以 google_sub 为准；头像首字母从名字/邮箱派生。

状态只有 active/disabled。登录使用 Google OAuth 2.0 Authorization Code + OpenID Connect；具体参数见[Google 登录数据定义](#google-login)。登录临时数据和会话保存在进程内存。每个请求重新核对 accounts.status/auth_version；已有 Bearer 兼容身份也执行相同的状态检查。

内存保存一次性登录状态（5 分钟）和本站会话（闲置 24 小时、绝对 7 天）；随机 opaque Cookie 引用服务端会话。退出即删除，Server 重启全部失效、用户重新登录，设备上传凭证与后台任务不受影响。登录跳转的临时 Cookie 使用 Secure/HttpOnly/SameSite=Lax，本站会话使用 Secure/HttpOnly/SameSite=Strict，均为 host-only、Path=/。容量、清理和回调重放处理见下方参数。

所有读取按服务端身份过滤 owner，跨用户对象统一 404；写请求校验准确 Origin 与会话 CSRF。首次登录建立普通账号；维护操作沿用现有受控权限。

</details>

| SQLite | 内存 | 浏览器 |
|---|---|---|
| accounts、设备归属、录音、原文、任务 | 一次性 LoginFlow、Session、Google 公钥缓存 | HttpOnly Cookie；页面临时 CSRF token |
| 重启保留 | 退出/到期/重启清除 | 会话失效后重新 Google 登录 |

<details>
<summary>展开 Google 登录步骤、内存结构与异常处理</summary>

### Google 接入

1. 配置 Google Web application client、同意屏幕和精确的 HTTPS 回调 URI。申请 `openid email profile`，采用在线登录模式。Client secret 由服务器环境变量或私密配置加载。
2. `GET /api/boa/v1/auth/google/start` 创建高熵 state、nonce、浏览器绑定值和 S256 PKCE verifier；LoginFlow 放有界内存 map。设置 5 分钟临时 `__Host-boa_oauth` Cookie，然后 302 跳 Google。使用 Authlib 处理授权码流程，启用 S256 PKCE，并将 LoginFlow 存储适配到服务端内存。
3. 回调是 `GET /api/boa/v1/auth/google/callback?code=&state=`。先匹配未过期 state 与临时 Cookie 的摘要，再原子取走 LoginFlow，随后交换 code。重复回调或 nonce/签名验证失败时，清理本次流程并要求重新登录。Google 拒绝授权时清理匹配的流程并回登录页。
4. 通过标准 Google ID token 验证库校验签名、Google issuer、本站 client_id/audience、到期时间，再比较 nonce；多 audience 时校验 azp，要求有效 sub、email 和 `email_verified=true`。身份字段取自验证通过的 ID token。公钥允许按缓存头有界缓存；网络/密钥服务不可用时拒绝本次新登录。后续请求使用本站会话鉴权。
5. 按 google_sub 同步 accounts，沿用稳定 user_id。首次登录建立用户；相同 sub 复用；同邮箱不同 sub 或邮箱更新撞已有账号时返回 `409 account_identity_conflict`，保留现有账号归属并终止本次登录。旧 sub 为空的用户只能经维护侧核实映射。禁用账号返回 403。
6. 生成新的本站随机 session token 和 CSRF token，内存登记后设置会话 Cookie，清临时 Cookie，303 到固定 `/`。登录完成后固定返回首页。Google access/id token 在校验结束后释放引用；日志和错误响应仅保留错误码与请求 ID。
7. 静态首页加载后通过同源 `GET /auth/session` 取得基本资料和 CSRF token；响应 `Cache-Control: no-store`。会话 Cookie 设置 HttpOnly；CSRF token 只保存在页面内存。退出 `DELETE /auth/session` 校验 Origin/CSRF 后删会话、清 Cookie，并通知其他标签停止播放/请求。退出操作清理本站会话，设备继续使用独立上传凭证。

### 最少内存结构

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

</details>

<a id="devices"></a>

## 4. 设备添加、Wi-Fi 与移除

![设备添加界面](docs/assets/diagrams/03-device-onboarding.svg)


![Clip 扫描与选网](docs/assets/diagrams/08-wifi-configuration.svg)

<details>
<summary>展开实现细则</summary>

1. 用户在空录音页或设备页点击添加，主动打开 BLE 选择器。
2. 连接后读取完整 UID、固件和能力；设备身份使用完整 UID。
3. Server 根据已验证用户与**既有可信设备登记/凭证依据**取得或建立绑定，申请设备上传凭证。已属其他用户则拒绝；同用户重复请求复用同绑定，保留有效凭证。
4. Web 通过 BLE 写入上传配置，读回 binding/epoch/revision，再上报确认；同步设备时间，区分“客户端写入”与“实际收件”。
5. 通过 BLE 请求 Clip 扫描周围 Wi-Fi；用户从返回列表选择 SSID、输入密码、写入设备并读取连接结果，完成后回到列表。网页关闭不影响后续设备自行上传。

设备激活接入现有受控登记和凭证发放机制。Server 校验登记依据、当前归属与上传凭证，Web 写入配置后读取 binding、epoch 和 revision 完成确认。实机验收包含凭证写入、配置读回和真实上传。

### Wi-Fi：Clip 扫描，Web 选择设置

Web 通过 BLE 请求目标 Clip 扫描周围 Wi-Fi，显示设备返回的列表。用户选择 SSID、填写密码后，通过 BLE 将配置写回设备。

1. 先连接目标 Clip；Web 发 `scanWifi()`，由 Clip 实际执行无线扫描。
2. Clip 通过 BLE 返回可用 SSID、信号强度和安全类型；Web 显示列表与重新扫描按钮。扫描结果与已保存配置分别展示。
3. 用户选择列表中的网络，输入密码；页面保留选中的 SSID。
4. Web 经 BLE 将选中 SSID/密码交给 Clip，由设备保存并尝试连接；密码仅在本次页面交互和 BLE 写入期间使用，完成后清空。
5. 读取 Clip 的保存/连接结果，分别显示“已保存”“连接中”“已连接”或具体失败；密码错误允许重输，扫描为空/超时允许重扫。保存成功、Wi-Fi 已连接、Server 已收件分别展示。

已保存网络支持查看和删除；数量以设备实际容量为准，上限 5 个。扫描、保存和连接结果由固件返回。固件缺少所需能力时显示具体原因。无线兼容基线为 2.4 GHz WPA2。

### 设备卡片

改名写既有 registry.bindings.display_name，更新时同时核对 owner、binding_id 与 active；未命名回退既有显示名/设备 ID。别名随绑定隔离，UID 和上传凭证保持原值。设备卡片展示固件版本。在线、电量、待上传数必须有来源和采样时间；只有最近收件证据时显示“最近收件/状态未知”。移除先撤销服务端上传凭证，尝试清理在线 BLE 上传配置；离线清理失败沿用既有交接锁。**已上传录音保留原 owner**，重新添加走受控绑定。

</details>

<a id="ingest"></a>

## 5. 收件、录音聚合与原件保留

![收件与数据投影](docs/assets/diagrams/04-raw-ingest-outbox.svg)


<details>
<summary>展开实现细则</summary>

保持 v3 原协议：数据 fsync → 持久检查点 → 整文件 size/hash 校验 → rename/目录 fsync。只有 raw 和可恢复归属的身份元数据持久后才回 COMPLETE，WAV、ASR 和 VTT 由后台独立处理。设备凭证撤销后拒绝上传；旧绑定的历史文件仍属原用户。

既有 registry 的 `sources` ready 行就是持久待投影项，通过 projected_at 记录投影进度。消费者在 business 单事务建立/更新 recording 与 recording_segments；同一片段行保存 raw 路径/size/hash，并以唯一 `(source_namespace,source_id)` 兼作来源收据。业务事务成功后才标 projected_at。文件已落盘但索引失败，可从既有 identity/raw 对账；业务已提交但未标记时重放，ready→ready 且 hash 相同时保留当前版本，hash 冲突拒绝。启动分批核对全部 ready 来源。

录音按 `(source_kind, source_namespace, binding_epoch, source_session)` 聚合；新 ready 片段才递增 input_revision，重复 source 保持当前版本。App 上传继续通过现有接口接入。可定期读取已有 receiving 索引创建上传中的录音元信息，片段收完整并校验后标记 ready、创建处理任务。

接收期间显示“已收到 N 个片段/完整性未知”。片段连续且静默 10 分钟后，处理当前已收内容；缺号时等待补齐。后续片段到达后递增输入版本并更新 WAV 与转写。整段完整性依据设备协议提供的闭合信息判断。

</details>

<a id="recording-decode"></a>

## 6. raw + WAV 双保留

![文件存储与解码规范](docs/assets/diagrams/05-decode-and-retain.svg)


<details>
<summary>展开实现细则</summary>

- Clip raw 格式为 `uint16 little-endian length + raw Opus packet`；先检查包边界/时长/声道，再正确封装或用受控解码器处理。
- 校验 raw hash 后解码为 **16 kHz、mono、PCM16 little-endian WAV**。逐段临时解码，再按冻结片段顺序合为一份 `recording.wav`，记录样本数、长度和独立 hash。
- 已发布 WAV 同时用于播放、ASR 和下载。临时分段文件成功后清理；原始文件始终保留。
- 内部存储路径按 raw 来源或 job/attempt 与输入版本确定；当前播放与更新使用独立路径。当前指针只指向 jobs 中 ready 的文件；旧派生文件在任务与读取释放引用后清理，raw 持续保留。
- Ogg granule 的 48 kHz 时基与 PCM 16 kHz 区分；raw 没有 pre-skip 元数据时保留当前样本策略并标明时间来源。样本数与时间轴保持一致，解码错误返回具体原因。

单 raw 段遵守既有 8 MiB 上限，连续录音处理默认上限 8 小时。16 kHz mono PCM16 约 115.2 MB/小时，先检查磁盘预算与工具超时；超限留 raw 并给出可恢复失败。下载按钮标为“下载音频（.wav）”，文件由设备 raw 解码生成。

</details>

<a id="dual-write"></a>

## 7. 任务兼作文件索引与发布恢复

![文件发布与恢复状态](docs/assets/diagrams/06-file-database-publication.svg)


<details>
<summary>展开实现细则</summary>

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

</details>

<a id="vtt"></a>
<a id="transcript-format"></a>

## 8. 转写与 WebVTT

![转写原文存储格式](docs/assets/diagrams/10-transcript-format.svg)

![音频与文字版本对齐](docs/assets/diagrams/07-transcript-vtt.svg)


<details>
<summary>展开实现细则</summary>

ASR 消费当前 WAV，返回 cue 的 start_ms/end_ms/text 和可空 speaker。说话人按当前录音稳定映射为 A/B/C；供应方未提供分离结果时，speaker 保存为 null，页面显示“未区分”。

### 8.1 生成与存储

1. 校验 JSON 片段：文本非空、毫秒为整数、`0 <= start < end`、时间不超当前 WAV 时长（允许最多 1ms 表示精度误差），起点不倒序。合法的多人重叠允许保留。
2. 准备版本化 JSON `{schema_version:1,time_unit:"ms",cues:[...]}`，在步骤 5 的最终事务中整体写入 `recordings.transcript_json`，关联 transcript_revision。识别原文保存在 SQLite，VTT 和 Markdown 均由同一批 cues 生成。采用 UTF-8 纯文本、整数毫秒和可空 speaker，完整 JSON/字段/空结果约定见[转写格式](#transcript-format)及下方 [JSON 示例](#json-example)。text 使用 UTF-8 纯文本。
3. 生成 UTF-8 `transcript.vtt`，使用 `WEBVTT` 文件头、空行、稳定 cue 编号、`HH:MM:SS.mmm --> HH:MM:SS.mmm` 和可选 voice 标签。说明依据：[W3C WebVTT 格式](https://www.w3.org/TR/webvtt1/)。
4. 用户文本的 `& < >` 转义，空白行规范化，speaker 标签只来自受控映射。
5. VTT 通过相同文件发布流程校验/持久，随后在短事务中提交 transcript_json、vtt_job_id 指针和 transcript_revision/state；中断时保留处理状态，重启后重做。若仅有已 rename 的 VTT 而 cues 事务未提交，恢复时先确认文字事务，尚未提交则废弃该次未提交的派生产物并用同版本 WAV 重跑 ASR，新的 cues/VTT 重新一起发布；raw/WAV 保留。

ASR 耗时不影响 WAV 播放。新 WAV 发布后，只展示与 audio_revision 相同的 cues/VTT；处理中展示当前状态。当前输入更新期间仍可保留上一份音频与同版本文字，标“更新中”；新音频替换时旧文字先隐藏。

<a id="vtt-example"></a>

### 8.2 实际 VTT 示例

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

下载 MIME 为 `text/vtt; charset=utf-8`。Web 显示文字与 speaker；时间戳用于音频定位与字幕下载。播放定位使用同一组 cues。

### 8.3 下载

导出菜单提供 WAV、Markdown 和 VTT。WAV/VTT 保存为磁盘文件，元数据位于 jobs；Markdown 按当前转写 JSON 生成，内容为日期标题、说话人和原文。

</details>

| 字段 | 格式 | 示例 |
|---|---|---|
| recording_id + revision | API 录音与版本，数据库使用 id/transcript_revision | demo-recording / 1 |
| cue_index | 从 1 开始的连续整数 | 1 |
| start_ms / end_ms | 相对当前 WAV 的整数毫秒 | 0 / 2400 |
| speaker | 稳定匿名标签或 NULL | A |
| text | UTF-8 纯文本原文 | 我们确认一下今天的安排。 |

<details>
<summary>JSON、发布事务、空结果与异常恢复</summary>

### 格式与边界

SQLite 在 `recordings.transcript_json` 存一份 `{schema_version:1,time_unit:"ms",cues:[...]}`，录音 owner 与 transcript_revision 在同一行。`text` 保存识别原文，输出 VTT 时再转义。统一 CRLF 为 LF，拒绝 NUL/非法编码与纯空白句；原有标点、中文和换行保留。speaker 只能为 A/B/C…稳定映射或 NULL，Web 用 textContent 渲染。运行日志仅保留请求 ID、阶段与错误码。

API 外层固定为 `schema_version:1, recording_id, revision, time_unit:"ms", cues:[], next_cursor`；`revision` 对应 recordings.transcript_revision，并须等于当前 audio_revision；input_revision 表示最新收到的输入版本，cue 字段名固定为 cue_index/start_ms/end_ms/speaker/text。owner 取自服务端会话。持久 JSON 保存 schema_version、time_unit、cues，接口补充录音、版本与分页字段。

供应方秒数在 adapter 中转为整数毫秒；校验 `0 <= start_ms < end_ms <= duration_ms`，最大 1ms 精度误差可夹到音频边界，夹后仍须 start < end。按 start_ms 与供应方稳定顺序排序后生成连续 cue_index；合法多人重叠保留。单句最多 10000 字符、每录音最多 100000 cues、持久 JSON 编码后最多 8 MiB UTF-8，超限报 `transcript_limit_exceeded`，整批结果保留失败状态。数字/类型/文本不合法则整批失败，返回校验错误。

静音时允许 **0 cues**：transcript_state=ready，JSON cues=[]，VTT 为 `WEBVTT\n\n`，Markdown 仅日期标题，Web 显示“未识别到文字”。ASR 未配置、失败与成功无文字是不同状态；用户仍可播放 WAV。

### 原子发布

1. ASR 读取冻结的同版本 WAV，校验并准备 cues；任务持有效 lease。
2. 从同组 cues 生成 UTF-8 VTT，转义 `& < >`，清理会破坏 cue 分隔的文本空行；text 原文不受影响。文件名/路径由 Server 生成。VTT 经当前 transcribe jobs 行保存的临时/最终路径、size/hash、publication_state 完成 fsync/rename 持久化。
3. 持录音锁，在**一个 SQLite 事务**内检查 lease、当前 input_revision/audio_revision，整体写入 transcript_json、更新 vtt_job_id/transcript_revision/transcript_state，并将对应 jobs 文件设 publication_state=ready、任务设 succeeded。任一失败全部回滚，读者继续读取已提交版本。
4. 相同任务重放保持幂等；失效 lease 不得覆盖新输入。针对尚未提交的同版本尝试，只在事务内替换待发布 transcript_json；已成功版本直接读取持久结果。新输入先隐藏不匹配的旧文字。

### 恢复与读取

| 中断位置 | 恢复动作 |
|---|---|
| cues 仅在内存 | 任务租约回收，重跑同版本 ASR |
| VTT rename 后、cues 提交前 | 将 jobs 内未提交的文件尝试标 abandoned，重新 ASR 并整体发布；通过 JSON 事务判断发布结果 |
| cues/VTT/ready 已提交、进程退出 | SQLite 直接读文字，VTT 直接下载；不重跑成功任务 |
| 成功后 VTT 文件缺失/损坏 | 保留已存 cues，当前 VTT 下载报暂不可用；维护侧从已提交同版本 cues 经文件发布恢复，不重新 ASR |
| 音频更新或请求版本不符 | 409 recording_revision_changed；Web 取消旧请求后重新加载 |

恢复时不删除任何 raw；废弃的派生产物只有在无当前指针/在途读取引用后才清理。当前 JSON 仅在新音频对应转写成功时整体替换；已开启的旧 SQLite 读取快照按 WAL 规则完成。

JSON 每页最多 200 cues，游标绑定录音/版本。每个请求在同一 SQLite 读取快照核对 owner、当前 audio_revision、transcript_revision 和 ready 状态；不匹配拒绝。复制全部文字要取完同版本全部页才写剪贴板。VTT 已持久保存，JSON 分页/Markdown 从同一 SQLite 快照的 transcript_json.cues 按数组顺序读取；可使用 json_each 分页或迭代，避免构造整批 Python cue 对象。Markdown 按句生成；三者使用相同 speaker 和文字。JSON/VTT/MD 为当前音频同版本，响应均标注 revision，下载附件固定 UTF-8 与安全 filename。

</details>

<a id="json-example"></a>

### JSON 接口示例

<details>
<summary>展开完整 JSON（与上方 VTT 同一段文字）</summary>

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

</details>

<a id="web"></a>

## 9. Web 与 API

<details>
<summary>展开实现细则</summary>

Web 提供“录音、设备”两个导航和账号菜单，产品名称为“录音助手”。

列表标题由录音时间生成，支持开始/结束日期筛选；结束日期按业务时区次日零点转 UTC 半开区间。第一版部署级业务时区默认 Asia/Shanghai。日期非法或开始晚于结束返回 422；设备时间不可信时用收件时间并提示来源。列表每页 30 条，按日期/id 稳定分页。

详情页包含文字、复制、导出与播放器。使用已有 `<audio>` 和进度控制。所有音频 Range/HEAD、VTT、Markdown 都使用同源 Cookie/Bearer + 当前 owner 直接鉴权。跨标签退出时停止音频、取消旧请求，后续 Range 拒绝。

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
| GET/HEAD `/recordings/{id}/audio.wav?revision=` | 固定音频版本，鉴权 WAV，Range 206 / 非法范围 416 |
| GET `/recordings/{id}/transcript?revision=&cursor=` | 固定版本 JSON cues，每页最多 200 条；游标绑定录音/版本 |
| GET `/recordings/{id}/transcript.vtt?revision=` | 固定音频版本的 VTT 下载 |
| GET `/recordings/{id}/transcript.md?revision=` | 固定版本 cues 生成 Markdown |
| GET `/health` | 最少服务存活信息，无用户/凭证内容 |

**跨请求版本约束：** 详情先固定 audio_revision，WAV、JSON cues、VTT、MD 请求均必须携带 revision，cue 游标也绑定 recording/revision。Server 在同一读取快照内检查请求版本为当前音频版本，文字还须匹配 transcript_revision；不匹配返回 409 `recording_revision_changed`，未就绪返回明确处理中状态。响应标注版本。列表轮询发现新音频版本或收到 409 时，Web 取消旧分页/复制、停止旧播放并重新载入详情；复制全部文字必须在全部同版本分页成功后才写剪贴板。在途读取完成后清理旧派生文件。

Wi-Fi 扫描、保存、删除通过 BLE 执行。处理暂不可用时返回具体阶段状态；语音服务未配置显示 not_configured。维护重试复用内部 job 接口/CLI。旧 API `/api/audio/*` 与设备协议保持兼容。

</details>

<a id="sqlite-model"></a>

## 10. SQLite：4 张新增业务表

![四表关系](docs/assets/diagrams/02-user-data-model.svg)

| 表 | 一条记录承载什么 |
|---|---|
| accounts | 基本用户与 Google sub，仍为 9 字段 |
| recordings | 录音状态、版本、当前文件任务指针、完整转写 JSON |
| recording_segments | 原始片段 + raw 路径/size/hash + 幂等来源收据 |
| jobs | decode/transcribe 任务 + 派生文件元数据 + 发布/恢复状态 |

<details>
<summary>展开存储职责与约束</summary>

registry.bindings 保存设备别名与绑定，registry.sources 保存来源和投影进度；业务库负责用户、录音、原始片段和处理任务。迁移版本通过 PRAGMA user_version 管理。

用户与录音为一对多，录音与原始片段、处理任务分别为一对多。文字保存为录音行中的版本化 JSON，最大 8 MiB UTF-8、100000 cues、每句 10000 字符。超限返回明确错误。API 按 200 cues 分页，使用 SQLite json_each 在读取快照中取页；导出按句读取。

recordings 的 wav_job_id/vtt_job_id 用 owner/录音/版本复合 FK 指向 jobs；文件发布与文件读取同时验证 job.kind、state/publication_state、size/hash；文字 API 独立读取录音当前 JSON，VTT 缺失时仍可读取已存文字。原件来源唯一约束负责幂等，条件更新 receiving→ready 与 input_revision 递增同事务。每次启动对账全部 registry ready 来源，分批 500 条异步执行，由后台对账线程执行。

迁移脚本保存在 Git，业务库通过 PRAGMA user_version 顺序升级并拒绝未知高版本；实施中同时把既有 registry.py 的 bindings/sources 位置式 INSERT 改为显式列名，防止 ALTER ADD COLUMN 后旧写入因列数变化失败；加入真实旧 schema 升级夹具。registry 增量先检查既有列，沿用其迁移所有权。每连接 foreign_keys=ON、busy_timeout=5000、synchronous=FULL；业务库 WAL。音频保存为磁盘文件。登录事务/会话仍只在内存。

</details>

<a id="operations"></a>

## 11. 实施与验收

<details>
<summary>展开实现细则</summary>

开发分为 **S01–S12，共 12 项任务**。先基本用户/设备链路，再收件与 WAV，接 ASR/VTT，最后完善列表/详情/设备页面与迁移验收。见[任务计划](#implementation)。

备份保持简单：停服务、持排他维护锁、整体备份 SQLite/WAL、raw、identity、配置/凭证与派生文件；私密备份不入仓库。在隔离副本迁移并核对 user_id、绑定、数量、字节和 hash；生产迁移前先完成隔离副本验证。回退前先保存新收件原件，回退时保留上线后新增录音，并核对恢复后的文件索引。

验证分层：表/约束与 API 测试；真实浏览器；真实 Clip 收件；实际 WAV 解码/播放；ASR 样本与 VTT 解析；固件能力缺项；恢复演练；实际部署。重启会清空网页登录状态，恢复后再次 Google 登录；用户、绑定、录音、任务均从持久存储恢复。

上线前完成 Google 配置、设备实测、备份恢复和部署验收。

</details>

<a id="implementation"></a>

## 12. 开发任务与实施顺序

![开发里程碑排期](docs/assets/diagrams/12-implementation-order.svg)

S01–S12，共 12 项任务、60 个步骤；实施前以本文设计和当前源码为准。推荐按顺序交付，逐项验证后提交。

<details>
<summary>依赖、文件与接口约定</summary>

### 全局约定

- 代码基线使用 BofAI/reSpeaker_Clip；实施前记录源码版本并建立独立开发分支。
- 保留单进程、一个目录锁、9529 Web、9528 HTTPS/UDP DTLS、v3 原始帧/ACK；ASR 由后台任务执行。
- 新增业务表仅 accounts / recordings / recording_segments / jobs；registry 复用现有表。转写只存 recordings.transcript_json，文件发布只存 jobs，迁移版本用 PRAGMA user_version。
- 用户表只有既定 9 个字段；两个导航“录音、设备”，账号菜单邮箱/退出；Google Code/OIDC 接入和内存会话在 S02。
- raw 与 WAV 双保留；同一 WAV 用于播放、ASR、下载；VTT 是转写产物，MD 由同组 cues 即时生成。
- WAV 16 kHz / mono / PCM16 LE；raw 单段 8 MiB、连续处理默认 8 小时上限；旧协议无整段闭合证据，静默 10 分钟只是处理触发。
- SQLite 每连接 FK=ON、busy_timeout=5000、synchronous=FULL；UTC 毫秒；部署业务时区默认 Asia/Shanghai；原件持续保留。
- 一个活动任务；lease 60 秒、15 秒续期；最多重试 3 次，间隔 30 秒/2 分钟/10 分钟。任务完成检查当前输入版本/lease。
- Wi-Fi 只用 Clip 经 BLE 返回的周围扫描列表：选择 SSID、输入密码、BLE 设置；扫描结果由目标 Clip 返回。已保存网络数量按固件容量展示，上限 5 个。

### 重点验证项目

1. OAuth state/nonce/PKCE 错误、回调重放、服务器重启、身份冲突：拒绝错误登录，内存失效只要求重登，不影响设备收件。S02/S12。
2. 激活请求重放、设备已属别人、移除时还在上传：同用户幂等、异用户拒绝、立即撤凭证，历史文件归属不变。S03/S11。
3. raw/DB 双写、重启、迟到片段：不丢原件、不重复增版本、旧 lease 不覆盖新结果。S05–S07。
4. ASR 畸形时间戳、文本注入、多人重叠、VTT 中文：有效 cue 保留，非法 cue 不发布，转义正确，音频与文字同版本。S08/S10。
5. 时区日期边界、多标签退出、Range 越界：结束日期包含当天，跨用户无泄露，后续流请求拒绝，非法范围 416。S07/S09/S10。

### 开发顺序与文件位置

| 顺序 | 任务 | 前置 | 可审查交付 |
|---|---|---|---|
| 1 | S01 基线与数据库迁移 | 无 | 4 张业务表、registry 仅加列/索引、旧数据夹具 |
| 2 | S02 Google 登录与内存会话 | S01 | Google 登录、用户唯一性、内存会话与 owner 门禁 |
| 3 | S03 设备激活与归属适配 | S02 | 现有可信发放/绑定适配，改名/移除 API |
| 4 | S04 Web 框架与添加向导 | S02/S03 | 两导航、账号菜单、四步向导 |
| 5 | S05 原件与业务录音投影 | S01/S02 | receiving/ready、来源收据、聚合与版本 |
| 6 | S06 两类任务与文件发布恢复 | S05 | 一个活动任务、租约、prepared→ready |
| 7 | S07 WAV 解码与鉴权播放 | S06 | raw/WAV 双保留、Range、可用音频 |
| 8 | S08 ASR、cues 与 VTT | S07 | 当前音频对应文字和真实 .vtt |
| 9 | S09 日期列表 | S04/S05/S08 | from/to、预览、状态、分页 |
| 10 | S10 详情、复制与三种下载 | S07/S08/S09 | 基础播放、文字、WAV/MD/VTT |
| 11 | S11 设备卡片与 Wi-Fi | S03/S04 | 能力真实、最多 5 个、改名/移除 |
| 12 | S12 集成、迁移恢复与候选包 | S01–S11 | 分层验收证据、备份/回退说明 |

新增后端放 `server/boa/product/`：`db.py`、`auth.py`、`users.py`、`devices.py`、`recordings.py`、`jobs.py`、`files.py`、`decode.py`、`transcript.py`、`routes.py` 和 `migrations/`。测试放 `server/boa/tests/product/`。

新 Web 放 `server/web/product/`：`index.html`、`style.css`、`app.mjs`、`api.mjs`、`devices.mjs`、`recordings.mjs`、`detail.mjs`，复用原 BLE/绑定模块；对应 Node 测试仍放 `server/web/tests/`。旧 `/firmware/` 与 App API 保持兼容。

公共接口约定在 S01 定义：

- `Actor(user_id: str, auth_version: int)`：由服务端认证取得，owner 取自会话对应用户。
- `SourceEvent(owner, namespace, source_id, session, epoch, segment_no, relative_path, size, sha256, created_at_ms)`：只包含服务端已确认来源。
- `InputSnapshot(recording_id, owner, revision, sources: tuple[SourceEvent, ...])`：按片段号冻结，hash 列表进 job.input_json。
- `Lease(job_id, recording_id, revision, token, expires_at_ms)`：存储/发布都引用同一个 fence。
- `Cue(cue_index: int, start_ms: int, end_ms: int, speaker: str | None, text: str)`：JSON、VTT、MD 的共同结构。

下列模块接口均在 `ProductContext` 内装配：该上下文包含 root、Registry、BusinessDB、clock_ms 和按 recording/source 键的锁。S01 定义这些公共类型，后续模块统一使用。测试 fixture `ctx`、`two_users`、`source_factory`、`fake_clock`、`faults` 均使用临时库和合成资料。

</details>

### S01：实施基线与版本化迁移

<details>
<summary>展开文件、接口与验收步骤</summary>

**涉及文件：** 新增 `product/{__init__,contracts,db}.py`、`product/migrations/*.sql`、`tests/product/{conftest,test_db}.py`、基线记录；修改打包文件清单。**接口：** `migrate(root: Path, dry_run: bool) -> dict`、`BusinessDB.connect() -> sqlite3.Connection`。

- [ ] 记录源码版本，建立开发分支和 `.venv-boa`，运行原 Python/Node 测试，记录基线结果与环境依赖。
- [ ] 写 `test_schema_has_four_business_tables`、`test_legacy_ids_and_time_units_survive_migration`，运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_db.py -q`，记录结果。
- [ ] 参考 SQL 转为真实版本化迁移，保留旧 registry/上传库；新业务库 4 表、PRAGMA user_version 原子更新；registry 只加 bindings 别名列和 sources.projected_at。同步把 registry.py 中 bindings/sources 的位置式 INSERT 改成显式列名，验证加列后兼容；毫秒桥接与公共接口约定一次统一。
- [ ] 验证目标测试，FK/integrity、旧库夹具升级、失败重跑、未知高版本拒绝均验证；迁移先在隔离副本运行。
- [ ] 交付四表迁移、旧库升级夹具和数据库访问接口。

</details>

### S02：基本用户、会话和统一 owner 检查

<details>
<summary>展开文件、接口与验收步骤</summary>

**涉及文件：** `product/{auth,users}.py`、`test_users.py`、`test_google_auth.py`；修改 `web_sessions.py`、`boa_app.py`、依赖锁。**接口：** `begin_google_login(request: Request) -> Response`、`finish_google_login(request: Request) -> Response`、`sync_verified_user(sub: str, email: str, name: str) -> str`、`principal(request: Request) -> Actor`、`logout(request: Request) -> None`。登录参数、TTL、Cookie、容量和错误码以[接口约定](#google-login)为准。

- [ ] 写 `test_sub_reuses_owner`、`test_same_email_never_merges_user`、`test_invalid_state_nonce_pkce_or_id_token_denied`、`test_callback_replay_and_browser_mismatch_denied`、`test_restart_requires_login_but_keeps_device_upload`、`test_logout_keeps_recordings`、`test_disabled_user_denied`；账号 9 字段，旧 sub 可空，登录状态与会话不落盘。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_users.py server/boa/tests/product/test_google_auth.py -q`，记录结果。
- [ ] 接 Google Code/OIDC + S256 PKCE 与标准验证库，配置固定 HTTPS 回调、openid/email/profile；实现内存 LoginFlow/Session、Cookie、当前用户/退出、Origin/CSRF，旧 Bearer 统一门禁。Google token 使用后释放，登录采用 online 模式；sub 来自已验证 token，owner 来自本站会话。
- [ ] fake clock 验证 5 分钟/24 小时/7 天、单次消费、容量到顶拒绝且已有有效会话继续使用、禁用/auth_version 立即生效；同邮箱不同 sub、同 sub 邮箱冲突、Google 失败时清理本次认证状态；完成目标测试和旧接口回归，随后验证真实 Google 跳转。
- [ ] 交付 Google 登录、内存会话、当前用户和退出接口。

</details>

### S03：最少的设备激活、改名与移除

<details>
<summary>展开文件、接口与验收步骤</summary>

**涉及文件：** `product/devices.py`、`test_devices.py`；适配 `registry.py`、`device_configurations.py`。**接口：** `activate(actor: Actor, uid: str, evidence: dict) -> dict`、`rename(actor: Actor, device_id: str, name: str) -> None`、`remove(actor: Actor, device_id: str) -> dict`。

- [ ] 写 `test_activation_requires_trusted_enrollment`、`test_same_owner_activation_is_idempotent`、`test_other_owner_cannot_claim`、`test_remove_revokes_upload_but_keeps_audio`。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_devices.py -q`，记录结果。
- [ ] 把原型自动激活接到既有可信登记/发放和 binding/epoch/读回 API，凭据只给本人并 no-store。别名写既有 registry.bindings.display_name，WHERE 同时核对本人 owner、binding_id、active；移除先撤凭证，离线清理保留既有锁。验证依据使用现有受控登记与设备凭证。
- [ ] 验证绑定接口和实机激活；无有效登记依据、已属其他用户或配置读回失败时，拒绝激活并显示具体错误。
- [ ] 交付设备激活、改名、移除接口及绑定回归结果。

</details>

### S04：两导航、账号菜单与添加设备向导

<details>
<summary>展开文件、接口与验收步骤</summary>

**涉及文件：** `server/web/product/{index.html,style.css,app.mjs,api.mjs,devices.mjs}`、`server/web/tests/product-shell.test.mjs`；修改 `frontend.py`。**接口：** `createApi({fetcher,onLogout}) -> {request,reset}`、`mountDeviceWizard({root,api,ble}) -> {dispose}`。

- [ ] 写 `only recordings and devices navigation`、`account menu only shows email and logout`、`stale response is cancelled`、`activation readback is not upload success`。
- [ ] 运行 `node --test server/web/tests/product-shell.test.mjs`，记录结果。
- [ ] 新 `/` 静态入口复现原型，显示“录音助手”；向导为准备/连接/自动激活/设置 Wi-Fi，调用 S03 接口及原 BLE 读回/校时。
- [ ] 目标 JS/原 frontend 测试通过；Chrome 核对空态、选择器取消、BLE 不支持、失败重试和关闭向导；分别记录浏览器测试与实机写入结果。
- [ ] 交付录音/设备导航、账号菜单和设备添加向导。

</details>

### S05：来源投影、片段幂等和上传状态

<details>
<summary>展开文件、接口与验收步骤</summary>

**涉及文件：** `product/recordings.py`、`test_sources.py`；修改 `registry.py`、`receiver.py` 和 App 完成适配。**接口：** `import_ready(ctx, event: SourceEvent) -> str`、`sync_receiving(ctx) -> int`、`snapshot(actor: Actor, recording_id: str) -> InputSnapshot`。

- [ ] 写 `test_raw_ack_does_not_wait_for_business`、`test_ready_event_replay_changes_revision_once`、`test_receiving_has_no_ready_file`、`test_gap_and_new_epoch_not_merged`、`test_projected_marker_never_hides_restore_gap`、`test_same_source_hash_conflict_rejected`。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_sources.py -q`，记录结果。
- [ ] raw/identity/fsync/ACK 保持旧语义；sources ready 行本身就是待投影项；business 片段行同时存 raw 元数据与收据，唯一 namespace/source_id，条件 receiving→ready 与录音增版本同事务。先提交 business 再标 sources.projected_at；启动按 500 条分页对账全部 ready 来源。receiving 用于上传状态，校验完成后创建处理任务；App 仅兼容既有接口。
- [ ] 在 raw 后、registry 后、business 后、消费标记前故障注入并重启，确认原件完整、版本幂等，并完成原 DTLS/HTTP 回归。
- [ ] 交付来源投影、片段幂等和收件故障恢复结果。

</details>

### S06：两类持久任务与文件发布恢复

<details>
<summary>展开文件、接口与验收步骤</summary>

**涉及文件：** `product/jobs.py`、`files.py`、`test_jobs.py`、`test_files.py`；修改服务 lifespan。**接口：** `enqueue(snapshot: InputSnapshot, kind: str) -> str`、`claim(now_ms: int) -> Lease | None`、`publish(lease: Lease, tmp: Path, metadata: dict) -> str`、`recover(ctx) -> int`。

- [ ] 写 `test_single_active_job`、`test_expired_lease_cannot_publish`、`test_rename_before_commit_recovers`、`test_new_revision_fences_old_output`。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_jobs.py server/boa/tests/product/test_files.py -q`，记录结果。
- [ ] jobs 一行含任务、文件路径/hash/size、publication_state；decode 仅 WAV、transcribe 仅 VTT。实现按 recording/revision/kind 去重、SQL 部分唯一索引限制一个 running、60 秒 lease/15 秒续期、有界重试；prepared→临时 fsync→预期 hash→同盘独占 rename/目录 fsync→ready；WAV 可核 hash 恢复，VTT/cues 的联合提交恢复由 S08 验证。用输入版本和租约控制发布。
- [ ] 对发布边界中断、磁盘满、hash 冲突、文件缺失、双监听重复启动运行时做测试，确认恢复行为；服务退出停止领新任务，15 秒后留待重启恢复。
- [ ] 交付持久任务调度、文件发布与重启恢复模块。

</details>

### S07：raw 解码为一份 WAV，鉴权 Range 播放

<details>
<summary>展开文件、接口与验收步骤</summary>

**涉及文件：** `product/decode.py`、`test_decode.py`、`test_audio_http.py`；修改 `product/routes.py`、依赖/工具版本清单。**接口：** `decode(snapshot: InputSnapshot, output: Path) -> dict`、`serve_audio(actor: Actor, recording_id: str, revision: int, range_header: str | None) -> Response`。

- [ ] 写 `test_raw_packet_framing_to_16000_mono_pcm16`、`test_bad_packet_preserves_raw`、`test_gap_does_not_get_silence`、`test_range_owner_and_logout`；1 秒合成样本应得 16000 样本，Range 合法 206、非法 416。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_decode.py server/boa/tests/product/test_audio_http.py -q`，记录结果。
- [ ] 按实际 raw profile 解包/封装并解码，临时分段后合一份 WAV；raw 元数据只在 recording_segments；样本数/独立 hash 随 WAV jobs 行入库；S06 发布当前音频。WAV 同时供播放、ASR、下载。Cookie/Bearer + owner 直接鉴权。
- [ ] 目标测试和授权真实样本解码/试听分别通过；验证长录音拖动、超时/体积限制、并发新片段和旧音频仍可安全读取，记录 pre-skip 时间来源限制。
- [ ] 交付 raw 解码器、WAV 文件及鉴权 Range 接口。

</details>

### S08：ASR 文字、说话人与 WebVTT

<details>
<summary>展开文件、接口与验收步骤</summary>

**涉及文件：** `product/transcript.py`、`test_transcript.py`、`test_vtt.py`；从本文 [VTT 示例](#vtt-example)提取人工合成测试夹具。**接口：** `ASR.transcribe(wav: Path, request_id: str) -> list[Cue]`、`validate_cues(cues: list[Cue], duration_ms: int) -> list[Cue]`、`render_vtt(cues: list[Cue]) -> bytes`、`publish_transcript(lease: Lease, cues: list[Cue]) -> None`。

- [ ] 写 `test_vtt_header_utf8_milliseconds_and_voice`、`test_invalid_time_rejected_but_valid_overlap_kept`、`test_untrusted_text_escaped`、`test_old_transcript_not_on_new_wav`；示例应解析出 2 个 cue，结尾 5800ms，speaker A/B，空白文本 cue/逆序/越界拒绝；全程静音允许 0 cues。增加 `test_plain_text_roundtrip_and_json_vtt_same_cues`、`test_restart_loads_text_without_asr`、`test_vtt_file_without_cue_commit_is_reprocessed`、`test_missing_vtt_rebuilds_from_stored_json`、`test_json_limit_never_truncates_text`。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_transcript.py server/boa/tests/product/test_vtt.py -q`，记录结果。
- [ ] 按 v1 JSON 接口约定固定 cue_index 和整数毫秒，整份 transcript_json 不超过 8 MiB UTF-8，text 为未转义原文，speaker 可空；接一套实际私有 ASR adapter，未配置明确 not_configured；校验后生成 UTF-8 VTT，按 S06 持久发布，并把 recordings.transcript_json、vtt_job_id、文字 ready 与 jobs 成功原子提交。当前 audio_revision 与 transcript_revision 一致才对外显示；说话人缺失保存为 null。
- [ ] 目标测试通过，重启后直接从 recordings.transcript_json 读文字、由同版本 cues 导出 MD；缺失 VTT 复用已存 JSON 重建；VTT 已落盘且 cues 未提交时，恢复任务重新识别并整体发布。浏览器实际解析示例 VTT；真实端点用授权样本检查时间/文本/分离质量。ASR 失败时，验证已发布 WAV 仍可播放。
- [ ] 交付 ASR 适配器、转写 JSON 持久化和 VTT 文件。

</details>

### S09：日期列表 API 与 Web

<details>
<summary>展开文件、接口与验收步骤</summary>

**涉及文件：** 扩展 `product/{recordings,routes}.py`、`server/web/product/recordings.mjs`；新增 `test_recording_list.py`、`product-recordings.test.mjs`。**接口：** `list_recordings(actor: Actor, from_date: str | None, to_date: str | None, cursor: str | None, limit: int=30) -> dict`。

- [ ] 写 `test_inclusive_end_date_uses_next_local_midnight`、`test_invalid_dates_and_owner_filter`；JS 验证日期筛选、文字开头预览和列表状态。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_recording_list.py -q`、`node --test server/web/tests/product-recordings.test.mjs`，记录结果。
- [ ] COALESCE 可信录音时间/收件时间后按部署时区分组，结束日转次日零点半开区间；每页 30 条稳定日期/id 游标。显示真实 receiving、处理状态和时长；可见 5 秒/隐藏 30 秒轮询、日期变化取消旧请求。
- [ ] 目标测试通过；Chrome 检查同日/跨日、清空筛选、无数据、后端离线和返回列表；跨用户访问返回 404。
- [ ] 交付日期筛选接口、录音列表和分页交互。

</details>

### S10：详情、基础播放器、复制与 WAV/MD/VTT 下载

<details>
<summary>展开文件、接口与验收步骤</summary>

**涉及文件：** `server/web/product/detail.mjs`、`test_downloads.py`、`product-detail.test.mjs`；扩展 transcript/routes。**接口：** `get_cues(actor: Actor, recording_id: str, revision: int, cursor: str | None) -> dict`、`render_markdown(cues: list[Cue], heading: str) -> bytes`、Web `mountDetail({root,api,audio,id}) -> {dispose}`。

- [ ] 写 `test_wav_md_vtt_same_owner_and_revision`、`test_publication_between_pages_requires_reload`、`test_markdown_preserves_transcript_text`；JS 断言复制文字、播放暂停/拖动、退出清理音频。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_downloads.py -q`、`node --test server/web/tests/product-detail.test.mjs`，记录结果。
- [ ] 展示日期标题、时长、A/B 文字；cue 分页每页 200 条，复制/MD 覆盖全部当前文字而不只第一页。导出菜单提供 WAV、Markdown、VTT。详情固定 audio_revision，四类内容请求和 cue 游标都带 revision；读快照内匹配当前音频/文字版本，否则 409，Web 取消分页/播放后重新载入，版本变化时重新取齐文字。MD 即时生成。
- [ ] 目标测试通过；Chrome 试听/拖动、复制全文、下载 WAV/MD/VTT 并核对中文/时间戳和 MIME；新 WAV 就绪时隐藏不同版本文字，切换账号中断旧请求。
- [ ] 交付详情播放器、全文复制和 WAV/Markdown/VTT 下载。

</details>

### S11：设备卡片与基于 Clip 扫描的 Wi-Fi 配置

<details>
<summary>展开文件、接口与验收步骤</summary>

**涉及文件：** 扩展 `product/devices.py`、`server/web/product/devices.mjs` 和既有 BLE adapter；新增 `product-wifi.test.mjs`、`test_device_views.py`。**接口：** BLE adapter `capabilities()`、`scanWifi() -> {ssid,rssi,security}[]`、`saveWifi(selectedSsid,password)`、`readWifiStatus()`、`deleteWifi(ssid)`；扫描与连接状态由 Clip 真实返回，缺能力为 unsupported。

- [ ] 写 `wifi list comes from clip scan over ble`、`ssid must be selected from scan results`、`missing scan does not enable manual ssid`、`saved is not connected`、`at most five saved networks`、`password never sent to server`；后端验证别名/归属/移除保留录音，状态来源缺失时显示“未知”。
- [ ] 运行 `node --test server/web/tests/product-wifi.test.mjs`、`.venv-boa/bin/python -m pytest server/boa/tests/product/test_device_views.py -q`，记录结果。
- [ ] 设备卡片保留改名、版本、状态、Wi-Fi 管理和移除；Wi-Fi 操作固定为连接 BLE→请求 Clip 扫描→选择返回的 SSID→输入密码→BLE 写入→读取保存/连接结果。空列表/超时重扫、密码错误重输。扫描接口不可用时显示固件能力要求；已保存网络按设备容量展示。
- [ ] 模拟边界测试通过；实机验证扫描列表确实来自目标 Clip、选网/密码写入/连接结果、删除/重连/移除；验收记录包含扫描来源、网络容量和遥测采样时间。
- [ ] 交付设备卡片、BLE Wi-Fi 配置和实机验证结果。

</details>

### S12：整体回归、迁移恢复与候选包

<details>
<summary>展开文件、接口与验收步骤</summary>

**涉及文件：** `tests/product/test_end_to_end.py`、`docs/development/recording-v1-acceptance.md`；修改打包脚本/部署说明，必要时新增小型迁移/备份 CLI。**交付：** 候选包、源码/依赖/文档 SHA、分层检查记录；形成待部署候选包。

- [ ] 在隔离夹具写端到端失败用例：用户→设备→receiving→raw→WAV→文字/VTT→列表→复制/下载→移除设备，断言历史文件归属不变，Bob 请求 Alice 的录音时返回 404。
- [ ] 执行 `.venv-boa/bin/python -m pytest server/tests server/boa/tests server/storage/tests -q`、`.venv-boa/bin/python -m unittest tools.upload.tests.test_dtls_receiver -v`、`node --test server/web/tests/*.test.mjs`，修复回归；环境缺失单列。
- [ ] 真实浏览器、Google 登录及重启重登、Clip 收件、WAV 试听、ASR/VTT、Wi-Fi 实机分别验收；记录缺失的发放/固件能力，Google 配置缺失则登录未验收，固件缺项则实机闭环未验收；联调记录附真实返回数据。
- [ ] 停机整体备份并在隔离目录迁移/恢复，核对旧 user_id、设备、raw 数量/字节/hash；回退先保存新录音；测实际响应/处理时间并记录，给出实测处理能力。
- [ ] 打包排除录音/数据库/凭证，核对 manifest/哈希；交付候选包、校验清单和验收记录 并明确未完成的真实验收，完成上线验收后标记发布版本。

</details>

### 交付里程碑

- **M1：S01–S04。** Google 登录、内存会话和设备向导可用；自动激活需真实可信发放能力，验收覆盖凭证发放与实机配置。
- **M2：S05–S08。** 原件入库、WAV 双保留、可播放，完成 ASR、JSON 和 VTT 的发布与恢复验证。
- **M3：S09–S12。** 日期列表、文字/下载、设备卡片与实机/迁移验收，形成候选包。


<a id="sql"></a>

## 13. 完整 SQL 参考

<a id="business-sql"></a>

<details>
<summary>业务库：4 张表，完整 DDL</summary>

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

</details>

<a id="registry-sql"></a>

<details>
<summary>既有 registry：只加列与索引，新增 0 张表</summary>

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

</details>

<a id="self-review"></a>

## 14. 评审与验收

| 检查项 | 设计要求 | 任务 |
|---|---|---|
| 身份验证 | 校验 state、浏览器绑定、PKCE、nonce、ID token；google_sub 对应稳定 user_id | S02 |
| 会话生命周期 | 到期、退出和服务重启清理网页登录状态；设备凭证独立工作 | S02/S12 |
| registry 升级 | bindings/sources 使用显式列名写入，加列后旧接口继续可用 | S01/S03/S05 |
| 收件幂等 | 来源唯一键、首次 ready 条件更新、跨库先提交业务再标进度、启动对账 | S05/S12 |
| 文件发布 | 校验 hash、版本和 lease，提交文件状态与录音指针 | S06/S07 |
| 文字持久化 | transcript_json 保存原文、时间与 speaker，和 VTT 指针同事务提交 | S08 |
| 转写恢复 | VTT 已落盘且文字事务未提交时重新识别；VTT 丢失时从已存 JSON 重建 | S06/S08 |
| 空结果 | 区分静音成功、识别失败和 ASR 未配置 | S08/S10 |
| 版本一致性 | WAV、JSON、VTT、Markdown 和分页使用相同 revision | S07/S10 |
| Wi-Fi 配置 | 实机验证 Clip 扫描列表、BLE 写入、保存与连接结果 | S04/S11 |
| 数据隔离 | 验证跨用户 API、Range、下载、禁用状态和旧 Bearer 兼容 | S02/S07/S10 |
| 长录音与恢复 | 测试 JSON 8 MiB 限制、长录音、磁盘容量、备份迁移与回退 | S08/S12 |

<details>
<summary>验收记录</summary>

| 项目 | 当前状态 | 交付要求 |
|---|---|---|
| 参考 DDL | 四表建库、19 项约束拒绝检查、外键与完整性检查已完成 | 真实迁移夹具与故障注入结果 |
| 转写格式 | JSON/VTT 示例文本与时间戳一致 | 授权样本的识别质量、说话人和时间校准 |
| Google 登录 | 接口、Cookie 与验证条件已定义 | 真实配置、跳转、退出、重启与错误场景结果 |
| Clip 接入 | BLE 配置、凭证与收件接口已定义 | 真实设备配置与上传记录 |
| Wi-Fi | 扫描和连接交互已定义 | 固件扫描返回、实际网络容量与连接结果 |
| 发布运行 | 单进程部署和备份方法已定义 | 部署记录、恢复演练和容量实测 |

</details>

<a id="prototype-review"></a>

## 15. 页面与联调清单

<details>
<summary>页面交互与设备能力</summary>

| 页面或能力 | 开发内容 | 验收依据 |
|---|---|---|
| 登录和账号菜单 | Google 登录、邮箱展示、退出 | 真实 Google 账号登录与会话失效 |
| 录音列表 | 日期筛选、时长、文字预览、处理状态 | 跨日期、空列表、处理中文件 |
| 录音详情 | 播放、进度、说话人、复制、三种下载 | 音频、文字与下载版本一致 |
| 添加设备 | BLE 选择、激活、上传配置、读回、校时 | 可信登记与实机读回 |
| Wi-Fi | Clip 扫描、选网、密码写入、保存与连接反馈 | 目标设备扫描与联网结果 |
| 设备卡片 | 别名、版本、状态、电量、待上传数、移除 | 带采样时间的遥测与解绑结果 |
| 原始音频 | Opus 包解码为 WAV，保存 raw 与 WAV | 包边界、样本数、hash、试听 |
| 转写服务 | 私有 ASR、JSON 原文持久化、VTT 与 Markdown | 授权样本与重启读取 |

</details>

<a id="diagram-maintenance"></a>

## 16. 配图维护

<details>
<summary>图源与生成方式</summary>

配图使用 SVG，尺寸与文字布局由[生成脚本](docs/assets/diagrams/render.py)管理。

| 图 | 表达内容 |
|---|---|
| 产品页面 | 录音列表、详情与设备卡片 |
| 部署架构 | 接入端口、进程、业务模块、外部服务和存储 |
| 数据关系 | 用户、录音、片段与任务的主外键关系 |
| 设备添加 | 四步向导的界面和确认结果 |
| 收件投影 | 原件、registry 与业务索引的持久化职责 |
| 文件存储 | raw、WAV、JSON、VTT、Markdown 的位置与用途 |
| 发布恢复 | 文件与数据库在各提交阶段的状态 |
| 版本对齐 | 详情、音频、文字和下载的版本要求 |
| Wi-Fi | 扫描列表、密码输入与 Clip BLE 连接 |
| 登录存储 | 浏览器、Server 内存与 SQLite 的数据生命周期 |
| 转写格式 | JSON 实例及字段定义 |
| 开发排期 | 三个里程碑与 S01–S12 的对应关系 |

在仓库根目录运行：

```sh
python docs/assets/diagrams/render.py
```

修改配图后检查文字、关系、版本与正文中的接口和字段定义。

</details>
