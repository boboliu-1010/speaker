# 录音助手 Server + Web 第一版设计

日期：2026-10-29。状态：设计文档，未实施产品代码或真实数据迁移。

本版按[当前原型](https://comfy-faloodeh-ec9b57.netlify.app/)重新检查登录、添加设备、Wi-Fi、录音列表、详情、导出、设备卡片和移除提示，并纳入用户新增的 **VTT 原文持久化、Google OAuth 与内存会话** 要求。本文替代旧版“大而全”的设计；历史保留在 Git，不再将旧功能当作待办。

文档管理：[boboliu-1010/speaker](https://github.com/boboliu-1010/speaker)。现有代码基线：[BofAI/reSpeaker_Clip](https://github.com/BofAI/reSpeaker_Clip)，此前读取 `77ae7fc`；实施前重新检查当前代码，不将原型演示当作真实协议能力。

## 阅读顺序

先读[图解](../../boa-v1-illustrated-guide.md)，再看[原型核对与删减清单](../../2026-10-29-prototype-review.md)、本文和[实施计划](../plans/2026-10-29-boa-server-web-v1-implementation-plan.md)。数据结构见[业务库 SQL](2026-10-29-boa-v1-business-schema.sql)和[registry 最小增量](2026-10-29-boa-v1-registry-additions.sql)。

<a id="scope"></a>

## 1. 最小产品范围

![产品范围](../../assets/diagrams/00-product-overview.svg)

<details>
<summary>展开实现细则</summary>

| 位置 | 保留的功能 |
|---|---|
| 登录/账号 | Google OAuth 2.0 / OIDC 登录；基本用户落库，临时状态与本站会话只在内存。账号菜单显示邮箱和退出 |
| 录音列表 | 按日期分组、开始/结束日期筛选、时长、转写开头预览、真实上传/处理状态 |
| 录音详情 | 日期时间标题、文字和 A/B 等说话人标签、基础播放/暂停/进度、复制文字 |
| 下载 | WAV 音频、Markdown 文字；按用户新增要求提供 WebVTT 文件 |
| 添加设备 | 准备 → BLE 连接 → 自动激活/凭证配置/校时 → Wi-Fi → 完成 |
| 设备卡片 | 名称、版本、可信的状态/电量/待上传信息、Wi-Fi 添加/删除、改名、移除 |
| Server 内部 | 原始文件与 WAV 双保留、SQLite 入库、ASR/VTT、最小持久任务和文件恢复、同用户鉴权 |

不开发：邀请、组织、本地密码、多身份绑定、纪要/结论/待办/章节、全文搜索、Word/TXT 导出、录音改名/删除/回收站、历史结果切换、审计页面、管理员工作台、OTA/维修面板、公开分享、MP3、副本音频库、独立消息队列或多服务拆分。

维护侧仍可复用既有固件/设备工具，不为它们增加新产品页面或开发任务。录音删除在本版没有入口，云端录音不自动过期；不得以精简为由让原件自动消失。

</details>

<a id="system-architecture"></a>

## 2. 架构与模块

![精简架构](../../assets/diagrams/01-system-architecture.svg)


<details>
<summary>展开实现细则</summary>

沿用 Python/FastAPI 单个常驻进程、静态 HTML/CSS/ES modules、SQLite、本机持久目录。Web HTTPS 9529 与 HTTPS API 9528 共享后台，Clip 使用 UDP/DTLS 9528。媒体工具是有超时/资源限制的子进程；ASR 使用配置的私有端点。不开多个 worker 共用目录，不在接收线程或事件循环执行解码。

模块只按职责拆：`auth`（Google 登录/内存会话）、`users`（基本资料）、`devices`（既有绑定适配）、`recordings`（来源/列表）、`jobs`（一个活动处理任务）、`files`（持久发布/恢复）、`decode`（WAV）、`transcript`（ASR/cues/VTT）、`routes`（同源 API）。不新增通用工作流平台。

Web 的 `/api/boa/v1` 在 9529 同源转交同进程处理；浏览器不直接跨端口调用 9528，不启用跨域 Cookie。旧 9528 接口继续服务原有客户端。Google 回调也固定在 9529 的公开 HTTPS origin；反向代理场景只信任显式配置的代理，不从任意 Host/X-Forwarded-* 拼回调地址。

浏览器可见时每 5 秒更新活动录音、每 15 秒更新设备；隐藏后降到 30 秒，恢复时立即更新。采用轮询即可，不增加 WebSocket/SSE。

</details>

<a id="user-model"></a>

## 3. 基本用户与会话

![用户主表](../../assets/diagrams/02-user-data-model.svg)

![Google 登录与内存会话](../../assets/diagrams/09-google-memory-login.svg)


<details>
<summary>展开实现细则</summary>

`accounts` 保留 9 个字段：`user_id`、`google_sub`、`email`、`display_name`、`status`、`auth_version`、`last_login_at`、`created_at`、`updated_at`。内部 user_id 关联所有 owner，既有用户沿用旧 ID；google_sub 唯一，旧用户迁移未核验时允许为空。邮箱唯一但不是自动合并身份的依据；头像首字母从名字/邮箱派生。

状态只有 active/disabled。登录使用 Google OAuth 2.0 Authorization Code + OpenID Connect；具体契约见[Google 登录与内存边界](2026-10-29-google-login-and-transcript-contract.md#google-login)。不建 OAuth、token、browser_sessions 表。每个请求重新核对 accounts.status/auth_version；已有 Bearer 兼容身份也经过相同门禁，不能绕过禁用。

内存保存一次性登录状态（5 分钟）和本站会话（闲置 24 小时、绝对 7 天）；随机 opaque Cookie 引用服务端会话。退出即删除，Server 重启全部失效、用户重新登录，设备上传凭证与后台任务不受影响。登录跳转的临时 Cookie 使用 Secure/HttpOnly/SameSite=Lax，本站会话使用 Secure/HttpOnly/SameSite=Strict，均为 host-only、Path=/；不把内存 map 序列化到磁盘。容量/清理/重放边界见登录契约。

所有读取按服务端身份过滤 owner，跨用户对象统一 404；写请求校验准确 Origin 与会话 CSRF。普通用户不因首次登录获得开发者权限，既有维护通道权限仅为兼容，不复制成新用户角色体系。

</details>

<a id="devices"></a>

## 4. 设备添加、Wi-Fi 与移除

![设备添加](../../assets/diagrams/03-device-onboarding.svg)


![Clip 扫描与选网](../../assets/diagrams/08-wifi-configuration.svg)

<details>
<summary>展开实现细则</summary>

1. 用户在空录音页或设备页点击添加，主动打开 BLE 选择器。
2. 连接后读取完整 UID、固件和能力；不能以 BLE 名称代替 UID。
3. Server 根据已验证用户与**既有可信设备登记/凭证依据**取得或建立绑定，申请设备上传凭证。已属其他用户则拒绝；同用户重复请求复用同绑定，不反复轮换凭证。
4. Web 通过 BLE 写入上传配置，读回 binding/epoch/revision，再上报确认；同步设备时间，区分“客户端写入”与“实际收件”。
5. 通过 BLE 请求 Clip 扫描周围 Wi-Fi；用户从返回列表选择 SSID、输入密码、写入设备并读取连接结果，完成后回到列表。网页关闭不影响后续设备自行上传。

**激活的必要前提：** 当前代码以开发者受控登记/配置为主。原型的自动激活需要接上现有可信设备发放能力；UID 和“网页声称已连接”都不是所有权证明。若现有固件/发放机制不能提供依据，自动激活实机验收必须标为未完成；不以新增用户邀请、激活码页面或假成功绕过这个缺口。

### Wi-Fi：Clip 扫描，Web 选择设置

**用户确认的唯一新增配置路径：** Web 通过 BLE 请求 Clip 扫描周围 Wi-Fi，显示 Clip 返回的列表，用户选择一个 SSID、填写密码，再经 BLE 写入 Clip。网络来自录音设备所在位置，不从 Mac、浏览器或 Server 获取周边 Wi-Fi，也不提供手动填写 SSID/远处网络入口。

1. 先连接目标 Clip；Web 发 `scanWifi()`，由 Clip 实际执行无线扫描。
2. Clip 通过 BLE 返回可用 SSID、信号强度和安全类型；Web 显示列表与重新扫描按钮。列表只代表搜到，不能当作已保存配置。
3. 用户选择列表中的网络，输入密码；页面保留选中的 SSID，不开放任意 SSID 输入框。
4. Web 经 BLE 将选中 SSID/密码交给 Clip，由设备保存并尝试连接；密码不经过 Server，不入 SQLite、日志或 localStorage。
5. 读取 Clip 的保存/连接结果，分别显示“已保存”“连接中”“已连接”或具体失败；密码错误允许重输，扫描为空/超时允许重扫，不用手填 SSID 绕过。不把仅保存成功显示为联网成功，Wi-Fi 连通也不等于服务器已收录音。

保留已保存网络的查看/删除，最大数量按设备能力、上限 5 个；添加新网络始终来自当次 Clip 扫描结果。若当前固件没有扫描/结果返回能力，添加配置显示“不支持/待固件能力补齐”，不能降级为手动 SSID 或假扫描。多配置存储不足时按真实容量展示，不宣称完整 5 网络支持。当前文档基线为 2.4 GHz WPA2，原型中的“办公室-5G”名称不是 5 GHz 支持证据。

### 设备卡片

改名写既有 registry.bindings.display_name，更新时同时核对 owner、binding_id 与 active；未命名回退既有显示名/设备 ID。别名随绑定隔离，不另建 device_preferences，不改 UID/凭证。固件版本仅展示，不增加升级入口。在线、电量、待上传数必须有来源和采样时间；只有最近收件证据时显示“最近收件/状态未知”，不能假装在线。移除先撤销服务端上传凭证，尝试清理在线 BLE 上传配置；离线清理失败沿用既有交接锁。**已上传录音保留原 owner**，重新添加走受控绑定。

</details>

<a id="ingest"></a>

## 5. 收件、录音聚合与原件保留

![接收与业务入库](../../assets/diagrams/04-raw-ingest-outbox.svg)


<details>
<summary>展开实现细则</summary>

保持 v3 原协议：数据 fsync → 持久检查点 → 整文件 size/hash 校验 → rename/目录 fsync。只有 raw 和可恢复归属的身份元数据持久后才回 COMPLETE，不等待 WAV、ASR 或 VTT。设备撤销后不能继续写入；旧绑定的历史文件仍属原用户。

既有 registry 的 `sources` ready 行就是持久待投影项，新增 projected_at 标记，不再建 outbox 表。消费者在 business 单事务建立/更新 recording 与 recording_segments；同一片段行保存 raw 路径/size/hash，并以唯一 `(source_namespace,source_id)` 兼作来源收据。业务事务成功后才标 projected_at。文件已落盘但索引失败，可从既有 identity/raw 对账；业务已提交但未标记时重放，ready→ready 且 hash 相同不重复增版本，hash 冲突拒绝。启动分批核对全部 ready 来源，不能只信标记。

录音按 `(source_kind, source_namespace, binding_epoch, source_session)` 聚合；新 ready 片段才递增 input_revision，重复 source 不增加。App 原上传接口只作为兼容来源，不添加文件上传页面。可定期读取已有 receiving 索引创建上传中的录音元信息，未收完整时不标片段 ready、不生成处理任务。

旧协议没有总片段清单，所以显示“已收到 N 个片段/完整性未知”，不伪造 3/5 或整段完成。收到连续片段后静默 10 分钟可处理当前已收内容，这不是结束证据；有缺号则等待补齐，不补静音、不生成虚假完整时间轴。后续片段到达更新输入版本并重做派生内容；不做用户可选择的历史版本功能。

</details>

<a id="recording-decode"></a>

## 6. raw + WAV 双保留

![解码流水线](../../assets/diagrams/05-decode-and-retain.svg)


<details>
<summary>展开实现细则</summary>

- Clip raw 格式为 `uint16 little-endian length + raw Opus packet`；先检查包边界/时长/声道，再正确封装或用受控解码器处理，不能直接当 Ogg 或 WAV。
- 校验 raw hash 后解码为 **16 kHz、mono、PCM16 little-endian WAV**。逐段临时解码，再按冻结片段顺序合为一份 `recording.wav`，记录样本数、长度和独立 hash。
- 一份已发布 WAV 同时用于原型播放、ASR 和下载，不另存 MP3、长期片段 WAV 或第二份 ASR WAV。临时分段文件成功后清理；原始文件始终保留。
- 内部存储路径按 raw 来源或 job/attempt 与输入版本确定，不覆盖已发布路径；更新不覆盖正在播放的文件。当前指针只指向 jobs 中 ready 的文件；旧派生文件在任务与读取不再使用后可清理，raw 不参与此清理。
- Ogg granule 的 48 kHz 时基与 PCM 16 kHz 区分；raw 没有 pre-skip 元数据时保留当前样本策略并标明时间来源。禁止隐式丢样、补音或把解码错误当正常音频。

单 raw 段遵守既有 8 MiB 上限，连续录音处理默认上限 8 小时。16 kHz mono PCM16 约 115.2 MB/小时，先检查磁盘预算与工具超时；超限留 raw 并给出可恢复失败。原型“音频原文件（.wav）”实际是**设备原件解码所得 WAV**，不是原始 Opus 改后缀，建议按钮文字为“下载音频（.wav）”。

</details>

<a id="dual-write"></a>

## 7. 任务兼作文件索引与发布恢复

![文件和 SQLite 发布](../../assets/diagrams/06-file-database-publication.svg)


<details>
<summary>展开实现细则</summary>

只需 decode、transcribe 两类持久任务；VTT 随 transcribe 生成，Markdown 下载即时生成，不创建导出任务系统。

| 步骤 | 操作 | 可见性 |
|---|---|---|
| 1 | jobs 一行保存输入快照、lease、临时/最终路径与 publication_state=prepared | 不可下载 |
| 2 | 事务外写临时文件，检查 size/hash，flush/fsync | 不可下载 |
| 3 | jobs 记录预期 size/hash；持录音锁检查当前 input_revision 和 lease | 不可下载 |
| 4 | 同文件系统独占 rename，相关目录 fsync | 文件存在仍不算 ready |
| 5 | DB 再检查 fence，同事务提交 jobs 成功/文件 ready、录音指针和下一阶段状态 | 当前用户可读 |

文件与 SQLite 不是一个原子事务；靠 jobs 内的发布字段恢复，不靠“同时写成功”的假设。WAV rename 后 DB 提交前崩溃，重启任务用新 lease 校验文件后补提交；VTT 同时依赖 cues，若 cues 事务未提交则重跑 ASR 并重新整体发布，不能套用仅校验文件的补提交。输入已过期则不改当前指针。jobs 对应文件缺失则标 publication_state=missing：WAV 由 raw 重建，VTT 优先由已提交的同版本 cues 重建；原件缺失单独告警。不同 hash 的同路径对象拒绝覆盖。

每个 decode 任务只发布一份 WAV，每个 transcribe 任务只发布一份 VTT，文件 MIME 由 kind 派生；不建通用 storage_objects/file_publications。原件元数据在 recording_segments，不复制到 jobs。

任务 input_json 冻结原件清单和媒体/ASR 配置版本，transcribe 还固定所消费的 wav_job_id 与 WAV hash；运行环境不匹配时不偷偷换工具执行。需因配置变化重做时由维护流程建立新输入修订，禁止同 revision 悄悄改变时间轴。

单个活动任务，60 秒 lease、15 秒续期；瞬时错误最多重试 3 次，间隔 30 秒/2 分钟/10 分钟。解码超时 10 分钟、ASR 最长 60 分钟作为可配置初值。启动先恢复来源索引/事件，再恢复文件发布和过期任务；API/接收线程不等待模型执行。

</details>

<a id="vtt"></a>

## 8. 转写与 WebVTT

![WAV、转写片段和 VTT](../../assets/diagrams/07-transcript-vtt.svg)


<details>
<summary>展开实现细则</summary>

ASR 消费当前 WAV，返回 cue 的 start_ms/end_ms/text 和可空 speaker。说话人按当前录音稳定映射为 A/B/C；供应方无分离结果时显示未区分，不能猜姓名。只接 ASR，不接纪要模型。

### 8.1 生成与存储

1. 校验 JSON 片段：文本非空、毫秒为整数、`0 <= start < end`、时间不超当前 WAV 时长（允许最多 1ms 表示精度误差），起点不倒序。合法的多人重叠允许保留。
2. 准备版本化 JSON `{schema_version:1,time_unit:"ms",cues:[...]}`，在步骤 5 的最终事务中整体写入 `recordings.transcript_json`，关联 transcript_revision；不另建 transcript_cues 表。它是唯一结构化文字主源，**识别出的原文必须存入 SQLite**，VTT 和 Markdown 均由同一批 cues 生成。采用 UTF-8 纯文本、整数毫秒和可空 speaker，完整 JSON/字段/空结果约定见[转写格式](2026-10-29-google-login-and-transcript-contract.md#transcript-format)及[JSON 示例](../../examples/transcript.json)。不把 VTT 标签或转义后的 HTML 存进 text。
3. 生成 UTF-8 `transcript.vtt`，使用 `WEBVTT` 文件头、空行、稳定 cue 编号、`HH:MM:SS.mmm --> HH:MM:SS.mmm` 和可选 voice 标签。说明依据：[W3C WebVTT 格式](https://www.w3.org/TR/webvtt1/)。
4. 用户文本的 `& < >` 转义，空白行规范化，speaker 标签只来自受控映射，不将 ASR 内容当任意 HTML/VTT 控制块。
5. VTT 通过相同文件发布流程校验/持久，随后在短事务中提交 transcript_json、vtt_job_id 指针和 transcript_revision/state；中断时不显示文字 ready，重启可重做。若仅有已 rename 的 VTT 而 cues 事务未提交，不能只凭文件 hash 补 ready：废弃该次未提交的派生产物并用同版本 WAV 重跑 ASR，新的 cues/VTT 重新一起发布；raw/WAV 保留。

ASR 耗时不影响 WAV 播放。新 WAV 发布后，只展示与 audio_revision 相同的 cues/VTT；旧文字不贴到新时间轴。没有用户历史版本切换：处理中提示等待即可。当前输入更新期间仍可保留上一份音频与同版本文字，标“更新中”；新音频替换时旧文字先隐藏。

### 8.2 实际 VTT 示例

以下为人工编写的演示内容，不是用户录音。完整文件：[recording.vtt](../../examples/recording.vtt)。

```vtt
WEBVTT

1
00:00:00.000 --> 00:00:02.400
<v A>我们确认一下今天的安排。</v>

2
00:00:02.400 --> 00:00:05.800
<v B>先检查设备，再核对录音文字。</v>
```

下载 MIME 为 `text/vtt; charset=utf-8`。Web 默认显示清爽文字及 speaker，不强制显示时间戳、不增加字幕编辑器；时间戳用于当前音频对应的定位与 VTT 下载。需要跟随播放时使用这同一组 cues，不额外维护另一套字幕数据。

### 8.3 下载

原型保留 WAV 与 `.md`；按用户追加要求，在同一个导出菜单加 `.vtt`，不增加新页面。WAV/VTT 为磁盘文件，其索引在对应 jobs 行，Markdown 按当前 cues 流式生成：日期标题和 A/B 文字，不夹带摘要。没有 Word、TXT、异步导出记录、过期链接或公开分享链接。

</details>

<a id="web"></a>

## 9. Web 与 API

<details>
<summary>展开实现细则</summary>

只保留“录音、设备”两个导航和账号菜单，品牌显示以新原型“录音助手”为准；Boa 仅为内部包/仓库名。

列表标题由录音时间生成，不提供改名。按开始/结束日期筛选，无搜索框；结束日期按业务时区次日零点转 UTC 半开区间。第一版部署级业务时区默认 Asia/Shanghai，不增加用户时区设置表。日期非法或开始晚于结束返回 422；设备时间不可信时用收件时间并提示来源。列表每页 30 条，按日期/id 稳定分页。

详情为文字、复制、导出与基础播放器；不强加倍速、±15 秒、全文编辑、章节或纪要。使用已有 `<audio>` 和进度控制。所有音频 Range/HEAD、VTT、Markdown 都使用同源 Cookie/Bearer + 当前 owner 直接鉴权，不新建 media_ticket 表。跨标签退出时停止音频、取消旧请求，后续 Range 拒绝；已发送的字节不能追回。

| 方法/路径（统一前缀 `/api/boa/v1`） | 内容 |
|---|---|
| GET `/auth/google/start` | 创建一次性内存登录事务，跳转 Google |
| GET `/auth/google/callback` | 消费 state、验证 Google 身份、创建本站会话后 303 回首页 |
| GET `/auth/session`；DELETE `/auth/session` | 本人基本资料和 CSRF token（no-store）；退出清 Cookie/内存会话 |
| GET `/devices` | 本人设备/能力/带时间的可信状态 |
| POST `/devices/activate` | 已验证身份、完整 UID、可信登记依据；复用/建立本人绑定 |
| POST `/devices/{id}/binding/confirm` | 设备配置读回确认，不代表真实上传 |
| PATCH `/devices/{id}` | 仅改别名 |
| DELETE `/devices/{id}/binding` | 撤上传凭证，历史录音保留；清理失败如实返回 |
| GET `/recordings?from=&to=&cursor=&limit=` | 日期筛选、列表预览与处理状态 |
| GET `/recordings/{id}` | 时间、时长、完整性、当前音频/文字版本与状态 |
| GET/HEAD `/recordings/{id}/audio.wav?revision=` | 固定音频版本，鉴权 WAV，Range 206 / 非法范围 416 |
| GET `/recordings/{id}/transcript?revision=&cursor=` | 固定版本 JSON cues，每页最多 200 条；游标绑定录音/版本 |
| GET `/recordings/{id}/transcript.vtt?revision=` | 固定音频版本的 VTT 下载 |
| GET `/recordings/{id}/transcript.md?revision=` | 固定版本 cues 生成 Markdown |
| GET `/health` | 最少服务存活信息，无用户/凭证内容 |

**跨请求版本约束：** 详情先固定 audio_revision，WAV、JSON cues、VTT、MD 请求均必须携带 revision，cue 游标也绑定 recording/revision。Server 在同一读取快照内检查请求版本为当前音频版本，文字还须匹配 transcript_revision；不匹配返回 409 `recording_revision_changed`，未就绪返回明确处理中状态，不能静默返回新版内容。响应标注版本。列表轮询发现新音频版本或收到 409 时，Web 取消旧分页/复制、停止旧播放并重新载入详情；复制全部文字必须在全部同版本分页成功后才写剪贴板。只保留内部在途读取所需旧文件，不增加历史版本 UI。

Wi-Fi 扫描/保存/删除通过 BLE，不设计对应 Server 密码接口。处理暂不可用时返回具体阶段状态；语音服务未配置显示 not_configured，不无限转圈。维护重试复用内部 job 接口/CLI，不新增用户任务管理页。旧 API `/api/audio/*` 与设备协议保持兼容。

</details>

<a id="sqlite-model"></a>

## 10. SQLite：4 张新增业务表

![四表关系](../../assets/diagrams/02-user-data-model.svg)

| 表 | 一条记录承载什么 |
|---|---|
| accounts | 基本用户与 Google sub，仍为 9 字段 |
| recordings | 录音状态、版本、当前文件任务指针、完整转写 JSON |
| recording_segments | 原始片段 + raw 路径/size/hash + 幂等来源收据 |
| jobs | decode/transcribe 任务 + 派生文件元数据 + 发布/恢复状态 |

<details>
<summary>合并清单与保留边界</summary>

| 原设计 | 合并到 |
|---|---|
| transcript_cues | recordings.transcript_json；没有全文搜索/逐句编辑需求，无需逐句表 |
| source_receipts | recording_segments 唯一 namespace/source_id 与 imported_at |
| storage_objects：raw | recording_segments 的 raw 路径/size/hash |
| storage_objects：WAV/VTT、file_publications | jobs 的文件路径/size/hash/publication_state |
| device_preferences | 既有 registry.bindings 的 display_name/name_updated_at |
| schema_migrations | SQLite PRAGMA user_version；每次迁移与版本更新同事务 |
| 新增 source_outbox | 既有 registry.sources ready 行 + projected_at |

**本次新增业务表从 10 减至 4；registry 新增 0 张表。** 既有 registry 的凭证、绑定和清理锁仍然保留，不把整个系统宣称成只有 4 张表。参考 DDL 尚未生产部署，不执行删表式真实数据迁移。

保留这四表的理由：用户跨录音复用；录音包含多个独立原件；同一录音可同时存在旧版本处理任务与新版本等待任务。jobs 因而保留独立行，原始片段不能塞进单个录音字段。文字当前只有一版展示，可放一个有界 JSON：最多 8 MiB UTF-8、100000 cues、每句 10000 字符，超限明确失败，不截断。API 仍按 200 cues 分页；实现可用 SQLite json_each 在固定快照取页，避免每个请求构造全部句子；导出逐句迭代。没有额外的 JSON 文件副本或逐句表。

recordings 的 wav_job_id/vtt_job_id 用 owner/录音/版本复合 FK 指向 jobs；文件发布与文件读取同时验证 job.kind、state/publication_state、size/hash；文字 API 独立读取录音当前 JSON，不因 VTT 文件缺失而丢掉已存文字。原件来源唯一约束负责幂等，条件更新 receiving→ready 与 input_revision 递增同事务。每次启动对账全部 registry ready 来源，分批 500 条异步执行，不阻塞 DTLS。

迁移脚本保存在 Git，业务库通过 PRAGMA user_version 顺序升级并拒绝未知高版本；实施中同时把既有 registry.py 的 bindings/sources 位置式 INSERT 改为显式列名，防止 ALTER ADD COLUMN 后旧写入因列数变化失败；加入真实旧 schema 升级夹具。registry 增量先检查既有列，沿用其迁移所有权，不覆盖其他组件版本号。每连接 foreign_keys=ON、busy_timeout=5000、synchronous=FULL；业务库 WAL。音频不入 BLOB。登录事务/会话仍只在内存。

</details>

<a id="operations"></a>

## 11. 实施与验收

![实施顺序](../../assets/diagrams/12-implementation-order.svg)

<details>
<summary>展开实现细则</summary>

实施重排为 **S01–S12，共 12 项任务**，旧 T00–T23 不再作为当前待办。先基本用户/设备链路，再收件与 WAV，接 ASR/VTT，最后完善列表/详情/设备页面与迁移验收。见[任务计划](../plans/2026-10-29-boa-server-web-v1-implementation-plan.md)。

备份保持简单：停服务、持排他维护锁、整体备份 SQLite/WAL、raw、identity、配置/凭证与派生文件；私密备份不入仓库。在隔离副本迁移并核对 user_id、绑定、数量、字节和 hash；真实根不直接试迁移。回退前先保存新收件原件，不能用旧快照覆盖上线后录音。不额外开发备份调度平台或人为设定未测容量承诺。

验证分层：表/约束与 API 测试；真实浏览器；真实 Clip 收件；实际 WAV 解码/播放；ASR 样本与 VTT 解析；固件能力缺项；恢复演练；实际部署。重启会清空网页登录状态，恢复后再次 Google 登录；用户、绑定、录音、任务均从持久存储恢复。

此轮只更新文档/参考 SQL/图，不执行登录配置、刷写、生产数据迁移或部署。

</details>

[自我评审与验收缺口](../../2026-10-29-design-self-review.md) · [登录与转写数据契约](2026-10-29-google-login-and-transcript-contract.md)
