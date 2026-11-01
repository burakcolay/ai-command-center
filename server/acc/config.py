import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("ACC_DATA_DIR", ROOT / "data"))
WORKSPACE_DIR = Path(os.environ.get("ACC_WORKSPACE_DIR", ROOT / "workspace" / "projects"))
WEB_DIST = ROOT / "web" / "dist"

# Only ever bind to loopback. Remote access is out of scope by design.
HOST = "127.0.0.1"
PORT = int(os.environ.get("ACC_PORT", "7420"))

# Project memory: one markdown file per project. Point this at a folder inside an
# Obsidian vault to see and link the notes there (plain files, no plugin needed).
MEMORY_DIR = Path(os.environ.get("ACC_MEMORY_DIR", DATA_DIR / "memory")).expanduser()

# Local models via Ollama.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

# Isolated per-task git worktrees live here, never inside the user's project.
WORKTREES_DIR = DATA_DIR / "worktrees"

# sandbox-runtime (srt) runs quality-gate commands; installed by `make setup` into tools/.
SRT_BIN = Path(os.environ.get("ACC_SRT_BIN", ROOT / "tools" / "node_modules" / ".bin" / "srt"))
CHECK_TIMEOUT_S = 600

# How many tasks may execute at once. 1 keeps RAM and subscription quota predictable.
MAX_PARALLEL_TASKS = 1

# Demo adapter: fake responses for trying the UI without any CLI login.
DEMO_MODE = os.environ.get("ACC_DEMO") == "1"

# Paid API usage is hard-disabled. Intentionally not read from env or settings:
# turning it on must be a deliberate code change, never a toggle an agent can flip.
ALLOW_PAID_API = False
