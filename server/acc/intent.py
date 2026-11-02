"""Is this message just talk, or real work? Decided without a model call (no tokens).

Measured on one short chat message through Claude Code (2.1.316): the full setup (Opus, all
tools, the team) wrote ~14k tokens; Sonnet without the team ~10k; Sonnet without tools ~6k.
Most of a short turn is fixed overhead (Claude Code's own instructions, tool and team
definitions), and Opus tokens weigh the most against the subscription limit. So plain talk
goes light: the middle model, low effort, read-only tools, no team. Anything that looks like
work — or an answer that green-lights work ("tamam", "devam") — gets the full plan; and the
light model itself can hand a turn back for the full plan when it was misjudged.
"""

from __future__ import annotations

import re

LIGHT_LIMIT = 600  # longer messages usually carry a spec or detailed request
ESCALATE = "[[ORBIT:TAM_GUC]]"

# Erring towards the full plan is safe; erring the other way costs one retry.
# Word-start stems that mean "do something" or green-light work, in Turkish and English.
# Nouns people talk about (proje, ekran, kod, dosya…) are deliberately absent: discussing them
# is talk, and the light turn can still read files. "uygula" excludes "uygulama" (an app).
_WORK = re.compile(
    r"\b(araştır|arastir|rapor|tasarla|tasarım|tasarim|çiz|ciz|ekle|değiştir|degistir|"
    r"düzelt|duzelt|uygula(?!ma)|oluştur|olustur|kur|yap|yaz|test|incele|analiz|"
    r"karşılaştır|karsilastir|planla|kart|aşama|asama|devam|başla|basla|tamam|onay|evet|"
    r"olur|ok|sil|kaldır|kaldir|güncelle|guncelle|hata|bug|birleştir|birlestir|commit|"
    r"deploy|refactor|implement|build|fix|readme|yükle|yukle|entegre|hazırla|hazirla|"
    r"çalıştır|calistir|hadi|haydi)",
    re.IGNORECASE,
)


def is_light(text: str, attachments: list[str] | None = None) -> bool:
    if attachments:
        return False
    stripped = text.strip()
    if not stripped or len(stripped) > LIGHT_LIMIT:
        return False
    return _WORK.search(stripped) is None


LIGHT_NOTE = (
    "HAFİF SOHBET TURU: Bu mesaj sohbet olarak değerlendirildi; bu turda dosya değiştiremez ve "
    "ekibe iş veremezsin. Kısa ve doğal cevap ver. Mesaj aslında gerçek bir iş istiyorsa (kod "
    "değişikliği, tasarım çizimi, kapsamlı araştırma, Proje Kartı, bir planı uygulama) cevabın "
    f"yalnızca şu satır olsun ve başka hiçbir şey yazma: {ESCALATE}\n\n"
)
