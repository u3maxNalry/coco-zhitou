"""
coco智投 · Web API 服务
========================
启动: python web_app.py
访问: http://localhost:8000
文档: http://localhost:8000/docs
"""

import json
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from agent import (
    ZhiTouAgent, AgentConfig, parse_input, generate_sample_data, DecisionContext
)

app = FastAPI(
    title="coco智投 · 多因子量化投资智能体",
    description="动量 + 资金流 + 质量 三因子综合评分模型",
    version="1.0.0",
)


@app.get("/", response_class=HTMLResponse)
async def index():
    """前端页面"""
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>coco智投 · 多因子量化投资智能体</title>
<style>
  :root {
    --bg: #0a1f3d; --card: #0f2b52; --text: #e4e8ec;
    --accent: #6db3f2; --border: rgba(255,255,255,.08);
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); min-height:100vh; }
  .container { max-width: 900px; margin:0 auto; padding: 2rem 1.5rem; }
  header { text-align:center; padding:2rem 0; }
  header h1 { font-size:2.2rem; font-weight:800; background: linear-gradient(135deg, var(--accent), #a78bfa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
  header p { margin-top:.5rem; opacity:.6; font-size:.95rem; }
  .controls { display:flex; gap:1rem; margin:2rem 0; flex-wrap:wrap; justify-content:center; }
  button, select { padding:.7rem 1.5rem; border-radius:8px; border:none; font-size:1rem; cursor:pointer; transition:.2s; }
  .btn-primary { background: var(--accent); color:var(--bg); font-weight:600; }
  .btn-primary:hover { transform: translateY(-1px); box-shadow:0 4px 20px rgba(109,179,242,.3); }
  .btn-outline { background:transparent; border:1px solid var(--border); color:var(--text); }
  .btn-outline:hover { background:rgba(255,255,255,.05); }
  .btn-tech { background: linear-gradient(135deg, #f59e0b, #ef4444); color:#fff; font-weight:600; }
  .result { background: var(--card); border-radius:12px; padding:1.5rem; border:1px solid var(--border); }
  .result h2 { font-size:1.1rem; margin-bottom:1rem; opacity:.7; }
  table { width:100%; border-collapse:collapse; }
  th, td { padding:.8rem .6rem; text-align:left; border-bottom:1px solid var(--border); font-size:.95rem; }
  th { opacity:.5; font-weight:500; font-size:.85rem; text-transform:uppercase; letter-spacing:.05em; }
  .tag { display:inline-block; padding:.2rem .6rem; border-radius:4px; font-size:.75rem; font-weight:600; }
  .tag-tech { background:rgba(245,158,11,.15); color:#f59e0b; }
  .tag-main { background:rgba(109,179,242,.15); color:var(--accent); }
  .log-box { background:rgba(0,0,0,.3); border-radius:8px; padding:1rem; margin-top:1rem; font-family:monospace; font-size:.8rem; line-height:1.6; max-height:300px; overflow-y:auto; color:rgba(255,255,255,.6); }
  .loading { text-align:center; padding:2rem; opacity:.5; }
  .summary { display:flex; gap:1.5rem; flex-wrap:wrap; margin-bottom:1.5rem; }
  .summary-item { background:rgba(255,255,255,.03); border-radius:8px; padding:1rem; min-width:120px; }
  .summary-item .label { font-size:.75rem; opacity:.5; margin-bottom:.3rem; }
  .summary-item .value { font-size:1.4rem; font-weight:700; }
  .error { background:rgba(239,68,68,.1); border:1px solid rgba(239,68,68,.2); color:#fca5a5; border-radius:8px; padding:1rem; }
  footer { text-align:center; padding:2rem; opacity:.3; font-size:.8rem; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>coco智投</h1>
    <p>多因子量化投资智能体 · 动量(40%) + 资金流(35%) + 质量(25%)</p>
  </header>

  <div class="controls">
    <button class="btn-primary" onclick="run('sample')">🚀 运行全市场分析</button>
    <button class="btn-tech" onclick="run('tech')">⚡ 科技赛道聚焦</button>
    <button class="btn-outline" onclick="run('json')">📋 查看原始 JSON</button>
  </div>

  <div id="output"></div>
</div>
<footer>coco智投 · 基于 AI4Value 竞赛框架 | 仅供研究参考，不构成投资建议</footer>

<script>
async function run(mode) {
  const out = document.getElementById('output');
  out.innerHTML = '<div class="loading">⏳ coco智投正在分析中...</div>';

  try {
    const params = mode === 'tech' ? '?tech=true&verbose=true' : (mode === 'json' ? '?verbose=false' : '?verbose=true');
    const resp = await fetch('/api/decide' + params);
    const data = await resp.json();

    if (data.error) {
      out.innerHTML = `<div class="error">❌ ${data.error}</div>`;
      return;
    }

    const isTech = mode === 'tech';
    let html = `<div class="result">
      <h2>📊 ${isTech ? '科技赛道聚焦 · ' : '全市场 · '}投资建议</h2>
      <div class="summary">
        <div class="summary-item"><div class="label">推荐标的</div><div class="value">${data.recommendations.length} 只</div></div>
        <div class="summary-item"><div class="label">可用资金</div><div class="value">¥50万</div></div>
        <div class="summary-item"><div class="label">日期</div><div class="value">${data.date}</div></div>
        <div class="summary-item"><div class="label">模式</div><div class="value">${isTech ? '🔬 科技' : '📈 全市场'}</div></div>
      </div>`;

    if (data.recommendations.length > 0) {
      html += `<table>
        <tr><th>#</th><th>标的</th><th>代码</th><th>股数</th><th>赛道</th></tr>`;
      data.recommendations.forEach((r, i) => {
        const isT = ['300','688'].some(p => r.symbol.startsWith(p)) || ['电子','科技','光电','半导体','芯片','软件','数据','智能','机器人','新能源','光伏','锂电','储能','电池','通信','信息','生物','医药'].some(k => r.symbol_name.includes(k));
        html += `<tr>
          <td>${i+1}</td>
          <td><strong>${r.symbol_name}</strong></td>
          <td style="font-family:monospace">${r.symbol}</td>
          <td>${r.volume.toLocaleString()}</td>
          <td><span class="tag ${isT ? 'tag-tech' : 'tag-main'}">${isT ? '科技' : '综合'}</span></td>
        </tr>`;
      });
      html += '</table>';
    } else {
      html += '<p style="opacity:.5;text-align:center;padding:2rem">当日无符合条件的投资建议（市场风险过高或候选不足）</p>';
    }

    if (data.log && mode !== 'json') {
      html += `<details style="margin-top:1rem"><summary style="cursor:pointer;opacity:.5;font-size:.85rem">📋 决策日志</summary>
        <div class="log-box">${data.log.replace(/\n/g, '<br>')}</div></details>`;
    }

    html += '</div>';
    out.innerHTML = html;
  } catch (e) {
    out.innerHTML = `<div class="error">❌ 请求失败: ${e.message}</div>`;
  }
}
</script>
</body>
</html>
""")


@app.get("/api/decide")
async def decide(
    tech: bool = Query(False, description="聚焦科技赛道"),
    verbose: bool = Query(True, description="是否返回决策日志"),
    date: str = Query("2026-05-13", description="决策日期"),
    capital: float = Query(500000, description="总资金"),
):
    """
    coco智投核心 API：提交决策请求，返回投资建议
    """
    try:
        data = generate_sample_data()
        data["date"] = date
        data["total_capital"] = capital

        context = parse_input(data)
        config = AgentConfig(tech_focus=tech, tech_only=tech)
        agent = ZhiTouAgent(config=config)

        recommendations, log = agent.decide(context)

        return {
            "date": date,
            "total_capital": capital,
            "mode": "科技聚焦" if tech else "全市场",
            "recommendations": [
                {
                    "symbol": r.symbol,
                    "symbol_name": r.symbol_name,
                    "volume": r.volume,
                }
                for r in recommendations
            ],
            "count": len(recommendations),
            "log": log if verbose else None,
        }
    except Exception as e:
        return {"error": str(e), "recommendations": []}


@app.get("/api/health")
async def health():
    return {"status": "ok", "agent": "coco智投", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  coco智投 · Web 服务启动中...")
    print("  前端: http://localhost:8000")
    print("  API文档: http://localhost:8000/docs")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
