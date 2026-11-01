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


# Architecture: each component states what it receives, does, and saves.
p = Plate('系统由哪些部分组成，各自负责什么', 'Clip 上传录音；Web 配置设备并查看结果；Server 校验归属、保存文件并处理录音。', 1395)
p.card(40, 150, 280, 210, '浏览器 Web', ['发起登录并查看本人录音', 'HTTPS 9529：请求业务数据', '通过 BLE 把配置写入 Clip', '按块播放音频并下载字幕'], BLUE)
p.card(347, 150, 280, 210, 'ReSpeaker Clip', ['采集声音并保存 raw 片段', '扫描附近 Wi-Fi 并连接网络', '通过 DTLS 9528 直传原件', 'COMPLETE：本次上传已完成'], TEAL)
p.card(654, 150, 280, 210, 'Google 身份服务', ['通过 OIDC 验证 Google 身份', '把授权结果回调给 Server', 'Server 随后创建本站会话'], BLUE)
p.card(961, 150, 279, 210, '受控 ASR 服务', ['每次接收一个短块及上下文', '返回识别原文和时间戳', 'speaker 表示匿名说话人', '服务地址由 Server 配置'], TEAL)
p.rect(40, 405, 1200, 650, PALE)
p.text(62, 445, 'Server · Python FastAPI 单进程', 25, INK, '600')
p.text(62, 476, '接入：HTTPS 9529 提供 Web 与业务 API；HTTPS 9528 保留兼容接口；UDP 9528 接收认证 DTLS 上传。', 17, MUTED)
p.card(60, 502, 360, 195, '认证与会话', ['验证 Google 回调并找到本站账号', 'user_id：确定当前请求用户', '检查账号状态与会话有效期', 'CSRF：校验写请求的防伪标记', '会话和登录临时状态只保存在内存'], BLUE)
p.card(460, 502, 360, 195, '设备与绑定', ['验证设备登记与用户归属', '发放设备上传配置', '记录 BLE 写入后的读回确认', '移除设备时撤销上传凭证'], BLUE)
p.card(860, 502, 360, 195, '原件接收', ['按设备凭证确定原件所属用户', '保存 raw 文件和来源身份记录', 'registry.sources 记录接收状态', '持久成功后返回 COMPLETE'], TEAL)
p.card(60, 710, 360, 185, '来源导入与录音聚合', ['把来源记录导入业务 SQLite', '按绑定与录音会话归并片段', '用来源唯一键避免重复导入', '新片段使 input_revision 增加一次'], TEAL)
p.card(460, 710, 360, 185, '录音查询与媒体读取', ['只查询当前用户拥有的录音', '核对版本后打开已发布文件', 'Range：读取指定音频字节区间', '从同版本原文生成 Markdown'], BLUE)
p.card(860, 710, 360, 185, '后台任务与恢复', ['从片段行领取单块并续租', '成功块持续保存，失败块单独重试', '汇总时间轴、原文与整条 VTT', '恢复未提交发布，不重跑成功块'], TEAL)
p.rect(60, 923, 1160, 101, 'white')
p.text(82, 958, '受控解码子进程', 21, TEAL, '600')
p.text(82, 994, '每份 raw 流式解码为短 WAV，不合成整条音频；默认 60 秒核心块，ASR 另加同原件内上下文。', 18)
p.card(40, 1095, 380, 255, '业务 SQLite · 保存录音业务数据', ['accounts：保存本站用户身份', 'recordings：汇总版本、清单、JSON/VTT', 'recording_segments：原件与行内分块结果', '共三张表，不另设 jobs 或 chunk 表'], TEAL)
p.card(450, 1095, 380, 255, '设备与上传 SQLite · registry', ['bindings：保存设备归属与凭证', 'device_uids：映射硬件 UID 与设备', 'binding_profiles：保存上传配置版本', 'sources：记录每份原件及导入进度'], TEAL)
p.card(860, 1095, 380, 255, '私有文件存储 · 保存文件内容', ['raw：保留设备上传原件', '核心 WAV：按块播放与生成 ASR 输入', 'VTT：保存可下载字幕', '通过鉴权接口读取，路径不对外公开'], TEAL)
p.save('01-system-architecture')

# Source receipt: one annotated JSON field per line, plus the import boundaries.
p = Plate('原始录音文件如何进入业务库', '设备与上传 SQLite（registry）保存来源记录；接收成功后，再导入业务 SQLite。', 1010)
p.rect(40, 150, 760, 738)
p.text(62, 189, 'registry.sources · 原始文件的接收记录', 23, INK, '600')
p.text(62, 221, '每条来源对应一个片段；下面的值仅用于说明字段。', 17, MUTED)
p.text(64, 255, '{', 18)
source_fields = [
 ('id', '"source-001"', '来源记录唯一 ID；导入后对应片段的 source_id'),
 ('owner', '"user-001"', '录音所属用户 ID；由验证通过的设备绑定确定'),
 ('binding', '"binding-001"', '设备绑定 ID；导入后对应 source_namespace'),
 ('device', '"clip-001"', '设备 ID；标识这份录音来自哪台 Clip'),
 ('session', '"session-001"', '设备录音会话 ID；与绑定及代次一起归并为一条录音'),
 ('segment', '1', '会话内原件序号；从 1 开始，确定全局时间偏移'),
 ('size', '1024', '原始文件字节数；用于接收限额与完整性校验'),
 ('sha256', '"' + 'a' * 64 + '"', '原始文件完整 SHA-256；示例值不代表真实文件'),
 ('object_id', '"object-001"', '服务端文件标识；定位原件，不接受客户端文件路径'),
 ('created', '1793318400', '首次收件时间；既有字段使用 Unix 秒，导入业务时转毫秒'),
 ('state', '"ready"', 'receiving 表示尚在接收；ready 表示原件校验并持久化成功'),
 ('projected_at', 'null', '业务导入完成时间，Unix 毫秒；null 表示尚未标记导入完成'),
]
for i, (key, value, meaning) in enumerate(source_fields):
    y = 282 + i * 46
    p.text(80, y, '// ' + meaning, 15, MUTED)
    p.text(80, y + 21, '"' + key + '": ' + value + (',' if i < len(source_fields)-1 else ''), 16, INK)
p.text(64, 857, '}', 18)
p.card(840, 150, 400, 158, '1 · 保存原始文件', ['校验上传凭证与用户归属', '原件、身份信息和来源 ready 均持久化', 'ready 表示文件收件成功'], TEAL)
p.card(840, 334, 400, 140, '2 · 向 Clip 确认接收', ['返回 COMPLETE，设备可结束本次上传', '此时可以尚未完成业务导入与转写'], BLUE)
p.card(840, 500, 400, 178, '3 · 后台导入业务库', ['binding 映射为片段 source_namespace', 'id 映射为片段 source_id', '同一事务保存录音、片段与输入版本', '重复导入同一来源不再增加版本'], TEAL)
p.card(840, 704, 400, 184, '4 · 标记业务导入完成', ['业务事务提交后填写 projected_at', 'null：尚未标记完成，可重试导入', '非空：记录最近一次完成标记的时间', '启动仍会核对文件与业务记录'], BLUE)
p.rect(40, 920, 1200, 58, PALE)
p.text(62, 955, '业务提交后标记失败：重放同一来源并核对片段，避免重复录音与版本递增。', 19)
p.save('04-raw-ingest-outbox')

# File publication: show each stored field separately from the write stages.
def annotated_fields(plate, x, y, fields, step=44):
    plate.text(x, y, '{', 18)
    for i, (key, value, meaning) in enumerate(fields):
        yy = y + 29 + i * step
        plate.text(x + 16, yy, '// ' + meaning, 15, MUTED)
        plate.text(x + 16, yy + 20, '"' + key + '": ' + value + (',' if i < len(fields)-1 else ''), 16)
    plate.text(x, y + 29 + len(fields) * step, '}', 18)

p = Plate('先保存每块结果，再发布整条录音的汇总', '没有独立 jobs 表；recording_segments 保存块结果，recordings 保存播放清单、JSON 与 VTT。', 1100)
p.card(40, 150, 585, 250, 'recording_segments · 原件与分块', ['raw：保留原件路径、大小与 hash', 'chunks_json：每块核心 WAV、文字及状态', '每块保存重试次数和下次执行时间', 'generation + 租约：防止旧执行者覆盖结果', '成功块提交后，标记录音 merge_dirty'], TEAL)
p.card(655, 150, 585, 250, 'recordings · 当前已发布汇总', ['audio_manifest_json：有序核心音频清单', 'transcript_json：全局时间戳与覆盖缺口', 'vtt_file_json：当前字幕路径、大小与 hash', 'result_revision：音频清单和文字的共同版本', 'pending_publication_json：可恢复的发布候选'], BLUE)
for x, title, lines in [
 (40, '1 · 解码核心块', ['独立流式解码一份原件', '只生成无重叠核心 WAV', '文件先 fsync，再提交块索引', '扫描完成后确认总样本数']),
 (347, '2 · 单块识别', ['原件内前后各加至多 1 秒', '每次识别一个短块', '成功原文立即入库', '失败只重试当前块']),
 (654, '3 · 汇总字幕', ['按连续原件样本数计算偏移', '缺号后的识别结果先缓存', '失败块保留真实时长与缺口', '不调用 ASR，只合并已有结果']),
 (961, '4 · 发布结果', ['记录候选与新字幕路径', '字幕落盘，校验大小和摘要', 'CAS 提交清单、JSON 与版本', '保留正在下载的旧文件']),
]: p.card(x, 440, 279 if x == 961 else 280, 240, title, lines, BLUE)
p.card(40, 720, 585, 150, '块已识别，汇总或 VTT 发布中断', ['直接复用 chunks_json 中的成功原文。', '恢复候选发布或重新合并，不重新调用 ASR。'], TEAL)
p.card(655, 720, 585, 150, '已提交 VTT 丢失，或核心 WAV 丢失', ['字幕从同版本 JSON 重建；音频从原件重建目标块。', '核验原摘要，保留文字结果与旧文件引用。'], TEAL)
p.rect(40, 910, 1200, 135, PALE)
p.text(62, 947, '时间轴与部分结果', 23, INK, '600')
p.text(62, 986, '缺少原件时不猜全局偏移；识别失败的块占时保留；partial 与 coverage 明确展示缺口。', 19)
p.text(62, 1020, '局部 speaker 不等于跨块同一人；默认播放器逐块切换，不承诺无缝播放。', 18, MUTED)
p.save('06-file-database-publication')

# Security boundaries: each component describes its concrete checks and responsibility.
p = Plate('录音文件由谁访问，Server 如何保护数据', '浏览器不能直接访问存储目录；Server 核对用户归属和版本后，才读取或处理对应文件。', 1070)
p.card(40, 150, 380, 255, '浏览器 · 发起读取请求', ['Cookie：携带本站会话身份', '录音 ID：指定要读取的录音', 'revision：固定音频清单和字幕快照', '通过 HTTPS 请求音频和文字', '退出时清理播放状态与本地会话状态'], BLUE)
p.card(450, 150, 380, 255, 'Server · 核对会话与归属', ['检查会话有效期和账号状态', 'owner：录音所属的本站用户 ID', '仅允许读取当前用户拥有的录音', '跨用户查询统一返回 404', '每次媒体请求都重新鉴权'], BLUE)
p.card(860, 150, 380, 255, 'Server · 校验文件并执行任务', ['核对请求版本和文件发布状态', '以受控路径打开普通文件句柄', '拒绝符号链接和存储根之外的路径', '解码使用受限子进程并设置超时', '发布前核对大小、摘要和有效租约'], BLUE)
p.card(40, 450, 380, 360, '私有加密数据卷 · 保存业务数据', ['raw：保留设备上传原件', '核心 WAV：保存无重叠播放块', 'VTT：保存与原文对应的字幕', 'SQLite：保存归属、版本及原文 JSON', '由专用服务账号访问存储内容', '目录权限 0700：仅服务账号可进入', '文件权限 0600：仅服务账号可读写', '文件位于 Web 静态资源目录之外'], TEAL)
p.card(450, 450, 380, 360, '受控 ASR · 处理音频并返回原文', ['服务地址由 Server 配置', '远程连接使用 HTTPS 并校验证书', '本机端点须明确登记并限制访问', '禁止重定向，出站只放行配置目标', '输入 WAV 须先校验完整摘要', '返回原文、时间戳及说话人标识', '本地临时音频在处理结束后清理', '供应方留存按已核实的约定执行'], TEAL)
p.card(860, 450, 380, 360, '独立加密备份 · 恢复存储卷', ['每日停写后复制一致性快照', '同时备份数据库、原件和当前产物', '清单记录每个文件的字节数与摘要', '校验成功后保留最近 7 份快照', '备份置于独立存储介质', '备份密钥与备份数据分开授权', '恢复时先校验清单和数据库完整性', '恢复后撤销旧凭证，重新确认访问'], TEAL)
p.rect(40, 850, 1200, 175, PALE)
p.text(62, 887, '访问、保存与恢复分别承担什么责任', 23, INK, '600')
p.text(62, 926, '访问控制：阻止其他用户读取录音。加密存储：保护离线数据卷与备份中的内容。', 19)
p.text(62, 961, '文件与数据库双写：保持产物和索引一致。独立备份：提供数据卷损坏后的恢复点。', 19)
p.text(62, 996, '日志只保留定位信息和错误码，认证凭证与录音正文不写入日志。', 18, MUTED)
p.save('07-storage-security')

print('Generated 4 design SVG plates.')
