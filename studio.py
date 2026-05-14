#!/usr/bin/env python3
"""
studio.py — KarmazynOS Studio v1.0.0
=====================================
Lokalny serwer HTTP + WebSocket jako środowisko rozwoju KarmazynOS.
Przeglądarka jako renderer — działa wszędzie (Termux, NUC, Chromebook).

Uruchomienie:
    python studio.py [--port 8080] [--host 127.0.0.1]

Następnie otwórz: http://localhost:8080
Na Termux:        termux-open-url http://localhost:8080
"""

import os
import sys
import json
import time
import threading
import subprocess
import traceback
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import io

try:
    from karmazyn import KarmazynOS, VERSION as KARM_VERSION
except ImportError:
    print("Błąd: nie znaleziono karmazyn.py")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("Błąd: brak numpy")
    sys.exit(1)

STUDIO_VERSION = "1.1.0"

# ─── Katalog static ───────────────────────────────────────────────────────────
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# ─── Globalny stan ────────────────────────────────────────────────────────────

_ko = KarmazynOS()
_lock = threading.Lock()
_stdout_lock = threading.Lock() # Lock dla synchronizacji przechwytywania stdout
_exec_log: list = []          # historia exec() w środowisku KarmazynOS
_media_store: dict = {}       # label → {type, data, mime}


# ─── Exec w kontekście KarmazynOS ─────────────────────────────────────────────

def karmazyn_exec(code: str) -> dict:
    """
    Wykonuje kod Python w kontekście KarmazynOS.
    System może modyfikować samego siebie przez ten interfejs.
    """
    env = {
        "ko":      _ko,
        "phi":     _ko.phi,
        "bubbles": _ko.bubbles,
        "np":      np,
        "os":      os,
        "sys":     sys,
        "__name__": "__karmazyn__",
    }
    out_buf = io.StringIO()
    import builtins
    old_print = builtins.print

    captured = []
    def capture_print(*args, **kwargs):
        text = " ".join(str(a) for a in args)
        captured.append(text)
        old_print(*args, **kwargs)

    builtins.print = capture_print
    result = {"ok": False, "output": "", "error": "", "result": None}
    try:
        exec(compile(code, "<karmazyn_studio>", "exec"), env)
        result["ok"] = True
        result["output"] = "\n".join(captured)
        # jeśli ostatnia linia to wyrażenie — eval jej
        lines = [l for l in code.strip().splitlines() if l.strip()]
        if lines:
            try:
                val = eval(compile(lines[-1], "<karmazyn_expr>", "eval"), env)
                if val is not None:
                    result["result"] = repr(val)
            except:
                pass
    except Exception as e:
        result["error"] = traceback.format_exc()
        result["output"] = "\n".join(captured)
    finally:
        builtins.print = old_print

    _exec_log.append({
        "ts":     time.time(),
        "code":   code[:200],
        "ok":     result["ok"],
        "output": result["output"][:500],
    })
    return result


# ─── API handlers ─────────────────────────────────────────────────────────────

def api_stats() -> dict:
    with _lock:
        s = _ko.stats()
        atoms = [{"label": a["label"][:40], "T": round(a["T"], 3)}
                 for a in sorted(_ko.phi._mx.atoms, key=lambda x: -x["T"])[:20]]
        bubbles = [{"label": b.label[:40],
                    "liv":   round(b.liveliness(_ko.phi.epoch), 3),
                    "rc":    b.recall_count}
                   for b in sorted(_ko.bubbles.all_active,
                                   key=lambda b: b.liveliness(_ko.phi.epoch),
                                   reverse=True)[:20]]
        holograms = [{"id": hid[:40], "topic": h.topic,
                      "liv": round(h.liveliness(_ko.phi.epoch), 3)}
                     for hid, h in _ko.holograms.items()]
        return {**s, "atoms_list": atoms,
                "bubbles_list": bubbles, "holograms_list": holograms}

def api_write(content: str) -> dict:
    with _lock:
        label = _ko.write(content)
        return {"label": label, "epoch": _ko.phi.epoch}

def api_recall(query: str, k: int = 5) -> dict:
    with _lock:
        results = _ko.recall(query, k=k)
        return {"results": results}

def api_consolidate(label: str) -> dict:
    with _lock:
        bid = _ko.consolidate(label)
        return {"bubble_id": bid}

def api_step(n: int = 1) -> dict:
    with _lock:
        s = _ko.step(n)
        return s

def api_exec(code: str) -> dict:
    with _lock:
        return karmazyn_exec(code)

def api_shell(cmdline: str) -> dict:
    """Uruchamia komendę w bezpiecznym shellu KarmazynOS."""
    import concurrent.futures

    def run_cmd():
        try:
            from shell import process_command
            from contextlib import redirect_stdout, redirect_stderr
            import io

            out_f = io.StringIO()
            err_f = io.StringIO()
            # Używamy globalnego _stdout_lock zdefiniowanego na poziomie modułu
            with _stdout_lock:
                with redirect_stdout(out_f), redirect_stderr(err_f):
                    res = process_command(cmdline)
                    if res:
                        print(res)
            return {"ok": True, "output": out_f.getvalue(), "error": err_f.getvalue()}
        except Exception as e:
            return {"ok": False, "output": "", "error": str(e)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_cmd)
        try:
            return future.result(timeout=30)
        except concurrent.futures.TimeoutError:
            return {"ok": False, "output": "", "error": "Command timed out (30s)"}
        except Exception as e:
            return {"ok": False, "output": "", "error": str(e)}

def api_save(path: str = "./karmazyn_data") -> dict:
    with _lock:
        _ko.save(path)
        return {"ok": True, "path": path}

def api_load(path: str = "./karmazyn_data") -> dict:
    with _lock:
        ok = _ko.load(path)
        return {"ok": ok, "path": path}

def api_exec_log() -> dict:
    return {"log": _exec_log[-50:]}


# ─── HTML/CSS/JS (interfejs) ──────────────────────────────────────────────────

STUDIO_HTML = r"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KarmazynOS Studio</title>
<link rel="stylesheet" href="/static/karmazyn.css">
<script src="/static/karmazyn_tokens.js"></script>
<style>
  /* ── Studio layout — specyficzny dla Studio, nie w Design Language ── */

  body {
    font-family: var(--font-mono);
    font-size: 13px;
    height: 100vh;
    overflow: hidden;
    display: grid;
    grid-template-rows: 48px 1fr;
    grid-template-columns: 280px 1fr 300px;
    grid-template-areas:
      "header header header"
      "left   main   right";
  }

  header {
    grid-area: header;
    background: var(--entropy-surface);
    border-bottom: 1px solid var(--phi-core);
    display: flex;
    align-items: center;
    padding: 0 20px;
    gap: 20px;
  }
  header h1 {
    font-family: var(--font-display);
    font-size: 28px;
    color: var(--phi-bright);
    letter-spacing: 3px;
  }
  header h1 span { color: var(--phi-thermal); }
  .header-stats {
    display: flex; gap: 16px; margin-left: auto;
    font-size: 11px; color: var(--type-secondary);
  }
  .header-stats b { color: var(--phi-ember); }
  .pulse {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--phi-bright);
    animation: phi-pulse var(--dur-pulse) infinite;
  }

  .panel {
    background: var(--entropy-surface);
    border-right: 1px solid var(--entropy-border);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .panel-title {
    font-family: var(--font-display);
    font-size: 16px;
    color: var(--phi-core);
    letter-spacing: 2px;
    padding: 12px 14px 8px;
    border-bottom: 1px solid var(--entropy-border);
    position: sticky; top: 0;
    background: var(--entropy-surface);
    z-index: 1;
  }

  #panel-left { grid-area: left; }
  .atom-item {
    padding: 6px 14px;
    border-bottom: 1px solid var(--entropy-bg);
    cursor: pointer;
    transition: background var(--dur-fast) var(--ease-phi);
    display: flex; align-items: center; gap: 8px;
  }
  .atom-item:hover { background: var(--entropy-raised); }
  .atom-label {
    flex: 1; color: var(--type-primary);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .temp-bar {
    width: 40px; height: 6px;
    background: var(--entropy-raised);
    border-radius: var(--radius-sm);
    overflow: hidden; flex-shrink: 0;
  }
  .temp-fill {
    height: 100%;
    border-radius: var(--radius-sm);
    transition: width var(--dur-slow) var(--ease-phi),
                background var(--dur-slow) var(--ease-phi);
  }
  .tab-bar {
    display: flex;
    border-bottom: 1px solid var(--entropy-border);
    background: var(--entropy-surface);
  }
  .tab {
    padding: 7px 14px;
    cursor: pointer;
    color: var(--type-secondary);
    font-size: 11px; letter-spacing: 1px;
    border-bottom: 2px solid transparent;
    transition: all var(--dur-mid) var(--ease-phi);
  }
  .tab.active { color: var(--phi-ember); border-bottom-color: var(--phi-bright); }

  #panel-main {
    grid-area: main;
    display: grid;
    grid-template-rows: 1fr 1fr;
    background: var(--entropy-bg);
  }
  .editor-area {
    display: flex; flex-direction: column;
    border-bottom: 2px solid var(--phi-core);
  }
  .editor-toolbar {
    display: flex; align-items: center; gap: 8px;
    padding: 6px 12px;
    background: var(--entropy-surface);
    border-bottom: 1px solid var(--entropy-border);
  }
  .editor-mode {
    font-size: 10px; letter-spacing: 2px;
    color: var(--type-secondary);
  }
  .btn {
    padding: 4px 12px;
    background: transparent;
    border: 1px solid var(--phi-core);
    color: var(--phi-ember);
    font-family: var(--font-mono);
    font-size: 11px; cursor: pointer; letter-spacing: 1px;
    transition: all var(--dur-fast) var(--ease-phi);
  }
  .btn:hover { background: var(--phi-core); color: var(--type-primary); }
  .btn.gold { border-color: var(--phi-thermal); color: var(--phi-thermal); }
  .btn.gold:hover { background: var(--phi-thermal); color: var(--entropy-void); }

  #editor {
    flex: 1;
    background: var(--entropy-bg);
    color: var(--type-primary);
    font-family: var(--font-mono);
    font-size: 13px;
    border: none; outline: none;
    padding: 14px; resize: none;
    line-height: 1.6; tab-size: 4;
  }
  #editor::placeholder { color: var(--type-muted); }

  .output-area { display: flex; flex-direction: column; overflow: hidden; }
  .output-header {
    padding: 6px 14px;
    background: var(--entropy-surface);
    border-bottom: 1px solid var(--entropy-border);
    font-size: 11px; color: var(--type-secondary);
    letter-spacing: 1px;
    display: flex; align-items: center; gap: 10px;
  }
  #output {
    flex: 1; overflow-y: auto;
    padding: 12px 14px;
    font-size: 12px; line-height: 1.7;
  }
  .out-ok     { color: var(--phi-stable); }
  .out-err    { color: var(--phi-ember); }
  .out-info   { color: var(--type-secondary); }
  .out-result { color: var(--phi-thermal); }

  #panel-right {
    grid-area: right;
    border-right: none;
    border-left: 1px solid var(--entropy-border);
  }
  .bubble-item {
    padding: 6px 14px;
    border-bottom: 1px solid var(--entropy-bg);
    cursor: pointer;
  }
  .bubble-item:hover { background: var(--entropy-raised); }
  .bubble-label { color: var(--type-primary); font-size: 12px; }
  .bubble-meta  { color: var(--type-secondary); font-size: 10px; margin-top: 2px; }
  .liv-dot {
    display: inline-block;
    width: 6px; height: 6px;
    border-radius: 50%; margin-right: 4px;
  }

  #media-canvas {
    width: 100%; aspect-ratio: 16/9;
    background: var(--entropy-void); display: block;
  }

  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: var(--entropy-bg); }
  ::-webkit-scrollbar-thumb { background: var(--phi-core); border-radius: 2px; }

  .shell-row {
    display: flex; align-items: center;
    padding: 6px 12px;
    border-top: 1px solid var(--phi-core);
    background: var(--entropy-surface);
    gap: 8px;
  }
  .shell-prompt { color: var(--phi-bright); font-size: 12px; }
  #shell-input {
    flex: 1; background: transparent;
    border: none; outline: none;
    color: var(--type-primary);
    font-family: var(--font-mono); font-size: 12px;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .fade-in { animation: fadeIn var(--dur-mid) var(--ease-enter); }

  #phi-canvas {
    width: 100%; height: 140px;
    display: block; cursor: crosshair;
  }
</style>
</head>

<body>

<header>
  <div class="pulse"></div>
  <h1>KARMAZYN<span>OS</span> STUDIO</h1>
  <div class="header-stats">
    <span>EPOKA <b id="h-epoch">0</b></span>
    <span>Φ <b id="h-atoms">0</b></span>
    <span>BĄBLE <b id="h-bubbles">0</b></span>
    <span>T̄ <b id="h-temp">0.00</b></span>
    <span>v<b id="h-ver">?</b></span>
  </div>
  <div style="margin-left:16px;display:flex;gap:8px;">
    <button class="btn" onclick="apiStep(1)">STEP</button>
    <button class="btn" onclick="apiStep(10)">×10</button>
    <button class="btn gold" onclick="apiSave()">SAVE</button>
  </div>
</header>

<!-- LEFT: Φ atoms -->
<div class="panel" id="panel-left">
  <div class="panel-title">Φ — ATOMY</div>
  <canvas id="phi-canvas"></canvas>
  <div class="tab-bar">
    <div class="tab active" onclick="switchLeftTab('atoms',this)">ATOMY</div>
    <div class="tab" onclick="switchLeftTab('ideas',this)">IDEE</div>
  </div>
  <div id="left-content"></div>
</div>

<!-- MAIN: editor + output -->
<div id="panel-main">
  <div class="editor-area">
    <div class="editor-toolbar">
      <span class="editor-mode" id="editor-mode-label">PYTHON · KARMAZYN CTX</span>
      <div style="margin-left:auto;display:flex;gap:6px;">
        <button class="btn" onclick="setMode('python')">PY</button>
        <button class="btn" onclick="setMode('karm')">KARM</button>
        <button class="btn" onclick="setMode('shell')">SH</button>
        <button class="btn gold" onclick="runCode()" title="Ctrl+Enter">▶ RUN</button>
      </div>
    </div>
    <textarea id="editor" placeholder="# Python w kontekście KarmazynOS
# Dostępne: ko, phi, bubbles, np
# Przykład:
label = ko.write('Nowa wiedza')
print(label)
results = ko.recall('wiedza', k=3)
for r in results:
    print(r['label'], r['score'])
"></textarea>
  </div>

  <div class="output-area">
    <div class="output-header">
      <span>OUTPUT</span>
      <span id="out-status" style="margin-left:auto;"></span>
      <button class="btn" onclick="clearOutput()" style="padding:2px 8px;font-size:10px;">CLR</button>
    </div>
    <div id="output"></div>
    <div class="shell-row">
      <span class="shell-prompt">ksh&gt;</span>
      <input id="shell-input" placeholder="komenda systemowa lub KarmazynOS..." autocomplete="off">
    </div>
  </div>
</div>

<!-- RIGHT: bubbles + media -->
<div class="panel" id="panel-right">
  <div class="panel-title">BĄBLE · MEDIA</div>
  <div class="tab-bar">
    <div class="tab active" onclick="switchRightTab('bubbles',this)">BĄBLE</div>
    <div class="tab" onclick="switchRightTab('canvas',this)">CANVAS</div>
  </div>
  <div id="right-content"></div>
  <canvas id="media-canvas" style="display:none;"></canvas>
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let mode = 'python';
let leftTab = 'atoms';
let rightTab = 'bubbles';
let phiCtx = null;
const cmdHistory = [];
let cmdHistIdx = -1;

// ── API ────────────────────────────────────────────────────────────────────
async function api(endpoint, data={}) {
  const r = await fetch('/api/' + endpoint, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(data)
  });
  return r.json();
}

// ── Stats refresh ──────────────────────────────────────────────────────────
async function refreshStats() {
  const s = await api('stats');
  document.getElementById('h-epoch').textContent   = s.epoch;
  document.getElementById('h-atoms').textContent   = s.atoms_phi;
  document.getElementById('h-bubbles').textContent = s.bubbles;
  document.getElementById('h-temp').textContent    = (s.temperature||0).toFixed(2);
  document.getElementById('h-ver').textContent     = s.version || '?';

  renderAtoms(s.atoms_list || []);
  renderBubbles(s.bubbles_list || []);
  renderIdeas(s.holograms_list || []);
  drawPhiCanvas(s.atoms_list || [], s.temperature, s.t_vacuum);
}

// ── Φ Canvas visualization ─────────────────────────────────────────────────
function drawPhiCanvas(atoms, temp, tvac) {
  const c = document.getElementById('phi-canvas');
  const ctx = c.getContext('2d');
  c.width = c.offsetWidth; c.height = 140;
  ctx.fillStyle = '#08080e';
  ctx.fillRect(0,0,c.width,c.height);

  const maxT = Math.max(...atoms.map(a=>a.T), 0.1);
  atoms.forEach((a, i) => {
    const x = (i / Math.max(atoms.length-1,1)) * (c.width - 20) + 10;
    const h = (a.T / maxT) * 110 + 10;
    const y = c.height - h;
    const heat = a.T / maxT;
    const r = Math.floor(80 + heat*175);
    const g = Math.floor(20 + heat*30);
    const b = Math.floor(20);
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.fillRect(x-2, y, 4, h);
  });

  // vacuum line
  if (tvac && maxT > 0) {
    const vy = c.height - (tvac/maxT)*110 - 10;
    ctx.strokeStyle = 'rgba(243,156,18,0.4)';
    ctx.setLineDash([4,4]);
    ctx.beginPath(); ctx.moveTo(0,vy); ctx.lineTo(c.width,vy); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = 'rgba(243,156,18,0.7)';
    ctx.font = '9px Share Tech Mono';
    ctx.fillText('T_vac', 4, vy-2);
  }
}

// ── Render lists ───────────────────────────────────────────────────────────
function tempColor(T, max=10) {
  const heat = Math.min(T/max, 1);
  const r = Math.floor(80 + heat*175);
  const g = Math.floor(20 + heat*50);
  return `rgb(${r},${g},20)`;
}

function renderAtoms(atoms) {
  if (leftTab !== 'atoms') return;
  const el = document.getElementById('left-content');
  el.innerHTML = atoms.map(a => {
    const pct = Math.min(a.T/10*100, 100).toFixed(0);
    const col = tempColor(a.T);
    return `<div class="atom-item fade-in" onclick="recallAtom('${a.label}')">
      <span class="atom-label" title="${a.label}">${a.label}</span>
      <div class="temp-bar"><div class="temp-fill" style="width:${pct}%;background:${col}"></div></div>
      <span style="color:${col};font-size:10px;width:32px;text-align:right">${a.T.toFixed(1)}</span>
    </div>`;
  }).join('');
}

function renderIdeas(ideas) {
  if (leftTab !== 'ideas') return;
  const el = document.getElementById('left-content');
  el.innerHTML = ideas.map(h => {
    const col = `rgba(243,156,18,${h.liv.toFixed(2)})`;
    return `<div class="atom-item fade-in">
      <span class="atom-label" title="${h.id}">${h.topic}</span>
      <span style="color:${col};font-size:10px">${(h.liv*100).toFixed(0)}%</span>
    </div>`;
  }).join('') || '<div style="padding:14px;color:var(--dim)">Brak idei</div>';
}

function renderBubbles(bubbles) {
  if (rightTab !== 'bubbles') return;
  const el = document.getElementById('right-content');
  el.innerHTML = bubbles.map(b => {
    const col = b.liv > 0.7 ? '#44ff88' : b.liv > 0.3 ? '#ffaa44' : '#ff4444';
    return `<div class="bubble-item fade-in" onclick="readBubble('${b.label}')">
      <div class="bubble-label">
        <span class="liv-dot" style="background:${col}"></span>${b.label}
      </div>
      <div class="bubble-meta">liv=${b.liv.toFixed(2)} · rc=${b.rc}</div>
    </div>`;
  }).join('') || '<div style="padding:14px;color:var(--dim)">Brak bąbli</div>';
}

// ── Tab switching ──────────────────────────────────────────────────────────
function switchLeftTab(tab, el) {
  leftTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  refreshStats();
}
function switchRightTab(tab, el) {
  rightTab = tab;
  el.parentNode.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('right-content').style.display = tab==='bubbles'?'block':'none';
  document.getElementById('media-canvas').style.display  = tab==='canvas' ?'block':'none';
  if (tab === 'canvas') initMediaCanvas();
  else refreshStats();
}

// ── Media canvas ───────────────────────────────────────────────────────────
function initMediaCanvas() {
  const c = document.getElementById('media-canvas');
  const ctx = c.getContext('2d');
  c.width = c.offsetWidth; c.height = c.offsetWidth * 9/16;
  ctx.fillStyle = '#000';
  ctx.fillRect(0,0,c.width,c.height);
  ctx.fillStyle = 'rgba(192,57,43,0.15)';
  ctx.font = '14px Share Tech Mono';
  ctx.fillStyle = '#333344';
  ctx.fillText('KARMAZYN CANVAS — dostępny przez ko.write() i exec()', 20, c.height/2);
}

// ── Code execution ─────────────────────────────────────────────────────────
function setMode(m) {
  mode = m;
  const labels = {python:'PYTHON · KARMAZYN CTX', karm:'KARM SCRIPT', shell:'SYSTEM SHELL'};
  document.getElementById('editor-mode-label').textContent = labels[m];
}

async function runCode() {
  const code = document.getElementById('editor').value.trim();
  if (!code) return;
  appendOutput(`<span class="out-info">▶ [${mode.toUpperCase()}] ${new Date().toLocaleTimeString()}</span>`);
  document.getElementById('out-status').textContent = '⟳';

  let result;
  if (mode === 'python') {
    result = await api('exec', {code});
    if (result.ok) {
      if (result.output) appendOutput(`<span class="out-ok">${escHtml(result.output)}</span>`);
      if (result.result) appendOutput(`<span class="out-result">→ ${escHtml(result.result)}</span>`);
    } else {
      appendOutput(`<span class="out-err">${escHtml(result.error)}</span>`);
    }
  } else if (mode === 'karm') {
    // każda linia jako komenda KarmazynOS
    for (const line of code.split('\n')) {
      if (!line.trim() || line.startsWith('#')) continue;
      result = await api('shell_karm', {cmd: line});
      appendOutput(`<span class="out-info">ksh&gt; ${escHtml(line)}</span>`);
      if (result && result.output)
        appendOutput(`<span class="out-ok">${escHtml(result.output)}</span>`);
    }
  } else {
    result = await api('shell', {cmd: code});
    if (result.output) appendOutput(`<span class="out-ok">${escHtml(result.output)}</span>`);
    if (result.error)  appendOutput(`<span class="out-err">${escHtml(result.error)}</span>`);
  }

  document.getElementById('out-status').textContent = result?.ok ? '✓' : '✗';
  await refreshStats();
}

// ── Shell input (bottom bar) ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const inp = document.getElementById('shell-input');
  inp.addEventListener('keydown', async (e) => {
    if (e.key === 'Enter') {
      const cmd = inp.value.trim();
      if (!cmd) return;
      cmdHistory.unshift(cmd); cmdHistIdx = -1;
      appendOutput(`<span class="out-info">ksh&gt; ${escHtml(cmd)}</span>`);
      inp.value = '';
      const r = await api('shell', {cmd});
      if (r.output) appendOutput(`<span class="out-ok">${escHtml(r.output)}</span>`);
      if (r.error)  appendOutput(`<span class="out-err">${escHtml(r.error)}</span>`);
      await refreshStats();
    } else if (e.key === 'ArrowUp') {
      cmdHistIdx = Math.min(cmdHistIdx+1, cmdHistory.length-1);
      inp.value = cmdHistory[cmdHistIdx] || '';
      e.preventDefault();
    } else if (e.key === 'ArrowDown') {
      cmdHistIdx = Math.max(cmdHistIdx-1, -1);
      inp.value = cmdHistIdx >= 0 ? cmdHistory[cmdHistIdx] : '';
    }
  });

  // Ctrl+Enter w edytorze
  document.getElementById('editor').addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); runCode(); }
    if (e.key === 'Tab') {
      e.preventDefault();
      const s = e.target.selectionStart;
      e.target.value = e.target.value.substring(0,s) + '    ' + e.target.value.substring(s);
      e.target.selectionStart = e.target.selectionEnd = s + 4;
    }
  });
});

// ── Quick actions ──────────────────────────────────────────────────────────
async function recallAtom(label) {
  const r = await api('recall', {query: label, k: 5});
  appendOutput(`<span class="out-info">recall: ${escHtml(label)}</span>`);
  (r.results||[]).forEach(res => {
    appendOutput(`<span class="out-ok">  [${res.layer}] ${escHtml(res.label)} score=${res.score?.toFixed(3)}</span>`);
  });
}

async function readBubble(label) {
  const r = await api('exec', {code: `ko.read_bubble('${label}')`});
  appendOutput(`<span class="out-info">bubble: ${escHtml(label)}</span>`);
  appendOutput(`<span class="out-result">${escHtml(r.result||'(pusty)')}</span>`);
}

async function apiStep(n) {
  await api('step', {n});
  await refreshStats();
}

async function apiSave() {
  const r = await api('save', {path: './karmazyn_data'});
  appendOutput(`<span class="out-info">SAVE → ${r.path}</span>`);
}

// ── Output helpers ─────────────────────────────────────────────────────────
function appendOutput(html) {
  const el = document.getElementById('output');
  const div = document.createElement('div');
  div.innerHTML = html;
  div.classList.add('fade-in');
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}
function clearOutput() {
  document.getElementById('output').innerHTML = '';
}
function escHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Auto-refresh ───────────────────────────────────────────────────────────
refreshStats();
setInterval(refreshStats, 5000);
</script>
</body>
</html>"""


# ─── HTTP Server ──────────────────────────────────────────────────────────────

class StudioHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # wycisz domyślne logi

    def _send_json(self, data: dict, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_html(STUDIO_HTML)
        elif path.startswith("/static/"):
            self._send_static(path)
        else:
            self.send_response(404)
            self.end_headers()

    def _send_static(self, url_path: str):
        """Serwuje pliki z katalogu static/."""
        rel   = url_path.lstrip("/")          # "static/karmazyn.css"
        fpath = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), rel
        )
        if not os.path.isfile(fpath):
            self.send_response(404)
            self.end_headers()
            return
        ext = os.path.splitext(fpath)[1].lower()
        mime = {
            ".css": "text/css; charset=utf-8",
            ".js":  "application/javascript; charset=utf-8",
            ".json":"application/json; charset=utf-8",
            ".html":"text/html; charset=utf-8",
        }.get(ext, "application/octet-stream")
        with open(fpath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}

        path = urlparse(self.path).path

        if path == "/api/stats":
            self._send_json(api_stats())

        elif path == "/api/write":
            self._send_json(api_write(data.get("content", "")))

        elif path == "/api/recall":
            self._send_json(api_recall(data.get("query",""), data.get("k",5)))

        elif path == "/api/consolidate":
            self._send_json(api_consolidate(data.get("label","")))

        elif path == "/api/step":
            self._send_json(api_step(data.get("n",1)))

        elif path == "/api/exec":
            self._send_json(api_exec(data.get("code","")))

        elif path == "/api/shell":
            self._send_json(api_shell(data.get("cmd","")))

        elif path == "/api/shell_karm":
            # przekieruj przez process_command
            try:
                from shell import process_command
                import io as _io
                old_stdout = sys.stdout
                sys.stdout = buf = _io.StringIO()
                res = process_command(data.get("cmd", ""))
                if res:
                    print(res)
                sys.stdout = old_stdout
                self._send_json({"ok": True, "output": buf.getvalue()})
            except Exception as e:
                self._send_json({"ok": False, "output": "", "error": str(e)})

        elif path == "/api/save":
            self._send_json(api_save(data.get("path","./karmazyn_data")))

        elif path == "/api/load":
            self._send_json(api_load(data.get("path","./karmazyn_data")))

        elif path == "/api/exec_log":
            self._send_json(api_exec_log())

        else:
            self._send_json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="KarmazynOS Studio")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--load", default="", help="Wczytaj stan przy starcie")
    args = parser.parse_args()

    if args.load and os.path.isdir(args.load):
        _ko.load(args.load)

    server = HTTPServer((args.host, args.port), StudioHandler)
    url    = f"http://{args.host}:{args.port}"

    print(f"\n  KarmazynOS Studio v{STUDIO_VERSION}")
    print(f"  ──────────────────────────────")
    print(f"  URL:   {url}")
    print(f"  Φ dim: {_ko.phi.dim}  T_vacuum: {_ko.phi.t_vacuum():.4f}")
    print(f"\n  Na Termux: termux-open-url {url}")
    print(f"  Ctrl+C aby zatrzymać\n")

    # spróbuj otworzyć przeglądarkę
    try:
        if sys.platform == "linux":
            subprocess.Popen(["xdg-open", url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Studio zatrzymane.")
        server.shutdown()


if __name__ == "__main__":
    main()
