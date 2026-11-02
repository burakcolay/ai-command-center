import subprocess
import sys


def test_app_imports_cleanly_in_a_fresh_process():
    """The test session imports modules in its own order; a real start must work too
    (catches circular imports that only show up when the server is launched)."""
    r = subprocess.run(
        [sys.executable, "-c", "import acc.main"], capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, r.stderr[-2000:]


def test_port_check_sees_real_listeners_only():
    import socket

    from acc.main import _port_free

    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # as uvicorn does
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert not _port_free("127.0.0.1", port)
        # A connection that was open when the server stopped leaves TIME_WAIT behind.
        client = socket.create_connection(("127.0.0.1", port))
        conn, _ = listener.accept()
        conn.close()
        client.close()
    assert _port_free("127.0.0.1", port)  # a quick restart is not "port busy"
