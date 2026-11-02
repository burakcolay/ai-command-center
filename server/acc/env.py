"""Environment for every process Orbit starts. No dependencies: anything may import it."""

import os
import sys

# Env vars that would silently switch a CLI from subscription login to per-token billing.
BILLING_ENV_VARS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
        "AWS_BEARER_TOKEN_BEDROCK",
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "XAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "MOONSHOT_API_KEY",
        "KIMI_API_KEY",
        # Google: an API key or Vertex/Cloud credentials would bill per token instead of
        # using the Google account (AI Plus/Pro) the Antigravity CLI is signed in with.
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_APPLICATION_CREDENTIALS",
    }
)


def _own_venv_bins() -> set[str]:
    """Orbit's own virtualenv. Child processes must not pick up its python and packages."""
    dirs = set()
    if venv := os.environ.get("VIRTUAL_ENV"):
        dirs.add(os.path.join(venv, "bin"))
    if sys.prefix != sys.base_prefix:
        dirs.add(os.path.join(sys.prefix, "bin"))
    return {os.path.realpath(d) for d in dirs}


def sanitized_env() -> dict[str, str]:
    """Environment for spawned processes: no billing keys, and none of Orbit's own Python
    environment (an agent's `python` must be the project's, not Orbit's)."""
    env = {k: v for k, v in os.environ.items() if k not in BILLING_ENV_VARS}
    env.pop("VIRTUAL_ENV", None)
    own = _own_venv_bins()
    path = env.get("PATH", "").split(os.pathsep)
    env["PATH"] = os.pathsep.join(p for p in path if p and os.path.realpath(p) not in own)
    return env
