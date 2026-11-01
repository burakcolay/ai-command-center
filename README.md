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

Yazma kutusunda beş mod vardır: **Sohbet**, **Araştırma**, **Tasarım**, **Düzenle** ve **Görev**.

- **Tasarım:** "Bu ekranı beğenmedim, 3 alternatif" gibi istekler için.
  - Birbirinden gerçekten farklı 2-3 ekran çizilir ve görselleri yan yana gösterilir.
  - "2'nin düzeni, 1'in renkleri" gibi yeni turlar istenebilir.
  - **Bunu uygula**, seçilen tasarımı referans olarak Düzenle moduna aktarır.
  - Tasarımlar internet erişimi ve JavaScript kapalı bir tarayıcıda çizilir.
- **Görsel ekleme:** Ataç butonu, yapıştırma (⌘V) veya sürükle-bırak ile ekran görüntüsü eklenebilir; her modda Claude görseli okur.

- **Düzenle:** Küçük değişiklikler için. Plan ve onay adımı yoktur; her mesaj projenin izole bir kopyasında hemen uygulanır, kalite kontrolleri çalışır ve diff önüne gelir. Mesaj yazdıkça aynı oturuma yeni adımlar eklenir. **Son değişikliği geri al**, **Birleştir** ve **Hepsini at** butonları vardır.

- **Araştırma:** Bir pazar, rakip ya da teknoloji sorusu için onlarca kaynağı tarar ve rakamları karşılaştırır. Kaynakçalı bir rapor yazar: rakip tablosu, fırsatlar, net öneri ve MVP. Rapor `Araştırmalar/` klasörüne markdown olarak kaydedilir. Birkaç dakika sürer.
- **Model ve düşünme:** **Ayarlar**'dan kalite (Ekonomik / Dengeli / En iyi) ve model (Varsayılan / Sonnet / Opus / Fable) seçilir. Daha yüksek kalite daha derin düşünür ama kotayı daha hızlı harcar.

1. **Sohbet modunda konuşun.** Fikrinizi anlatın, soru sorun, seçenekleri tartışın. Proje seçtiyseniz asistan kodunuzu okuyarak konuşur. Bu modda hiçbir dosya değişmez.
2. **Karar netleşince "Göreve dönüştür"e basın.** Orchestrator tüm konuşmayı okuyup bir plan çıkarır. Planı onaylar, değiştirtir ya da reddedersiniz.
3. **Ajanlar izole bir kopyada çalışır.** Bitince diff'i inceler, **Birleştir**, **Değişiklik iste** veya **Reddet** seçersiniz.

Kısa ve net işler için doğrudan **Görev** moduna geçip yazabilirsiniz. İyi bir görev tarifi şunları içerir:
- ne istendiği,
- kapsamın sınırı (ne yapılmayacağı),
- "bitti" sayılma ölçütü, örneğin "testler geçsin".

## İş dağılımı (model yönlendirici)

Her iş bir türe ayrılır: planlama, sohbet, araştırma, tasarım, kod yazma, inceleme/test ve özetleme. Her türün varsayılan bir model sırası vardır.

**Seçim kuralları:**
- Gereken yeteneği olmayan model atlanır; örneğin yerel model asla kod yazmaz.
- Sağlıksız, kotası dolmuş veya ücretli API gerektiren model atlanır.
- Kotası %90'ı geçmiş bir model, uygun alternatif varsa yükü ona devreder.
- İnceleme işleri, kodu yazan modelden farklı bir modele gider (ikinci göz).

**Bugünkü dağılım ve Codex:** Bugün özetleme yerel modelde, diğer her şey Claude'da. Codex eklendiğinde ayar gerekmeden inceleme işlerini almaya başlar.

**Elle müdahale:** **Model Yöneticisi → İş dağılımı**'nda her iş türü için o an seçilen model ve nedeni görünür; istersen elle sabitleyebilirsin. Her görev adımında hangi modelin çalıştığı da yazar.

## Kalite kontrolleri

Ajanlar işini bitirince ORBIT projenizin test, lint ve tip kontrolü komutlarını **kendisi** çalıştırır ve sonucu diff'in yanında gösterir. Böylece "testler geçti" bilgisi bir modelin iddiası değil, ölçülmüş bir sonuç olur.
- **Komut seçimi:** npm, Python (uv veya requirements) ve Makefile projelerinde komutlar otomatik algılanır. **Projeler → Kontroller**'den değiştirilebilir.
- **Sandbox:** Komutlar `sandbox-runtime` içinde çalışır; yalnızca görevin kopyasına yazabilir ve internete yalnızca paket depoları üzerinden çıkabilir. Sandbox kurulu değilse komutlar hiç çalıştırılmaz.
- **Başarısız kontrol:** **Ajana düzelttir** hata çıktısıyla bir düzeltme adımı ekler. **Yeniden çalıştır** ajan çalıştırmadan kontrolleri tekrarlar.

## Kota, bildirimler, şablonlar

- **Kota dolunca:** Görev hata vermez, "Kota bekleniyor" durumuna geçer ve kota sıfırlandığında kendiliğinden devam eder. İsterseniz **Şimdi dene** ile hemen deneyebilirsiniz. Ücretli kullanıma hiçbir durumda geçilmez.
- **Bildirimler:** Plan hazır, inceleme hazır, kota doldu veya görev başarısız olduğunda macOS bildirimi gelir. **Ayarlar**'dan kapatılıp test edilebilir.
- **Şablonlar:** Yazma kutusundaki şablon butonu ya da kutunun başına `/` yazmak hazır istekleri açar (test ekle, hata düzelt, güvenlik incelemesi …). Yazdığınız bir metni şablon olarak kaydedebilirsiniz.

## Güvenlik

- **Ağ:** Sunucu yalnızca `127.0.0.1`'de dinler. Başka sitelerden gelen istekler (CSRF) ve sahte host adları (DNS rebinding) reddedilir.
- **Gizli dosyalar:** Ajanlar `.env`, `*.pem`, `*.key`, `*.p8` gibi dosyaları okuyamaz. Komut çalıştıranlar `~/.ssh`, `~/.aws`, `~/.claude` gibi klasörleri ve ORBIT'in kendi veritabanını göremez.
- **Repo ayarları:** Repo içindeki `.claude/settings.json` dikkate alınmaz; bir repo kendi hook'larıyla komut çalıştıramaz.
- **Loglar:** Token, anahtar ve şifre benzeri değerler kaydedilmeden önce `[gizli]` olarak maskelenir. `data/` klasörü yalnızca sizin kullanıcınız tarafından okunabilir.
- **Git:** Veritabanı, loglar, hafıza ve çalışma kopyaları `.gitignore`'dadır; GitHub'a gitmez.

## Proje Hafızası

Her projenin, ORBIT'in her sohbete, plana ve ajana verdiği bir hafıza dosyası vardır. Açmak için **Projeler → Hafıza**.
- **Notlar:** Kalıcı kararları buraya yazın, örneğin "arayüz Türkçe", "SwiftUI kullan", "yeni bağımlılık ekleme".
- **Karar Günlüğü:** Birleştirilen her görev buraya otomatik olarak eklenir.

Dosyalar düz markdown'dır. Obsidian kullanıyorsanız klasörü kasanızın içine taşıyıp notları orada görebilir ve bağlayabilirsiniz:

```bash
make start MEMORY_DIR=~/Documents/Obsidian/Orbit
```

## Yerel modeller (Ollama, isteğe bağlı)

Ücretsizdir ve kota harcamaz. Sohbette model seçiciden **Yerel** seçilebilir. Uzun sohbetlerin özetlenmesi de varsa yerel modelle yapılır. Yerel modeller dosya okuyamaz ve kod yazamaz; o işler Claude'da kalır.

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
  orchestrator.py Plan üretimi ve onay durum makinesi
  cost_guard.py   Ücretli kullanım engelleri
  agents.py       Uzman ajan tanımları
web/src/          React arayüzü
docs/             Mimari kararlar
```
