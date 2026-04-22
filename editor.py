#!/usr/bin/env -S uv run --env-file .env --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "flask>=3.0",
#     "fire>=0.7.1",
# ]
# ///
import json
from flask import Flask, jsonify

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

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Riverline FSM Editor</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #fdfdfd; --text: #111; --brand: #8A5CF5; --brand-light: #c4b0f9;
    --gray: #514E4D; --gray-light: #e8e8e8; --red: #D51A24; --red-light: #F7C5C7;
    --green: #307722; --green-light: #d4efc9; --blue: #1C6ACA; --blue-light: #bcf2ed;
    --yellow: #914d08; --yellow-light: #f4eddc; --border: #e0e0e0;
    --sidebar-w: 240px; --fsm-w: 400px;
  }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 15px; background: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; }

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

  #main { flex: 1; display: flex; overflow: hidden; }

  #conv-panel { flex: 1; overflow-y: auto; border-right: 1px solid var(--border); }
  #conv-panel-inner { padding: 16px; }
  .panel-title { font-size: 11px; font-weight: 700; color: var(--brand); text-transform: uppercase; letter-spacing: .6px; margin-bottom: 10px; }

  .meta-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 14px; }
  .meta-card { background: var(--gray-light); border-radius: 6px; padding: 7px 10px; }
  .meta-card .label { font-size: 10px; color: var(--gray); }
  .meta-card .val { font-size: 13px; font-weight: 600; margin-top: 1px; }

  .messages { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }

  .msg-group { display: flex; flex-direction: column; }
  .msg-group.bot { align-items: flex-start; }
  .msg-group.borrower { align-items: flex-end; }

  .msg-bubble-wrap { position: relative; max-width: 82%; }
  .msg { padding: 7px 10px; border-radius: 10px; font-size: 14px; line-height: 1.5; }
  .msg-group.bot .msg { background: var(--gray-light); border-bottom-left-radius: 3px; }
  .msg-group.borrower .msg { background: var(--brand); color: white; border-bottom-right-radius: 3px; }
  .msg-ts { font-size: 11px; color: var(--gray); margin-top: 2px; }
  .msg-group.borrower .msg-ts { color: var(--brand-light); text-align: right; }
  .msg-class { font-size: 9px; color: var(--blue); background: var(--blue-light); padding: 1px 5px; border-radius: 3px; margin-top: 3px; display: inline-block; }

  .fn-call { font-size: 10px; padding: 3px 7px; background: var(--blue-light); color: var(--blue); border-radius: 3px; margin-top: 4px; font-family: monospace; border-left: 2px solid var(--blue); }

  /* Annotation button on borrower bubbles */
  .ann-btn { position: absolute; top: -8px; right: -8px; width: 18px; height: 18px; border-radius: 50%; background: var(--yellow-light); border: 1px solid var(--yellow); color: var(--yellow); font-size: 9px; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; z-index: 10; line-height: 1; }
  .ann-btn:hover { background: var(--yellow); color: white; }

  /* Annotation popover */
  .ann-popover { position: absolute; top: 16px; right: 0; width: 320px; background: white; border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,.12); z-index: 100; padding: 10px; display: none; }
  .ann-popover.open { display: block; }
  .ann-popover-title { font-size: 10px; font-weight: 700; color: var(--brand); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 8px; }
  .ann-fp { background: var(--red-light); border-left: 3px solid var(--red); border-radius: 3px; padding: 5px 7px; margin-bottom: 5px; font-size: 11px; }
  .ann-fp .fp-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; }
  .ann-fp .fp-cat { font-weight: 600; color: var(--red); font-size: 10px; }
  .ann-fp .fp-sev { font-size: 9px; color: var(--gray); }
  .ann-fp .fp-who { font-size: 9px; color: var(--brand); font-weight: 600; }
  .ann-fp .fp-note { color: var(--gray); }
  .ann-no-fp { font-size: 11px; color: var(--gray); font-style: italic; }

  .outcome-card { border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 14px; }
  .outcome-row { display: flex; justify-content: space-between; align-items: center; padding: 3px 0; border-bottom: 1px solid var(--gray-light); font-size: 11px; }
  .outcome-row:last-child { border-bottom: none; }
  .ok { color: var(--green); font-weight: 600; }
  .bad { color: var(--red); font-weight: 600; }
  .muted { color: var(--gray); }
  .tag-list { display: flex; gap: 4px; flex-wrap: wrap; }
  .tag { font-size: 9px; padding: 1px 5px; border-radius: 3px; background: var(--blue-light); color: var(--blue); font-weight: 600; }

  .annotation { border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 8px; }
  .ann-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
  .ann-name { font-size: 10px; font-weight: 600; color: var(--brand); }
  .ann-score { font-size: 13px; font-weight: 700; }
  .ann-assessment { font-size: 11px; color: var(--gray); margin-bottom: 6px; font-style: italic; }
  .full-fp { font-size: 11px; padding: 4px 7px; background: var(--red-light); border-left: 3px solid var(--red); border-radius: 3px; margin-bottom: 4px; }
  .full-fp .fp-cat { font-weight: 600; color: var(--red); }
  .full-fp .fp-note { color: var(--gray); margin-top: 2px; }
  .risk-flag { display: inline-block; font-size: 9px; background: var(--yellow-light); color: var(--yellow); padding: 2px 6px; border-radius: 3px; font-weight: 600; margin-right: 4px; }

  #fsm-panel { width: var(--fsm-w); overflow-y: auto; flex-shrink: 0; }
  #fsm-panel-inner { padding: 16px; }

  .transitions-list { margin-bottom: 14px; }
  .tr-row { display: flex; align-items: center; gap: 6px; font-size: 11px; padding: 4px 0; border-bottom: 1px solid var(--gray-light); }
  .tr-row:last-child { border-bottom: none; }
  .tr-from, .tr-to { font-family: monospace; font-size: 10px; background: var(--gray-light); padding: 1px 5px; border-radius: 3px; }
  .tr-arrow { color: var(--gray); }
  .tr-reason { color: var(--gray); font-size: 10px; }
  .tr-turn { font-size: 9px; color: var(--brand); min-width: 24px; }

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
      <div id="empty-state"><h2>Select a Conversation</h2><p>Choose a conversation from the sidebar.</p></div>
    </div>
  </div>
  <div id="fsm-panel">
    <div id="fsm-panel-inner">
      <div class="panel-title">FSM</div>
      <div id="fsm-svg-wrap"></div>
      <hr class="section-sep">
      <div class="panel-title">State Transitions</div>
      <div id="transitions-list" class="transitions-list"></div>
    </div>
  </div>
</div>

<script>
const STATES = ['new','message_received','verification','intent_asked','settlement_explained','amount_pending','amount_sent','date_amount_asked','payment_confirmed','escalated','dormant'];
const STATE_LABEL = {
  new:'new',message_received:'msg_recv',verification:'verif',intent_asked:'intent',
  settlement_explained:'settl_exp',amount_pending:'amt_pend',amount_sent:'amt_sent',
  date_amount_asked:'date_amt',payment_confirmed:'pay_conf',escalated:'escalated',dormant:'dormant'
};

let convIds = [], activeId = null;

async function init() {
  const ids = await fetch('/api/conversations').then(r=>r.json());
  convIds = ids;
  document.getElementById('conv-count').textContent = `${ids.length} conversations`;
  renderList(ids);
}

function renderList(ids) {
  const list = document.getElementById('conv-list');
  list.innerHTML = '';
  ids.forEach(id => {
    const el = document.createElement('div');
    el.className = 'conv-item' + (id === activeId ? ' active' : '');
    el.innerHTML = `<span class="idx">#${convIds.indexOf(id)+1}</span><span class="cid">${id.slice(0,18)}…</span>`;
    el.onclick = () => loadConversation(id);
    list.appendChild(el);
  });
}

document.getElementById('search').addEventListener('input', e => {
  const q = e.target.value.toLowerCase();
  renderList(convIds.filter((id,i) => id.toLowerCase().includes(q) || String(i+1).includes(q)));
});

document.addEventListener('click', e => {
  if (!e.target.closest('.ann-btn') && !e.target.closest('.ann-popover')) {
    document.querySelectorAll('.ann-popover.open').forEach(p => p.classList.remove('open'));
  }
});

async function loadConversation(cid) {
  activeId = cid;
  const q = document.getElementById('search').value.toLowerCase();
  renderList(convIds.filter((id,i) => !q || id.toLowerCase().includes(q) || String(i+1).includes(q)));
  const data = await fetch(`/api/conversation/${cid}`).then(r=>r.json());
  renderConv(data);
}

function renderConv({conversation: conv, outcome, annotations}) {
  const panel = document.getElementById('conv-panel-inner');
  const m = conv.metadata;

  // Build per-turn annotation index from all annotators
  const turnAnns = {};
  (annotations||[]).forEach(ann => {
    (ann.failure_points||[]).forEach(fp => {
      turnAnns[fp.turn] = turnAnns[fp.turn] || [];
      turnAnns[fp.turn].push({...fp, annotator: ann._annotator});
    });
  });

  // Function calls indexed by turn
  const fnByTurn = {};
  (conv.function_calls||[]).forEach(fc => {
    fnByTurn[fc.turn] = fnByTurn[fc.turn] || [];
    fnByTurn[fc.turn].push(fc);
  });

  // Classifications indexed by turn
  const classMap = {};
  (conv.bot_classifications||[]).forEach(c => { classMap[c.turn] = c; });

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
      <div class="meta-card"><div class="label">Settlement offered</div><div class="val">${m.settlement_offered ? '₹'+m.settlement_offered.toLocaleString() : '—'}</div></div>
      <div class="meta-card"><div class="label">Turns</div><div class="val">${m.total_turns}</div></div>
    </div>

    <div class="panel-title">Messages</div>
    <div class="messages" id="messages-wrap"></div>

    ${outcome ? `<hr class="section-sep">
    <div class="panel-title">Outcome</div>
    <div class="outcome-card">
      <div class="outcome-row"><span>Payment received</span>${yesno(outcome.payment_received)}</div>
      <div class="outcome-row"><span>Days to payment</span><span>${fmt(outcome.days_to_payment)}</span></div>
      <div class="outcome-row"><span>Payment amount</span><span>${outcome.payment_amount != null ? outcome.payment_amount.toLocaleString() : '<span class="muted">—</span>'}</span></div>
      <div class="outcome-row"><span>Expected amount</span><span>${fmt(outcome.expected_amount)}</span></div>
      <div class="outcome-row"><span>Attribution</span><span class="muted">${fmt(outcome.channel_attribution)}</span></div>
      <div class="outcome-row"><span>Concurrent channels</span><span>${outcome.concurrent_channels?.length ? `<div class="tag-list">${outcome.concurrent_channels.map(c=>`<span class="tag">${c}</span>`).join('')}</div>` : '<span class="muted">none</span>'}</span></div>
      <div class="outcome-row"><span>Life event</span><span>${fmt(outcome.borrower_life_event)}</span></div>
      <div class="outcome-row"><span>Borrower complained</span>${yesno(outcome.borrower_complained)}</div>
      <div class="outcome-row"><span>Regulatory flag</span>${outcome.regulatory_flag ? '<span class="bad">Yes</span>' : '<span class="ok">No</span>'}</div>
      <div class="outcome-row"><span>Human intervention</span>${yesno(outcome.required_human_intervention)}</div>
    </div>` : ''}

    ${annotations?.length ? `<hr class="section-sep">
    <div class="panel-title">Annotations (${annotations.length})</div>
    <div id="annotations-wrap"></div>` : ''}
  `;

  // Render messages
  const msgWrap = document.getElementById('messages-wrap');
  conv.messages.forEach(msg => {
    const isBot = msg.role === 'bot';
    const cls = !isBot && classMap[msg.turn];
    const fns = isBot ? (fnByTurn[msg.turn] || []) : [];
    const _d = new Date(msg.timestamp + (msg.timestamp.includes('Z') || msg.timestamp.includes('+') ? '' : 'Z'));
    const ts = _d.toLocaleString('en-IN', {day:'numeric',month:'short',timeZone:'Asia/Kolkata'}) + ' · ' + _d.toLocaleString('en-IN', {hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false,timeZone:'Asia/Kolkata'}) + ' IST';
    const turnFps = !isBot ? (turnAnns[msg.turn] || []) : [];

    const group = document.createElement('div');
    group.className = `msg-group ${isBot ? 'bot' : 'borrower'}`;

    const fnHtml = fns.map(fc => {
      const params = Object.entries(fc.params||{}).map(([k,v])=>`${k}=${v}`).join(', ');
      return `<div class="fn-call">⚡ ${fc.function}(${params})</div>`;
    }).join('');

    let annBtnHtml = '';
    let popoverHtml = '';
    if (!isBot) {
      const hasFps = turnFps.length > 0;
      annBtnHtml = `<button class="ann-btn" data-turn="${msg.turn}" title="Annotations for turn ${msg.turn}">${hasFps ? turnFps.length : '·'}</button>`;
      const fpItems = hasFps
        ? turnFps.map(fp => `
            <div class="ann-fp">
              <div class="fp-header">
                <span class="fp-who">${fp.annotator}</span>
                <span class="fp-cat">${fp.category}</span>
                <span class="fp-sev">sev ${fp.severity}</span>
              </div>
              <div class="fp-note">${fp.note}</div>
            </div>`).join('')
        : '<div class="ann-no-fp">No failure points flagged for this turn.</div>';
      popoverHtml = `<div class="ann-popover" data-turn="${msg.turn}">
        <div class="ann-popover-title">Turn ${msg.turn} annotations</div>
        ${fpItems}
      </div>`;
    }

    group.innerHTML = `
      <div class="msg-bubble-wrap">
        ${annBtnHtml}
        <div class="msg">${msg.text}</div>
        ${fnHtml}
        ${cls ? `<span class="msg-class">${cls.classification} (${cls.confidence})</span>` : ''}
        <div class="msg-ts">Turn ${msg.turn} · ${ts}</div>
        ${popoverHtml}
      </div>`;
    msgWrap.appendChild(group);
  });

  // Wire annotation buttons
  msgWrap.querySelectorAll('.ann-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const turn = btn.dataset.turn;
      const popover = msgWrap.querySelector(`.ann-popover[data-turn="${turn}"]`);
      const wasOpen = popover?.classList.contains('open');
      document.querySelectorAll('.ann-popover.open').forEach(p => p.classList.remove('open'));
      if (popover && !wasOpen) popover.classList.add('open');
    });
  });

  // Full annotations section
  const annWrap = document.getElementById('annotations-wrap');
  if (annWrap && annotations) {
    annotations.forEach(ann => {
      const scoreColor = ann.quality_score >= 0.7 ? 'var(--green)' : ann.quality_score >= 0.4 ? 'var(--yellow)' : 'var(--red)';
      const fps = (ann.failure_points||[]).map(fp => `
        <div class="full-fp">
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

  renderFSM(conv);
  renderTransitions(conv);
}

function renderFSM(conv) {
  const visited = new Set();
  const transitions = conv.state_transitions || [];
  transitions.forEach(t => { visited.add(t.from_state); visited.add(t.to_state); });
  const finalState = transitions.length ? transitions[transitions.length-1].to_state : 'new';

  const W = 368, PAD = 28, NODE_W = 78, NODE_H = 28, RX = 5;
  const progStates = ['new','message_received','verification','intent_asked','settlement_explained','amount_pending','amount_sent','date_amount_asked','payment_confirmed'];

  const cols = 3;
  const rows = Math.ceil(progStates.length / cols);
  const cellW = (W - 2*PAD) / cols;
  const cellH = 48;

  const pos = {};
  progStates.forEach((s, i) => {
    const r = Math.floor(i/cols), c = i%cols;
    pos[s] = { x: PAD + c*cellW + cellW/2, y: PAD + r*cellH + NODE_H/2 };
  });
  const H_prog = PAD + rows*cellH;
  pos['escalated'] = { x: PAD + cellW/2, y: H_prog + 38 };
  pos['dormant'] = { x: PAD + 3*cellW/2, y: H_prog + 38 };
  const SVG_H = H_prog + 72;

  const nodeColor = s => {
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
    const len = Math.sqrt(dx*dx + dy*dy);
    const nx = dx/len, ny = dy/len;
    const x1 = a.x + nx*(NODE_W/2), y1 = a.y + ny*(NODE_H/2);
    const x2 = b.x - nx*(NODE_W/2+4), y2 = b.y - ny*(NODE_H/2+4);
    edges += `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="#8A5CF5" stroke-width="1.5" marker-end="url(#arr)" opacity=".7"/>`;
  });

  const nodes = STATES.map(s => {
    const p = pos[s];
    if (!p) return '';
    return `<g>
      <rect x="${(p.x-NODE_W/2).toFixed(1)}" y="${(p.y-NODE_H/2).toFixed(1)}" width="${NODE_W}" height="${NODE_H}" rx="${RX}" fill="${nodeColor(s)}" stroke="${s===finalState?'#6d3fd4':'#ccc'}" stroke-width="${s===finalState?2:1}"/>
      <text x="${p.x.toFixed(1)}" y="${(p.y+1).toFixed(1)}" text-anchor="middle" dominant-baseline="middle" font-size="9" font-family="monospace" fill="${textColor(s)}">${STATE_LABEL[s]||s}</text>
    </g>`;
  }).join('');

  document.getElementById('fsm-svg-wrap').innerHTML = `
    <svg width="${W}" height="${SVG_H}" xmlns="http://www.w3.org/2000/svg">
      <defs><marker id="arr" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
        <path d="M0,0 L0,6 L6,3 z" fill="#8A5CF5"/>
      </marker></defs>
      ${edges}${nodes}
    </svg>`;
}

function renderTransitions(conv) {
  const list = document.getElementById('transitions-list');
  list.innerHTML = (conv.state_transitions||[]).map(t =>
    `<div class="tr-row">
      <span class="tr-turn">T${t.turn}</span>
      <span class="tr-from">${t.from_state}</span>
      <span class="tr-arrow">→</span>
      <span class="tr-to">${t.to_state}</span>
      <span class="tr-reason">${t.reason||''}</span>
    </div>`
  ).join('') || '<span class="muted" style="font-size:11px">None</span>';
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
