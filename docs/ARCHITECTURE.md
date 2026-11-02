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
- **Repodaki `.claude/settings.json` güvenilmez veridir.** CLI destekliyorsa Claude Code `--restricted` ile başlar (sağlık kontrolü `--help`'e bakar): hiçbir ayar dosyası yüklenmez, dosya araçları çalışma klasörü ve `--add-dir` ile sınırlıdır, `.git` ve ayar dosyalarına yazılamaz. Doğrulandı: klasör dışından okuma ve `.git/hooks/pre-commit`'e yazma reddedildi. Eski CLI'da `--setting-sources user` kullanılır. Her çalıştırma `--strict-mcp-config` ile yalnızca Orbit'in verdiği MCP sunucularını görür.
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
- `review`: değişikliklerin bağımsız incelemesi. Sıra: Codex → Gemini → Claude Code; değişikliği yazan model `avoid` ile en sona itilir.
- `summarize`: uzun sohbet özetleri ve Claude kullanılamadığında yedek sohbet. Sıra: Ollama → Gemini → Claude Code.

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

### Gemini (Antigravity CLI): doğrulanmış davranış (agy 1.4.12)

- Gemini CLI, Haziran 2026'dan beri kişisel Google hesaplarını kabul etmiyor. AI Plus/Pro aboneliği terminalden Antigravity CLI (`agy`) ile kullanılır.
- Kullanıcının Mac'inde doğrulandı: `agy -p "…" --output-format json < /dev/null > dosya` terminalsiz çalışır, 0 ile çıkar ve tek bir JSON yazar: `{conversation_id, status: "SUCCESS", response, duration_seconds, num_turns, usage}`. Bayraklar `agy --help`'ten alındı: `--json-schema`, `--effort`, `--sandbox`, `--add-dir`, `--print-timeout`.
- Rolü yalnızca inceleme ve özettir; asla değişikliği yazan model olmaz (`coding=False`). Terminalsiz `agy` izin istemlerine cevap veremez, bu yüzden dosya düzenleyemez ve komut çalıştıramaz. Ayrıca `--sandbox` ile çalışır, `--dangerously-skip-permissions` hiç kullanılmaz. Özetler boş bir geçici klasörde çalışır.
- Google API anahtarı ve Vertex/Cloud değişkenleri alt sürece verilmez; yalnızca giriş yapılmış hesap kullanılabilir. Sağlık kontrolü `agy models` çıkış koduna bakar.
- Kullanıcının denemesinde model kodu test etmek için komut çalıştırmak istedi; terminalsiz agy bunu reddetti ve `status: SUCCESS`, boş `response`, `denied_actions: [{action: "command"}]` döndü. Bu yüzden istemin başında komut çalıştıramayacağı söylenir; yine denerse bir kez "araç kullanmadan cevap ver" diye tekrar sorulur, yine boşsa inceleme hata olarak günlüğe düşer (sessizce "sorun yok" sayılmaz).
- Henüz doğrulanmadı: başarılı bir `--json-schema` cevabının yeri. Adaptör ayrı bir alanı ya da JSON olarak yazılmış `response`'u kabul eder.

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

### Proje Kartı ve alan uzmanları (`card.py`)

- **Kart:** Proje kökündeki `PROJE.md`. Fikir ya da spec gelince, yeni bir projede veya birden çok alanı kapsayan büyük bir işte lider önce kartı yazar ve onay ister (talimat `assistant.SYSTEM`). Kart her turda liderin istemine (`card.lead_block`, 16 bin karakter) ve inceleyicinin istemine eklenir.
- **Ekip tablosu:** `| Alan | Teknoloji | Klasör | Yapan |`. `card.team` okur (Türkçe karakter ve başlık çeşitlerine dayanıklı, en fazla 8 alan). `assistant.specialists` her alana bir `<alan>-gelistirici` kurar:
  - Talimatında kartın kendisi (8 bin karakter) ve "kartı ve klasöründeki kodu okumadan yazma, yalnızca kendi klasörüne yaz" kuralı vardır.
  - Model Dengeli'de `sonnet`, En iyi'de `inherit`; Ekonomik'te uzman yoktur. Salt okunur projede kod yazan uzman kurulmaz.
- **Codex aynı anda** (`mcp_codex.py`): "Yapan: Codex" olan alana ayrıca bir `<alan>-codex` koordinatörü kurulur.
  - Koordinatörün tek yazma yolu `mcp__orbit__codex_gorev` aracıdır. Orbit, o tur için Claude Code'a kendi küçük MCP sunucusunu verir (`--mcp-config`, `--strict-mcp-config`; kullanıcının MCP sunucuları yüklenmez).
  - Aracın tek girdisi görev metnidir. Kök klasör (o sohbetin izole kopyası), ChatGPT girişi, `workspace-write` sandbox'ı ve ağın kapalı olması Orbit tarafından sabitlenir; model bunları değiştiremez.
  - Arka plandaki Claude alt ajanlarıyla birlikte iki abonelik aynı anda çalışır. Kota dolarsa araç `CODEX_KULLANILAMADI` döner ve lider alanı Claude geliştiricisine verir. Uzun işler için Claude'a `MCP_TOOL_TIMEOUT=30 dk` verilir.
  - Codex o turda yazdıysa inceleme ne Claude'a ne Codex'e, üçüncü bir modele (Gemini) gider.
- **Gerçek denemeler** (Claude Code 2.1.316; Codex tarafı sahte CLI ile):
  - Lider Backend'i Codex koordinatörüne, Frontend'i Claude uzmanına aynı anda verdi.
  - Koordinatör kartı, klasör sınırını ve kabul ölçütünü içeren bir görev yazdı, sonucu kontrol edip bir kez düzeltme istedi.
  - Spec'ten yazılan kartta 9 bölüm vardı ve Codex hazırken Backend'i Codex'e verdi.
- **Görüntüleme:** `GET /projects/{id}/card` kartın en yeni halini döndürür: henüz birleştirilmemişse sohbetin kopyasındakini (`pending`), değilse projedekini (`merged`).

### Model planı ve canlı orkestra (`tiers.py`, `orchestra.py`)

- **Seviyeler:** güçlü / orta / hafif × efor (low…max). Claude: opus / sonnet / haiku (takma adlar). Codex: gpt-6-astra / gpt-6.1-sol / gpt-6-luna (`codex debug models` açıklamalarına göre: "frontier", "workhorse for coding", "fast and affordable").
- **Roller:** lead, builder, designer, reader, reviewer. Kaliteye göre ön ayar (`tiers.PRESETS`):
  - Ekonomik: lider orta·medium.
  - Dengeli: lider güçlü·high, kod yazan orta·medium, okuyucu hafif·low.
  - En iyi: lider güçlü·xhigh, kod yazan güçlü·medium.
- **Alan seviyesi:** Kartın "Güç" sütunu her alanın seviyesini belirler; `BUILDER_CAP` ile sınırlanır (lider düşürebilir, yükseltemez).
- **Diğer kurallar:**
  - Kullanıcının "Lider modeli" sabitlemesi plandan önce gelir.
  - Özetler hafif·low çalışır.
- **Doğrulandı:**
  - Alt ajan tanımında `model` ve `effort` uygulanıyor; geçersiz bir efor değeri CLI tarafından reddediliyor.
  - "haiku" denen alt ajan `claude-haiku-5-5` ile çalıştı.
  - Gerçek bir turda lider Opus 5.5 · high, frontend uzmanı Sonnet 5.5 · medium, Codex koordinatörü Sonnet 5.5 · low ile çalıştı.
- **Model yoksa:**
  - Claude 404 / "issue with the selected model" döner. Adaptör `--model` olmadan, aynı modeli isteyen alt ajanları `inherit` yaparak bir kez yeniden dener.
  - Codex "model … not supported" verirse `-m` olmadan yeniden dener.
- **Canlı orkestra:** Claude akışındaki olaylar kullanılır:
  - `system/task_started|task_progress|task_notification`: alt ajan başladı, ilerliyor (`usage.total_tokens`), bitti.
  - Alt ajan mesajlarındaki `message.model`: gerçek model.
  - Codex köprüsü çağrısı ve dönüşü.
  - `result.modelUsage`: modele göre token.

  `Orchestra` bunları `{lead, members, usage}` olarak WebSocket'e (`type: "team"`) yayınlar ve turun sonunda `messages.meta.team`'e yazar. İnceleyici de bir üye olarak görünür.

### Sohbet mi, iş mi? (`intent.py`) ve model seçici

- **Ölçüm (Claude Code 2.1.316, aynı kısa sohbet mesajı):**
  - Opus, tüm araçlar ve ekip: yaklaşık 13,5 bin token.
  - Sonnet, araçlar, ekip yok: yaklaşık 9,7 bin.
  - Sonnet, araçsız: yaklaşık 5,9 bin.

  Kısa bir turun çoğu sabit yüktür (Claude Code'un kendi talimatı, araç ve ekip tanımları); Opus token'ı da limitten en çok yiyendir.
- **Otomatik:** `intent.is_light`, model çağrısı yapmadan karar verir. Ek yoksa, mesaj 600 karakterden kısaysa ve kelime başında bir iş ya da onay kökü yoksa (araştır, ekle, yap, tamam, devam…; "uygulama" ismi hariç) mesaj hafif kabul edilir.
  - Hafif tur: Sonnet · low, salt okunur araçlar, ekip ve köprü yok.
  - Hafif model mesajın aslında iş olduğuna karar verirse yalnızca `[[ORBIT:TAM_GUC]]` yazar. Bu işaret akışta tutulup ekrana hiç yansımaz; aynı mesaj aynı Claude oturumunda tam planla yeniden işlenir.
  - Gerçek deneme: sohbet girişi Sonnet 5.5 · low ile yaklaşık 6,1 bin token tuttu. Kaçırılan bir iş mesajında hafif tur 38 çıktı token'ıyla işi geri verdi ve Opus işi yaptı.
- **Seçici** (`catalog.py`, `GET /api/catalog`): `chats.model_choice` ("auto" ya da "<sağlayıcı>/<model>", eski "haiku/sonnet/opus" da geçerli) ve `chats.effort_choice` her mesajla gönderilir, sohbette kalır ve `^(auto|…|(claude_code|codex|gemini|ollama|mock)/[\w.:-]+)$` ile doğrulanır.
  - Model listeleri sağlayıcılardan gelir ve 10 dakika önbelleklenir: Codex `codex debug models` (görünürlüğü "list" olanlar ve modelin efor seviyeleri), Gemini `agy models`, yerel modeller Ollama'dan. Claude'un listesi sabittir (Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.1); abonelikte olmayan model 404 ile varsayılana düşer.
  - Seçilen sağlayıcı kullanılamıyorsa (kurulu değil, giriş yok, kota, ücretli) tur Otomatik ile çalışır ve cevabın başına neden yazılır.
  - Codex lider olabilir (ekip yok). Gemini okuyup arar ama dosya değiştirmez; istemde bu söylenir. Yerel model araçsız çalışır.
  - `chats.claude_seen_until`: Claude kendi oturumunu sürdürürken, oturumun görmediği diğer modellerin turları "ARADA BAŞKA MODELLERLE KONUŞULANLAR" olarak eklenir.
  - Düzeltilen hata: model seçimi eklendiğinde Claude oturumu her mesajda yanlışlıkla sıfırlanıyordu (geçmiş her turda metin olarak gidiyordu). Artık yalnızca proje değişince sıfırlanır; testle korunuyor.
- **Sağlamlık:** Tur, kendi hata yakalamasından önce bir hata verirse `_guarded` mesajı hata olarak bitirir; mesaj "yazılıyor" durumunda kalmaz.
- **Token toplamı:** Bir turdaki bütün çalıştırmalar (hafif tur, tam tur, ayrı oturumda inceleme) modele göre toplanır.

### Görseller ve tasarımlar

- **Yüklemeler** (`attachments.py`):
  - Görsellerde tür uzantıdan değil ilk baytlardan belirlenir: PNG, JPEG, WebP, GIF, en fazla 10 MB. Metin dosyaları (`.md`, `.txt`) NUL baytı olmayan geçerli UTF-8 olmalıdır, en fazla 1 MB. Metin dosyaları `text/plain` ve `nosniff` ile sunulur, asla sayfa olarak işlenmez.
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
- [x] **Gemini (Antigravity CLI):** bağımsız inceleme ve özet; Google hesabıyla, kod yazmaz
- [x] **Kalite kapıları** (sandbox'ta, ORBIT'in kendisi çalıştırır)
- [x] **Kota dolunca otomatik bekleme ve devam**
- [x] **macOS bildirimleri**
- [x] **Şablonlar** (hazır ve kullanıcı)
- [x] **Güvenlik sertleştirmesi:** CSRF, gizli dosya erişimi, log maskeleme, özel veri klasörü, temiz alt süreç ortamı
- [x] **Görsel ekleme + tasarım varyantları**
- [x] **Model yönlendirici** (kota baskısı, sağlık, elle sabitleme)
- [x] **GitHub PR:** sohbetin değişikliklerini tek tıkla PR olarak gönderme ve güncelleme
- [x] **Proje Kartı + alan uzmanları:** spec/.md'den kart, karttan uzmanlar, kart her ajanın talimatında
- [x] **Claude ve Codex aynı anda:** Orbit'in MCP köprüsüyle Codex bir alanı paralel yazar
- [x] **Kısıtlı mod** (`--restricted`) ve tur başına yalnızca Orbit'in MCP sunucuları
- [x] **Rol başına model ve efor planı** (Claude ve Codex karşılıkları, kartta alan başına seviye, abonelikte olmayan modelde geri düşme)
- [x] **Canlı orkestra paneli** (kim, hangi gerçek model, efor, ne yapıyor, token)
- [ ] **Sıradaki adaylar:** iOS simülatör ekran görüntüsü (Mac'te doğrulanmalı); web projeleri için canlı önizleme
- [ ] Grok Build adaptörü (ücretsiz erişim doğrulanırsa)
- [ ] Faz 4–8: dokümandaki sırayla
