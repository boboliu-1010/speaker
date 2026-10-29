# 精简版配图

保留 8 组图源与同名 SVG，正文直接引用 SVG。旧票据播放、删除/回收站、纪要版本和大模型关系图随对应功能删除；历史可从 Git 查看。

| 图源 | 说明 |
|---|---|
| [01 系统架构](01-system-architecture.mmd) | 一个进程、最少处理链 |
| [02 用户关系](02-user-data-model.mmd) | 9 字段基本用户与录音/会话 |
| [03 设备向导](03-device-onboarding.mmd) | 可信发放、凭证/校时、Wi-Fi |
| [04 收件](04-raw-ingest-outbox.mmd) | raw ACK 与 SQLite 投影 |
| [05 解码](05-decode-and-retain.mmd) | raw 加一份 WAV，取消 MP3/重复 WAV |
| [06 文件发布](06-file-database-publication.mmd) | fsync/rename/ready 与恢复 |
| [07 VTT](07-transcript-vtt.mmd) | cues、VTT、Markdown 同源 |
| [12 实施顺序](12-implementation-order.mmd) | S01–S12；文件编号保留以减少链接变动 |

使用 Mermaid CLI 12.0.0、[主题配置](mermaid.config.json)和本机受信任 Chrome 渲染；工具是文档构建依赖，不是产品运行依赖。

```sh
mmdc -i 07-transcript-vtt.mmd -o 07-transcript-vtt.svg \
  -b white -c mermaid.config.json -p /path/to/puppeteer-config.json
```

保持白底、中文字体与 htmlLabels=false，避免深色页面透明底文字不可读。更新图源后重新渲染、目视检查，并同步设计/任务；不提交临时浏览器配置或其本机路径。
