"""Generate the SVG plates used in the recording assistant design document."""
from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parent
INK = '#17283f'
MUTED = '#607088'
LINE = '#d8e0ea'
BLUE = '#245cca'
TEAL = '#087f74'
PALE = '#f3f6fa'


class Plate:
    def __init__(self, title, subtitle, height=780):
        self.height = height
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="{height}" viewBox="0 0 1280 {height}">',
                      f'<title>{escape(title)}</title>',
                      '<rect width="1280" height="100%" fill="white"/>',
                      '<g font-family="PingFang SC,Microsoft YaHei,Noto Sans CJK SC,Arial,sans-serif">']
        self.text(40, 55, title, 30, INK, '600')
        self.text(40, 88, subtitle, 17, MUTED)
        self.line(40, 112, 1240, 112)

    def text(self, x, y, value, size=19, color=INK, weight='400'):
        values = value if isinstance(value, list) else str(value).split('\n')
        for index, line in enumerate(values):
            self.parts.append(f'<text x="{x}" y="{y + index * (size + 10)}" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(str(line))}</text>')

    def rect(self, x, y, w, h, fill='white', stroke=LINE, radius=8):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>')

    def line(self, x1, y1, x2, y2, color=LINE, width=1.5, dashed=False):
        dash = ' stroke-dasharray="5 5"' if dashed else ''
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"{dash}/>')

    def card(self, x, y, w, h, title, lines=(), accent=BLUE):
        self.rect(x, y, w, h)
        self.rect(x, y, 5, h, accent, accent, 0)
        self.text(x + 22, y + 34, title, 21, INK, '600')
        self.text(x + 22, y + 70, list(lines), 18, MUTED)

    def pill(self, x, y, text, width=120, fill='#e9f1ff', color=BLUE):
        self.rect(x, y, width, 30, fill, fill, 5)
        self.text(x + 12, y + 21, text, 15, color, '500')

    def entity(self, x, y, w, name, rows):
        h = 58 + 31 * len(rows)
        self.rect(x, y, w, h)
        self.rect(x, y, w, 48, INK, INK, 0)
        self.text(x + 18, y + 32, name, 21, 'white', '600')
        for i, row in enumerate(rows):
            yy = y + 48 + i * 31
            if i % 2 == 0:
                self.rect(x + 1, yy, w - 2, 31, PALE, PALE, 0)
            self.text(x + 16, yy + 22, row, 16)
        return h

    def save(self, stem):
        self.parts.extend(['</g>', '</svg>'])
        (ROOT / (stem + '.svg')).write_text('\n'.join(self.parts) + '\n')


# Deployment architecture: process boundary, interface tier, modules, and stores.
p = Plate('部署与模块架构', 'HTTP / DTLS 接入、进程边界、业务模块与持久存储', 850)
p.card(40, 170, 215, 180, '浏览器', ['原生 ES modules', '同源 HTTPS API', 'BLE adapter'])
p.card(40, 545, 215, 140, 'ReSpeaker Clip', ['Wi-Fi 上传', 'UDP / DTLS 9528'], TEAL)
p.rect(300, 144, 650, 645, PALE)
p.text(322, 180, 'Server 主机', 24, INK, '600')
p.rect(320, 204, 610, 312)
p.text(340, 237, 'Python / FastAPI 单进程', 21, INK, '600')
for x, title, sub in [(340, 'Web 9529', '静态资源 / 同源 API'), (535, 'HTTPS 9528', '兼容接口'), (730, 'DTLS 9528', '设备收件与确认')]:
    p.rect(x, 257, 178, 73, '#edf3ff', '#cbdaf7')
    p.text(x + 12, 286, title, 18, BLUE, '600')
    p.text(x + 12, 312, sub, 14, MUTED)
for x, title, sub in [(340, '认证与设备', 'Google / Session / 绑定'), (535, '录音与文件', '列表 / 鉴权 / Range'), (730, '后台处理', '对账 / 任务 / 转写')]:
    p.rect(x, 355, 178, 99, PALE)
    p.text(x + 12, 386, title, 19, INK, '500')
    p.text(x + 12, 419, sub, 14, MUTED)
p.rect(320, 537, 610, 62)
p.text(341, 576, '受控解码子进程     raw Opus → 16 kHz 单声道 WAV', 18)
for x, title, sub in [(320, '业务 SQLite', '用户 / 录音 / 片段 / 任务'), (528, 'registry', '凭证 / 绑定 / 来源'), (736, '文件目录', 'raw / WAV / VTT')]:
    p.rect(x, 640, 194, 110, '#eaf5f1', '#c4ded5')
    p.text(x + 14, 675, title, 20, TEAL, '600')
    p.text(x + 14, 711, sub, 14, MUTED)
p.card(1005, 205, 235, 125, 'Google', ['OAuth 2.0 / OIDC', '身份验证'])
p.card(1005, 399, 235, 125, '私有 ASR', ['WAV 识别', '时间戳 / 文字 / speaker'], TEAL)
p.line(255, 260, 300, 260, BLUE, 2)
p.line(255, 602, 278, 602, TEAL, 2);p.line(278, 602, 278, 306, TEAL, 2);p.line(278, 306, 300, 306, TEAL, 2)
p.line(950, 265, 1005, 265, BLUE, 2)
p.line(950, 461, 1005, 461, TEAL, 2)
p.text(1005, 588, ['认证临时状态保存在内存', '任务与录音保存在 SQLite', '音频文件保存在磁盘'], 18, MUTED)
p.save('01-system-architecture')

# Four-table ER layout, with relationship lines and key fields.
p = Plate('业务数据关系', '四张业务表；设备绑定和来源索引复用 registry', 910)
p.entity(40, 160, 355, 'accounts', ['PK  user_id', 'UK  google_sub', 'UK  email', 'display_name / status', 'auth_version / last_login_at', 'created_at / updated_at'])
p.entity(460, 160, 780, 'recordings', ['PK  id                      FK  owner → accounts.user_id', 'input_revision / audio_revision / transcript_revision', 'transcript_json             版本化原文', 'wav_job_id / vtt_job_id      当前文件任务指针', 'recorded_at / duration_ms / audio_state / transcript_state'])
p.entity(40, 575, 565, 'recording_segments', ['PK  id                     FK  recording_id / owner', 'UK  source_namespace + source_id', 'raw_relative_path / size_bytes / sha256', 'segment_no / state / imported_at'])
p.entity(665, 575, 575, 'jobs', ['PK  id                     FK  recording_id / owner', 'UK  recording_id + input_revision + kind', 'kind / state / attempt / lease_token / lease_until', 'publication_state / path / size_bytes / sha256'])
p.line(395, 270, 460, 270, BLUE, 2);p.text(405, 252, '1:N', 16, BLUE)
p.line(710, 373, 710, 480, BLUE, 2);p.line(710, 480, 325, 480, BLUE, 2);p.line(325, 480, 325, 575, BLUE, 2);p.text(342, 520, '一条录音，多个原始片段', 17, MUTED)
p.line(1000, 373, 1000, 575, BLUE, 2);p.text(1017, 485, '1:N  处理任务', 17, MUTED)
p.text(40, 856, '复合外键校验录音、owner 和版本；jobs.kind 区分 WAV 解码与 VTT 转写产物。', 18, MUTED)
p.save('02-user-data-model')

# Persistence ownership view for receive and projection.
p = Plate('收件与数据投影', '原件持久化与业务索引分别承担确认和读取职责', 760)
p.card(40, 160, 250, 370, '设备 / 接收器', ['设备凭证与归属校验', '已持久偏移 ACK', 'size / SHA-256 检查', 'raw 与 identity 持久化', '完整来源就绪后 COMPLETE'], TEAL)
p.entity(335, 160, 415, 'registry.sources', ['source_id / owner / binding', 'session / segment / object_id', 'size / sha256', 'state = ready', 'projected_at = NULL 或提交时间'])
p.entity(795, 160, 445, '业务库', ['recordings：来源聚合与输入版本', 'recording_segments：raw 元数据', '唯一键：namespace + source_id', 'imported_at：首次导入时间', '同一事务更新片段与录音版本'])
p.rect(335, 430, 905, 100, '#edf3ff', '#d3e0f7')
p.text(357, 465, '跨库提交规则', 20, BLUE, '600')
p.text(357, 500, '业务提交成功后填写 projected_at；重放时核对来源唯一键与 hash。', 18)
p.rect(40, 570, 1200, 124, PALE)
p.text(62, 605, '启动对账', 22, INK, '600')
p.text(62, 643, '后台按每批 500 条核对 ready 来源；片段首次 ready 时递增 input_revision。', 19)
p.text(62, 675, '设备接收确认与 WAV / ASR 任务独立运行。', 18, MUTED)
p.save('04-raw-ingest-outbox')

# Storage inventory and codec specification.
p = Plate('录音文件与存储职责', '设备原件、播放音频与识别文本的保存位置', 790)
cols = [40, 260, 580, 900]
for x, text in zip(cols, ['数据', '保存位置', '格式', '用途']):p.text(x + 16, 169, text, 20, INK, '600')
rows = [
 ('设备原件', '磁盘 raw；segments 索引', '长度前缀 + Opus packet', '归档 / 解码重试'),
 ('播放音频', '磁盘 WAV；jobs 索引', '16 kHz / mono / PCM16', '播放 / ASR / 下载'),
 ('识别原文', 'recordings.transcript_json', 'UTF-8 JSON v1', '阅读 / 复制 / 导出'),
 ('字幕文件', '磁盘 VTT；jobs 索引', 'UTF-8 WEBVTT', '字幕下载'),
 ('Markdown', '下载时生成', '日期标题 + speaker + 原文', '文字下载'),
]
for i, row in enumerate(rows):
    y = 194 + i * 70
    p.rect(40, y, 1200, 70, PALE if i % 2 == 0 else 'white', LINE, 0)
    for x, text in zip(cols, row):p.text(x + 16, y + 43, text, 17)
p.card(40, 590, 580, 139, 'raw 解包与 WAV 校验', ['uint16 little-endian 包长度；按冻结片段顺序解码', '记录样本数、时长、字节数与独立 SHA-256'])
p.card(650, 590, 590, 139, '处理容量', ['单个 raw 段上限 8 MiB；连续处理上限 8 小时', '临时分段文件在发布完成后清理'], TEAL)
p.save('05-decode-and-retain')

# State matrix makes file/database commit and failure handling visible.
p = Plate('文件发布与恢复状态', 'jobs 保存发布元数据；recordings 保存当前版本指针', 805)
xs = [40, 205, 490, 760, 1010]
heads = ['提交阶段', '磁盘文件', 'jobs', 'recordings', '恢复动作']
for x, h in zip(xs, heads):p.text(x + 12, 165, h, 19, INK, '600')
rows = [
 ('准备', ['临时路径 / 最终路径'], ['prepared', '记录 lease'], ['保留当前指针'], ['回收过期 lease']),
 ('生成', ['临时文件 fsync', '记录预期 size/hash'], ['prepared', '元数据已保存'], ['保留当前指针'], ['重做未完成产物']),
 ('文件落盘', ['rename + 目录 fsync'], ['prepared', '最终文件可校验'], ['等待事务提交'], ['WAV 校验后补提交', 'VTT 结合文字事务处理']),
 ('事务完成', ['最终 WAV / VTT'], ['succeeded / ready'], ['更新版本与指针', '转写同时写 JSON'], ['直接读取已存结果']),
]
for i, row in enumerate(rows):
    y = 194 + i * 100
    p.rect(40, y, 1200, 100, PALE if i % 2 == 0 else 'white', LINE, 0)
    for x, cell in zip(xs, row):p.text(x + 12, y + 36, cell, 16)
p.rect(40, 636, 1200, 103, '#edf5f2', '#c8dfd8')
p.text(60, 671, '转写恢复规则', 22, TEAL, '600')
p.text(60, 709, 'VTT 已落盘、JSON 未提交：重跑 ASR 后整体发布。JSON 已提交、VTT 丢失：从 JSON 重建 VTT。', 18)
p.save('06-file-database-publication')

# Version consistency across published objects and requests.
p = Plate('版本与读取约束', 'recordings 固定当前音频与文字版本；各接口在读取快照内校验', 740)
xs = [40, 360, 750]
for x, title in zip(xs, ['校验对象', '固定字段', '读取条件']): p.text(x + 16, 166, title, 21, INK, '600')
rows = [
    ('WAV', 'wav_job_id / audio_revision', 'job.kind=decode；文件 ready'),
    ('转写 JSON', 'transcript_json / transcript_revision', '文字 ready；版本等于 audio_revision'),
    ('VTT', 'vtt_job_id / transcript_revision', 'job.kind=transcribe；文件 ready'),
    ('Markdown', '当前 JSON 的全部 cues', '同一 SQLite 快照内迭代'),
    ('文字分页', 'recording_id / revision / last_cue_index', '每页最多 200；游标属于当前录音'),
]
for i, row in enumerate(rows):
    y = 195 + i * 68
    p.rect(40, y, 1200, 68, PALE if i % 2 == 0 else 'white', LINE, 0)
    for x, value in zip(xs, row): p.text(x + 16, y + 42, value, 17)
p.card(40, 574, 580, 107, '版本变化', ['返回 409 recording_revision_changed'], BLUE)
p.card(650, 574, 590, 107, 'Web 处理', ['取消旧请求与音频，重新固定版本后取齐文字'], TEAL)
p.save('07-transcript-vtt')

# BLE adapter, firmware capabilities, and server binding responsibilities.
p = Plate('设备接入与 BLE 适配', '凭证与归属由 Server 管理；网络扫描和连接由 Clip 执行', 820)
p.rect(40, 155, 600, 573, PALE)
p.text(62, 194, 'Web 设备控制器', 25, INK, '600')
p.entity(62, 219, 556, 'devices.mjs / ClipAdapter', ['连接 generation 与命令串行队列', 'readIdentity() / capabilities()', 'writeUploadConfiguration() / 读回确认', 'scanWifi() / saveWifi() / readWifiStatus()', '断开连接：取消旧命令与密码引用'])
p.card(62, 480, 556, 205, '服务端调用', ['activate(uid, evidence)：核验登记与归属', 'binding/confirm：核对配置 revision/hash', 'rename：限定本人 active binding', 'remove：撤销上传凭证与清理配置'], BLUE)
p.card(800, 155, 440, 220, 'Clip 固件 / BLE', ['完整 UID、固件版本与 capability', '写入上传参数、校时、配置读回', '扫描 SSID / rssi / security', '保存网络、建立连接、返回错误'], TEAL)
p.card(800, 442, 440, 220, 'Server / registry', ['owner / binding / epoch / credential', '设备受控登记与配置 revision', '别名、凭证撤销、cleanup_pending', '历史来源与录音归属'], BLUE)
p.line(640, 290, 800, 290, TEAL, 2);p.text(688, 272, 'BLE', 18, TEAL, '600')
p.line(640, 555, 800, 555, BLUE, 2);p.text(668, 536, 'HTTPS API', 18, BLUE, '600')
p.text(40, 780, 'SSID 取自当前连接的扫描结果；保存状态、连接状态和 Server 收件状态分别读取。', 18, MUTED)
p.save('08-wifi-configuration')

# Authentication storage and lifecycle.
p = Plate('Google 登录的数据边界', '认证协议使用 OAuth 2.0 / OIDC + S256 PKCE', 790)
p.card(40, 165, 370, 349, '浏览器', ['__Host-boa_oauth', '临时绑定 Cookie，SameSite=Lax', '__Host-boa_session', '会话 Cookie，Secure / HttpOnly', '页面内存保存 CSRF token'])
p.card(455, 165, 370, 349, 'Server 内存', ['LoginFlow：state / nonce / PKCE', '一次消费，5 分钟过期', 'Session：user_id / auth_version', '闲置 24 小时，最长 7 天', '验证 Google 签名、公钥与 audience'], TEAL)
p.card(870, 165, 370, 349, 'SQLite / registry', ['accounts：稳定 user_id 与 sub', '设备绑定与上传凭证', '录音原件与识别文字', '后台任务与来源投影', '每次请求检查用户状态和 owner'])
p.rect(40, 555, 1200, 163, PALE)
p.text(63, 592, '生命周期', 23, INK, '600')
for x, title, desc in [(63, '登录完成', '创建新的本站会话'), (460, '退出 / 到期', '清除当前会话'), (859, 'Server 重启', '网页登录重新认证')]:
    p.text(x, 636, title, 20, TEAL, '500');p.text(x, 673, desc, 19)
p.text(40, 759, '用户、设备、录音与后台任务持续保存在持久存储中。', 18, MUTED)
p.save('09-google-memory-login')

# Concrete JSON specimen plus a field definition table.
p = Plate('识别原文的存储格式', 'SQLite recordings.transcript_json；UTF-8 JSON v1', 790)
p.rect(40, 159, 685, 542, '#10233c', '#10233c')
code = ['{', '  "schema_version": 1,', '  "time_unit": "ms",', '  "cues": [', '    {', '      "cue_index": 1,', '      "start_ms": 0,', '      "end_ms": 2400,', '      "speaker": "A",', '      "text": "我们确认一下今天的安排。"', '    }', '  ]', '}']
for i, line in enumerate(code):p.text(64, 198 + i * 35, line, 18, '#e1ecfa')
p.entity(775, 159, 465, '字段约定', ['cue_index       从 1 开始的连续整数', 'start_ms        当前 WAV 的起始毫秒', 'end_ms          当前 WAV 的结束毫秒', 'speaker         A / B / C… 或 null', 'text            UTF-8 识别原文'])
p.card(775, 445, 465, 154, '存储与导出', ['录音行保存 owner 和 transcript_revision', 'API 补充录音 ID、版本和分页游标', 'VTT / Markdown 由同组 cues 生成'], TEAL)
p.text(40, 752, '整份 JSON 上限 8 MiB；API 每页最多 200 cues；静音结果保存为空数组。', 19, MUTED)
p.save('10-transcript-format')

# Milestone schedule.
p = Plate('开发任务与交付里程碑', '按 M1、M2、M3 依次交付；S01–S12 对应正文开发任务', 860)
left = 420
for i, (name, sub) in enumerate([('M1  账号与设备', 'S01–S04'), ('M2  录音与转写', 'S05–S08'), ('M3  接口集成与验收', 'S09–S12')]):
    x = left + i * 270;p.rect(x, 150, 260, 70, '#edf3ff', '#edf3ff');p.text(x + 18, 178, name, 20, BLUE, '600');p.text(x + 18, 207, sub, 17, MUTED)
items = [('S01 / S02', '四表迁移、Google 登录、会话', 0), ('S03 / S04', '绑定、Web 请求与会话管理', 0), ('S05 / S06', '来源投影、任务与文件发布', 1), ('S07', 'WAV 解码与 Range 播放', 1), ('S08', 'ASR、原文 JSON、VTT', 1), ('S09 / S10', '日期列表、详情与下载', 2), ('S11', 'BLE 能力与 Clip Wi-Fi', 2), ('S12', '集成、迁移恢复、候选包', 2)]
for i, (code, name, stage) in enumerate(items):
    y = 242 + i * 66
    p.text(40, y + 25, code, 18, BLUE, '600');p.text(177, y + 25, name, 17)
    for c in range(3):p.rect(left + c * 270, y, 260, 44, PALE, PALE, 3)
    p.rect(left + stage * 270 + 12, y + 8, 236, 28, TEAL if stage == 1 else BLUE, TEAL if stage == 1 else BLUE, 4)
p.text(40, 821, '交付依据：接口与单元验证、真实浏览器、Google / Clip / ASR 联调、备份恢复记录。', 18, MUTED)
p.save('12-implementation-order')
print('Generated 10 engineering SVG plates.')
