"""iOS preview against stand-ins for xcodebuild and xcrun (no Mac here): what Orbit runs, in
which order, with which safety, and that it always leaves the simulator as it found it."""

import json
import plistlib
import sys
import time
from pathlib import Path

import pytest

from acc import checks, ios_preview, preview, sessions
from tests.helpers import git, new_chat, project, task, turn

needs_sandbox = pytest.mark.skipif(not checks.sandbox_available(), reason="srt yok")

FAKE_XCODEBUILD = r"""#!{python}
import json, os, plistlib, sys
args = sys.argv[1:]
derived = args[args.index("-derivedDataPath") + 1]
scheme = args[args.index("-scheme") + 1]
os.makedirs(derived, exist_ok=True)
with open(os.path.join(derived, "fake-xcodebuild.json"), "w") as f:
    json.dump({{"args": args, "home": os.environ.get("HOME"),
               "cf_home": os.environ.get("CFFIXED_USER_HOME")}}, f)
if os.environ.get("FAKE_XC_FAIL"):
    print("error: Signing for 'App' requires a development team.")
    sys.exit(65)
app = os.path.join(derived, "Build", "Products", "Debug-iphonesimulator", scheme + ".app")
os.makedirs(app, exist_ok=True)
with open(os.path.join(app, "Info.plist"), "wb") as f:
    plistlib.dump({{"CFBundleIdentifier": "com.orbit." + scheme.lower()}}, f,
                  fmt=plistlib.FMT_BINARY)
print("** BUILD SUCCEEDED **")
"""

FAKE_XCRUN = r"""#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_XCRUN_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
if args[:2] != ["simctl", "list"] and args[0] != "simctl":
    sys.exit(2)
cmd = args[1]
if cmd == "list":
    booted = "Booted" if os.environ.get("FAKE_BOOTED") else "Shutdown"
    print(json.dumps({{"devices": {{
        "com.apple.CoreSimulator.SimRuntime.iOS-17-5": [
            {{"udid": "OLD", "name": "iPhone 15", "state": booted, "isAvailable": True}}],
        "com.apple.CoreSimulator.SimRuntime.iOS-18-2": [
            {{"udid": "IPAD", "name": "iPad Pro", "state": "Shutdown", "isAvailable": True}},
            {{"udid": "NEW", "name": "iPhone 16 Pro", "state": "Shutdown", "isAvailable": True}}],
        "com.apple.CoreSimulator.SimRuntime.watchOS-11-2": [
            {{"udid": "W", "name": "Apple Watch", "state": "Shutdown", "isAvailable": True}}],
    }}}}))
elif cmd == "launch" and os.environ.get("FAKE_LAUNCH_FAIL"):
    print("An error was encountered processing the command (code=4): app crashed")
    sys.exit(4)
elif cmd == "io":
    with open(args[-1], "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
"""


@pytest.fixture
def xcode(tmp_path, monkeypatch):
    bins = tmp_path / "bin"
    bins.mkdir()
    for name, body in (("xcodebuild", FAKE_XCODEBUILD), ("xcrun", FAKE_XCRUN)):
        f = bins / name
        f.write_text(body.format(python=sys.executable))
        f.chmod(0o755)
    log = tmp_path / "xcrun.jsonl"
    monkeypatch.setenv("ACC_XCODEBUILD", str(bins / "xcodebuild"))
    monkeypatch.setenv("ACC_XCRUN", str(bins / "xcrun"))
    monkeypatch.setenv("FAKE_XCRUN_LOG", str(log))
    monkeypatch.setattr(ios_preview, "LAUNCH_WAIT_S", 0)
    return log


def _calls(log: Path) -> list[list[str]]:
    return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


def _ios_project(client):
    p = project(client)
    root = Path(p["path"])
    schemes = root / "Sayac.xcodeproj" / "xcshareddata" / "xcschemes"
    schemes.mkdir(parents=True)
    (root / "Sayac.xcodeproj" / "project.pbxproj").write_text("// !$*UTF8*$!\n")
    (schemes / "Sayac.xcscheme").write_text("<Scheme/>")
    (schemes / "SayacWidget.xcscheme").write_text("<Scheme/>")
    git(p["path"], "add", "-A")
    git(p["path"], "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "ios")
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Bir satır ekle", p["id"])["meta"]["task_id"]
    return chat_id, task_id


def _wait(client, chat_id, task_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = task(client, chat_id, task_id)["preview"]
        if got and got["status"] != "running":
            return got
        time.sleep(0.2)
    raise AssertionError("önizleme bitmedi")


# ---------- pieces ----------


def test_the_project_scheme_and_device_are_found(tmp_path):
    assert ios_preview.find(tmp_path) is None
    (tmp_path / "ios" / "App.xcodeproj").mkdir(parents=True)  # React Native / Expo layout
    assert ios_preview.find(tmp_path) == {"flag": "-project", "path": "ios/App.xcodeproj"}
    (tmp_path / "ios" / "App.xcworkspace").mkdir()  # CocoaPods: the workspace is what builds
    assert ios_preview.find(tmp_path)["flag"] == "-workspace"
    found = ios_preview.find(tmp_path)
    assert ios_preview.scheme(tmp_path, found) == "App"  # no shared scheme: the project name

    listing = {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-17-5": [
                {"udid": "A", "name": "iPhone 15", "state": "Shutdown"}
            ],
            "com.apple.CoreSimulator.SimRuntime.iOS-18-2": [
                {"udid": "B", "name": "iPhone 16", "state": "Shutdown"},
                {"udid": "C", "name": "iPad Air", "state": "Booted"},
            ],
        }
    }
    assert ios_preview.pick_device(listing)["udid"] == "B"  # newest iOS, iPhones only
    listing["devices"]["com.apple.CoreSimulator.SimRuntime.iOS-17-5"][0]["state"] = "Booted"
    assert ios_preview.pick_device(listing)["udid"] == "A"  # one already running is reused
    assert ios_preview.pick_device({"devices": {}}) is None


def test_the_build_never_signs_and_stays_in_the_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("ACC_XCODEBUILD", "/x/xcodebuild")
    cmd = ios_preview.build_command(
        tmp_path, {"flag": "-project", "path": "My App.xcodeproj"}, "My App"
    )
    assert "-project 'My App.xcodeproj' -scheme 'My App'" in cmd
    assert "CODE_SIGNING_ALLOWED=NO" in cmd and "-sdk iphonesimulator" in cmd
    assert f"-derivedDataPath {ios_preview.BUILD_DIR}" in cmd
    app = tmp_path / "X.app"
    app.mkdir()
    with (app / "Info.plist").open("wb") as f:
        plistlib.dump({"CFBundleIdentifier": "com.x"}, f, fmt=plistlib.FMT_BINARY)
    assert ios_preview.bundle_id(app) == "com.x"
    assert ios_preview.bundle_id(tmp_path) is None


def test_without_xcode_it_says_so(client, monkeypatch):
    monkeypatch.delenv("ACC_XCRUN", raising=False)
    monkeypatch.delenv("ACC_XCODEBUILD", raising=False)
    chat_id, task_id = _ios_project(client)
    r = client.post(f"/api/tasks/{task_id}/preview")  # nothing to confirm: it won't run
    assert r.status_code == 202
    got = _wait(client, chat_id, task_id)
    assert got["status"] == "unsupported" and "Xcode" in got["reason"]


# ---------- the whole run ----------


@needs_sandbox
def test_ios_preview_asks_first_then_builds_sandboxed_and_cleans_up(client, xcode):
    chat_id, task_id = _ios_project(client)
    r = client.post(f"/api/tasks/{task_id}/preview")
    assert r.status_code == 428 and "Simülatör" in r.json()["detail"]
    assert not _calls(xcode)  # nothing ran before the user agreed

    r = client.post(f"/api/tasks/{task_id}/preview", json={"allow_device": True})
    assert r.status_code == 202
    got = _wait(client, chat_id, task_id)
    assert got["status"] == "ok" and got["kind"] == "ios" and got["sandboxed"] is True
    assert got["device"] == "iPhone 16 Pro · iOS 18.2"
    assert client.get(got["images"]["ios"]).status_code == 200

    steps = [c[1] for c in _calls(xcode)]
    assert steps == [
        "list",
        "bootstatus",
        "install",
        "launch",
        "status_bar",
        "io",
        "terminate",
        "uninstall",
        "shutdown",  # Orbit booted it, so Orbit shuts it down
    ]
    install = next(c for c in _calls(xcode) if c[1] == "install")
    assert install[2] == "NEW" and install[3].endswith("Sayac.app")
    assert next(c for c in _calls(xcode) if c[1] == "launch")[-1] == "com.orbit.sayac"

    wt = sessions.worktree_path(chat_id)
    built = json.loads((wt / ios_preview.BUILD_DIR / "fake-xcodebuild.json").read_text())
    assert built["home"].startswith(str(wt)) and built["cf_home"] == built["home"]
    assert "Sayac" in built["args"]  # the shared scheme named like the project
    files = [f["path"] for f in client.get(f"/api/tasks/{task_id}/diff").json()["files"]]
    assert files == ["ORBIT_DEMO.md"]  # the build never joins the change


@needs_sandbox
def test_a_running_simulator_is_left_running(client, xcode, monkeypatch):
    monkeypatch.setenv("FAKE_BOOTED", "1")
    chat_id, task_id = _ios_project(client)
    client.post(f"/api/tasks/{task_id}/preview", json={"allow_device": True})
    assert _wait(client, chat_id, task_id)["status"] == "ok"
    steps = [c[1] for c in _calls(xcode)]
    assert "shutdown" not in steps and steps[-1] == "uninstall"
    assert next(c for c in _calls(xcode) if c[1] == "install")[2] == "OLD"


@needs_sandbox
def test_a_crashing_app_is_reported_and_still_cleaned_up(client, xcode, monkeypatch):
    monkeypatch.setenv("FAKE_LAUNCH_FAIL", "1")
    chat_id, task_id = _ios_project(client)
    client.post(f"/api/tasks/{task_id}/preview", json={"allow_device": True})
    got = _wait(client, chat_id, task_id)
    assert got["status"] == "error" and "launch" in got["reason"]
    assert [c[1] for c in _calls(xcode)][-3:] == ["terminate", "uninstall", "shutdown"]


@needs_sandbox
def test_building_outside_the_sandbox_needs_its_own_yes(client, xcode, monkeypatch):
    monkeypatch.setenv("FAKE_XC_FAIL", "1")
    chat_id, task_id = _ios_project(client)
    client.post(f"/api/tasks/{task_id}/preview", json={"allow_device": True})
    got = _wait(client, chat_id, task_id)
    assert got["status"] == "build_failed" and got["sandboxed"] is True
    assert "korumasız" in got["confirm"] and "development team" in got["output"]
    assert "ÖNİZLEME DERLEMESİ BAŞARISIZ" in sessions.preview_block(task_id)

    # "unsandboxed" alone is not enough: the Simulator still needs its yes.
    r = client.post(f"/api/tasks/{task_id}/preview", json={"unsandboxed": True})
    assert r.status_code == 428

    monkeypatch.delenv("FAKE_XC_FAIL")
    r = client.post(
        f"/api/tasks/{task_id}/preview", json={"allow_device": True, "unsandboxed": True}
    )
    assert r.status_code == 202
    got = _wait(client, chat_id, task_id)
    assert got["status"] == "ok" and got["sandboxed"] is False
    events = client.get(f"/api/tasks/{task_id}/events").json()
    assert any("sandbox dışında" in (e["data"].get("text") or "") for e in events)


def test_web_projects_never_ask(client, tmp_path):
    p = project(client)
    (Path(p["path"]) / "index.html").write_text("<p>x</p>")
    assert preview.kind(Path(p["path"])) == "web"
    assert preview.kind(tmp_path) is None
