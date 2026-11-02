"""Demo adapter: deterministic fake turns so the UI can be tried without any login.

Enabled only with ACC_DEMO=1 (and in tests). It reacts to words in the user's message the way
the real assistant reacts to intent: "tasarım" → writes design files, "rapor" → writes a
report, "değiştir"/"ekle"/"uygula" → edits ORBIT_DEMO.md in the project copy; otherwise it
just talks.
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

MARKER = "KULLANICININ MESAJI:"
EDIT_WORDS = ("değiştir", "ekle", "uygula", "düzelt")


def _message(prompt: str) -> str:
    return prompt.rsplit(MARKER, 1)[-1].strip()


def _screen(bg: str, fg: str, title: str) -> str:
    return (
        f"<!-- başlık: {title} | fikir: Demo: {title.lower()} yaklaşım. | görünüm: phone -->\n"
        f"<!doctype html><html><body style='margin:0;height:852px;background:{bg};color:{fg};"
        f"font:600 28px -apple-system,system-ui;display:grid;place-items:center'>{title}"
        "<script>document.body.style.background='red'</script></body></html>"
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
    capabilities = Capabilities(
        chat=True,
        tools=True,
        planning=True,
        coding=True,
        review=True,
        web_search=True,
        headless=True,
        structured_output=True,
    )

    def __init__(self, delay: float = 0.4) -> None:
        self.delay = delay
        self._cancelled: set[str] = set()

    async def health_check(self) -> Health:
        return Health(ModelState.AVAILABLE, "Demo modu aktif.")

    async def _say(self, text: str, run_id: str, stream: bool) -> AsyncIterator[AdapterEvent]:
        for i in range(0, len(text), 24):
            if run_id in self._cancelled:
                raise AdapterError("Çalıştırma iptal edildi.")
            if stream:
                yield AdapterEvent("delta", {"text": text[i : i + 24]})
            await asyncio.sleep(self.delay / 10)

    async def run(self, req: RunRequest, run_id: str) -> AsyncIterator[AdapterEvent]:
        if not req.tools:  # summaries and local-only chat
            text = "Demo özeti: konuşmada alınan kararlar burada özetlenir."
            async for ev in self._say(text, run_id, req.stream_text):
                yield ev
            yield AdapterEvent("result", {"text": text})
            return

        message = _message(req.prompt).lower()
        edit = any(w in message for w in EDIT_WORDS)
        parts = ["Demo yanıtı: mesajını aldım."]
        if "tasarım" in message and not edit and req.output_dir:
            screens = [
                ("#000", "#fff", "Sade"),
                ("#f4f4f4", "#111", "Kartlı"),
                ("#0b1f3a", "#e8eef7", "Yoğun"),
            ]
            for n, (bg, fg, title) in enumerate(screens, start=1):
                (req.output_dir / f"tasarim-{n}.html").write_text(_screen(bg, fg, title))
            yield AdapterEvent("tool", {"name": "Write", "input": {"file_path": "tasarim-1.html"}})
            parts.append("3 farklı tasarım çizdim.")
        if "rapor" in message and req.output_dir:
            (req.output_dir / "rapor-demo.md").write_text(
                "# Demo raporu\n\n**Kısa cevap:** demo.\n"
            )
            parts.append("Raporu kaydettim.")
        if edit and req.cwd and "Write" in req.tools:
            await asyncio.sleep(self.delay)
            if run_id in self._cancelled:
                raise AdapterError("Çalıştırma iptal edildi.")
            f = req.cwd / "ORBIT_DEMO.md"
            existing = f.read_text() if f.exists() else "# Orbit demo\n\n"
            f.write_text(existing + "Demo adaptörünün yazdığı satır.\n")
            yield AdapterEvent("tool", {"name": "Edit", "input": {"file_path": "ORBIT_DEMO.md"}})
            parts.append("ORBIT_DEMO.md dosyasını güncelledim.")
        text = " ".join(parts) + "\n\n- Demo modunda gerçek bir model çalışmaz."
        async for ev in self._say(text, run_id, req.stream_text):
            yield ev
        yield AdapterEvent("result", {"text": text})

    async def cancel(self, run_id: str) -> None:
        self._cancelled.add(run_id)
