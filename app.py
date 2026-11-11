from flask import Flask, request, jsonify, render_template_string
import os
import time

app = Flask(__name__)
rooms = {}

CATEGORIES = [
    {
        "id": "backend",
        "name": "Backend",
        "range": "4-7",
        "min": 4,
        "max": 7,
        "tooltip": "<b>0</b> Бэкенд не меняется<br><b>4</b> Изменение существующего API, добавление простого поля<br><b>5</b> Новый endpoint или изменение бизнес-логики сервиса<br><b>6</b> Несколько сервисов, сложная валидация<br><b>7</b> Существенная переработка доменной логики",
    },
    {
        "id": "frontend",
        "name": "Frontend",
        "range": "1-4",
        "min": 1,
        "max": 4,
        "tooltip": "<b>0</b> Нет фронтенда<br><b>1</b> Изменение текста, поля или кнопки<br><b>2</b> Новый небольшой компонент<br><b>3</b> Новая форма или сложный экран<br><b>4</b> Новый пользовательский сценарий, несколько экранов",
    },
    {
        "id": "business",
        "name": "Business Process",
        "range": "4-9",
        "min": 4,
        "max": 9,
        "tooltip": "Под бизнес-процессом понимается изменение того, как работает бизнес.<br><br><b>0</b> Процесс не меняется<br><b>4</b> Небольшое изменение маршрута<br><b>6</b> Изменение нескольких правил<br><b>8</b> Изменение работы нескольких отделов<br><b>9</b> Новый бизнес-процесс",
    },
    {
        "id": "design",
        "name": "Design",
        "range": "1-6",
        "min": 1,
        "max": 6,
        "tooltip": "<b>0</b> Дизайн не меняется<br><b>1</b> Изменение цвета или текста<br><b>2</b> Новая секция<br><b>4</b> Новый Landing Page<br><b>6</b> Полный редизайн сценария",
    },
    {
        "id": "database",
        "name": "DB",
        "range": "3-8",
        "min": 3,
        "max": 8,
        "tooltip": "<b>0</b> База не меняется<br><b>3</b> Добавление столбца<br><b>5</b> Новая таблица<br><b>7</b> Реструктуризация нескольких таблиц<br><b>8</b> Сложная миграция данных",
    },
    {
        "id": "integrations",
        "name": "Integrations",
        "range": "3-9",
        "min": 3,
        "max": 9,
        "tooltip": "<b>0</b> Интеграций нет<br><b>3</b> Изменить существующий API-вызов<br><b>5</b> Подключить новый внешний сервис<br><b>7</b> Несколько систем<br><b>9</b> Критичная интеграция с большим объёмом логики",
    },
]

HOURS_CAT = {
    "id": "hours",
    "name": "Hours",
    "range": "1-21",
    "min": 1,
    "max": 21,
    "tooltip": "Оценка сложности задачи в часах по шкале Фибоначчи:<br>1, 2, 3, 5, 8, 13, 21",
}

PAGE = r"""
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
    background: #03030a; color:#e8e8f0;
    display:flex; flex-direction:column; align-items:center;
    padding:40px 20px; position:relative;
    letter-spacing:.02em; cursor: crosshair;
  }
  .bg-nebula { position:fixed; inset:0; z-index:0; pointer-events:none;
    background: radial-gradient(ellipse 60% 40% at 20% 30%, rgba(120,20,140,0.18), transparent 60%),
                radial-gradient(ellipse 50% 35% at 80% 70%, rgba(20,80,150,0.15), transparent 60%),
                radial-gradient(ellipse 70% 50% at 50% 50%, rgba(60,10,80,0.12), transparent 70%),
                radial-gradient(ellipse at top, #0a0a20 0%, #03030a 60%); }
  .vignette { position:fixed; inset:0; z-index:1; pointer-events:none; background: radial-gradient(ellipse at center, transparent 30%, rgba(3,3,10,0.85) 100%); }
  .scanline { position:fixed; inset:0; z-index:2; pointer-events:none; background: repeating-linear-gradient(to bottom, transparent 0px, transparent 3px, rgba(255,60,60,0.015) 3px, rgba(255,60,60,0.015) 4px); opacity:.6; }
  #bg-canvas { position:fixed; inset:0; z-index:3; pointer-events:none; }
  .content { position:relative; z-index:10; width:100%; display:flex; flex-direction:column; align-items:center; }
  .hud-header { display:flex; align-items:center; gap:14px; margin-bottom:8px; }
  .hud-dot { width:8px; height:8px; border-radius:50%; background:#ff3333; box-shadow: 0 0 12px #ff3333, 0 0 24px #ff3333; animation: pulse 2s ease infinite; }
  @keyframes pulse { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:.4; transform:scale(0.85); } }
  .hud-label { font-family: 'JetBrains Mono',monospace; font-size:.7rem; letter-spacing:.25em; color:#ff5555; text-transform:uppercase; }
  h1 { font-size:2.4rem; font-weight:800; letter-spacing:.05em; background: linear-gradient(135deg,#ffffff 0%,#ff5555 50%,#ff0033 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; text-transform:uppercase; margin: 4px 0 6px; filter: drop-shadow(0 0 30px rgba(255,60,60,0.4)); }
  .subtitle { font-family: 'JetBrains Mono',monospace; color:#5a5a7a; margin-bottom:35px; font-size:.75rem; letter-spacing:.25em; text-transform:uppercase; }
  .card { position:relative; background: linear-gradient(180deg, rgba(10,10,24,0.7), rgba(6,6,16,0.8)); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); border:1px solid rgba(255,80,80,0.22); padding:28px; width:100%; max-width:900px; margin-bottom:20px; clip-path: polygon(0 12px, 12px 0, calc(100% - 12px) 0, 100% 12px, 100% calc(100% - 12px), calc(100% - 12px) 100%, 12px 100%, 0 calc(100% - 12px)); box-shadow: 0 0 60px rgba(255,60,60,0.08), inset 0 0 80px rgba(255,60,60,0.015); }
  .card::before, .card::after { content:''; position:absolute; width:14px; height:14px; border:1px solid #ff5555; }
  .card::before { top:-1px; left:-1px; border-right:0; border-bottom:0; }
  .card::after  { bottom:-1px; right:-1px; border-left:0; border-top:0; }
  .row { display:flex; gap:10px; flex-wrap:wrap; }
  input, button, select { padding:13px 18px; border:none; font-size:.95rem; outline:none; transition:.25s cubic-bezier(.4,0,.2,1); font-family:inherit; letter-spacing:.03em; cursor:default; }
  input, select { flex:1; min-width:150px; background: rgba(255,60,60,0.04); color:#fff; border:1px solid rgba(255,80,80,0.25); clip-path: polygon(0 8px, 8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%); }
  input::placeholder { color:#4a4a6a; }
  input:focus, select:focus { border-color:#ff5555; background: rgba(255,60,60,0.08); box-shadow: 0 0 24px rgba(255,60,60,0.25); }
  select option { background:#03030a; color:#fff; }
  button { cursor:pointer; background: linear-gradient(135deg, #ff3333, #ff7777); color:#04040c; font-weight:700; text-transform:uppercase; font-size:.8rem; letter-spacing:.15em; clip-path: polygon(0 8px, 8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%); }
  button:hover { transform:translateY(-2px); box-shadow: 0 0 30px rgba(255,60,60,0.6), 0 0 60px rgba(255,120,120,0.35); }
  button:active { transform:scale(0.96); }
  button:disabled { opacity: 0.3; cursor: not-allowed; transform:none; box-shadow:none; }
  h3 { font-family: 'JetBrains Mono', monospace; font-size:.75rem; letter-spacing:.25em; text-transform:uppercase; color:#ff5555; margin-bottom:14px; font-weight:500; }
  .mode-picker { display:flex; gap:8px; margin-top:14px; }
  .mode-btn { flex:1; padding:14px 16px; text-align:center; cursor:pointer; border:1px solid rgba(255,80,80,0.3); background: rgba(255,60,60,0.04); color:#e0e8ff; font-family:'JetBrains Mono', monospace; font-size:.8rem; font-weight:700; text-transform:uppercase; letter-spacing:.1em; clip-path: polygon(0 8px, 8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%); transition:.2s; }
  .mode-btn:hover { border-color:#ff5555; background: rgba(255,60,60,0.1); }
  .mode-btn.active { background: linear-gradient(160deg,#ff3333,#ff7777); border-color:#fff; color:#04040c; box-shadow: 0 0 25px rgba(255,60,60,0.6); }
  .mode-btn .sub { font-size:.65rem; opacity:.75; margin-top:4px; font-weight:400; letter-spacing:.05em; }
  .cards-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(48px, 1fr)); gap:6px; margin-top:18px; }
  .poker-card { aspect-ratio: 1 / 1.35; background: linear-gradient(160deg, rgba(255,60,60,0.04), rgba(255,120,120,0.04)); border:1px solid rgba(255,80,80,0.2); display:flex; align-items:center; justify-content:center; font-family: 'JetBrains Mono', monospace; font-size:1.05rem; font-weight:700; cursor:pointer; transition:.2s cubic-bezier(.4,0,.2,1); color:#e0e8ff; clip-path: polygon(0 8px, 8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%); user-select:none; }
  .poker-card:hover { border-color:#ff5555; color:#ff5555; transform:translateY(-4px); box-shadow: 0 0 18px rgba(255,60,60,0.45), inset 0 0 18px rgba(255,60,60,0.1); }
  .poker-card.selected { background: linear-gradient(160deg,#ff3333,#ff7777); border-color:#fff; color:#04040c; transform:translateY(-4px); box-shadow: 0 0 25px rgba(255,60,60,0.7), 0 0 50px rgba(255,120,120,0.5); }
  .mega-cat { background: rgba(255,60,60,0.03); border:1px solid rgba(255,80,80,0.15); padding:14px 16px; margin-bottom:10px; clip-path: polygon(0 8px, 8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%); transition: .25s; }
  .mega-cat.done { border-color: rgba(34,197,94,0.5); background: rgba(34,197,94,0.04); }
  .mega-cat-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; font-family: 'JetBrains Mono', monospace; }
  .mega-cat-name { font-size:.82rem; color:#e0e8ff; letter-spacing:.02em; display:flex; align-items:center; gap:8px; }
  .mega-cat-range { font-size:.7rem; color:#ff5555; letter-spacing:.15em; }
  .mega-cat-options { display:flex; gap:5px; flex-wrap:wrap; }
  .mega-card { min-width:40px; height:44px; padding:0 10px; display:flex; align-items:center; justify-content:center; border:1px solid rgba(255,80,80,0.25); background: rgba(255,60,60,0.04); font-family: 'JetBrains Mono', monospace; font-size:.9rem; font-weight:700; cursor:pointer; transition:.15s; color:#e0e8ff; clip-path: polygon(0 5px, 5px 0, 100% 0, 100% calc(100% - 5px), calc(100% - 5px) 100%, 0 100%); user-select:none; }
  .mega-card:hover { border-color:#ff5555; color:#ff5555; background: rgba(255,60,60,0.12); transform:translateY(-2px); }
  .mega-card.selected { background: linear-gradient(160deg,#ff3333,#ff7777); border-color:#fff; color:#04040c; box-shadow: 0 0 15px rgba(255,60,60,0.6); transform:translateY(-2px); }
  .info-btn { display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; border-radius:50%; background:rgba(255,80,80,0.2); color:#ff5555; font-size:12px; cursor:pointer; border:1px solid rgba(255,80,80,0.5); transition:0.2s; font-weight:900; font-family: sans-serif; }
  .info-btn:hover { background:#ff5555; color:#04040c; }
  .users { margin-top:20px; display:flex; flex-direction:column; gap:8px; }
  .user-row { display:flex; justify-content:space-between; align-items:center; padding:12px 18px; background: rgba(255,60,60,0.03); border:1px solid rgba(255,80,80,0.1); font-family: 'JetBrains Mono', monospace; font-size:.85rem; transition:.3s; clip-path: polygon(0 6px, 6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%); }
  .user-row.voted { border-left:3px solid #22c55e; }
  .user-row.just-revealed { animation: popIn .5s ease; }
  @keyframes popIn { 0% { transform:scale(0.92); opacity:0.4; } 60% { transform:scale(1.03); } 100% { transform:scale(1); opacity:1; } }
  .badge { padding:4px 12px; font-family: 'JetBrains Mono', monospace; font-size:.75rem; background: rgba(255,60,60,0.08); color:#ff5555; border:1px solid rgba(255,80,80,0.3); letter-spacing:.05em; }
  .badge.voted { background: rgba(34,197,94,0.1); color:#4ade80; border-color:rgba(34,197,94,0.4); }
  .badge.partial { background: rgba(255,165,0,0.1); color:#ffb84d; border-color:rgba(255,165,0,0.4); }
  .badge.admin { background: linear-gradient(135deg, #ffd700, #ff8c00); color:#000; border:none; font-weight:800; }
  .result { text-align:center; padding:26px; background: linear-gradient(135deg, rgba(255,60,60,0.05), rgba(255,120,120,0.05)); border:1px solid rgba(255,80,80,0.15); margin-top:20px; transition:.3s; clip-path: polygon(0 14px, 14px 0, calc(100% - 14px) 0, 100% 14px, 100% calc(100% - 14px), calc(100% - 14px) 100%, 14px 100%, 0 calc(100% - 14px)); }
  .result.ready { border-color: rgba(255,60,60,0.5); box-shadow: 0 0 80px rgba(255,60,60,0.25), inset 0 0 40px rgba(255,60,60,0.05); }
  .result .avg { font-family: 'JetBrains Mono', monospace; font-size:3.6rem; font-weight:800; background: linear-gradient(135deg,#ff5555,#ffffff,#ff0033); background-size: 200% 200%; -webkit-background-clip:text; -webkit-text-fill-color:transparent; animation: shiftGrad 4s ease infinite; line-height:1.1; letter-spacing:-.02em; }
  @keyframes shiftGrad { 0%,100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
  .result .label { font-family: 'JetBrains Mono', monospace; color:#5a5a7a; font-size:.75rem; letter-spacing:.25em; text-transform:uppercase; }
  .table-scroll { overflow-x: auto; margin-top:8px; }
  .results-table { width:100%; border-collapse: collapse; font-family: 'JetBrains Mono', monospace; font-size:.85rem; }
  .results-table th, .results-table td { padding:10px 12px; text-align:left; border-bottom:1px solid rgba(255,80,80,0.15); white-space: nowrap; }
  .results-table th { color:#ff5555; font-size:.7rem; letter-spacing:.15em; text-transform:uppercase; font-weight:500; }
  .results-table td { color:#e0e8ff; }
  .results-table td:first-child { font-size:.78rem; color:#c8c8dc; white-space: normal; min-width: 150px; }
  .results-table tfoot td { border-top:2px solid rgba(255,80,80,0.4); border-bottom:none; padding-top:14px; font-weight:700; color:#fff; font-size:1rem; }
  .results-table tfoot td:first-child { color:#ff5555; }
  #total-avg { color:#ff5555; text-shadow: 0 0 12px rgba(255,60,60,0.6); font-size:1.2rem; }
  .results-table th.user-col, .results-table td.user-col { background: rgba(255,60,60,0.04); }
  .results-table th.user-col.me, .results-table td.user-col.me { background: rgba(255,60,60,0.12); }
  .hidden { display:none !important; }
  .footer-note { font-family: 'JetBrains Mono', monospace; color:#3a3a5a; font-size:.7rem; margin-top:12px; text-align:center; letter-spacing:.15em; text-transform:uppercase; }
  .room-list { margin-top:15px; display:flex; flex-direction:column; gap:6px; }
  .room-item { display:flex; justify-content:space-between; align-items:center; padding:12px 18px; background: rgba(255,60,60,0.03); border:1px solid rgba(255,80,80,0.15); cursor:pointer; transition:.25s; font-family: 'JetBrains Mono', monospace; font-size:.85rem; clip-path: polygon(0 6px, 6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%); }
  .room-item:hover { background: rgba(255,60,60,0.1); border-color:#ff5555; transform:translateX(6px); box-shadow: -4px 0 24px rgba(255,60,60,0.4); }
  .room-item .count { color:#ff5555; font-size:.75rem; }
  .room-item .mode-tag { color:#5a5a7a; font-size:.65rem; letter-spacing:.15em; margin-left:8px; }
  .actions-row { display:flex; gap:10px; margin-top:16px; flex-wrap:wrap; align-items:center; }
  .actions-row button { flex:1; padding:14px 18px; min-width: 140px; }
  .btn-reveal { background: linear-gradient(135deg,#22c55e,#ff3333) !important; }
  .btn-hide { background: rgba(255,255,255,0.06) !important; color:#a0a0c0 !important; }
  .btn-download { background: linear-gradient(135deg,#22c55e,#4ade80) !important; color:#04040c !important; }
  .btn-toggle-details { background: rgba(255,60,60,0.15) !important; color: #ff5555 !important; border: 1px solid rgba(255,80,80,0.5) !important; }
  .btn-toggle-details:hover { box-shadow: 0 0 25px rgba(255,60,60,0.4) !important; }
  .timer-box { display:flex; align-items:center; gap:10px; background:rgba(255,60,60,0.05); padding:8px 16px; border:1px solid rgba(255,80,80,0.3); clip-path: polygon(0 6px, 6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%); }
  .timer-display { font-family:'JetBrains Mono', monospace; font-size:1.5rem; font-weight:800; color:#ff5555; min-width: 60px; text-align:center; }
  .timer-display.active { animation: pulseRed 1s infinite alternate; }
  @keyframes pulseRed { from { text-shadow: 0 0 10px rgba(255,60,60,0.4); } to { text-shadow: 0 0 30px rgba(255,60,60,1); color:#fff; } }
  .timer-select { background:transparent; border:1px solid rgba(255,80,80,0.4); color:#fff; padding:6px 10px; font-size:0.8rem; border-radius:4px; cursor:pointer; }
  .share-box { display:flex; gap:8px; margin-top:12px; }
  .share-box input { font-size:.8rem; padding:9px 12px; }
  .share-box button { padding:9px 14px; font-size:.7rem; }
  .room-header { display:flex; justify-content:space-between; align-items:center; padding-bottom:18px; margin-bottom:18px; border-bottom:1px solid rgba(255,80,80,0.1); }
  .room-header .label-sm { font-family: 'JetBrains Mono', monospace; font-size:.7rem; color:#5a5a7a; letter-spacing:.25em; text-transform:uppercase; }
  .room-header .label-sm .mode-badge { display:inline-block; padding:2px 8px; margin-left:8px; background: rgba(255,60,60,0.15); color:#ff5555; border:1px solid rgba(255,80,80,0.4); font-size:.65rem; }
  .room-header .label-sm .mode-badge.mega { background: linear-gradient(135deg,#ff3333,#ff7777); color:#04040c; border-color:#fff; box-shadow: 0 0 12px rgba(255,60,60,0.6); }
  .room-header .room-name { font-family: 'JetBrains Mono', monospace; font-size:1.3rem; font-weight:700; color:#ff5555; text-shadow: 0 0 20px rgba(255,60,60,0.6); letter-spacing:.05em; }
  .flash-overlay { position:fixed; inset:0; background: radial-gradient(circle at center, rgba(255,0,50,0.5), rgba(255,100,100,0.3), transparent 70%); pointer-events:none; z-index:100; opacity:0; mix-blend-mode:screen; }
  .flash-overlay.active { animation: flashBang 0.5s ease-out; }
  @keyframes flashBang { 0% { opacity:1; transform:scale(0.3); } 100% { opacity:0; transform:scale(3); } }
  #kill-counter { position:fixed; bottom:20px; right:24px; font-family: 'JetBrains Mono', monospace; font-size:.75rem; letter-spacing:.2em; color:#ff5555; text-transform:uppercase; z-index:20; padding:8px 14px; background: rgba(10,10,24,0.6); backdrop-filter: blur(8px); border:1px solid rgba(255,80,80,0.3); clip-path: polygon(0 6px, 6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%); pointer-events:none; text-shadow: 0 0 10px rgba(255,60,60,0.6); }
  #kill-counter span { color:#ffffff; font-weight:700; }
  
  .modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.8); backdrop-filter:blur(5px); z-index:1000; display:flex; align-items:center; justify-content:center; opacity:0; pointer-events:none; transition:0.3s; }
  .modal-overlay.active { opacity:1; pointer-events:auto; }
  #tooltip-modal { z-index: 1100 !important; }
  .modal-content { position: relative; background:linear-gradient(180deg, rgba(20,20,40,0.95), rgba(10,10,24,0.95)); border:1px solid rgba(255,80,80,0.4); padding:30px; width:100%; max-width:600px; max-height:90vh; overflow-y:auto; clip-path: polygon(0 15px, 15px 0, calc(100% - 15px) 0, 100% 15px, 100% calc(100% - 15px), calc(100% - 15px) 100%, 15px 100%, 0 calc(100% - 15px)); box-shadow: 0 0 100px rgba(255,60,60,0.15); transform:translateY(20px); transition:0.3s; }
  .modal-overlay.active .modal-content { transform:translateY(0); }
  .modal-close { position: absolute; top: 15px; right: 15px; font-size: 24px; line-height: 1; color: #ff5555; cursor: pointer; transition: 0.2s; background: none; border: none; padding: 5px; }
  .modal-close:hover { color: #fff; transform: scale(1.2); }
  .modal-title { font-family:'JetBrains Mono',monospace; font-size:1.2rem; color:#ff5555; margin-bottom:20px; text-transform:uppercase; letter-spacing:.1em; text-align:center; }
  .tooltip-content { font-size:0.9rem; line-height:1.6; color:#d0d0e0; font-family:'Inter',sans-serif; }
  .tooltip-content b { color:#fff; font-family:'JetBrains Mono',monospace; display:inline-block; width:20px; }
  .form-grid { display:grid; grid-template-columns: 1fr 1fr; gap:15px; margin-bottom:20px; }
  .form-group { display:flex; flex-direction:column; gap:5px; }
  .form-group label { font-size:0.75rem; font-family:'JetBrains Mono',monospace; color:#aaa; text-transform:uppercase; letter-spacing:.05em; display:flex; justify-content:space-between; align-items:center; }
  .form-group input { padding:10px; font-size:1rem; }
  .form-group input.edited { border-color:#22c55e; background:rgba(34,197,94,0.1); color:#4ade80; font-weight:bold; }
  @media (max-width:600px) {
    .cards-grid { grid-template-columns: repeat(auto-fit, minmax(42px, 1fr)); }
    .poker-card { font-size:.9rem; }
    .card { padding:20px; }
    #kill-counter { bottom:10px; right:10px; font-size:.65rem; }
    .mega-cat-name { font-size:.72rem; }
    .mega-card { min-width:34px; height:38px; font-size:.8rem; padding:0 8px; }
    .results-table th, .results-table td { padding:8px; font-size:.75rem; }
    .form-grid { grid-template-columns: 1fr; }
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
    <div class="hud-label">DRONE OPS · v10.4</div>
  </div>
  <h1>Planning Poker</h1>
  <p class="subtitle">// estimate · vote · reveal · excel //</p>

  <div class="card" id="join-screen">
    <h3>[ ВХОД В КОМНАТУ ]</h3>
    <div class="row">
      <input id="name-input" placeholder="Имя оператора" maxlength="20">
      <input id="room-input" placeholder="ID комнаты" maxlength="20">
    </div>
    <p style="margin-top:16px; color:#5a5a7a; font-size:.72rem; font-family:'JetBrains Mono',monospace; letter-spacing:.2em; text-transform:uppercase;">// режим оценки</p>
    <div class="mode-picker">
      <div class="mode-btn active" data-mode="normal" onclick="pickMode('normal')">
        Обычный
        <div class="sub">1 оценка · 0–24</div>
      </div>
      <div class="mode-btn" data-mode="mega" onclick="pickMode('mega')">
        Мега сложный
        <div class="sub">6 категорий + часы</div>
      </div>
    </div>
    <div class="row" style="margin-top:16px;">
      <button onclick="joinRoom()" style="width:100%;">Войти →</button>
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
          <div class="label-sm">Комната <span class="mode-badge" id="mode-badge">ОБЫЧНЫЙ</span></div>
          <div class="room-name" id="room-name"></div>
        </div>
        <button onclick="leaveRoom()" style="background:rgba(255,60,60,0.12); color:#ff5555; border:1px solid rgba(255,80,80,0.4);">Выйти</button>
      </div>

      <div class="share-box">
        <input id="share-link" readonly>
        <button onclick="copyLink(event)">📋 Copy</button>
      </div>

      <div id="normal-mode">
        <h3 style="margin-top:26px;">[ ВЫБЕРИТЕ ОЦЕНКУ ]</h3>
        <div class="cards-grid" id="cards"></div>
      </div>

      <div id="mega-mode" class="hidden">
        <h3 style="margin-top:26px;">[ ОЦЕНКА ПО КАТЕГОРИЯМ ]</h3>
        <div id="mega-categories"></div>
      </div>

      <div class="actions-row">
        <div class="timer-box hidden" id="timer-box">
          <select id="timer-select" class="timer-select" onchange="updateTimerSetting()">
            <option value="5">5 сек</option>
            <option value="10">10 сек</option>
            <option value="15">15 сек</option>
            <option value="20" selected>20 сек</option>
            <option value="25">25 сек</option>
            <option value="30">30 сек</option>
            <option value="45">45 сек</option>
            <option value="60">60 сек</option>
          </select>
          <div class="timer-display" id="timer-display">20</div>
          <button id="timer-start-btn" onclick="startTimer()" style="padding:8px 12px; font-size:0.7rem;">▶</button>
        </div>
        <button id="reveal-btn" class="btn-reveal" onclick="revealResults()">👁 Reveal</button>
        <button id="reset-btn" onclick="resetVotes()" class="btn-hide">🔄 Reset</button>
      </div>

      <div class="result" id="result">
        <div class="label">Средняя оценка</div>
        <div class="avg" id="avg-value">—</div>
        <div class="label" id="votes-info">Ожидание…</div>
      </div>

      <div class="result hidden" id="mega-result">
        <div class="label" style="margin-bottom:16px;">Результаты по категориям</div>
        <div class="table-scroll">
          <table class="results-table" id="results-table">
            <thead id="results-thead"></thead>
            <tbody id="results-tbody"></tbody>
            <tfoot id="results-tfoot"></tfoot>
          </table>
        </div>
        <div class="actions-row" style="margin-top:18px;">
          <button id="toggle-details-btn" class="btn-toggle-details" onclick="toggleDetails()">👥 Голоса команды</button>
          <button id="save-btn" class="btn-download" onclick="openSaveModal()" style="display:none;">💾 Сохранить</button>
        </div>
        <div class="label" id="mega-votes-info" style="margin-top:14px;">Ожидание…</div>
      </div>

      <h3 style="margin-top:26px;">[ УЧАСТНИКИ ]</h3>
      <div class="users" id="users"></div>
    </div>
  </div>
</div>

<div class="modal-overlay" id="tooltip-modal" onclick="closeModal('tooltip-modal')">
  <div class="modal-content" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="closeModal('tooltip-modal')">×</button>
    <div class="modal-title" id="tooltip-title">Информация</div>
    <div class="tooltip-content" id="tooltip-body"></div>
  </div>
</div>

<div class="modal-overlay" id="save-modal" onclick="closeModal('save-modal')">
  <div class="modal-content" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="closeModal('save-modal')">×</button>
    <div class="modal-title">Сохранение в Excel</div>
    <div class="form-grid" id="save-form-fields"></div>
    <div class="actions-row" style="margin-top:20px;">
      <button onclick="closeModal('save-modal')" class="btn-hide">Отмена</button>
      <button onclick="downloadExcel()" class="btn-download">💾 Скачать</button>
    </div>
  </div>
</div>

<script>
/* ===================================================================
   SCI-FI DRONE + RED LASERS + CRAWLING BUGS
   =================================================================== */
const canvas = document.getElementById('bg-canvas');
const ctx = canvas.getContext('2d');
let W = 0, H = 0;
let DPR = Math.min(window.devicePixelRatio || 1, 2);
const mouse = { x: 0, y: 0 };

let drone = {
  cx: 0, cy: 0, R: 90, bobPhase: 0, surprise: 0, explode: 0, visorGlow: 0, scanPhase: 0,
  leftPupil: { x: 0, y: 0 }, rightPupil: { x: 0, y: 0 }, antennaPhase: 0, panelPhase: 0,
};
const sparkParticles = [], lasers = [], bugs = [], bugParts = [];
const LASER_PALETTE = ['#ff0000', '#ff2222', '#ff4444'];
const EXPLOSION_PALETTE = ['#ffffff', '#ff5555', '#ff0033', '#ff8888'];
const BUG_COUNT = 50, BUG_MIN = 40, BUG_SPAWN_AMOUNT = 30;

function createBug() {
  const angle = Math.random() * Math.PI * 2;
  const speed = 0.25 + Math.random() * 0.55;
  return { x: Math.random() * W, y: Math.random() * H, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, size: 5 + Math.random() * 3.5, legPhase: Math.random() * Math.PI * 2, legSpeed: 0.35 + Math.random() * 0.25, bodyAngle: angle, pauseTimer: 0, pauseCd: 120 + Math.random() * 300, isPaused: false, turnTimer: 0, turnCd: 80 + Math.random() * 150 };
}
function spawnBugs() { bugs.length = 0; for (let i = 0; i < BUG_COUNT; i++) bugs.push(createBug()); updateBugCount(); }
function updateBugCount() { const el = document.getElementById('bug-count'); if (el) el.textContent = bugs.length; }

function updateBugs(dt) {
  for (const b of bugs) {
    b.pauseTimer++;
    if (b.pauseTimer > b.pauseCd) { b.pauseTimer = 0; b.pauseCd = 120 + Math.random() * 300; b.isPaused = !b.isPaused; }
    if (b.isPaused) { b.vx *= 0.9; b.vy *= 0.9; }
    else {
      b.turnTimer++;
      if (b.turnTimer > b.turnCd) {
        b.turnTimer = 0; b.turnCd = 80 + Math.random() * 150;
        const angle = Math.atan2(b.vy, b.vx);
        const newAngle = angle + (Math.random() - 0.5) * 0.7;
        const s = Math.sqrt(b.vx * b.vx + b.vy * b.vy) || 0.4;
        b.vx = Math.cos(newAngle) * s; b.vy = Math.sin(newAngle) * s;
      }
    }
    const spd = Math.sqrt(b.vx * b.vx + b.vy * b.vy);
    if (spd > 1.2) { b.vx = (b.vx / spd) * 1.2; b.vy = (b.vy / spd) * 1.2; }
    b.vx *= 0.97; b.vy *= 0.97;
    b.x += b.vx; b.y += b.vy;
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
    if (!b.isPaused && spd > 0.1) b.legPhase += b.legSpeed;
    const dx = b.x - mouse.x; const dy = b.y - mouse.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    if (dist < 100) { const push = (100 - dist) / 100 * 0.8; b.vx += (dx / dist) * push; b.vy += (dy / dist) * push; }
  }
}

function drawBugs() {
  for (const b of bugs) {
    ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.bodyAngle);
    const s = b.size;
    const legPairs = [
      { xOffset: -s * 0.5, length: s * 1.3, baseAngle: -Math.PI * 0.75 },
      { xOffset: 0, length: s * 1.4, baseAngle: -Math.PI * 0.55 },
      { xOffset: s * 0.5, length: s * 1.2, baseAngle: -Math.PI * 0.35 },
      { xOffset: -s * 0.5, length: s * 1.3, baseAngle: Math.PI * 0.75 },
      { xOffset: 0, length: s * 1.4, baseAngle: Math.PI * 0.55 },
      { xOffset: s * 0.5, length: s * 1.2, baseAngle: Math.PI * 0.35 },
    ];
    ctx.strokeStyle = '#3a1a1a'; ctx.lineWidth = 1.6; ctx.lineCap = 'round';
    legPairs.forEach((leg, i) => {
      const phase = b.legPhase + (i % 2 === 0 ? 0 : Math.PI) + (i >= 3 ? Math.PI : 0);
      const stepAmp = Math.sin(phase) * 0.35;
      const kneeAngle = leg.baseAngle + stepAmp * 0.6;
      const kneeX = leg.xOffset + Math.cos(kneeAngle) * leg.length * 0.5;
      const kneeY = Math.sin(kneeAngle) * leg.length * 0.5;
      const footAngle = leg.baseAngle + stepAmp;
      const footX = kneeX + Math.cos(footAngle) * leg.length * 0.5;
      const footY = kneeY + Math.sin(footAngle) * leg.length * 0.5;
      ctx.beginPath(); ctx.moveTo(leg.xOffset, 0); ctx.lineTo(kneeX, kneeY); ctx.lineTo(footX, footY); ctx.stroke();
    });
    const bodyGrad = ctx.createRadialGradient(-s * 0.2, -s * 0.2, 0, 0, 0, s * 1.3);
    bodyGrad.addColorStop(0, '#3a1010'); bodyGrad.addColorStop(0.7, '#1a0808'); bodyGrad.addColorStop(1, '#000000');
    ctx.fillStyle = bodyGrad;
    ctx.beginPath(); ctx.ellipse(0, 0, s * 1.1, s * 0.75, 0, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = 'rgba(255,60,60,0.85)'; ctx.lineWidth = 1.2; ctx.stroke();
    ctx.fillStyle = '#1a0808';
    ctx.beginPath(); ctx.arc(s * 1.1, 0, s * 0.55, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = 'rgba(255,60,60,0.85)'; ctx.stroke();
    ctx.strokeStyle = 'rgba(255,80,80,0.9)'; ctx.lineWidth = 1;
    const antWiggle = Math.sin(b.legPhase * 1.5) * 0.15;
    ctx.beginPath(); ctx.moveTo(s * 1.4, -s * 0.2); ctx.quadraticCurveTo(s * 2.0, -s * 0.4 + antWiggle * s, s * 2.4, -s * 0.6 + antWiggle * s * 1.5); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(s * 1.4, s * 0.2); ctx.quadraticCurveTo(s * 2.0, s * 0.4 - antWiggle * s, s * 2.4, s * 0.6 - antWiggle * s * 1.5); ctx.stroke();
    ctx.fillStyle = '#ff2222'; ctx.shadowColor = '#ff2222'; ctx.shadowBlur = 5;
    ctx.beginPath(); ctx.arc(s * 1.25, -s * 0.28, s * 0.13, 0, Math.PI * 2); ctx.arc(s * 1.25, s * 0.28, s * 0.13, 0, Math.PI * 2); ctx.fill();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = 'rgba(255,60,60,0.4)'; ctx.lineWidth = 0.8;
    for (let i = -1; i <= 1; i++) { ctx.beginPath(); ctx.moveTo(i * s * 0.4 - s * 0.3, -s * 0.55); ctx.lineTo(i * s * 0.4 + s * 0.3, s * 0.55); ctx.stroke(); }
    ctx.restore();
  }
}

function checkLaserHit(x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  const ux = dx / len, uy = dy / len;
  let killedAny = false;
  for (let i = bugs.length - 1; i >= 0; i--) {
    const b = bugs[i];
    if (!b) continue;
    const px = b.x - x1, py = b.y - y1;
    const proj = px * ux + py * uy;
    if (proj < 0 || proj > len) continue;
    const cx = x1 + ux * proj, cy = y1 + uy * proj;
    const distToLine = Math.sqrt((b.x - cx) ** 2 + (b.y - cy) ** 2);
    if (distToLine < b.size * 2.2) { killBug(i); killedAny = true; }
  }
  return killedAny;
}

function killBug(index) {
  if (index < 0 || index >= bugs.length) return;
  const b = bugs[index];
  if (!b) return;
  const count = 18;
  for (let i = 0; i < count; i++) {
    const a = (Math.PI * 2 * i) / count + Math.random() * 0.6;
    const s = 3 + Math.random() * 7;
    bugParts.push({ x: b.x, y: b.y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, size: 1 + Math.random() * 2.5, life: 1, color: Math.random() < 0.5 ? '#ff0000' : '#ff8888' });
  }
  bugs.splice(index, 1);
  const killsEl = document.getElementById('kills');
  if (killsEl) killsEl.textContent = parseInt(killsEl.textContent) + 1;
  updateBugCount();
}

function updateBugParts() {
  for (let i = bugParts.length - 1; i >= 0; i--) {
    const p = bugParts[i];
    p.x += p.vx; p.y += p.vy; p.vx *= 0.88; p.vy *= 0.88; p.vy += 0.15; p.life -= 0.045;
    if (p.life <= 0) bugParts.splice(i, 1);
  }
}

function drawBugParts() {
  ctx.globalCompositeOperation = 'lighter';
  for (const p of bugParts) {
    ctx.globalAlpha = p.life;
    const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.size * 4);
    g.addColorStop(0, '#ffffff'); g.addColorStop(0.3, p.color); g.addColorStop(1, 'rgba(255,0,0,0)');
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.x, p.y, p.size * 4, 0, Math.PI * 2); ctx.fill();
  }
  ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
}

function positionElements() { const cornerPad = Math.min(W, H) * 0.16; drone.R = Math.min(W, H) * 0.10; drone.cx = W - cornerPad; drone.cy = cornerPad; }
function resize() { W = window.innerWidth; H = window.innerHeight; canvas.width = W * DPR; canvas.height = H * DPR; canvas.style.width = W + 'px'; canvas.style.height = H + 'px'; ctx.setTransform(DPR, 0, 0, DPR, 0, 0); positionElements(); if (bugs.length === 0) spawnBugs(); }
function hexA(hex, a) { const n = parseInt(hex.slice(1), 16); const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255; return `rgba(${r},${g},${b},${a})`; }

function updateDrone(t) {
  drone.bobPhase = t * 0.002; drone.antennaPhase = t * 0.005; drone.panelPhase = t * 0.001;
  drone.explode *= 0.9; drone.surprise *= 0.98; drone.visorGlow += (drone.surprise - drone.visorGlow) * 0.15; drone.scanPhase = (t * 0.0009) % 1;
  for (let i = sparkParticles.length - 1; i >= 0; i--) { const s = sparkParticles[i]; s.x += s.vx; s.y += s.vy; s.vx *= 0.94; s.vy *= 0.94; s.vy += 0.15; s.life -= 0.02; if (s.life <= 0) sparkParticles.splice(i, 1); }
  for (let i = lasers.length - 1; i >= 0; i--) { lasers[i].life -= 0.11; if (lasers[i].life <= 0) lasers.splice(i, 1); }
}

function drawDrone() {
  const bob = Math.sin(drone.bobPhase) * 6;
  const cx = drone.cx, cy = drone.cy + bob;
  const R = drone.R * (1 + drone.explode * 0.1);
  const glowGrad = ctx.createRadialGradient(cx, cy, R * 0.85, cx, cy, R * 2.2);
  glowGrad.addColorStop(0, 'rgba(255,60,60,0.35)'); glowGrad.addColorStop(0.5, 'rgba(255,60,60,0.12)'); glowGrad.addColorStop(1, 'rgba(255,60,60,0)');
  ctx.fillStyle = glowGrad; ctx.beginPath(); ctx.arc(cx, cy, R * 2.2, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = 'rgba(0,0,0,0.4)'; ctx.beginPath(); ctx.ellipse(cx, cy + R * 1.35, R * 0.7, R * 0.1, 0, 0, Math.PI * 2); ctx.fill();
  const antWave = Math.sin(drone.antennaPhase) * 3;
  ctx.strokeStyle = '#3a1010'; ctx.lineWidth = 3; ctx.lineCap = 'round';
  const at1 = { x: cx - R * 0.7 + antWave, y: cy - R * 1.5 };
  ctx.beginPath(); ctx.moveTo(cx - R * 0.5, cy - R * 0.9); ctx.quadraticCurveTo(cx - R * 0.65, cy - R * 1.2, at1.x, at1.y); ctx.stroke();
  ctx.fillStyle = '#ff2222'; ctx.shadowColor = '#ff2222'; ctx.shadowBlur = 10; ctx.beginPath(); ctx.arc(at1.x, at1.y, 3, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0;
  const at2 = { x: cx + R * 0.7 - antWave, y: cy - R * 1.5 };
  ctx.beginPath(); ctx.moveTo(cx + R * 0.5, cy - R * 0.9); ctx.quadraticCurveTo(cx + R * 0.65, cy - R * 1.2, at2.x, at2.y); ctx.stroke();
  ctx.fillStyle = '#ff2222'; ctx.shadowColor = '#ff2222'; ctx.shadowBlur = 10; ctx.beginPath(); ctx.arc(at2.x, at2.y, 3, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0;
  const bodyGrad = ctx.createRadialGradient(cx - R * 0.3, cy - R * 0.3, R * 0.1, cx, cy, R);
  bodyGrad.addColorStop(0, '#2a2a3a'); bodyGrad.addColorStop(0.6, '#14141f'); bodyGrad.addColorStop(1, '#05050a');
  ctx.fillStyle = bodyGrad; ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = '#000000'; ctx.lineWidth = 5; ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
  ctx.strokeStyle = 'rgba(255,50,50,0.9)'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(cx, cy, R + 3, 0, Math.PI * 2); ctx.stroke();
  ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(cx, cy, R * 0.92, 0, Math.PI * 2); ctx.stroke();
  for (let i = 0; i < 8; i++) {
    const a = (Math.PI * 2 * i) / 8 + Math.PI / 8;
    const bx = cx + Math.cos(a) * R * 0.86, by = cy + Math.sin(a) * R * 0.86;
    ctx.fillStyle = '#3a3a4a'; ctx.beginPath(); ctx.arc(bx, by, 2.5, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = '#000'; ctx.lineWidth = 1; ctx.stroke();
    ctx.strokeStyle = 'rgba(0,0,0,0.7)'; ctx.beginPath(); ctx.moveTo(bx - 1.5, by); ctx.lineTo(bx + 1.5, by); ctx.moveTo(bx, by - 1.5); ctx.lineTo(bx, by + 1.5); ctx.stroke();
  }
  ctx.fillStyle = 'rgba(0,0,0,0.5)'; ctx.beginPath(); ctx.arc(cx, cy, R * 0.94, Math.PI * 1.15, Math.PI * 1.85); ctx.lineTo(cx, cy); ctx.closePath(); ctx.fill();
  ctx.strokeStyle = 'rgba(255,60,60,0.4)'; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(cx, cy, R * 0.94, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke();
  ctx.strokeStyle = 'rgba(255,60,60,0.5)'; ctx.lineWidth = 1;
  for (let i = 0; i < 4; i++) {
    const xOff = R * (0.72 + i * 0.05);
    ctx.beginPath(); ctx.moveTo(cx + xOff, cy - R * 0.35); ctx.lineTo(cx + xOff, cy + R * 0.35); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx - xOff, cy - R * 0.35); ctx.lineTo(cx - xOff, cy + R * 0.35); ctx.stroke();
  }
  const finGrad = ctx.createLinearGradient(cx, cy - R * 1.4, cx, cy - R * 0.9);
  finGrad.addColorStop(0, '#ff2222'); finGrad.addColorStop(0.5, '#7a1010'); finGrad.addColorStop(1, '#14141f');
  ctx.fillStyle = finGrad; ctx.beginPath(); ctx.moveTo(cx - R * 0.22, cy - R * 0.9); ctx.lineTo(cx, cy - R * 1.4); ctx.lineTo(cx + R * 0.22, cy - R * 0.9); ctx.closePath(); ctx.fill();
  ctx.strokeStyle = '#000'; ctx.lineWidth = 2.5; ctx.stroke();
  ctx.fillStyle = '#ff2222'; ctx.shadowColor = '#ff2222'; ctx.shadowBlur = 6; ctx.beginPath(); ctx.arc(cx, cy - R * 1.2, 2, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0;
  const ledY = cy + R * 0.65, ledW = R * 0.7;
  const ledPulse = 0.6 + Math.sin(drone.panelPhase * 2) * 0.4;
  ctx.fillStyle = `rgba(255,40,40,${ledPulse})`; ctx.shadowColor = '#ff2222'; ctx.shadowBlur = 10; ctx.fillRect(cx - ledW / 2, ledY - 2, ledW, 4); ctx.shadowBlur = 0;
  ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, R * 0.9, 0, Math.PI * 2); ctx.clip();
  const scanY = cy - R + drone.scanPhase * R * 2;
  const scanGrad = ctx.createLinearGradient(cx - R, scanY, cx + R, scanY);
  scanGrad.addColorStop(0, 'rgba(255,60,60,0)'); scanGrad.addColorStop(0.5, 'rgba(255,60,60,0.5)'); scanGrad.addColorStop(1, 'rgba(255,60,60,0)');
  ctx.fillStyle = scanGrad; ctx.fillRect(cx - R, scanY - 1, R * 2, 2); ctx.restore();
  drawVisor(cx, cy, R);
}

function drawVisor(cx, cy, R) {
  const visorW = R * 1.55, visorH = R * 0.55, visorY = cy - R * 0.05;
  ctx.fillStyle = '#000000'; ctx.beginPath(); ctx.ellipse(cx, visorY, visorW / 2, visorH / 2, 0, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = 'rgba(255,50,50,0.9)'; ctx.lineWidth = 2; ctx.beginPath(); ctx.ellipse(cx, visorY, visorW / 2, visorH / 2, 0, 0, Math.PI * 2); ctx.stroke();
  ctx.strokeStyle = 'rgba(255,50,50,0.35)'; ctx.lineWidth = 1; ctx.beginPath(); ctx.ellipse(cx, visorY, visorW / 2 - 3, visorH / 2 - 3, 0, 0, Math.PI * 2); ctx.stroke();
  ctx.save(); ctx.beginPath(); ctx.ellipse(cx, visorY, visorW / 2 - 3, visorH / 2 - 3, 0, 0, Math.PI * 2); ctx.clip();
  const scanX = cx - visorW / 2 + drone.scanPhase * visorW;
  const scanGrad = ctx.createLinearGradient(scanX - 30, 0, scanX + 30, 0);
  scanGrad.addColorStop(0, 'rgba(255,0,0,0)'); scanGrad.addColorStop(0.5, `rgba(255,40,40,${0.7 + drone.visorGlow * 0.3})`); scanGrad.addColorStop(1, 'rgba(255,0,0,0)');
  ctx.fillStyle = scanGrad; ctx.fillRect(cx - visorW / 2, visorY - visorH / 2, visorW, visorH);
  const eyeOff = R * 0.42, eyeR = R * 0.2, eyeH = R * 0.28;
  for (let side = -1; side <= 1; side += 2) {
    const ex = cx + side * eyeOff;
    const dx = mouse.x - ex, dy = mouse.y - visorY;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const maxShiftX = visorW / 2 - eyeOff - eyeR * 0.5;
    const maxShiftY = visorH / 2 - eyeH * 0.6;
    const shiftX = Math.max(-maxShiftX, Math.min(maxShiftX, (dx / dist) * Math.min(maxShiftX, dist * 0.05)));
    const shiftY = Math.max(-maxShiftY, Math.min(maxShiftY, (dy / dist) * Math.min(maxShiftY, dist * 0.05)));
    const px = ex + shiftX, py = visorY + shiftY;
    if (side === -1) { drone.leftPupil.x = px; drone.leftPupil.y = py; } else { drone.rightPupil.x = px; drone.rightPupil.y = py; }
    const pupilGrad = ctx.createRadialGradient(px, py, 0, px, py, eyeR * 1.5);
    pupilGrad.addColorStop(0, '#ffffff'); pupilGrad.addColorStop(0.3, '#ff5050'); pupilGrad.addColorStop(0.7, '#ff0000'); pupilGrad.addColorStop(1, 'rgba(255,0,0,0)');
    ctx.fillStyle = pupilGrad; ctx.beginPath(); ctx.ellipse(px, py, eyeR * 1.4, eyeH * 1.1, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#ffffff'; ctx.beginPath(); ctx.ellipse(px, py, eyeR * 0.5, eyeH * 0.6, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = 'rgba(0,0,0,0.6)'; ctx.fillRect(px - eyeR * 1.8, py - 0.8, eyeR * 3.6, 1.6);
    if (drone.surprise > 0.3) {
      ctx.strokeStyle = `rgba(255,0,0,${drone.surprise * 0.7})`; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.ellipse(px, py, eyeR * (1.8 + drone.surprise * 1.5), eyeH * (1.4 + drone.surprise * 0.8), 0, 0, Math.PI * 2); ctx.stroke();
    }
  }
  ctx.strokeStyle = 'rgba(255,50,50,0.7)'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(cx, visorY - visorH / 2 + 2); ctx.lineTo(cx, visorY + visorH / 2 - 2); ctx.stroke();
  ctx.strokeStyle = 'rgba(255,50,50,0.5)'; ctx.lineWidth = 1;
  for (let i = 1; i <= 3; i++) {
    const tickX = cx - visorW / 2 + (visorW / 4) * i;
    ctx.beginPath(); ctx.moveTo(tickX, visorY - visorH / 2 + 2); ctx.lineTo(tickX, visorY - visorH / 2 + 5); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(tickX, visorY + visorH / 2 - 2); ctx.lineTo(tickX, visorY + visorH / 2 - 5); ctx.stroke();
  }
  ctx.restore();
  if (drone.surprise > 0.4) {
    ctx.strokeStyle = `rgba(255,0,0,${drone.surprise * 0.8})`; ctx.lineWidth = 3; ctx.shadowColor = '#ff0000'; ctx.shadowBlur = 20 * drone.surprise;
    ctx.beginPath(); ctx.ellipse(cx, visorY, visorW / 2 + 4, visorH / 2 + 4, 0, 0, Math.PI * 2); ctx.stroke(); ctx.shadowBlur = 0;
  }
}

function drawScene() {
  ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = 'rgba(3,3,10,0.4)'; ctx.fillRect(0, 0, W, H);
  drawBugs(); drawBugParts(); drawLasers(); drawDrone();
  for (const s of sparkParticles) {
    ctx.globalCompositeOperation = 'lighter';
    const g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.size * 4);
    g.addColorStop(0, s.color); g.addColorStop(0.5, hexA(s.color, 0.4)); g.addColorStop(1, hexA(s.color, 0));
    ctx.globalAlpha = s.life; ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(s.x, s.y, s.size * 4, 0, Math.PI * 2); ctx.fill();
    ctx.globalAlpha = 1;
  }
  ctx.globalCompositeOperation = 'source-over';
}

function drawLasers() {
  for (const l of lasers) {
    const alpha = l.life, col = l.color;
    ctx.globalCompositeOperation = 'lighter';
    ctx.strokeStyle = hexA(col, 0.35 * alpha); ctx.lineWidth = 14 * alpha + 4; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(l.x1, l.y1); ctx.lineTo(l.x2, l.y2); ctx.stroke();
    ctx.strokeStyle = hexA(col, 0.85 * alpha); ctx.lineWidth = 6 * alpha + 1;
    ctx.beginPath(); ctx.moveTo(l.x1, l.y1); ctx.lineTo(l.x2, l.y2); ctx.stroke();
    ctx.strokeStyle = `rgba(255,255,255,${alpha})`; ctx.lineWidth = 2 * alpha + 0.8;
    ctx.beginPath(); ctx.moveTo(l.x1, l.y1); ctx.lineTo(l.x2, l.y2); ctx.stroke();
    const r = 40 * alpha + 10;
    const g = ctx.createRadialGradient(l.x2, l.y2, 0, l.x2, l.y2, r);
    g.addColorStop(0, `rgba(255,255,255,${alpha})`); g.addColorStop(0.3, hexA(col, 0.7 * alpha)); g.addColorStop(1, hexA(col, 0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(l.x2, l.y2, r, 0, Math.PI * 2); ctx.fill();
    ctx.globalCompositeOperation = 'source-over';
  }
}

function shootLasers(targetX, targetY) {
  const froms = [drone.leftPupil, drone.rightPupil];
  let anyKill = false;
  for (let i = 0; i < froms.length; i++) {
    const f = froms[i]; if (!f || !f.x) continue;
    lasers.push({ x1: f.x, y1: f.y, x2: targetX, y2: targetY, life: 1, color: LASER_PALETTE[i % LASER_PALETTE.length] });
    if (checkLaserHit(f.x, f.y, targetX, targetY)) anyKill = true;
  }
  if (anyKill) drone.explode = Math.max(drone.explode, 0.4);
}

function triggerExplosion() {
  drone.explode = 1; drone.surprise = 1; drone.visorGlow = 1;
  const count = 260;
  for (let i = 0; i < count; i++) {
    const angle = (Math.PI * 2 * i) / count + Math.random() * 0.5;
    const speed = 6 + Math.random() * 16;
    sparkParticles.push({ x: drone.cx, y: drone.cy, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, size: 1 + Math.random() * 3, life: 1, color: EXPLOSION_PALETTE[Math.floor(Math.random() * EXPLOSION_PALETTE.length)] });
  }
  for (let i = 0; i < 8; i++) {
    const angle = (Math.PI * 2 * i) / 8, dist = Math.max(W, H);
    const x2 = drone.cx + Math.cos(angle) * dist, y2 = drone.cy + Math.sin(angle) * dist;
    lasers.push({ x1: drone.cx, y1: drone.cy, x2, y2, life: 1, color: LASER_PALETTE[i % LASER_PALETTE.length] });
    checkLaserHit(drone.cx, drone.cy, x2, y2);
  }
  const flash = document.getElementById('flash');
  flash.classList.remove('active'); void flash.offsetWidth; flash.classList.add('active');
}

let lastT = performance.now();
let bugCheckTimer = 0, bugRespawnCooldown = 0;
function loop(t) {
  const dt = t - lastT; lastT = t;
  updateDrone(t); updateBugs(dt); updateBugParts(); drawScene();
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

window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });
window.addEventListener('touchmove', e => { if (e.touches[0]) { mouse.x = e.touches[0].clientX; mouse.y = e.touches[0].clientY; } });
window.addEventListener('click', e => { if (e.target.closest && e.target.closest('.poker-card, .mega-card, button, input, select, .mode-btn, .room-item, .modal-overlay, .info-btn')) return; shootLasers(e.clientX, e.clientY); });
window.addEventListener('resize', resize);

mouse.x = window.innerWidth / 2; mouse.y = window.innerHeight / 2;
resize(); requestAnimationFrame(loop);

/* ===================================================================
   ЛОГИКА ПРИЛОЖЕНИЯ
   =================================================================== */
const CATEGORIES = [
  { id: "backend", name: "Backend", range: "4-7", min: 4, max: 7, tooltip: "<b>0</b> Бэкенд не меняется<br><b>4</b> Изменение существующего API, добавление простого поля<br><b>5</b> Новый endpoint или изменение бизнес-логики сервиса<br><b>6</b> Несколько сервисов, сложная валидация<br><b>7</b> Существенная переработка доменной логики" },
  { id: "frontend", name: "Frontend", range: "1-4", min: 1, max: 4, tooltip: "<b>0</b> Нет фронтенда<br><b>1</b> Изменение текста, поля или кнопки<br><b>2</b> Новый небольшой компонент<br><b>3</b> Новая форма или сложный экран<br><b>4</b> Новый пользовательский сценарий, несколько экранов" },
  { id: "business", name: "Business Process", range: "4-9", min: 4, max: 9, tooltip: "Под бизнес-процессом понимается изменение того, как работает бизнес.<br><br><b>0</b> Процесс не меняется<br><b>4</b> Небольшое изменение маршрута<br><b>6</b> Изменение нескольких правил<br><b>8</b> Изменение работы нескольких отделов<br><b>9</b> Новый бизнес-процесс" },
  { id: "design", name: "Design", range: "1-6", min: 1, max: 6, tooltip: "<b>0</b> Дизайн не меняется<br><b>1</b> Изменение цвета или текста<br><b>2</b> Новая секция<br><b>4</b> Новый Landing Page<br><b>6</b> Полный редизайн сценария" },
  { id: "database", name: "DB", range: "3-8", min: 3, max: 8, tooltip: "<b>0</b> База не меняется<br><b>3</b> Добавление столбца<br><b>5</b> Новая таблица<br><b>7</b> Реструктуризация нескольких таблиц<br><b>8</b> Сложная миграция данных" },
  { id: "integrations", name: "Integrations", range: "3-9", min: 3, max: 9, tooltip: "<b>0</b> Интеграций нет<br><b>3</b> Изменить существующий API-вызов<br><b>5</b> Подключить новый внешний сервис<br><b>7</b> Несколько систем<br><b>9</b> Критичная интеграция с большим объёмом логики" }
];
const HOURS_CAT = { id: "hours", name: "Hours", range: "1-21", min: 1, max: 21, tooltip: "Оценка сложности задачи в часах по шкале Фибоначчи:<br>1, 2, 3, 5, 8, 13, 21" };
const NORMAL_CARDS = ["0","1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","16","17","18","19","20","21","22","23","24","?","☕"];

let state = {
  name:'', room:'', mode:'normal', isAdmin:false, myVote: null, revealed:false, lastData: null, pickedMode: 'normal',
  detailsVisible: false, timerEnd: 0, timerDuration: 20, timerInterval: null, audioCtx: null, gameOverPlayed: false
};

function pickMode(mode) { state.pickedMode = mode; document.querySelectorAll('.mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode)); }
function getOptions(cat) {
  if (cat.id === "hours") return ['0', '1', '2', '3', '5', '8', '13', '21', '☕'];
  const opts = ['0']; for (let i = cat.min; i <= cat.max; i++) opts.push(String(i)); opts.push('☕'); return opts;
}

function openTooltip(title, body) { document.getElementById('tooltip-title').innerHTML = title; document.getElementById('tooltip-body').innerHTML = body; document.getElementById('tooltip-modal').classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

function initAudio() { if (!state.audioCtx) state.audioCtx = new (window.AudioContext || window.webkitAudioContext)(); }

function playTick(isFinal = false) {
  initAudio();
  if (state.audioCtx.state === 'suspended') state.audioCtx.resume();
  
  if (isFinal) {
    const notes = [440, 349.23, 261.63];
    notes.forEach((freq, i) => {
      const osc = state.audioCtx.createOscillator();
      const gain = state.audioCtx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(freq, state.audioCtx.currentTime + i * 0.2);
      gain.gain.setValueAtTime(0.3, state.audioCtx.currentTime + i * 0.2);
      gain.gain.exponentialRampToValueAtTime(0.01, state.audioCtx.currentTime + i * 0.2 + 0.3);
      osc.connect(gain); gain.connect(state.audioCtx.destination);
      osc.start(state.audioCtx.currentTime + i * 0.2); osc.stop(state.audioCtx.currentTime + i * 0.2 + 0.3);
    });
  } else {
    const osc = state.audioCtx.createOscillator();
    const gain = state.audioCtx.createGain();
    osc.type = 'square'; osc.frequency.setValueAtTime(1200, state.audioCtx.currentTime);
    gain.gain.setValueAtTime(0.1, state.audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, state.audioCtx.currentTime + 0.05);
    osc.connect(gain); gain.connect(state.audioCtx.destination);
    osc.start(); osc.stop(state.audioCtx.currentTime + 0.05);
  }
}

function updateTimerSetting() {
  const val = parseInt(document.getElementById('timer-select').value);
  state.timerDuration = val;
  if (!state.timerEnd) document.getElementById('timer-display').textContent = val;
}

function startTimer() {
  if (!state.isAdmin) return;
  const seconds = parseInt(document.getElementById('timer-select').value);
  fetch('/api/timer', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({room:state.room, name:state.name, seconds: seconds}) });
}

function tickTimer() {
  if (!state.timerEnd) return;
  const now = Date.now();
  const left = Math.ceil((state.timerEnd - now) / 1000);
  const display = document.getElementById('timer-display');
  
  if (left > 0) {
    if (display.textContent != left) {
      display.textContent = left;
      playTick(false);
    }
    display.classList.add('active');
  } else {
    display.textContent = '0';
    display.classList.remove('active');
    clearInterval(state.timerInterval);
    state.timerInterval = null;
    
    if (!state.gameOverPlayed) {
      playTick(true);
      state.gameOverPlayed = true;
    }
  }
}

window.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const roomFromUrl = params.get('room');
  if (roomFromUrl) { document.getElementById('room-input').value = roomFromUrl; document.getElementById('name-input').focus(); }
  loadRooms(); setInterval(loadRooms, 3000);
});

function loadRooms() {
  fetch('/api/rooms').then(r => r.json()).then(data => {
    const section = document.getElementById('rooms-section'), list = document.getElementById('room-list');
    if (!data.rooms || data.rooms.length === 0) { section.classList.add('hidden'); return; }
    section.classList.remove('hidden'); list.innerHTML = '';
    data.rooms.forEach(r => {
      const item = document.createElement('div'); item.className = 'room-item';
      const modeLabel = r.mode === 'mega' ? 'МЕГА' : 'ОБЫЧН.';
      item.innerHTML = `<span>▸ ${r.name}<span class="mode-tag">[${modeLabel}]</span></span><span class="count">${r.users} участн.</span>`;
      item.onclick = () => { document.getElementById('room-input').value = r.name; if (r.mode === 'mega') pickMode('mega'); else pickMode('normal'); document.getElementById('name-input').focus(); };
      list.appendChild(item);
    });
  });
}

function joinRoom() {
  const name = document.getElementById('name-input').value.trim(), room = document.getElementById('room-input').value.trim().toLowerCase();
  if (!name || !room) return alert('Введите имя и комнату');
  state.name = name; state.room = room;
  
  fetch('/api/join', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name, room, mode: state.pickedMode}) })
  .then(r => r.json()).then(resp => {
    state.mode = resp.mode || 'normal';
    state.isAdmin = resp.admin === state.name;
    
    if (!resp.is_creator) {
      alert('Ошибка: В этой комнате уже есть администратор (' + resp.admin + ').\nАдмин может быть только 1 (тот, кто создал комнату). Вы вошли как участник.');
    }

    if (state.mode === 'mega') { state.myVote = {}; CATEGORIES.forEach(c => state.myVote[c.id] = null); state.myVote['hours'] = null; } else { state.myVote = null; }

    document.getElementById('join-screen').classList.add('hidden');
    document.getElementById('game-screen').classList.remove('hidden');
    document.getElementById('room-name').textContent = room;
    document.getElementById('share-link').value = location.origin + '/?room=' + encodeURIComponent(room);
    
    const timerBox = document.getElementById('timer-box');
    if (state.isAdmin) { timerBox.classList.remove('hidden'); } else { timerBox.classList.remove('hidden'); document.getElementById('timer-start-btn').style.display = 'none'; document.getElementById('timer-select').style.display = 'none'; }

    const modeBadge = document.getElementById('mode-badge');
    if (state.mode === 'mega') {
      modeBadge.textContent = 'МЕГА'; modeBadge.classList.add('mega');
      document.getElementById('normal-mode').classList.add('hidden'); document.getElementById('mega-mode').classList.remove('hidden');
      document.getElementById('result').classList.add('hidden'); document.getElementById('mega-result').classList.add('hidden');
      buildMegaUI();
    } else {
      modeBadge.textContent = 'ОБЫЧНЫЙ'; modeBadge.classList.remove('mega');
      document.getElementById('normal-mode').classList.remove('hidden'); document.getElementById('mega-mode').classList.add('hidden');
      document.getElementById('result').classList.remove('hidden'); document.getElementById('mega-result').classList.add('hidden');
      buildCards();
    }
    poll();
  });
}

function buildCards() {
  const grid = document.getElementById('cards'); grid.innerHTML = '';
  NORMAL_CARDS.forEach(c => {
    const el = document.createElement('div'); el.className = 'poker-card'; el.textContent = c; el.dataset.value = c;
    el.onclick = () => vote(c); grid.appendChild(el);
  });
}

function vote(value) {
  if (state.revealed) return;
  state.myVote = value;
  document.querySelectorAll('.poker-card').forEach(el => { el.classList.toggle('selected', el.textContent === value); });
  fetch('/api/vote', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({room:state.room, name:state.name, vote:value}) });
}

function buildMegaUI() {
  const container = document.getElementById('mega-categories'); container.innerHTML = '';
  const allCats = [...CATEGORIES, HOURS_CAT];
  allCats.forEach(cat => {
    const block = document.createElement('div'); block.className = 'mega-cat'; block.dataset.catId = cat.id;
    const header = document.createElement('div'); header.className = 'mega-cat-header';
    header.innerHTML = `
      <span class="mega-cat-name">${cat.name} <div class="info-btn" onclick="showCatInfo('${cat.id}')">i</div></span>
      <span class="mega-cat-range">${cat.range}</span>
    `;
    const options = document.createElement('div'); options.className = 'mega-cat-options';
    getOptions(cat).forEach(opt => {
      const card = document.createElement('div'); card.className = 'mega-card'; card.textContent = opt; card.dataset.value = opt; card.dataset.cat = cat.id;
      card.onclick = () => voteMega(cat.id, opt); options.appendChild(card);
    });
    block.appendChild(header); block.appendChild(options); container.appendChild(block);
  });
}

function showCatInfo(id) {
  if (id === 'hours') {
    openTooltip(HOURS_CAT.name + ' (' + HOURS_CAT.range + ')', HOURS_CAT.tooltip);
  } else {
    const cat = CATEGORIES.find(c => c.id === id);
    if (cat) openTooltip(cat.name + ' (' + cat.range + ')', cat.tooltip);
  }
}

function voteMega(catId, value) {
  if (state.revealed) return;
  state.myVote[catId] = value;
  document.querySelectorAll(`.mega-card[data-cat="${catId}"]`).forEach(el => { el.classList.toggle('selected', el.dataset.value === value); });
  const block = document.querySelector(`.mega-cat[data-cat-id="${catId}"]`); if (block) block.classList.toggle('done', value !== null);
  fetch('/api/vote', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({room:state.room, name:state.name, category:catId, value}) });
}

function revealResults() {
  if (!state.isAdmin) { 
    alert("Ошибка: Админ уже есть и может быть только 1 (тот, кто создал комнату). Только он может раскрыть результаты!"); 
    return; 
  }
  
  if (state.timerInterval) { clearInterval(state.timerInterval); state.timerInterval = null; }
  state.timerEnd = 0;
  state.gameOverPlayed = true;
  document.getElementById('timer-display').textContent = state.timerDuration;
  document.getElementById('timer-display').classList.remove('active');

  fetch('/api/reveal', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({room:state.room, name:state.name}) });
}

function resetVotes() {
  if (!state.isAdmin) return;
  fetch('/api/reset', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({room:state.room}) });
}

function leaveRoom() { fetch('/api/leave', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({room:state.room, name:state.name}) }).then(() => location.href = '/'); }

function copyLink(e) {
  const input = document.getElementById('share-link'); input.select(); try { document.execCommand('copy'); } catch (err) {}
  const btn = e.target; const orig = btn.textContent; btn.textContent = '✓ OK'; setTimeout(() => btn.textContent = orig, 1500);
}

function toggleDetails() {
  state.detailsVisible = !state.detailsVisible;
  document.getElementById('toggle-details-btn').textContent = state.detailsVisible ? '🙈 Скрыть голоса' : '👥 Голоса команды';
  if (state.lastData) renderMegaResults(state.lastData);
}

function poll() {
  fetch('/api/state?room=' + encodeURIComponent(state.room) + '&name=' + encodeURIComponent(state.name))
    .then(r => r.json()).then(updateUI).catch(() => {});
  setTimeout(poll, 1500);
}

function updateUI(data) {
  if (!data.users) return;
  state.lastData = data;

  if (data.timer_end && data.timer_end > Date.now()) {
    if (state.timerEnd !== data.timer_end) {
      state.timerEnd = data.timer_end;
      if (!state.timerInterval) state.timerInterval = setInterval(tickTimer, 200);
      state.gameOverPlayed = false;
    }
  } else if (state.timerEnd) {
    state.timerEnd = 0;
    if (state.timerInterval) { clearInterval(state.timerInterval); state.timerInterval = null; }
    document.getElementById('timer-display').textContent = state.timerDuration;
    document.getElementById('timer-display').classList.remove('active');
  }

  const serverVote = data.users[state.name];
  if (state.mode === 'mega') { state.myVote = serverVote ? { ...serverVote } : {}; } else { state.myVote = (serverVote === undefined) ? null : serverVote; }

  const wasRevealed = state.revealed;
  state.revealed = data.revealed;
  if (data.revealed && !wasRevealed) triggerExplosion();

  if (!data.revealed) {
    if (state.mode === 'mega') {
      document.querySelectorAll('.mega-card').forEach(el => {
        const catId = el.dataset.cat, val = state.myVote[catId];
        el.classList.toggle('selected', val !== null && val !== undefined && el.dataset.value === val);
        el.style.pointerEvents = 'auto'; el.style.opacity = '1';
      });
      document.querySelectorAll('.mega-cat').forEach(block => {
        const catId = block.dataset.catId, val = state.myVote[catId];
        block.classList.toggle('done', val !== null && val !== undefined);
      });
    } else {
      document.querySelectorAll('.poker-card').forEach(el => {
        el.classList.toggle('selected', el.dataset.value === state.myVote);
        el.style.pointerEvents = 'auto'; el.style.opacity = '1';
      });
    }
  } else {
    if (state.mode === 'mega') {
      document.querySelectorAll('.mega-card').forEach(el => {
        const catId = el.dataset.cat, val = state.myVote[catId];
        el.style.pointerEvents = 'none';
        el.style.opacity = (val !== null && val !== undefined && el.dataset.value === val) ? '1' : '0.4';
      });
    } else {
      document.querySelectorAll('.poker-card').forEach(el => {
        el.style.pointerEvents = 'none';
        el.style.opacity = el.dataset.value === state.myVote ? '1' : '0.4';
      });
    }
  }

  const revealBtn = document.getElementById('reveal-btn');
  const saveBtn = document.getElementById('save-btn');
  const resetBtn = document.getElementById('reset-btn');
  
  if (data.revealed) {
    revealBtn.textContent = '🙈 Hide'; revealBtn.classList.remove('btn-reveal'); revealBtn.classList.add('btn-hide');
    revealBtn.onclick = resetVotes; if(saveBtn) saveBtn.style.display = 'block';
  } else {
    revealBtn.textContent = '👁 Reveal'; revealBtn.classList.add('btn-reveal'); revealBtn.classList.remove('btn-hide');
    revealBtn.onclick = revealResults; if(saveBtn) saveBtn.style.display = 'none';
  }

  if (!state.isAdmin) {
    revealBtn.disabled = true; revealBtn.style.opacity = '0.3';
    if (resetBtn) { resetBtn.disabled = true; resetBtn.style.opacity = '0.3'; }
  } else {
    revealBtn.disabled = false; revealBtn.style.opacity = '1';
    if (resetBtn) { resetBtn.disabled = false; resetBtn.style.opacity = '1'; }
  }

  const usersEl = document.getElementById('users'); usersEl.innerHTML = '';
  let votedCount = 0, total = 0;

  if (state.mode === 'mega') {
    for (const [name, votes] of Object.entries(data.users)) {
      total++;
      const filled = votes ? Object.values(votes).filter(v => v !== null && v !== undefined).length : 0;
      const allDone = filled === (CATEGORIES.length + 1);
      if (allDone) votedCount++;
      const row = document.createElement('div'); row.className = 'user-row' + (allDone ? ' voted' : '');
      if (data.revealed && !wasRevealed) row.classList.add('just-revealed');
      let badgeHtml;
      if (data.revealed) badgeHtml = `<span class="badge voted">✓ ${filled}/${CATEGORIES.length + 1}</span>`;
      else if (allDone) badgeHtml = `<span class="badge voted">✓ готов</span>`;
      else if (filled > 0) badgeHtml = `<span class="badge partial">${filled}/${CATEGORIES.length + 1}</span>`;
      else badgeHtml = `<span class="badge">…WAIT</span>`;
      let adminHtml = name === data.admin ? `<span class="badge admin">ADMIN</span>` : '';
      row.innerHTML = `<span>${name === state.name ? '▶ ' + name + ' (вы)' : name}</span><div style="display:flex; gap:8px;">${adminHtml} ${badgeHtml}</div>`;
      usersEl.appendChild(row);
    }
    document.getElementById('mega-votes-info').textContent = data.revealed ? `Проголосовало: ${votedCount} / ${total}` : `${votedCount} / ${total} · голосуют`;
  } else {
    const numericVotes = [];
    for (const [name, vote] of Object.entries(data.users)) {
      total++; const hasVoted = vote !== null;
      if (hasVoted) { votedCount++; const n = parseFloat(vote); if (!isNaN(n)) numericVotes.push(n); }
      const row = document.createElement('div'); row.className = 'user-row' + (hasVoted ? ' voted' : '');
      if (data.revealed && !wasRevealed) row.classList.add('just-revealed');
      let badgeHtml;
      if (data.revealed && hasVoted) badgeHtml = `<span class="badge voted">${vote}</span>`;
      else if (hasVoted) badgeHtml = `<span class="badge voted">✓ VOTED</span>`;
      else badgeHtml = `<span class="badge">…WAIT</span>`;
      let adminHtml = name === data.admin ? `<span class="badge admin">ADMIN</span>` : '';
      row.innerHTML = `<span>${name === state.name ? '▶ ' + name + ' (вы)' : name}</span><div style="display:flex; gap:8px;">${adminHtml} ${badgeHtml}</div>`;
      usersEl.appendChild(row);
    }
    document.getElementById('votes-info').textContent = data.revealed ? `Проголосовало: ${votedCount} / ${total}` : `${votedCount} / ${total} · голосуют`;
    const resultEl = document.getElementById('result');
    if (data.revealed && numericVotes.length > 0) { const avg = numericVotes.reduce((a,b) => a+b, 0) / numericVotes.length; document.getElementById('avg-value').textContent = avg.toFixed(1); resultEl.classList.add('ready'); }
    else { document.getElementById('avg-value').textContent = '—'; if (!data.revealed) resultEl.classList.remove('ready'); }
  }

  if (state.mode === 'mega') {
    const megaResult = document.getElementById('mega-result');
    if (data.revealed) { megaResult.classList.remove('hidden'); renderMegaResults(data); } else { megaResult.classList.add('hidden'); }
  }
}

function renderMegaResults(data) {
  const thead = document.getElementById('results-thead'), tbody = document.getElementById('results-tbody'), tfoot = document.getElementById('results-tfoot');
  const userNames = Object.keys(data.users);
  thead.innerHTML = ''; tbody.innerHTML = ''; tfoot.innerHTML = '';

  let headHtml = '<tr><th>Категория</th><th>Min</th><th>Max</th><th>Avg</th>';
  if (state.detailsVisible) userNames.forEach(un => { const meCls = un === state.name ? ' user-col me' : ' user-col'; headHtml += `<th class="${meCls.trim()}">${un}</th>`; });
  headHtml += '</tr>'; thead.innerHTML = headHtml;

  let totalSumComplexity = 0, totalMin = 0, totalMax = 0, anyData = false;
  const allCats = [...CATEGORIES, HOURS_CAT];

  allCats.forEach(cat => {
    const votes = [], userVotes = [];
    userNames.forEach(un => {
      const v = data.users[un] ? data.users[un][cat.id] : null; userVotes.push(v);
      if (v !== null && v !== undefined && v !== '☕') { const n = parseFloat(v); if (!isNaN(n)) votes.push(n); }
    });
    let avg = '—';
    if (votes.length > 0) {
      const sum = votes.reduce((a,b) => a+b, 0); avg = (sum / votes.length).toFixed(1);
      if (cat.id !== 'hours') { totalSumComplexity += parseFloat(avg); totalMin += cat.min; totalMax += cat.max; }
      anyData = true;
    }
    let rowHtml = `<tr><td>${cat.name}</td><td>${cat.min}</td><td>${cat.max}</td><td><b>${avg}</b></td>`;
    if (state.detailsVisible) userVotes.forEach((v, idx) => { const un = userNames[idx], meCls = un === state.name ? 'user-col me' : 'user-col'; const display = (v === null || v === undefined) ? '—' : v; rowHtml += `<td class="${meCls}">${display}</td>`; });
    rowHtml += '</tr>'; tbody.insertAdjacentHTML('beforeend', rowHtml);
  });
  
  const hoursVotes = []; userNames.forEach(un => { const v = data.users[un] ? data.users[un]['hours'] : null; if (v !== null && v !== undefined && v !== '☕') hoursVotes.push(parseFloat(v)); });
  let hoursAvg = 0; if (hoursVotes.length > 0) hoursAvg = hoursVotes.reduce((a,b) => a+b, 0) / hoursVotes.length;
  const duration = calcDuration(hoursAvg);

  let durRow = `<tr><td>Duration (auto)</td><td>-</td><td>-</td><td><b>${duration}</b></td>`;
  if (state.detailsVisible) userNames.forEach(() => durRow += `<td></td>`);
  durRow += `</tr>`; tbody.insertAdjacentHTML('beforeend', durRow);

  let footHtml = `<tr><td>Total Complexity</td><td>${totalMin}</td><td>${totalMax}</td><td id="total-avg">${anyData ? totalSumComplexity.toFixed(1) : '—'}</td>`;
  if (state.detailsVisible) userNames.forEach(un => { const meCls = un === state.name ? 'user-col me' : 'user-col'; footHtml += `<td class="${meCls}"></td>`; });
  footHtml += '</tr>'; tfoot.innerHTML = footHtml;
}

function calcDuration(avgHours) {
  if (!avgHours) return 0;
  const map = { 1:1, 2:2, 3:2, 5:3, 8:4, 13:6, 21:10 };
  const keys = [1, 2, 3, 5, 8, 13, 21];
  let closest = keys[0], minDiff = Infinity;
  keys.forEach(k => { const diff = Math.abs(k - avgHours); if (diff < minDiff) { minDiff = diff; closest = k; } });
  return map[closest];
}

function openSaveModal() {
  const data = state.lastData; if (!data) return;
  const userNames = Object.keys(data.users);
  const form = document.getElementById('save-form-fields'); form.innerHTML = '';
  
  let totalComplexity = 0;
  const allCats = [...CATEGORIES, HOURS_CAT];
  
  allCats.forEach(cat => {
    let sum = 0, count = 0;
    userNames.forEach(un => { const v = data.users[un] ? data.users[un][cat.id] : null; if (v !== null && v !== undefined && v !== '☕') { const n = parseFloat(v); if (!isNaN(n)) { sum += n; count++; } } });
    const avg = count > 0 ? (sum / count) : 0;
    if (cat.id !== 'hours') totalComplexity += avg;
    
    const group = document.createElement('div'); group.className = 'form-group';
    group.innerHTML = `<label>${cat.name}</label><input type="number" step="0.1" id="save-${cat.id}" value="${avg.toFixed(1)}" onchange="this.classList.add('edited')">`;
    form.appendChild(group);
  });
  
  const durVal = calcDuration(parseFloat(document.getElementById('save-hours').value) || 0);
  
  const tcGroup = document.createElement('div'); tcGroup.className = 'form-group';
  tcGroup.innerHTML = `<label>Total Complexity</label><input type="number" step="0.1" id="save-total" value="${totalComplexity.toFixed(1)}" onchange="this.classList.add('edited')">`;
  form.appendChild(tcGroup);

  const durGroup = document.createElement('div'); durGroup.className = 'form-group';
  durGroup.innerHTML = `
    <label style="display:flex; justify-content:space-between; align-items:center;">
      Duration (Continuity)
      <div class="info-btn" onclick="openTooltip('Duration Calculation', 'Соотношение средних часов к продолжительности:<br><br><b>1</b> час = <b>1</b><br><b>2</b> часа = <b>2</b><br><b>3</b> часа = <b>2</b><br><b>5</b> часов = <b>3</b><br><b>8</b> часов = <b>4</b><br><b>13</b> часов = <b>6</b><br><b>21</b> час = <b>10</b>')">i</div>
    </label>
    <input type="number" step="1" id="save-duration" value="${durVal}" onchange="this.classList.add('edited')">
  `;
  form.appendChild(durGroup);

  document.getElementById('save-modal').classList.add('active');
}

function downloadExcel() {
  const vals = {
    backend: parseFloat(document.getElementById('save-backend').value) || 0,
    frontend: parseFloat(document.getElementById('save-frontend').value) || 0,
    business: parseFloat(document.getElementById('save-business').value) || 0,
    design: parseFloat(document.getElementById('save-design').value) || 0,
    database: parseFloat(document.getElementById('save-database').value) || 0,
    integrations: parseFloat(document.getElementById('save-integrations').value) || 0,
    hours: parseFloat(document.getElementById('save-hours').value) || 0,
    total: parseFloat(document.getElementById('save-total').value) || 0,
    duration: parseFloat(document.getElementById('save-duration').value) || 0,
  };

  let html = '<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel">';
  html += '<head><meta charset="UTF-8">';
  html += '<style>';
  html += 'table { border-collapse: collapse; font-family: Arial, sans-serif; }';
  html += 'th, td { border: 1px solid #444; padding: 8px 12px; text-align: center; }';
  html += 'th { background: #5b9bd5; color: white; font-weight: bold; }';
  html += '.light { background: #e9eff7; font-weight: bold; }';
  html += '.green { background: #70ad47; color: white; }';
  html += '.num { mso-number-format:"0\\.0"; }';
  html += '.int { mso-number-format:"0"; }';
  html += '</style>';
  html += '</head><body>';
  
  html += '<table>';
  html += '<tr>';
  html += '<th>Backend (4-7)</th><th>Frontend (1-4)</th><th>Business Process (4-9)</th>';
  html += '<th>Design (1-6)</th><th>DB (3-8)</th><th>Integrations (3-9)</th>';
  html += '<th class="light">Total Complexity</th><th class="green">Continuity (1-10)</th>';
  html += '</tr>';
  
  html += '<tr>';
  html += `<td class="num" x:num="${vals.backend}">${vals.backend.toFixed(1).replace('.',',')}</td>`;
  html += `<td class="num" x:num="${vals.frontend}">${vals.frontend.toFixed(1).replace('.',',')}</td>`;
  html += `<td class="num" x:num="${vals.business}">${vals.business.toFixed(1).replace('.',',')}</td>`;
  html += `<td class="num" x:num="${vals.design}">${vals.design.toFixed(1).replace('.',',')}</td>`;
  html += `<td class="num" x:num="${vals.database}">${vals.database.toFixed(1).replace('.',',')}</td>`;
  html += `<td class="num" x:num="${vals.integrations}">${vals.integrations.toFixed(1).replace('.',',')}</td>`;
  html += `<td class="light num" x:num="${vals.total}">${vals.total.toFixed(1).replace('.',',')}</td>`;
  html += `<td class="green int" x:num="${vals.duration}">${vals.duration}</td>`;
  html += '</tr>';
  
  html += '</table>';
  html += '</body></html>';

  const blob = new Blob(['\ufeff' + html], { type: 'application/vnd.ms-excel;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'Planning_Poker_' + state.room + '.xls';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  
  closeModal('save-modal');
}

function escapeHtml(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
['name-input','room-input'].forEach(id => { document.getElementById(id).addEventListener('keypress', e => { if (e.key === 'Enter') joinRoom(); }); });
</script>
</body>
</html>
"""


def get_room(rid):
    if rid not in rooms:
        rooms[rid] = {
            "mode": "normal",
            "users": {},
            "revealed": False,
            "admin": "",
            "timer_end": 0,
        }
    return rooms[rid]


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/api/rooms")
def list_rooms():
    return jsonify(
        {
            "rooms": [
                {"name": n, "users": len(r["users"]), "mode": r.get("mode", "normal")}
                for n, r in sorted(rooms.items())
            ]
        }
    )


@app.route("/api/join", methods=["POST"])
def join():
    d = request.json
    r = get_room(d["room"])
    if len(r["users"]) == 0:
        r["mode"] = d.get("mode", "normal")
        r["admin"] = d["name"]
    mode = r["mode"]
    if mode == "mega":
        r["users"][d["name"]] = {c["id"]: None for c in CATEGORIES}
        r["users"][d["name"]]["hours"] = None
    else:
        r["users"][d["name"]] = None
    is_creator = r["admin"] == d["name"]
    return jsonify(
        {"ok": True, "mode": mode, "admin": r["admin"], "is_creator": is_creator}
    )


@app.route("/api/vote", methods=["POST"])
def vote():
    d = request.json
    r = get_room(d["room"])
    if r["revealed"]:
        return jsonify({"ok": False})
    if r["mode"] == "mega":
        if d["name"] in r["users"] and "category" in d:
            r["users"][d["name"]][d["category"]] = d["value"]
    else:
        if d["name"] in r["users"]:
            r["users"][d["name"]] = d["vote"]
    return jsonify({"ok": True})


@app.route("/api/reveal", methods=["POST"])
def reveal():
    d = request.json
    r = get_room(d["room"])
    if d.get("name") != r.get("admin"):
        return jsonify({"ok": False, "error": "Админ уже есть и может быть только 1!"})
    r["revealed"] = True
    r["timer_end"] = 0
    return jsonify({"ok": True})


@app.route("/api/timer", methods=["POST"])
def timer():
    d = request.json
    r = get_room(d["room"])
    if d.get("name") != r.get("admin"):
        return jsonify({"ok": False})
    seconds = d.get("seconds", 20)
    r["timer_end"] = int(time.time() * 1000) + (seconds * 1000)
    return jsonify({"ok": True})


@app.route("/api/reset", methods=["POST"])
def reset():
    r = get_room(request.json["room"])
    if r["mode"] == "mega":
        for n in r["users"]:
            r["users"][n] = {c["id"]: None for c in CATEGORIES}
            r["users"][n]["hours"] = None
    else:
        for n in r["users"]:
            r["users"][n] = None
    r["revealed"] = False
    r["timer_end"] = 0
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
    return jsonify(
        {
            "mode": r.get("mode", "normal"),
            "users": r["users"],
            "revealed": r["revealed"],
            "admin": r.get("admin", ""),
            "timer_end": r.get("timer_end", 0),
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)
