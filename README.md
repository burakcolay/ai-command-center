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

**Tasarımı uygulama:** Bir tasarımın altındaki **Bunu uygula** butonu, o tasarımı (görsel ve HTML) ekleyerek mesajı hazırlar. Siz gönderirsiniz. Tasarımlar internet erişimi ve JavaScript kapalı bir tarayıcıda çizilir.

**Görsel ekleme:** Ataç butonu, yapıştırma (⌘V) veya sürükle-bırak ile ekran görüntüsü eklenebilir. Asistan görseli okur.

**Hafıza:** Asistan aynı sohbetteki konuşmayı hatırlar. Çok uzun sohbetlerin eski kısımları özetlenir; özetleme varsa ücretsiz yerel modelle yapılır.

**Model ve düşünme:** **Ayarlar**'dan kalite (Ekonomik / Dengeli / En iyi) ve model (Varsayılan / Sonnet / Opus / Fable) seçilir. Daha yüksek kalite daha derin düşünür ama kotayı daha hızlı harcar.

## Model seçimi

Asistan Claude Code ile çalışır. **Model Yöneticisi → İş dağılımı**'nda o an hangi modelin çalıştığı ve nedeni görünür. Model elle de sabitlenebilir.

**Seçim kuralları:**
- Sağlıksız, kotası dolmuş veya ücretli API gerektiren model atlanır.
- Claude'un kotası %90'ı geçerse ve başka bir abonelik modeli (ör. Codex) eklenmişse iş ona geçer.
- Claude hiç kullanılamıyorsa yerel model (Ollama) sohbeti sürdürür. Yerel model dosya okuyamaz ve değişiklik yapamaz.

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
- **Gizli dosyalar:** Asistan `.env`, `*.pem`, `*.key`, `*.p8` gibi dosyaları okuyamaz. Çalıştırdığı komutlar sandbox içindedir; `~/.ssh`, `~/.aws`, `~/.claude` gibi klasörleri ve ORBIT'in kendi veritabanını göremez, projenin kopyası dışına yazamaz.
- **Repo ayarları:** Repo içindeki `.claude/settings.json` dikkate alınmaz; bir repo kendi hook'larıyla komut çalıştıramaz.
- **Loglar:** Token, anahtar ve şifre benzeri değerler kaydedilmeden önce `[gizli]` olarak maskelenir. `data/` klasörü yalnızca sizin kullanıcınız tarafından okunabilir.
- **Git:** Veritabanı, loglar, hafıza ve çalışma kopyaları `.gitignore`'dadır; GitHub'a gitmez.

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
  adapters/       Model sağlayıcıları (her biri ayrı modül)
  assistant.py    Tek asistanın talimatı ve araçları
  chat.py         Sohbet turu: model seçimi, oturum, çıktılar
  sessions.py     Sohbetteki değişiklikler: kopya, commit, kontroller, birleştirme
  cost_guard.py   Ücretli kullanım engelleri
web/src/          React arayüzü
docs/             Mimari kararlar
```
