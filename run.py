import os
import uvicorn
from app.config import load

cfg = load()
port = int(os.getenv("PORT", cfg["web"]["port"]))

if __name__ == "__main__":
    # workers は必ず 1（複数にするとスケジューラが重複実行される）
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        limit_concurrency=int(os.getenv("LIMIT_CONCURRENCY", "200")),
        backlog=int(os.getenv("BACKLOG", "256")),
        timeout_keep_alive=int(os.getenv("KEEPALIVE", "20")),
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level=os.getenv("LOG_LEVEL", "info"),
    )