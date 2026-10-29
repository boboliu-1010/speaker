# 音频存储、双写与 VTT 开发设计

v1 · 2026-10-29 · [Server / Web 主文档](../README.md)

## 关键点

1. 本模块负责 raw/WAV/VTT 文件存储、转写原文、文件与数据库双写、安全读取和恢复。
2. 原件先完成文件和来源索引持久化，再给设备 COMPLETE；解码与 ASR 在后台独立处理。
3. WAV/VTT 先可靠落盘，再提交 jobs 和录音指针；转写 JSON 与 VTT 指针在同一事务提交。
4. 每个文件关联 owner、recording_id 和版本；通过鉴权接口读取，存储卷与独立备份采用加密保护。
5. raw 原件与当前 WAV 分别保留，VTT/Markdown 由同组原文生成；损坏或中断按已提交状态恢复。

[收件](#ingest) · [字段](#tables) · [存储](#storage) · [转写](#transcript) · [双写恢复](#publication) · [接口](#media-api) · [安全](#security)

<a id="ingest"></a>

## 1. 原件收件与录音聚合

![收件与投影](assets/diagrams/04-raw-ingest-outbox.svg)

| 数据 / 操作 | 规则 |
|---|---|
| 原件格式 | uint16 little-endian 包长度 + Opus payload；校验包边界、size/hash 与媒体 profile |
| 持久确认 | data fsync、持久检查点、完整 hash、rename/目录 fsync；raw、身份元数据及 registry.sources ready 持久后返回 COMPLETE |
| 来源归属 | 从有效设备 binding 或已验证 App 来源取得 owner；旧来源 owner 保持原值 |
| 聚合键 | source_kind + source_namespace + binding_epoch + source_session；Clip 的 source_namespace 使用 binding_id，App 使用包含 owner 和来源标识的稳定命名空间 |
| 输入版本 | 原始片段首次 ready 导入时 input_revision 加 1；重复来源保持版本 |
| 处理触发 | 片段从 1 开始连续且静默 10 分钟后处理当前已收内容；缺号时等待补齐 |
| 完整性 | 现有协议缺少整段闭合信息时保持 unknown；确认完整须有协议证据 |

业务投影使用一个短事务：按 source_namespace/source_id 查询片段；已有 ready 且 owner、recording_id、segment_no、hash/size 全部一致则幂等返回，冲突报 source_identity_conflict；首次 ready 同时保存原件元数据、imported_at 并增加录音版本。business 提交后再更新 registry.sources.projected_at。

启动按每批 500 条核对全部 ready 来源，检查 raw 存在和 size/hash；来源时间 created 从既有秒值转为 UTC 毫秒。receiving 保存上传状态，校验完成后创建处理输入。

<a id="tables"></a>

## 2. 处理对象与数据表

完整 DDL 见[主文档](../README.md#business-sql)。下面说明录音处理使用的三张表；时间为 UTC Unix 毫秒，时长为毫秒，size 为字节数。

### 2.1 recordings

| 字段 | 类型 | 约束 / 默认 | 含义 |
|---|---|---|---|
| id | TEXT | 主键；必填 | 录音 ID。 |
| owner | TEXT | 必填；外键 | 所属用户 ID，引用 accounts.user_id。 |
| source_kind | TEXT | 必填 | 来源类型：clip_direct / app_upload。 |
| source_namespace | TEXT | 必填 | 全局来源空间：Clip 用 binding_id，App 空间包含 owner 与既有来源标识。 |
| binding_epoch | INTEGER | 必填；≥0；Clip >0 | Clip 绑定代次；App 来源为 0。 |
| source_session | TEXT | 必填 | 来源的录音 session；与来源/绑定代次一起确定一条录音。 |
| recorded_at | INTEGER | 可空 | 录音时间，可空；时间不可信时按 received_at 查询。 |
| time_source | TEXT | 必填 | device_unverified / server_received / client_confirmed。 |
| received_at | INTEGER | 必填 | 首次收件时间。 |
| last_received_at | INTEGER | 必填 | 最近片段收件时间。 |
| integrity | TEXT | 必填；默认 'unknown' | unknown / gap / confirmed_complete；依协议证据更新。 |
| input_revision | INTEGER | 必填；默认 0；≥0 | 已收输入版本；新 ready 片段首次导入时加 1。 |
| audio_revision | INTEGER | >0 且 ≤ input_revision | 当前 WAV 对应的输入版本，可空。 |
| transcript_revision | INTEGER | >0 且 ≤ input_revision | 当前转写对应的输入版本，可空；ready 时等于 audio_revision。 |
| audio_state | TEXT | 必填；默认 'pending' | 当前输入的解码状态：pending / running / ready / failed。 |
| transcript_state | TEXT | 必填；默认 'pending' | not_configured / pending / running / ready / failed。 |
| wav_job_id | TEXT | 录音/owner/版本复合外键 | 当前 WAV 的 decode 任务，可空。 |
| vtt_job_id | TEXT | 录音/owner/版本复合外键 | 当前 VTT 的 transcribe 任务，可空。 |
| duration_ms | INTEGER | ≥0 | 当前 WAV 时长，毫秒，可空。 |
| transcript_json | TEXT | 合法 JSON v1；≤8 MiB | schema_version、time_unit、cues，可空。 |
| updated_at | INTEGER | 必填 | 录音状态或结果更新时间。 |

### 2.2 recording_segments

| 字段 | 类型 | 约束 / 默认 | 含义 |
|---|---|---|---|
| id | TEXT | 主键；必填 | 原始片段 ID。 |
| owner | TEXT | 必填；与录音组成复合外键 | 所属用户；与 recording_id 对应的录音一致。 |
| recording_id | TEXT | 必填；与 owner 组成复合外键 | 所属录音 ID。 |
| source_namespace | TEXT | 必填 | 来源命名空间。 |
| source_id | TEXT | 必填；与 source_namespace 组合唯一 | 来源索引 ID；与 source_namespace 组成幂等键。 |
| segment_no | INTEGER | 必填；>0；录音内唯一 | 录音内片段号，从 1 开始。 |
| state | TEXT | 必填 | receiving / ready。 |
| raw_relative_path | TEXT | 唯一 | 原件相对路径，可空；ready 时必须存在。 |
| size_bytes | INTEGER | >0 | 原件字节数，可空；ready 时必须存在。 |
| sha256 | TEXT | 64 字符 | 原件的 SHA-256，可空；ready 时必须存在。 |
| received_at | INTEGER | 必填 | 片段首次接收时间。 |
| imported_at | INTEGER | 可空 | 首次导入业务库的时间，可空；ready 时填写，兼作来源收据。 |

### 2.3 jobs

| 字段 | 类型 | 约束 / 默认 | 含义 |
|---|---|---|---|
| id | TEXT | 主键；必填 | 任务 ID；一个任务对应一个 WAV 或 VTT 文件。 |
| owner | TEXT | 必填；与录音组成复合外键 | 任务所属用户，与录音 owner 相同。 |
| recording_id | TEXT | 必填；与 owner 组成复合外键 | 任务处理的录音 ID。 |
| input_revision | INTEGER | 必填；>0 | 任务对应的输入版本。 |
| kind | TEXT | 必填；与录音/版本组合唯一 | decode / transcribe。 |
| state | TEXT | 必填 | pending / running / retry_wait / succeeded / failed。 |
| attempt | INTEGER | 必填；默认 0；0–4 | 已执行次数；0–4，包含首次执行与 3 次重试。 |
| run_after | INTEGER | 必填 | 允许领取的最早时间。 |
| lease_token | TEXT | 可空 | 当前执行的随机标识，可空；running 时填写。 |
| lease_until | INTEGER | 可空 | 当前执行的到期时间，可空；running 时填写。 |
| input_json | TEXT | 必填；合法 JSON | 固定的原件清单、hash、配置版本；转写任务固定 WAV 任务/hash，文件修复时保存 repair_expected 元数据。 |
| publication_state | TEXT | 必填；默认 none | none / prepared / ready / missing / abandoned。 |
| tmp_relative_path | TEXT | 唯一 | 临时产物相对路径，可空；prepared 时填写。 |
| final_relative_path | TEXT | 唯一 | 最终文件相对路径，可空；prepared/ready 时填写。 |
| size_bytes | INTEGER | >0 | 最终产物字节数，可空；ready 时填写。 |
| sha256 | TEXT | 64 字符 | 最终产物 SHA-256，可空；ready 时填写。 |
| sample_count | INTEGER | ≥0 | WAV 的 PCM 样本数，可空。 |
| error_code | TEXT | 可空 | 固定错误码，可空；记录失败原因。 |
| created_at | INTEGER | 必填 | 任务建立时间。 |
| updated_at | INTEGER | 必填 | 任务或文件状态更新时间。 |

| 关联 / 唯一约束 | 规则 |
|---|---|
| owner | 片段、任务与录音 owner 相同 |
| 来源唯一键 | source_namespace + source_id |
| 录音内片段 | recording_id + segment_no 唯一 |
| 后台处理 | recording_id + input_revision + kind 唯一；一个 running |
| 当前文件指针 | 复合 FK 保证录音/owner/版本；读写逻辑校验 WAV=decode、VTT=transcribe |
| registry.sources | 保存原件身份和 ready/projected_at，业务投影后再更新标记 |

<a id="storage"></a>
<a id="decode"></a>

## 3. 音频文件存储

### 3.1 保存对象与读取条件

| 数据 | 保存内容 / 元数据 | 何时可用 | 保留规则 |
|---|---|---|---|
| raw | 原件文件；registry.sources 和 recording_segments 保存归属、size/hash、路径 | 完整校验后 sources/segment 为 ready | 持续保存，用于重试和恢复 |
| WAV | 文件；decode jobs 保存最终路径、size/hash、sample_count | 文件 ready 且被 recordings.wav_job_id 引用 | 每条录音一个当前版本；旧版本在引用释放后清理 |
| 转写 JSON | recordings.transcript_json、transcript_revision | 与当前音频同版本且文字 ready | 整体替换为新版本原文 |
| VTT | 文件；transcribe jobs 保存路径、size/hash | 文件 ready 且被 recordings.vtt_job_id 引用 | 与对应 JSON 一起发布和保留 |
| Markdown | 从同版本 JSON 即时生成 | 文字 ready | 随本次下载返回 |

raw 与 WAV 是两种分别保存的音频。双写是文件持久化与 SQLite 记录提交，具体顺序见[第 5 节](#publication)。文件索引继续使用现有三张处理表，DDL 见[主文档](../README.md#business-sql)。

### 3.2 文件保存规则

| 项目 | 处理规则 |
|---|---|
| 文件标识 | owner、recording_id、job_id 由 Server 取得或生成；final_relative_path 按输入版本和本次执行生成，发布后保持不变 |
| 路径使用 | 路径只保存在索引中；Web 使用录音 API 地址；原件沿用现有 ResumeStore |
| 临时文件 | 创建时独占新文件，放在与最终文件相同的文件系统；写入期间 publication_state=prepared |
| 完整性 | raw 入库、派生产物发布、ASR 调用前与备份恢复时校验 size/SHA-256；WAV 另核对格式、样本数和时长 |
| 容量检查 | 接收前计算剩余原件空间；生成前预留临时产物与新 WAV/VTT 所需空间，并保留至少 256 MiB 余量 |
| 用户额度 | 每用户存储额度为必填部署配置，启动时检查为正整数字节数；按 owner 的原件、已登记接收量和派生文件检查，超额反馈 storage_quota_exceeded |
| 清理 | 放弃的临时文件在执行结束后清理；旧产物只有在无当前指针、未结束任务或下载引用时清理对应文件和过期 jobs 记录 |
| 原件缺失 | 保留来源索引，暂停依赖该原件的处理并记录 source_missing；由校验通过的备份恢复 |


存储失败按发生位置返回：

| 位置 | 反馈 |
|---|---|
| 原件接收 | 使用既有 HTTP/DTLS 接收协议反馈过限、空间不足或身份/hash 冲突；失败时仅保留已持久偏移 |
| 后台生成 | jobs.state=failed，error_code 保存 storage_full、storage_quota_exceeded、source_missing 或具体处理错误 |
| Web 查询 | 详情返回 audio_error_code / transcript_error_code；已成功发布的旧结果继续按版本读取 |
| 媒体读取 | 文件不可用时返回 503 audio_unavailable / vtt_unavailable；错误格式见主文档 |

### 3.3 解码与产物校验

固定来源清单，按 segment_no 从 1 连续读取。逐包解析 uint16 little-endian 长度与 Opus payload，检查包边界、size/hash 和媒体 profile；临时解码后合成一份 **16 kHz、mono、PCM16 little-endian WAV**。

sample_count 与 WAV PCM 字节数对应，duration_ms=round(sample_count×1000/16000)。Ogg granule 使用 48 kHz 时基；raw 缺少 pre-skip 元数据时沿用当前样本策略，固定 decoder/raw profile/ASR 配置版本，配置变化使用新的输入修订。

| 限制 | 值 / 失败处理 |
|---|---|
| 单 raw 段 | 8 MiB；按实际已收字节执行限制 |
| 连续录音 | 默认上限 8 小时，PCM16 约 115.2 MB/小时 |
| 单 WAV 输出 | 上限 1 GiB，与时长/样本数限制一起校验 |
| 执行时间 | decode 默认 10 分钟，ASR 默认 60 分钟 |
| 空间不足 | 接收或生成停止，原件和上一份已提交结果保留；错误为 storage_full |

解码成功后将 size_bytes、sha256、sample_count 保存到对应 jobs 行，按第 5 节发布。解码错误使用 packet_invalid、segment_gap、decode_timeout 等固定 code。WAV 使用固定 fmt/data 头和 PCM 内容，避免时间戳等可变头信息影响同版本修复的 hash。

<a id="transcript"></a>

## 4. 识别原文与 VTT

| Cue 字段 | 类型 / 含义 |
|---|---|
| cue_index | 从 1 开始的连续整数，按起点和供应方稳定顺序排列 |
| start_ms / end_ms | 当前 WAV 相对时间，整数；0 ≤ start < end ≤ duration_ms |
| speaker | A/B/C…稳定匿名映射，缺失时 null |
| text | UTF-8 原文，统一 CRLF 为 LF，保留标点和换行 |

持久格式为 `{schema_version:1,time_unit:"ms",cues:[...]}`。接口补充 recording_id、revision 和 next_cursor：

<a id="json-example"></a>

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

秒数在 ASR adapter 中转换为整数毫秒，最多 1ms 的边界精度误差夹到音频范围，处理后仍须 start<end。拒绝 NUL、非法编码、空白句和非法时间，整批校验后发布；合法多人重叠保留。每句最多 10000 字符、每录音最多 100000 cues，JSON 最多 8 MiB UTF-8，超限返回 transcript_limit_exceeded。

静音识别成功保存 cues=[]、状态 ready 和 `WEBVTT\n\n`；ASR 未配置为 not_configured，识别失败为 failed。WAV 独立可播放。

<a id="vtt-example"></a>

对应 VTT：

```vtt
WEBVTT

1
00:00:00.000 --> 00:00:02.400
<v A>我们确认一下今天的安排。</v>

2
00:00:02.400 --> 00:00:05.800
<v B>先检查设备，再核对录音文字。</v>
```

VTT 使用 UTF-8、WEBVTT 头、毫秒时间戳、稳定编号和可选 voice 标签；输出时转义 `& < >`，规范化会切断 cue 的空白行。SQLite text 保留原文，Web 用 textContent 渲染。Markdown 使用固定日期标题、speaker 模板，原文按纯文本转义后输出。格式依据：[W3C WebVTT](https://www.w3.org/TR/webvtt1/)。

<a id="publication"></a>

## 5. 文件与数据库双写

![双写状态](assets/diagrams/06-file-database-publication.svg)

### 5.1 原件双写与业务投影

| 顺序 | 文件 / 数据库操作 | 设备确认 |
|---|---|---|
| 1 | 校验有效上传凭证、owner、绑定代次和原件身份，保存 receiving 来源 | 接收请求可继续 |
| 2 | 写 raw 数据并 fsync，再持久化检查点；恢复时以检查点偏移为准 | ACK 已持久偏移 |
| 3 | 收完整后验证 size/hash，原件 rename，目录 fsync，保存可恢复的身份元数据 | 等待完成确认 |
| 4 | registry.sources 提交 ready，保留 owner、binding/session/segment、object_id、size/hash | 返回 COMPLETE |
| 5 | 业务短事务提交 recordings、recording_segments、imported_at 与输入版本；随后标记 projected_at | 后台执行 |

原件与 registry 双写完成是 COMPLETE 的条件。业务库暂不可用时，ready 来源留待投影，设备确认继续按原件持久结果执行。业务提交后标记失败则重放，相同来源只增加一次版本。

### 5.2 WAV/VTT 双写提交

| 顺序 | jobs / 文件 / 录音 | 可见性 |
|---|---|---|
| 1 | jobs 保存 owner、recording_id、input_revision、输入快照、lease、临时/最终路径，设 prepared | 处理结果未发布 |
| 2 | 生成临时文件，校验内容、size/hash，文件 fsync；预期元数据写入 jobs.size_bytes/sha256，WAV 同时写 sample_count | 处理结果未发布 |
| 3 | 复核任务身份与当前输入，按本次发布的唯一最终路径 rename，目录 fsync | 文件已存在，API 仍等待提交 |
| 4 | 一个短事务核对 owner、录音/输入版本、kind、lease_token 与有效期；提交 jobs ready/succeeded 及录音结果 | 当前版本可读 |
| WAV 结果 | wav_job_id、audio_revision、duration_ms 同事务更新；新音频替换时将旧版本文字置 pending | 音频可读取 |
| 转写结果 | transcript_json、vtt_job_id、transcript_revision、文字 ready 与 jobs 成功同事务更新 | 文字与 VTT 一起发布 |

最终路径已存在时核对该任务、版本及 size/hash；相同内容幂等复用，冲突返回 file_publication_conflict 并保留已有文件。最终事务失败时保持原录音指针，产物由恢复流程核验后处理。

### 5.3 后台执行与恢复

| 处理规则 | 值 |
|---|---|
| kind / 去重键 | decode、transcribe；recording_id + input_revision + kind |
| 执行 | 顺序领取一个任务，固定 owner、输入版本与配置 |
| 租约 | 60 秒，15 秒续期；发布时校验 token、有效期和版本 |
| 重试 | 最多 4 次执行，间隔 30 秒 / 2 分钟 / 10 分钟 |
| 旧版本 | 未执行旧版本设 state=failed、error_code=input_superseded；已过期执行停止发布 |
| 恢复次数 | 仅核验并补提交时可换租约、保留 attempt；真正重做时增加 attempt，达到上限标 failed |

| 中断 / 错误 | 恢复结果 |
|---|---|
| raw 数据已写，检查点尚未提交 | 按持久检查点恢复，未确认的尾部截断后续传 |
| raw 完整，registry ready 未提交 | 由身份元数据和 size/hash 对账补 ready，再响应重试请求 |
| 业务已提交，projected_at 未更新 | 幂等重放，保持一次版本递增 |
| WAV 已落盘，DB 最终事务未提交 | 校验元数据、当前输入和新租约后补提交 |
| VTT 已落盘，JSON 未提交 | 放弃本次未提交产物，重跑 ASR 后整体发布 |
| JSON 已提交，VTT 缺失/不可信 | 保留原文，从同版本 JSON 重建 VTT |
| WAV 缺失/不可信 | jobs.publication_state=missing，从校验通过的 raw 重建 |
| 原件缺失 | 记录 source_missing，保持来源归属，等待备份恢复 |
| 文件冲突、磁盘满、事务失败 | 保留 raw 与上一份已提交结果；API 返回明确状态 |

恢复仅处理仍被当前结果或未结束任务引用的产物；无引用旧版本进入安全清理。文件与 SQLite 分步提交，通过上述状态和幂等恢复保持一致。

### 5.4 已提交文件修复

| 项目 | 规则 |
|---|---|
| 开始修复 | 当前已成功产物首次变为 missing 时，复用同一 jobs 行，原 size/hash/sample_count 写入 input_json.repair_expected，再置 pending、attempt=0；修复失败按本轮上限停止，维护确认后才可再次重启 |
| 新路径 | 每次发布另生成 Server UUID 作为唯一标识；重试和修复使用新路径，避免复用旧 attempt 路径 |
| WAV 修复 | 使用原输入快照和固定解码配置，从 raw 重建；输出 size/hash/sample_count 必须与 repair_expected 一致，否则 repair_content_mismatch |
| VTT 修复 | 直接从已提交同版本 JSON 重建，不重新 ASR；校验结果与 repair_expected 的 size/hash 一致 |
| 修复提交 | WAV 复核 wav_job_id/audio_revision 仍指向本任务/版本；VTT 复核 vtt_job_id、transcript_revision、audio_revision 与 JSON 仍对应；只替换文件元数据，不改变录音版本和文字 |
| 已被替换 | 当前指针已更新或版本不再匹配时，放弃旧文件修复并清理本次临时产物 |

普通新结果发布以当前 input_revision 为条件；修复以当前已发布指针和版本为条件。两者都在最终事务内复核 owner 和租约，旧执行结果不能覆盖新结果。


<a id="media-api"></a>

## 6. 音频与文字 API

路径前缀 `/api/boa/v1`，携带本站会话，owner 取自会话；统一错误格式见[主文档](../README.md#web-api)。

| 接口 | 请求 | 响应 |
|---|---|---|
| GET `/recordings/{id}/audio.wav` | revision；可选 Range | audio/wav，200 或 206 |
| HEAD `/recordings/{id}/audio.wav` | revision | 200，资源头和空 body；忽略 Range |
| GET `/recordings/{id}/transcript` | revision、cursor | JSON v1，每页最多 200 cues |
| GET `/recordings/{id}/transcript.vtt` | revision | text/vtt; charset=utf-8，附件 |
| GET `/recordings/{id}/transcript.md` | revision | text/markdown; charset=utf-8，附件 |

| 状态 / code | 条件 |
|---|---|
| 401 / 403 | 会话失效 / 账号禁用 |
| 404 | 不存在或不属于当前 owner |
| 409 recording_revision_changed | 请求版本与当前音频不符 |
| 409 audio_not_ready / transcript_not_ready | 对应结果处理中 |
| 503 asr_not_configured / transcript_failed | ASR 未配置 / 识别失败 |
| 503 audio_unavailable / vtt_unavailable | WAV / VTT 文件缺失或不可用；VTT 缺失时已存 JSON 和 Markdown 仍可读取 |
| 429 | 单用户媒体请求超过并发上限 |
| 416 | GET 字节范围无效 |

### 6.1 版本与分页

详情先固定 recordings.audio_revision。所有媒体请求的 revision 为正整数；文字接口返回的 revision 取自 transcript_revision，并须等于 audio_revision。游标绑定 recording_id、revision、last_cue_index。

| 判断顺序 | 结果 |
|---|---|
| 录音不存在或 owner 不匹配 | 404 |
| audio_revision 为空 | 解码失败为 503 audio_unavailable，其余为 409 audio_not_ready |
| 请求 revision 与当前 audio_revision 不同 | 409 recording_revision_changed |
| 文字请求且 transcript_state 为 not_configured / failed | 503 asr_not_configured / transcript_failed |
| 文字处理中或 transcript_revision 尚未匹配 | 409 transcript_not_ready |
| 文件请求 | 校验 jobs.kind、publication_state、路径；WAV 来自 decode，VTT 来自 transcribe；文件缺失分别返回 503 audio_unavailable / vtt_unavailable |

同一读取快照内完成以上判断。audio_state 描述当前输入的处理进度；已有 WAV 以 wav_job_id/audio_revision 及对应文件状态判断可用性。VTT 文件缺失不影响同版本 JSON/Markdown 读取。

JSON 使用 json_each 按 cue 数组下标读取 201 条：返回前 200 条，第 201 条决定 next_cursor。Markdown 迭代同一快照的全部 cues。复制取齐同版本全部页后再写剪贴板；仅遇到 409 recording_revision_changed 时重置旧音频和分页；not_ready 状态继续查询处理结果。

### 6.2 Range 与响应头

支持单一 `bytes=start-end`、`bytes=start-`、`bytes=-suffix`。end 截至 size-1，省略 end 时取 size-1；suffix>0 时 start=max(0,size-suffix)。start≥size、start>end 或 suffix=0 返回 416 与 `Content-Range: bytes */<size>`。多范围请求按普通 GET 返回整文件 200。

以 1000 字节文件为例：

| 请求 | 响应 |
|---|---|
| GET，bytes=0-99 | 206；bytes 0-99/1000；Content-Length=100 |
| GET，bytes=900-2000 | 206；bytes 900-999/1000；Content-Length=100 |
| GET，bytes=-200 | 206；bytes 800-999/1000；Content-Length=200 |
| GET，bytes=1000- | 416；bytes */1000 |
| HEAD，bytes=0-99 | 200；Content-Length=1000，空 body |

所有媒体请求重新鉴权。JSON body 返回 revision，文件响应设置 X-Recording-Revision。WAV/VTT 使用不可变路径，ETag 取对应 jobs.sha256；响应设置 Cache-Control: private, no-store。导出文件名由 Server 生成。Range/HEAD 依据 [RFC 9110 §14.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-14.2)。

<a id="security"></a>

## 7. 文件与音频数据安全

![存储与访问边界](assets/diagrams/07-storage-security.svg)

| 保护对象 | 具体处理 |
|---|---|
| 用户隔离 | 所有列表、GET/HEAD/Range、JSON/VTT/Markdown 读取与后台处理先限定 owner；原件 owner 来自验证通过的绑定或 App 身份 |
| 上传凭证 | OPEN、续传和 COMPLETE 检查有效绑定/凭证；撤销后拒绝继续写入，历史归属保持原值 |
| 文件路径 | 服务端 ID 构造路径；逐级校验目录与文件为非符号链接，解析后位于允许存储根；读取普通文件，路径参数按固定格式校验 |
| 元数据写入 | 使用参数化 SQL，owner 由会话/来源确定；按录音、owner、版本复核关联后提交 |
| 存储访问 | 数据位于 Web 静态资源之外，由专用服务账号访问；目录 0700，音频、SQLite/WAL/SHM、配置和备份 0600 |
| 传输 | Web 使用 HTTPS，Clip 使用现有认证 DTLS；证书和设备凭证由服务端受控配置 |
| 静态数据 | 数据卷与独立备份启用存储层加密；卷解锁和备份密钥由部署环境管理，密钥与备份分开授权 |
| 文件完整性 | 发布、ASR 输入和恢复核对完整 SHA-256；下载使用同一已打开文件句柄检查类型与 size，异常停止读取并标记产物不可用 |
| 资源限制 | 接收检查实际字节数、用户额度和空间；解码限制输出/时长/超时；媒体 GET/HEAD 按 owner 最多 4 个活动请求，超额返回 429 与 Retry-After: 1 |
| 解码执行 | 以服务账号用参数数组启动受控解码器，输入输出来自验证后的文件标识；部署环境限制 CPU/内存，超时结束子进程及其临时输出 |
| ASR 出站 | 仅调用服务端配置的 HTTPS 或受控本机端点，按服务端白名单校验目标和重定向；发送已校验 WAV，凭证由服务器侧加载 |
| 文本输出 | JSON 保留纯文本，Web 用 textContent；VTT 转义，Markdown 用固定模板并转义原文中的 HTML/Markdown 控制字符后作为附件返回；响应设置 nosniff 和 private,no-store |
| 日志 | 记录 request_id、recording_id/job_id、阶段、错误码和必要计量；认证凭证与录音/识别正文只用于业务处理 |
| 清理 | 密码、Google/ASR token 使用后释放引用；ASR 临时音频在本次处理结束后清理；raw 持续保留，旧派生文件按引用条件清理 |

卷加密保护离线存储；在线读取通过 owner 和会话鉴权。以上文件保护依据 [OWASP 文件上传](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)与[访问控制](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)，参数为本系统的存储策略。

### 7.1 一致性备份与恢复

| 项目 | 规则 |
|---|---|
| 默认备份 | 每日停服务后生成加密一致性快照，保留最近 7 个验证成功的快照；周期与份数可配置 |
| 快照内容 | 两个数据库及仍存在的 WAL、raw/身份元数据/检查点、当前 WAV/VTT、配置和恢复所需凭证；SHM 在恢复时重建 |
| 独立副本 | 备份置于独立存储介质，恢复授权与线上读写分开；备份清单记录时间、数据库版本、文件 size/hash |
| 验证 | 在临时验证副本校验数据库完整性、外键、原件数量和文件 size/hash；备份包保持只读，验证成功后才替换旧快照 |
| 恢复 | 从最近验证成功快照隔离恢复，重做来源投影和未提交发布；核对最新账号/绑定状态后开放访问，历史录音 owner 保持原值 |
| 恢复后的凭证 | 本站会话清空，上传与旧 Bearer 凭证重新核发并确认；按当前有效状态恢复账号访问，避免恢复旧快照时重新启用已撤销凭证 |

双写负责文件与索引一致，独立备份负责存储卷损坏恢复；可恢复的数据范围以最近验证成功的快照为准。
