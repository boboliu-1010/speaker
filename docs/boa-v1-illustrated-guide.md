# 录音助手 · 图解

[设计细则](superpowers/specs/2026-10-29-boa-server-web-v1-design.md) · [开发任务](superpowers/plans/2026-10-29-boa-server-web-v1-implementation-plan.md) · [SQL](superpowers/specs/2026-10-29-boa-v1-business-schema.sql)

<a id="product"></a>

## 1. 产品

![产品范围](assets/diagrams/00-product-overview.svg)

<a id="overview"></a>

## 2. Server

![系统架构](assets/diagrams/01-system-architecture.svg)

<a id="users"></a>

## 3. 用户

![基本用户与归属](assets/diagrams/02-user-data-model.svg)

![Google 登录与内存边界](assets/diagrams/09-google-memory-login.svg)

重启后重新登录；用户与录音保留。[登录细则](superpowers/specs/2026-10-29-google-login-and-transcript-contract.md#google-login)

<a id="devices"></a>

## 4. 设备添加

![BLE、激活、校时和配置](assets/diagrams/03-device-onboarding.svg)

<a id="wifi"></a>

## 5. Wi-Fi

![Clip 扫描、用户选网、BLE 写入](assets/diagrams/08-wifi-configuration.svg)

<a id="decode"></a>

## 6. 录音处理

![原件、WAV、转写与下载](assets/diagrams/05-decode-and-retain.svg)

<a id="vtt"></a>

## 7. 文字与 VTT

![识别原文的存储格式](assets/diagrams/10-transcript-format.svg)

![cues、VTT、Markdown 同源](assets/diagrams/07-transcript-vtt.svg)

[JSON 格式](examples/transcript.json) · [查看 VTT 内容](examples/recording.vtt) · [格式与版本约束](superpowers/specs/2026-10-29-boa-server-web-v1-design.md#vtt)

<a id="implementation"></a>

## 8. 实施顺序

![S01–S12](assets/diagrams/12-implementation-order.svg)

<details>
<summary>技术图：持久收件与双写恢复</summary>

<a id="ingest"></a>

### 收件

![raw ACK 与 SQLite 投影](assets/diagrams/04-raw-ingest-outbox.svg)

<a id="publication"></a>

### 文件发布

![文件与数据库发布恢复](assets/diagrams/06-file-database-publication.svg)

</details>

图是设计，真实能力与未验收项见[原型核对](2026-10-29-prototype-review.md)。

[自我评审：已修正问题与待实测项](2026-10-29-design-self-review.md)
