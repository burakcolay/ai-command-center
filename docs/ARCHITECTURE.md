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
- **Asıl kontrol noktası merge'dür.** Her görev `data/worktrees/task-N` altında, `orbit/task-N` branch'inde ayrı bir git worktree'de çalışır. Kullanıcının çalışma klasörüne yalnızca onaylanan bir birleştirme dokunur.
- **Bash kullanan ajanlar** (Geliştirici, QA) Claude Code'un işletim sistemi seviyesindeki sandbox'ında çalışır (`agents.SANDBOX_SETTINGS`):
  - Yalnızca worktree'ye yazabilirler.
  - `~/.ssh`, `~/.aws`, `~/.config/gh` gibi kimlik bilgisi klasörlerini okuyamazlar.
  - Ağ erişimleri yalnızca paket kayıtlarıyla (npm, PyPI) sınırlıdır.
  - `failIfUnavailable: true`: sandbox başlayamazsa komut hiç çalışmaz. Bu hem kapalı hem açık durumda test edildi.
- **Salt okunur ajanlar** (QA, İnceleme, Araştırma, Mimar) dosya değiştirirse Orbit bu değişiklikleri adım sonunda otomatik geri alır ve günlüğe yazar.
- **Git işlemlerini her zaman Orbit yapar.** Ajanlar commit, merge veya push yapmaz. Derleme ve test çöpleri (`__pycache__`, `node_modules`, `.pytest_cache` …) proje `.gitignore`'u olmasa bile commit'lere girmez.
- **Repodaki `.claude/settings.json` güvenilmez veridir.** Claude Code `--setting-sources user` ile başlatılır; böylece bir repo kendi hook'larıyla komut çalıştıramaz.
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

`projects`, `chats`, `messages`, `tasks`, `task_steps` (yürütme adımları ve özetleri), `task_events` (yalnızca ekleme yapılan günlük ve canlı akış), `approvals`, `audit_logs`.

**Şema geçişi:** `db._add_missing_columns` yalnızca ekleme yapar; yeni sütunları mevcut veritabanına `ALTER TABLE ADD COLUMN` ile ekler. Eski veritabanları sürüm güncellemelerinde bozulmaz.

Dokümandaki diğer tablolar (`model_usage`, `skill_registry`, `mcp_connections` …) ilgili faz geldiğinde eklenecek.

## 6. Görev yaşam döngüsü

Görevin bir `stage` alanı (plan → execute → merge → done) ve bir `status` alanı vardır:

```
[plan]    planning ──► waiting_approval ──approve──► queued
                         ├─request_changes──► planning (yeniden plan)
                         └─reject──► cancelled
[execute] queued ──► running ──(adım adım, her adım bir commit)──► waiting_approval [merge]
                       └──(hata)──► failed ──retry──► kaldığı adımdan devam
[merge]   waiting_approval ──approve──► git merge --no-ff ──► completed (worktree + branch silinir)
                         ├─request_changes──► "Geri bildirimi uygula" adımı eklenir ──► queued
                         └─reject──► cancelled (worktree + branch silinir)
Her aktif durumdan cancel ──► cancelled
```

- **Birleştirme güvenliği:** Birleştirme yalnızca görevin başladığı branch açıkken yapılır. Çakışma olursa `merge --abort` ile geri alınır ve onay beklemede kalır.
- **Kaldığı yerden devam:** Her adım ayrı bir commit olduğu için checkpoint görevi görür. Sunucu yeniden başlarsa kuyruktaki görevler devam eder; yarıda kalanlar "Kaldığı yerden devam et" ile tamamlanmamış adımdan sürdürülür.
- **Eşzamanlılık:** Aynı anda en fazla `MAX_PARALLEL_TASKS = 1` görev yürütülür. Bu, RAM ve abonelik kotası için bilinçli bir seçim.

## 7. Yol haritası durumu

- [x] **Faz 1 — Temel:** iskelet, SQLite, sohbet, projeler, loglar, WebSocket
- [x] **Adaptör arayüzü + Claude Code adaptörü + maliyet koruması**
- [x] **Orchestrator v0:** plan üretimi, onay, değişiklik talebi, red, iptal, tekrar deneme
- [x] **Yürütme motoru:** git worktree, adım adım ajanlar, sandbox, diff ekranı, değişiklik isteme, birleştirme onayı, kaldığı yerden devam
- [ ] **Sıradaki — Faz 2:** Codex ve Ollama adaptörleri (Claude kotasını rahatlatmak için), ardından Grok
- [ ] Faz 4–8: dokümandaki sırayla
