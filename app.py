from flask import Flask, request, jsonify, Response
import hashlib
import hmac
import os
import re
import threading
import time
import uuid

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
rooms = {}
ROOM_LOCK = threading.RLock()

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
CATEGORY_BY_ID = {category["id"]: category for category in CATEGORIES}
CATEGORY_BY_ID["hours"] = HOURS_CAT
NORMAL_VOTES = {str(value) for value in range(25)} | {"?", "☕"}
HOURS_VOTES = {"0", "1", "2", "3", "5", "8", "13", "21", "☕"}
TIMER_SECONDS = {5, 10, 15, 20, 25, 30, 45, 60}
ROOM_ID_RE = re.compile(r"^[a-z0-9_-]{1,20}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9._~-]{20,200}$")


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


@app.errorhandler(APIError)
def handle_api_error(error):
    return jsonify({"ok": False, "error": error.message}), error.status


@app.errorhandler(413)
def handle_too_large(_error):
    return jsonify({"ok": False, "error": "Слишком большой запрос."}), 413


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("Ожидался JSON-объект.")
    return data


def normalize_room_id(value):
    if not isinstance(value, str):
        raise APIError("Некорректный ID комнаты.")
    room_id = value.strip().lower()
    if not ROOM_ID_RE.fullmatch(room_id):
        raise APIError(
            "ID комнаты: от 1 до 20 символов — латинские буквы, цифры, дефис или подчёркивание."
        )
    return room_id


def normalize_name(value):
    if not isinstance(value, str):
        raise APIError("Некорректное имя участника.")
    name = value.strip()
    if (
        not name
        or len(name) > 20
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
    ):
        raise APIError("Имя должно содержать от 1 до 20 печатных символов.")
    return name


def token_digest(token):
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        raise APIError("Сессия участника некорректна. Перезайдите в комнату.", 401)
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_vote(mode):
    if mode == "mega":
        return {category["id"]: None for category in CATEGORIES + [HOURS_CAT]}
    return None


def new_room(mode):
    return {
        "mode": mode,
        "users": {},
        "revealed": False,
        "admin_id": None,
        "timer_end": 0,
        "task_name": "",
        "created_at": time.time(),
    }


def next_admin(room):
    if not room["users"]:
        room["admin_id"] = None
        return
    next_user = min(room["users"].values(), key=lambda user: user["joined_at"])
    room["admin_id"] = next_user["id"]


def cleanup_room(room_id, now=None):
    """Удаляет участников без heartbeat более 10 секунд."""
    room = rooms.get(room_id)
    if room is None:
        return
    now = now or time.time()
    stale_ids = [
        user_id
        for user_id, user in room["users"].items()
        if now - user["last_seen"] > 10
    ]
    admin_removed = room["admin_id"] in stale_ids
    for user_id in stale_ids:
        room["users"].pop(user_id, None)
    if admin_removed:
        next_admin(room)
    if not room["users"]:
        rooms.pop(room_id, None)


def get_room_and_actor(room_id):
    room_id = normalize_room_id(room_id)
    cleanup_room(room_id)
    room = rooms.get(room_id)
    if room is None:
        raise APIError("Комната не найдена или все участники отключились.", 404)
    token = request.headers.get("X-Session-Token", "")
    digest = token_digest(token)
    actor_id = None
    actor = None
    now = time.time()
    for user_id, user in room["users"].items():
        if hmac.compare_digest(user["token_hash"], digest):
            actor_id, actor = user_id, user
            break
    if actor is None:
        raise APIError("Сессия участника не найдена. Войдите в комнату заново.", 401)
    actor["last_seen"] = now
    return room_id, room, actor_id, actor


def require_admin(room, actor_id):
    if room["admin_id"] != actor_id:
        raise APIError("Это действие доступно только администратору комнаты.", 403)


def room_state(room_id, room, actor_id):
    revealed = bool(room["revealed"])
    users = []
    current_vote = None
    if room["mode"] == "mega":
        current_vote = dict(room["users"][actor_id]["vote"])
    else:
        current_vote = room["users"][actor_id]["vote"]

    for user_id, user in sorted(
        room["users"].items(), key=lambda item: item[1]["joined_at"]
    ):
        if room["mode"] == "mega":
            votes = user["vote"]
            filled = sum(value is not None for value in votes.values())
            item = {
                "id": user_id,
                "name": user["name"],
                "has_voted": filled > 0,
                "filled": filled,
                "ready": filled == len(CATEGORIES) + 1,
            }
            if revealed or user_id == actor_id:
                item["votes"] = dict(votes)
        else:
            vote_value = user["vote"]
            item = {
                "id": user_id,
                "name": user["name"],
                "has_voted": vote_value is not None,
                "filled": int(vote_value is not None),
                "ready": vote_value is not None,
            }
            if revealed or user_id == actor_id:
                item["vote"] = vote_value
        users.append(item)

    if room["timer_end"] and room["timer_end"] <= int(time.time() * 1000):
        room["timer_end"] = 0
    admin = room["users"].get(room["admin_id"])
    return {
        "ok": True,
        "room": room_id,
        "mode": room["mode"],
        "revealed": revealed,
        "admin_id": room["admin_id"],
        "admin_name": admin["name"] if admin else "",
        "current_user_id": actor_id,
        "users": users,
        "my_vote": current_vote,
        "task_name": room["task_name"],
        "timer_end": room["timer_end"],
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
  
  /* РАСШИРЕННЫЙ БЛОК УЧАСТНИКОВ */
  .main-layout { display: flex; gap: 24px; max-width: 1300px; width: 100%; align-items: flex-start; justify-content: center; }
  .left-panel { flex: 1; max-width: 880px; min-width: 0; }
  .right-panel { width: 380px; flex-shrink: 0; }
  
  @media (max-width: 1100px) {
    .main-layout { flex-direction: column; align-items: center; }
    .right-panel { width: 100%; max-width: 880px; margin-bottom: 20px; order: 2; }
  }

  .hud-header { display:flex; align-items:center; gap:14px; margin-bottom:8px; }
  .hud-dot { width:8px; height:8px; border-radius:50%; background:#ff3333; box-shadow: 0 0 12px #ff3333, 0 0 24px #ff3333; animation: pulse 2s ease infinite; }
  @keyframes pulse { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:.4; transform:scale(0.85); } }
  .hud-label { font-family: 'JetBrains Mono',monospace; font-size:.7rem; letter-spacing:.25em; color:#ff5555; text-transform:uppercase; }
  h1 { font-size:2.4rem; font-weight:800; letter-spacing:.05em; background: linear-gradient(135deg,#ffffff 0%,#ff5555 50%,#ff0033 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; text-transform:uppercase; margin: 4px 0 6px; filter: drop-shadow(0 0 30px rgba(255,60,60,0.4)); text-align: center; }
  .subtitle { font-family: 'JetBrains Mono',monospace; color:#5a5a7a; margin-bottom:35px; font-size:.75rem; letter-spacing:.25em; text-transform:uppercase; text-align: center; }
  
  .card { position:relative; background: linear-gradient(180deg, rgba(10,10,24,0.7), rgba(6,6,16,0.8)); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); border:1px solid rgba(255,80,80,0.22); padding:28px; width:100%; margin-bottom:20px; clip-path: polygon(0 12px, 12px 0, calc(100% - 12px) 0, 100% 12px, 100% calc(100% - 12px), calc(100% - 12px) 100%, 12px 100%, 0 calc(100% - 12px)); box-shadow: 0 0 60px rgba(255,60,60,0.08), inset 0 0 80px rgba(255,60,60,0.015); }
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
  
  /* МГНОВЕННЫЕ КАРТОЧКИ (Убраны transition) */
  .cards-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(48px, 1fr)); gap:6px; margin-top:18px; }
  .poker-card { 
    aspect-ratio: 1 / 1.35; 
    background: linear-gradient(160deg, rgba(255,60,60,0.04), rgba(255,120,120,0.04)); 
    border:1px solid rgba(255,80,80,0.2); 
    display:flex; align-items:center; justify-content:center; 
    font-family: 'JetBrains Mono', monospace; font-size:1.05rem; font-weight:700; 
    cursor:pointer; 
    transition: none !important; /* Мгновенная реакция */
    color:#e0e8ff; 
    clip-path: polygon(0 8px, 8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%); 
    user-select:none; 
  }
  .poker-card:hover { border-color:#ff5555; color:#ff5555; box-shadow: 0 0 18px rgba(255,60,60,0.45), inset 0 0 18px rgba(255,60,60,0.1); }
  .poker-card:active { transform: scale(0.92); }
  .poker-card.selected { 
    background: #ff3333; /* Сплошной цвет быстрее градиента */
    border-color:#fff; color:#04040c; 
    box-shadow: 0 0 25px rgba(255,60,60,0.7), 0 0 50px rgba(255,120,120,0.5); 
  }
  
  .mega-cat { background: rgba(255,60,60,0.03); border:1px solid rgba(255,80,80,0.15); padding:14px 16px; margin-bottom:10px; clip-path: polygon(0 8px, 8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%); }
  .mega-cat.done { border-color: rgba(34,197,94,0.5); background: rgba(34,197,94,0.04); }
  .mega-cat-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; font-family: 'JetBrains Mono', monospace; }
  .mega-cat-name { font-size:.82rem; color:#e0e8ff; letter-spacing:.02em; display:flex; align-items:center; gap:8px; }
  .mega-cat-range { font-size:.7rem; color:#ff5555; letter-spacing:.15em; }
  .mega-cat-options { display:flex; gap:5px; flex-wrap:wrap; }
  .mega-card { 
    min-width:40px; height:44px; padding:0 10px; 
    display:flex; align-items:center; justify-content:center; 
    border:1px solid rgba(255,80,80,0.25); background: rgba(255,60,60,0.04); 
    font-family: 'JetBrains Mono', monospace; font-size:.9rem; font-weight:700; 
    cursor:pointer; 
    transition: none !important; /* Мгновенная реакция */
    color:#e0e8ff; clip-path: polygon(0 5px, 5px 0, 100% 0, 100% calc(100% - 5px), calc(100% - 5px) 100%, 0 100%); 
    user-select:none; 
  }
  .mega-card:hover { border-color:#ff5555; color:#ff5555; background: rgba(255,60,60,0.12); }
  .mega-card:active { transform: scale(0.92); }
  .mega-card.selected { 
    background: #ff3333; 
    border-color:#fff; color:#04040c; 
    box-shadow: 0 0 15px rgba(255,60,60,0.6); 
  }
  
  .info-btn { display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; border-radius:50%; background:rgba(255,80,80,0.2); color:#ff5555; font-size:12px; cursor:pointer; border:1px solid rgba(255,80,80,0.5); transition:0.2s; font-weight:900; font-family: sans-serif; margin-left: 6px; }
  .info-btn:hover { background:#ff5555; color:#04040c; }
  
  .users { display:flex; flex-direction:column; gap:8px; }
  .user-row { display:flex; justify-content:space-between; align-items:center; padding:12px 18px; background: rgba(255,60,60,0.03); border:1px solid rgba(255,80,80,0.1); font-family: 'JetBrains Mono', monospace; font-size:.85rem; transition:.3s; clip-path: polygon(0 6px, 6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%); gap: 12px; }
  .user-row.voted { border-left:3px solid #22c55e; }
  .user-row.just-revealed { animation: popIn .5s ease; }
  @keyframes popIn { 0% { transform:scale(0.92); opacity:0.4; } 60% { transform:scale(1.03); } 100% { transform:scale(1); opacity:1; } }
  
  /* ФИКС ДЛИННЫХ ИМЕН */
  .user-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .user-status-wrap { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
  
  .badge { padding:4px 12px; font-family: 'JetBrains Mono', monospace; font-size:.75rem; background: rgba(255,60,60,0.08); color:#ff5555; border:1px solid rgba(255,80,80,0.3); letter-spacing:.05em; white-space: nowrap; }
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
  
  .room-list { display:flex; flex-direction:column; gap:6px; }
  .room-item { display:flex; justify-content:space-between; align-items:center; padding:12px 18px; background: rgba(255,60,60,0.03); border:1px solid rgba(255,80,80,0.15); cursor:pointer; transition:.25s; font-family: 'JetBrains Mono', monospace; font-size:.85rem; clip-path: polygon(0 6px, 6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%); }
  .room-item:hover { background: rgba(255,60,60,0.1); border-color:#ff5555; transform:translateX(6px); box-shadow: -4px 0 24px rgba(255,60,60,0.4); }
  .room-item.selected { background: rgba(255,60,60,0.15); border-color:#ff5555; box-shadow: 0 0 15px rgba(255,60,60,0.3); }
  .room-item .count { color:#ff5555; font-size:.75rem; }
  .room-item .mode-tag { color:#5a5a7a; font-size:.65rem; letter-spacing:.15em; margin-left:8px; }
  
  .actions-row { display:flex; gap:10px; margin-top:16px; flex-wrap:wrap; align-items:center; }
  .actions-row button { flex:1; padding:14px 18px; min-width: 140px; }
  .btn-reveal { background: linear-gradient(135deg,#22c55e,#ff3333) !important; }
  .btn-hide { background: rgba(255,255,255,0.06) !important; color:#a0a0c0 !important; }
  .btn-download { background: linear-gradient(135deg,#22c55e,#4ade80) !important; color:#04040c !important; }
  .btn-toggle-details { background: rgba(255,60,60,0.15) !important; color: #ff5555 !important; border: 1px solid rgba(255,80,80,0.5) !important; }
  .btn-toggle-details:hover { box-shadow: 0 0 25px rgba(255,60,60,0.4) !important; }
  
  .task-timer-bar {
    display: flex; gap: 15px; align-items: stretch;
    margin-top: 12px; margin-bottom: 24px;
    background: rgba(255,60,60,0.05);
    border: 1px solid rgba(255,80,80,0.3);
    padding: 12px; 
    clip-path: polygon(0 10px, 10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%);
  }
  .task-name-wrapper { flex: 1; display: flex; flex-direction: column; justify-content: center; }
  .task-name-wrapper label { font-size: 0.65rem; color: #ff5555; font-family: 'JetBrains Mono', monospace; letter-spacing: 0.2em; text-transform: uppercase; margin-bottom: 5px; margin-left: 10px; }
  .task-name-input { width: 100%; font-size: 1.1rem; font-weight: bold; padding: 12px 16px; background: rgba(0,0,0,0.4); border: 1px solid rgba(255,80,80,0.4); color: #fff; transition: 0.3s; }
  .task-name-input:focus { border-color: #ff5555; box-shadow: 0 0 20px rgba(255,60,60,0.2); }

  .timer-box { display:flex; align-items:center; gap:10px; background:rgba(0,0,0,0.4); padding:8px 16px; border:1px solid rgba(255,80,80,0.3); clip-path: polygon(0 6px, 6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%); flex-shrink: 0; }
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
  
  .btn-transfer {
    background: linear-gradient(135deg, #ffd700, #ff8c00);
    color: #000;
    border: none;
    font-size: 0.65rem;
    padding: 4px 8px;
    cursor: pointer;
    clip-path: polygon(0 4px, 4px 0, 100% 0, 100% calc(100% - 4px), calc(100% - 4px) 100%, 0 100%);
    font-weight: 800;
    margin-left: 8px;
    transition: 0.2s;
  }
  .btn-transfer:hover {
    box-shadow: 0 0 15px rgba(255, 215, 0, 0.6);
    transform: scale(1.05);
  }

  .divider { height: 1px; background: rgba(255,80,80,0.2); margin: 30px 0; }
  .join-area { margin-top: 15px; padding: 15px; background: rgba(255,60,60,0.05); border: 1px solid rgba(255,80,80,0.2); clip-path: polygon(0 10px, 10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%); animation: fadeIn 0.3s ease; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
  .join-selected-name { font-family:'JetBrains Mono', monospace; font-size:0.9rem; color:#fff; margin-bottom:10px; font-weight:bold; }

  @media (max-width:600px) {
    .cards-grid { grid-template-columns: repeat(auto-fit, minmax(42px, 1fr)); }
    .poker-card { font-size:.9rem; }
    .card { padding:20px; }
    #kill-counter { bottom:10px; right:10px; font-size:.65rem; }
    .mega-cat-name { font-size:.72rem; }
    .mega-card { min-width:34px; height:38px; font-size:.8rem; padding:0 8px; }
    .results-table th, .results-table td { padding:8px; font-size:.75rem; }
    .form-grid { grid-template-columns: 1fr; }
    .task-timer-bar { flex-direction: column; align-items: stretch; }
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
    <div class="hud-label">DRONE OPS · v11.2</div>
  </div>
  <h1>Planning Poker</h1>
  <p class="subtitle">// estimate · vote · reveal · excel //</p>

  <div class="card" id="join-screen" style="max-width:900px;">
    <h3>[ СОЗДАТЬ НОВУЮ КОМНАТУ ]</h3>
    <div class="row">
      <input id="create-name-input" placeholder="Ваше имя (Создатель)" maxlength="20">
      <input id="create-room-input" placeholder="Новый ID комнаты" maxlength="20">
    </div>
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
      <button onclick="createRoom()" style="width:100%;">Создать комнату →</button>
    </div>

    <div class="divider"></div>

    <h3>[ ПРИСОЕДИНИТЬСЯ К СУЩЕСТВУЮЩЕЙ ]</h3>
    <div class="room-list" id="room-list">
    </div>
    
    <div id="join-existing-area" class="join-area hidden">
      <div class="join-selected-name" id="join-selected-label">Выбрана комната: ...</div>
      <div class="row">
        <input id="join-name-input" placeholder="Ваше имя (Участник)" maxlength="20">
        <button onclick="joinExistingRoom()" style="width: 150px;">Войти →</button>
      </div>
    </div>
    <p class="footer-note" style="margin-top:20px;">Защита от потери связи: неактивные участники удаляются автоматически</p>
  </div>

  <div id="game-screen" class="hidden" style="width: 100%; display: flex; justify-content: center;">
    <div class="main-layout">
      <div class="left-panel">
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

          <div class="task-timer-bar">
            <div class="task-name-wrapper">
              <label>Оцениваемая задача</label>
              <input class="task-name-input" id="task-name-input" placeholder="Введите название задачи..." onchange="updateTaskName(this.value)">
            </div>
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
              <button id="timer-start-btn" onclick="toggleTimer()" style="padding:8px 12px; font-size:1rem; min-width:40px;">▶</button>
            </div>
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
        </div>
      </div>

      <div class="right-panel">
        <div class="card">
          <h3>[ УЧАСТНИКИ ]</h3>
          <div class="users" id="users"></div>
        </div>
      </div>
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
    <div class="form-grid" id="save-form-fields" style="grid-template-columns: 1fr;">
      <div class="form-group">
        <label>Название задачи (Имя файла)</label>
        <input type="text" id="save-task-title" style="font-weight:bold; color:#ff5555;">
      </div>
      <div id="save-categories-fields" class="form-grid" style="margin-bottom:0;"></div>
    </div>
    <div class="actions-row" style="margin-top:20px;">
      <button onclick="closeModal('save-modal')" class="btn-hide">Отмена</button>
      <button onclick="downloadExcel()" class="btn-download">💾 Скачать</button>
    </div>
  </div>
</div>

<script>
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
const TOTAL_COMPLEXITY_LABEL = "Total Complexity (Story Points)";
const POLL_INTERVAL_MS = 1000;

let state = {
  name: '', room: '', mode: 'normal', isAdmin: false, myVote: null,
  revealed: false, lastData: null, pickedMode: 'normal', detailsVisible: false,
  timerEnd: 0, timerDuration: 20, timerInterval: null, audioCtx: null,
  gameOverPlayed: false, taskName: '', selectedRoomForJoin: '',
  sessionToken: '', pollTimer: null, roomsTimer: null, active: false,
  exportTotalEdited: false, exportDurationEdited: false
};

function makeClientToken() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
  const bytes = new Uint8Array(24);
  if (window.crypto && window.crypto.getRandomValues) window.crypto.getRandomValues(bytes);
  else for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}
function tokenStorageKey(room) { return 'planning-poker-token:' + room; }
function getJoinToken(room, creating) {
  if (!creating) {
    try {
      const existing = sessionStorage.getItem(tokenStorageKey(room));
      if (existing) return existing;
    } catch (_) {}
  }
  return makeClientToken();
}
function saveJoinToken(room, token) {
  try { sessionStorage.setItem(tokenStorageKey(room), token); } catch (_) {}
}
function clearJoinToken(room) {
  try { sessionStorage.removeItem(tokenStorageKey(room)); } catch (_) {}
}

async function apiRequest(path, options = {}) {
  const headers = { 'Accept': 'application/json', ...(options.headers || {}) };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (state.sessionToken) headers['X-Session-Token'] = state.sessionToken;
  const response = await fetch(path, {
    method: options.method || 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: 'no-store'
  });
  let payload;
  try { payload = await response.json(); }
  catch (_) { payload = { ok: false, error: 'Сервер вернул некорректный ответ.' }; }
  if (!response.ok || payload.ok === false) {
    const error = new Error(payload.error || `Ошибка запроса (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return payload;
}
function showRequestError(error) {
  console.error(error);
  alert(error && error.message ? error.message : 'Не удалось выполнить запрос. Проверьте соединение.');
}

function initAudio() {
  try {
    if (!state.audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return;
      state.audioCtx = new AudioContextClass();
    }
    if (state.audioCtx.state === 'suspended') state.audioCtx.resume().catch(() => {});
  } catch (error) { console.warn('Audio is unavailable:', error); }
}
function playTick(isFinal = false) {
  initAudio();
  if (!state.audioCtx || state.audioCtx.state === 'suspended') return;
  try {
    if (isFinal) {
      [440, 349.23, 261.63].forEach((freq, i) => {
        const osc = state.audioCtx.createOscillator();
        const gain = state.audioCtx.createGain();
        const startAt = state.audioCtx.currentTime + i * 0.2;
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(freq, startAt);
        gain.gain.setValueAtTime(0.3, startAt);
        gain.gain.exponentialRampToValueAtTime(0.01, startAt + 0.3);
        osc.connect(gain); gain.connect(state.audioCtx.destination);
        osc.start(startAt); osc.stop(startAt + 0.3);
      });
    } else {
      const osc = state.audioCtx.createOscillator();
      const gain = state.audioCtx.createGain();
      osc.type = 'square';
      osc.frequency.setValueAtTime(1200, state.audioCtx.currentTime);
      gain.gain.setValueAtTime(0.1, state.audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, state.audioCtx.currentTime + 0.05);
      osc.connect(gain); gain.connect(state.audioCtx.destination);
      osc.start(); osc.stop(state.audioCtx.currentTime + 0.05);
    }
  } catch (error) { console.warn('Could not play timer sound:', error); }
}
document.addEventListener('click', initAudio, { once: true });

function pickMode(mode) {
  if (!['normal', 'mega'].includes(mode)) return;
  state.pickedMode = mode;
  document.querySelectorAll('.mode-btn').forEach(button => button.classList.toggle('active', button.dataset.mode === mode));
}
function getOptions(cat) {
  if (cat.id === 'hours') return ['0', '1', '2', '3', '5', '8', '13', '21', '☕'];
  const options = ['0'];
  for (let value = cat.min; value <= cat.max; value++) options.push(String(value));
  options.push('☕');
  return options;
}
function openTooltip(title, body) {
  document.getElementById('tooltip-title').textContent = title;
  document.getElementById('tooltip-body').innerHTML = body;
  document.getElementById('tooltip-modal').classList.add('active');
}
function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove('active');
}

function updateTimerSetting() {
  const value = Number.parseInt(document.getElementById('timer-select').value, 10);
  if (![5, 10, 15, 20, 25, 30, 45, 60].includes(value)) return;
  state.timerDuration = value;
  if (!state.timerEnd) document.getElementById('timer-display').textContent = String(value);
}
async function toggleTimer() {
  if (!state.isAdmin || !state.active) return;
  try {
    if (state.timerEnd > Date.now()) {
      await apiRequest('/api/timer', { method: 'POST', body: { room: state.room, action: 'stop' } });
    } else {
      const seconds = Number.parseInt(document.getElementById('timer-select').value, 10);
      await apiRequest('/api/timer', { method: 'POST', body: { room: state.room, action: 'start', seconds } });
    }
  } catch (error) { showRequestError(error); }
}
function tickTimer() {
  if (!state.timerEnd) return;
  const left = Math.max(0, Math.ceil((state.timerEnd - Date.now()) / 1000));
  const display = document.getElementById('timer-display');
  if (left > 0) {
    if (display.textContent !== String(left)) {
      display.textContent = String(left);
      playTick(false);
    }
    display.classList.add('active');
  } else {
    display.textContent = '0';
    display.classList.remove('active');
    if (state.timerInterval) clearInterval(state.timerInterval);
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
  if (roomFromUrl) {
    document.getElementById('create-room-input').value = roomFromUrl;
    selectRoomToJoin(roomFromUrl);
  }
  loadRooms();
  state.roomsTimer = setInterval(loadRooms, 3000);
});

async function loadRooms() {
  try {
    const data = await apiRequest('/api/rooms');
    const list = document.getElementById('room-list');
    list.replaceChildren();
    if (!Array.isArray(data.rooms) || data.rooms.length === 0) {
      const empty = document.createElement('div');
      empty.style.cssText = "color:#5a5a7a;font-size:.85rem;font-family:'JetBrains Mono';text-align:center;padding:10px;";
      empty.textContent = 'Нет активных комнат';
      list.appendChild(empty);
      return;
    }
    data.rooms.forEach(room => {
      const item = document.createElement('div');
      item.className = 'room-item' + (state.selectedRoomForJoin === room.name ? ' selected' : '');
      item.dataset.room = room.name;
      const title = document.createElement('span');
      title.textContent = '▸ ' + room.name + ' ';
      const tag = document.createElement('span');
      tag.className = 'mode-tag';
      tag.textContent = room.mode === 'mega' ? '[МЕГА]' : '[ОБЫЧН.]';
      title.appendChild(tag);
      const count = document.createElement('span');
      count.className = 'count';
      count.textContent = `${room.users} участн.`;
      item.append(title, count);
      item.addEventListener('click', () => selectRoomToJoin(room.name));
      list.appendChild(item);
    });
  } catch (error) {
    console.warn('Не удалось обновить список комнат:', error);
  }
}
function selectRoomToJoin(roomName) {
  roomName = String(roomName || '').trim().toLowerCase();
  state.selectedRoomForJoin = roomName;
  document.querySelectorAll('.room-item').forEach(item => {
    item.classList.toggle('selected', item.dataset.room === roomName);
  });
  const area = document.getElementById('join-existing-area');
  const label = document.getElementById('join-selected-label');
  if (roomName) {
    area.classList.remove('hidden');
    label.textContent = `Выбрана комната: ${roomName}`;
    document.getElementById('join-name-input').focus();
  } else area.classList.add('hidden');
}
async function createRoom() {
  const name = document.getElementById('create-name-input').value.trim();
  const room = document.getElementById('create-room-input').value.trim().toLowerCase();
  if (!name || !room) return alert('Введите ваше имя и ID новой комнаты');
  const token = getJoinToken(room, true);
  try {
    const response = await apiRequest('/api/join', {
      method: 'POST',
      body: { name, room, mode: state.pickedMode, is_create: true, client_token: token }
    });
    enterRoom(response, token);
  } catch (error) { showRequestError(error); }
}
async function joinExistingRoom() {
  const name = document.getElementById('join-name-input').value.trim();
  const room = state.selectedRoomForJoin;
  if (!name) return alert('Введите ваше имя');
  if (!room) return alert('Сначала выберите комнату из списка');
  const token = getJoinToken(room, false);
  try {
    const response = await apiRequest('/api/join', {
      method: 'POST',
      body: { name, room, is_create: false, client_token: token }
    });
    enterRoom(response, token);
  } catch (error) { showRequestError(error); }
}
function enterRoom(response, token) {
  state.room = response.room_id;
  state.name = response.name;
  state.mode = response.mode || 'normal';
  state.sessionToken = token;
  state.isAdmin = Boolean(response.is_admin);
  state.active = true;
  state.revealed = false;
  state.lastData = null;
  state.myVote = state.mode === 'mega' ? {} : null;
  state.timerEnd = 0;
  state.gameOverPlayed = false;
  saveJoinToken(state.room, token);
  if (state.pollTimer) clearTimeout(state.pollTimer);
  if (state.roomsTimer) clearInterval(state.roomsTimer);

  document.getElementById('join-screen').classList.add('hidden');
  document.getElementById('game-screen').classList.remove('hidden');
  document.getElementById('room-name').textContent = state.room;
  document.getElementById('share-link').value = location.origin + '/?room=' + encodeURIComponent(state.room);
  document.getElementById('task-name-input').readOnly = !state.isAdmin;
  const modeBadge = document.getElementById('mode-badge');
  if (state.mode === 'mega') {
    modeBadge.textContent = 'МЕГА';
    modeBadge.classList.add('mega');
    document.getElementById('normal-mode').classList.add('hidden');
    document.getElementById('mega-mode').classList.remove('hidden');
    document.getElementById('result').classList.add('hidden');
    document.getElementById('mega-result').classList.add('hidden');
    buildMegaUI();
  } else {
    modeBadge.textContent = 'ОБЫЧНЫЙ';
    modeBadge.classList.remove('mega');
    document.getElementById('normal-mode').classList.remove('hidden');
    document.getElementById('mega-mode').classList.add('hidden');
    document.getElementById('result').classList.remove('hidden');
    document.getElementById('mega-result').classList.add('hidden');
    buildCards();
  }
  const timerBox = document.getElementById('timer-box');
  timerBox.classList.remove('hidden');
  document.getElementById('timer-start-btn').style.display = state.isAdmin ? '' : 'none';
  document.getElementById('timer-select').style.display = state.isAdmin ? '' : 'none';
  poll();
}

async function updateTaskName(value) {
  if (!state.isAdmin || !state.active) return;
  state.taskName = String(value).slice(0, 200);
  try {
    await apiRequest('/api/task', { method: 'POST', body: { room: state.room, task_name: state.taskName } });
  } catch (error) { showRequestError(error); }
}
function buildCards() {
  const grid = document.getElementById('cards');
  grid.replaceChildren();
  NORMAL_CARDS.forEach(value => {
    const card = document.createElement('div');
    card.className = 'poker-card';
    card.textContent = value;
    card.dataset.value = value;
    card.addEventListener('click', () => vote(value));
    grid.appendChild(card);
  });
}
async function vote(value) {
  if (state.revealed || !state.active || !NORMAL_CARDS.includes(String(value))) return;
  
  // Оптимистичный UI (мгновенно)
  state.myVote = String(value);
  document.querySelectorAll('.poker-card').forEach(card => {
    card.classList.toggle('selected', card.dataset.value === state.myVote);
  });

  try {
    await apiRequest('/api/vote', { method: 'POST', body: { room: state.room, vote: String(value) } });
  } catch (error) { showRequestError(error); }
}
function buildMegaUI() {
  const container = document.getElementById('mega-categories');
  container.replaceChildren();
  [...CATEGORIES, HOURS_CAT].forEach(cat => {
    const block = document.createElement('div');
    block.className = 'mega-cat';
    block.dataset.catId = cat.id;
    const header = document.createElement('div');
    header.className = 'mega-cat-header';
    const name = document.createElement('span');
    name.className = 'mega-cat-name';
    name.append(document.createTextNode(cat.name + ' '));
    const info = document.createElement('div');
    info.className = 'info-btn';
    info.setAttribute('role', 'button');
    info.tabIndex = 0;
    info.style.padding = '0';
    info.textContent = 'i';
    info.title = 'Описание категории';
    info.addEventListener('click', () => showCatInfo(cat.id));
    info.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') showCatInfo(cat.id); });
    name.appendChild(info);
    const range = document.createElement('span');
    range.className = 'mega-cat-range';
    range.textContent = cat.range;
    header.append(name, range);
    const options = document.createElement('div');
    options.className = 'mega-cat-options';
    getOptions(cat).forEach(value => {
      const card = document.createElement('div');
      card.className = 'mega-card';
      card.textContent = value;
      card.dataset.value = value;
      card.dataset.cat = cat.id;
      card.addEventListener('click', () => voteMega(cat.id, value));
      options.appendChild(card);
    });
    block.append(header, options);
    container.appendChild(block);
  });
}
function showCatInfo(id) {
  if (id === 'hours') openTooltip(HOURS_CAT.name + ' (' + HOURS_CAT.range + ')', HOURS_CAT.tooltip);
  else {
    const category = CATEGORIES.find(item => item.id === id);
    if (category) openTooltip(category.name + ' (' + category.range + ')', category.tooltip);
  }
}
async function voteMega(categoryId, value) {
  if (state.revealed || !state.active) return;
  const category = [...CATEGORIES, HOURS_CAT].find(item => item.id === categoryId);
  if (!category || !getOptions(category).includes(String(value))) return;

  // Оптимистичный UI (мгновенно)
  if (!state.myVote) state.myVote = {};
  state.myVote[categoryId] = String(value);
  document.querySelectorAll(`.mega-card[data-cat="${categoryId}"]`).forEach(card => {
    card.classList.toggle('selected', card.dataset.value === String(value));
  });

  try {
    await apiRequest('/api/vote', { method: 'POST', body: { room: state.room, category: categoryId, value: String(value) } });
  } catch (error) { showRequestError(error); }
}
async function revealResults() {
  if (!state.isAdmin || !state.active) return;
  try { await apiRequest('/api/reveal', { method: 'POST', body: { room: state.room } }); }
  catch (error) { showRequestError(error); }
}
async function resetVotes() {
  if (!state.isAdmin || !state.active) return;
  try { await apiRequest('/api/reset', { method: 'POST', body: { room: state.room } }); }
  catch (error) { showRequestError(error); }
}
async function leaveRoom() {
  if (!state.active) { location.href = '/'; return; }
  const room = state.room;
  try {
    await apiRequest('/api/leave', { method: 'POST', body: { room } });
  } catch (error) {
    console.warn('Leave request failed:', error);
  } finally {
    state.active = false;
    if (state.pollTimer) clearTimeout(state.pollTimer);
    if (state.timerInterval) clearInterval(state.timerInterval);
    clearJoinToken(room);
    location.href = '/';
  }
}
async function transferAdmin(targetId) {
  if (!state.isAdmin || !state.active) return;
  const target = (state.lastData?.users || []).find(user => user.id === targetId);
  if (!target || !confirm(`Передать права администратора пользователю ${target.name}?`)) return;
  try { await apiRequest('/api/transfer_admin', { method: 'POST', body: { room: state.room, target_id: targetId } }); }
  catch (error) { showRequestError(error); }
}
async function copyLink(event) {
  const input = document.getElementById('share-link');
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(input.value);
    else {
      input.select();
      if (!document.execCommand('copy')) throw new Error('Копирование не поддерживается браузером.');
    }
    const button = event.currentTarget;
    const original = button.textContent;
    button.textContent = '✓ OK';
    setTimeout(() => { button.textContent = original; }, 1500);
  } catch (error) { showRequestError(error); }
}
function toggleDetails() {
  state.detailsVisible = !state.detailsVisible;
  document.getElementById('toggle-details-btn').textContent = state.detailsVisible ? '🙈 Скрыть голоса' : '👥 Голоса команды';
  if (state.lastData) renderMegaResults(state.lastData);
}

async function poll() {
  if (!state.active || !state.room) return;
  try {
    const data = await apiRequest('/api/state?room=' + encodeURIComponent(state.room));
    updateUI(data);
  } catch (error) {
    if (error.status === 401 || error.status === 404) {
      state.active = false;
      if (state.pollTimer) clearTimeout(state.pollTimer);
      alert('Сессия участника больше не активна. Возможно, вы были отключены из-за потери связи.');
      location.href = '/';
      return;
    }
    console.warn('Не удалось обновить состояние комнаты:', error);
  } finally {
    if (state.active) state.pollTimer = setTimeout(poll, POLL_INTERVAL_MS);
  }
}
function makeBadge(text, className) {
  const badge = document.createElement('span');
  badge.className = 'badge' + (className ? ' ' + className : '');
  badge.textContent = text;
  return badge;
}
function updateUsersList(data) {
  const usersElement = document.getElementById('users');
  usersElement.replaceChildren();
  let completeCount = 0;
  const total = data.users.length;
  data.users.forEach(user => {
    const isCurrent = user.id === data.current_user_id;
    const isAdmin = user.id === data.admin_id;
    if (state.mode === 'mega' ? user.ready : user.has_voted) completeCount++;
    const row = document.createElement('div');
    row.className = 'user-row' + ((state.mode === 'mega' ? user.ready : user.has_voted) ? ' voted' : '');
    
    // Фикс длинных имен
    const name = document.createElement('span');
    name.className = 'user-name';
    name.textContent = (isCurrent ? '▶ ' : '') + user.name + (isCurrent ? ' (вы)' : '');
    name.title = user.name;
    
    const right = document.createElement('div');
    right.className = 'user-status-wrap';
    
    if (isAdmin) right.appendChild(makeBadge('ADMIN', 'admin'));
    else if (state.isAdmin) {
      const transfer = document.createElement('button');
      transfer.type = 'button';
      transfer.className = 'btn-transfer';
      transfer.textContent = '👑';
      transfer.title = 'Сделать администратором';
      transfer.addEventListener('click', () => transferAdmin(user.id));
      right.appendChild(transfer);
    }
    let status;
    if (state.mode === 'mega') {
      const totalFields = CATEGORIES.length + 1;
      if (data.revealed) status = makeBadge(`✓ ${user.filled}/${totalFields}`, 'voted');
      else if (user.ready) status = makeBadge('✓ готов', 'voted');
      else if (user.filled > 0) status = makeBadge(`${user.filled}/${totalFields}`, 'partial');
      else status = makeBadge('…WAIT', '');
    } else {
      if (data.revealed && user.has_voted) status = makeBadge(user.vote ?? '✓', 'voted');
      else if (user.has_voted) status = makeBadge('✓ VOTED', 'voted');
      else status = makeBadge('…WAIT', '');
    }
    right.appendChild(status);
    row.append(name, right);
    usersElement.appendChild(row);
  });
  if (state.mode === 'mega') {
    document.getElementById('mega-votes-info').textContent = data.revealed
      ? `Полностью оценили: ${completeCount} / ${total}`
      : `${completeCount} / ${total} · оценили все категории`;
  } else {
    document.getElementById('votes-info').textContent = data.revealed
      ? `Проголосовало: ${completeCount} / ${total}`
      : `${completeCount} / ${total} · голосуют`;
  }
}
function updateUI(data) {
  if (!data || !Array.isArray(data.users)) return;
  state.lastData = data;
  state.isAdmin = data.admin_id === data.current_user_id;
  document.getElementById('task-name-input').readOnly = !state.isAdmin;
  document.getElementById('timer-start-btn').style.display = state.isAdmin ? '' : 'none';
  document.getElementById('timer-select').style.display = state.isAdmin ? '' : 'none';

  if (typeof data.task_name === 'string') {
    state.taskName = data.task_name;
    const taskInput = document.getElementById('task-name-input');
    if (document.activeElement !== taskInput) taskInput.value = data.task_name;
  }
  const timerEnd = Number(data.timer_end) || 0;
  if (timerEnd > Date.now()) {
    if (state.timerEnd !== timerEnd) {
      state.timerEnd = timerEnd;
      state.gameOverPlayed = false;
      if (!state.timerInterval) state.timerInterval = setInterval(tickTimer, 200);
    }
    document.getElementById('timer-start-btn').textContent = '⏹';
    tickTimer();
  } else {
    state.timerEnd = 0;
    if (state.timerInterval) clearInterval(state.timerInterval);
    state.timerInterval = null;
    document.getElementById('timer-display').textContent = String(state.timerDuration);
    document.getElementById('timer-display').classList.remove('active');
    document.getElementById('timer-start-btn').textContent = '▶';
  }

  state.myVote = data.my_vote;
  const wasRevealed = state.revealed;
  state.revealed = Boolean(data.revealed);
  if (state.revealed && !wasRevealed) triggerExplosion();

  if (state.mode === 'mega') {
    document.querySelectorAll('.mega-card').forEach(card => {
      const value = state.myVote ? state.myVote[card.dataset.cat] : null;
      const selected = value !== null && value !== undefined && card.dataset.value === value;
      card.classList.toggle('selected', selected);
      card.style.pointerEvents = state.revealed ? 'none' : 'auto';
      card.style.opacity = !state.revealed || selected ? '1' : '0.4';
    });
    document.querySelectorAll('.mega-cat').forEach(block => {
      const value = state.myVote ? state.myVote[block.dataset.catId] : null;
      block.classList.toggle('done', value !== null && value !== undefined);
    });
  } else {
    document.querySelectorAll('.poker-card').forEach(card => {
      const selected = card.dataset.value === state.myVote;
      card.classList.toggle('selected', selected);
      card.style.pointerEvents = state.revealed ? 'none' : 'auto';
      card.style.opacity = !state.revealed || selected ? '1' : '0.4';
    });
  }

  const revealButton = document.getElementById('reveal-btn');
  const saveButton = document.getElementById('save-btn');
  const resetButton = document.getElementById('reset-btn');
  if (data.revealed) {
    revealButton.textContent = '🙈 Hide';
    revealButton.classList.remove('btn-reveal');
    revealButton.classList.add('btn-hide');
    revealButton.onclick = resetVotes;
    if (saveButton) saveButton.style.display = state.mode === 'mega' ? 'block' : 'none';
  } else {
    revealButton.textContent = '👁 Reveal';
    revealButton.classList.add('btn-reveal');
    revealButton.classList.remove('btn-hide');
    revealButton.onclick = revealResults;
    if (saveButton) saveButton.style.display = 'none';
  }
  revealButton.disabled = !state.isAdmin;
  revealButton.style.opacity = state.isAdmin ? '1' : '0.3';
  resetButton.disabled = !state.isAdmin;
  resetButton.style.opacity = state.isAdmin ? '1' : '0.3';

  updateUsersList(data);
  if (state.mode === 'normal') {
    const numericVotes = data.users
      .filter(user => user.has_voted && user.vote !== null && user.vote !== undefined)
      .map(user => Number.parseFloat(user.vote))
      .filter(Number.isFinite);
    const resultElement = document.getElementById('result');
    if (data.revealed && numericVotes.length > 0) {
      const average = numericVotes.reduce((sum, value) => sum + value, 0) / numericVotes.length;
      document.getElementById('avg-value').textContent = average.toFixed(1);
      resultElement.classList.add('ready');
    } else {
      document.getElementById('avg-value').textContent = '—';
      if (!data.revealed) resultElement.classList.remove('ready');
    }
  } else {
    const result = document.getElementById('mega-result');
    if (data.revealed) {
      result.classList.remove('hidden');
      renderMegaResults(data);
    } else result.classList.add('hidden');
  }
}

function appendCell(row, value, className = '') {
  const cell = document.createElement('td');
  if (className) cell.className = className;
  cell.textContent = value === null || value === undefined ? '—' : String(value);
  row.appendChild(cell);
  return cell;
}
function renderMegaResults(data) {
  const thead = document.getElementById('results-thead');
  const tbody = document.getElementById('results-tbody');
  const tfoot = document.getElementById('results-tfoot');
  const users = data.users || [];
  thead.replaceChildren(); tbody.replaceChildren(); tfoot.replaceChildren();

  const headerRow = document.createElement('tr');
  ['Категория', 'Min', 'Max', 'Avg'].forEach(label => {
    const th = document.createElement('th'); th.textContent = label; headerRow.appendChild(th);
  });
  if (state.detailsVisible) users.forEach(user => {
    const th = document.createElement('th');
    th.className = 'user-col' + (user.id === data.current_user_id ? ' me' : '');
    th.textContent = user.name;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);

  let totalSumComplexity = 0;
  let totalMin = 0;
  let totalMax = 0;
  let anyNumericVote = false;
  const allCategories = [...CATEGORIES, HOURS_CAT];
  allCategories.forEach(category => {
    const values = users.map(user => user.votes ? user.votes[category.id] : null);
    const numericVotes = values
      .filter(value => value !== null && value !== undefined && value !== '☕')
      .map(value => Number.parseFloat(value))
      .filter(Number.isFinite);
    const row = document.createElement('tr');
    let average = null;
    if (numericVotes.length > 0) {
      average = numericVotes.reduce((sum, value) => sum + value, 0) / numericVotes.length;
      anyNumericVote = true;
      if (category.id !== 'hours') {
        totalSumComplexity += average;
        totalMin += category.min;
        totalMax += category.max;
      }
    }
    appendCell(row, category.name);
    appendCell(row, category.min);
    appendCell(row, category.max);
    const averageCell = appendCell(row, average === null ? '—' : average.toFixed(1));
    averageCell.innerHTML = average === null ? '—' : `<b>${average.toFixed(1)}</b>`;
    if (state.detailsVisible) values.forEach((value, index) => {
      appendCell(row, value, 'user-col' + (users[index].id === data.current_user_id ? ' me' : ''));
    });
    tbody.appendChild(row);
  });

  const hoursVotes = users
    .map(user => user.votes ? user.votes.hours : null)
    .filter(value => value !== null && value !== undefined && value !== '☕')
    .map(value => Number.parseFloat(value))
    .filter(Number.isFinite);
  const averageHours = hoursVotes.length
    ? hoursVotes.reduce((sum, value) => sum + value, 0) / hoursVotes.length
    : 0;
  const duration = calcDuration(averageHours);
  const durationRow = document.createElement('tr');
  appendCell(durationRow, 'Duration (auto)');
  appendCell(durationRow, '-');
  appendCell(durationRow, '-');
  const durationAverage = appendCell(durationRow, duration);
  durationAverage.innerHTML = `<b>${duration}</b>`;
  if (state.detailsVisible) users.forEach(() => appendCell(durationRow, ''));
  tbody.appendChild(durationRow);

  const footerRow = document.createElement('tr');
  appendCell(footerRow, TOTAL_COMPLEXITY_LABEL);
  appendCell(footerRow, totalMin);
  appendCell(footerRow, totalMax);
  const totalCell = appendCell(footerRow, anyNumericVote ? totalSumComplexity.toFixed(1) : '—');
  totalCell.id = 'total-avg';
  if (state.detailsVisible) users.forEach(user => appendCell(footerRow, '', 'user-col' + (user.id === data.current_user_id ? ' me' : '')));
  tfoot.appendChild(footerRow);
}
function calcDuration(avgHours) {
  if (!Number.isFinite(avgHours) || avgHours <= 0) return 0;
  const mapping = { 1: 1, 2: 2, 3: 2, 5: 3, 8: 4, 13: 6, 21: 10 };
  const keys = [1, 2, 3, 5, 8, 13, 21];
  let closest = keys[0];
  let minDifference = Infinity;
  keys.forEach(key => {
    const difference = Math.abs(key - avgHours);
    if (difference < minDifference) { minDifference = difference; closest = key; }
  });
  return mapping[closest];
}

function createFormGroup(labelText, inputId, value, options = {}) {
  const group = document.createElement('div');
  group.className = 'form-group';
  const label = document.createElement('label');
  label.htmlFor = inputId;
  label.textContent = labelText;
  const input = document.createElement('input');
  input.type = 'number';
  input.id = inputId;
  input.step = options.step || '0.1';
  input.min = options.min === undefined ? '0' : String(options.min);
  if (options.max !== undefined) input.max = String(options.max);
  input.value = String(value);
  input.required = true;
  group.append(label, input);
  return { group, input };
}
function getAverageForCategory(users, categoryId) {
  const values = users
    .map(user => user.votes ? user.votes[categoryId] : null)
    .filter(value => value !== null && value !== undefined && value !== '☕')
    .map(value => Number.parseFloat(value))
    .filter(Number.isFinite);
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}
function getExportCategoryTotal() {
  return CATEGORIES.reduce((sum, category) => {
    const input = document.getElementById('save-' + category.id);
    return sum + (input ? Number.parseFloat(input.value) || 0 : 0);
  }, 0);
}
function refreshExportTotal() {
  const totalInput = document.getElementById('save-total');
  if (totalInput && !state.exportTotalEdited) totalInput.value = getExportCategoryTotal().toFixed(1);
}
function refreshExportDuration() {
  const hoursInput = document.getElementById('save-hours');
  const durationInput = document.getElementById('save-duration');
  if (hoursInput && durationInput && !state.exportDurationEdited) {
    durationInput.value = String(calcDuration(Number.parseFloat(hoursInput.value) || 0));
  }
}
function openSaveModal() {
  const data = state.lastData;
  if (!data || !data.revealed || state.mode !== 'mega') return;
  document.getElementById('save-task-title').value = state.taskName || 'Planning_Poker_' + state.room;
  const form = document.getElementById('save-categories-fields');
  form.replaceChildren();
  state.exportTotalEdited = false;
  state.exportDurationEdited = false;
  CATEGORIES.concat(HOURS_CAT).forEach(category => {
    const average = getAverageForCategory(data.users, category.id);
    const field = createFormGroup(category.name, 'save-' + category.id, average.toFixed(1), {
      min: 0, max: category.id === 'hours' ? 21 : category.max, step: '0.1'
    });
    field.input.addEventListener('input', () => {
      field.input.classList.add('edited');
      if (category.id === 'hours') refreshExportDuration();
      else refreshExportTotal();
    });
    form.appendChild(field.group);
  });

  const totalInput = createFormGroup(TOTAL_COMPLEXITY_LABEL, 'save-total', getExportCategoryTotal().toFixed(1), { min: 0, max: 43, step: '0.1' });
  totalInput.input.addEventListener('input', () => {
    state.exportTotalEdited = true;
    totalInput.input.classList.add('edited');
  });
  form.appendChild(totalInput.group);

  const durationField = createFormGroup('Duration (Continuity)', 'save-duration', calcDuration(Number.parseFloat(document.getElementById('save-hours').value) || 0), { min: 0, max: 10, step: '1' });
  durationField.input.addEventListener('input', () => {
    state.exportDurationEdited = true;
    durationField.input.classList.add('edited');
  });
  
  // Иконка подсказки (используем div вместо button)
  const hintButton = document.createElement('div');
  hintButton.className = 'info-btn';
  hintButton.style.marginLeft = '8px';
  hintButton.textContent = 'i';
  hintButton.title = 'Как рассчитывается Duration';
  hintButton.addEventListener('click', () => openTooltip('Duration Calculation', 'Соотношение средних часов к продолжительности:<br><br><b>1</b> час = <b>1</b><br><b>2</b> часа = <b>2</b><br><b>3</b> часа = <b>2</b><br><b>5</b> часов = <b>3</b><br><b>8</b> часов = <b>4</b><br><b>13</b> часов = <b>6</b><br><b>21</b> час = <b>10</b>'));
  durationField.group.querySelector('label').appendChild(hintButton);
  durationField.input.addEventListener('input', () => {
    const value = Number(durationField.input.value);
    if (!Number.isInteger(value)) durationField.input.setCustomValidity('Введите целое число от 0 до 10.');
    else durationField.input.setCustomValidity('');
  });
  form.appendChild(durationField.group);
  document.getElementById('save-modal').classList.add('active');
}
function readNumericInput(id, label, min, max, integer = false) {
  const input = document.getElementById(id);
  if (!input) throw new Error(`Не найдено поле «${label}».`);
  const raw = input.value.trim();
  const value = Number(raw);
  if (raw === '' || !Number.isFinite(value)) throw new Error(`Поле «${label}» должно содержать число.`);
  if (value < min || value > max) throw new Error(`Поле «${label}» должно быть от ${min} до ${max}.`);
  if (integer && !Number.isInteger(value)) throw new Error(`Поле «${label}» должно содержать целое число.`);
  return value;
}
function escapeHtml(value) {
  return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function safeFileName(value) {
  const cleaned = String(value || 'Planning_Poker')
    .replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_')
    .replace(/\s+/g, '_')
    .replace(/[. ]+$/g, '')
    .slice(0, 100);
  return cleaned || 'Planning_Poker';
}
function downloadExcel() {
  try {
    const taskTitle = document.getElementById('save-task-title').value.trim() || ('Planning_Poker_' + state.room);
    const vals = {
      backend: readNumericInput('save-backend', 'Backend', 0, 7),
      frontend: readNumericInput('save-frontend', 'Frontend', 0, 4),
      business: readNumericInput('save-business', 'Business Process', 0, 9),
      design: readNumericInput('save-design', 'Design', 0, 6),
      database: readNumericInput('save-database', 'DB', 0, 8),
      integrations: readNumericInput('save-integrations', 'Integrations', 0, 9),
      hours: readNumericInput('save-hours', 'Hours', 0, 21),
      total: readNumericInput('save-total', TOTAL_COMPLEXITY_LABEL, 0, 43),
      duration: readNumericInput('save-duration', 'Duration', 0, 10, true)
    };
    const decimalCell = value => `<td class="num" x:num="${value.toFixed(1)}">${value.toFixed(1).replace('.', ',')}</td>`;
    const integerCell = value => `<td class="int" x:num="${value}">${value}</td>`;
    let html = '<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel">';
    html += '<head><meta charset="UTF-8"><style>';
    html += 'table{border-collapse:collapse;font-family:Arial,sans-serif}th,td{border:1px solid #444;padding:8px 12px;text-align:center}th{background:#5b9bd5;color:white;font-weight:bold}.light{background:#e9eff7;font-weight:bold}.green{background:#70ad47;color:white}.num{mso-number-format:"0\\.0"}.int{mso-number-format:"0"}caption{font-weight:bold;text-align:left;margin-bottom:10px}';
    html += '</style></head><body><table>';
    html += `<caption>${escapeHtml(taskTitle)}</caption><tr>`;
    html += '<th>Backend (0-7)</th><th>Frontend (0-4)</th><th>Business Process (0-9)</th>';
    html += '<th>Design (0-6)</th><th>DB (0-8)</th><th>Integrations (0-9)</th><th>Hours</th>';
    html += `<th class="light">${escapeHtml(TOTAL_COMPLEXITY_LABEL)}</th><th class="green">Duration (Continuity)</th></tr><tr>`;
    html += decimalCell(vals.backend) + decimalCell(vals.frontend) + decimalCell(vals.business);
    html += decimalCell(vals.design) + decimalCell(vals.database) + decimalCell(vals.integrations) + decimalCell(vals.hours);
    html += `<td class="light num" x:num="${vals.total.toFixed(1)}">${vals.total.toFixed(1).replace('.', ',')}</td>`;
    html += `<td class="green int" x:num="${vals.duration}">${vals.duration}</td></tr></table></body></html>`;
    const blob = new Blob(['\ufeff' + html], { type: 'application/vnd.ms-excel;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = safeFileName(taskTitle) + '.xls';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    closeModal('save-modal');
  } catch (error) {
    showRequestError(error);
  }
}

['create-name-input', 'create-room-input', 'join-name-input'].forEach(id => {
  const input = document.getElementById(id);
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      if (id.startsWith('create')) createRoom();
      else joinExistingRoom();
    }
  });
});
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html; charset=utf-8")


@app.route("/api/rooms", methods=["GET"])
def list_rooms():
    with ROOM_LOCK:
        now = time.time()
        for room_id in list(rooms):
            cleanup_room(room_id, now)
        result = [
            {"name": room_id, "users": len(room["users"]), "mode": room["mode"]}
            for room_id, room in sorted(rooms.items())
        ]
        return jsonify({"rooms": result})


@app.route("/api/join", methods=["POST"])
def join():
    data = json_body()
    room_id = normalize_room_id(data.get("room"))
    name = normalize_name(data.get("name"))
    digest = token_digest(data.get("client_token", ""))
    is_create = data.get("is_create", False)
    if not isinstance(is_create, bool):
        raise APIError("Некорректный параметр создания комнаты.")
    with ROOM_LOCK:
        if is_create:
            if room_id in rooms:
                raise APIError(
                    "Комната с таким ID уже существует. Выберите её из списка ниже.",
                    409,
                )
            mode = data.get("mode", "normal")
            if mode not in ("normal", "mega"):
                raise APIError("Неизвестный режим комнаты.")
            room = new_room(mode)
            rooms[room_id] = room
        else:
            cleanup_room(room_id)
            room = rooms.get(room_id)
            if room is None:
                raise APIError("Комната не найдена.", 404)
        for user_id, user in room["users"].items():
            if hmac.compare_digest(user["token_hash"], digest):
                if user["name"].casefold() != name.casefold():
                    raise APIError("Для этой сессии уже используется другое имя.", 409)
                user["last_seen"] = time.time()
                admin = room["users"].get(room["admin_id"])
                return jsonify(
                    {
                        "ok": True,
                        "room_id": room_id,
                        "name": user["name"],
                        "mode": room["mode"],
                        "admin": admin["name"] if admin else "",
                        "is_admin": room["admin_id"] == user_id,
                    }
                )
        if room["revealed"]:
            raise APIError(
                "Результаты уже раскрыты. Попросите администратора сбросить голосование.",
                409,
            )
        if any(
            user["name"].casefold() == name.casefold()
            for user in room["users"].values()
        ):
            raise APIError(
                "Участник с таким именем уже находится в комнате. Выберите другое имя.",
                409,
            )
        user_id = uuid.uuid4().hex
        now = time.time()
        room["users"][user_id] = {
            "id": user_id,
            "name": name,
            "token_hash": digest,
            "vote": new_vote(room["mode"]),
            "joined_at": now,
            "last_seen": now,
        }
        if room["admin_id"] is None:
            room["admin_id"] = user_id
        admin = room["users"].get(room["admin_id"])
        return jsonify(
            {
                "ok": True,
                "room_id": room_id,
                "name": name,
                "mode": room["mode"],
                "admin": admin["name"] if admin else "",
                "is_admin": room["admin_id"] == user_id,
            }
        )


@app.route("/api/state", methods=["GET"])
def get_state():
    with ROOM_LOCK:
        room_id, room, actor_id, _actor = get_room_and_actor(
            request.args.get("room", "")
        )
        return jsonify(room_state(room_id, room, actor_id))


@app.route("/api/vote", methods=["POST"])
def vote():
    data = json_body()
    with ROOM_LOCK:
        _room_id, room, _actor_id, actor = get_room_and_actor(data.get("room", ""))
        if room["revealed"]:
            raise APIError("Голосование уже раскрыто. Сначала выполните Reset.", 409)
        if room["mode"] == "mega":
            category_id, value = data.get("category"), data.get("value")
            if category_id not in CATEGORY_BY_ID:
                raise APIError("Неизвестная категория голосования.")
            category = CATEGORY_BY_ID[category_id]
            options = (
                HOURS_VOTES
                if category_id == "hours"
                else (
                    {"0", "☕"}
                    | {
                        str(number)
                        for number in range(category["min"], category["max"] + 1)
                    }
                )
            )
            if not isinstance(value, str) or value not in options:
                raise APIError("Недопустимое значение оценки.")
            actor["vote"][category_id] = value
        else:
            value = data.get("vote")
            if not isinstance(value, str) or value not in NORMAL_VOTES:
                raise APIError("Недопустимое значение голоса.")
            actor["vote"] = value
        return jsonify({"ok": True})


@app.route("/api/reveal", methods=["POST"])
def reveal():
    data = json_body()
    with ROOM_LOCK:
        _room_id, room, actor_id, _actor = get_room_and_actor(data.get("room", ""))
        require_admin(room, actor_id)
        room["revealed"] = True
        room["timer_end"] = 0
        return jsonify({"ok": True})


@app.route("/api/reset", methods=["POST"])
def reset():
    data = json_body()
    with ROOM_LOCK:
        _room_id, room, actor_id, _actor = get_room_and_actor(data.get("room", ""))
        require_admin(room, actor_id)
        room["revealed"] = False
        room["timer_end"] = 0
        for user in room["users"].values():
            user["vote"] = new_vote(room["mode"])
        return jsonify({"ok": True})


@app.route("/api/leave", methods=["POST"])
def leave():
    data = json_body()
    with ROOM_LOCK:
        room_id, room, actor_id, _actor = get_room_and_actor(data.get("room", ""))
        was_admin = room["admin_id"] == actor_id
        room["users"].pop(actor_id, None)
        if not room["users"]:
            rooms.pop(room_id, None)
        elif was_admin:
            next_admin(room)
        return jsonify({"ok": True})


@app.route("/api/transfer_admin", methods=["POST"])
def transfer_admin():
    data = json_body()
    with ROOM_LOCK:
        _room_id, room, actor_id, _actor = get_room_and_actor(data.get("room", ""))
        require_admin(room, actor_id)
        target_id = data.get("target_id")
        if not isinstance(target_id, str) or target_id not in room["users"]:
            raise APIError("Участник, которому передаются права, не найден.", 404)
        room["admin_id"] = target_id
        return jsonify({"ok": True})


@app.route("/api/task", methods=["POST"])
def update_task():
    data = json_body()
    task_name = data.get("task_name", "")
    if not isinstance(task_name, str):
        raise APIError("Название задачи должно быть текстом.")
    task_name = task_name.strip()
    if len(task_name) > 200 or any(
        ord(char) < 32 or ord(char) == 127 for char in task_name
    ):
        raise APIError(
            "Название задачи не должно превышать 200 символов и содержать управляющие символы."
        )
    with ROOM_LOCK:
        _room_id, room, actor_id, _actor = get_room_and_actor(data.get("room", ""))
        require_admin(room, actor_id)
        room["task_name"] = task_name
        return jsonify({"ok": True})


@app.route("/api/timer", methods=["POST"])
def timer():
    data = json_body()
    with ROOM_LOCK:
        _room_id, room, actor_id, _actor = get_room_and_actor(data.get("room", ""))
        require_admin(room, actor_id)
        action = data.get("action")
        if action == "start":
            seconds = data.get("seconds")
            if (
                isinstance(seconds, bool)
                or not isinstance(seconds, int)
                or seconds not in TIMER_SECONDS
            ):
                raise APIError("Недопустимая длительность таймера.")
            room["timer_end"] = int(time.time() * 1000) + seconds * 1000
        elif action == "stop":
            room["timer_end"] = 0
        else:
            raise APIError("Неизвестное действие таймера.")
        return jsonify({"ok": True, "timer_end": room["timer_end"]})


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=False, threaded=True)
