import json
import stat

import pytest

from acc.adapters.base import AdapterInfo, Billing, ModelState
from acc.adapters.claude_code import ClaudeCodeAdapter
from acc.cost_guard import CostBlocked, check_allowed, sanitized_env


def _info(billing: Billing) -> AdapterInfo:
    return AdapterInfo("x", "X", "p", billing, "-", False, billing == Billing.PAID_API)


def test_paid_api_is_blocked():
    with pytest.raises(CostBlocked):
        check_allowed(_info(Billing.PAID_API))
    for ok in (Billing.SUBSCRIPTION, Billing.LOCAL_FREE, Billing.FREE_TIER):
        check_allowed(_info(ok))


def test_billing_env_vars_removed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME_TEST_VAR", "kept")
    env = sanitized_env()
    assert "ANTHROPIC_API_KEY" not in env and "OPENAI_API_KEY" not in env
    assert env["HOME_TEST_VAR"] == "kept"


def test_api_key_session_aborts():
    a = ClaudeCodeAdapter()
    with pytest.raises(CostBlocked):
        a._translate({"type": "system", "subtype": "init", "apiKeySource": "ANTHROPIC_API_KEY"})
    assert a._translate({"type": "system", "subtype": "init", "apiKeySource": "none"})


def test_overage_aborts_and_usage_is_verified():
    a = ClaudeCodeAdapter()
    ok = {
        "type": "rate_limit_event",
        "rate_limit_info": {
            "isUsingOverage": False,
            "unifiedWindows": {
                "five_hour": {"utilization": 0.08, "resetsAt": 1, "status": "allowed"}
            },
        },
    }
    (ev,) = a._translate(ok)
    assert ev.kind == "usage"
    assert a._last_usage.source == "verified"
    assert a._last_usage.windows[0].utilization == 0.08
    with pytest.raises(CostBlocked):
        a._translate({"type": "rate_limit_event", "rate_limit_info": {"isUsingOverage": True}})


def test_structured_result_parsed():
    a = ClaudeCodeAdapter()
    (ev,) = a._translate(
        {"type": "result", "is_error": False, "result": "{}", "structured_output": {"a": 1}}
    )
    assert ev.kind == "result" and ev.data["structured"] == {"a": 1}


def _fake_cli(tmp_path, status: dict):
    script = tmp_path / "claude"
    script.write_text(f"#!/bin/sh\necho '{json.dumps(status)}'\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (
            {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"},
            ModelState.AVAILABLE,
        ),
        (
            {"loggedIn": True, "authMethod": "api_key", "apiProvider": "firstParty"},
            ModelState.PAID_ACCESS_REQUIRED,
        ),
        (
            {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "bedrock"},
            ModelState.PAID_ACCESS_REQUIRED,
        ),
        ({"loggedIn": False}, ModelState.AUTH_REQUIRED),
    ],
)
async def test_health_check_auth_methods(tmp_path, status, expected):
    a = ClaudeCodeAdapter(binary=_fake_cli(tmp_path, status))
    assert (await a.health_check()).state == expected
