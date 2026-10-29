# 精简版配图

保留 12 组图源与同名 SVG，正文直接引用 SVG。旧票据播放、删除/回收站、纪要版本和大模型关系图随对应功能删除；历史可从 Git 查看。

| 图源 | 说明 |
|---|---|
| [00 产品范围](00-product-overview.mmd) | 两个页面和基础操作 |
| [01 系统架构](01-system-architecture.mmd) | 一个进程、最少处理链 |
| [02 用户关系](02-user-data-model.mmd) | 四表关系，用户仍为 9 字段 |
| [03 设备向导](03-device-onboarding.mmd) | 可信发放、凭证/校时、Wi-Fi |
| [04 收件](04-raw-ingest-outbox.mmd) | raw ACK 与 SQLite 投影 |
| [05 解码](05-decode-and-retain.mmd) | raw 加一份 WAV，取消 MP3/重复 WAV |
| [06 文件发布](06-file-database-publication.mmd) | fsync/rename/ready 与恢复 |
| [07 VTT](07-transcript-vtt.mmd) | 录音行 JSON、VTT、Markdown 同源 |
| [08 Wi-Fi 配置](08-wifi-configuration.mmd) | Clip 扫描、用户选网、BLE 写入 |
| [09 Google 登录](09-google-memory-login.mmd) | OIDC 与内存状态/会话边界 |
| [10 文本格式](10-transcript-format.mmd) | transcript_json 原文与 JSON / VTT / MD 同源 |
| [12 实施顺序](12-implementation-order.mmd) | S01–S12；文件编号保留以减少链接变动 |

使用 Mermaid CLI 12.0.0、[主题配置](mermaid.config.json)和本机受信任 Chrome 渲染；工具是文档构建依赖，不是产品运行依赖。

```sh
mmdc -i 07-transcript-vtt.mmd -o 07-transcript-vtt.svg \
  -b white -c mermaid.config.json -p /path/to/puppeteer-config.json
```

保持白底、中文字体与 htmlLabels=false，避免深色页面透明底文字不可读。更新图源后重新渲染、目视检查，并同步设计/任务；不提交临时浏览器配置或其本机路径。
