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

p = Plate('Clip 与 Web 的收件交接', 'Clip 验证后信任上报字段，用 ready JSON 交接；不建来源或上传表。', 970)
p.card(40, 150, 570, 210, '1 · Clip Server 完成接入', ['本地授权文件验证设备凭证与归属', '相信已验证上报，核对实际 size/hash', '原件 fsync 后原子发布 ready JSON', '不连接数据库，不建 Clip 表'], TEAL)
p.card(650, 150, 590, 210, '2 · Web Server 读取 ready 来源', ['校验归属、原件和处理限额', '复制 raw 与来源描述到两音频盘', '两份均 hash / fsync 通过再继续', '来源未就绪或双盘异常时暂停'], BLUE)
p.card(40, 405, 570, 210, '3 · 文件锁内幂等导入', ['固定 state.lock 排他锁 + 进程内 mutex', '按来源 ID 去重，按会话聚合录音', '原子更新 recording.json 及内容版本', '按确定 ID 补齐 decode / asr job'], BLUE)
p.card(650, 405, 590, 210, '4 · 文件对账与幂等重放', ['录音和所需 job 全部 fsync 后完成', 'ready 来源文件保持不可变', '再扫描同一来源时按身份去重', '无需 projected_at 或已消费表'], TEAL)
p.card(40, 660, 1200, 210, '崩溃与服务停止', ['Clip 停止：Web 可导入/解码，ASR 暂停；Web 停止：Clip 仍可收件。', '录音写成但 job 未创建：Web 启动对账，按确定 ID 补建；不重复新增录音。', 'ready 文件与原件不一致：拒绝导入并告警；同来源不同内容不能覆盖。', '启动分批扫描全部 ready JSON；不依赖数据库登记来源或消费进度。'], TEAL)
p.save('04-raw-ingest-outbox')

p = Plate('录音文件与 job 文件提交', '文件锁解决并发；原子替换解决半写 JSON；提交顺序和对账解决多文件中断。', 1090)
p.card(40, 150, 570, 215, 'recording.json · 可见结果提交点', ['owner、可信来源、片段信息与 WAV 引用', '不可变识别原文 JSON 的路径 / size / hash', 'content_revision / result_revision / result_json', 'last_*_commit 保存 job_id 与 attempt_id'], BLUE)
p.card(650, 150, 590, 215, 'jobs/id.json · 可重建调度记录', ['阶段、代次、状态、attempt 与 run_after', 'attempt_id / 输入 hash / 错误码', 'decode、asr、merge、repair 各自定位', '不保存真实凭证，不新增 job 表'], TEAL)
for x,title,lines in [
 (40,'1 · 锁内领取',['复核输入与预算','次数加一并写 running','生成唯一 attempt_id','释放 state 锁']),
 (347,'2 · 锁外执行',['解码或调用 ASR','双盘 WAV 校验发布','原文 JSON 持久化','不阻塞 Web 事件循环']),
 (654,'3 · 锁内提交',['再次核对 attempt_id','原子替换录音 JSON','再把 job 标 ready','补齐下一阶段 job']),
 (961,'4 · 读取与导出',['共享锁捕获一致视图','释放锁后读取音频','从快照生成 VTT / MD','不暴露磁盘路径']),
]: p.card(x,410,279 if x==961 else 280,220,title,lines,BLUE)
p.card(40,675,570,220,'结果已保存，job 尚未完成',['启动核对录音中的执行提交标识','匹配时补标 job ready，不重复 ASR','若无提交结果，保留次数退避重试','Clip 内推理不保证恰好调用一次'],TEAL)
p.card(650,675,590,220,'快照与修复',['锁外构建，锁内复核 content_revision','版本变化则重新汇总，不重识别','repair 独立预算，保留成功文字','状态根损坏不能当空数据覆盖'],TEAL)
p.rect(40,935,1200,100,PALE)
p.text(62,974,'固定锁 inode 不删除、不替换；不能直接锁将被 rename 的 JSON。',22)
p.text(62,1010,'JSON 写入：同目录临时文件 → fsync → os.replace → fsync 目录；无录音 / 片段 / job 表。',19,MUTED)
p.save('06-file-database-publication')

p = Plate('文件访问与数据保护', 'Web 校验 owner / revision；Clip 校验接入身份；元数据文件独立于音频双盘。', 1010)
p.card(40,150,380,245,'Web Server · 授权读取',['本站会话、账号状态与 CSRF','仅返回当前 owner 的录音','每次 GET / HEAD / Range 鉴权','共享锁内读取录音和 job','锁外执行媒体 I/O 与导出'],BLUE)
p.card(450,150,380,245,'Clip Server · 可信收件',['只读授权文件及凭证校验材料','验证通过后信任 Clip 上报信息','owner 必须与已验证凭证一致','内置离线 ASR；不加载 Google 凭证','不连接任何数据库'],TEAL)
p.card(860,150,380,245,'文件发布与受控处理',['路径使用服务端生成 ID','openat / O_NOFOLLOW 检查','拒绝符号链接与根外路径','受限解码子进程与超时','ASR 仅用本机私有 socket'],BLUE)
p.card(40,440,380,300,'独立元数据卷',['单个 SQLite：accounts / devices','授权 / 收件 / 录音 / job 文件','固定角色锁与共享 state 锁','目录 0700，文件 0600','不部署到 NFS 或公开静态目录','损坏告警，禁止自动覆盖空状态'],TEAL)
p.card(450,440,380,300,'两个独立音频盘',['raw / 描述 / WAV 双份保存','先两份 fsync 再提交录音引用','一盘故障暂停接入发布及处理','离线只写替换盘，幸存盘只读','保留成功 ASR 和 job 执行预算','不因换盘回滚当前元数据'],TEAL)
p.card(860,440,380,300,'独立加密版本备份',['同时停两个服务及在途执行','关闭数据库，复制完整状态根','备份 raw / WAV / 配置与清单','核对数据库、JSON 关联和 hash','保留最近 7 份完整版本','恢复不重建账号或撤销授权'],TEAL)
p.rect(40,785,1200,155,PALE)
p.text(62,826,'文件锁不代替持久化，也不代替 SQLite 事务。',23,INK,'600')
p.text(62,866,'音频盘故障不影响健康元数据卷中的既有文字；元数据卷故障从一致备份恢复。',20)
p.text(62,906,'两个服务各自单实例；无第三个常驻工作进程。日志不记录凭证和录音正文。',19,MUTED)
p.save('07-storage-security')
# Internal module contracts, without introducing extra services.
p = Plate('Web Server 与 Clip Server 模块边界', '两个独立入口，各自分层；共享契约和文件工具，不共享数据库访问或进程内状态。', 1290)
p.card(40,150,1200,145,'共享 contracts / platform',['DTO、文件 schema、错误码；配置、受控路径、flock、原子写和脱敏计量', '不导入 FastAPI / DTLS / SQLite / ASR SDK；不持全局连接，不启动任何监听'],TEAL)
p.rect(40,335,570,650,PALE)
p.text(62,377,'Clip Server · 独立进程',25,TEAL,'600')
p.card(60,410,530,145,'transport / protocol',['DTLS连接、帧解析、消息状态机', '输入有界；不把socket交给业务模块'],TEAL)
p.card(60,575,530,145,'application / ports',['验证、开始/续传/完成收件用例', '只依赖授权读取、收件、发布接口'],TEAL)
p.card(60,740,530,200,'文件与授权 adapters',['只读本地授权/凭证材料', '写收件/来源/会话事件与设备报告', '无SQLite、无Web app、无job仓储', '内置模型与本机接口，独立推理线程'],TEAL)
p.rect(640,335,600,650,PALE)
p.text(662,377,'Web Server · 独立进程',25,BLUE,'600')
p.card(660,410,560,145,'API / middleware',['登录、用户设备、录音、媒体、health', '会话、owner、CSRF、限流、错误映射'],BLUE)
p.card(660,575,560,145,'application / domain / worker',['设备配置、导入、job、识别、汇总用例', '一个后台循环；router/worker不直接I/O'],BLUE)
p.card(660,740,560,200,'仓储与执行 adapters',['SQLite仅accounts/devices；录音/job文件', '受限解码、Clip ASR客户端、VTT/MD', 'FastAPI lifespan集中启动、恢复和退出', 'bootstrap注入接口实现，禁止反向依赖'],BLUE)
p.card(40,1020,570,170,'进程交接与所有权',['Clip发布ready/会话事件，Web重放导入', 'Web发布授权文件，Clip只读验证', '固定state锁保护短提交；I/O在锁外'],TEAL)
p.card(640,1020,600,170,'依赖方向',['入口 → 用例 → port / contracts', 'adapter实现接口，由bootstrap装配', 'Clip不引用Web或任何数据库模块'],BLUE)
p.save('08-module-boundaries')
print('Generated 5 design SVG plates.')
