# Boa Voice — Server & Web

ReSpeaker Clip 配套 Server + Web 第一版的设计与实施文档。

当前阶段：设计与任务规划。产品代码尚未在此仓库实现，参考 SQL 尚未应用到真实数据。

建议先读 [架构图解与关键步骤](docs/boa-v1-illustrated-guide.md)，再查完整设计和开发任务。图解按“目的 → 配图 → 操作步骤 → 成功判据 → 失败恢复”组织，覆盖 12 条主要视图与流程。

![Boa Voice Server 与 Web 架构总览](docs/assets/diagrams/01-system-architecture.svg)

## 文档导航

| 文档 | 内容 |
|---|---|
| [架构图解与关键步骤](docs/boa-v1-illustrated-guide.md) | 12 张 SVG 配图，逐步解释登录、绑定、收件、解码、双写恢复、播放、删除、数据模型、迁移和实施顺序 |
| [完整设计](docs/superpowers/specs/2026-10-29-boa-server-web-v1-design.md) | 产品范围、Server/Web 架构、Google OAuth、录音解码转存与双写恢复、API、SQLite 模型、部署迁移和验收 |
| [业务库参考 SQL](docs/superpowers/specs/2026-10-29-boa-v1-business-schema.sql) | 账户、OAuth、会话、录音、处理任务、文件发布、全文、纪要、审计和检索 |
| [registry 扩展参考 SQL](docs/superpowers/specs/2026-10-29-boa-v1-registry-additions.sql) | 来源 outbox、Clip/App 删除屏障和删除事件 |
| [实施计划](docs/superpowers/plans/2026-10-29-boa-server-web-v1-implementation-plan.md) | T00–T23 共 24 项开发任务、依赖、接口、验证步骤和里程碑 |

## 第一版路线

- 沿用 Python 单进程、SQLite 和静态 Web，复用现有 DTLS v3 接收与 BLE/OTA 能力。
- Google OAuth/OIDC 与受邀账户，原始录音和解码 WAV 双保留，MP3 用于网页播放。
- 优先跑通上传、入库、解码双写、播放、删除与恢复；随后接入私有 ASR、纪要、搜索和导出。

现有实现基线来自 [`BofAI/reSpeaker_Clip`](https://github.com/BofAI/reSpeaker_Clip)，设计读取的提交为 `77ae7fc`。实施前需核对该源码仓库的当前状态和分支约定。

## 文档维护

此仓库为设计和计划的版本管理入口；修改设计时同步核对 SQL 附件与实施计划。SQL 文件是结构参考，真正迁移需要在实现仓库编写版本化迁移并验证旧数据兼容。

图形以 Mermaid `.mmd` 维护可编辑源文件，同时提交 SVG，直接在文档中展示；更新流程时同步更新图源与导出图。渲染方式见 [配图维护说明](docs/assets/diagrams/README.md)。

提交仅包含文档与参考 SQL。真实录音、数据库、OAuth 凭证、设备令牌、签名材料和邀请链接保存在仓库之外。
