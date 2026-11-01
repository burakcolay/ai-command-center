# Mimari ve Kararlar

Bu belge, ana proje dokümanındaki vizyonun nasıl uygulandığını ve hangi kararların neden alındığını kaydeder. Yeni bir karar alındığında buraya eklenir.

## 1. Fizibilite ve maliyet

**Hedef:** Claude (~20 $) ve ChatGPT (~20 $) üyelikleri dışında hiçbir ücret oluşmaması.

| Bileşen | Maliyet | Not |
|---|---|---|
| Claude Code | Claude aboneliği | `claude -p` headless, claude.ai girişi ile |
| OpenAI Codex CLI | ChatGPT aboneliği | ChatGPT hesabıyla giriş destekleniyor |
| Ollama | Ücretsiz (yerel) | 16 GB RAM'de 7–8B, Q4 modeller |
| Grok Build | Koşullu | Ücretsiz erişim doğrulanmadan aktif edilmez |
| Kimi Code | Üyelik gerekli | İlk sürümde yok |
| DeepSeek | Ücretli API | Varsayılan kapalı, maliyet koruması engeller |
| FastAPI, SQLite, React, Playwright, gh, git, Obsidian, MCP | Ücretsiz | Açık kaynak veya ücretsiz araçlar |

**Gerçekçi sınırlar:**
- Asıl darboğaz **abonelik limitleri**dir. Claude Pro'nun 5 saatlik ve haftalık pencereleri var. Sistem bunları ölçer ve gösterir. Limit dolunca görev bekler; ücretli API'ye geçmez.
- Mac uykudayken görevler durur. Bulut veya 7/24 çalışma kapsam dışıdır.
- App Store Connect işlemleri için zaten Apple Developer üyeliği gerekir. Bu sistemin getirdiği bir maliyet değildir.

### Maliyet koruması (kodda uygulanır, prompt'a bırakılmaz)

1. `config.ALLOW_PAID_API = False` sabittir; ortam değişkeni veya arayüzle açılamaz.
2. Her adaptör bir `billing` türü bildirir. `paid_api` türündekiler `cost_guard.check_allowed` tarafından reddedilir.
3. Başlatılan CLI süreçlerine API anahtarı ortam değişkenleri **aktarılmaz** (`cost_guard.BILLING_ENV_VARS`). Böylece bir CLI sessizce API faturalamasına geçemez.
4. **Claude Code ön kontrolü:** `claude auth status --json` çıktısında `authMethod` abonelik türü ve `apiProvider == firstParty` olmalıdır. Bilinmeyen değerler varsayılan olarak engellenir.
5. **Çalışma sırasında:**
   - `system/init` içindeki `apiKeySource` değeri `none` değilse süreç durdurulur.
   - `rate_limit_event` içinde `isUsingOverage: true` (ücretli ekstra kullanım) görülürse süreç durdurulur.
6. Kullanıcıya düşen tek ayar: claude.ai ve ChatGPT hesap ayarlarında "extra usage / kredi" özelliklerini kapalı tutmak.

## 2. Teknoloji kararları

| Karar | Seçim | Gerekçe |
|---|---|---|
| Frontend | Vite + React + TS + Tailwind v4 + lucide | Localhost'ta SSR gereksiz. Tek port, daha az RAM. Next.js yerine seçildi. |
| UI bileşenleri | Elle yazılmış, az sayıda | shadcn/ui gerektiğinde bileşen bazında eklenecek. |
| Backend | FastAPI + SQLAlchemy 2 + SQLite (WAL) | Dokümandaki gibi. |
| Kuyruk | SQLite + asyncio | Redis/Celery gerekmez. |
| Orchestrator beyni | Claude Code (`--json-schema` ile yapılandırılmış plan) | 16 GB'da yerel modeller planlama için zayıf. |
| Karar mantığı | Deterministik Python | Durum geçişleri, izinler ve maliyet kuralları AI'ya bırakılmaz. |
| Ajanlar | Konfigürasyon (`server/acc/agents.py`) | Rol, araç listesi ve model tercihi. Ayrı süreç değil. |
| Arayüz dili | Türkçe | Kullanıcı tercihi. |
| Tasarım | Siyah-beyaz, nokta deseni, nokta-matris tipografi | Tek vurgu rengi beyaz; kırmızı yalnızca hatalar için. |

## 3. Güvenlik modeli

- Sunucu yalnızca `127.0.0.1` adresinde dinler. `Host` başlığı localhost olmayan istekler reddedilir (DNS rebinding koruması). WebSocket'te `Origin` kontrol edilir.
- **İzin kontrolü CLI seviyesinde yapılır.** Ajanın araç listesi `--tools` ve `--allowedTools` ile, izin modu `--permission-mode dontAsk` ile verilir. Örneğin Orchestrator yalnızca `Read`, `Glob` ve `Grep` kullanabilir.
- **Asıl kontrol noktası merge'dür** (sıradaki sürüm). Yazan ajanlar görev başına ayrı bir `git worktree` içinde çalışır. Diff, test ve kullanıcı onayı olmadan ana branch'e hiçbir şey girmez.
- Proje dosyaları, web sayfaları ve skill'ler güvenilmeyen veri sayılır. Planlayıcı sistem prompt'u bunu belirtir. Daha önemlisi, izinler zaten koddadır; prompt değiştirse bile araç listesi değişmez.
- Bir proje uygulamadan kaldırıldığında diskteki dosyalar silinmez.

## 4. Adaptör sözleşmesi

`server/acc/adapters/base.py` dosyasındaki `ModelAdapter`:

| Doküman | Uygulama |
|---|---|
| connect + authenticate + health_check | `health_check()`: giriş her zaman kullanıcı tarafından CLI'da yapılır; şifre işlenmez |
| get_capabilities | `.capabilities` |
| get_usage_status | `usage_status()`: kaynak `verified`, `estimated`, `user` veya `unknown` |
| execute_task + get_result | `run()`: async event akışı; son event `result` veya `error` |
| cancel_task | `cancel()` |

**Yeni sağlayıcı eklemek** için `adapters/` altına bir modül yazılır ve `build_registry()` içine bir satır eklenir. Orchestrator'a dokunulmaz.

### Claude Code: doğrulanmış davranış (CLI 2.1.x)

- `claude -p --output-format stream-json --verbose` komutu satır satır JSON üretir.
- `system/init.apiKeySource == "none"` abonelik kullanıldığını gösterir.
- `rate_limit_event.rate_limit_info.unifiedWindows.{five_hour,seven_day}.utilization` alanları **gerçek** limit kullanımını verir.
- `result.structured_output` alanı `--json-schema` ile doğrulanmış çıktıyı içerir.
- `result.total_cost_usd` abonelikte temsili bir değerdir; harcama olarak gösterilmez.

## 5. Veri modeli (SQLite)

`projects`, `chats`, `messages`, `tasks`, `task_events` (yalnızca ekleme yapılan günlük ve canlı akış), `approvals`, `audit_logs`.

Dokümandaki diğer tablolar (`model_usage`, `skill_registry`, `mcp_connections` …) ilgili faz geldiğinde eklenecek.

## 6. Görev yaşam döngüsü

```
planning ──► waiting_approval ──approve──► queued ──► running ──► completed
   │               │  └─request_changes──► planning        │
   │               └─reject──► cancelled                   └──► failed ──retry──► planning
   └──(hata)──► failed            her aktif durumdan ──cancel──► cancelled
```

Sunucu yeniden başlatıldığında `planning` veya `running` durumunda kalan görevler `failed` olarak işaretlenir ve "Tekrar dene" ile sürdürülebilir. Checkpoint/resume Faz 8'de gelecek.

## 7. Yol haritası durumu

- [x] **Faz 1 — Temel:** iskelet, SQLite, sohbet, projeler, loglar, WebSocket
- [x] **Adaptör arayüzü + Claude Code adaptörü + maliyet koruması**
- [x] **Orchestrator v0:** plan üretimi, onay, değişiklik talebi, red, iptal, tekrar deneme
- [ ] **Sıradaki — Yürütme motoru:** git worktree, Developer ajanı, canlı çıktı, diff ekranı, merge onayı
- [ ] Faz 2: Codex, Ollama ve Grok adaptörleri
- [ ] Faz 4–8: dokümandaki sırayla
