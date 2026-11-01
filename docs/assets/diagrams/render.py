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
p = Plate('系统架构', '原件就绪后导入业务库，由 Server 完成解码、识别、播放和导出。', 1395)
p.card(40, 150, 280, 210, '浏览器 Web', ['发起登录并查看本人录音', 'HTTPS 9529：请求业务数据', '通过 BLE 把配置写入 Clip', '按片段播放音频并下载字幕'], BLUE)
p.card(347, 150, 280, 210, '已就绪原件来源', ['由接入组件提供', 'raw 文件已经可靠保存', '来源包含归属、会话与段号', '提供可信来源元数据'], TEAL)
p.card(654, 150, 280, 210, 'Google 身份服务', ['通过 OIDC 验证 Google 身份', '把授权结果回调给 Server', 'Server 随后创建本站会话'], BLUE)
p.card(961, 150, 279, 210, '受控 ASR 服务', ['每次识别一份片段 WAV', '返回识别原文和时间戳', 'speaker 表示匿名说话人', '服务地址由 Server 配置'], TEAL)
p.rect(40, 405, 1200, 650, PALE)
p.text(62, 445, 'Server · Python FastAPI 单进程', 25, INK, '600')
p.text(62, 476, 'HTTP：用户、会话、设备、录音、播放与导出；原件导入读取 ready 来源。', 17, MUTED)
p.card(60, 502, 360, 195, '用户与会话', ['Google 登录并建立本站会话', 'users/me：读取本人资料', '仅允许修改本人的显示名称', 'CSRF：校验写请求的防伪标记', '会话和登录临时状态只保存在内存'], BLUE)
p.card(460, 502, 360, 195, '设备与绑定', ['验证设备登记与用户归属', '发放设备上传配置', '记录 BLE 写入后的读回确认', '移除设备时撤销上传凭证'], BLUE)
p.card(860, 502, 360, 195, '已就绪原件校验', ['读取 registry.sources 的 ready 来源', 'owner 与身份来自可信来源记录', '校验原件存在、实际大小与 hash', '检查处理限额，异常来源暂不导入'], TEAL)
p.card(60, 710, 360, 185, '原件导入与录音聚合', ['把来源记录导入业务 SQLite', '按绑定与录音会话归并片段', '用来源唯一键避免重复导入', '可见内容变化递增 content_revision'], TEAL)
p.card(460, 710, 360, 185, '录音查询与媒体读取', ['只查询当前用户拥有的录音', '核对版本后打开已发布文件', 'Range：读取指定音频字节区间', '从同快照生成 VTT 与 Markdown'], BLUE)
p.card(860, 710, 360, 185, '后台任务与恢复', ['一个工作者持独占锁，顺序处理', '成功片段保留，失败片段单独重试', '有版本差时重建录音结果快照', '保留执行次数，重启恢复未完成片段'], TEAL)
p.rect(60, 923, 1160, 101, 'white')
p.text(82, 958, '受控解码子进程', 21, TEAL, '600')
p.text(82, 994, '设备每 5 分钟生成一段原件，每段解码为一个 WAV 并独立识别；Server 不再二次切块。', 18)
p.card(40, 1095, 380, 255, '业务 SQLite · 保存录音业务数据', ['accounts：保存本站用户身份', 'recordings：内容/结果版本与 JSON 快照', 'recording_segments：片段与识别结果', '每段保存一份 WAV 和识别结果'], TEAL)
p.card(450, 1095, 380, 255, '设备与上传 SQLite · registry', ['bindings：保存设备归属与凭证', 'device_uids：映射硬件 UID 与设备', 'binding_profiles：保存上传配置版本', 'sources：记录每份原件及导入进度'], TEAL)
p.card(860, 1095, 380, 255, '私有文件存储 · 保存文件内容', ['raw：保留设备上传原件', '片段 WAV：同时用于播放和 ASR', 'VTT / Markdown：从 JSON 即时生成', '通过鉴权接口读取，路径不对外公开'], TEAL)
p.save('01-system-architecture')

# Source receipt: one annotated JSON field per line, plus the import boundaries.
p = Plate('原件导入', '读取 ready 来源，校验原件和归属，写入业务记录后标记导入完成。', 1010)
p.rect(40, 150, 760, 738)
p.text(62, 189, 'registry.sources · 已就绪原件的来源记录', 23, INK, '600')
p.text(62, 221, '每条来源对应一个片段；下面的值仅用于说明字段。', 17, MUTED)
p.text(64, 255, '{', 18)
source_fields = [
 ('id', '"source-001"', '来源记录唯一 ID；导入后对应片段的 source_id'),
 ('owner', '"user-001"', '录音所属用户 ID；由验证通过的设备绑定确定'),
 ('binding', '"binding-001"', '设备绑定 ID；导入后对应 source_namespace'),
 ('device', '"clip-001"', '设备 ID；标识这份录音来自哪台 Clip'),
 ('session', '"session-001"', '设备录音会话 ID；与绑定及代次一起归并为一条录音'),
 ('segment', '1', '会话内原件序号；从 1 开始，确定全局时间偏移'),
 ('size', '1024', '原始文件字节数；用于实际文件校验与处理限额'),
 ('sha256', '"' + 'a' * 64 + '"', '原始文件完整 SHA-256；示例值不代表真实文件'),
 ('object_id', '"object-001"', '服务端文件标识；定位原件，不接受客户端文件路径'),
 ('created', '1793318400', '来源建立时间；既有字段使用 Unix 秒，导入业务时转毫秒'),
 ('state', '"ready"', '只导入 ready 来源；其他状态由接入组件管理'),
 ('projected_at', 'null', '业务导入完成时间，Unix 毫秒；null 表示尚未标记导入完成'),
]
for i, (key, value, meaning) in enumerate(source_fields):
    y = 282 + i * 46
    p.text(80, y, '// ' + meaning, 15, MUTED)
    p.text(80, y + 21, '"' + key + '": ' + value + (',' if i < len(source_fields)-1 else ''), 16, INK)
p.text(64, 857, '}', 18)
p.card(840, 150, 400, 158, '1 · 读取 ready 来源', ['读取原件来源记录', 'owner、会话与段号取可信元数据', '原件已由接入组件可靠保存'], TEAL)
p.card(840, 334, 400, 140, '2 · 校验原件与归属', ['验证文件存在、类型、大小和 hash', '异常保留来源，暂不创建业务片段'], BLUE)
p.card(840, 500, 400, 178, '3 · 后台导入业务库', ['binding 映射为片段 source_namespace', 'id 映射为片段 source_id', '同一事务保存原件并递增内容版本', '重复导入同一来源不再增加版本'], TEAL)
p.card(840, 704, 400, 184, '4 · 标记业务导入完成', ['业务事务提交后填写 projected_at', 'null：尚未标记完成，可重试导入', '非空：记录最近一次完成标记的时间', '启动仍会核对文件与业务记录'], BLUE)
p.rect(40, 920, 1200, 58, PALE)
p.text(62, 955, '业务提交后标记失败：重放同一来源并核对片段，避免重复录音与版本递增。', 19)
p.save('04-raw-ingest-outbox')

# Segment processing and one rebuildable recording snapshot.
p = Plate('片段处理与结果汇总', '每份原件生成一个 WAV，按五分钟片段识别，汇总后用于播放和字幕导出。', 1070)
p.card(40, 150, 585, 245, 'recording_segments · 原件与识别结果', ['raw_relative_path：原件位置', 'sample_count：片段样本总数', 'decode_state / decode_attempt：解码状态与次数', 'wav_state / wav_*：WAV 状态与元数据', 'asr_state / asr_attempt：识别状态与次数', 'transcript_json：本片段的识别文字'], TEAL)
p.card(655, 150, 585, 245, 'recordings · 缓存一份结果快照', ['content_revision：当前可见内容版本', 'result_revision：已汇总到哪个内容版本', 'result_json：清单、时间轴、覆盖状态和原文', '内容版本与结果版本不同时重新汇总', '查询时根据片段计算进度'], BLUE)
for x, title, lines in [
 (40, '1 · 解码片段', ['一份原件独立流式解码', 'WAV 先落盘、校验与 fsync', '校验完成后提交片段索引', '不合成整条大音频']),
 (347, '2 · 片段识别', ['每段 ASR 调用前记录次数', '成功原文立即入库', '失败只重试当前片段', '中断不清空已执行次数']),
 (654, '3 · 更新快照', ['按实际样本数累计全局偏移', '缺号后的结果先缓存', 'CAS 核对当前内容版本', '一个事务替换整份快照']),
 (961, '4 · 播放与导出', ['按片段 WAV 清单播放', '从同一 JSON 生成字幕', 'VTT / Markdown 不落盘', 'HEAD 与 GET 使用同字节']),
]: p.card(x, 435, 279 if x == 961 else 280, 235, title, lines, BLUE)
p.card(40, 710, 585, 145, '识别成功但汇总中断', ['版本差仍然存在，重新汇总即可，不重跑成功片段。', '字幕由已提交 JSON 生成，不单独保存文件。'], TEAL)
p.card(655, 710, 585, 145, '片段 WAV 缺失或损坏', ['按原件和冻结配置重建，验证原摘要与样本范围。', '保留已有文字和缺失片段的时间区间。'], TEAL)
p.rect(40, 895, 1200, 125, PALE)
p.text(62, 932, '部分结果与运行限制', 23, INK, '600')
p.text(62, 970, 'partial 描述快照缺口；result_stale 表示还有新内容；单进程单工作者禁止多机并行运行。', 19)
p.text(62, 1003, 'speaker 编号仅在本片段内有效；原件边界识别与播放切换效果需实机验证。', 18, MUTED)
p.save('06-file-database-publication')

# Security boundaries: each component describes its concrete checks and responsibility.
p = Plate('文件访问与数据保护', '浏览器不能直接访问存储目录；Server 核对用户归属和版本后，才读取或处理对应文件。', 1070)
p.card(40, 150, 380, 255, '浏览器 · 发起读取请求', ['Cookie：携带本站会话身份', '录音 ID：指定要读取的录音', 'revision：固定音频清单和字幕快照', '通过 HTTPS 请求音频和文字', '退出时清理播放状态与本地会话状态'], BLUE)
p.card(450, 150, 380, 255, 'Server · 核对会话与归属', ['检查会话有效期和账号状态', 'owner：录音所属的本站用户 ID', '仅允许读取当前用户拥有的录音', '跨用户查询统一返回 404', '每次媒体请求都重新鉴权'], BLUE)
p.card(860, 150, 380, 255, 'Server · 校验文件并执行任务', ['核对快照版本与片段 WAV 状态', '以受控路径打开普通文件句柄', '拒绝符号链接和存储根之外的路径', '解码使用受限子进程并设置超时', '写索引前核对 WAV 大小与摘要'], BLUE)
p.card(40, 450, 380, 360, '私有加密数据卷 · 保存业务数据', ['raw：保留设备上传原件', '片段 WAV：每份原件对应一个文件', '字幕不落盘，由 JSON 快照生成', 'SQLite：保存归属、版本及原文 JSON', '由专用服务账号访问存储内容', '目录权限 0700：仅服务账号可进入', '文件权限 0600：仅服务账号可读写', '文件位于 Web 静态资源目录之外'], TEAL)
p.card(450, 450, 380, 360, '受控 ASR · 处理音频并返回原文', ['服务地址由 Server 配置', '远程连接使用 HTTPS 并校验证书', '本机端点须明确登记并限制访问', '禁止重定向，出站只放行配置目标', '输入 WAV 须先校验完整摘要', '返回原文、时间戳及说话人标识', '本地临时音频在处理结束后清理', '供应方留存按已核实的约定执行'], TEAL)
p.card(860, 450, 380, 360, '独立加密备份 · 恢复存储卷', ['每日停写后复制一致性快照', '同时备份数据库、原件和当前产物', '清单记录每个文件的字节数与摘要', '校验成功后保留最近 7 份快照', '备份置于独立存储介质', '备份密钥与备份数据分开授权', '恢复时先校验清单和数据库完整性', '恢复后撤销旧凭证，重新确认访问'], TEAL)
p.rect(40, 850, 1200, 175, PALE)
p.text(62, 887, '访问控制、存储与恢复', 23, INK, '600')
p.text(62, 926, '访问控制：阻止其他用户读取录音。加密存储：保护离线数据卷与备份中的内容。', 19)
p.text(62, 961, '文件与数据库双写：保持产物和索引一致。独立备份：提供数据卷损坏后的恢复点。', 19)
p.text(62, 996, '日志只保留定位信息和错误码，认证凭证与录音正文不写入日志。', 18, MUTED)
p.save('07-storage-security')

print('Generated 4 design SVG plates.')
