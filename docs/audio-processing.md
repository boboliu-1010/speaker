# 音频、转写与 VTT 开发设计

v1 · 2026-10-29 · [Server / Web 主文档](../README.md)

## 关键点

1. 保存设备 raw 原件和一份当前 WAV，WAV 同时用于播放、识别和下载。
2. 识别原文保存为 recordings.transcript_json；VTT 和 Markdown 使用同组 cues。
3. jobs 一行保存后台处理、文件元数据与发布状态；recording_segments 兼作来源幂等收据。
4. 当前音频、文字、分页和下载固定相同 revision；输入变化后重新生成结果。
5. 原件持久确认与解码/ASR 独立，失败和重启保留原件并从已提交状态恢复。

[收件](#ingest) · [字段](#tables) · [解码](#decode) · [转写格式](#transcript) · [发布恢复](#publication) · [接口](#media-api)

<a id="ingest"></a>

## 1. 原件收件与录音聚合

![收件与投影](assets/diagrams/04-raw-ingest-outbox.svg)

| 数据 / 操作 | 规则 |
|---|---|
| 原件格式 | uint16 little-endian 包长度 + Opus payload；校验包边界、size/hash 与媒体 profile |
| 持久确认 | data fsync、持久检查点、完整 hash、rename/目录 fsync；raw 与归属元数据持久后返回 COMPLETE |
| 来源归属 | 从有效设备 binding 或已验证 App 来源取得 owner；旧来源 owner 保持原值 |
| 聚合键 | source_kind + source_namespace + binding_epoch + source_session |
| 输入版本 | 原始片段首次 ready 导入时 input_revision 加 1；重复来源保持版本 |
| 处理触发 | 片段从 1 开始连续且静默 10 分钟后处理当前已收内容；缺号时等待补齐 |
| 完整性 | 现有协议缺少整段闭合信息时保持 unknown；确认完整须有协议证据 |

业务投影使用一个短事务：按 namespace/source_id 查询片段；已有 ready 且 hash/size 相同则幂等返回，冲突报 source_identity_conflict；首次 ready 同时保存原件元数据、imported_at 并增加录音版本。business 提交后再更新 registry.sources.projected_at。

启动按每批 500 条核对全部 ready 来源，检查 raw 存在和 size/hash；来源时间 created 从既有秒值转为 UTC 毫秒。receiving 保存上传状态，校验完成后创建处理输入。

<a id="tables"></a>

## 2. 处理对象与数据表

| 对象 | 关键数据 | 作用 |
|---|---|---|
| SourceEvent | owner、来源类型/命名空间/ID、绑定代次、session、segment、raw 路径、size/hash、收件时间 | 导入经过验证的来源 |
| InputSnapshot | recording_id、owner、revision、有序来源清单与 hash | 固定本次处理输入 |
| Lease | job_id、recording_id、revision、lease_token、lease_until | 校验当前执行与发布资格 |
| Cue | cue_index、start_ms、end_ms、speaker、text | 保存原文和生成导出 |

完整 DDL 见[主文档](../README.md#business-sql)。下面说明录音处理使用的三张表；时间为 UTC Unix 毫秒，时长为毫秒，size 为字节数。

### 2.1 recordings

| 字段 | 类型 | 约束 / 默认 | 含义 |
|---|---|---|---|
| id | TEXT | 主键 | 录音 ID。 |
| owner | TEXT | 必填；外键 | 所属用户 ID，引用 accounts.user_id。 |
| source_kind | TEXT | 必填 | 来源类型：clip_direct / app_upload。 |
| source_namespace | TEXT | 必填 | 来源所在的存储命名空间。 |
| binding_epoch | INTEGER | 必填；≥0；Clip >0 | Clip 绑定代次；App 来源为 0。 |
| source_session | TEXT | 必填 | 来源的录音 session；与来源/绑定代次一起确定一条录音。 |
| recorded_at | INTEGER | 可空 | 录音时间，可空；时间不可信时按 received_at 查询。 |
| time_source | TEXT | 必填 | device_unverified / server_received / client_confirmed。 |
| received_at | INTEGER | 必填 | 首次收件时间。 |
| last_received_at | INTEGER | 必填 | 最近片段收件时间。 |
| integrity | TEXT | 必填；默认 'unknown' | unknown / gap / confirmed_complete；依协议证据更新。 |
| input_revision | INTEGER | 必填；默认 0；≥0 | 已接收输入版本；新 ready 片段首次导入时加 1。 |
| audio_revision | INTEGER | >0 且 ≤ input_revision | 当前 WAV 对应的输入版本，可空。 |
| transcript_revision | INTEGER | >0 且 ≤ input_revision | 当前转写对应的输入版本，可空；ready 时等于 audio_revision。 |
| audio_state | TEXT | 必填；默认 'pending' | pending / running / ready / failed。 |
| transcript_state | TEXT | 必填；默认 'pending' | not_configured / pending / running / ready / failed。 |
| wav_job_id | TEXT | 录音/owner/版本复合外键 | 当前 WAV 的 decode 任务，可空。 |
| vtt_job_id | TEXT | 录音/owner/版本复合外键 | 当前 VTT 的 transcribe 任务，可空。 |
| duration_ms | INTEGER | ≥0 | 当前 WAV 时长，毫秒，可空。 |
| transcript_json | TEXT | 合法 JSON v1；≤8 MiB | UTF-8 JSON v1：schema_version、time_unit、cues；上限 8 MiB，可空。 |
| updated_at | INTEGER | 必填 | 录音状态或结果更新时间。 |

### 2.2 recording_segments

| 字段 | 类型 | 约束 / 默认 | 含义 |
|---|---|---|---|
| id | TEXT | 主键 | 原始片段 ID。 |
| owner | TEXT | 必填；与录音组成复合外键 | 所属用户；与 recording_id 对应的录音一致。 |
| recording_id | TEXT | 必填；与 owner 组成复合外键 | 所属录音 ID。 |
| source_namespace | TEXT | 必填 | 来源命名空间。 |
| source_id | TEXT | 必填；与 source_namespace 组合唯一 | 来源索引 ID；与 namespace 组成幂等键。 |
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
| id | TEXT | 主键 | 任务 ID；一个任务对应一个 WAV 或 VTT 文件。 |
| owner | TEXT | 必填；与录音组成复合外键 | 任务所属用户，与录音 owner 相同。 |
| recording_id | TEXT | 必填；与 owner 组成复合外键 | 任务处理的录音 ID。 |
| input_revision | INTEGER | 必填；>0 | 任务对应的输入版本。 |
| kind | TEXT | 必填；与录音/版本组合唯一 | decode / transcribe。 |
| state | TEXT | 必填 | pending / running / retry_wait / succeeded / failed。 |
| attempt | INTEGER | 必填；默认 0；0–4 | 已执行次数；0–4，包含首次执行与 3 次重试。 |
| run_after | INTEGER | 必填 | 允许领取的最早时间。 |
| lease_token | TEXT | 可空 | 当前执行的随机标识，可空；running 时填写。 |
| lease_until | INTEGER | 可空 | 当前执行的到期时间，可空；running 时填写。 |
| input_json | TEXT | 必填；合法 JSON | 固定的原件清单、hash、配置版本；转写任务还固定 WAV 任务与 hash。 |
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
| 当前文件指针 | wav_job_id/vtt_job_id 指向相同录音、owner、版本的 jobs |
| registry.sources | 保存原件身份和 ready/projected_at，业务投影后再更新标记 |

<a id="decode"></a>

## 3. raw 解码与文件保存

| 产物 | 保存位置 | 用途 |
|---|---|---|
| raw | 原件文件，recording_segments 保存路径/size/hash | 原始归档、解码重试 |
| WAV | 文件，decode jobs 保存元数据 | 播放、ASR、下载 |
| 转写 JSON | recordings.transcript_json | 原文、时间和 speaker 的主源 |
| VTT | 文件，transcribe jobs 保存元数据 | 字幕下载 |
| Markdown | 请求时从同版本 JSON 生成 | 文字下载 |

解码前固定来源清单，逐包校验后按 segment_no 顺序临时解码，再合成一份 WAV。输出为 **16 kHz、mono、PCM16 little-endian**，按 sample_count/16000 计算时长并核对 WAV 数据长度。Ogg granule 使用 48 kHz 时基；raw 缺少 pre-skip 元数据时沿用当前样本策略并记录时间来源。

单 raw 段上限 8 MiB，连续处理默认上限 8 小时，PCM16 约 115.2 MB/小时。解码前检查磁盘预算，完成后记录样本数、size 和独立 SHA-256；临时分段文件在发布成功后清理。固定 decoder/raw profile/ASR 配置版本，变更处理配置时使用新输入修订。

文件按服务端 ID 生成独立路径；读取先校验 owner 和当前版本。旧派生文件在任务和读取释放引用后清理，raw 持续保存。错误使用 packet_invalid、segment_gap、decode_timeout、disk_full 等固定 code。

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

VTT 使用 UTF-8、WEBVTT 头、毫秒时间戳、稳定编号和可选 voice 标签；输出时转义 `& < >`，规范化会切断 cue 的空白行。SQLite text 保留原文，Web 用 textContent 渲染。Markdown 为日期标题、speaker 和原文。格式依据：[W3C WebVTT](https://www.w3.org/TR/webvtt1/)。

<a id="publication"></a>

## 5. 后台处理、发布与恢复

![发布状态](assets/diagrams/06-file-database-publication.svg)

| 处理规则 | 值 |
|---|---|
| kind | decode 产生 WAV；transcribe 产生 VTT 并提交原文 JSON |
| 去重键 | recording_id + input_revision + kind |
| 执行 | 顺序领取一个任务，固定该任务 owner 与输入版本 |
| 租约 | 60 秒；15 秒续期；提交检查 token、有效期和输入版本 |
| 重试 | 最多 4 次执行，重试间隔 30 秒 / 2 分钟 / 10 分钟 |
| 超时 | decode 默认 10 分钟；ASR 默认 60 分钟 |

领取和续期使用短事务，已过期执行的结果放弃发布；新输入使待执行旧版本标为 input_superseded。恢复时仅核验已落盘结果并补提交可换租约、保留 attempt；真正重做时增加 attempt。

| 发布阶段 | jobs / 文件 / 录音 |
|---|---|
| 准备 | jobs 保存输入快照、临时/最终路径、lease 与 prepared |
| 生成 | 临时文件校验、fsync；保存预期 size/hash |
| 文件落盘 | 同文件系统按本次 attempt 唯一路径 rename，目录 fsync |
| 短事务提交 | 核对 owner、版本和 lease；jobs ready/succeeded 与录音指针一起提交 |
| WAV 提交 | 更新 wav_job_id、audio_revision、duration_ms；新音频发布时将旧版本文字置 pending |
| 转写提交 | 同事务写 transcript_json、vtt_job_id、transcript_revision、文字 ready 与 jobs 成功 |

| 中断 / 错误 | 恢复规则 |
|---|---|
| raw 已持久、索引未提交 | 由原件/checkpoint/来源对账恢复 |
| 业务已提交、projected_at 未更新 | 幂等重放，版本保持一次递增 |
| WAV rename 后、DB 提交前 | 校验 hash、当前版本和租约后补提交 |
| VTT 已落盘、JSON 尚未提交 | 重跑 ASR，重新整体发布 |
| JSON 已提交、VTT 丢失 | 保留原文，从同版本 JSON 重建 VTT |
| WAV 缺失 | 标 missing，从 raw 重建 |
| lease 到期、输入版本改变或配置不匹配 | 停止旧结果发布；错误记录固定 code |

<a id="media-api"></a>

## 6. 音频与文字 API

路径前缀 `/api/boa/v1`，携带本站会话，owner 取自会话。错误 body 使用 `{error:{code,message},request_id}`。

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
| 503 audio_unavailable | 已发布音频文件缺失或不可用 |
| 416 | GET 字节范围无效 |

### 6.1 版本与分页

详情先固定 audio_revision。音频、JSON、VTT、Markdown 请求都携带 revision；文字还须匹配 transcript_revision 和 ready 状态。游标绑定 recording_id、revision、last_cue_index。每个请求在同一 SQLite 快照核对 owner 和版本后读取。

JSON 使用 json_each 按 cue 数组下标读取 201 条：返回前 200 条，第 201 条决定 next_cursor。Markdown 迭代同一快照的全部 cues。复制取齐同版本全部页后再写剪贴板；新版本或 409 时，Web 取消旧分页和音频，重新固定版本。

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

每次 GET/HEAD 都重新鉴权；文件使用不可变路径，响应标注 revision，ETag 取 SHA-256，Cache-Control 为 private, no-store。导出文件名由 Server 生成。Range/HEAD 依据 [RFC 9110 §14.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-14.2)。
