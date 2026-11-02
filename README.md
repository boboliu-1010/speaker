# ReSpeaker Clip · 架构与模块设计

## 1. 整体架构

![整体架构](docs/assets/diagrams/01-system-overview.svg)

单机运行两个服务，通过本机文件交接授权和成品。浏览器通过HTTP访问Web Server，通过蓝牙直接配置Clip设备。

| 服务 | 职责 | 数据 |
| --- | --- | --- |
| Clip Server | 接收Opus，内置ASR，生成完整WAV/VTT/MD | 录音及job用文件，不连接数据库 |
| Web Server | 登录、设备管理、成品播放与下载 | 管理accounts/devices及授权文件，读取成品 |

两个服务独立运行；Nginx、进程托管和整体备份由OP管理。SQLite表结构见[数据库文档](docs/sqlite-schema.md)。

## 2. Clip Server 模块

### 2.1 启动与生命周期

读取配置、取得Clip单实例锁、恢复未完成任务，然后启动DTLS和后台处理循环。退出先停止收件及新任务，保存进度，等待执行结束。

### 2.2 DTLS与协议

![设备接入模块调用关系](docs/assets/diagrams/09a-clip-ingest.svg)

监听DTLS/UDP 9528，解析认证、上传、续传及录完消息；接入循环不等待ASR。

### 2.3 身份与凭证验证

读取Web发布的`SPEAKER_DATA_ROOT/device-authorizations/<device_id>.json`，验证设备凭证、owner、binding_id和epoch。握手、续传及最终接受均复核；缺失、损坏或撤销一律拒绝。

Web串行执行设备授权变更：先写deny，再更新devices，最后发布匹配的active；解绑保持deny。中断后默认拒绝，不能自动恢复未完成授权。已接受录音保留原owner。

### 2.4 原件收件与续传

文件完整且size/hash校验通过后，持久化原件及收件记录，再返回回执。上传偏移用于续传；相同录音、段号及hash重传时复用原件，不同内容报冲突。Server只记录收件和处理进度。

单片最多300秒、8MiB，整条最多12小时；默认每用户10GiB，跨其所有Clip计算。收件预留原件、分段WAV及完整WAV空间，空间不足暂停。

### 2.5 录音聚合与结束判定

按录音ID和段号聚合，最终段号N写入收件记录；1..N收齐且处理成功才可合并，缺片不跳号、不补静音。

**固件需支持受认证的session_end及最终段号N。** 现有v3文件完成消息不能表示录完；缺少结束信息时只预处理，不发布。

### 2.6 文件仓储

服务端只配置一个存储根`SPEAKER_DATA_ROOT`，音频和处理状态放在同一用户、Clip目录下。路径由ID推导，不维护地址映射表：

```text
${SPEAKER_DATA_ROOT}/
├── db/business.sqlite3                         # Web专用
├── device-authorizations/<device_id>.json       # Web写，Clip读
├── credentials/trust/                          # Web验证设备证书的信任根
├── credentials/devices/                        # 私有上传凭证材料
├── locks/                                     # 两个角色锁及state.lock
└── users/<owner>/clips/<device_id>/
    ├── incoming/<recording_id>/<upload_id>/
    │   ├── audio.part
    │   └── progress.json
    ├── raw/<recording_id>/<segment_no>.opus
    ├── segments/<recording_id>/<segment_no>.wav
    ├── processing/<recording_id>/              # 服务端处理进度
    │   ├── state.json
    │   ├── transcripts/<segment_no>.json
    │   └── jobs/<job_id>.json
    └── recordings/<recording_id>/              # 正式成品，Web只读
        ├── recording.wav
        ├── transcript.vtt
        ├── transcript.md
        └── recording.json
```

owner来自授权或登录会话，客户端不能指定；不同用户、Clip分别隔离，换绑不改变旧录音归属。JSON提交使用固定文件锁及同目录原子替换。

recording.json只含录音ID、归属、开始时间（UTC毫秒）和完整时长（毫秒）；缺少设备时间时用首段接收时间：

```json
{
  "recording_id": "rec-demo-20261102-001",
  "owner": "demo-user",
  "recorded_at": 1793584800000,
  "duration_ms": 642000
}
```

### 2.7 音频处理与成品

![音频任务启动、处理中状态与终止时序](docs/assets/diagrams/09b-clip-processing.svg)

- **转码**：将已收完整的Opus片段逐包解码为16kHz、单声道PCM16 WAV，保留实际样本数。原件是长度前缀Opus包序列，不是Ogg。
- **ASR**：内置Paraformer-zh + FSMN-VAD + CT-Punc + CAM++候选组合，离线处理中文为主、少量英语。按句末标点断句，每行一句，保留时间戳和匿名说话人A/B/C；标签仅在片段内有效，跨段标作“片段1·A”等。效果需真实录音验收。
- **合并与发布**：满足第2.5节条件后，按段号拼接PCM并重写WAV头；字幕按实际样本数累加偏移，生成完整VTT和MD。在隐藏临时目录写齐四文件，校验、fsync后原子发布整个录音目录。

VTT示例（仅展示格式）：

```vtt
WEBVTT

1
00:00:00.800 --> 00:00:04.200
<v s001_A>我们先确认今天的录音流程。</v>

2
00:05:00.300 --> 00:05:03.500
<v s002_A>Next, we review the results.</v>
```

MD每句一行，例如：`[00:05:00.300] 片段2·A：Next, we review the results.`。

## 3. Web Server 模块

![Web模块调用关系](docs/assets/diagrams/10-web-components.svg)

### 3.1 登录与用户

Google OIDC登录后建立或复用accounts用户，校验回调及账号状态，创建内存会话。退出或Web重启后重新登录。

### 3.2 设备管理

用户登录并通过蓝牙连接Clip，Web校验设备持有证明后自动创建devices及device_id，无需OP登记。未绑定设备可认领，已绑定本人则复用；已绑定他人返回409 device_already_bound，不允许覆盖。

转交时原用户先解绑，Web撤销授权并清空owner；蓝牙清理完成后，新用户重新绑定，复用device_id但生成新binding_id、递增epoch和revision。历史录音仍归原用户。

维护devices并按第2.3节发布授权，配置流程见第4.3节。凭证只在配置响应中返回，不进入列表、日志或前端持久缓存。

### 3.3 成品读取

只查询本人正式录音目录，忽略临时目录；按ID读取录音信息、播放WAV、加载VTT和下载MD。每次读取鉴权，WAV支持Range，不触发处理任务。无权限或不存在返回404，损坏成品返回503并告警；数据根不静态暴露。

## 4. 接口

### 4.1 Web Server HTTP接口

统一前缀`/api/boa/v1`。除登录入口、回调和health，其余验证会话；写请求还验证Origin和`X-CSRF-Token`。错误为`{code,message,request_id}`，私有响应不缓存。

| 方法与路径 | 输入 / 返回 |
| --- | --- |
| GET /auth/google/start | 跳转Google登录 |
| GET /auth/google/callback | 校验回调，创建会话并返回页面 |
| GET /auth/session | 当前用户及csrf_token |
| DELETE /auth/session | 退出登录，204 |
| GET /users/me | user_id、email、display_name |
| PATCH /users/me | 仅修改display_name |
| GET /devices | 本人设备列表，不含凭证 |
| POST /devices/binding/challenge | 输入device_uid；返回当前会话的一次性挑战 |
| POST /devices/activate | 输入device_uid、challenge_id、proof；验证后自动建档或复用，返回configuration |
| POST /devices/{id}/binding/confirm | 输入device_uid、binding_id、revision、saved=true；核对后确认配置 |
| PATCH /devices/{id} | 仅修改display_name |
| DELETE /devices/{id}/binding | 原用户撤销并清空owner；返回revoked、device_cleanup_pending及旧binding_id/revision供蓝牙清理 |
| GET /recordings | 返回录音ID列表；支持device_id、from/to、limit、cursor |
| GET /health | Web自身及成品目录可读状态，不返回秘密 |

POST `/devices/binding/challenge` 返回示例：

```json
{
  "challenge_id": "challenge-demo",
  "nonce": "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
  "expires_in": 300
}
```

nonce为随机32字节的十六进制；挑战保存在Web内存，绑定当前登录会话及UID，5分钟有效、成功激活后一次消费，重启后重新申请。`proof`取AT+BINDPROOF返回的data；Web验证证书、签名及nonce，proof的UID须与挑战一致；在串行事务内核对当前归属再建档，不能只凭UID认领。无效证明返回403 device_proof_invalid；首次认领或解绑后重绑时proof仍为bound=true，返回409 device_cleanup_required，清理后用新挑战重试。

激活时的configuration示例（凭证为占位值）：

```json
{
  "device_id": "demo-device",
  "device_uid": "0011223344556677",
  "owner_id": "demo-user",
  "binding_id": "00112233445566778899aabbccddeeff",
  "epoch": 1,
  "revision": 1,
  "endpoint": "upload.example.com:9528",
  "device_token": "0123456789abcdef0123456789abcdef"
}
```

录音列表只返回ID和游标：

```json
{
  "items": [{"device_id":"demo-device","recording_id":"rec-demo-20261102-001"}],
  "next_cursor": null
}
```

前端用ID拼固定路由，四个文件都支持GET/HEAD：

```text
/api/boa/v1/recordings/<device_id>/<recording_id>/recording.json
/api/boa/v1/recordings/<device_id>/<recording_id>/recording.wav
/api/boa/v1/recordings/<device_id>/<recording_id>/transcript.vtt
/api/boa/v1/recordings/<device_id>/<recording_id>/transcript.md
```

文件定位与隔离规则见第2.6节，API不返回磁盘地址或下载URL。from/to为UTC毫秒，limit默认50、最大200；按录音时间及ID倒序分页，游标不携带授权。

### 4.2 Clip设备蓝牙接口

浏览器通过Web Bluetooth直接连接Clip，使用GATT传递AT命令，与HTTP接口独立。

| GATT | UUID |
| --- | --- |
| 服务 | 6e400001-b5a3-f393-e0a9-e50e24dcca9e |
| RX：写命令 | 6e400002-b5a3-f393-e0a9-e50e24dcca9e |
| TX：接收通知 | 6e400003-b5a3-f393-e0a9-e50e24dcca9e |

先订阅TX再写RX，命令串行、UTF-8最多255字节；通知分片拼成JSON，超时重连读回，异步事件单独处理。

以下返回示例仅列主要字段。

#### AT+IDENTITY? — 读取设备身份

```json
{
  "ok": true,
  "data": {
    "device_uid": "0011223344556677",
    "binding_protocol_version": 1,
    "binding_proof_version": 1
  }
}
```

#### AT+BINDPROOF — 证明持有设备

`AT+BINDPROOF=nonce`，经本地配对的BLE调用，返回设备签名的当前绑定快照：

```json
{
  "ok": true,
  "data": {
    "device_uid": "0011223344556677",
    "nonce": "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
    "bound": false,
    "binding_id": null,
    "epoch": 0,
    "revision": 0,
    "signature": "base64url-signature",
    "certificate_chain": ["base64-der-device-certificate", "base64-der-issuer-certificate"]
  }
}
```

签名覆盖紧凑UTF-8 JSON数组`["speaker-bind-v1",device_uid,nonce,bound,binding_id,epoch,revision]`。设备证书须绑定UID且链至Web信任根；每台设备使用独立私钥且仅保存在设备；签名和证书为示例占位值。首次绑定或转交要求bound=false；本人重复配置可返回当前绑定快照。

#### AT+BINDING? — 读取绑定

```json
{
  "ok": true,
  "data": {
    "device_uid": "0011223344556677",
    "bound": true,
    "saved": true,
    "binding_id": "00112233445566778899aabbccddeeff",
    "epoch": 1,
    "revision": 1
  }
}
```

#### AT+BINDCFG — 保存绑定

`AT+BINDCFG=host,port,device_id,token,binding_id,epoch,revision`

```json
{
  "ok": true,
  "data": {
    "device_uid": "0011223344556677",
    "bound": true,
    "saved": true,
    "binding_id": "00112233445566778899aabbccddeeff",
    "epoch": 1,
    "revision": 1
  }
}
```

#### AT+BINDCLR — 清理绑定

`AT+BINDCLR=binding_id,revision`

```json
{
  "ok": true,
  "data": {
    "bound": false,
    "saved": true,
    "cleared_binding_id": "00112233445566778899aabbccddeeff"
  }
}
```

#### AT+NETCFG — 保存Wi-Fi

`AT+NETCFG=ssid,password`

```json
{
  "ok": true,
  "data": {
    "configured": true,
    "saved": true,
    "networks": [
      {
        "slot": 1,
        "ssid_hex": "44656d6f"
      }
    ]
  }
}
```

#### AT+NETCFG? — 读取Wi-Fi配置

```json
{
  "ok": true,
  "data": {
    "configured": true,
    "saved": true,
    "networks": [
      {
        "slot": 1,
        "ssid_hex": "44656d6f"
      }
    ]
  }
}
```

#### AT+NETSCAN — 扫描Wi-Fi

```json
{
  "ok": true,
  "data": {
    "accepted": true,
    "job": 1,
    "state": "scanning"
  }
}
```

#### AT+NETCHECK — 启动联网检查

```json
{
  "ok": true,
  "data": {
    "accepted": true,
    "job": 2,
    "state": "checking",
    "scope": "wifi_dhcp"
  }
}
```

#### AT+NETCHECK? — 查询联网检查

```json
{
  "ok": true,
  "data": {
    "job": 2,
    "state": "succeeded",
    "scope": "wifi_dhcp",
    "ip": "192.168.1.20",
    "error": 0
  }
}
```

#### 不支持的命令

```json
{
  "ok": false,
  "msg": "Unknown command"
}
```

#### Wi-Fi扫描结果事件

异步返回，job对应AT+NETSCAN请求：

```json
{
  "event": "wifi_scan",
  "job": 1,
  "state": "succeeded",
  "error": 0,
  "cleanup_error": 0,
  "truncated": false,
  "networks": [{"ssid_hex":"44656d6f","rssi":-55}]
}
```

ssid_hex为SSID的UTF-8字节十六进制，示例为Demo；Wi-Fi配置saved不代表已联网，NETCHECK成功也不代表上传端点一定可达。

**绑定及持有证明均为目标固件能力。** 启用前需支持`binding_protocol_version=1`、`binding_proof_version=1`及设备证书签名；基础固件未具备这些能力时提示升级，不降级为仅凭UID绑定。设备身份凭证预置于设备，Web信任根随部署制品提供，无需OP逐台登记用户归属。

Wi-Fi密码仅通过蓝牙写入，不发送Web。

### 4.3 设备配置配合流程

![HTTP与蓝牙配置流程](docs/assets/diagrams/11-device-configuration.svg)

浏览器先读设备UID及能力，再执行下图。操作前确保设备空闲；读回UID、binding_id、epoch、revision及saved与configuration匹配后确认，失败保持provisioning。有效绑定的本人重试复用配置；解绑后重新认领才更换绑定及代次。
