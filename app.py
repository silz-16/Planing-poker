from flask import Flask, request, jsonify, render_template_string
import os

app = Flask(__name__)
rooms = {}

PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PLANNING POKER // DRONE</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html, body { min-height:100vh; overflow-x:hidden; }
  body {
    font-family: 'Inter', 'Segoe UI', sans-serif;
    background: #03030a;
    color:#e8e8f0;
    display:flex; flex-direction:column; align-items:center;
    padding:40px 20px;
    position:relative;
    letter-spacing:.02em;
    cursor: crosshair;
  }

  .bg-nebula {
    position:fixed; inset:0; z-index:0; pointer-events:none;
    background:
      radial-gradient(ellipse 60% 40% at 20% 30%, rgba(120,20,140,0.18), transparent 60%),
      radial-gradient(ellipse 50% 35% at 80% 70%, rgba(20,80,150,0.15), transparent 60%),
      radial-gradient(ellipse 70% 50% at 50% 50%, rgba(60,10,80,0.12), transparent 70%),
      radial-gradient(ellipse at top, #0a0a20 0%, #03030a 60%);
  }
  .vignette {
    position:fixed; inset:0; z-index:1; pointer-events:none;
    background: radial-gradient(ellipse at center, transparent 30%, rgba(3,3,10,0.85) 100%);
  }
  .scanline {
    position:fixed; inset:0; z-index:2; pointer-events:none;
    background: repeating-linear-gradient(
      to bottom,
      transparent 0px, transparent 3px,
      rgba(255,60,60,0.015) 3px, rgba(255,60,60,0.015) 4px
    );
    opacity:.6;
  }
  #bg-canvas {
    position:fixed; inset:0;
    z-index:3;
    pointer-events:none;
  }

  .content {
    position:relative;
    z-index:10;
    width:100%;
    display:flex; flex-direction:column; align-items:center;
  }

  .hud-header {
    display:flex; align-items:center; gap:14px;
    margin-bottom:8px;
  }
  .hud-dot {
    width:8px; height:8px; border-radius:50%;
    background:#ff3333;
    box-shadow: 0 0 12px #ff3333, 0 0 24px #ff3333;
    animation: pulse 2s ease infinite;
  }
  @keyframes pulse {
    0%,100% { opacity:1; transform:scale(1); }
    50% { opacity:.4; transform:scale(0.85); }
  }
  .hud-label {
    font-family: 'JetBrains Mono','Consolas',monospace;
    font-size:.7rem;
    letter-spacing:.25em;
    color:#ff5555;
    text-transform:uppercase;
  }

  h1 {
    font-size:2.4rem;
    font-weight:800;
    letter-spacing:.05em;
    background: linear-gradient(135deg,#ffffff 0%,#ff5555 50%,#ff0033 100%);
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
    text-transform:uppercase;
    margin: 4px 0 6px;
    filter: drop-shadow(0 0 30px rgba(255,60,60,0.4));
  }
  .subtitle {
    font-family: 'JetBrains Mono',monospace;
    color:#5a5a7a;
    margin-bottom:35px;
    font-size:.75rem;
    letter-spacing:.25em;
    text-transform:uppercase;
  }

  .card {
    position:relative;
    background: linear-gradient(180deg, rgba(10,10,24,0.7), rgba(6,6,16,0.8));
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    border:1px solid rgba(255,80,80,0.22);
    padding:28px;
    width:100%; max-width:820px;
    margin-bottom:20px;
    clip-path: polygon(0 12px, 12px 0, calc(100% - 12px) 0, 100% 12px, 100% calc(100% - 12px), calc(100% - 12px) 100%, 12px 100%, 0 calc(100% - 12px));
    box-shadow:
      0 0 60px rgba(255,60,60,0.08),
      inset 0 0 80px rgba(255,60,60,0.015);
  }
  .card::before, .card::after {
    content:'';
    position:absolute;
    width:14px; height:14px;
    border:1px solid #ff5555;
  }
  .card::before { top:-1px; left:-1px; border-right:0; border-bottom:0; }
  .card::after  { bottom:-1px; right:-1px; border-left:0; border-top:0; }

  .row { display:flex; gap:10px; flex-wrap:wrap; }

  input, button {
    padding:13px 18px;
    border:none;
    font-size:.95rem;
    outline:none;
    transition:.25s cubic-bezier(.4,0,.2,1);
    font-family:inherit;
    letter-spacing:.03em;
    cursor: default;
  }
  input {
    flex:1; min-width:150px;
    background: rgba(255,60,60,0.04);
    color:#fff;
    border:1px solid rgba(255,80,80,0.25);
    clip-path: polygon(0 8px, 8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%);
  }
  input::placeholder { color:#4a4a6a; }
  input:focus {
    border-color:#ff5555;
    background: rgba(255,60,60,0.08);
    box-shadow: 0 0 24px rgba(255,60,60,0.25);
  }

  button {
    cursor:pointer;
    background: linear-gradient(135deg, #ff3333, #ff7777);
    color:#04040c;
    font-weight:700;
    text-transform:uppercase;
    font-size:.8rem;
    letter-spacing:.15em;
    clip-path: polygon(0 8px, 8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%);
    position:relative;
  }
  button:hover {
    transform:translateY(-2px);
    box-shadow: 0 0 30px rgba(255,60,60,0.6), 0 0 60px rgba(255,120,120,0.35);
  }
  button:active { transform:scale(0.96); }

  h3 {
    font-family: 'JetBrains Mono', monospace;
    font-size:.75rem;
    letter-spacing:.25em;
    text-transform:uppercase;
    color:#ff5555;
    margin-bottom:14px;
    font-weight:500;
  }

  .cards-grid {
    display:grid;
    grid-template-columns: repeat(auto-fit, minmax(48px, 1fr));
    gap:6px;
    margin-top:18px;
  }
  .poker-card {
    aspect-ratio: 1 / 1.35;
    background: linear-gradient(160deg, rgba(255,60,60,0.04), rgba(255,120,120,0.04));
    border:1px solid rgba(255,80,80,0.2);
    display:flex; align-items:center; justify-content:center;
    font-family: 'JetBrains Mono', monospace;
    font-size:1.05rem; font-weight:700;
    cursor:pointer;
    transition:.2s cubic-bezier(.4,0,.2,1);
    color:#e0e8ff;
    position:relative;
    overflow:hidden;
    clip-path: polygon(0 8px, 8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%);
    user-select:none;
  }
  .poker-card:hover {
    border-color:#ff5555;
    color:#ff5555;
    transform:translateY(-4px);
    box-shadow:
      0 0 18px rgba(255,60,60,0.45),
      inset 0 0 18px rgba(255,60,60,0.1);
  }
  .poker-card.selected {
    background: linear-gradient(160deg,#ff3333,#ff7777);
    border-color:#fff;
    color:#04040c;
    transform:translateY(-4px);
    box-shadow:
      0 0 25px rgba(255,60,60,0.7),
      0 0 50px rgba(255,120,120,0.5);
  }
  .poker-card.clicked { animation: cardPulse 0.3s cubic-bezier(.4,0,.2,1); }
  @keyframes cardPulse {
    0% { box-shadow: 0 0 0 rgba(255,255,255,0); transform: translateY(-4px) scale(1); }
    30% {
      box-shadow:
        0 0 40px rgba(255,255,255,0.9),
        0 0 80px rgba(255,60,60,0.8),
        0 0 120px rgba(255,0,50,0.6),
        inset 0 0 30px rgba(255,255,255,0.5);
      transform: translateY(-8px) scale(1.1);
      border-color: #fff;
    }
    100% { box-shadow: 0 0 0 rgba(255,255,255,0); transform: translateY(-4px) scale(1); }
  }

  .users { margin-top:20px; display:flex; flex-direction:column; gap:8px; }
  .user-row {
    display:flex; justify-content:space-between; align-items:center;
    padding:12px 18px;
    background: rgba(255,60,60,0.03);
    border:1px solid rgba(255,80,80,0.1);
    font-family: 'JetBrains Mono', monospace;
    font-size:.85rem;
    transition:.3s;
    clip-path: polygon(0 6px, 6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%);
  }
  .user-row.voted { border-left:3px solid #22c55e; }
  .user-row.just-revealed { animation: popIn .5s ease; }
  @keyframes popIn {
    0% { transform:scale(0.92); opacity:0.4; }
    60% { transform:scale(1.03); }
    100% { transform:scale(1); opacity:1; }
  }
  .badge {
    padding:4px 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size:.75rem;
    background: rgba(255,60,60,0.08);
    color:#ff5555;
    border:1px solid rgba(255,80,80,0.3);
    letter-spacing:.05em;
  }
  .badge.voted { background: rgba(34,197,94,0.1); color:#4ade80; border-color:rgba(34,197,94,0.4); }
  .badge.revealed {
    background: linear-gradient(135deg,#ff3333,#ff7777);
    color:#04040c;
    border-color:transparent;
    font-weight:700;
    box-shadow: 0 0 20px rgba(255,60,60,0.6);
  }

  .result {
    text-align:center;
    padding:26px;
    background: linear-gradient(135deg, rgba(255,60,60,0.05), rgba(255,120,120,0.05));
    border:1px solid rgba(255,80,80,0.15);
    margin-top:20px;
    transition:.3s;
    clip-path: polygon(0 14px, 14px 0, calc(100% - 14px) 0, 100% 14px, 100% calc(100% - 14px), calc(100% - 14px) 100%, 14px 100%, 0 calc(100% - 14px));
    position:relative;
  }
  .result.ready {
    border-color: rgba(255,60,60,0.5);
    box-shadow: 0 0 80px rgba(255,60,60,0.25), inset 0 0 40px rgba(255,60,60,0.05);
  }
  .result .avg {
    font-family: 'JetBrains Mono', monospace;
    font-size:3.6rem;
    font-weight:800;
    background: linear-gradient(135deg,#ff5555,#ffffff,#ff0033);
    background-size: 200% 200%;
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
    animation: shiftGrad 4s ease infinite;
    line-height:1.1;
    letter-spacing:-.02em;
  }
  @keyframes shiftGrad {
    0%,100% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
  }
  .result .label {
    font-family: 'JetBrains Mono', monospace;
    color:#5a5a7a;
    font-size:.75rem;
    letter-spacing:.25em;
    text-transform:uppercase;
  }
  .hidden { display:none; }
  .footer-note {
    font-family: 'JetBrains Mono', monospace;
    color:#3a3a5a;
    font-size:.7rem;
    margin-top:12px;
    text-align:center;
    letter-spacing:.15em;
    text-transform:uppercase;
  }

  .room-list { margin-top:15px; display:flex; flex-direction:column; gap:6px; }
  .room-item {
    display:flex; justify-content:space-between; align-items:center;
    padding:12px 18px;
    background: rgba(255,60,60,0.03);
    border:1px solid rgba(255,80,80,0.15);
    cursor:pointer;
    transition:.25s;
    font-family: 'JetBrains Mono', monospace;
    font-size:.85rem;
    clip-path: polygon(0 6px, 6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%);
  }
  .room-item:hover {
    background: rgba(255,60,60,0.1);
    border-color:#ff5555;
    transform:translateX(6px);
    box-shadow: -4px 0 24px rgba(255,60,60,0.4);
  }
  .room-item .count { color:#ff5555; font-size:.75rem; }

  .actions-row { display:flex; gap:10px; margin-top:16px; }
  .actions-row button { flex:1; padding:14px 18px; }
  .btn-reveal { background: linear-gradient(135deg,#22c55e,#ff3333) !important; }
  .btn-reveal:hover { box-shadow: 0 0 40px rgba(34,197,94,0.7) !important; }
  .btn-hide { background: rgba(255,255,255,0.06) !important; color:#a0a0c0 !important; }
  .btn-hide:hover { background: rgba(255,255,255,0.12) !important; box-shadow: 0 0 24px rgba(255,255,255,0.15) !important; }

  .share-box { display:flex; gap:8px; margin-top:12px; }
  .share-box input { font-size:.8rem; padding:9px 12px; }
  .share-box button { padding:9px 14px; font-size:.7rem; }

  .room-header {
    display:flex; justify-content:space-between; align-items:center;
    padding-bottom:18px; margin-bottom:18px;
    border-bottom:1px solid rgba(255,80,80,0.1);
  }
  .room-header .label-sm {
    font-family: 'JetBrains Mono', monospace;
    font-size:.7rem;
    color:#5a5a7a;
    letter-spacing:.25em;
    text-transform:uppercase;
  }
  .room-header .room-name {
    font-family: 'JetBrains Mono', monospace;
    font-size:1.3rem;
    font-weight:700;
    color:#ff5555;
    text-shadow: 0 0 20px rgba(255,60,60,0.6);
    letter-spacing:.05em;
  }

  .flash-overlay {
    position:fixed; inset:0;
    background: radial-gradient(circle at center, rgba(255,0,50,0.5), rgba(255,100,100,0.3), transparent 70%);
    pointer-events:none;
    z-index:100;
    opacity:0;
    mix-blend-mode:screen;
  }
  .flash-overlay.active { animation: flashBang 0.5s ease-out; }
  @keyframes flashBang {
    0% { opacity:1; transform:scale(0.3); }
    100% { opacity:0; transform:scale(3); }
  }

  #kill-counter {
    position:fixed;
    bottom:20px; right:24px;
    font-family: 'JetBrains Mono', monospace;
    font-size:.75rem;
    letter-spacing:.2em;
    color:#ff5555;
    text-transform:uppercase;
    z-index:20;
    padding:8px 14px;
    background: rgba(10,10,24,0.6);
    backdrop-filter: blur(8px);
    border:1px solid rgba(255,80,80,0.3);
    clip-path: polygon(0 6px, 6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%);
    pointer-events:none;
    text-shadow: 0 0 10px rgba(255,60,60,0.6);
  }
  #kill-counter span { color:#ffffff; font-weight:700; }

  @media (max-width:600px) {
    .cards-grid { grid-template-columns: repeat(auto-fit, minmax(42px, 1fr)); }
    .poker-card { font-size:.9rem; }
    .card { padding:20px; }
    #kill-counter { bottom:10px; right:10px; font-size:.65rem; }
  }
</style>
</head>
<body>

<div class="bg-nebula"></div>
<div class="vignette"></div>
<div class="scanline"></div>
<canvas id="bg-canvas"></canvas>
<div class="flash-overlay" id="flash"></div>

<div id="kill-counter">🐛 KILLS: <span id="kills">0</span> · BUGS: <span id="bug-count">50</span></div>

<div class="content">
  <div class="hud-header">
    <div class="hud-dot"></div>
    <div class="hud-label">DRONE OPS · v8.1</div>
  </div>
  <h1>Planning Poker</h1>
  <p class="subtitle">// estimate · vote · reveal · pew pew //</p>

  <div class="card" id="join-screen">
    <h3>[ ВХОД В КОМНАТУ ]</h3>
    <div class="row">
      <input id="name-input" placeholder="Имя оператора" maxlength="20">
      <input id="room-input" placeholder="ID комнаты" maxlength="20">
      <button onclick="joinRoom()">Войти →</button>
    </div>
    <div id="rooms-section" class="hidden">
      <p style="margin-top:22px; margin-bottom:10px; color:#5a5a7a; font-size:.75rem; font-family:'JetBrains Mono',monospace; letter-spacing:.2em; text-transform:uppercase;">// активные комнаты</p>
      <div class="room-list" id="room-list"></div>
    </div>
    <p class="footer-note">комната создастся автоматически</p>
  </div>

  <div id="game-screen" class="hidden">
    <div class="card">
      <div class="room-header">
        <div>
          <div class="label-sm">Комната</div>
          <div class="room-name" id="room-name"></div>
        </div>
        <button onclick="leaveRoom()" style="background:rgba(255,60,60,0.12); color:#ff5555; border:1px solid rgba(255,80,80,0.4);">Выйти</button>
      </div>

      <div class="share-box">
        <input id="share-link" readonly>
        <button onclick="copyLink(event)">📋 Copy</button>
      </div>

      <h3 style="margin-top:26px;">[ ВЫБЕРИТЕ ОЦЕНКУ ]</h3>
      <div class="cards-grid" id="cards"></div>

      <div class="actions-row">
        <button id="reveal-btn" class="btn-reveal" onclick="revealResults()">👁 Reveal</button>
        <button onclick="resetVotes()" class="btn-hide">🔄 Reset</button>
      </div>

      <div class="result" id="result">
        <div class="label">Средняя оценка</div>
        <div class="avg" id="avg-value">—</div>
        <div class="label" id="votes-info">Ожидание…</div>
      </div>

      <h3 style="margin-top:26px;">[ УЧАСТНИКИ ]</h3>
      <div class="users" id="users"></div>
    </div>
  </div>
</div>

<script>
/* ===================================================================
   SCI-FI DRONE (top-right) + RED LASERS + CRAWLING BUGS
   =================================================================== */
const canvas = document.getElementById('bg-canvas');
const ctx = canvas.getContext('2d');
let W = 0, H = 0;
let DPR = Math.min(window.devicePixelRatio || 1, 2);
const mouse = { x: 0, y: 0 };

/* ============ ДРОН ============ */
let drone = {
  cx: 0, cy: 0,
  R: 90,
  bobPhase: 0,
  surprise: 0,
  explode: 0,
  visorGlow: 0,
  scanPhase: 0,
  leftPupil: { x: 0, y: 0 },
  rightPupil: { x: 0, y: 0 },
  antennaPhase: 0,
  panelPhase: 0,
};
const sparkParticles = [];
const lasers = [];
const bugs = [];
const bugParts = [];

const LASER_PALETTE = ['#ff0000', '#ff2222', '#ff4444'];
const EXPLOSION_PALETTE = ['#ffffff', '#ff5555', '#ff0033', '#ff8888'];

/* ============ ЖУЧКИ: КОНСТАНТЫ ============ */
const BUG_COUNT = 50;
const BUG_MIN = 40;
const BUG_SPAWN_AMOUNT = 30;

function createBug() {
  const angle = Math.random() * Math.PI * 2;
  const speed = 0.25 + Math.random() * 0.55;
  return {
    x: Math.random() * W,
    y: Math.random() * H,
    vx: Math.cos(angle) * speed,
    vy: Math.sin(angle) * speed,
    size: 5 + Math.random() * 3.5,
    legPhase: Math.random() * Math.PI * 2,
    legSpeed: 0.35 + Math.random() * 0.25,
    bodyAngle: angle,
    pauseTimer: 0,
    pauseCd: 120 + Math.random() * 300,
    isPaused: false,
    turnTimer: 0,
    turnCd: 80 + Math.random() * 150,
  };
}

function spawnBugs() {
  bugs.length = 0;
  for (let i = 0; i < BUG_COUNT; i++) bugs.push(createBug());
  updateBugCount();
}

function updateBugCount() {
  const el = document.getElementById('bug-count');
  if (el) el.textContent = bugs.length;
}

function updateBugs(dt) {
  for (const b of bugs) {
    b.pauseTimer++;
    if (b.pauseTimer > b.pauseCd) {
      b.pauseTimer = 0;
      b.pauseCd = 120 + Math.random() * 300;
      b.isPaused = !b.isPaused;
    }

    if (b.isPaused) {
      b.vx *= 0.9;
      b.vy *= 0.9;
    } else {
      b.turnTimer++;
      if (b.turnTimer > b.turnCd) {
        b.turnTimer = 0;
        b.turnCd = 80 + Math.random() * 150;
        const angle = Math.atan2(b.vy, b.vx);
        const newAngle = angle + (Math.random() - 0.5) * 0.7;
        const s = Math.sqrt(b.vx * b.vx + b.vy * b.vy) || 0.4;
        b.vx = Math.cos(newAngle) * s;
        b.vy = Math.sin(newAngle) * s;
      }
    }

    const spd = Math.sqrt(b.vx * b.vx + b.vy * b.vy);
    const maxSpd = 1.2;
    if (spd > maxSpd) {
      b.vx = (b.vx / spd) * maxSpd;
      b.vy = (b.vy / spd) * maxSpd;
    }

    b.vx *= 0.97;
    b.vy *= 0.97;

    b.x += b.vx;
    b.y += b.vy;

    if (spd > 0.05) {
      const targetAngle = Math.atan2(b.vy, b.vx);
      let diff = targetAngle - b.bodyAngle;
      while (diff > Math.PI) diff -= Math.PI * 2;
      while (diff < -Math.PI) diff += Math.PI * 2;
      b.bodyAngle += diff * 0.15;
    }

    if (b.x < 15) { b.x = 15; b.vx = Math.abs(b.vx); }
    if (b.x > W - 15) { b.x = W - 15; b.vx = -Math.abs(b.vx); }
    if (b.y < 15) { b.y = 15; b.vy = Math.abs(b.vy); }
    if (b.y > H - 15) { b.y = H - 15; b.vy = -Math.abs(b.vy); }

    if (!b.isPaused && spd > 0.1) {
      b.legPhase += b.legSpeed;
    }

    const dx = b.x - mouse.x;
    const dy = b.y - mouse.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    if (dist < 100) {
      const push = (100 - dist) / 100 * 0.8;
      b.vx += (dx / dist) * push;
      b.vy += (dy / dist) * push;
    }
  }
}

function drawBugs() {
  for (const b of bugs) {
    ctx.save();
    ctx.translate(b.x, b.y);
    ctx.rotate(b.bodyAngle);

    const s = b.size;

    const legPairs = [
      { xOffset: -s * 0.5, length: s * 1.3, baseAngle: -Math.PI * 0.75 },
      { xOffset: 0,        length: s * 1.4, baseAngle: -Math.PI * 0.55 },
      { xOffset: s * 0.5,  length: s * 1.2, baseAngle: -Math.PI * 0.35 },
      { xOffset: -s * 0.5, length: s * 1.3, baseAngle: Math.PI * 0.75 },
      { xOffset: 0,        length: s * 1.4, baseAngle: Math.PI * 0.55 },
      { xOffset: s * 0.5,  length: s * 1.2, baseAngle: Math.PI * 0.35 },
    ];

    ctx.strokeStyle = '#3a1a1a';
    ctx.lineWidth = 1.6;
    ctx.lineCap = 'round';

    legPairs.forEach((leg, i) => {
      const phase = b.legPhase + (i % 2 === 0 ? 0 : Math.PI) + (i >= 3 ? Math.PI : 0);
      const stepAmp = Math.sin(phase) * 0.35;
      const startX = leg.xOffset;
      const startY = 0;
      const kneeAngle = leg.baseAngle + stepAmp * 0.6;
      const kneeX = startX + Math.cos(kneeAngle) * leg.length * 0.5;
      const kneeY = startY + Math.sin(kneeAngle) * leg.length * 0.5;
      const footAngle = leg.baseAngle + stepAmp;
      const footX = kneeX + Math.cos(footAngle) * leg.length * 0.5;
      const footY = kneeY + Math.sin(footAngle) * leg.length * 0.5;
      ctx.beginPath();
      ctx.moveTo(startX, startY);
      ctx.lineTo(kneeX, kneeY);
      ctx.lineTo(footX, footY);
      ctx.stroke();
    });

    const bodyGrad = ctx.createRadialGradient(-s * 0.2, -s * 0.2, 0, 0, 0, s * 1.3);
    bodyGrad.addColorStop(0, '#3a1010');
    bodyGrad.addColorStop(0.7, '#1a0808');
    bodyGrad.addColorStop(1, '#000000');

    ctx.fillStyle = bodyGrad;
    ctx.beginPath();
    ctx.ellipse(0, 0, s * 1.1, s * 0.75, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = 'rgba(255,60,60,0.85)';
    ctx.lineWidth = 1.2;
    ctx.stroke();

    ctx.fillStyle = '#1a0808';
    ctx.beginPath();
    ctx.arc(s * 1.1, 0, s * 0.55, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,60,60,0.85)';
    ctx.stroke();

    ctx.strokeStyle = 'rgba(255,80,80,0.9)';
    ctx.lineWidth = 1;
    const antWiggle = Math.sin(b.legPhase * 1.5) * 0.15;
    ctx.beginPath();
    ctx.moveTo(s * 1.4, -s * 0.2);
    ctx.quadraticCurveTo(s * 2.0, -s * 0.4 + antWiggle * s, s * 2.4, -s * 0.6 + antWiggle * s * 1.5);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(s * 1.4, s * 0.2);
    ctx.quadraticCurveTo(s * 2.0, s * 0.4 - antWiggle * s, s * 2.4, s * 0.6 - antWiggle * s * 1.5);
    ctx.stroke();

    ctx.fillStyle = '#ff2222';
    ctx.shadowColor = '#ff2222';
    ctx.shadowBlur = 5;
    ctx.beginPath();
    ctx.arc(s * 1.25, -s * 0.28, s * 0.13, 0, Math.PI * 2);
    ctx.arc(s * 1.25, s * 0.28, s * 0.13, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    ctx.strokeStyle = 'rgba(255,60,60,0.4)';
    ctx.lineWidth = 0.8;
    for (let i = -1; i <= 1; i++) {
      ctx.beginPath();
      ctx.moveTo(i * s * 0.4 - s * 0.3, -s * 0.55);
      ctx.lineTo(i * s * 0.4 + s * 0.3, s * 0.55);
      ctx.stroke();
    }

    ctx.restore();
  }
}

function checkLaserHit(x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  const ux = dx / len;
  const uy = dy / len;

  let killedAny = false;
  for (let i = bugs.length - 1; i >= 0; i--) {
    const b = bugs[i];
    const px = b.x - x1;
    const py = b.y - y1;
    const proj = px * ux + py * uy;
    if (proj < 0 || proj > len) continue;
    const cx = x1 + ux * proj;
    const cy = y1 + uy * proj;
    const distToLine = Math.sqrt((b.x - cx) ** 2 + (b.y - cy) ** 2);
    if (distToLine < b.size * 2.2) {
      killBug(i);
      killedAny = true;
    }
  }
  return killedAny;
}

function killBug(index) {
  const b = bugs[index];
  const count = 18;
  for (let i = 0; i < count; i++) {
    const a = (Math.PI * 2 * i) / count + Math.random() * 0.6;
    const s = 3 + Math.random() * 7;
    bugParts.push({
      x: b.x, y: b.y,
      vx: Math.cos(a) * s,
      vy: Math.sin(a) * s,
      size: 1 + Math.random() * 2.5,
      life: 1,
      color: Math.random() < 0.5 ? '#ff0000' : '#ff8888',
    });
  }
  bugs.splice(index, 1);

  const killsEl = document.getElementById('kills');
  if (killsEl) killsEl.textContent = parseInt(killsEl.textContent) + 1;
  updateBugCount();

  if (bugs.length < BUG_MIN) {
    setTimeout(() => {
      for (let i = 0; i < BUG_SPAWN_AMOUNT; i++) bugs.push(createBug());
      updateBugCount();
    }, 800);
  }
}

function updateBugParts() {
  for (let i = bugParts.length - 1; i >= 0; i--) {
    const p = bugParts[i];
    p.x += p.vx;
    p.y += p.vy;
    p.vx *= 0.88;
    p.vy *= 0.88;
    p.vy += 0.15;
    p.life -= 0.045;
    if (p.life <= 0) bugParts.splice(i, 1);
  }
}

function drawBugParts() {
  ctx.globalCompositeOperation = 'lighter';
  for (const p of bugParts) {
    ctx.globalAlpha = p.life;
    const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.size * 4);
    g.addColorStop(0, '#ffffff');
    g.addColorStop(0.3, p.color);
    g.addColorStop(1, 'rgba(255,0,0,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size * 4, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = 'source-over';
}

/* ============ ДРОН: ПОЗИЦИЯ ============ */
function positionElements() {
  const cornerPad = Math.min(W, H) * 0.16;
  drone.R = Math.min(W, H) * 0.10;
  drone.cx = W - cornerPad;
  drone.cy = cornerPad;
}

function resize() {
  W = window.innerWidth;
  H = window.innerHeight;
  canvas.width = W * DPR;
  canvas.height = H * DPR;
  canvas.style.width = W + 'px';
  canvas.style.height = H + 'px';
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  positionElements();
  if (bugs.length === 0) spawnBugs();
}

function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return `rgba(${r},${g},${b},${a})`;
}

/* ============ ОБНОВЛЕНИЕ ДРОНА ============ */
function updateDrone(t) {
  drone.bobPhase = t * 0.002;
  drone.antennaPhase = t * 0.005;
  drone.panelPhase = t * 0.001;
  drone.explode *= 0.9;
  drone.surprise *= 0.98;
  drone.visorGlow += (drone.surprise - drone.visorGlow) * 0.15;
  drone.scanPhase = (t * 0.0009) % 1;

  for (let i = sparkParticles.length - 1; i >= 0; i--) {
    const s = sparkParticles[i];
    s.x += s.vx;
    s.y += s.vy;
    s.vx *= 0.94;
    s.vy *= 0.94;
    s.vy += 0.15;
    s.life -= 0.02;
    if (s.life <= 0) sparkParticles.splice(i, 1);
  }

  for (let i = lasers.length - 1; i >= 0; i--) {
    const l = lasers[i];
    l.life -= 0.11;
    if (l.life <= 0) lasers.splice(i, 1);
  }
}

/* ============ РИСОВАНИЕ SCI-FI ДРОНА ============ */
function drawDrone() {
  const bob = Math.sin(drone.bobPhase) * 6;
  const cx = drone.cx;
  const cy = drone.cy + bob;
  const R = drone.R * (1 + drone.explode * 0.1);

  const glowGrad = ctx.createRadialGradient(cx, cy, R * 0.85, cx, cy, R * 2.2);
  glowGrad.addColorStop(0, 'rgba(255,60,60,0.35)');
  glowGrad.addColorStop(0.5, 'rgba(255,60,60,0.12)');
  glowGrad.addColorStop(1, 'rgba(255,60,60,0)');
  ctx.fillStyle = glowGrad;
  ctx.beginPath();
  ctx.arc(cx, cy, R * 2.2, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = 'rgba(0,0,0,0.4)';
  ctx.beginPath();
  ctx.ellipse(cx, cy + R * 1.35, R * 0.7, R * 0.1, 0, 0, Math.PI * 2);
  ctx.fill();

  const antWave = Math.sin(drone.antennaPhase) * 3;
  ctx.strokeStyle = '#3a1010';
  ctx.lineWidth = 3;
  ctx.lineCap = 'round';
  const ab1 = { x: cx - R * 0.5, y: cy - R * 0.9 };
  const at1 = { x: cx - R * 0.7 + antWave, y: cy - R * 1.5 };
  ctx.beginPath();
  ctx.moveTo(ab1.x, ab1.y);
  ctx.quadraticCurveTo(cx - R * 0.65, cy - R * 1.2, at1.x, at1.y);
  ctx.stroke();
  ctx.fillStyle = '#ff2222';
  ctx.shadowColor = '#ff2222';
  ctx.shadowBlur = 10;
  ctx.beginPath();
  ctx.arc(at1.x, at1.y, 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;

  const ab2 = { x: cx + R * 0.5, y: cy - R * 0.9 };
  const at2 = { x: cx + R * 0.7 - antWave, y: cy - R * 1.5 };
  ctx.beginPath();
  ctx.moveTo(ab2.x, ab2.y);
  ctx.quadraticCurveTo(cx + R * 0.65, cy - R * 1.2, at2.x, at2.y);
  ctx.stroke();
  ctx.fillStyle = '#ff2222';
  ctx.shadowColor = '#ff2222';
  ctx.shadowBlur = 10;
  ctx.beginPath();
  ctx.arc(at2.x, at2.y, 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;

  const bodyGrad = ctx.createRadialGradient(cx - R * 0.3, cy - R * 0.3, R * 0.1, cx, cy, R);
  bodyGrad.addColorStop(0, '#2a2a3a');
  bodyGrad.addColorStop(0.6, '#14141f');
  bodyGrad.addColorStop(1, '#05050a');
  ctx.fillStyle = bodyGrad;
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = '#000000';
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.stroke();

  ctx.strokeStyle = 'rgba(255,50,50,0.9)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(cx, cy, R + 3, 0, Math.PI * 2);
  ctx.stroke();

  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, R * 0.92, 0, Math.PI * 2);
  ctx.stroke();

  for (let i = 0; i < 8; i++) {
    const a = (Math.PI * 2 * i) / 8 + Math.PI / 8;
    const bx = cx + Math.cos(a) * R * 0.86;
    const by = cy + Math.sin(a) * R * 0.86;
    ctx.fillStyle = '#3a3a4a';
    ctx.beginPath();
    ctx.arc(bx, by, 2.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.strokeStyle = 'rgba(0,0,0,0.7)';
    ctx.beginPath();
    ctx.moveTo(bx - 1.5, by);
    ctx.lineTo(bx + 1.5, by);
    ctx.moveTo(bx, by - 1.5);
    ctx.lineTo(bx, by + 1.5);
    ctx.stroke();
  }

  ctx.fillStyle = 'rgba(0,0,0,0.5)';
  ctx.beginPath();
  ctx.arc(cx, cy, R * 0.94, Math.PI * 1.15, Math.PI * 1.85);
  ctx.lineTo(cx, cy);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,60,60,0.4)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, R * 0.94, Math.PI * 1.15, Math.PI * 1.85);
  ctx.stroke();

  ctx.strokeStyle = 'rgba(255,60,60,0.5)';
  ctx.lineWidth = 1;
  for (let i = 0; i < 4; i++) {
    const xOff = R * (0.72 + i * 0.05);
    ctx.beginPath();
    ctx.moveTo(cx + xOff, cy - R * 0.35);
    ctx.lineTo(cx + xOff, cy + R * 0.35);
    ctx.stroke();
  }

  for (let i = 0; i < 4; i++) {
    const xOff = R * (0.72 + i * 0.05);
    ctx.beginPath();
    ctx.moveTo(cx - xOff, cy - R * 0.35);
    ctx.lineTo(cx - xOff, cy + R * 0.35);
    ctx.stroke();
  }

  const finGrad = ctx.createLinearGradient(cx, cy - R * 1.4, cx, cy - R * 0.9);
  finGrad.addColorStop(0, '#ff2222');
  finGrad.addColorStop(0.5, '#7a1010');
  finGrad.addColorStop(1, '#14141f');
  ctx.fillStyle = finGrad;
  ctx.beginPath();
  ctx.moveTo(cx - R * 0.22, cy - R * 0.9);
  ctx.lineTo(cx, cy - R * 1.4);
  ctx.lineTo(cx + R * 0.22, cy - R * 0.9);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = '#000';
  ctx.lineWidth = 2.5;
  ctx.stroke();

  ctx.fillStyle = '#ff2222';
  ctx.shadowColor = '#ff2222';
  ctx.shadowBlur = 6;
  ctx.beginPath();
  ctx.arc(cx, cy - R * 1.2, 2, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;

  const ledY = cy + R * 0.65;
  const ledW = R * 0.7;
  const ledPulse = 0.6 + Math.sin(drone.panelPhase * 2) * 0.4;
  ctx.fillStyle = `rgba(255,40,40,${ledPulse})`;
  ctx.shadowColor = '#ff2222';
  ctx.shadowBlur = 10;
  ctx.fillRect(cx - ledW / 2, ledY - 2, ledW, 4);
  ctx.shadowBlur = 0;

  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, R * 0.9, 0, Math.PI * 2);
  ctx.clip();
  const scanY = cy - R + drone.scanPhase * R * 2;
  const scanGrad = ctx.createLinearGradient(cx - R, scanY, cx + R, scanY);
  scanGrad.addColorStop(0, 'rgba(255,60,60,0)');
  scanGrad.addColorStop(0.5, 'rgba(255,60,60,0.5)');
  scanGrad.addColorStop(1, 'rgba(255,60,60,0)');
  ctx.fillStyle = scanGrad;
  ctx.fillRect(cx - R, scanY - 1, R * 2, 2);
  ctx.restore();

  drawVisor(cx, cy, R);
}

function drawVisor(cx, cy, R) {
  const visorW = R * 1.55;
  const visorH = R * 0.55;
  const visorY = cy - R * 0.05;

  ctx.fillStyle = '#000000';
  ctx.beginPath();
  ctx.ellipse(cx, visorY, visorW / 2, visorH / 2, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = 'rgba(255,50,50,0.9)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.ellipse(cx, visorY, visorW / 2, visorH / 2, 0, 0, Math.PI * 2);
  ctx.stroke();

  ctx.strokeStyle = 'rgba(255,50,50,0.35)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.ellipse(cx, visorY, visorW / 2 - 3, visorH / 2 - 3, 0, 0, Math.PI * 2);
  ctx.stroke();

  ctx.save();
  ctx.beginPath();
  ctx.ellipse(cx, visorY, visorW / 2 - 3, visorH / 2 - 3, 0, 0, Math.PI * 2);
  ctx.clip();

  const scanX = cx - visorW / 2 + drone.scanPhase * visorW;
  const scanGrad = ctx.createLinearGradient(scanX - 30, 0, scanX + 30, 0);
  scanGrad.addColorStop(0, 'rgba(255,0,0,0)');
  scanGrad.addColorStop(0.5, `rgba(255,40,40,${0.7 + drone.visorGlow * 0.3})`);
  scanGrad.addColorStop(1, 'rgba(255,0,0,0)');
  ctx.fillStyle = scanGrad;
  ctx.fillRect(cx - visorW / 2, visorY - visorH / 2, visorW, visorH);

  const eyeOff = R * 0.42;
  const eyeR = R * 0.2;
  const eyeH = R * 0.28;

  for (let side = -1; side <= 1; side += 2) {
    const ex = cx + side * eyeOff;

    const dx = mouse.x - ex;
    const dy = mouse.y - visorY;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const maxShiftX = visorW / 2 - eyeOff - eyeR * 0.5;
    const maxShiftY = visorH / 2 - eyeH * 0.6;
    const shiftX = Math.max(-maxShiftX, Math.min(maxShiftX, (dx / dist) * Math.min(maxShiftX, dist * 0.05)));
    const shiftY = Math.max(-maxShiftY, Math.min(maxShiftY, (dy / dist) * Math.min(maxShiftY, dist * 0.05)));

    const px = ex + shiftX;
    const py = visorY + shiftY;

    if (side === -1) {
      drone.leftPupil.x = px;
      drone.leftPupil.y = py;
    } else {
      drone.rightPupil.x = px;
      drone.rightPupil.y = py;
    }

    const pupilGrad = ctx.createRadialGradient(px, py, 0, px, py, eyeR * 1.5);
    pupilGrad.addColorStop(0, '#ffffff');
    pupilGrad.addColorStop(0.3, '#ff5050');
    pupilGrad.addColorStop(0.7, '#ff0000');
    pupilGrad.addColorStop(1, 'rgba(255,0,0,0)');
    ctx.fillStyle = pupilGrad;
    ctx.beginPath();
    ctx.ellipse(px, py, eyeR * 1.4, eyeH * 1.1, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.ellipse(px, py, eyeR * 0.5, eyeH * 0.6, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(px - eyeR * 1.8, py - 0.8, eyeR * 3.6, 1.6);

    if (drone.surprise > 0.3) {
      ctx.strokeStyle = `rgba(255,0,0,${drone.surprise * 0.7})`;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.ellipse(px, py, eyeR * (1.8 + drone.surprise * 1.5), eyeH * (1.4 + drone.surprise * 0.8), 0, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  ctx.strokeStyle = 'rgba(255,50,50,0.7)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(cx, visorY - visorH / 2 + 2);
  ctx.lineTo(cx, visorY + visorH / 2 - 2);
  ctx.stroke();

  ctx.strokeStyle = 'rgba(255,50,50,0.5)';
  ctx.lineWidth = 1;
  for (let i = 1; i <= 3; i++) {
    const tickX = cx - visorW / 2 + (visorW / 4) * i;
    ctx.beginPath();
    ctx.moveTo(tickX, visorY - visorH / 2 + 2);
    ctx.lineTo(tickX, visorY - visorH / 2 + 5);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(tickX, visorY + visorH / 2 - 2);
    ctx.lineTo(tickX, visorY + visorH / 2 - 5);
    ctx.stroke();
  }

  ctx.restore();

  if (drone.surprise > 0.4) {
    ctx.strokeStyle = `rgba(255,0,0,${drone.surprise * 0.8})`;
    ctx.lineWidth = 3;
    ctx.shadowColor = '#ff0000';
    ctx.shadowBlur = 20 * drone.surprise;
    ctx.beginPath();
    ctx.ellipse(cx, visorY, visorW / 2 + 4, visorH / 2 + 4, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.shadowBlur = 0;
  }
}

/* ============ СЦЕНА ============ */
function drawScene() {
  ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = 'rgba(3,3,10,0.4)';
  ctx.fillRect(0, 0, W, H);

  drawBugs();
  drawBugParts();
  drawLasers();
  drawDrone();

  for (const s of sparkParticles) {
    ctx.globalCompositeOperation = 'lighter';
    const g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.size * 4);
    g.addColorStop(0, s.color);
    g.addColorStop(0.5, hexA(s.color, 0.4));
    g.addColorStop(1, hexA(s.color, 0));
    ctx.globalAlpha = s.life;
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(s.x, s.y, s.size * 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  }
  ctx.globalCompositeOperation = 'source-over';
}

function drawLasers() {
  for (const l of lasers) {
    const alpha = l.life;
    const col = l.color;
    ctx.globalCompositeOperation = 'lighter';

    ctx.strokeStyle = hexA(col, 0.35 * alpha);
    ctx.lineWidth = 14 * alpha + 4;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(l.x1, l.y1);
    ctx.lineTo(l.x2, l.y2);
    ctx.stroke();

    ctx.strokeStyle = hexA(col, 0.85 * alpha);
    ctx.lineWidth = 6 * alpha + 1;
    ctx.beginPath();
    ctx.moveTo(l.x1, l.y1);
    ctx.lineTo(l.x2, l.y2);
    ctx.stroke();

    ctx.strokeStyle = `rgba(255,255,255,${alpha})`;
    ctx.lineWidth = 2 * alpha + 0.8;
    ctx.beginPath();
    ctx.moveTo(l.x1, l.y1);
    ctx.lineTo(l.x2, l.y2);
    ctx.stroke();

    const r = 40 * alpha + 10;
    const g = ctx.createRadialGradient(l.x2, l.y2, 0, l.x2, l.y2, r);
    g.addColorStop(0, `rgba(255,255,255,${alpha})`);
    g.addColorStop(0.3, hexA(col, 0.7 * alpha));
    g.addColorStop(1, hexA(col, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(l.x2, l.y2, r, 0, Math.PI * 2);
    ctx.fill();

    ctx.globalCompositeOperation = 'source-over';
  }
}

function shootLasers(targetX, targetY) {
  const froms = [drone.leftPupil, drone.rightPupil];
  let anyKill = false;
  for (let i = 0; i < froms.length; i++) {
    const f = froms[i];
    if (!f || !f.x) continue;
    lasers.push({
      x1: f.x, y1: f.y,
      x2: targetX, y2: targetY,
      life: 1,
      color: LASER_PALETTE[i % LASER_PALETTE.length],
    });
    if (checkLaserHit(f.x, f.y, targetX, targetY)) anyKill = true;
  }
  if (anyKill) drone.explode = Math.max(drone.explode, 0.4);
}

function triggerExplosion() {
  drone.explode = 1;
  drone.surprise = 1;
  drone.visorGlow = 1;

  const count = 260;
  for (let i = 0; i < count; i++) {
    const angle = (Math.PI * 2 * i) / count + Math.random() * 0.5;
    const speed = 6 + Math.random() * 16;
    sparkParticles.push({
      x: drone.cx, y: drone.cy,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      size: 1 + Math.random() * 3,
      life: 1,
      color: EXPLOSION_PALETTE[Math.floor(Math.random() * EXPLOSION_PALETTE.length)],
    });
  }

  for (let i = 0; i < 8; i++) {
    const angle = (Math.PI * 2 * i) / 8;
    const dist = Math.max(W, H);
    const x2 = drone.cx + Math.cos(angle) * dist;
    const y2 = drone.cy + Math.sin(angle) * dist;
    lasers.push({
      x1: drone.cx, y1: drone.cy,
      x2, y2,
      life: 1,
      color: LASER_PALETTE[i % LASER_PALETTE.length],
    });
    checkLaserHit(drone.cx, drone.cy, x2, y2);
  }

  const flash = document.getElementById('flash');
  flash.classList.remove('active');
  void flash.offsetWidth;
  flash.classList.add('active');
}

/* ============ ЦИКЛ ============ */
let lastT = performance.now();
let bugCheckTimer = 0;
let bugRespawnCooldown = 0;

function loop(t) {
  const dt = t - lastT;
  lastT = t;

  updateDrone(t);
  updateBugs(dt);
  updateBugParts();
  drawScene();

  bugCheckTimer += dt;
  if (bugRespawnCooldown > 0) bugRespawnCooldown -= dt;

  if (bugCheckTimer > 1000 && bugRespawnCooldown <= 0) {
    bugCheckTimer = 0;
    if (bugs.length < BUG_MIN) {
      for (let i = 0; i < BUG_SPAWN_AMOUNT; i++) bugs.push(createBug());
      updateBugCount();
      bugRespawnCooldown = 1500;
    }
  }

  requestAnimationFrame(loop);
}

window.addEventListener('mousemove', e => {
  mouse.x = e.clientX;
  mouse.y = e.clientY;
});
window.addEventListener('touchmove', e => {
  if (e.touches[0]) {
    mouse.x = e.touches[0].clientX;
    mouse.y = e.touches[0].clientY;
  }
});
window.addEventListener('click', e => {
  if (e.target.closest && e.target.closest('.poker-card')) return;
  shootLasers(e.clientX, e.clientY);
});
window.addEventListener('resize', resize);

mouse.x = window.innerWidth / 2;
mouse.y = window.innerHeight / 2;

resize();
requestAnimationFrame(loop);

/* ===================================================================
   ЛОГИКА ПРИЛОЖЕНИЯ
   =================================================================== */
let state = { name:'', room:'', myVote:null, revealed:false };

const CARDS = [
  "0","1","2","3","4","5","6","7","8",
  "9","10","11","12","13","14","15","16",
  "17","18","19","20","21","22","23","24",
  "?","☕"
];

window.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const roomFromUrl = params.get('room');
  if (roomFromUrl) {
    document.getElementById('room-input').value = roomFromUrl;
    document.getElementById('name-input').focus();
  }
  loadRooms();
  setInterval(loadRooms, 3000);
});

function loadRooms() {
  fetch('/api/rooms').then(r => r.json()).then(data => {
    const section = document.getElementById('rooms-section');
    const list = document.getElementById('room-list');
    if (!data.rooms || data.rooms.length === 0) {
      section.classList.add('hidden');
      return;
    }
    section.classList.remove('hidden');
    list.innerHTML = '';
    data.rooms.forEach(r => {
      const item = document.createElement('div');
      item.className = 'room-item';
      item.innerHTML = `<span>▸ ${r.name}</span><span class="count">${r.users} участн.</span>`;
      item.onclick = () => {
        document.getElementById('room-input').value = r.name;
        document.getElementById('name-input').focus();
      };
      list.appendChild(item);
    });
  });
}

function joinRoom() {
  const name = document.getElementById('name-input').value.trim();
  const room = document.getElementById('room-input').value.trim().toLowerCase();
  if (!name || !room) return alert('Введите имя и комнату');
  state.name = name; state.room = room;
  fetch('/api/join', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, room})
  }).then(() => {
    document.getElementById('join-screen').classList.add('hidden');
    document.getElementById('game-screen').classList.remove('hidden');
    document.getElementById('room-name').textContent = room;
    document.getElementById('share-link').value = location.origin + '/?room=' + encodeURIComponent(room);
    buildCards();
    poll();
  });
}

function buildCards() {
  const grid = document.getElementById('cards');
  grid.innerHTML = '';
  CARDS.forEach(c => {
    const el = document.createElement('div');
    el.className = 'poker-card';
    el.textContent = c;
    el.dataset.value = c;
    el.onclick = (e) => {
      el.classList.remove('clicked');
      void el.offsetWidth;
      el.classList.add('clicked');
      setTimeout(() => el.classList.remove('clicked'), 350);
      vote(c);
    };
    grid.appendChild(el);
  });
}

function vote(value) {
  if (state.revealed) return;
  state.myVote = value;
  document.querySelectorAll('.poker-card').forEach(el => {
    el.classList.toggle('selected', el.textContent === value);
  });
  fetch('/api/vote', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({room:state.room, name:state.name, vote:value})
  });
}

function revealResults() {
  fetch('/api/reveal', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({room:state.room})
  });
}

function resetVotes() {
  state.myVote = null;
  state.revealed = false;
  document.querySelectorAll('.poker-card').forEach(el => el.classList.remove('selected'));
  fetch('/api/reset', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({room:state.room})
  });
}

function leaveRoom() {
  fetch('/api/leave', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({room:state.room, name:state.name})
  }).then(() => location.href = '/');
}

function copyLink(e) {
  const input = document.getElementById('share-link');
  input.select();
  document.execCommand('copy');
  const btn = e.target;
  const orig = btn.textContent;
  btn.textContent = '✓ OK';
  setTimeout(() => btn.textContent = orig, 1500);
}

function poll() {
  fetch('/api/state?room=' + encodeURIComponent(state.room) + '&name=' + encodeURIComponent(state.name))
    .then(r => r.json())
    .then(updateUI);
  setTimeout(poll, 1500);
}

function updateUI(data) {
  if (!data.users) return;

  const wasRevealed = state.revealed;
  state.revealed = data.revealed;

  if (data.revealed && !wasRevealed) triggerExplosion();

  document.querySelectorAll('.poker-card').forEach(el => {
    el.style.pointerEvents = data.revealed ? 'none' : 'auto';
    el.style.opacity = data.revealed && el.dataset.value !== state.myVote ? '0.4' : '1';
  });

  const revealBtn = document.getElementById('reveal-btn');
  if (data.revealed) {
    revealBtn.textContent = '🙈 Hide';
    revealBtn.classList.remove('btn-reveal');
    revealBtn.classList.add('btn-hide');
    revealBtn.onclick = resetVotes;
  } else {
    revealBtn.textContent = '👁 Reveal';
    revealBtn.classList.add('btn-reveal');
    revealBtn.classList.remove('btn-hide');
    revealBtn.onclick = revealResults;
  }

  const usersEl = document.getElementById('users');
  usersEl.innerHTML = '';
  let votedCount = 0, total = 0;
  const numericVotes = [];

  for (const [name, vote] of Object.entries(data.users)) {
    total++;
    const hasVoted = vote !== null;
    if (hasVoted) {
      votedCount++;
      const n = parseFloat(vote);
      if (!isNaN(n)) numericVotes.push(n);
    }
    const row = document.createElement('div');
    row.className = 'user-row' + (hasVoted ? ' voted' : '');
    if (data.revealed && !wasRevealed) row.classList.add('just-revealed');

    let badgeHtml;
    if (data.revealed && hasVoted) {
      badgeHtml = `<span class="badge revealed">${vote}</span>`;
    } else if (hasVoted) {
      badgeHtml = `<span class="badge voted">✓ VOTED</span>`;
    } else {
      badgeHtml = `<span class="badge">…WAIT</span>`;
    }

    row.innerHTML = `
      <span>${name === state.name ? '▶ ' + name + ' (вы)' : name}</span>
      ${badgeHtml}`;
    usersEl.appendChild(row);
  }

  document.getElementById('votes-info').textContent =
    data.revealed
      ? `Проголосовало: ${votedCount} / ${total}`
      : `${votedCount} / ${total} · голосуют`;

  const resultEl = document.getElementById('result');
  if (data.revealed && numericVotes.length > 0) {
    const avg = numericVotes.reduce((a,b) => a+b, 0) / numericVotes.length;
    document.getElementById('avg-value').textContent = avg.toFixed(1);
    resultEl.classList.add('ready');
  } else {
    document.getElementById('avg-value').textContent = '—';
    if (!data.revealed) resultEl.classList.remove('ready');
  }
}

['name-input','room-input'].forEach(id => {
  document.getElementById(id).addEventListener('keypress', e => {
    if (e.key === 'Enter') joinRoom();
  });
});
</script>
</body>
</html>
"""


def get_room(rid):
    if rid not in rooms:
        rooms[rid] = {"users": {}, "revealed": False}
    return rooms[rid]


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/api/rooms")
def list_rooms():
    return jsonify({
        "rooms": [
            {"name": n, "users": len(r["users"])}
            for n, r in sorted(rooms.items())
        ]
    })


@app.route("/api/join", methods=["POST"])
def join():
    d = request.json
    get_room(d["room"])["users"][d["name"]] = None
    return jsonify({"ok": True})


@app.route("/api/vote", methods=["POST"])
def vote():
    d = request.json
    r = get_room(d["room"])
    if d["name"] in r["users"] and not r["revealed"]:
        r["users"][d["name"]] = d["vote"]
    return jsonify({"ok": True})


@app.route("/api/reveal", methods=["POST"])
def reveal():
    get_room(request.json["room"])["revealed"] = True
    return jsonify({"ok": True})


@app.route("/api/reset", methods=["POST"])
def reset():
    r = get_room(request.json["room"])
    for n in r["users"]:
        r["users"][n] = None
    r["revealed"] = False
    return jsonify({"ok": True})


@app.route("/api/leave", methods=["POST"])
def leave():
    d = request.json
    r = get_room(d["room"])
    r["users"].pop(d["name"], None)
    if not r["users"]:
        rooms.pop(d["room"], None)
    return jsonify({"ok": True})


@app.route("/api/state")
def state():
    r = get_room(request.args.get("room"))
    return jsonify({"users": r["users"], "revealed": r["revealed"]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)