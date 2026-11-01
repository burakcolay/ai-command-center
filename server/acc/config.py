import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("ACC_DATA_DIR", ROOT / "data"))
WORKSPACE_DIR = Path(os.environ.get("ACC_WORKSPACE_DIR", ROOT / "workspace" / "projects"))
WEB_DIST = ROOT / "web" / "dist"

# Only ever bind to loopback. Remote access is out of scope by design.
HOST = "127.0.0.1"
PORT = int(os.environ.get("ACC_PORT", "7420"))

# Demo adapter: fake responses for trying the UI without any CLI login.
DEMO_MODE = os.environ.get("ACC_DEMO") == "1"

# Paid API usage is hard-disabled. Intentionally not read from env or settings:
# turning it on must be a deliberate code change, never a toggle an agent can flip.
ALLOW_PAID_API = False
