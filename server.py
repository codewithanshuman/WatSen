"""Single-deployment entrypoint for WatSen on Vercel.

The API keeps its existing module layout under services/api. The built Vite
application is mounted last so every API route remains available while the
landing page and hash-routed workspace are served from the same origin.
"""

from pathlib import Path
import sys

from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
API_ROOT = ROOT / "services" / "api"
WEB_DIST = ROOT / "web" / "dist"

sys.path.insert(0, str(API_ROOT))

from app.main import app  # noqa: E402

if not WEB_DIST.exists():
    raise RuntimeError("web/dist is missing. Run the frontend production build before deployment.")

app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
