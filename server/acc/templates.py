"""Ready-made requests for the composer ("/"). Each states the goal, the boundaries and when
it counts as done. [Köşeli parantez] marks a part the user fills in."""

BUILTIN = [
    {
        "id": "b-market",
        "title": "Pazar araştırması",
        "description": "Trendler, rakipler, boşluklar ve net öneri",
        "body": (
            "[Kategori veya fikir] için global bir iOS uygulaması fırsatını kapsamlı araştır: "
            "büyüyen kategoriler, öne çıkan rakipler ve kullanıcıların en çok şikayet ettiği "
            "yanları, düşük rekabetli ama talebi olan nişler. Raporu kaydet; sonunda tek bir net "
            "öneri ve MVP kapsamı ver."
        ),
    },
    {
        "id": "b-competitors",
        "title": "Rakip analizi",
        "description": "Rakipler, fiyatlar ve yorumlardaki şikayetler",
        "body": (
            "[uygulama alanı] alanındaki en güçlü 5-8 rakibi araştır: özellikler, fiyatlandırma, "
            "puanlar ve App Store yorumlarındaki tekrar eden şikayetler. Bizim için farklılaşma "
            "fırsatlarını öner."
        ),
    },
    {
        "id": "b-design",
        "title": "Ekran alternatifleri",
        "description": "Bir ekran için 3 farklı tasarım, yan yana",
        "body": (
            "[ekran, ör. giriş ekranı] için birbirinden farklı 3 tasarım göster. Beğenmediğim "
            "yanı: [ne beğenilmedi]. Hedef his: [ör. sade, premium, eğlenceli]."
        ),
    },
    {
        "id": "b-bug",
        "title": "Hata düzelt",
        "description": "Önce hatayı yakalayan test, sonra düzeltme",
        "body": (
            "Şu hatayı incele ve kök nedenini düzelt:\n\n[hata mesajı veya tekrar üretme adımları]"
            "\n\nÖnce hatayı yakalayan bir test yaz, sonra düzelt. İlgisiz kodu değiştirme."
        ),
    },
    {
        "id": "b-test",
        "title": "Test ekle",
        "description": "Testi olmayan önemli kod yolları için testler",
        "body": (
            "Projede testi olmayan önemli kod yollarını bul ve anlamlı testler yaz. Mevcut test "
            "altyapısını kullan, yeni bağımlılık ekleme, uygulama kodunu değiştirme."
        ),
    },
    {
        "id": "b-security",
        "title": "Güvenlik incelemesi",
        "description": "Rapor; dosya değişmez",
        "body": (
            "Projeyi güvenlik açısından incele: gizli bilgi sızıntısı, injection, yetkisiz erişim, "
            "güvensiz bağımlılık ve yapılandırma. Hiçbir dosyayı değiştirme; bulguları önem "
            "sırasına göre, dosya ve satır belirterek ve düzeltme önerisiyle raporla."
        ),
    },
    {
        "id": "b-readme",
        "title": "README güncelle",
        "description": "Kodla uyumlu, uydurmasız README",
        "body": (
            "README.md'yi mevcut koda göre güncelle: proje ne yapar, kurulum, çalıştırma, test. "
            "Kodda olmayan özellik yazma. Yalnızca README.md'yi değiştir."
        ),
    },
]
