"""Hard rules that keep the system inside the user's existing memberships.

Every adapter run goes through here. The rules are code, not prompts, so no model output,
web page or skill file can switch them off.
"""

import os

from acc import config
from acc.adapters.base import AdapterError, AdapterInfo, Billing

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
    }
)


class CostBlocked(AdapterError):
    pass


def check_allowed(info: AdapterInfo) -> None:
    if info.billing == Billing.PAID_API and not config.ALLOW_PAID_API:
        raise CostBlocked(
            f"{info.name} ücretli API gerektiriyor. Ücretli kullanım kapalı; görev çalıştırılmadı."
        )


def sanitized_env() -> dict[str, str]:
    """Environment for spawned CLIs, with every billing-related key removed."""
    return {k: v for k, v in os.environ.items() if k not in BILLING_ENV_VARS}
