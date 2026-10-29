# 录音助手精简版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans, or superpowers:subagent-driven-development when explicitly selected, to implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按新原型完成基本用户、设备添加/Wi-Fi、录音日期列表、WAV 播放、转写文字与 MD/VTT 下载。

**Architecture:** Python 单进程 + SQLite + 静态 Web，复用既有 DTLS 和 BLE。只处理原件→WAV→ASR/cues/VTT，持久任务与文件发布记录负责最少的故障恢复，不引入纪要、搜索、回收站或导出平台。

**Tech Stack:** 现有 Python/FastAPI/Uvicorn/SQLite、原生 ES modules、pytest、Node test runner、受控媒体工具、私有 ASR adapter。

**Spec:** [精简设计](../specs/2026-10-29-boa-server-web-v1-design.md)、[业务 SQL](../specs/2026-10-29-boa-v1-business-schema.sql)、[registry SQL](../specs/2026-10-29-boa-v1-registry-additions.sql)、[原型核对](../../2026-10-29-prototype-review.md)、[VTT 示例](../../examples/recording.vtt)。

## Global Constraints

- 本轮只更新文档。旧 T00–T23 计划作废，重排为 **S01–S12，12 个任务、60 个步骤**，不沿用旧任务号的含义。
- 文档仓库为 boboliu-1010/speaker；实施基线为 BofAI/reSpeaker_Clip，本机此前检出 `/Users/bobo/code/respeaker-boa-integration`。实施时先核对当前源码和 AGENTS，使用 using-git-worktrees 建隔离工作区，并记录文档 commit。
- 保留单进程、一个目录锁、9529 Web、9528 HTTPS/UDP DTLS、v3 原始帧/ACK；不把 ASR 放在接收线程。
- 用户表只有既定 9 个字段；两个导航“录音、设备”，账号菜单邮箱/退出；OAuth 细节、本地密码/邀请/组织不在任务中。
- raw 与 WAV 双保留；同一 WAV 用于播放、ASR、下载；不存 MP3、持久分段 WAV、重复 ASR WAV；VTT 是转写产物，MD 由同组 cues 即时生成。
- WAV 16 kHz / mono / PCM16 LE；raw 单段 8 MiB、连续处理默认 8 小时上限；旧协议无整段闭合证据，静默 10 分钟只是处理触发。
- SQLite 每连接 FK=ON、busy_timeout=5000、synchronous=FULL；UTC 毫秒；部署业务时区默认 Asia/Shanghai；原件不因错误或移除设备删除。
- 一个活动任务；lease 60 秒、15 秒续期；最多重试 3 次，间隔 30 秒/2 分钟/10 分钟。任务完成检查当前输入版本/lease，不做历史结果切换页面。
- Wi-Fi 只用 Clip 经 BLE 返回的周围扫描列表：选择 SSID、输入密码、BLE 设置；不从 Mac/Server 扫描，不手填 SSID。已保存网络最多 5 个按真实能力展示；没有 Clip 扫描能力则标未完成，不回退手填。

## Review Focus

1. 相同邮箱不同身份、旧 user_id 映射：不自动合并或移走历史录音。S02。
2. 激活请求重放、设备已属别人、移除时还在上传：同用户幂等、异用户拒绝、立即撤凭证，历史文件归属不变。S03/S11。
3. raw/DB 双写、重启、迟到片段：不丢原件、不重复增版本、旧 lease 不覆盖新结果。S05–S07。
4. ASR 畸形时间戳、文本注入、多人重叠、VTT 中文：有效 cue 保留，非法 cue 不发布，转义正确，音频与文字同版本。S08/S10。
5. 时区日期边界、多标签退出、Range 越界：结束日期包含当天，跨用户无泄露，后续流请求拒绝，非法范围 416。S07/S09/S10。

## 顺序与文件边界

![实施顺序](../../assets/diagrams/12-implementation-order.svg)

| 顺序 | 任务 | 前置 | 可审查交付 |
|---|---|---|---|
| 1 | S01 基线与精简 SQL 迁移 | 无 | 11 张业务表、1 张 registry 增量、旧数据夹具 |
| 2 | S02 基本用户与会话 | S01 | 用户唯一性、当前会话、退出、owner 门禁 |
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

新增后端放 `server/boa/product/`：`db.py`、`users.py`、`devices.py`、`recordings.py`、`jobs.py`、`files.py`、`decode.py`、`transcript.py`、`routes.py` 和 `migrations/`；不新建多层通用平台。测试放 `server/boa/tests/product/`。

新 Web 放 `server/web/product/`：`index.html`、`style.css`、`app.mjs`、`api.mjs`、`devices.mjs`、`recordings.mjs`、`detail.mjs`，复用原 BLE/绑定模块；对应 Node 测试仍放 `server/web/tests/`。旧 `/firmware/`、App API 不删除，不新开发其功能。

公共契约在 S01 定义：

- `Actor(user_id: str, auth_version: int)`：由服务端认证取得，不接受请求指定 owner。
- `SourceEvent(event_id, owner, namespace, source_id, session, epoch, segment_no, relative_path, size, sha256, created_at_ms)`：只包含服务端已确认来源。
- `InputSnapshot(recording_id, owner, revision, sources: tuple[SourceEvent, ...])`：按片段号冻结，hash 列表进 job.input_json。
- `Lease(job_id, recording_id, revision, token, expires_at_ms)`：存储/发布都引用同一个 fence。
- `Cue(index: int, start_ms: int, end_ms: int, speaker: str | None, text: str)`：JSON、VTT、MD 的共同结构。

下列模块接口均在 `ProductContext` 内装配：该上下文包含 root、Registry、BusinessDB、clock_ms 和按 recording/source 键的锁。S01 负责定义，后续任务不可另造身份/时间单位。测试 fixture `ctx`、`two_users`、`source_factory`、`fake_clock`、`faults` 均使用临时库和合成资料。

## S01：实施基线与版本化精简迁移

**Files：** 新增 `product/{__init__,contracts,db}.py`、`product/migrations/*.sql`、`tests/product/{conftest,test_db}.py`、基线记录；修改打包文件清单。**接口：** `migrate(root: Path, dry_run: bool) -> dict`、`BusinessDB.connect() -> sqlite3.Connection`。

- [ ] 核对源码 SHA/AGENTS、建立隔离工作区和 `.venv-boa`，执行原 Python/Node 测试并记录现有失败；这一步不把环境缺失当通过。
- [ ] 写 `test_schema_has_only_minimal_tables`、`test_legacy_ids_and_time_units_survive_migration`，运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_db.py -q`，确认新要求 FAIL。
- [ ] 参考 SQL 转为真实版本化迁移，保留旧 registry/上传库；新业务库 11 表、registry source_outbox，连接 PRAGMA、毫秒桥接与公共契约一次统一。
- [ ] 重跑目标测试 PASS，FK/integrity、旧库夹具升级、失败重跑、未知高版本拒绝均验证；不对真实数据根试迁移。
- [ ] 仅提交代码/合成 fixture/文档，提交 `feat: establish minimal recording data model`。

## S02：基本用户、会话和统一 owner 检查

**Files：** `product/users.py`、`test_users.py`；修改 `web_sessions.py`、`boa_app.py`。**接口：** `sync_verified_user(sub: str, email: str, name: str) -> str`、`principal(request: Request) -> Actor`、`logout(request: Request) -> None`。

- [ ] 写 `test_sub_reuses_owner`、`test_same_email_never_merges_user`、`test_logout_keeps_recordings`、`test_disabled_user_denied`；断言 9 字段、空昵称可用、旧用户 sub 可空但不凭邮箱认领。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_users.py -q`，确认 FAIL。
- [ ] 消费已有可信身份适配器结果，做用户资料同步、Cookie 会话、当前用户/退出与 CSRF/Origin 门禁；旧 Bearer 兼容。不存在可信登录适配时使用测试注入，不对客户端开放“任意 sub 登录”。
- [ ] fake clock 验证 30/90 天边界、跨标签退出与禁用；跨用户旧/新 API 均不可读，目标及原会话测试 PASS。
- [ ] 提交 `feat: add basic user and session ownership`。

## S03：最少的设备激活、改名与移除

**Files：** `product/devices.py`、`test_devices.py`；适配 `registry.py`、`device_configurations.py`。**接口：** `activate(actor: Actor, uid: str, evidence: dict) -> dict`、`rename(actor: Actor, device_id: str, name: str) -> None`、`remove(actor: Actor, device_id: str) -> dict`。

- [ ] 写 `test_activation_requires_trusted_enrollment`、`test_same_owner_activation_is_idempotent`、`test_other_owner_cannot_claim`、`test_remove_revokes_upload_but_keeps_audio`。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_devices.py -q`，确认 FAIL。
- [ ] 把原型自动激活接到既有可信登记/发放和 binding/epoch/读回 API，凭据只给本人并 no-store。别名只写 device_preferences；移除先撤凭证，离线清理保留既有锁。UID 不是认证，不自创邀请/激活码/远程信任机制。
- [ ] 目标测试及原绑定回归 PASS；若现有发放/固件不能提供可靠证据，记录自动激活真实联调未完成，而不是给未知设备放行。
- [ ] 提交 `feat: adapt trusted device activation and removal`。

## S04：两导航、账号菜单与添加设备向导

**Files：** `server/web/product/{index.html,style.css,app.mjs,api.mjs,devices.mjs}`、`server/web/tests/product-shell.test.mjs`；修改 `frontend.py`。**接口：** `createApi({fetcher,onLogout}) -> {request,reset}`、`mountDeviceWizard({root,api,ble}) -> {dispose}`。

- [ ] 写 `only recordings and devices navigation`、`account menu only shows email and logout`、`stale response is cancelled`、`activation readback is not upload success`。
- [ ] 运行 `node --test server/web/tests/product-shell.test.mjs`，确认 FAIL。
- [ ] 新 `/` 静态入口复现原型，显示“录音助手”；向导为准备/连接/自动激活/设置 Wi-Fi，调用 S03 接口及原 BLE 读回/校时；不加设置页、管理工作台或 OAuth 时序 UI。
- [ ] 目标 JS/原 frontend 测试 PASS；Chrome 核对空态、选择器取消、BLE 不支持、失败重试和关闭向导；不写真实设备即记录仅浏览器/模拟验证。
- [ ] 提交 `feat: add minimal recording assistant web shell`。

## S05：收件 outbox、聚合和上传状态

**Files：** `product/recordings.py`、`test_sources.py`；修改 `registry.py`、`receiver.py` 和 App 完成适配。**接口：** `import_ready(ctx, event: SourceEvent) -> str`、`sync_receiving(ctx) -> int`、`snapshot(actor: Actor, recording_id: str) -> InputSnapshot`。

- [ ] 写 `test_raw_ack_does_not_wait_for_business`、`test_ready_event_replay_changes_revision_once`、`test_receiving_has_no_ready_file`、`test_gap_and_new_epoch_not_merged`。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_sources.py -q`，确认 FAIL。
- [ ] raw/identity/fsync/ACK 保持旧语义；ready 来源与 outbox 同库事务，business 投影和收据同库事务。扫描 receiving 显示真实上传中，ready 才生成原件对象/增版本；App 仅兼容既有接口。
- [ ] 在 raw 后、registry 后、business 后、消费标记前故障注入并重启，均不丢原件、不重复录音；原 DTLS/HTTP 回归 PASS。
- [ ] 提交 `feat: project raw recordings through replayable source events`。

## S06：两类持久任务与文件发布恢复

**Files：** `product/jobs.py`、`files.py`、`test_jobs.py`、`test_files.py`；修改服务 lifespan。**接口：** `enqueue(snapshot: InputSnapshot, kind: str) -> str`、`claim(now_ms: int) -> Lease | None`、`publish(lease: Lease, object_id: str, tmp: Path, metadata: dict) -> str`、`recover(ctx) -> int`。

- [ ] 写 `test_single_active_job`、`test_expired_lease_cannot_publish`、`test_rename_before_commit_recovers`、`test_new_revision_fences_old_output`。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_jobs.py server/boa/tests/product/test_files.py -q`，确认 FAIL。
- [ ] 实现 decode/transcribe 去重、60 秒 lease/15 秒续期、有界重试；prepared→临时 fsync→预期 hash→同盘独占 rename/目录 fsync→ready。用输入版本和租约控制发布，不创建多套运行历史表。
- [ ] 对发布边界中断、磁盘满、hash 冲突、文件缺失、双监听重复启动运行时做测试，PASS；服务退出停止领新任务，15 秒后留待重启恢复。
- [ ] 提交 `feat: add minimal durable processing and file publication`。

## S07：raw 解码为一份 WAV，鉴权 Range 播放

**Files：** `product/decode.py`、`test_decode.py`、`test_audio_http.py`；修改 `product/routes.py`、依赖/工具版本清单。**接口：** `decode(snapshot: InputSnapshot, output: Path) -> dict`、`serve_audio(actor: Actor, recording_id: str, revision: int, range_header: str | None) -> Response`。

- [ ] 写 `test_raw_packet_framing_to_16000_mono_pcm16`、`test_bad_packet_preserves_raw`、`test_gap_does_not_get_silence`、`test_range_owner_and_logout`；1 秒合成样本应得 16000 样本，Range 合法 206、非法 416。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_decode.py server/boa/tests/product/test_audio_http.py -q`，确认 FAIL。
- [ ] 按实际 raw profile 解包/封装并解码，临时分段后合一份 WAV；raw 不改写，样本数/独立 hash 入库；S06 发布当前音频。WAV 同时供播放、ASR、下载，不生成 MP3。Cookie/Bearer + owner 直接鉴权，不加 ticket 系统。
- [ ] 目标测试和授权真实样本解码/试听分别通过；验证长录音拖动、超时/体积限制、并发新片段和旧音频仍可安全读取，记录 pre-skip 时间来源限制。
- [ ] 提交 `feat: decode and serve persistent recording wav`。

## S08：ASR 文字、说话人与 WebVTT

**Files：** `product/transcript.py`、`test_transcript.py`、`test_vtt.py`；复用 `docs/examples/recording.vtt` 为人工示例，不提交真实音频。**接口：** `ASR.transcribe(wav: Path, request_id: str) -> list[Cue]`、`validate_cues(cues: list[Cue], duration_ms: int) -> list[Cue]`、`render_vtt(cues: list[Cue]) -> bytes`、`publish_transcript(lease: Lease, cues: list[Cue]) -> None`。

- [ ] 写 `test_vtt_header_utf8_milliseconds_and_voice`、`test_invalid_time_rejected_but_valid_overlap_kept`、`test_untrusted_text_escaped`、`test_old_transcript_not_on_new_wav`；示例应解析出 2 个 cue，结尾 5800ms，speaker A/B，空/逆序/越界拒绝。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_transcript.py server/boa/tests/product/test_vtt.py -q`，确认 FAIL。
- [ ] 接一套实际私有 ASR adapter，未配置明确 not_configured；校验后生成 UTF-8 VTT，按 S06 持久发布，并把 cues/文件指针/文字 ready 原子提交。当前 audio_revision 与 transcript_revision 一致才对外显示；没有说话人就不编造。
- [ ] 目标测试 PASS，浏览器实际解析示例 VTT；真实端点用授权样本检查时间/文本/分离质量。缺端点时只记契约通过；ASR 失败仍可播放 WAV，无纪要模型任务。
- [ ] 提交 `feat: add timestamped transcripts and webvtt output`。

## S09：日期列表 API 与 Web

**Files：** 扩展 `product/{recordings,routes}.py`、`server/web/product/recordings.mjs`；新增 `test_recording_list.py`、`product-recordings.test.mjs`。**接口：** `list_recordings(actor: Actor, from_date: str | None, to_date: str | None, cursor: str | None, limit: int=30) -> dict`。

- [ ] 写 `test_inclusive_end_date_uses_next_local_midnight`、`test_invalid_dates_and_owner_filter`；JS 断言只有日期筛选、文字开头预览、无纪要/全文搜索/录音改名入口。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_recording_list.py -q`、`node --test server/web/tests/product-recordings.test.mjs`，确认新用例 FAIL。
- [ ] COALESCE 可信录音时间/收件时间后按部署时区分组，结束日转次日零点半开区间；每页 30 条稳定日期/id 游标。显示真实 receiving、处理状态和时长；可见 5 秒/隐藏 30 秒轮询、日期变化取消旧请求。
- [ ] 目标测试 PASS；Chrome 检查同日/跨日、清空筛选、无数据、后端离线和返回列表；不暴露其他 owner。
- [ ] 提交 `feat: add date filtered recording list`。

## S10：详情、基础播放器、复制与 WAV/MD/VTT 下载

**Files：** `server/web/product/detail.mjs`、`test_downloads.py`、`product-detail.test.mjs`；扩展 transcript/routes。**接口：** `get_cues(actor: Actor, recording_id: str, revision: int, cursor: str | None) -> dict`、`render_markdown(cues: list[Cue], heading: str) -> bytes`、Web `mountDetail({root,api,audio,id}) -> {dispose}`。

- [ ] 写 `test_wav_md_vtt_same_owner_and_revision`、`test_publication_between_pages_requires_reload`、`test_markdown_has_transcript_not_summary`；JS 断言复制文字、播放暂停/拖动、退出清理音频，没有倍速/章节/纪要/编辑器/回收站。
- [ ] 运行 `.venv-boa/bin/python -m pytest server/boa/tests/product/test_downloads.py -q`、`node --test server/web/tests/product-detail.test.mjs`，确认 FAIL。
- [ ] 展示日期标题、时长、A/B 文字；cue 分页每页 200 条，复制/MD 覆盖全部当前文字而不只第一页。导出菜单为 WAV/Markdown，并追加用户要求的 VTT。详情固定 audio_revision，四类内容请求和 cue 游标都带 revision；读快照内匹配当前音频/文字版本，否则 409，Web 取消分页/播放后重新载入，不能复制部分混合结果。MD 即时生成，无 exports 表/异步导出任务/24 小时链接。
- [ ] 目标测试 PASS；Chrome 试听/拖动、复制全文、下载 WAV/MD/VTT 并核对中文/时间戳和 MIME；新 WAV 就绪时隐藏不同版本文字，切换账号中断旧请求。
- [ ] 提交 `feat: add simple transcript detail and wav md vtt downloads`。

## S11：设备卡片与基于 Clip 扫描的 Wi-Fi 配置

**Files：** 扩展 `product/devices.py`、`server/web/product/devices.mjs` 和既有 BLE adapter；新增 `product-wifi.test.mjs`、`test_device_views.py`。**接口：** BLE adapter `capabilities()`、`scanWifi() -> {ssid,rssi,security}[]`、`saveWifi(selectedSsid,password)`、`readWifiStatus()`、`deleteWifi(ssid)`；扫描与连接状态由 Clip 真实返回，缺能力为 unsupported。

- [ ] 写 `wifi list comes from clip scan over ble`、`ssid must be selected from scan results`、`missing scan does not enable manual ssid`、`saved is not connected`、`at most five saved networks`、`password never sent to server`；后端验证别名/归属/移除保留录音，状态来源不明不显示在线。
- [ ] 运行 `node --test server/web/tests/product-wifi.test.mjs`、`.venv-boa/bin/python -m pytest server/boa/tests/product/test_device_views.py -q`，确认 FAIL。
- [ ] 设备卡片保留改名、版本、状态、Wi-Fi 管理和移除；Wi-Fi 操作固定为连接 BLE→请求 Clip 扫描→选择返回的 SSID→输入密码→BLE 写入→读取保存/连接结果。空列表/超时重扫、密码错误重输；没有手动 SSID、远处网络或本机扫描入口。没有 Clip 扫描能力就禁用新增配置并标缺项，已保存项仍可按真实能力查看/删除。
- [ ] 模拟边界测试 PASS；实机验证扫描列表确实来自目标 Clip、选网/密码写入/连接结果、删除/重连/移除；不能把 mock 当扫描或 5 网络支持。缺扫描则该配置闭环未验收，不能以手填方式完成；自动激活、多 Wi-Fi、遥测缺项分别记录。
- [ ] 提交 `feat: align device cards and wifi management with prototype`。

## S12：整体回归、迁移恢复与候选包

**Files：** `tests/product/test_end_to_end.py`、`docs/development/recording-v1-acceptance.md`；修改打包脚本/部署说明，必要时新增小型迁移/备份 CLI。**产出：** 候选包、源码/依赖/文档 SHA、分层检查记录；不自动部署或刷写。

- [ ] 在隔离夹具写端到端失败用例：用户→设备→receiving→raw→WAV→文字/VTT→列表→复制/下载→移除设备，断言历史文件归属不变，Bob 全路径不能访问 Alice。
- [ ] 执行 `.venv-boa/bin/python -m pytest server/tests server/boa/tests server/storage/tests -q`、`.venv-boa/bin/python -m unittest tools.upload.tests.test_dtls_receiver -v`、`node --test server/web/tests/*.test.mjs`，修复回归；环境缺失单列。
- [ ] 真实浏览器、可信身份适配、Clip 收件、WAV 试听、ASR/VTT、Wi-Fi 实机分别验收；记录缺失的发放/固件能力，不做新的固件功能或 OAuth 协议开发来掩盖缺项。
- [ ] 停机整体备份并在隔离目录迁移/恢复，核对旧 user_id、设备、raw 数量/字节/hash；回退先保存新录音；测实际响应/处理时间并记录，不承诺未测吞吐。
- [ ] 打包排除录音/数据库/凭证，核对 manifest/哈希；提交 `release: prepare minimal recording assistant candidate` 并明确未完成的真实验收，不将候选包称为已上线。

## 交付里程碑

- **M1：S01–S04。** 基本用户和设备向导可用；自动激活需真实可信发放能力，不是仅有 UI。
- **M2：S05–S08。** 原件入库、WAV 双保留、可播放，ASR/cues/VTT 全链路恢复可测。
- **M3：S09–S12。** 日期列表、文字/下载、设备卡片与实机/迁移验收，形成候选包。

本计划使用 writing-plans 工作流完成自检：设计每项保留功能都有责任任务；删减功能无残留任务；VTT 在 S08/S10/S12 贯通；公共类型不各模块重定义；图/DDL/任务以同一文档提交为准。步骤中的 FAIL/PASS 是未来实施要求，本轮没有执行这些产品测试。
