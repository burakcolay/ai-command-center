"""Demo adapter: deterministic fake output so the UI can be tried without any login.

Enabled only with ACC_DEMO=1. Everything it produces is labelled as demo in the UI.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from acc.adapters.base import (
    AdapterError,
    AdapterEvent,
    AdapterInfo,
    Billing,
    Capabilities,
    Health,
    ModelAdapter,
    ModelState,
    RunRequest,
)


class MockAdapter(ModelAdapter):
    info = AdapterInfo(
        id="mock",
        name="Demo Adaptörü",
        provider="Yerel (sahte)",
        billing=Billing.LOCAL_FREE,
        auth_method="yok",
        requires_membership=False,
        requires_api_key=False,
        notes="Arayüzü denemek için sahte yanıtlar üretir. Gerçek iş yapmaz.",
    )
    capabilities = Capabilities(planning=True, headless=True, structured_output=True)

    def __init__(self, delay: float = 0.4) -> None:
        self.delay = delay
        self._cancelled: set[str] = set()

    async def health_check(self) -> Health:
        return Health(ModelState.AVAILABLE, "Demo modu aktif.")

    async def run(self, req: RunRequest, run_id: str) -> AsyncIterator[AdapterEvent]:
        if req.stream_text:  # conversation
            reply = (
                "Demo yanıtı: mesajını aldım. Gerçek yanıtlar için Claude Code'a giriş yap.\n\n"
                "- Fikri birlikte netleştirebiliriz\n- Hazır olunca **Göreve dönüştür**"
            )
            for i in range(0, len(reply), 24):
                if run_id in self._cancelled:
                    raise AdapterError("Çalıştırma iptal edildi.")
                yield AdapterEvent("delta", {"text": reply[i : i + 24]})
                await asyncio.sleep(self.delay / 10)
            yield AdapterEvent("result", {"text": reply})
            return
        if req.json_schema is None:  # an execution step, not planning
            async for ev in self._step(req, run_id):
                yield ev
            return
        yield AdapterEvent("log", {"text": "Demo: istek analiz ediliyor"})
        await asyncio.sleep(self.delay)
        if run_id in self._cancelled:
            raise AdapterError("Çalıştırma iptal edildi.")
        yield AdapterEvent("tool", {"name": "Glob", "input": {"pattern": "**/*"}})
        await asyncio.sleep(self.delay)
        request = req.prompt.split("KULLANICI İSTEĞİ:", 1)[-1].strip().splitlines()[0][:80]
        plan = {
            "title": request or "Demo görevi",
            "summary": f"Demo planı: “{request}” isteği üç adıma bölündü.",
            "steps": [
                {
                    "id": "s1",
                    "title": "Proje yapısını incele",
                    "agent": "research",
                    "description": "Dosya yapısı ve bağımlılıklar taranır.",
                    "depends_on": [],
                    "writes_files": False,
                },
                {
                    "id": "s2",
                    "title": "Değişiklikleri uygula",
                    "agent": "developer",
                    "description": "Onaydan sonra izole worktree içinde kod değiştirilir.",
                    "depends_on": ["s1"],
                    "writes_files": True,
                },
                {
                    "id": "s3",
                    "title": "Test ve inceleme",
                    "agent": "qa",
                    "description": "Lint ve testler çalıştırılır, sonuç raporlanır.",
                    "depends_on": ["s2"],
                    "writes_files": False,
                },
            ],
            "risks": ["Bu bir demo planıdır; gerçek analiz yapılmadı."],
        }
        yield AdapterEvent("result", {"text": plan["summary"], "structured": plan})

    async def _step(self, req: RunRequest, run_id: str) -> AsyncIterator[AdapterEvent]:
        await asyncio.sleep(self.delay)
        if run_id in self._cancelled:
            raise AdapterError("Çalıştırma iptal edildi.")
        if req.cwd and "Write" in (req.tools or []):
            f = req.cwd / "ORBIT_DEMO.md"
            existing = f.read_text() if f.exists() else "# Orbit demo\n\n"
            f.write_text(existing + "Demo adaptörünün yazdığı satır.\n")
            yield AdapterEvent("tool", {"name": "Write", "input": {"file_path": "ORBIT_DEMO.md"}})
            yield AdapterEvent("result", {"text": "Demo: ORBIT_DEMO.md güncellendi."})
        else:
            yield AdapterEvent("tool", {"name": "Grep", "input": {"pattern": "TODO"}})
            yield AdapterEvent("result", {"text": "Demo: inceleme tamamlandı, sorun yok."})

    async def cancel(self, run_id: str) -> None:
        self._cancelled.add(run_id)
