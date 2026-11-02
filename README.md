# Orbit — AI Komuta Merkezi

Kişisel, local-first AI asistanı. Tek bir sohbet var; ne istediğinizi düz yazarsınız. Asistan sohbet eder, araştırır, tasarım çizer ya da projenizde değişiklik yapar. Değişiklikler projenin izole bir kopyasında yapılır ve siz birleştirene kadar gerçek projenize dokunmaz.

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
- `make demo`: Claude Code olmadan, sahte yanıtlarla arayüzü deneme
- `make test`: backend testleri ve frontend typecheck

## Nasıl kullanılır

Mod yok, ayrı ekran yok. Ne istediğinizi yazın; asistan mesajdan ne yapması gerektiğini anlar.

| Yazdığınız | Olan |
| --- | --- |
| "Aklımda bir uygulama fikri var…" | Sohbet eder, soru sorar, gerekçeli öneri verir. |
| "Habit tracker'ların en büyük şikayetleri neler, araştır" | Onlarca kaynağı tarar. Kapsamlı bir araştırmaysa kaynakçalı raporu `Araştırmalar/` klasörüne markdown olarak kaydeder, sohbette özetini verir. |
| "Giriş ekranı için 3 farklı tasarım" | Birbirinden farklı ekranlar çizer, görselleri yan yana gösterir. "2'nin düzeni, 1'in renkleri" gibi yeni turlar isteyebilirsiniz. |
| "Başlığı büyüt", "hata mesajlarını Türkçeleştir" | Projenin bir kopyasında hemen yapar. |
| Büyük, çok dosyalı bir iş | Önce kısa bir plan yazar ve onayınızı ister; "tamam" deyince uygular. |

**Proje seçimi:** Yazma kutusundaki proje seçicisinden bir proje seçerseniz asistan kodunuzu okuyabilir ve değişiklik yapabilir. Proje seçmezseniz yalnızca sohbet, araştırma ve tasarım yapar.

**Değişiklik kartı:** Bir mesaj projede bir şeyi değiştirdiğinde sohbette bir kart çıkar. Kartta yapılan değişiklikler, kalite kontrolleri ve diff görünür. Kartın butonları:
- **Birleştir:** Değişiklikleri projenize alır.
- **Son değişikliği geri al:** Yalnızca son mesajın yaptığı değişikliği geri alır.
- **Hepsini at:** Kopyadaki tüm değişiklikleri siler.

Sohbete yazmaya devam ettikçe değişiklikler aynı kopyada birikir.

**GitHub:** Projenin `origin`'i GitHub'daysa kartta **GitHub'da PR aç** butonu da çıkar. Değişiklikler `orbit/task-N` branch'ine push edilir ve bir pull request açılır; sonraki değişikliklerden sonra **PR'ı güncelle** ile aynı PR güncellenir. Bunun için GitHub CLI gerekir (`brew install gh && gh auth login`). Push ve PR yalnızca butona bastığınızda yapılır. Asistan kendisi push edemez, çünkü komutları internete yalnızca paket depoları üzerinden çıkabilir. Orbit token saklamaz.

**Tasarımı uygulama:** Bir tasarımın altındaki **Bunu uygula** butonu, o tasarımı (görsel ve HTML) ekleyerek mesajı hazırlar. Siz gönderirsiniz. Tasarımlar internet erişimi ve JavaScript kapalı bir tarayıcıda çizilir.

**Görsel ekleme:** Ataç butonu, yapıştırma (⌘V) veya sürükle-bırak ile ekran görüntüsü eklenebilir. Asistan görseli okur.

**Hazır bir fikir ya da spec dosyasıyla başlamak:** Ataç butonuyla `.md` ya da `.txt` dosyanı ekle ve "bununla başlayalım" de. Asistan kod yazmadan önce projede bir **Proje Kartı** (`PROJE.md`) hazırlar:
- amaç ve kapsam (MVP / sonra),
- mimari ve her alan için en uygun teknoloji (gerekçesiyle),
- ekip: hangi alanı kim yapar,
- alanlar arası API sözleşmesi,
- veri modeli,
- kabul ölçütlü aşamalar.

En fazla 3 kritik soru sorar ve onay ister; sen onaylamadan uygulama koduna başlamaz. Kart **Projeler → Kart**'tan okunabilir. Kararlar değiştikçe güncellenir.

Onaydan sonra iş aşama aşama ilerler:
1. Önce alanlar arası sözleşme sabitlenir.
2. Her alanın işi o alanın uzmanına gider; bağımsız alanlar aynı anda çalışır.
3. Testler yazılır.
4. Kontroller çalışır ve bağımsız inceleme yapılır.

Her aşamanın sonunda tek bir değişiklik kartı görürsün; "devam" deyince sonraki aşamaya geçilir.

**Ekip:** Asistan tek başına çalışmak zorunda değil; sen model seçmezsin, iş bölümünü kendisi yapar:
- **Claude (lider):** İsteği anlar, planlar, kartı yazar ve işi dağıtır. Genel uzmanları: **Araştırmacı**, **Tasarımcı**, **Test yazarı**, **İnceleyici**.
- **Alan uzmanları:** Proje Kartı'ndaki her alan için Orbit kendiliğinden bir uzman kurar, ör. "Backend geliştirici (FastAPI, server/)" ya da "Frontend geliştirici (React, web/)". Her uzmanın talimatında kartın kendisi vardır; projeyi anlamadan, kartı ve kendi klasöründeki kodu okumadan çalışmaz ve yalnızca kendi klasörüne yazar. Kodu yazan uzmanlar Dengeli kalitede daha hızlı ve kotayı az harcayan Sonnet'le çalışır; mimariyi kuran lider senin seçtiğin modelde kalır.
- **Codex (ikinci geliştirici):** Kartta "Yapan: Codex" olan alanların kodunu Codex yazar, Claude'un uzmanlarıyla **aynı anda**. Böylece iki abonelik birlikte çalışır; Codex yalnızca yedekte beklemez. Lider, Codex kuruluyken bağımsız alanlardan en az birini ona verir. Codex'in kotası dolarsa o alanı Claude'un uzmanı devralır.
- **Bağımsız inceleme:** Değişikliği, onu yazmayan bir model inceler: Claude yazdıysa Codex ya da Gemini, Codex de yazdıysa Gemini. Ciddi bir sorun bulunursa Claude düzeltir, katılmadığı maddeyi gerekçesiyle reddeder. Bulgular cevabın altında görünür.
- **Gemini (ikinci göz):** Google hesabınla (AI Plus/Pro) çalışır. Codex yoksa Claude'un değişikliklerini o inceler; uzun sohbet özetlerini de o çıkarır, böylece Claude'un kotası harcanmaz. Kod yazmaz.
- **Ollama (yerel):** Varsa uzun sohbetleri ücretsiz özetler.

**Model seçici:** Yazma kutusundaki model düğmesi bir panel açar. Panelde **Otomatik** ve her sağlayıcının modelleri vardır:
- **Claude:** Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.1.
- **Codex:** `codex debug models`'tan, ör. GPT-6.1 Sol, GPT-6 Astra, GPT-6 Luna.
- **Gemini:** Antigravity hesabındaki modeller (`agy models`), Antigravity üzerinden sunulan Claude ve GPT-OSS dahil.
- **Yerel:** Ollama'da kurulu modeller.

Seçilen modelin altında o modelin desteklediği efor seviyeleri çıkar (low, medium, high, xhigh, max; bazı Codex modellerinde ultra). Her sohbet kendi seçimini hatırlar. Kurulu ya da kullanılabilir olmayan sağlayıcı nedeniyle birlikte soluk görünür. Seçilen model o an kullanılamıyorsa cevap Otomatik ile verilir ve bu cevabın başında yazar.
- **Claude seçiliyse:** Ekip ve Codex köprüsü dahil her şey çalışır.
- **Codex seçiliyse:** Dosya değiştirir ve komut çalıştırır, ama Claude'un ekibi olmadan.
- **Gemini seçiliyse:** Okur ve araştırır, dosya değiştiremez.
- **Yerel model seçiliyse:** Yalnızca sohbet eder.
- **Model değiştirince:** Sohbet ortasında Claude'dan başka bir modele geçip geri dönersen, aradaki konuşmalar Claude'a ayrıca aktarılır; Claude kendi oturumunu sürdürür.
- **Otomatik (önerilen):** Orbit mesajı token harcamadan inceler. Sıradan sohbet ("aklımda bir fikir var", "sence tutar mı?") Sonnet · low ile, ekip ve yazma araçları olmadan gider. Ölçüm: bir sohbet girişi Opus ve tam ekiple yaklaşık 14-25 bin token tutarken bu modda yaklaşık 6 bin token tutuyor ve daha ucuz bir model kullanılıyor. Gerçek iş ("ekle", "araştır", "tasarla", "tamam, başla") tam plana gider. Orbit bir işi yanlışlıkla sohbet sanarsa model bunu söyler ve aynı mesaj tam güçle yeniden işlenir (gerçek denemede yaklaşık 5 bin token ek maliyet).
- **Belirli bir model:** Liderin modelini ve eforunu sen seçersin.

**Kim hangi modelle çalışır:** Her rolün bir model seviyesi (güçlü / orta / hafif) ve bir eforu vardır. Orbit seviyeyi Claude'da Opus / Sonnet / Haiku'ya, Codex'te GPT-6 Astra / GPT-6.1 Sol / GPT-6 Luna'ya çevirir. Dengeli kalitede:
- **Lider:** Opus · high. Planlar, işi böler, kontrol eder.
- **Kod yazan uzmanlar:** Sonnet · medium.
- **Keşifçi ve araştırmacı:** Haiku · low. Okur, bulur, özetler.
- **İnceleyici:** Sonnet · medium.
- **Özetler:** Önce yerel model, sonra Gemini Flash, en son Haiku.

Lider, kartta her alan için bundan daha düşük bir seviye seçebilir ama daha yükseğini seçemez. Örneğin basit bir arayüz için "Orta · low", güvenlik ya da eşzamanlılık içeren bir backend için "Güçlü · medium". Pahalı lider çok dosya okumak yerine bu işi ucuz Keşifçi'ye verir. Planın tamamı **Ayarlar → Model planı**'nda görünür. Bir model aboneliğinde yoksa Orbit kendiliğinden varsayılan modele geçer.

**Canlı orkestra:** Ekip çalışırken cevabın üstünde bir **Orkestra** paneli açılır. Panelde şunlar görünür:
- lider ve her ajan, hangi şirketin modeli olduğu,
- gerçekte çalışan model (ör. "Haiku 5.5") ve eforu (nokta göstergesi),
- o an ne yaptığı ve harcadığı token,
- Codex'in hangi alanda çalıştığı ve inceleyicinin bulduğu sorun sayısı.

Tur bitince panel mesajda özet olarak kalır ve modele göre toplam girdi ve çıktı token'ını gösterir.

Ekibin ne kadar çalışacağını **Ayarlar → Kalite** belirler:
- **Ekonomik:** Tek asistan, Sonnet · medium; alt ajan ve inceleme yok.
- **Dengeli:** Yukarıdaki plan. Her değişikliği başka bir model inceler; başka model yoksa yalnızca büyük değişiklikler incelenir.
- **En iyi:** Lider Opus · xhigh, kod yazanlar Opus · medium, okuyucular Sonnet · low; her değişiklik incelenir. Kota en hızlı bu ayarda biter.

**Hafıza:** Asistan aynı sohbetteki konuşmayı hatırlar. Çok uzun sohbetlerin eski kısımları özetlenir; özetleme varsa ücretsiz yerel modelle yapılır.

**Model ve düşünme:** **Ayarlar**'dan kalite (Ekonomik / Dengeli / En iyi) ve model (Varsayılan / Sonnet / Opus / Fable) seçilir. Daha yüksek kalite daha derin düşünür ama kotayı daha hızlı harcar.

## Model seçimi

Asistan Claude Code ile çalışır. **Model Yöneticisi → İş dağılımı**'nda o an hangi modelin çalıştığı ve nedeni görünür. Model elle de sabitlenebilir.

**Seçim kuralları:**
- Sağlıksız, kotası dolmuş veya ücretli API gerektiren model atlanır.
- İnceleme, değişikliği yazandan farklı bir modele gider: önce Codex, sonra Gemini, ikisi de yoksa Claude ayrı bir oturumda.
- Claude'un kotası %90'ı geçerse ve Codex kuruluysa iş ona geçer.
- Claude hiç kullanılamıyorsa yerel model (Ollama) sohbeti sürdürür. Yerel model dosya okuyamaz ve değişiklik yapamaz.

**Gemini'yi eklemek (Google hesabı):** Gemini CLI kişisel hesapları artık kabul etmiyor; Google'ın yerine çıkardığı Antigravity CLI kullanılır.

```bash
brew install --cask antigravity-cli
```

Sonra bir kez `agy` çalıştırıp Google hesabınla giriş yap ve **Model Yöneticisi → Kontrol et**'e bas. Orbit, Gemini'yi API anahtarıyla değil yalnızca giriş yaptığın hesapla çalıştırır; Google API anahtarı ortam değişkenleri ona verilmez. Antigravity'de ek kredi satın almadığın sürece abonelik dışı ücret oluşmaz.

**Codex'i eklemek (ChatGPT aboneliği):**

```bash
npm install -g @openai/codex
```

```bash
codex login
```

Girişte **ChatGPT hesabıyla** giriş yapın, API anahtarıyla değil. Orbit API anahtarıyla yapılmış bir girişi algılar ve ücret oluşmaması için Codex'i kapalı tutar; API anahtarı ortam değişkenleri de Codex'e hiç verilmez. Ardından **Model Yöneticisi → Kontrol et**'e basın, Codex "Kullanılabilir" görünmeli. Ayar gerekmez; inceleme işini kendiliğinden alır.

## Kalite kontrolleri

Asistan projede bir değişiklik yapınca ORBIT projenizin test, lint ve tip kontrolü komutlarını **kendisi** çalıştırır ve sonucu diff'in yanında gösterir. Böylece "testler geçti" bilgisi bir modelin iddiası değil, ölçülmüş bir sonuç olur.
- **Komut seçimi:** npm, Python (uv veya requirements) ve Makefile projelerinde komutlar otomatik algılanır. **Projeler → Kontroller**'den değiştirilebilir.
- **Sandbox:** Komutlar `sandbox-runtime` içinde çalışır; yalnızca projenin kopyasına yazabilir ve internete yalnızca paket depoları üzerinden çıkabilir. Sandbox kurulu değilse komutlar hiç çalıştırılmaz.
- **Başarısız kontrol:** Asistan bir sonraki mesajda hata çıktısını görür; "düzelt" demeniz yeter. **Düzeltmesini iste** bu mesajı sizin için hazırlar. **Yeniden çalıştır** asistanı çalıştırmadan kontrolleri tekrarlar.

## Kota, bildirimler, şablonlar

- **Kota dolunca:** Yanıt hata vermez, bekler ve kota sıfırlandığında kendiliğinden devam eder. İsterseniz **Şimdi dene** ile hemen deneyebilirsiniz. Ücretli kullanıma hiçbir durumda geçilmez.
- **Bildirimler:** Uzun süren bir yanıt (araştırma, büyük değişiklik) bittiğinde veya kota dolduğunda macOS bildirimi gelir. **Ayarlar**'dan kapatılıp test edilebilir.
- **Şablonlar:** Yazma kutusundaki şablon butonu ya da kutunun başına `/` yazmak hazır istekleri açar (test ekle, hata düzelt, güvenlik incelemesi …). Yazdığınız bir metni şablon olarak kaydedebilirsiniz.

## Güvenlik

- **Ağ:** Sunucu yalnızca `127.0.0.1`'de dinler. Başka sitelerden gelen istekler (CSRF) ve sahte host adları (DNS rebinding) reddedilir.
- **Kısıtlı mod:** Claude Code destekliyorsa `--restricted` ile çalışır. Dosya araçları yalnızca çalışma kopyasına ve Orbit'in verdiği klasörlere erişir; `.git` ve ayar dosyalarına yazamaz, bu yüzden git kancası yerleştiremez. Ayar dosyaları ve senin kendi MCP sunucuların yüklenmez.
- **Gizli dosyalar:** Asistan `.env`, `*.pem`, `*.key`, `*.p8` gibi dosyaları okuyamaz. Çalıştırdığı komutlar sandbox içindedir; `~/.ssh`, `~/.aws`, `~/.claude` gibi klasörleri ve ORBIT'in kendi veritabanını göremez, projenin kopyası dışına yazamaz.
- **Repo ayarları:** Repo içindeki `.claude/settings.json` dikkate alınmaz; bir repo kendi hook'larıyla komut çalıştıramaz.
- **Loglar:** Token, anahtar ve şifre benzeri değerler kaydedilmeden önce `[gizli]` olarak maskelenir. `data/` klasörü yalnızca sizin kullanıcınız tarafından okunabilir.
- **Git:** Veritabanı, loglar, hafıza ve çalışma kopyaları `.gitignore`'dadır; GitHub'a gitmez.
- **GitHub:** Yalnızca Orbit'in kendi `orbit/task-N` branch'i ve yalnızca sizin tıklamanızla push edilir. Sizin branch'lerinize push yapılmaz.

## Proje Hafızası

Her projenin, asistana her mesajda verilen bir hafıza dosyası vardır. Açmak için **Projeler → Hafıza**.
- **Notlar:** Kalıcı kararları buraya yazın, örneğin "arayüz Türkçe", "SwiftUI kullan", "yeni bağımlılık ekleme".
- **Karar Günlüğü:** Birleştirilen her değişiklik buraya otomatik olarak eklenir.

Dosyalar düz markdown'dır. Obsidian kullanıyorsanız klasörü kasanızın içine taşıyıp notları orada görebilir ve bağlayabilirsiniz:

```bash
make start MEMORY_DIR=~/Documents/Obsidian/Orbit
```

## Yerel modeller (Ollama, isteğe bağlı)

Ücretsizdir ve kota harcamaz. Uzun sohbetlerin özetlenmesi varsa yerel modelle yapılır. Claude kullanılamıyorsa sohbeti yerel model sürdürür. Yerel modeller dosya okuyamaz ve kod yazamaz; o işler Claude'da kalır.

Kurun ve başlatın:

```bash
brew install ollama && brew services start ollama
```

16 GB RAM için ~4.7 GB'lık bir model indirin:

```bash
ollama pull qwen2.5:7b
```

ORBIT'te **Model Yöneticisi → Kontrol et**'e basın, Ollama "Kullanılabilir" görünmeli.

## Önemli

- claude.ai ve ChatGPT hesap ayarlarında **extra usage / ek kredi** özelliklerini kapalı tutun. Sistem ücretli aşım kullanımını algılarsa çalışmayı durdurur; yine de bu ayarı kapalı tutmak en güvenli yoldur.
- Veriler `data/acc.db` dosyasında, yeni projeler `workspace/projects/` altında tutulur. İkisi de git dışındadır.

## Yapı

```
server/acc/       FastAPI backend
  adapters/       Model sağlayıcıları: Claude Code, Codex, Gemini (Antigravity), Ollama
  assistant.py    Lider asistanın talimatı, araçları ve alt ajanları
  review.py       Bağımsız inceleme ve düzeltme turu
  card.py         Proje Kartı (PROJE.md) ve ekip tablosu
  mcp_codex.py    Claude'dan Codex'e iş veren köprü (MCP)
  tiers.py        Rol başına model seviyesi ve efor (Claude ve Codex karşılıkları)
  orchestra.py    Canlı orkestra: kim, hangi modelle, ne yapıyor, kaç token
  intent.py       Mesaj sohbet mi iş mi (token harcamadan)
  catalog.py      Seçilebilir modeller ve eforlar (sağlayıcıların kendi listelerinden)
  chat.py         Sohbet turu: model seçimi, oturum, çıktılar
  sessions.py     Sohbetteki değişiklikler: kopya, commit, kontroller, birleştirme
  github.py       Değişiklikleri GitHub'a PR olarak gönderme
  cost_guard.py   Ücretli kullanım engelleri
web/src/          React arayüzü
docs/             Mimari kararlar
```
