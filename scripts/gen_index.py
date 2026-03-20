"""
自动扫描 work/ 目录下所有 .html 文件，生成 work/index.html 索引页。
用法：python3 scripts/gen_index.py
"""
import os, json, re
from pathlib import Path

ROOT = Path(__file__).parent.parent / "work"
OUT  = ROOT / "index.html"

TAG_RULES = {
    "survey":  ["survey", "paper", "caption", "literature"],
    "bench":   ["bench", "eval", "metric", "score", "leaderboard"],
    "data":    ["data", "dataset", "corpus", "sft", "dpo"],
    "model":   ["model", "ckpt", "checkpoint", "train", "finetune"],
}

def guess_tag(name: str) -> str:
    n = name.lower()
    for tag, keywords in TAG_RULES.items():
        if any(k in n for k in keywords):
            return tag
    return "other"

def nice_title(name: str) -> str:
    stem = name.replace(".html", "")
    stem = re.sub(r"^exp\d+_", "", stem)          # 去掉 exp89_ 前缀
    stem = stem.replace("_", " ").replace("-", " ")
    return stem.title()

def scan_files():
    files = []
    for html in sorted(ROOT.rglob("*.html")):
        if html.name == "index.html" and html.parent == ROOT:
            continue                               # 跳过自身
        rel = html.relative_to(ROOT)
        parts = rel.parts
        exp = parts[0] if len(parts) > 1 else "root"
        files.append({
            "exp":   exp,
            "name":  html.name,
            "title": nice_title(html.name),
            "path":  str(rel).replace("\\", "/"),
            "tag":   guess_tag(html.name),
        })
    return files

FILES = scan_files()
EXPS  = sorted(set(f["exp"] for f in FILES))

# 过滤按钮（只显示出现过的 exp）
filter_btns_html = '<button class="filter-btn active" data-filter="all">全部</button>\n'
for exp in EXPS:
    filter_btns_html += f'    <button class="filter-btn" data-filter="{exp}">{exp}</button>\n'

FILES_JSON = json.dumps(FILES, ensure_ascii=False, indent=2)

HTML = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AwesomeSkill — 实验索引</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif; background: #0d1117; color: #c9d1d9; min-height: 100vh; }}
.header {{ background: linear-gradient(135deg, #0d1117 0%, #161b22 40%, #1a2332 100%); border-bottom: 1px solid #30363d; padding: 40px 48px 32px; position: relative; overflow: hidden; }}
.header::before {{ content: ''; position: absolute; top: -60px; right: -60px; width: 300px; height: 300px; background: radial-gradient(circle, rgba(88,166,255,0.08) 0%, transparent 70%); pointer-events: none; }}
.header h1 {{ font-size: 32px; font-weight: 700; color: #f0f6fc; margin-bottom: 8px; letter-spacing: -0.5px; }}
.header h1 span {{ color: #58a6ff; }}
.header p {{ color: #8b949e; font-size: 15px; }}
.header .stats {{ display: flex; gap: 32px; margin-top: 20px; }}
.header .stat {{ display: flex; flex-direction: column; }}
.header .stat .num {{ font-size: 24px; font-weight: 700; color: #58a6ff; }}
.header .stat .lbl {{ font-size: 12px; color: #8b949e; margin-top: 2px; }}
.toolbar {{ padding: 16px 48px; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #21262d; background: #0d1117; position: sticky; top: 0; z-index: 10; flex-wrap: wrap; }}
.search-box {{ flex: 1; max-width: 360px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 8px 14px; color: #c9d1d9; font-size: 14px; outline: none; }}
.search-box:focus {{ border-color: #58a6ff; }}
.search-box::placeholder {{ color: #484f58; }}
.filter-btns {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.filter-btn {{ padding: 6px 14px; border-radius: 20px; font-size: 13px; cursor: pointer; border: 1px solid #30363d; background: #161b22; color: #8b949e; transition: all 0.15s; }}
.filter-btn:hover, .filter-btn.active {{ background: #1f6feb; border-color: #1f6feb; color: #fff; }}
.count-badge {{ margin-left: auto; font-size: 13px; color: #8b949e; }}
.container {{ max-width: 1280px; margin: 0 auto; padding: 32px 48px; }}
.group {{ margin-bottom: 40px; }}
.group-title {{ font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: #8b949e; margin-bottom: 16px; display: flex; align-items: center; gap: 10px; }}
.group-title::after {{ content: ''; flex: 1; height: 1px; background: #21262d; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; cursor: pointer; transition: all 0.2s; text-decoration: none; display: block; position: relative; overflow: hidden; }}
.card::before {{ content: ''; position: absolute; inset: 0; opacity: 0; background: linear-gradient(135deg, rgba(88,166,255,0.05), transparent); transition: opacity 0.2s; }}
.card:hover {{ border-color: #58a6ff; transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.4); }}
.card:hover::before {{ opacity: 1; }}
.card-exp {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; color: #58a6ff; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }}
.card-exp .dot {{ width: 6px; height: 6px; border-radius: 50%; background: #58a6ff; }}
.card-title {{ font-size: 15px; font-weight: 600; color: #f0f6fc; margin-bottom: 6px; line-height: 1.4; }}
.card-path {{ font-size: 12px; color: #484f58; font-family: 'SF Mono', monospace; margin-bottom: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.card-footer {{ display: flex; align-items: center; justify-content: space-between; }}
.card-tag {{ display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }}
.tag-survey {{ background: rgba(88,166,255,0.15); color: #58a6ff; }}
.tag-bench  {{ background: rgba(63,185,80,0.15);  color: #3fb950; }}
.tag-data   {{ background: rgba(255,166,87,0.15);  color: #ffa657; }}
.tag-model  {{ background: rgba(188,140,255,0.15); color: #bc8cff; }}
.tag-other  {{ background: rgba(139,148,158,0.15); color: #8b949e; }}
.card-arrow {{ color: #484f58; font-size: 16px; transition: transform 0.2s; }}
.card:hover .card-arrow {{ color: #58a6ff; transform: translateX(4px); }}
.empty {{ text-align: center; padding: 80px 0; color: #484f58; }}
.empty .icon {{ font-size: 48px; margin-bottom: 16px; }}
footer {{ text-align: center; padding: 32px; color: #484f58; font-size: 13px; border-top: 1px solid #21262d; margin-top: 40px; }}
footer a {{ color: #58a6ff; text-decoration: none; }}
.hidden {{ display: none !important; }}
</style>
</head>
<body>
<div class="header">
  <h1>Awesome<span>Skill</span> · 实验索引</h1>
  <p>所有实验的 HTML 可视化报告，点击卡片直接访问 &nbsp;·&nbsp; 由 <code>scripts/gen_index.py</code> 自动生成</p>
  <div class="stats">
    <div class="stat"><span class="num" id="total-count">{len(FILES)}</span><span class="lbl">HTML 文件</span></div>
    <div class="stat"><span class="num" id="exp-count">{len(EXPS)}</span><span class="lbl">实验目录</span></div>
  </div>
</div>

<div class="toolbar">
  <input class="search-box" type="text" placeholder="搜索文件名或实验..." id="search-input" />
  <div class="filter-btns" id="filter-btns">
    {filter_btns_html}  </div>
  <span class="count-badge" id="count-badge">共 {len(FILES)} 个文件</span>
</div>

<div class="container">
  <div id="groups-container"></div>
  <div class="empty hidden" id="empty-state">
    <div class="icon">🔍</div>
    <p>没有找到匹配的文件</p>
  </div>
</div>

<footer>
  <a href="https://github.com/linjh1118/AwesomeSkill" target="_blank">GitHub · linjh1118/AwesomeSkill</a>
  &nbsp;·&nbsp; 自动索引所有 HTML 可视化文件
</footer>

<script>
const FILES = {FILES_JSON};
const TAG_LABELS = {{ survey: 'Survey', bench: 'Benchmark', data: 'Dataset', model: 'Model', other: 'Other' }};

function buildCards(files) {{
  return files.map(f => `
    <a class="card" href="${{f.path}}" target="_blank">
      <div class="card-exp"><span class="dot"></span>${{f.exp}}</div>
      <div class="card-title">${{f.title}}</div>
      <div class="card-path">${{f.path}}</div>
      <div class="card-footer">
        <span class="card-tag tag-${{f.tag}}">${{TAG_LABELS[f.tag] || f.tag}}</span>
        <span class="card-arrow">→</span>
      </div>
    </a>
  `).join('');
}}

function groupByExp(files) {{
  const g = {{}};
  files.forEach(f => {{ if (!g[f.exp]) g[f.exp] = []; g[f.exp].push(f); }});
  return g;
}}

function render(files) {{
  const container = document.getElementById('groups-container');
  const empty = document.getElementById('empty-state');
  document.getElementById('count-badge').textContent = `共 ${{files.length}} 个文件`;
  if (!files.length) {{ container.innerHTML = ''; empty.classList.remove('hidden'); return; }}
  empty.classList.add('hidden');
  const groups = groupByExp(files);
  container.innerHTML = Object.entries(groups).map(([exp, fs]) => `
    <div class="group">
      <div class="group-title">${{exp}} <span style="color:#484f58;font-size:12px;font-weight:400;text-transform:none;letter-spacing:0">${{fs.length}} 个文件</span></div>
      <div class="grid">${{buildCards(fs)}}</div>
    </div>
  `).join('');
}}

render(FILES);

let currentFilter = 'all';
const searchInput = document.getElementById('search-input');
function applyFilters() {{
  const q = searchInput.value.toLowerCase().trim();
  let result = FILES;
  if (currentFilter !== 'all') result = result.filter(f => f.exp === currentFilter);
  if (q) result = result.filter(f => f.name.toLowerCase().includes(q) || f.exp.toLowerCase().includes(q) || f.title.toLowerCase().includes(q));
  render(result);
}}
searchInput.addEventListener('input', applyFilters);
document.getElementById('filter-btns').addEventListener('click', e => {{
  const btn = e.target.closest('.filter-btn');
  if (!btn) return;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentFilter = btn.dataset.filter;
  applyFilters();
}});
</script>
</body>
</html>"""

OUT.write_text(HTML, encoding="utf-8")
print(f"✅ 生成完成：{OUT}")
print(f"   {len(FILES)} 个 HTML 文件，{len(EXPS)} 个实验目录")
for f in FILES:
    print(f"   [{f['tag']:6}] {f['path']}")
