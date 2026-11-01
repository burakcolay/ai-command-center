# Orbit — AI Komuta Merkezi

Kişisel, local-first AI ajan orkestrasyon ortamı. Adı çalışma şeklinden geliyor: uzman ajanlar merkezdeki Orchestrator'ın yörüngesinde çalışır. Doğal dille görev verirsiniz; Orchestrator bir plan çıkarır, siz onaylarsınız, ajanlar kontrollü şekilde çalışır.

**Maliyet ilkesi:** Mevcut Claude ve ChatGPT abonelikleri dışında hiçbir ücret oluşmaz. Ücretli API kullanımı kod seviyesinde kapalıdır. Ayrıntılar için [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) belgesine bakın.

## Gereksinimler (macOS)

```bash
brew install uv node git
```

Claude Code'a abonelik hesabınızla giriş yapın (API anahtarı ile değil):

```bash
claude auth login
```

## Kurulum

```bash
make setup
```

## Çalıştırma

```bash
make start
```

Ardından tarayıcıda http://127.0.0.1:7420 adresini açın.

Port 7420 doluysa başka bir port seçin (örnek: `make start PORT=7500`). Sunucu her zaman yalnızca `127.0.0.1` üzerinde dinler; dışarıdan erişilemez.

- `make dev`: geliştirme modu (Vite hot-reload: http://127.0.0.1:5173)
- `make demo`: Claude Code olmadan, sahte planlarla arayüzü deneme
- `make test`: backend testleri ve frontend typecheck

## Nasıl kullanılır

1. **Sohbet modunda konuşun.** Fikrinizi anlatın, soru sorun, seçenekleri tartışın. Proje seçtiyseniz asistan kodunuzu okuyarak konuşur. Bu modda hiçbir dosya değişmez.
2. **Karar netleşince "Göreve dönüştür"e basın.** Orchestrator tüm konuşmayı okuyup bir plan çıkarır. Planı onaylar, değiştirtir ya da reddedersiniz.
3. **Ajanlar izole bir kopyada çalışır.** Bitince diff'i inceler, **Birleştir**, **Değişiklik iste** veya **Reddet** seçersiniz.

Kısa ve net işler için doğrudan **Görev** moduna geçip yazabilirsiniz. İyi bir görev tarifi şunları içerir:
- ne istendiği,
- kapsamın sınırı (ne yapılmayacağı),
- "bitti" sayılma ölçütü, örneğin "testler geçsin".

## Önemli

- claude.ai ve ChatGPT hesap ayarlarında **extra usage / ek kredi** özelliklerini kapalı tutun. Sistem ücretli aşım kullanımını algılarsa çalışmayı durdurur; yine de bu ayarı kapalı tutmak en güvenli yoldur.
- Veriler `data/acc.db` dosyasında, yeni projeler `workspace/projects/` altında tutulur. İkisi de git dışındadır.

## Yapı

```
server/acc/       FastAPI backend
  adapters/       Model sağlayıcıları (her biri ayrı modül)
  orchestrator.py Plan üretimi ve onay durum makinesi
  cost_guard.py   Ücretli kullanım engelleri
  agents.py       Uzman ajan tanımları
web/src/          React arayüzü
docs/             Mimari kararlar
```
