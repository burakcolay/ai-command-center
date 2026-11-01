"""Hard rules that keep the system inside the user's existing memberships.

Every adapter run goes through here. The rules are code, not prompts, so no model output,
web page or skill file can switch them off.
"""

from acc import config
from acc.adapters.base import AdapterError, AdapterInfo, Billing
from acc.env import BILLING_ENV_VARS, sanitized_env  # noqa: F401  (re-exported)


class CostBlocked(AdapterError):
    pass


def check_allowed(info: AdapterInfo) -> None:
    if info.billing == Billing.PAID_API and not config.ALLOW_PAID_API:
        raise CostBlocked(
            f"{info.name} ücretli API gerektiriyor. Ücretli kullanım kapalı; görev çalıştırılmadı."
        )
