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
- Asıl darboğaz **abonelik limitleri**dir. Claude Pro'nun 5 saatlik ve haftalık pencereleri var. Sistem bunları ölçer ve gösterir. Limit dolunca yanıt bekler; ücretli API'ye geçmez.
- Mac uykudayken çalışma durur. Bulut veya 7/24 çalışma kapsam dışıdır.
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
| Asistan | Tek bir Claude Code oturumu (`assistant.py`, `chat.py`) | Kullanıcı mod seçmez; niyeti model anlar. 16 GB'da yerel modeller bu iş için zayıf. |
| Karar mantığı | Deterministik Python | İzinler, izole kopya, birleştirme ve maliyet kuralları AI'ya bırakılmaz. |
| Arayüz dili | Türkçe | Kullanıcı tercihi. |
| Tasarım | Siyah-beyaz, nokta deseni, nokta-matris tipografi | Tek vurgu rengi beyaz; kırmızı yalnızca hatalar için. |

## 3. Güvenlik modeli

- Sunucu yalnızca `127.0.0.1` adresinde dinler. `Host` başlığı localhost olmayan istekler reddedilir (DNS rebinding koruması). WebSocket'te `Origin` kontrol edilir.
- **İzin kontrolü CLI seviyesinde yapılır.** Araç listesi `--tools` ve `--allowedTools` ile, izin modu `--permission-mode dontAsk` ile verilir. Asistanın araçları nerede çalıştığına göre koddan gelir (`assistant.py`):
  - Proje seçili ve git deposuysa: okuma, yazma, Bash ve web, hepsi projenin izole kopyasında.
  - Proje git deposu değilse: yalnızca okuma ve web (salt okunur).
  - Proje yoksa: okuma, web ve sohbete özel bir çalışma klasörüne yazma; Bash yok.
- **Asıl kontrol noktası merge'dür.** Proje seçili her sohbet `data/worktrees/chat-N` altında, `orbit/task-M` branch'inde ayrı bir git worktree'de çalışır. Kullanıcının çalışma klasörüne yalnızca onaylanan bir birleştirme dokunur.
- **Bash** her zaman Claude Code'un işletim sistemi seviyesindeki sandbox'ında çalışır (`security.claude_sandbox_settings`):
  - Yalnızca worktree'ye yazabilir.
  - `~/.ssh`, `~/.aws`, `~/.config/gh` gibi kimlik bilgisi klasörlerini okuyamaz.
  - Ağ erişimi yalnızca paket kayıtlarıyla (npm, PyPI) sınırlıdır.
  - `failIfUnavailable: true`: sandbox başlayamazsa komut hiç çalışmaz. Bu hem kapalı hem açık durumda test edildi.
- **Git işlemlerini her zaman Orbit yapar.** Asistan commit, merge veya push yapmaz; her tur sonunda Orbit commit'ler. Derleme ve test çöpleri (`__pycache__`, `node_modules`, `.pytest_cache` …) proje `.gitignore`'u olmasa bile commit'lere girmez.
- **Repodaki `.claude/settings.json` güvenilmez veridir.** Claude Code `--setting-sources user` ile başlatılır; böylece bir repo kendi hook'larıyla komut çalıştıramaz.
- Proje dosyaları, görseller, web sayfaları ve skill'ler güvenilmeyen veri sayılır. Asistanın sistem prompt'u bunu belirtir. Daha önemlisi, izinler zaten koddadır; prompt değiştirse bile araç listesi değişmez.
- Bir proje uygulamadan kaldırıldığında diskteki dosyalar silinmez.
- **Gizli dosyalar** (`security.SECRET_FILE_GLOBS`): Her Claude çalıştırmasına `permissions.deny` olarak `Read(**/.env)`, `Read(**/*.p8)` gibi kurallar verilir. Claude Code bu kuralları sandbox içindeki shell komutlarına da uygular; doğrulandı: `cat .env` reddedildi, `.env.example` okunabiliyor.
- **Kimlik bilgisi klasörleri** (`security.CREDENTIAL_DIRS`) ve ORBIT'in kendi veritabanı sandbox'taki her komuttan gizlidir.
- **CSRF:** Tarayıcının `Origin` ya da `Sec-Fetch-Site: cross-site` başlığıyla işaretlediği yabancı istekler 403 alır.
- **Log maskeleme:** Değişiklik günlüğü, canlı araç etkinliği ve kontrol çıktıları kaydedilmeden ya da gösterilmeden önce `security.redact`'tan geçer.
- **Alt süreç ortamı:** Faturalama anahtarları ve ORBIT'in kendi Python sanal ortamı (`VIRTUAL_ENV`, `PATH` girdisi) alt süreçlere aktarılmaz. Böylece asistanın `python`'u projenin Python'u olur.

## 4. Model yönlendirici (`routing.py`)

**Üç iş türü vardır (`WORK_KINDS`):**
- `assistant`: kullanıcının her mesajı. Sıra: Claude Code → Codex. Araç, kod ve web yeteneği gerekir.
- `review`: değişikliklerin bağımsız incelemesi. Sıra: Codex → Claude Code; değişikliği yazan model `avoid` ile en sona itilir.
- `summarize`: uzun sohbet özetleri ve Claude kullanılamadığında yedek sohbet. Sıra: Ollama → Claude Code.

Sıralarda henüz kurulu olmayan adaptörler de (`codex`) yer alır. Adaptör kaydedildiği an devreye girer.

**Seçim kuralları (`Router.pick`):**
- Yetenek kontrolü yapılır; yerel model asla asistan olmaz.
- Maliyet koruması uygulanır.
- Model sağlıklı olmalıdır; cooldown durumundakiler atlanır.
- **Kota baskısı:** Doğrulanmış kullanımı %90'ı geçen modelin yerine, uygun alternatif varsa o seçilir.
- **Kullanıcı sabitlemesi:** `prefs.routing`. API, yeteneği olmayan bir modelin sabitlenmesini reddeder; yönlendirici de sabitlenmiş olsa bile yetenek kontrolünü uygular.
- Asistan için uygun model yoksa sohbeti `summarize` sırasındaki model (ör. Ollama) araçsız sürdürür ve bunu yanıtın başında söyler.

**Şeffaflık:** Mesajın `adapter_id`'si kaydedilir; Model Yöneticisi o an seçilen modeli ve nedenini gösterir.

## 4b. Adaptör sözleşmesi

`server/acc/adapters/base.py` dosyasındaki `ModelAdapter`:

| Doküman | Uygulama |
|---|---|
| connect + authenticate + health_check | `health_check()`: giriş her zaman kullanıcı tarafından CLI'da yapılır; şifre işlenmez |
| get_capabilities | `.capabilities` |
| get_usage_status | `usage_status()`: kaynak `verified`, `estimated`, `user` veya `unknown` |
| execute_task + get_result | `run()`: async event akışı; son event `result` veya `error` |
| cancel_task | `cancel()` |

**Yeni sağlayıcı eklemek** için `adapters/` altına bir modül yazılır ve `build_registry()` içine bir satır eklenir. Sohbet koduna dokunulmaz.

### Codex: doğrulanmış davranış (codex-cli 0.166)

- Bayraklar `--help` ile doğrulandı: `exec --json`, `-s read-only|workspace-write`, `-C`, `--add-dir`, `--output-schema`, `--ephemeral`, `--skip-git-repo-check`, `-c key=value`. `forced_login_method="chatgpt"` ve `web_search="live"` `--strict-config` ile kabul edildi.
- `codex login status`: girişsizken "Not logged in" ve çıkış kodu 1. "API key" içeren bir giriş **ücretli sayılır ve engellenir**.
- JSONL zarfı gözlendi: `thread.started`, `turn.started`, `error` (geçici yeniden bağlanma), `item.*`, `turn.completed` / `turn.failed`.
- Gerçek bir ChatGPT çalıştırması bu makineden yapılamadı (OpenAI erişimi yok). Olay içerikleri belgelere göre sahte bir CLI ile test edildi; ilk gerçek çalıştırma kullanıcının Mac'inde son doğrulamadır.
- İnceleme `read-only`, yazma işleri `workspace-write` sandbox'ında çalışır; ikisinde de ağ kapalıdır (web araması ayrı araçtır). Sistem talimatı istemin başına eklenir, çünkü Codex'te ayrı bir bayrağı yoktur.
- "usage limit" mesajı `QuotaExceeded` olur; "try again in X hours Y minutes" okunur, yoksa 30 dakika beklenir.

### Claude Code: doğrulanmış davranış (CLI 2.1.x)

- `claude -p --output-format stream-json --verbose` komutu satır satır JSON üretir.
- `system/init.apiKeySource == "none"` abonelik kullanıldığını gösterir.
- `rate_limit_event.rate_limit_info.unifiedWindows.{five_hour,seven_day}.utilization` alanları **gerçek** limit kullanımını verir.
- `result.structured_output` alanı `--json-schema` ile doğrulanmış çıktıyı içerir.
- `result.total_cost_usd` abonelikte temsili bir değerdir; harcama olarak gösterilmez.
- `--session-id <uuid>` yeni bir konuşma başlatır, `--resume <uuid>` sürdürür. Bilinmeyen bir kimlikle sürdürmek "No conversation found" yazar; adaptör bunu `SessionLost` olarak bildirir.
- `--add-dir` ile verilen klasörler (yüklemeler, çıktı klasörü) çalışma klasörü dışında okunup yazılabilir.

## 5. Kalite kapıları, kota ve bildirimler

- **Kalite kapıları** (`checks.py`): Bir tur projede değişiklik yaptıktan sonra projenin komutları ORBIT tarafından `sandbox-runtime` (`tools/`) içinde çalıştırılır.
  - Sandbox kuralları: yazma yalnızca worktree'ye; `TMPDIR` worktree içinde; ağ yalnızca npm/PyPI; araç önbellekleri `.orbit-cache`'te.
  - `srt` yoksa komutlar "atlandı" olarak işaretlenir, korumasız çalıştırılmaz.
  - Asistanın değiştirdiği bir test betiği güvenilmez koddur; bu yüzden sandbox şarttır.
  - Sonuç `tasks.checks`'e yazılır. Başarısız kontrollerin çıktısı bir sonraki turun prompt'una eklenir ("testleri silerek geçirme" kuralıyla); kullanıcının "düzelt" demesi yeter. `rerun_checks` yalnızca kontrolleri tekrarlar.
  - Not: `srt`'nin kendi soketleri sistemin geçici klasöründe kalır. Unix soket yolu ~104 karakterle sınırlı olduğundan `TMPDIR` yalnızca sandbox içindeki komuta verilir.
- **Kota** (`QuotaExceeded`):
  - `rate_limit_event.status == "rejected"` olunca yanıt `waiting` olur; yazılmış kısmı korunur, `meta.resume_at` sıfırlanma + 1 dk'dır.
  - Zamanlayıcı aynı turu yeniden çalıştırır; sunucu yeniden başlarsa zamanlayıcı yeniden kurulur. "Şimdi dene" beklemeyi atlar.
  - `allowed_warning` yalnızca bilgi amaçlıdır. Ücretli geçiş yoktur.
- **Bildirimler** (`notify.py`): macOS'ta `osascript`. Başlık ve gövde AppleScript koduna gömülmez, argüman olarak verilir; böylece bir mesaj komut enjekte edemez. 45 saniyeden uzun süren yanıtlar ve kota beklemesi bildirilir.
- **Şablonlar** (`templates.py` + `templates` tablosu): Hazır istekler kodda, kullanıcı şablonları veritabanında.

## 6. Tek sohbet, tek asistan

Kullanıcı mod seçmez. Her mesaj bir **turdur** (`ChatService._reply`). Asistan mesajdan ne istendiğini anlar: cevap verir, araştırır, tasarım çizer ya da projede değişiklik yapar. Talimat `assistant.SYSTEM`'dedir; Orbit ise çevreyi hazırlar ve sonuçları incelenebilir hale getirir.

**Bir tur:**
1. Model seçilir (`router.pick("assistant")`).
2. Çalışma yeri belirlenir: projenin izole kopyası (`sessions.workspace`), salt okunur proje ya da sohbete özel klasör.
3. Turun çıktı klasörü açılır: `data/outputs/<mesaj>`.
4. Prompt kurulur: proje hafızası, kalite kontrol komutları, başarısız kontroller, çıktı klasörü, önceki tasarımlar, ekler, gerekirse geçmiş ve kullanıcının mesajı.
5. Claude Code çalışır, yanıt parça parça akar.
6. Çıktılar toplanır: çıktı klasöründeki HTML'ler tasarım olarak çizilir (`meta.variants`), markdown'lar rapor olarak kaydedilir (`meta.reports`).
7. Projede değişiklik olduysa commit'lenir, kontroller çalışır ve değişiklik kartı güncellenir (`meta.task_id`).

**Konuşma hafızası:**
- Claude Code kendi oturumunu tutar: ilk tur `--session-id`, sonrakiler `--resume` ile (`chats.claude_session`). Geçmiş her turda yeniden gönderilmez; kota korunur.
- Oturum kaybolursa (`SessionLost`) ya da başka bir model yanıtlıyorsa geçmiş metin olarak gönderilir: en yeni 150 bin karakter, eskisi kayan özete katlanır (`chats.summary`). Özeti önce yerel model çıkarır.
- Proje değişince sohbetin Claude oturumu sıfırlanır (çalışma klasörü değişir).

**Düşünme seviyesi ve model:** Her çalıştırmaya `--effort` verilir (`assistant.EFFORT`): Ekonomik `medium`, Dengeli `high`, En iyi `xhigh`. Model tercihi `--model` ile geçer; "Varsayılan" seçiliyse aboneliğin seçtiği model kullanılır.

**Talimatın ana kuralları:**
- Kısa ya da belirsiz cevapları bağlamdan yorumlar ve ilerler; seçenek sıralamak yerine gerekçeli öneri yapar.
- Rakamları kaynakla verir, doğrulayamadığını "tahmini" diye işaretler, uydurmaz.
- Araştırma: alt sorular, 10-12+ arama, birincil kaynaklar. Kapsamlıysa rapor (Kısa cevap / Bulgular / Rakipler / Fırsatlar / Öneri + MVP / Riskler / Kaynaklar) çıktı klasörüne yazılır ve `MEMORY_DIR/Araştırmalar/` altına kaydedilir.
- Küçük değişiklikleri hemen yapar; büyük, çok dosyalı işlerde önce kısa plan yazıp onay ister.

### Ekip: alt ajanlar ve bağımsız inceleme

Kullanıcı model seçmez; iş bölümü koddadır.

- **Alt ajanlar** (`assistant.SUBAGENTS`, Claude Code `--agents` + `Agent` aracı): Araştırmacı, Tasarımcı, Test yazarı, İnceleyici. Her biri ayrı bir bağlamda, aynı abonelikle çalışır. Bir alt ajan liderin sahip olmadığı aracı alamaz (`assistant.team`); proje yoksa Test yazarı ve İnceleyici, salt okunur projede Tasarımcı da verilmez. Lider yalnızca büyük ve bölünebilir işlerde kullanır.
  - Doğrulanmış davranış (CLI 2.1.316): alt ajanlar arka planda çalışır. Liderin turu biter, her biten alt ajan yeni bir tur başlatır, süreç hepsi bitince kapanır ve her tur için bir `result` gelir; adaptör yalnızca sonuncusunu cevap sayar. Alt ajanın araç çağrıları `parent_tool_use_id` taşır; adaptör bunları alt ajanın adıyla etiketler, alt ajanın kendi metni ana cevaba karışmaz.
- **Bağımsız inceleme** (`review.py`, `ChatService._review`): Projede değişiklik yapan bir turdan sonra `router.pick("review", avoid={yazar})` bir inceleyici seçer.
  - İnceleyici aynı izole kopyada salt okunur çalışır ve sabit bir JSON şemasıyla cevap verir (`ozet`, `sorunlar[]`: önem/dosya/sorun/öneri). Sonrasında kopyadaki commitlenmemiş her şey atılır; inceleyici iz bırakamaz.
  - Yüksek ve orta önemli bulgular lidere tek bir düzeltme turu olarak gider. Claude kendi oturumunu sürdürür, geçmiş yeniden gönderilmez. Düzeltme ayrı bir commit ("İnceleme düzeltmeleri (Codex)") olur ve kontroller yeniden çalışır.
  - Ne zaman çalışır (`review.wanted`): Ekonomik hiç; Dengeli başka bir model varsa ya da değişiklik büyükse (≥5 dosya veya ≥200 satır); En iyi her zaman (gerekirse Claude ayrı oturumda).
  - İnceleme başarısız olursa (kota, hata) değişiklik korunur, günlüğe yazılır.

### Görseller ve tasarımlar

- **Yüklemeler** (`attachments.py`):
  - Dosya türü uzantıdan değil ilk baytlardan belirlenir; yalnızca PNG, JPEG, WebP ve GIF kabul edilir, en fazla 10 MB.
  - Görseller `data/uploads/` klasörüne kaydedilir.
  - Ek kimliği ya 32 karakterlik hex bir dosya kimliğidir ya da `design:<mesaj>:<n>` biçimindedir; bu ikisi dışındaki her şey reddedilir, bu da yol geçişini (path traversal) engeller.
  - Modele yalnızca dosya yolları ve `--add-dir` (okuma) verilir.
- **Tasarımlar** (`designs.py`):
  - Asistan her ekranı çıktı klasörüne bağımsız bir HTML olarak yazar. İlk satırdaki `<!-- başlık: … | fikir: … | görünüm: phone -->` yorumu başlığı, fikri ve ekran boyutunu verir.
  - ORBIT bu HTML'leri Playwright Chromium'da çizer. Sayfada JavaScript kapalıdır ve tüm ağ istekleri reddedilir. Arayüz yalnızca PNG'leri gösterir.
  - Önceki turların HTML'leri sonraki tura okunabilir olarak verilir; böylece "2'nin düzeni, 1'in renkleri" çalışır.
  - "Bunu uygula", tasarımın PNG'sini ve HTML'ini ek olarak yeni bir mesaja koyar.

### Sohbetteki değişiklikler (`sessions.py`, `tasks.kind = "session"`)

- **Kopya:** Proje seçili sohbetin ilk turunda bir oturum (task) ve worktree açılır. Sadece konuşulan sohbette değişiklik oluşmaz ve kart görünmez.
- **Commit:** Dosya değiştiren her tur bir commit ve bir adım (`task_steps`, `kind = "edit"`) olur. Ardından kontroller çalışır ve birleştirme onayı açılır.
- **Kararlar:** `approve` (birleştir), `undo_last` (son turu `reset --hard <commit>~1` ile geri al), `reject` (hepsini at), `rerun_checks`, `open_pr`. Asistan çalışırken karar verilemez.
- **GitHub PR** (`github.py`): `open_pr`, `orbit/task-N` branch'ini `--force-with-lease` ile push eder (geri alma branch'i yeniden yazdığı için) ve ilk seferde `gh pr create` ile PR açar; `tasks.pr_url` saklanır, sonraki gönderimler yalnızca push eder. Remote, insteadOf uygulanmamış `remote.origin.url`'den okunur. Git ve gh hiçbir zaman soru sormaz (`GIT_TERMINAL_PROMPT=0`, `GH_PROMPT_DISABLED=1`, SSH `BatchMode`) ve 120 sn'de zaman aşımına uğrar. Kimlik bilgisi kullanıcının git/gh ayarlarındadır; Orbit token saklamaz.
- **Ömür:** Birleştirme veya "Hepsini at" ile kapanır; sonraki değişiklik yeni bir oturum açar. Değişiklik içermeyen oturum, proje değiştirilince sessizce kapanır. Sohbet ya da proje silinince kopya ve branch temizlenir; kullanıcının projesine dokunulmaz.
- **Kurulum önbelleği:** Kontrollerin kurulum adımı, komut ve bağımlılık dosyaları değişmedikçe aynı worktree'de bir kez çalışır (`.orbit-cache/setup.done`).

### Proje Hafızası

- **Dosya:** Proje başına bir markdown dosyası (`MEMORY_DIR/<Proje>.md`, varsayılan `data/memory`).
- **Kullanım:** Her tura en fazla 12 bin karakteri eklenir. Uzunsa elle yazılmış baş kısmı ve en yeni günlük kayıtları korunur.
- **Karar Günlüğü:** Her birleştirmede birleştirilen isteklerin özeti ve commit otomatik eklenir. Ek model çağrısı yapılmaz.
- **Obsidian:** Zorunlu değil. Dosyalar düz markdown olduğu için `MEMORY_DIR` bir Obsidian kasasının içini gösterebilir; eklenti veya API gerekmez. Operasyonel durum SQLite'ta kalır, kalıcı bilgi markdown'dadır.

## 7. Veri modeli (SQLite)

`projects` (kontrol ayarı dahil), `chats` (kayan özet ve Claude oturumu dahil), `messages` (`meta`: ekler, tasarımlar, raporlar, değişiklik oturumu, kota bekleme), `tasks` (sohbetteki değişiklik oturumları), `task_steps` (tur başına bir commit), `task_events` (yalnızca ekleme yapılan günlük), `approvals`, `audit_logs`, `templates`, `preferences`.

**Şema geçişi:** `db._add_missing_columns` yalnızca ekleme yapar; yeni sütunları mevcut veritabanına `ALTER TABLE ADD COLUMN` ile ekler. Eski veritabanları sürüm güncellemelerinde bozulmaz.

Dokümandaki diğer tablolar (`model_usage`, `skill_registry`, `mcp_connections` …) ilgili faz geldiğinde eklenecek.

## 8. Yaşam döngüleri

**Mesaj:** `streaming` → `done` | `error` | `cancelled` | `waiting` (kota) → `streaming` (otomatik ya da "Şimdi dene").

**Değişiklik oturumu:**

```
tur başlar ──► running ──(tur biter: commit + kontroller)──► waiting_approval
waiting_approval ──yeni tur──► running
waiting_approval ──undo_last──► waiting_approval (son tur geri alındı)
waiting_approval ──approve──► git merge --no-ff ──► completed (worktree + branch silinir)
waiting_approval ──reject──► cancelled (worktree + branch silinir)
```

- **Birleştirme güvenliği:** Birleştirme yalnızca oturumun başladığı branch açıkken yapılır. Çakışma olursa `merge --abort` ile geri alınır ve onay beklemede kalır.
- **Yeniden başlatma:** Sunucu yeniden başlarsa yarıda kalan yanıtlar hata olarak işaretlenir, çalışır görünen oturumlar incelemeye döner, kota bekleyen yanıtların zamanlayıcısı yeniden kurulur.
- **Eşzamanlılık:** Bir sohbette aynı anda tek yanıt yazılır.

## 9. Yol haritası durumu

- [x] **Faz 1 — Temel:** iskelet, SQLite, sohbet, projeler, loglar, WebSocket
- [x] **Adaptör arayüzü + Claude Code adaptörü + maliyet koruması**
- [x] **Tek sohbet, tek asistan:** mod yok; sohbet, araştırma, tasarım ve değişiklik aynı akışta (eski Orchestrator, ajanlar ve modlar kaldırıldı)
- [x] **İzole kopyada değişiklik:** git worktree, tur başına commit, sandbox, diff, geri alma, birleştirme
- [x] **Claude oturum sürekliliği:** `--resume`, kaybolursa geçmişten yeniden kurulum
- [x] **Proje Hafızası + otomatik karar günlüğü** (Obsidian uyumlu düz markdown)
- [x] **Ollama adaptörü:** özetleme ve yedek sohbet; dosya araçları yok, asla değişiklik yapmaz
- [x] **Uzun sohbet özetleme** (önce yerel model)
- [x] **Codex adaptörü:** ChatGPT girişi zorunlu, salt okunur inceleme ve yedek asistan; gerçek hesapla ilk deneme kullanıcıda
- [x] **Ekip:** Claude alt ajanları (araştırmacı, tasarımcı, test yazarı, inceleyici) ve farklı modelle bağımsız inceleme + düzeltme turu
- [ ] **Gemini:** Gemini CLI kişisel girişi kapattı; Antigravity CLI (`agy`) arka planda güvenilir çalışıyorsa inceleme ve araştırma rolüyle
- [x] **Kalite kapıları** (sandbox'ta, ORBIT'in kendisi çalıştırır)
- [x] **Kota dolunca otomatik bekleme ve devam**
- [x] **macOS bildirimleri**
- [x] **Şablonlar** (hazır ve kullanıcı)
- [x] **Güvenlik sertleştirmesi:** CSRF, gizli dosya erişimi, log maskeleme, özel veri klasörü, temiz alt süreç ortamı
- [x] **Görsel ekleme + tasarım varyantları**
- [x] **Model yönlendirici** (kota baskısı, sağlık, elle sabitleme)
- [x] **GitHub PR:** sohbetin değişikliklerini tek tıkla PR olarak gönderme ve güncelleme
- [ ] **Sıradaki adaylar:** iOS simülatör ekran görüntüsü; web projeleri için görsel önizleme
- [ ] Grok Build adaptörü (ücretsiz erişim doğrulanırsa)
- [ ] Faz 4–8: dokümandaki sırayla
