"""Robot arena catalog and safe XP persistence helpers."""
import sqlite3
from pathlib import Path
from threading import RLock
from . import arcade
_LOCK = RLock()
ROBOTS = [
 {"id":"scout","name":"SCOUT-01","price":0,"hp":700,"speed":5.5,"damage":75,"range":250,"fire_rate":0.55,"weapon":"Pulse repeater","ultimate":"Dash burst","color":"#58d7ff","desc":"軽量偵察機。移動と回避に優れる。","reload_time":0.72,"gadget":"ブーストダッシュ","gadget_type":"dash"},
 {"id":"bulwark","name":"BULWARK","price":120,"hp":1500,"speed":2.8,"damage":120,"range":190,"fire_rate":1.0,"weapon":"Twin cannons","ultimate":"Aegis wall","color":"#ffb454","desc":"装甲重視。前線を押し上げる。","reload_time":1.35,"gadget":"アーマーシールド","gadget_type":"shield"},
 {"id":"striker","name":"STRIKER-X","price":260,"hp":900,"speed":4.6,"damage":180,"range":310,"fire_rate":0.9,"weapon":"Rail lance","ultimate":"Piercing shot","color":"#ff5e79","desc":"高火力の精密射撃型。","reload_time":1.0,"gadget":"貫通チャージ","gadget_type":"pierce"},
 {"id":"mortar","name":"MORTAR-7","price":420,"hp":1100,"speed":3.1,"damage":230,"range":360,"fire_rate":1.5,"weapon":"Arc mortar","ultimate":"Cluster barrage","color":"#c39bff","desc":"曲射で遮蔽物の向こうを狙う。","reload_time":1.6,"gadget":"クラスター地雷","gadget_type":"mine"},
 {"id":"volt","name":"VOLT-R","price":650,"hp":850,"speed":5.0,"damage":100,"range":220,"fire_rate":0.35,"weapon":"Chain arc","ultimate":"EMP field","color":"#7dffbc","desc":"連射と妨害に特化。","reload_time":0.48,"gadget":"EMPパルス","gadget_type":"emp"},
 {"id":"siege","name":"SIEGE-09","price":900,"hp":1900,"speed":2.4,"damage":160,"range":280,"fire_rate":0.8,"weapon":"Siege cannon","ultimate":"Ground breaker","color":"#ff845d","desc":"重装甲と範囲攻撃。","reload_time":1.45,"gadget":"震撃ウェーブ","gadget_type":"shockwave"},
 {"id":"phantom","name":"PHANTOM","price":1250,"hp":780,"speed":5.8,"damage":145,"range":270,"fire_rate":0.65,"weapon":"Cloak blaster","ultimate":"Phase strike","color":"#79a5ff","desc":"高速機動と奇襲。","reload_time":0.82,"gadget":"フェイズクローク","gadget_type":"cloak"},
 {"id":"root_overlord","name":"Ω-ROOT OVERLORD","price":0,"hp":99999,"speed":6.5,"damage":9999,"range":600,"fire_rate":0.12,"weapon":"Omni arsenal","ultimate":"ROOT singularity","color":"#ffe76b","desc":"ルート管理者専用機。全ギミック解放。","root_only":True,"reload_time":0.22,"gadget":"オーバーロード","gadget_type":"overload"},
]
STAGES = ["溶鉱炉ヤード","氷結採掘場","ネオン遺跡","ダストキャニオン"]
def _db():
    Path(arcade.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con=sqlite3.connect(arcade.DB_PATH, timeout=10); con.row_factory=sqlite3.Row
    con.execute('CREATE TABLE IF NOT EXISTS robot_ownership(username TEXT NOT NULL, robot_id TEXT NOT NULL, PRIMARY KEY(username,robot_id))')
    con.execute('CREATE TABLE IF NOT EXISTS robot_loadout(username TEXT PRIMARY KEY, robot_id TEXT NOT NULL DEFAULT "scout")')
    con.commit(); return con
def is_root(username):
    import os
    root=os.getenv('ADMIN_USER','').strip()
    return bool(root and username.casefold()==root.casefold())
def state(username):
    with _LOCK:
        con=_db()
        try:
            con.execute('INSERT OR IGNORE INTO robot_ownership VALUES(?,?)',(username,'scout'))
            if is_root(username): con.execute('INSERT OR IGNORE INTO robot_ownership VALUES(?,?)',(username,'root_overlord'))
            con.execute('INSERT OR IGNORE INTO robot_loadout(username,robot_id) VALUES(?,"scout")',(username,)); con.commit()
            owned=[r[0] for r in con.execute('SELECT robot_id FROM robot_ownership WHERE username=?',(username,))]
            load=con.execute('SELECT robot_id FROM robot_loadout WHERE username=?',(username,)).fetchone()[0]
            if load not in owned: load='scout'
            return {'owned':owned,'loadout':load,'xp':arcade.get_progress(username)['xp'],'root':is_root(username)}
        finally: con.close()
def buy(username, robot_id):
    robot=next((r for r in ROBOTS if r['id']==robot_id),None)
    if not robot or (robot.get('root_only') and not is_root(username)): return False,'機体が見つからないか購入できません'
    with _LOCK:
        con=_db()
        try:
            if con.execute('SELECT 1 FROM robot_ownership WHERE username=? AND robot_id=?',(username,robot_id)).fetchone(): return False,'すでに所有しています'
            xp=arcade.get_progress(username)['xp']
            if xp < robot['price']: return False,'XPが足りません'
            con.execute('BEGIN IMMEDIATE')
            con.execute('UPDATE arcade_progress SET xp=xp-? WHERE username=?',(robot['price'],username))
            con.execute('INSERT INTO robot_ownership VALUES(?,?)',(username,robot_id)); con.commit()
            return True,robot['name']+' を購入しました'
        except Exception: con.rollback(); raise
        finally: con.close()
def equip(username, robot_id):
    with _LOCK:
        con=_db()
        try:
            if robot_id=='root_overlord' and not is_root(username): return False
            if not con.execute('SELECT 1 FROM robot_ownership WHERE username=? AND robot_id=?',(username,robot_id)).fetchone(): return False
            con.execute('INSERT INTO robot_loadout(username,robot_id) VALUES(?,?) ON CONFLICT(username) DO UPDATE SET robot_id=excluded.robot_id',(username,robot_id)); con.commit(); return True
        finally: con.close()
def award_match(username, xp):
    # Called only after server-validated match completion; hard cap per match prevents client spoofing.
    xp=max(0,min(int(xp),25))
    with _LOCK:
        con=_db()
        try:
            con.execute('UPDATE arcade_progress SET xp=xp+?, updated_at=CURRENT_TIMESTAMP WHERE username=?',(xp,username)); con.commit()
        finally: con.close()
    return xp
