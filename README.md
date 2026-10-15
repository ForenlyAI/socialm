# socialm — Instagram Marketing Analiz Aracı

Meta'nın **resmi Instagram Graph API**'sini kullanarak Instagram'dan pazarlama verisi toplayan, sonuçları
**SQLite**'a kaydedip **CSV** olarak dışa aktaran Python komut satırı aracı.

Resmi API kullanıldığı için hesap engellenme riski yoktur ve Instagram kullanım koşullarına uygundur.
Sınırlama: yalnızca **Business / Creator** hesapları analiz edilebilir; kişisel hesaplar görünmez.

| Komut | Ne yapar | Kullanılan API |
|---|---|---|
| `competitors` | Rakip hesapların takipçi, gönderi, ort. beğeni/yorum, etkileşim oranı, paylaşım sıklığı, en çok kullandığı hashtag'ler | Business Discovery |
| `history` | Bir hesabın zaman içindeki takipçi/etkileşim değişimi (her `competitors` çalıştırması bir anlık görüntü kaydeder) | — (yerel veritabanı) |
| `hashtag` | Bir hashtag'in en popüler / en yeni gönderileri, birlikte kullanılan hashtag'ler, en çok anılan hesaplar | Hashtag Search |
| `influencers` | Aday hesapları takipçi aralığı ve etkileşim oranına göre filtreleyip sıralar; adaylar listeden veya hashtag gönderilerinde @ ile anılan hesaplardan gelir | Business Discovery + Hashtag Search |
| `report` | Kendi hesabınızın erişim, görüntülenme, profil ziyareti, etkileşim metrikleri ve gönderi bazlı insights | Insights |
| `export` | Veritabanındaki tüm tabloları CSV'ye aktarır | — |

## Kurulum

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # ardından değerleri doldurun
```

### Meta / Instagram erişimi

1. Instagram hesabınızı **Business** (veya Creator) hesabına çevirin ve bir **Facebook Sayfası**'na bağlayın.
2. [developers.facebook.com](https://developers.facebook.com) üzerinde **Business** türünde bir uygulama oluşturun ve
   *Instagram API with Facebook Login* ürününü ekleyin.
   (Not: *Instagram Login* varyantı Business Discovery ve Hashtag Search'ü desteklemez.)
3. Graph API Explorer'dan şu izinlerle bir kullanıcı token'ı alın:
   `instagram_basic`, `instagram_manage_insights`, `pages_show_list`, `pages_read_engagement`, `business_management`.
   Hashtag araması için uygulamanızın **Instagram Public Content Access** özelliğine sahip olması gerekir
   (geliştirme modunda uygulama rolü olan kullanıcılarla test edilebilir; canlıda App Review gerekir).
4. Kısa ömürlü token'ı **uzun ömürlü (60 gün)** token'a çevirin:
   ```
   GET https://graph.facebook.com/v23.0/oauth/access_token?grant_type=fb_exchange_token
       &client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=KISA_TOKEN
   ```
5. Instagram Business hesap ID'nizi bulun:
   ```
   GET https://graph.facebook.com/v23.0/me/accounts?fields=name,instagram_business_account&access_token=TOKEN
   ```
   `instagram_business_account.id` değerini `.env` içindeki `IG_USER_ID`'ye yazın.

## Kullanım

```bash
# Rakip analizi (her hesap için son 25 gönderi)
socialm competitors nike adidas puma --csv exports/rakipler.csv
socialm competitors -f rakipler.txt --media-limit 50

# Rakibin zaman içindeki büyümesi (competitors'ı düzenli çalıştırdıkça dolar)
socialm history nike

# Hashtag & trend analizi
socialm hashtag kahve istanbulkahve --kind top
socialm hashtag kahve --kind recent --limit 100 --csv exports/kahve.csv

# Influencer keşfi: hashtag'lerde anılan hesaplardan aday topla, 10K–500K takipçi, en az %2 etkileşim
socialm influencers --from-hashtag kahve --from-hashtag baristalife \
    --min-followers 10000 --max-followers 500000 --min-engagement 2 --csv exports/influencer.csv
socialm influencers -f adaylar.txt -v

# Kendi hesap raporunuz (son 28 gün)
socialm report --days 28 --csv exports/gonderiler.csv

# Tüm verileri CSV'ye aktar
socialm export --out exports
```

Kurulum yapmadan çalıştırmak için: `PYTHONPATH=src python3 -m socialm ...`

### Metrikler

- **Etkileşim oranı** = (beğeni + yorum) / takipçi × 100, analiz edilen gönderilerin ortalaması.
  Beğeni sayısını gizleyen gönderiler bu ortalamaya dahil edilmez.
- **Gönderi/hafta** = analiz edilen gönderi sayısı / ilk ile son gönderi arasındaki hafta sayısı.

## API limitleri

- **Hashtag Search:** bir Instagram hesabı **7 günde en fazla 30 farklı hashtag** sorgulayabilir.
  Araç hashtag ID'lerini veritabanında önbelleğe alır; aynı hashtag'i tekrar sorgulamak limiti harcamaz.
  `recent` yalnızca son 24 saatin gönderilerini döndürür. Hashtag gönderilerinde kullanıcı adı dönmez,
  bu yüzden influencer adayları açıklamalardaki @ etiketlerinden çıkarılır.
- **Business Discovery:** yalnızca Business/Creator hesaplarını görür; kişisel ve gizli hesaplar hata verir
  (`influencers` bunları "erişilemeyen" olarak raporlar).
- **Rate limit:** istemci, limit hatalarında (kod 4, 17, 32, 613, 80002) ve geçici sunucu hatalarında
  üstel bekleme ile otomatik olarak tekrar dener.
- **Insights:** hesap metrikleri en fazla 30 günlük aralık için alınabilir. Hesabınızda veya API sürümünüzde
  desteklenmeyen metrikler atlanır ve `-` olarak gösterilir.

## Geliştirme

```bash
pytest
```

Kod yapısı (`src/socialm/`):

- `client.py` — Graph API HTTP istemcisi (hata ayrıştırma, tekrar deneme, sayfalama)
- `instagram.py` — Business Discovery, Hashtag Search ve Insights uç noktaları
- `metrics.py` — etkileşim oranı, paylaşım sıklığı, hashtag/mention çıkarımı
- `analysis.py` — analiz akışları (API + metrik + kayıt)
- `storage.py` — SQLite şeması ve CSV dışa aktarma
- `cli.py` — komut satırı arayüzü
