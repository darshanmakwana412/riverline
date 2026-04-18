#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "flask>=3.0",
#     "fire>=0.7.1",
# ]
# ///
import json
from pathlib import Path
from flask import Flask, jsonify, send_file
import io

app = Flask(__name__)

data = {}

def load_data():
    convs = []
    with open("data/production_logs.jsonl") as f:
        for line in f:
            convs.append(json.loads(line))
    data["conversations"] = {c["conversation_id"]: c for c in convs}
    data["conv_ids"] = [c["conversation_id"] for c in convs]

    outcomes = {}
    with open("data/outcomes.jsonl") as f:
        for line in f:
            o = json.loads(line)
            outcomes[o["conversation_id"]] = o
    data["outcomes"] = outcomes

    annotations = {}
    for i in range(1, 4):
        with open(f"data/annotations/annotator_{i}.jsonl") as f:
            for line in f:
                a = json.loads(line)
                cid = a["conversation_id"]
                annotations.setdefault(cid, []).append(a)
    data["annotations"] = annotations

@app.get("/api/conversations")
def list_conversations():
    return jsonify(data["conv_ids"])

@app.get("/api/conversation/<cid>")
def get_conversation(cid):
    conv = data["conversations"].get(cid)
    if not conv:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "conversation": conv,
        "outcome": data["outcomes"].get(cid),
        "annotations": data["annotations"].get(cid, []),
    })

@app.get("/")
def index():
    return HTML

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Riverline FSM Editor</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #fdfdfd;
    --text: #111;
    --brand: #8A5CF5;
    --brand-light: #c4b0f9;
    --gray: #514E4D;
    --gray-light: #e8e8e8;
    --red: #D51A24;
    --red-light: #F7C5C7;
    --green: #307722;
    --green-light: #d4efc9;
    --blue: #1C6ACA;
    --blue-light: #bcf2ed;
    --yellow: #914d08;
    --yellow-light: #f4eddc;
    --border: #e0e0e0;
    --sidebar-w: 240px;
    --fsm-w: 420px;
  }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 13px; background: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; }

  /* Sidebar */
  #sidebar { width: var(--sidebar-w); border-right: 1px solid var(--border); display: flex; flex-direction: column; flex-shrink: 0; }
  #sidebar-header { padding: 12px; border-bottom: 1px solid var(--border); }
  #sidebar-header h1 { font-size: 14px; font-weight: 600; color: var(--brand); letter-spacing: -.3px; }
  #sidebar-header p { font-size: 11px; color: var(--gray); margin-top: 2px; }
  #search { width: 100%; margin-top: 8px; padding: 5px 8px; border: 1px solid var(--border); border-radius: 4px; font-size: 12px; outline: none; }
  #search:focus { border-color: var(--brand); }
  #conv-list { flex: 1; overflow-y: auto; }
  .conv-item { padding: 7px 12px; cursor: pointer; border-bottom: 1px solid var(--gray-light); font-size: 11px; display: flex; align-items: center; gap: 6px; }
  .conv-item:hover { background: var(--gray-light); }
  .conv-item.active { background: var(--brand); color: white; }
  .conv-item .idx { color: var(--gray); font-size: 10px; min-width: 28px; }
  .conv-item.active .idx { color: var(--brand-light); }
  .conv-item .cid { font-family: monospace; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .conv-item .badge { margin-left: auto; font-size: 9px; padding: 1px 4px; border-radius: 3px; font-weight: 600; flex-shrink: 0; }
  .badge-paid { background: var(--green-light); color: var(--green); }
  .badge-complaint { background: var(--red-light); color: var(--red); }
  .badge-esc { background: var(--yellow-light); color: var(--yellow); }

  /* Main */
  #main { flex: 1; display: flex; overflow: hidden; }

  /* Conv panel */
  #conv-panel { flex: 1; overflow-y: auto; border-right: 1px solid var(--border); }
  #conv-panel-inner { padding: 16px; }
  .panel-title { font-size: 12px; font-weight: 600; color: var(--brand); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 10px; }

  .meta-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 14px; }
  .meta-card { background: var(--gray-light); border-radius: 6px; padding: 7px 10px; }
  .meta-card .label { font-size: 10px; color: var(--gray); }
  .meta-card .val { font-size: 13px; font-weight: 600; margin-top: 1px; }

  .messages { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
  .msg { max-width: 82%; padding: 7px 10px; border-radius: 10px; font-size: 12px; line-height: 1.5; }
  .msg-bot { align-self: flex-start; background: var(--gray-light); border-bottom-left-radius: 3px; }
  .msg-borrower { align-self: flex-end; background: var(--brand); color: white; border-bottom-right-radius: 3px; }
  .msg-ts { font-size: 9px; color: var(--gray); margin-top: 2px; }
  .msg-borrower .msg-ts { color: var(--brand-light); text-align: right; }
  .msg-class { font-size: 9px; color: var(--blue); background: var(--blue-light); padding: 1px 5px; border-radius: 3px; margin-top: 3px; display: inline-block; }

  .outcome-card { border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 14px; }
  .outcome-row { display: flex; justify-content: space-between; align-items: center; padding: 3px 0; border-bottom: 1px solid var(--gray-light); font-size: 11px; }
  .outcome-row:last-child { border-bottom: none; }
  .outcome-row .ok { color: var(--green); font-weight: 600; }
  .outcome-row .bad { color: var(--red); font-weight: 600; }
  .outcome-row .muted { color: var(--gray); }

  .annotation { border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 8px; }
  .ann-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
  .ann-name { font-size: 10px; font-weight: 600; color: var(--brand); }
  .ann-score { font-size: 13px; font-weight: 700; }
  .ann-assessment { font-size: 11px; color: var(--gray); margin-bottom: 6px; font-style: italic; }
  .fp { font-size: 11px; padding: 4px 7px; background: var(--red-light); border-left: 3px solid var(--red); border-radius: 3px; margin-bottom: 4px; }
  .fp .fp-cat { font-weight: 600; color: var(--red); }
  .fp .fp-note { color: var(--gray); margin-top: 2px; }
  .risk-flag { display: inline-block; font-size: 9px; background: var(--yellow-light); color: var(--yellow); padding: 2px 6px; border-radius: 3px; font-weight: 600; margin-right: 4px; }

  /* FSM panel */
  #fsm-panel { width: var(--fsm-w); overflow-y: auto; flex-shrink: 0; }
  #fsm-panel-inner { padding: 16px; }
  #fsm-svg-wrap { overflow-x: auto; }
  svg#fsm { display: block; }

  .func-call { font-size: 10px; padding: 3px 7px; background: var(--blue-light); color: var(--blue); border-radius: 3px; margin-bottom: 3px; font-family: monospace; }
  .transitions-list { margin-bottom: 14px; }
  .tr-row { display: flex; align-items: center; gap: 6px; font-size: 11px; padding: 4px 0; border-bottom: 1px solid var(--gray-light); }
  .tr-row:last-child { border-bottom: none; }
  .tr-from, .tr-to { font-family: monospace; font-size: 10px; background: var(--gray-light); padding: 1px 5px; border-radius: 3px; }
  .tr-arrow { color: var(--gray); }
  .tr-reason { color: var(--gray); font-size: 10px; }

  #empty-state { padding: 60px 20px; text-align: center; color: var(--gray); }
  #empty-state h2 { font-size: 18px; color: var(--brand); margin-bottom: 8px; }

  .section-sep { border: none; border-top: 1px solid var(--border); margin: 14px 0; }
</style>
</head>
<body>
<div id="sidebar">
  <div id="sidebar-header">
    <h1>Riverline FSM Editor</h1>
    <p id="conv-count">Loading…</p>
    <input id="search" type="text" placeholder="Search ID or index…">
  </div>
  <div id="conv-list"></div>
</div>
<div id="main">
  <div id="conv-panel">
    <div id="conv-panel-inner">
      <div id="empty-state"><h2>Select a Conversation</h2><p>Choose a conversation from the sidebar to inspect it.</p></div>
    </div>
  </div>
  <div id="fsm-panel">
    <div id="fsm-panel-inner">
      <div class="panel-title">FSM</div>
      <div id="fsm-svg-wrap"></div>
      <hr class="section-sep">
      <div class="panel-title">State Transitions</div>
      <div id="transitions-list" class="transitions-list"></div>
      <hr class="section-sep">
      <div class="panel-title">Function Calls</div>
      <div id="func-calls"></div>
    </div>
  </div>
</div>

<script>
const STATES = ['new','message_received','verification','intent_asked','settlement_explained','amount_pending','amount_sent','date_amount_asked','payment_confirmed','escalated','dormant'];
const STATE_LABEL = {
  new:'new', message_received:'msg_recv', verification:'verif', intent_asked:'intent',
  settlement_explained:'settl_exp', amount_pending:'amt_pend', amount_sent:'amt_sent',
  date_amount_asked:'date_amt', payment_confirmed:'pay_conf', escalated:'escalated', dormant:'dormant'
};
const ALLOWED = {
  new:['message_received','escalated','dormant'],
  message_received:['verification','escalated','dormant'],
  verification:['intent_asked','escalated','dormant'],
  intent_asked:['settlement_explained','escalated','dormant'],
  settlement_explained:['intent_asked','amount_pending','escalated','dormant'],
  amount_pending:['intent_asked','amount_sent','escalated','dormant'],
  amount_sent:['date_amount_asked','escalated','dormant'],
  date_amount_asked:['payment_confirmed','escalated','dormant'],
  payment_confirmed:['escalated','dormant'],
  escalated:[],dormant:[]
};
const ANY_TO_PAY = ['new','message_received','verification','intent_asked','settlement_explained','amount_pending','amount_sent','date_amount_asked'];

let convIds = [];
let activeId = null;

async function init() {
  const ids = await fetch('/api/conversations').then(r=>r.json());
  convIds = ids;
  document.getElementById('conv-count').textContent = `${ids.length} conversations`;
  renderList(ids);
}

function renderList(ids) {
  const list = document.getElementById('conv-list');
  list.innerHTML = '';
  ids.forEach((id, i) => {
    const el = document.createElement('div');
    el.className = 'conv-item' + (id === activeId ? ' active' : '');
    el.innerHTML = `<span class="idx">#${convIds.indexOf(id)+1}</span><span class="cid">${id.slice(0,18)}…</span>`;
    el.onclick = () => loadConversation(id);
    list.appendChild(el);
  });
}

document.getElementById('search').addEventListener('input', e => {
  const q = e.target.value.toLowerCase();
  const filtered = convIds.filter((id, i) =>
    id.toLowerCase().includes(q) || String(i+1).includes(q)
  );
  renderList(filtered);
});

async function loadConversation(cid) {
  activeId = cid;
  renderList(convIds.filter(id => {
    const q = document.getElementById('search').value.toLowerCase();
    return !q || id.toLowerCase().includes(q) || String(convIds.indexOf(id)+1).includes(q);
  }));

  const data = await fetch(`/api/conversation/${cid}`).then(r=>r.json());
  renderConv(data);
}

function renderConv({conversation: conv, outcome, annotations}) {
  const panel = document.getElementById('conv-panel-inner');
  const m = conv.metadata;

  const fmt = v => v == null ? '<span class="muted">—</span>' : v;
  const yesno = v => v ? '<span class="ok">Yes</span>' : '<span class="bad">No</span>';

  panel.innerHTML = `
    <div class="panel-title">Conversation ${conv.conversation_id.slice(0,12)}…</div>
    <div class="meta-grid">
      <div class="meta-card"><div class="label">Language</div><div class="val">${m.language}</div></div>
      <div class="meta-card"><div class="label">Zone</div><div class="val">${m.zone}</div></div>
      <div class="meta-card"><div class="label">DPD</div><div class="val">${m.dpd}</div></div>
      <div class="meta-card"><div class="label">POS</div><div class="val">₹${m.pos?.toLocaleString()}</div></div>
      <div class="meta-card"><div class="label">TOS</div><div class="val">₹${m.tos?.toLocaleString()}</div></div>
      <div class="meta-card"><div class="label">Turns</div><div class="val">${m.total_turns}</div></div>
    </div>

    <div class="panel-title">Messages</div>
    <div class="messages" id="messages-wrap"></div>

    ${outcome ? `<hr class="section-sep">
    <div class="panel-title">Outcome</div>
    <div class="outcome-card">
      <div class="outcome-row"><span>Payment received</span>${yesno(outcome.payment_received)}</div>
      <div class="outcome-row"><span>Days to payment</span><span>${fmt(outcome.days_to_payment)}</span></div>
      <div class="outcome-row"><span>Payment amount</span><span>${outcome.payment_amount ? '₹'+outcome.payment_amount.toLocaleString() : '<span class="muted">—</span>'}</span></div>
      <div class="outcome-row"><span>Expected amount</span><span>₹${outcome.expected_amount?.toLocaleString()}</span></div>
      <div class="outcome-row"><span>Attribution</span><span class="muted">${outcome.channel_attribution || '—'}</span></div>
      <div class="outcome-row"><span>Borrower complained</span>${yesno(outcome.borrower_complained)}</div>
      <div class="outcome-row"><span>Regulatory flag</span>${outcome.regulatory_flag ? '<span class="bad">Yes</span>' : '<span class="ok">No</span>'}</div>
      <div class="outcome-row"><span>Human intervention</span>${yesno(outcome.required_human_intervention)}</div>
    </div>` : ''}

    ${annotations && annotations.length ? `<hr class="section-sep">
    <div class="panel-title">Annotations (${annotations.length})</div>
    <div id="annotations-wrap"></div>` : ''}
  `;

  // Messages
  const classMap = {};
  (conv.bot_classifications||[]).forEach(c => { classMap[c.turn] = c; });
  const msgWrap = document.getElementById('messages-wrap');
  conv.messages.forEach(msg => {
    const isBot = msg.role === 'bot';
    const cls = !isBot && classMap[msg.turn];
    const ts = new Date(msg.timestamp).toLocaleString('en-IN', {hour:'2-digit',minute:'2-digit',day:'numeric',month:'short'});
    const el = document.createElement('div');
    el.style.display = 'flex';
    el.style.flexDirection = 'column';
    el.style.alignItems = isBot ? 'flex-start' : 'flex-end';
    el.innerHTML = `
      <div class="msg ${isBot ? 'msg-bot' : 'msg-borrower'}">${msg.text}</div>
      ${cls ? `<span class="msg-class">${cls.classification} (${cls.confidence})</span>` : ''}
      <div class="msg-ts">Turn ${msg.turn} · ${ts}</div>
    `;
    msgWrap.appendChild(el);
  });

  // Annotations
  const annWrap = document.getElementById('annotations-wrap');
  if (annWrap && annotations) {
    annotations.forEach(ann => {
      const scoreColor = ann.quality_score >= 0.7 ? 'var(--green)' : ann.quality_score >= 0.4 ? 'var(--yellow)' : 'var(--red)';
      const fps = (ann.failure_points||[]).map(fp => `
        <div class="fp">
          <div class="fp-cat">Turn ${fp.turn} · ${fp.category} (sev: ${fp.severity})</div>
          <div class="fp-note">${fp.note}</div>
        </div>`).join('');
      const flags = (ann.risk_flags||[]).map(f => `<span class="risk-flag">${f}</span>`).join('');
      annWrap.innerHTML += `
        <div class="annotation">
          <div class="ann-header">
            <span class="ann-name">${ann._annotator || 'annotator'}</span>
            <span class="ann-score" style="color:${scoreColor}">${ann.quality_score?.toFixed(2)}</span>
          </div>
          <div class="ann-assessment">${ann.overall_assessment || ''}</div>
          ${flags ? `<div style="margin-bottom:6px">${flags}</div>` : ''}
          ${fps}
        </div>`;
    });
  }

  // FSM
  renderFSM(conv);
  renderTransitions(conv);
  renderFuncCalls(conv);
}

function renderFSM(conv) {
  const visited = new Set();
  const transitions = conv.state_transitions || [];
  transitions.forEach(t => { visited.add(t.from_state); visited.add(t.to_state); });
  const finalState = transitions.length ? transitions[transitions.length-1].to_state : 'new';
  const path = transitions.map(t => t.to_state);

  const W = 380, PAD = 30, NODE_W = 80, NODE_H = 30, RX = 6;
  const progStates = ['new','message_received','verification','intent_asked','settlement_explained','amount_pending','amount_sent','date_amount_asked','payment_confirmed'];
  const exitStates = ['escalated','dormant'];

  const cols = 3, rows = Math.ceil(progStates.length/cols);
  const cellW = (W - 2*PAD) / cols;
  const cellH = 50;

  const pos = {};
  progStates.forEach((s, i) => {
    const r = Math.floor(i/cols), c = i%cols;
    pos[s] = { x: PAD + c*cellW + cellW/2, y: PAD + r*cellH + NODE_H/2 };
  });
  const H_prog = PAD + rows*cellH;
  pos['escalated'] = { x: PAD + cellW/2, y: H_prog + 40 };
  pos['dormant'] = { x: PAD + 3*cellW/2, y: H_prog + 40 };
  const SVG_H = H_prog + 80;

  const color = s => {
    if (s === finalState) return '#8A5CF5';
    if (visited.has(s)) return '#c4b0f9';
    if (s === 'escalated') return '#F7C5C7';
    if (s === 'dormant') return '#f4eddc';
    return '#e8e8e8';
  };
  const textColor = s => s === finalState ? 'white' : '#111';

  let edges = '';
  transitions.forEach(t => {
    if (t.from_state === t.to_state) return;
    const a = pos[t.from_state], b = pos[t.to_state];
    if (!a || !b) return;
    const dx = b.x - a.x, dy = b.y - a.y;
    const len = Math.sqrt(dx*dx+dy*dy);
    const nx = dx/len, ny = dy/len;
    const x1 = a.x + nx*(NODE_W/2), y1 = a.y + ny*(NODE_H/2);
    const x2 = b.x - nx*(NODE_W/2+4), y2 = b.y - ny*(NODE_H/2+4);
    edges += `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="#8A5CF5" stroke-width="1.5" marker-end="url(#arr)" opacity=".7"/>`;
  });

  let nodes = STATES.map(s => {
    const p = pos[s];
    if (!p) return '';
    const fill = color(s);
    const tc = textColor(s);
    const lbl = STATE_LABEL[s] || s;
    return `<g>
      <rect x="${(p.x-NODE_W/2).toFixed(1)}" y="${(p.y-NODE_H/2).toFixed(1)}" width="${NODE_W}" height="${NODE_H}" rx="${RX}" fill="${fill}" stroke="${s===finalState?'#6d3fd4':'#ccc'}" stroke-width="${s===finalState?2:1}"/>
      <text x="${p.x.toFixed(1)}" y="${(p.y+1).toFixed(1)}" text-anchor="middle" dominant-baseline="middle" font-size="9" font-family="monospace" fill="${tc}">${lbl}</text>
    </g>`;
  }).join('');

  document.getElementById('fsm-svg-wrap').innerHTML = `
    <svg id="fsm" width="${W}" height="${SVG_H}" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arr" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill="#8A5CF5"/>
        </marker>
      </defs>
      ${edges}${nodes}
    </svg>`;
}

function renderTransitions(conv) {
  const list = document.getElementById('transitions-list');
  list.innerHTML = (conv.state_transitions||[]).map(t =>
    `<div class="tr-row">
      <span class="tr-from">${t.from_state}</span>
      <span class="tr-arrow">→</span>
      <span class="tr-to">${t.to_state}</span>
      <span class="tr-reason">${t.reason||''}</span>
    </div>`
  ).join('') || '<span style="color:var(--gray);font-size:11px">None</span>';
}

function renderFuncCalls(conv) {
  const el = document.getElementById('func-calls');
  el.innerHTML = (conv.function_calls||[]).map(fc => {
    const params = Object.entries(fc.params||{}).map(([k,v])=>`${k}=${v}`).join(', ');
    return `<div class="func-call">T${fc.turn}: ${fc.function}(${params})</div>`;
  }).join('') || '<span style="color:var(--gray);font-size:11px">None</span>';
}

init();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import fire
    def main(port: int = 5000, host: str = "127.0.0.1"):
        load_data()
        print(f"Editor running at http://{host}:{port}")
        app.run(host=host, port=port, debug=False)
    fire.Fire(main)
