# -*- coding: utf-8 -*-
"""
build.py —— ふしぎ遊戯 朱雀異聞 攻略站 构建脚本
------------------------------------------------
用法:  python build.py
读取同目录下的 攻略.md，生成 index.html。
无需第三方依赖（纯 Python 标准库）。
"""
import html
import os
import re
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(HERE, "攻略.md")
OUT_PATH = os.path.join(HERE, "index.html")

ASSET = lambda f: "assets/" + quote(f)

# ---------------------------------------------------------------- 解析


def parse_md(text):
    # 去掉文件头的 HTML 注释说明
    text = re.sub(r"^\s*<!--.*?-->\s*", "", text, flags=re.S)
    # front matter
    meta = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, flags=re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        text = text[m.end():]
    return meta, text


def split_sections(text):
    """按 '# ' 一级标题切分。返回 [ {'title':str|None,'lines':[...]} ]"""
    sections = []
    cur = {"title": None, "lines": []}
    for ln in text.splitlines():
        if ln.startswith("# ") and not ln.startswith("## "):
            sections.append(cur)
            cur = {"title": ln[2:].strip(), "lines": []}
        else:
            cur["lines"].append(ln)
    sections.append(cur)
    return sections


def parse_blocks(lines):
    """把行解析为块: (type, payload)
    type: h2 / h3 / table / quote / list / para / hr
    list 项: {'text':str,'subs':[str]}
    """
    blocks = []
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue
        if s == "---":
            blocks.append(("hr", None))
            i += 1
            continue
        if raw.startswith("### "):
            blocks.append(("h3", raw[4:].strip()))
            i += 1
            continue
        if raw.startswith("## "):
            blocks.append(("h2", raw[3:].strip()))
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            blocks.append(("table", rows))
            continue
        if raw.startswith("> "):
            q = []
            while i < n and lines[i].startswith("> "):
                q.append(lines[i][2:].strip())
                i += 1
            blocks.append(("quote", q))
            continue
        if raw.startswith("- "):
            items = []
            while i < n:
                l2 = lines[i]
                if l2.startswith("- "):
                    items.append({"text": l2[2:].strip(), "subs": []})
                    i += 1
                elif l2.lstrip().startswith("- ") and l2.startswith("  ") and items:
                    items[-1]["subs"].append(l2.strip()[2:].strip())
                    i += 1
                else:
                    break
            blocks.append(("list", items))
            continue
        # 普通段落（连续非空行合并）
        p = [s]
        i += 1
        while i < n:
            l2 = lines[i]
            t2 = l2.strip()
            if (not t2 or t2 == "---" or l2.startswith(("#", "|", "> ", "- "))
                    or l2.startswith("  - ")):
                break
            p.append(t2)
            i += 1
        blocks.append(("para", " ".join(p)))
    return blocks


# ---------------------------------------------------------------- 行内渲染


def esc(s):
    return html.escape(s, quote=False)


def inline(s):
    s = esc(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
               r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s


def render_table(rows):
    def cells(r):
        return [c.strip() for c in r.strip().strip("|").split("|")]

    head = cells(rows[0])
    body = [cells(r) for r in rows[1:]
            if not re.fullmatch(r"\|?[\s:|-]+\|?", r)]
    out = ['<div class="tbl-wrap"><table><thead><tr>']
    out += [f"<th>{inline(c)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for r in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


# ---------------------------------------------------------------- 角色卡

META_PAT = re.compile(r"^(CV|加入|生存)\s*[:：]\s*(.*)$")


def char_card(name, blocks):
    meta, desc = {}, []
    for b in blocks:
        if b[0] == "list":
            for it in b[1]:
                m = META_PAT.match(it["text"])
                if m:
                    meta[m.group(1)] = m.group(2).strip()
        elif b[0] == "quote":
            desc.extend(b[1])
    icon = {"CV": "🗣", "加入": "⚔", "生存": "🛡"}
    label = {"CV": "CV", "加入": "加入方法", "生存": "生存条件"}
    img = ASSET(name + ".png")
    img_html = (f'<img class="avatar" src="{img}" alt="{esc(name)}">'
                if os.path.exists(os.path.join(HERE, "assets", name + ".png"))
                else '<div class="avatar avatar-ph">✦</div>')
    rows = "".join(
        f'<div class="meta-row"><span class="meta-ic">{icon[k]}</span>'
        f'<span class="meta-k">{label[k]}</span>'
        f'<span class="meta-v">{inline(v)}</span></div>'
        for k, v in meta.items())
    d = "".join(f"<p>{inline(x)}</p>" for x in desc)
    return (f'<article class="char-card">'
            f'<div class="char-head">{img_html}<h3>{esc(name)}</h3></div>'
            f'{rows}{d}</article>')


# ---------------------------------------------------------------- 路线


def route_step(text, idx):
    t = text.strip()
    if t.startswith("【地】"):
        name = t[len("【地】"):].strip()
        return ('loc', f'<div class="step loc"><span class="pin">◆</span>'
                       f'<span class="loc-name">{esc(name)}</span></div>', idx)
    if t.startswith("★"):
        return ('warn', f'<div class="step warn"><span class="ic">⚠</span>'
                        f'<span>{esc(t[1:].strip())}</span></div>', idx)
    if t.startswith("＊") or t.startswith("*"):
        body = t.lstrip("＊*").strip()
        return ('spec', f'<div class="step spec"><span class="ic">✦</span>'
                        f'<span>{esc(body)}</span></div>', idx)
    if ("→" in t or "->" in t) and re.search(r"(END|ED|結局|结局)\s*$", t.rstrip()):
        parts = re.split(r"→|->", t)
        dest = parts[-1].strip()
        cond = "→".join(parts[:-1]).strip()
        cls = "end-a" if ("異世界" in dest or "异世界" in dest) else "end-b"
        return ('end', f'<div class="step ending {cls}">'
                       f'<span class="cond">{esc(cond)}</span>'
                       f'<span class="arr">➜</span>'
                       f'<span class="badge">{esc(dest)}</span></div>', idx)
    idx += 1
    return ('choice', f'<div class="step choice"><span class="num">{idx}</span>'
                      f'<span class="txt">{esc(t)}</span></div>', idx)


def route_panel(name, blocks):
    steps, notes_pre, notes_post, count = [], [], [], 0
    for b in blocks:
        if b[0] == "list":
            for it in b[1]:
                kind, h, count = route_step(it["text"], count)
                steps.append(h)
        elif b[0] == "quote":
            tgt = notes_pre if not steps else notes_post
            tgt.append("".join(f"<p>{inline(x)}</p>" for x in b[1]))
        elif b[0] == "para":
            (notes_pre if not steps else notes_post).append(
                f"<p>{inline(b[1])}</p>")
    pre = f'<div class="route-note">{"".join(notes_pre)}</div>' if notes_pre else ""
    post = f'<div class="route-note">{"".join(notes_post)}</div>' if notes_post else ""
    body = "".join(steps)
    return (f'<div class="route-panel" id="r{PAGE.roots.index(name)}">'
            f'{pre}<div class="timeline">{body}</div>{post}</div>'), count


# ---------------------------------------------------------------- 页面骨架

CSS = r"""
:root{
  --bg:#f6efe0; --panel:rgba(255,252,245,.86); --panel2:rgba(247,238,221,.90);
  --line:#e6d8bd; --gold:#b5712f; --gold-dim:#cd9a63;
  --ver:#c0532f; --ver-b:#d2693f; --text:#463726; --muted:#8c7757;
  --teal:#4f876f; --purple:#6f5d92; --suzaku:#c2603a;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0; color:var(--text); line-height:1.75;
  font-family:"Noto Serif SC","Source Han Serif SC","Yu Mincho",
    "Hiragino Mincho ProN","MS Mincho","SimSun",serif;
  background:var(--bg);
}
/* 朱雀水印：单色、低透明、固定于米白底之上 */
body::before{content:"";position:fixed;inset:0;z-index:-1;
  background:url('ASSET_BG') center 46% / min(560px,72%) no-repeat;
  opacity:.14}
a{color:var(--gold);text-decoration:none}
a:hover{color:var(--ver-b)}
code{background:#00000055;border:1px solid var(--line);border-radius:4px;
  padding:1px 6px;font-family:Consolas,monospace;font-size:.9em;color:var(--gold)}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}

/* ---- 导航 ---- */
#topnav{position:sticky;top:0;z-index:50;
  background:rgba(246,239,224,.92);backdrop-filter:blur(8px);
  border-bottom:1px solid var(--line)}
.nav-inner{max-width:1080px;margin:0 auto;padding:10px 20px;
  display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.brand{font-weight:bold;color:var(--ver);letter-spacing:2px;font-size:1.05em}
.nav-links{display:flex;gap:4px;overflow-x:auto}
.nav-links a{color:var(--muted);padding:4px 12px;border-radius:20px;
  font-size:.92em;white-space:nowrap}
.nav-links a:hover{color:var(--text)}
.nav-links a.active{background:var(--ver);color:#fff}
.genbu{margin-left:auto;display:inline-flex;align-items:center;gap:6px;padding:5px 15px;border-radius:20px;background:var(--ver);color:#fff;font-size:.9em;letter-spacing:1px;text-decoration:none;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.14);transition:filter .15s}
.genbu:hover{filter:brightness(1.1)}

/* ---- Hero ---- */
.hero{position:relative;overflow:hidden;text-align:center;padding:34px 20px 40px}
/* 朱雀：hero 纯米白底上的清晰大水印，置于内容之后 */
.hero-phoenix{position:absolute;left:50%;top:82%;transform:translate(-50%,-50%);
  width:min(400px,62%);max-width:none;opacity:.38;z-index:0;pointer-events:none}
.hero-orn,.cover,.hero h1,.hero .subtitle,.chips{position:relative;z-index:1}
.hero-orn{width:min(720px,92%);display:block;margin:0 auto 6px;opacity:.95}
/* 装饰边框：multiply 让白底隐形、线条融入米白，并调成暖棕 */
.hero-orn,.flourish,footer img{filter:sepia(.45) saturate(1.4) hue-rotate(-18deg) brightness(.82);
  mix-blend-mode:multiply}
.cover{display:block;width:min(880px,94%);margin:10px auto 28px;border-radius:14px;
  border:2px solid var(--gold-dim);box-shadow:0 12px 44px rgba(0,0,0,.65);
  background:#fff;image-rendering:auto}
.hero h1{font-size:clamp(30px,5.4vw,52px);margin:14px 0 8px;letter-spacing:6px;
  color:var(--gold);text-shadow:0 1px 2px rgba(120,80,40,.25)}
.hero .subtitle{color:var(--muted);letter-spacing:3px;font-size:clamp(13px,2vw,17px)}
.chips{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:22px}
.chip{border:1px solid var(--gold-dim);color:var(--gold);border-radius:20px;
  padding:4px 16px;font-size:.88em;background:rgba(255,255,255,.5);letter-spacing:1px}

/* ---- 区块 ---- */
main section{padding:42px 0 10px}
.sec-head{text-align:center;margin-bottom:8px}
.sec-head h2{display:inline-block;font-size:clamp(22px,3.4vw,30px);
  letter-spacing:8px;color:var(--text);margin:0 0 4px;position:relative;
  padding:0 18px}
.sec-head h2::before,.sec-head h2::after{
  content:"❖";color:var(--ver);font-size:.6em;vertical-align:middle;margin:0 12px}
.flourish{width:min(560px,86%);display:block;margin:0 auto 26px;opacity:.9}
.note{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--gold);
  border-radius:8px;padding:14px 20px;color:var(--muted);font-size:.95em}
.note p{margin:6px 0}

/* ---- 表格 ---- */
.tbl-wrap{overflow-x:auto;margin:18px auto;max-width:820px}
table{width:100%;border-collapse:collapse;background:var(--panel);
  border:1px solid var(--line);border-radius:8px;overflow:hidden;font-size:.95em}
th{background:rgba(192,83,47,.12);color:var(--ver);letter-spacing:2px;
  padding:10px 14px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
td{padding:9px 14px;border-bottom:1px solid rgba(74,50,48,.5)}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(216,169,95,.05)}

/* ---- 角色卡 ---- */
.char-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
  gap:18px;margin-top:10px}
.char-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:20px 22px;transition:transform .2s,border-color .2s}
.char-card:hover{transform:translateY(-3px);border-color:var(--gold-dim)}
.char-head{display:flex;align-items:center;gap:14px;margin-bottom:12px}
.avatar{width:64px;height:64px;border-radius:10px;border:2px solid var(--gold-dim);
  box-shadow:0 0 12px rgba(0,0,0,.5)}
.avatar-ph{display:flex;align-items:center;justify-content:center;
  font-size:30px;color:var(--gold);background:var(--panel2)}
.char-card h3{margin:0;font-size:1.35em;letter-spacing:4px;color:var(--gold)}
.meta-row{display:flex;gap:8px;font-size:.92em;margin:5px 0;align-items:baseline}
.meta-ic{flex:none}
.meta-k{flex:none;color:var(--ver-b);letter-spacing:1px}
.meta-v{color:var(--text)}
.char-card>p{color:var(--muted);font-size:.92em;margin:10px 0 0;
  border-top:1px dashed var(--line);padding-top:10px}

/* ---- 路线 tab ---- */
.route-tabs{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin:22px 0 6px}
.rtab{display:flex;align-items:center;gap:8px;cursor:pointer;
  background:var(--panel);color:var(--muted);border:1px solid var(--line);
  border-radius:24px;padding:7px 18px 7px 10px;font-family:inherit;font-size:1em;
  letter-spacing:2px;transition:all .15s}
.rtab img{width:30px;height:30px;border-radius:7px;border:1px solid var(--gold-dim)}
.rtab .ph{width:30px;height:30px;border-radius:7px;display:flex;align-items:center;
  justify-content:center;background:var(--panel2);color:var(--gold);font-size:15px}
.rtab:hover{color:var(--text);border-color:var(--gold-dim)}
.rtab.active{background:var(--ver);border-color:var(--ver-b);color:#fff}
.rtab .cnt{font-size:.75em;opacity:.75;letter-spacing:0}
.route-panel{display:none;max-width:760px;margin:22px auto 0}
.route-panel.active{display:block;animation:fade .3s}
@keyframes fade{from{opacity:0;transform:translateY(8px)}to{opacity:1}}
.route-note{background:var(--panel);border:1px solid var(--line);
  border-left:3px solid var(--gold);border-radius:8px;padding:12px 18px;
  color:var(--muted);font-size:.93em;margin-bottom:16px}
.route-note p{margin:4px 0}

/* ---- 时间线 ---- */
.timeline{position:relative;padding-left:30px}
.timeline::before{content:"";position:absolute;left:9px;top:6px;bottom:6px;
  width:2px;background:linear-gradient(var(--gold-dim),var(--ver),var(--gold-dim))}
.step{position:relative;margin:0 0 8px;display:flex;gap:10px;align-items:baseline}
.step .num{flex:none;width:22px;height:22px;border-radius:50%;
  background:var(--panel2);border:1px solid var(--gold-dim);color:var(--gold);
  display:flex;align-items:center;justify-content:center;font-size:.75em;
  transform:translateY(4px)}
.step .txt{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:6px 16px;flex:1}
.step.loc{margin:16px 0 10px}
.step.loc .pin{position:absolute;left:-27px;color:var(--ver);font-size:.8em;
  transform:translateY(1px)}
.step.loc .loc-name{color:var(--gold);letter-spacing:3px;font-weight:bold;
  background:linear-gradient(90deg,rgba(212,87,78,.22),transparent);
  padding:4px 18px 4px 12px;border-radius:6px}
.step.warn .ic{position:absolute;left:-27px;color:#ffb347;font-size:.9em}
.step.warn span:last-child,.step.warn span:nth-child(2){
  background:rgba(255,179,71,.12);border:1px solid rgba(255,179,71,.45);
  border-radius:8px;padding:6px 16px;color:#ffd9a0;flex:1}
.step.spec .ic{position:absolute;left:-27px;color:var(--purple)}
.step.spec span:nth-child(2){background:rgba(179,156,209,.12);
  border:1px solid rgba(179,156,209,.4);border-radius:8px;padding:6px 16px;
  color:#d8c8ec;flex:1}
.step.ending{margin-top:14px}
.step.ending .cond{background:var(--panel);border:1px solid var(--line);
  border-radius:8px;padding:6px 16px;flex:1}
.step.ending .arr{color:var(--muted)}
.step.ending .badge{flex:none;border-radius:20px;padding:4px 16px;
  font-weight:bold;letter-spacing:1px}
.end-a .badge{background:rgba(179,156,209,.2);border:1px solid var(--purple);color:var(--purple)}
.end-b .badge{background:rgba(143,196,176,.2);border:1px solid var(--teal);color:var(--teal)}

/* ---- FAQ / 小贴士 ---- */
.faq{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:14px 20px;margin:10px auto;max-width:860px}
.faq .q{color:var(--ver-b);font-weight:bold;letter-spacing:1px;margin-bottom:4px}
.faq .q::before{content:"Q ";color:var(--gold)}
.faq li{color:var(--muted);font-size:.94em;margin:3px 0}
.tip-list{max-width:860px;margin:10px auto}
.tip-list li{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:9px 18px;margin:8px 0;list-style:none;color:var(--text);font-size:.95em}
.tip-list li::marker{color:var(--ver)}
ul{padding-left:0}
.plain-list{max-width:860px;margin:10px auto;padding-left:0;list-style:none}
.plain-list li{margin:6px 0}
.plain-list li::before{content:"· ";color:var(--ver);font-weight:bold}

/* ---- 页脚 ---- */
footer{position:relative;overflow:hidden;margin-top:60px;padding:30px 20px 44px;text-align:center;
  border-top:1px solid var(--line);color:var(--muted);font-size:.88em}
/* 页脚纯米白区的大朱雀，保证清晰显形 */
.foot-phoenix{position:absolute;left:50%;top:54%;transform:translate(-50%,-50%);
  width:min(400px,60%);max-width:none;opacity:.42;z-index:0;pointer-events:none}
footer img,footer p{position:relative;z-index:1}
footer img{width:min(560px,80%);opacity:.7;display:block;margin:0 auto 18px}
footer p{margin:6px 0}
/* 访问统计徽章：页脚正下方居中 */
#visitor{display:block;margin:-14px auto 30px;max-width:calc(100% - 40px);height:auto}

@media (max-width:640px){
  .char-grid{grid-template-columns:1fr}
  .hero h1{letter-spacing:3px}
  .timeline{padding-left:24px}
}
"""

JS = r"""
// 路线 tab 切换
document.querySelectorAll('.rtab').forEach(function(b){
  b.addEventListener('click',function(){
    document.querySelectorAll('.rtab').forEach(function(x){x.classList.remove('active')});
    document.querySelectorAll('.route-panel').forEach(function(x){x.classList.remove('active')});
    b.classList.add('active');
    var p=document.getElementById(b.dataset.r);
    if(p)p.classList.add('active');
  });
});
// 导航高亮
var links=[].slice.call(document.querySelectorAll('.nav-links a'));
var secs=links.map(function(a){return document.querySelector(a.getAttribute('href'))});
window.addEventListener('scroll',function(){
  var y=window.scrollY+120,cur=0;
  secs.forEach(function(s,i){if(s&&s.offsetTop<=y)cur=i});
  links.forEach(function(a,i){a.classList.toggle('active',i===cur)});
},{passive:true});
"""

PAGE = type("P", (), {"roots": []})()  # 路线名注册表


def build():
    global PAGE
    text = open(MD_PATH, encoding="utf-8").read()
    meta, body = parse_md(text)
    sections = split_sections(body)

    # 预扫描路线名（供 tab/panel id 使用）
    route_names = []
    for sec in sections:
        if sec["title"] == "路线攻略":
            for b in parse_blocks(sec["lines"]):
                if b[0] == "h2":
                    route_names.append(b[1])
    PAGE.roots = route_names

    css = CSS.replace("ASSET_BG", ASSET("suzaku.png"))

    # ---------- 各区块渲染 ----------
    rendered = []
    for si, sec in enumerate(sections):
        title = sec["title"]
        if title is None:
            continue  # front matter 后的首个空段
        blocks = parse_blocks(sec["lines"])
        inner = []

        if title == "朱雀七星士":
            cards = []
            for b in blocks:
                if b[0] == "h2":
                    # 收集该 h2 之后的块直到下一个 h2
                    pass
            # 重新按 h2 分组
            cur_name, cur_blocks = None, []
            groups = []
            for b in blocks:
                if b[0] == "h2":
                    if cur_name:
                        groups.append((cur_name, cur_blocks))
                    cur_name, cur_blocks = b[1], []
                else:
                    cur_blocks.append(b)
            if cur_name:
                groups.append((cur_name, cur_blocks))
            inner.append('<div class="char-grid">')
            inner += [char_card(n, bs) for n, bs in groups]
            inner.append("</div>")

        elif title == "路线攻略":
            intro = []
            routes = []  # (name, blocks)
            cur_name, cur_blocks = None, []
            for b in blocks:
                if b[0] == "h2":
                    if cur_name:
                        routes.append((cur_name, cur_blocks))
                    cur_name, cur_blocks = b[1], []
                elif cur_name is None:
                    intro.append(b)
                else:
                    cur_blocks.append(b)
            if cur_name:
                routes.append((cur_name, cur_blocks))
            if intro:
                ih = "".join(f"<p>{inline(b[1])}</p>" for b in intro
                             if b[0] == "para")
                for b in intro:
                    if b[0] == "quote":
                        ih += "".join(f"<p>{inline(x)}</p>" for x in b[1])
                inner.append(f'<div class="note">{ih}</div>')
            tabs = []
            for ri, (rn, rb) in enumerate(routes):
                img = os.path.join(HERE, "assets", rn + ".png")
                tab_icon = (f'<img src="{ASSET(rn + ".png")}" alt="">'
                            if os.path.exists(img)
                            else '<span class="ph">✦</span>')
                _, count = route_panel(rn, rb)  # 复用计数（再生成一次无妨）
                tabs.append(f'<button class="rtab{" active" if ri==0 else ""}" '
                            f'data-r="r{ri}">{tab_icon}{esc(rn)}'
                            f'<span class="cnt">{count}步</span></button>')
            inner.append('<div class="route-tabs">' + "".join(tabs) + "</div>")
            for ri, (rn, rb) in enumerate(routes):
                ph, _ = route_panel(rn, rb)
                act = " active" if ri == 0 else ""
                inner.append(ph.replace('class="route-panel"',
                                        f'class="route-panel{act}"', 1))

        elif title == "Q&A":
            for b in blocks:
                if b[0] == "list":
                    for it in b[1]:
                        subs = "".join(f"<li>{inline(s)}</li>" for s in it["subs"])
                        inner.append(f'<div class="faq"><div class="q">'
                                     f'{inline(it["text"])}</div>'
                                     f'<ul>{subs}</ul></div>')
                elif b[0] == "para":
                    inner.append(f"<p>{inline(b[1])}</p>")

        else:  # 通用渲染
            for b in blocks:
                k = b[0]
                if k == "table":
                    inner.append(render_table(b[1]))
                elif k == "quote":
                    inner.append('<div class="note">'
                                 + "".join(f"<p>{inline(x)}</p>" for x in b[1])
                                 + "</div>")
                elif k == "list":
                    inner.append('<ul class="tip-list">'
                                 + "".join(f'<li>{inline(it["text"])}'
                                           + ("".join(f"<br><span style='color:var(--muted)'>└ {inline(s)}</span>"
                                                      for s in it["subs"]))
                                           + "</li>" for it in b[1])
                                 + "</ul>")
                elif k == "para":
                    inner.append(f"<p style='text-align:center'>{inline(b[1])}</p>")
                elif k == "h3":
                    inner.append(f"<h3 style='color:var(--gold);letter-spacing:3px'>{inline(b[1])}</h3>")

        # 尾部 hr 之后的内容 → 页脚
        footer_html = ""
        fblocks = [b for b in blocks if b[0] == "hr"]
        if fblocks:
            hi = next(i for i, b in enumerate(blocks) if b[0] == "hr")
            if si == len(sections) - 1 and hi > len(blocks) - 3:
                pass  # 处理在下方统一做
        rendered.append((si, title, "".join(inner)))

    # 组装主体 HTML
    main_html = []
    for si, title, inner in rendered:
        if not inner.strip():
            continue
        main_html.append(
            f'<section id="sec-{si}"><div class="sec-head"><h2>{esc(title)}</h2></div>'
            f'<img class="flourish" src="{ASSET("border_top.png")}" alt="">'
            f'<div class="wrap">{inner}</div></section>')

    # 页脚：取最后一个区块中 hr 之后的段落
    last = sections[-1]
    fb = parse_blocks(last["lines"])
    hr_seen = False
    foot_ps = []
    for b in fb:
        if b[0] == "hr":
            hr_seen = True
            continue
        if hr_seen and b[0] == "para":
            foot_ps.append(f"<p>{inline(b[1])}</p>")

    nav = "".join(f'<a href="#sec-{si}">{esc(t)}</a>' for si, t, _ in rendered)
    cover_name = meta.get("cover", "opening.jpg").strip()
    cover_html = ""
    if cover_name and os.path.exists(os.path.join(HERE, "assets", cover_name)):
        cover_html = (f'<img class="cover" src="{ASSET(cover_name)}" '
                      f'alt="{esc(meta.get("title", ""))}">')

    chips = (f'<span class="chip">{esc(meta.get("platform","PlayStation 2"))}</span>'
             f'<span class="chip">{esc(meta.get("release","2008.05.31"))}</span>'
             f'<span class="chip">女性向恋爱 ADV</span>'
             f'<span class="chip">CERO 12+</span>')

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(meta.get("title", "攻略"))}</title>
<style>{css}</style>
</head>
<body>
<nav id="topnav"><div class="nav-inner">
<a class="brand" href="#top">朱雀異聞·攻略</a>
<div class="nav-links">{nav}</div>
<a class="genbu" href="https://www.bilibili.com/toy/fushigi_genbu_guide/index.html" target="_blank" rel="noopener">玄武開傳·攻略 →</a>
</div></nav>
<header class="hero" id="top">
<img class="hero-phoenix" src="{ASSET("suzaku.png")}" alt="">
<img class="hero-orn" src="{ASSET("border_top.png")}" alt="">
{cover_html}
<h1>{esc(meta.get("title", ""))}</h1>
<p class="subtitle">{esc(meta.get("subtitle", ""))}</p>
<div class="chips">{chips}</div>
</header>
<main>{"".join(main_html)}</main>
<footer>
<img class="foot-phoenix" src="{ASSET("suzaku.png")}" alt="">
<img src="{ASSET("border_top.png")}" alt="">
{"".join(foot_ps)}
</footer>
<img id="visitor" src="https://visitor-badge.laobi.icu/badge?page_id=fushigisuzaku.visitor-badge&amp;left_text=dear%20friends&amp;left_color=%23ea8a8a&amp;right_color=%23b1d6ec" alt="访问统计">
<script>{JS}</script>
</body>
</html>"""

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(page)
    n_routes = len(route_names)
    print(f"✔ 生成完成: {OUT_PATH}")
    print(f"  区块 {len(main_html)} 个 | 路线 {n_routes} 条")


if __name__ == "__main__":
    build()
