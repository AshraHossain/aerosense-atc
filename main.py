import uvicorn
from api import app  # noqa: F401 — registers all routes
from core.config import HOST, PORT

if __name__ == "__main__":
    url = f"http://{'localhost' if HOST == '0.0.0.0' else HOST}:{PORT}"
    print(f"\n  AeroSense ATC — 12-Phase Multi-Agent ATC System")
    print(f"  Dashboard → {url}\n")
    uvicorn.run(app, host=HOST, port=PORT)
