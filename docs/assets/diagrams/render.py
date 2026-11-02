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
                      f'<rect width="1280" height="{height}" fill="white"/>',
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



# Render the standard C4 container view from its editable Mermaid source.
import runpy
runpy.run_path(str(ROOT / 'architecture.py'), run_name='__main__')

p = Plate('Clip 处理完整录音，Web 读取成品', '设备上传、中间状态和成品均在本机文件系统；通过正式录音目录交接。', 970)
p.card(40,150,570,210,'1 · Clip 接收与聚合',['验证设备授权、Opus size/hash', '保存原件、续传进度和录完声明', '按recording / segment_no聚合', '来源与job是Clip内部状态'],TEAL)
p.card(650,150,590,210,'2 · Clip 逐段处理',['原始Opus解码为标准分段WAV', '内置模型转写、断句及时间戳', '成功一段保存一段，失败局部重试', 'Web不参与解码、识别或job'],TEAL)
p.card(40,405,570,210,'3 · Clip 合并完整录音',['核对结束声明及1..N全部成功', '顺序拼接PCM并生成一个完整WAV', '累计样本偏移，生成完整VTT和MD', '缺片或失败不发布成品'],TEAL)
p.card(650,405,590,210,'4 · Web 只读完整三件套',['读取正式目录及录音信息', '会话校验，按用户 / Clip / ID定位', '完整WAV播放、VTT字幕和MD下载', '不读取半成品，不现场生成文件'],BLUE)
p.card(40,660,1200,210,'文件交接与独立运行',['Clip写完整WAV / VTT / MD，全部校验并fsync后原子发布整个录音目录。', 'Web写设备授权，Clip只读验证；Clip不访问数据库，Web不处理录音job。', 'Web停止：Clip继续收件、处理和发布；Clip停止：Web仍可读取已发布成品。', '同一本机文件系统按用户与Clip隔离，前端只用ID构造固定API请求。'],TEAL)
p.save('04-raw-ingest-outbox')

p = Plate('完整录音的成品发布', '一个recording一个目录，直接保存完整WAV、VTT、MD和录音信息。', 1080)
p.card(40,150,570,210,'内部处理提交',['recording和job都由Clip写文件', '片段任务校验本段输入hash与配置', '录音任务核对完整输入版本和段号', '持久attempt / generation拒绝旧执行'],TEAL)
p.card(650,150,590,210,'正式录音目录',['recording.wav：完整连续音频', 'transcript.vtt：全局时间字幕', 'transcript.md：完整逐句文本', 'recording.json：ID / owner / 时间 / 时长'],TEAL)
for x,title,lines in [
 (40,'1 · 生成',['锁外读取成功片段', '流式合并PCM', '统一字幕时间轴', '生成完整三件套']),
 (347,'2 · 持久化',['校验样本与hash', 'fsync所有文件', '保存录音信息', 'fsync临时目录']),
 (654,'3 · 原子发布',['短锁复核输入版本', '核对attempt代次', '原子重命名整个目录', 'fsync录音父目录']),
 (961,'4 · Web读取',['核对会话及owner', '只读录音信息', '从同一录音目录读取', '不解码或重新导出']),
]: p.card(x,410,279,220,title,lines,BLUE)
p.card(40,675,570,220,'提交中断后的对账',['重命名前：Web忽略隐藏临时目录', '重命名后：成品可读，补齐内部job', '校验发布标识，不重复ASR', '未知或坏状态告警，不覆盖为空'],TEAL)
p.card(650,675,590,220,'完整性与发布',['无结束声明或缺片：不发布', '全部片段解码和转写成功才合并', '总样本等于所有片段样本之和', '正式目录已存在时核对并幂等返回'],BLUE)
p.text(45,970,'固定文件锁保护短提交；音频处理、模型推理与hash校验均在锁外。',22)
p.save('06-file-database-publication')

p = Plate('两个服务的文件访问边界', '同一本机文件系统；按目录和接口控制所有权，不设置磁盘副本。', 970)
p.card(40,150,380,280,'Clip Server',['只读设备授权和离线模型', '写raw、片段WAV和逐段转写', '写recording / job处理状态', '合并完整WAV / VTT / MD', '发布四个文件的录音目录', '不连接用户与设备数据库'],TEAL)
p.card(450,150,380,280,'Web Server',['管理登录、用户和设备', '写设备授权，采用deny-first', '按用户作用域只读完整三件套', 'GET / HEAD / Range每次鉴权', '不访问原件、中间态或job', '不生成字幕、MD或音频'],BLUE)
p.card(860,150,380,280,'本机文件系统',['授权、来源与状态都是文件', '原件、中间与成品均按用户/Clip隔离', '路径受控，拒绝符号链接', '目录0700，文件0600', '临时文件校验后原子发布', '无双写、复制或备份任务'],TEAL)
p.card(40,475,570,260,'完整性与资源',['原始音频不可信，解码子进程隔离', '模型离线加载，输入与输出有界', '按样本合并，不跳号或补静音', '三件套全部持久化后才发布', '大文件流式处理，空间不足暂停'],TEAL)
p.card(650,475,590,260,'OP管理部署',['Nginx提供HTTPS，代理本机Web', 'OP管理托管器、资源、监控和证书', '整体备份与恢复不由应用实现', 'Clip故障不妨碍读取已有完整成品', '日志排除凭证和录音/识别正文'],BLUE)
p.text(45,820,'文件锁不代替fsync、原子发布或SQLite事务。',23)
p.text(45,868,'SQLite仅accounts / devices，由Web访问；录音、job和成品完全使用文件。',20)
p.save('07-storage-security')

p = Plate('Clip处理与Web读取的模块边界', '两个应用进程；Clip发布完整录音，Web读取成品；公共文件能力不持业务资源。', 1220)
p.card(40,150,1200,125,'公共契约与文件能力',['授权、job、录音信息的数据契约；受控路径、文件锁、原子写及脱敏日志'],TEAL)
p.rect(40,315,570,615,PALE)
p.text(62,357,'Clip Server · 收件与处理',25,TEAL,'600')
p.card(60,390,530,140,'设备接入与recording聚合',['DTLS / 身份验证 / Opus续传', '完整来源、结束声明与段号完整性'],TEAL)
p.card(60,550,530,160,'音频处理与任务调度',['recording / job文件，一个后台循环', '逐段解码和ASR，失败只重试相应阶段', '收齐后合并完整WAV / VTT / MD'],TEAL)
p.card(60,730,530,160,'成品发布',['三件套与录音信息全部校验 / fsync', '目录原子重命名作为交接提交点', '不连接任何数据库'],TEAL)
p.rect(640,315,600,615,PALE)
p.text(662,357,'Web Server · 用户设备与成品',25,BLUE,'600')
p.card(660,390,560,140,'用户、设备与授权',['Google OIDC / 会话 / CSRF', 'accounts / devices及设备授权文件'],BLUE)
p.card(660,550,560,160,'成品目录与读取',['只读本人Clip下的正式录音目录', '仅返回ID；后台推导目录并鉴权', '不读原件、内部recording或job'],BLUE)
p.card(660,730,560,160,'完整录音播放器与下载',['读取现成WAV、VTT和Markdown', '完整WAV播放、字幕与附件下载', '不解码、不转写、不合并、不生成文件'],BLUE)
p.card(40,970,1200,155,'同一本机文件系统',['Web写设备授权 → Clip只读；Clip写完整成品 → Web只读', '原件、中间态及成品均按owner / device_id隔离，地址按录音ID推导'],TEAL)
p.save('08-module-boundaries')
print('Generated system architecture and four supporting design diagrams.')
