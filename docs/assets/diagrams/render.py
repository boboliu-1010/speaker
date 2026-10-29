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

# Persistence ownership view for receive and projection.
p = Plate('原件存储与双写投影', '原件与来源索引完成持久化后确认设备；业务投影可恢复', 760)
p.card(40, 160, 250, 370, '设备 / 接收器', ['设备凭证与归属校验', '已持久偏移 ACK', 'size / SHA-256 检查', 'raw 与 identity 持久化', '完整来源就绪后 COMPLETE'], TEAL)
p.entity(335, 160, 415, 'registry.sources', ['id / owner / binding', 'session / segment / object_id', 'size / sha256', 'state = ready', 'projected_at = NULL 或提交时间'])
p.entity(795, 160, 445, '业务库', ['recordings：来源聚合与输入版本', 'recording_segments：raw 元数据', '唯一键：source_namespace + source_id', 'imported_at：首次导入时间', '同一事务更新片段与录音版本'])
p.rect(335, 430, 905, 100, '#edf3ff', '#d3e0f7')
p.text(357, 465, '跨库提交规则', 20, BLUE, '600')
p.text(357, 500, '业务提交成功后填写 projected_at；重放时核对来源唯一键与 hash。', 18)
p.rect(40, 570, 1200, 124, PALE)
p.text(62, 605, '启动对账', 22, INK, '600')
p.text(62, 643, '后台按每批 500 条核对 ready 来源；片段首次 ready 时递增 input_revision。', 19)
p.text(62, 675, '设备接收确认与 WAV / ASR 任务独立运行。', 18, MUTED)
p.save('04-raw-ingest-outbox')

# State matrix makes file/database commit and failure handling visible.
p = Plate('文件与数据库双写', '文件落盘后，jobs / 录音指针 / 转写 JSON 按事务发布', 805)
xs = [40, 205, 490, 760, 1010]
heads = ['提交阶段', '磁盘文件', 'jobs', 'recordings', '恢复动作']
for x, h in zip(xs, heads):p.text(x + 12, 165, h, 19, INK, '600')
rows = [
 ('准备', ['临时路径 / 最终路径'], ['prepared', '记录 lease'], ['保留当前指针'], ['回收过期 lease']),
 ('生成', ['临时文件 fsync', '记录 size/hash/sample_count'], ['prepared', '元数据已保存'], ['保留当前指针'], ['重做未完成产物']),
 ('文件落盘', ['link 不覆盖 + 目录 fsync'], ['prepared', '最终文件可校验'], ['等待事务提交'], ['WAV 校验后补提交', 'VTT 结合文字事务处理']),
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

# Owner-scoped access, private storage, and independent recovery copy.
p = Plate('音频存储与访问边界', '用户通过媒体接口读取；服务账号管理加密数据卷与独立备份', 825)
p.card(40, 190, 245, 212, 'Web 用户', ['本站 Cookie', '录音 ID + revision', 'WAV / JSON / VTT / MD'], BLUE)
p.rect(345, 150, 550, 290, PALE)
p.text(368, 188, '媒体与录音服务', 25, INK, '600')
p.card(367, 211, 246, 190, '访问校验', ['会话与账号状态', 'owner 与录音版本', '文件状态 / 类型 / size'], BLUE)
p.card(633, 211, 240, 190, '保存与发布', ['受限解码与识别', '文件 fsync / hash', 'SQLite 事务发布'], TEAL)
p.rect(345, 505, 550, 236, '#eaf5f1', '#c4ded5')
p.text(368, 544, '加密数据卷 · 专用服务账号', 24, TEAL, '600')
p.text(368, 591, ['raw 原件 / WAV / VTT', 'SQLite：归属、文件元数据、原文 JSON', '目录 0700 / 文件 0600', '文件通过服务端 ID 定位'], 19, INK)
p.card(960, 150, 280, 218, '受控 ASR', ['固定端点与目标白名单', 'HTTPS / 本机受控访问', '校验后传入 WAV', '本次处理后清理临时副本'], TEAL)
p.card(960, 505, 280, 236, '独立加密备份', ['一致性快照与 size/hash', '默认每日，最近 7 份', '验证后标记备份成功', '密钥与备份分开授权', '校验归属后恢复'], BLUE)
p.line(285, 288, 345, 288, BLUE, 2);p.text(289, 270, 'HTTPS', 14, BLUE)
p.line(895, 268, 960, 268, TEAL, 2)
p.line(620, 440, 620, 505, TEAL, 2)
p.line(895, 610, 960, 610, BLUE, 2)
p.text(40, 793, '双写保证文件与索引一致；独立备份提供存储卷损坏后的恢复点。', 19, MUTED)
p.save('07-storage-security')

print('Generated 4 design SVG plates.')
