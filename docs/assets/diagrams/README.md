# 配图维护说明

本目录保存 Boa Voice 第一版文档的 12 组配图。每组 `.mmd` 为 Mermaid 源文件，同名 `.svg` 为实际渲染的展示文件；正文引用 SVG，便于在 GitHub 和普通 Markdown 阅读器中查看。

## 图形索引

| 编号 | 图源 | 说明 |
|---|---|---|
| 01 | [系统架构](01-system-architecture.mmd) | 用户、设备、单进程服务、磁盘与私有推理端点 |
| 02 | [Google OAuth](02-google-oauth.mmd) | 发起、回调、身份校验与 Boa 会话建立 |
| 03 | [设备接入](03-device-onboarding.mmd) | 管理员登记、BLE 配置、读回、真实收件 |
| 04 | [原件与 outbox](04-raw-ingest-outbox.mmd) | 持久 ACK、来源索引、业务投影和收据 |
| 05 | [解码与双保留](05-decode-and-retain.mmd) | raw、WAV、MP3 与完整性判断 |
| 06 | [文件与数据库发布](06-file-database-publication.mmd) | staged、fsync、rename、ready、崩溃恢复 |
| 07 | [结果版本](07-result-versioning.mmd) | 媒体/全文/纪要独立发布及旧结果引用 |
| 08 | [鉴权播放](08-authorized-playback.mmd) | 会话绑定 ticket、Range、续期与撤销 |
| 09 | [删除恢复](09-delete-restore.mmd) | 权威屏障、epoch、回收站、GC 和墓碑 |
| 10 | [核心数据关系](10-core-data-model.mmd) | 业务库核心实体及输入/输出关系 |
| 11 | [迁移恢复](11-migration-and-recovery.mmd) | 停机快照、隔离迁移、恢复与安全回退 |
| 12 | [实施顺序](12-implementation-order.mmd) | T00–T23 推荐顺序及外部联调资源 |

## 更新流程

1. 修改相应 `.mmd`，与完整设计、SQL 和实施计划核对。
2. 使用 Mermaid CLI **12.0.0** 重新导出同名 SVG；渲染工具不属于产品运行依赖。
3. 使用已提交的 [mermaid.config.json](mermaid.config.json)，全局 `htmlLabels=false` 且 `flowchart.htmlLabels=false`，输出标准 SVG 文字；字体使用支持中文的本机字体。颜色统一浅绿/灰与深色文字，避免远程字体与外部图片依赖。
4. 以图片打开 SVG，检查中文、连线、分支和文字裁切；流程图布局、时序顺序与表格逐项对照。
5. 提交 `.mmd` 和 `.svg`，正文链接或说明变化时一同提交。

示例命令（在已经安装 mmdc 的文档渲染环境运行）：

```sh
mmdc -i 01-system-architecture.mmd -o 01-system-architecture.svg \
  -b white -c mermaid.config.json -p /path/to/puppeteer-config.json
```

`puppeteer-config.json` 按本机环境指定受信任 Chrome 的 executablePath。临时浏览器配置、工具安装目录和浏览器绝对路径不提交到此仓库；通用主题配置随图源一起管理。

SVG 使用白底，避免在深色页面中出现深色文字叠透明背景而不可读。

图只表示设计流程，不是运行证据。新增功能是否完成，以各任务的测试与真实联调记录为准。
