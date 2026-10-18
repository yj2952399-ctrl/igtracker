import uvicorn
from app.config import load

cfg = load()
uvicorn.run("app.main:app", host=cfg["web"]["host"], port=cfg["web"]["port"], workers=1)