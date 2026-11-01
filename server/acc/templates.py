"""Ready-made requests. Each states the goal, the boundaries and when it counts as done —
the three things that make an agent's output reviewable. [Köşeli parantez] marks a part
the user fills in."""

BUILTIN = [
    {
        "id": "b-market",
        "title": "Pazar araştırması",
        "mode": "research",
        "description": "Trendler, rakipler, boşluklar ve net öneri",
        "body": (
            "[Kategori veya fikir; boş bırakılırsa genel] için global bir iOS uygulaması "
            "fırsatı araştır: büyüyen kategoriler, öne çıkan rakipler ve kullanıcıların en çok "
            "şikayet ettiği yanları, düşük rekabetli ama talebi olan nişler. Sonunda tek bir "
            "net öneri ve MVP kapsamı ver."
        ),
    },
    {
        "id": "b-competitors",
        "title": "Rakip analizi",
        "mode": "research",
        "description": "Belirli bir alandaki rakipler ve şikayetler",
        "body": (
            "[uygulama alanı] alanındaki en güçlü 5-8 rakibi incele: özellikler, fiyatlandırma, "
            "puanlar ve App Store yorumlarındaki tekrar eden şikayetler. Bizim için farklılaşma "
            "fırsatlarını öner."
        ),
    },
    {
        "id": "b-test",
        "title": "Test ekle",
        "mode": "task",
        "description": "Testi olmayan önemli kod yolları için testler",
        "body": (
            "Projede testi olmayan önemli kod yollarını bul ve bunlar için anlamlı testler yaz. "
            "Mevcut test altyapısını ve stilini kullan; yeni bağımlılık ekleme. Uygulama kodunu "
            "değiştirme, yalnızca test ekle.\nBitti ölçütü: yeni ve mevcut testlerin hepsi geçiyor."
        ),
    },
    {
        "id": "b-bug",
        "title": "Hata düzelt",
        "mode": "task",
        "description": "Önce hatayı yakalayan test, sonra düzeltme",
        "body": (
            "Şu hatayı incele ve kök nedenini düzelt:\n\n[hata mesajı veya tekrar üretme adımları]"
            "\n\nÖnce hatayı yakalayan bir test yaz, sonra düzelt. İlgisiz kodu değiştirme.\n"
            "Bitti ölçütü: yeni test ve mevcut testler geçiyor."
        ),
    },
    {
        "id": "b-security",
        "title": "Güvenlik incelemesi",
        "mode": "task",
        "description": "Rapor; dosya değişmez",
        "body": (
            "Projeyi güvenlik açısından incele: gizli bilgi sızıntısı, injection, yetkisiz erişim, "
            "güvensiz bağımlılık ve yapılandırma. Dosya değiştirme. Bulguları önem sırasına göre, "
            "dosya ve satır belirterek, her biri için somut bir düzeltme önerisiyle raporla."
        ),
    },
    {
        "id": "b-review",
        "title": "Kod incelemesi",
        "mode": "task",
        "description": "Son commitlerin incelenmesi; rapor",
        "body": (
            "Son commitlerdeki değişiklikleri incele: hatalar, gereksiz karmaşıklık, tekrar eden "
            "kod, eksik hata yönetimi, performans sorunları. Dosya değiştirme; bulguları dosya ve "
            "satır belirterek raporla, en önemlisinden başla."
        ),
    },
    {
        "id": "b-readme",
        "title": "README güncelle",
        "mode": "task",
        "description": "Kodla uyumlu, uydurmasız README",
        "body": (
            "README.md'yi mevcut koda göre güncelle: proje ne yapar, kurulum, çalıştırma, test. "
            "Kodda olmayan özellik yazma. Yalnızca README.md'yi değiştir."
        ),
    },
    {
        "id": "b-deps",
        "title": "Bağımlılık kontrolü",
        "mode": "task",
        "description": "Eski veya riskli bağımlılıklar; rapor",
        "body": (
            "Projenin bağımlılıklarını incele: kullanılmayan, çok eski veya bilinen riskleri olan "
            "paketleri listele. Dosya değiştirme; her biri için öneri ve riskini yaz."
        ),
    },
    {
        "id": "b-idea",
        "title": "Fikri netleştir",
        "mode": "chat",
        "description": "Sohbetle kapsam ve MVP çıkar",
        "body": (
            "Aklımda bir özellik var: [kısaca anlat]. Bunu birlikte netleştirelim: kapsamı, "
            "kullanıcı akışını, veri modelini ve riskleri sor; sonunda kısa bir MVP tanımı çıkar."
        ),
    },
    {
        "id": "b-explain",
        "title": "Projeyi anlat",
        "mode": "chat",
        "description": "Mimari, veri akışı, önemli dosyalar",
        "body": (
            "Bu projenin mimarisini anlat: ana bileşenler, veri akışı ve önemli dosyalar. "
            "Kısa tut ve sonunda en değerli üç iyileştirme önerisini ver."
        ),
    },
]
