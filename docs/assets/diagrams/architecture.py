"""Render the C4 container source as a deterministic, locally generated SVG.

C4 semantics/labels/relationships come from the .mmd source. Layout comments
control SVG geometry; the unmodified source is also usable in Mermaid.
"""
from html import escape
import json
import math
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / '01-system-architecture.mmd'
FONT = 'PingFang SC,Microsoft YaHei,Noto Sans CJK SC,Arial,sans-serif'
BLUE, DARK, GREY, INK = '#1168bd', '#08427b', '#6b7280', '#253247'


def width_units(text):
    return sum(1.0 if unicodedata.east_asian_width(ch) in 'WF' else .55 for ch in text)


def wrap(text, pixels, size):
    result = []
    for paragraph in text.split('\n'):
        line = ''
        for ch in paragraph:
            if line and width_units(line + ch) * size > pixels:
                result.append(line.strip())
                line = ''
            line += ch
        result.append(line.strip())
    return result


def render():
    source = SOURCE.read_text()
    nodes, positions, relations, routes = {}, {}, [], {}
    boundary = None
    for line in source.splitlines():
        m = re.match(r'\s*(Person|System_Ext|Container|ContainerDb|Rel|BiRel)\((.*)\)\s*$', line)
        if m:
            kind, args = m.groups()
            tokens = re.findall(r'"(?:\\.|[^"\\])*"|[A-Za-z_]\w*', args)
            values = [json.loads(t) if t.startswith('"') else t for t in tokens]
            if kind in ('Rel', 'BiRel'):
                relations.append((kind, *values))
            else:
                nodes[values[0]] = (kind, values[1:])
        m = re.match(r'\s*%% @position (\w+) (\d+) (\d+) (\d+) (\d+)', line)
        if m: positions[m[1]] = tuple(map(int, m.groups()[1:]))
        m = re.match(r'\s*%% @boundary (\d+) (\d+) (\d+) (\d+)', line)
        if m: boundary = tuple(map(int, m.groups()))
        m = re.match(r'\s*%% @route (\w+) (\w+) (.*?) \| (\d+) (\d+) (\d+)', line)
        if m:
            points = [tuple(map(int, point.split(','))) for point in m[3].split()]
            routes[(m[1], m[2])] = (points, *map(int, m.groups()[3:]))
    assert set(nodes) == set(positions)
    assert set(routes) == {(r[1], r[2]) for r in relations}
    assert not any(r[1] == 'clip' and r[2] == 'database' for r in relations)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1590" viewBox="0 0 1800 1590" role="img" aria-labelledby="title desc">',
        '<title id="title">ReSpeaker Clip 系统架构图</title>',
        '<desc id="desc">两个独立服务，Clip无数据库访问；Web管理用户设备、文件任务和音频处理。箭头标明协议与数据读写方向。</desc>',
        '<rect width="1800" height="1590" fill="white"/>',
        '<defs><marker id="arrow" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="10" markerHeight="10" orient="auto-start-reverse"><path d="M 1 1 L 11 6 L 1 11 Z" fill="#64748b"/></marker></defs>',
        f'<g font-family="{FONT}">']

    def text(x, y, value, size=20, color=INK, anchor='middle', weight='400'):
        parts.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(value)}</text>')

    text(50, 47, 'ReSpeaker Clip · 系统架构图', 32, anchor='start', weight='600')
    text(50, 78, '系统边界、两个服务、外部依赖与数据存储', 20, '#64748b', anchor='start')
    x,y,w,h = boundary
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#fbfdff" stroke="#475569" stroke-width="2" stroke-dasharray="10 7"/>')
    text(x+22,y+34,'Speaker Server',23,anchor='start',weight='600')

    # Connectors first, nodes over them; all endpoint identities come from source.
    for kind, origin, destination, label, technology in relations:
        points,lx,ly,lw = routes[(origin,destination)]
        d = 'M ' + ' L '.join(f'{a} {b}' for a,b in points)
        parts.append(f'<path d="{d}" fill="none" stroke="#64748b" stroke-width="2.5" stroke-dasharray="7 5" stroke-linejoin="round"/>')
        # Explicit arrow polygons also render in platform SVG thumbnailers.
        def arrow(tip, previous):
            dx, dy = tip[0]-previous[0], tip[1]-previous[1]
            length = math.hypot(dx, dy)
            ux, uy = dx/length, dy/length
            bx, by = tip[0]-20*ux, tip[1]-20*uy
            pts = [tip, (bx-8*uy, by+8*ux), (bx+8*uy, by-8*ux)]
            parts.append('<polygon points="' + ' '.join(f'{a:.1f},{b:.1f}' for a,b in pts) + '" fill="#64748b"/>')
        arrow(points[-1], points[-2])
        if kind == 'BiRel':
            arrow(points[0], points[1])
        lines = wrap(label,lw,19) + [f'[{technology}]']
        box_w = min(lw+24,max(width_units(v)*19 for v in lines)+28)
        parts.append(f'<rect x="{lx-box_w/2:.1f}" y="{ly-23}" width="{box_w:.1f}" height="{len(lines)*27+8}" rx="4" fill="white" fill-opacity="0.97"/>')
        for i,v in enumerate(lines):text(lx,ly+i*27,v,19)

    for ident,(kind,values) in nodes.items():
        x,y,w,h = positions[ident]
        title = values[0]
        if kind == 'Person':
            cx = x+w/2
            parts.append(f'<circle cx="{cx}" cy="{y+23}" r="21" fill="{DARK}"/>')
            parts.append(f'<path d="M {cx-43} {y+88} Q {cx-43} {y+50} {cx} {y+50} Q {cx+43} {y+50} {cx+43} {y+88} Z" fill="{DARK}"/>')
            text(cx,y+120,title,25,DARK,weight='600')
            text(cx,y+148,'用户',17,'#64748b')
            text(cx,y+176,values[1],19)
            continue
        fill = GREY if kind == 'System_Ext' else BLUE
        if kind == 'ContainerDb':
            parts.append(f'<path d="M{x} {y+16} C{x} {y-7},{x+w} {y-7},{x+w} {y+16} L{x+w} {y+h-16} C{x+w} {y+h+7},{x} {y+h+7},{x} {y+h-16} Z" fill="{fill}" stroke="#0b4f90" stroke-width="2"/>')
            parts.append(f'<path d="M{x} {y+16} C{x} {y+39},{x+w} {y+39},{x+w} {y+16}" fill="none" stroke="white" stroke-opacity=".7" stroke-width="1.5"/>')
            top = y+57
            subtitle = values[1]
            description = values[2]
        else:
            parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{fill}" stroke-width="2"/>')
            top = y+40
            subtitle = '设备' if ident == 'device' else ('外部服务' if kind == 'System_Ext' else values[1])
            description = values[1] if kind == 'System_Ext' else values[2]
        text(x+w/2,top,title,25,'white',weight='600')
        text(x+w/2,top+29,subtitle,16,'#edf4fb')
        description_lines = wrap(description,w-35,19)
        assert top+64+(len(description_lines)-1)*27 < y+h-5,ident
        for i,v in enumerate(description_lines):text(x+w/2,top+64+i*27,v,19,'white')
    text(60,1557,'图例',20,anchor='start',weight='600')
    for x,fill,label in [(145,DARK,'人员'),(365,GREY,'外部系统'),(655,BLUE,'服务 / 数据存储')]:
        parts.append(f'<rect x="{x}" y="1540" width="30" height="24" rx="3" fill="{fill}"/>')
        text(x+45,1559,label,19,anchor='start')
    parts.extend(['</g>','</svg>'])
    (ROOT/'01-system-architecture.svg').write_text('\n'.join(parts)+'\n')


if __name__ == '__main__':
    render()
