import subprocess
import sys


def test_app_imports_cleanly_in_a_fresh_process():
    """The test session imports modules in its own order; a real start must work too
    (catches circular imports that only show up when the server is launched)."""
    r = subprocess.run(
        [sys.executable, "-c", "import acc.main"], capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, r.stderr[-2000:]
