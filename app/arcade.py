"""日替わりクイズとXP・称号・ペット進化の永続化。"""
import hashlib
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import RLock

DB_PATH = os.getenv("ARCADE_DB_PATH", "data/arcade.db")
_LOCK = RLock()

QUESTIONS = [
    {"q": "水が凍る温度は、標準的な気圧で何℃？", "choices": ["0℃", "10℃", "32℃", "100℃"], "answer": 0, "topic": "理科"},
    {"q": "日本で最も高い山は？", "choices": ["北岳", "富士山", "槍ヶ岳", "立山"], "answer": 1, "topic": "地理"},
    {"q": "太陽系で最も大きい惑星は？", "choices": ["地球", "火星", "木星", "金星"], "answer": 2, "topic": "宇宙"},
    {"q": "『走れメロス』を書いた作家は？", "choices": ["夏目漱石", "太宰治", "芥川龍之介", "宮沢賢治"], "answer": 1, "topic": "国語"},
    {"q": "三角形の内角の和は？", "choices": ["90度", "180度", "270度", "360度"], "answer": 1, "topic": "数学"},
    {"q": "植物が光を使って養分を作るはたらきは？", "choices": ["蒸発", "発酵", "光合成", "呼吸だけ"], "answer": 2, "topic": "理科"},
    {"q": "英語の ‘library’ の意味は？", "choices": ["図書館", "実験室", "駅", "病院"], "answer": 0, "topic": "英語"},
    {"q": "日本の都道府県の数は？", "choices": ["43", "45", "47", "49"], "answer": 2, "topic": "地理"},
    {"q": "地球が太陽の周りを一周するのにかかる時間はおよそ？", "choices": ["1日", "1か月", "1年", "10年"], "answer": 2, "topic": "宇宙"},
    {"q": "1キロメートルは何メートル？", "choices": ["10", "100", "1000", "10000"], "answer": 2, "topic": "数学"},
]


def _connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=10000")
    con.execute("""CREATE TABLE IF NOT EXISTS arcade_progress (
        username TEXT PRIMARY KEY, xp INTEGER NOT NULL DEFAULT 0,
        correct INTEGER NOT NULL DEFAULT 0, streak INTEGER NOT NULL DEFAULT 0,
        last_day TEXT NOT NULL DEFAULT '', pet_stage INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS arcade_answers (
        username TEXT NOT NULL, day TEXT NOT NULL, answer INTEGER NOT NULL,
        correct INTEGER NOT NULL, xp_awarded INTEGER NOT NULL,
        PRIMARY KEY(username, day))""")
    return con


def today():
    # Site's daily reset uses UTC to remain consistent across server regions.
    return datetime.now(timezone.utc).date().isoformat()


def daily_question():
    day = today()
    idx = int(hashlib.sha256(day.encode()).hexdigest()[:8], 16) % len(QUESTIONS)
    q = dict(QUESTIONS[idx])
    q["choices"] = list(q["choices"])
    q["day"] = day
    return q


def title_for(xp):
    titles = [(500, "クイズ伝説"), (250, "雑学マスター"), (100, "ひらめき名人"),
              (40, "知識ハンター"), (10, "挑戦者"), (0, "見習い")]
    return next(label for threshold, label in titles if xp >= threshold)


def _pet_stage(xp):
    if xp >= 500: return 4
    if xp >= 250: return 3
    if xp >= 100: return 2
    if xp >= 30: return 1
    return 0


def get_progress(username):
    with _LOCK:
        con = _connect()
        try:
            con.execute("INSERT OR IGNORE INTO arcade_progress(username) VALUES (?)", (username,))
            row = con.execute("SELECT * FROM arcade_progress WHERE username=?", (username,)).fetchone()
            d = dict(row)
            d["level"] = 1 + d["xp"] // 50
            d["next_level_xp"] = (d["level"] * 50) - d["xp"]
            d["pet_stage"] = _pet_stage(d["xp"])
            return d
        finally:
            con.close()


def get_today_result(username):
    with _LOCK:
        con = _connect()
        try:
            row = con.execute("SELECT * FROM arcade_answers WHERE username=? AND day=?", (username, today())).fetchone()
            return dict(row) if row else None
        finally:
            con.close()


def submit_answer(username, question, answer):
    day = today()
    is_correct = int(answer == question["answer"])
    awarded = 10 if is_correct else 0
    with _LOCK:
        con = _connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            try:
                con.execute("INSERT OR IGNORE INTO arcade_progress(username) VALUES (?)", (username,))
                exists = con.execute("SELECT 1 FROM arcade_answers WHERE username=? AND day=?", (username, day)).fetchone()
                if exists:
                    con.execute("ROLLBACK")
                    return "already"
                row = con.execute("SELECT xp,correct,streak,last_day FROM arcade_progress WHERE username=?", (username,)).fetchone()
                streak = (row["streak"] + 1) if is_correct and row["last_day"] == (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat() else (1 if is_correct else 0)
                con.execute("INSERT INTO arcade_answers(username,day,answer,correct,xp_awarded) VALUES(?,?,?,?,?)",
                            (username, day, answer, is_correct, awarded))
                con.execute("UPDATE arcade_progress SET xp=xp+?, correct=correct+?, streak=?, last_day=?, pet_stage=?, updated_at=CURRENT_TIMESTAMP WHERE username=?",
                            (awarded, is_correct, streak, day, _pet_stage(row["xp"] + awarded), username))
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        finally:
            con.close()
    return "correct" if is_correct else "wrong"
