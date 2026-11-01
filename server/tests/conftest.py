import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="acc-test-")
os.environ["ACC_DATA_DIR"] = os.path.join(_tmp, "data")
os.environ["ACC_WORKSPACE_DIR"] = os.path.join(_tmp, "workspace")
# Use a preinstalled Chromium if the machine has one outside Playwright's default location.
_chromium = sorted(__import__("glob").glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
if _chromium and "ACC_CHROMIUM" not in os.environ:
    os.environ["ACC_CHROMIUM"] = _chromium[-1]

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from acc.adapters import registry  # noqa: E402
from acc.adapters.mock import MockAdapter  # noqa: E402

# Tests never talk to a real CLI.
registry._adapters = {"mock": MockAdapter(delay=0.01)}
registry._health.clear()


@pytest.fixture
def client():
    from acc.main import app

    with TestClient(app, base_url="http://127.0.0.1:7420") as c:
        yield c
