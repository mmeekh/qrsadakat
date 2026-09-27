# Cheabby — QR sadakat (v1 → v2 → v3)

Mahalle işletmeleri için uygulama indirmeden dijital sadakat kartı. İşletme kasada
dakikada yenilenen QR'ı gösterir, müşteri kendi telefonuyla okutur, damga anında
işlenir; hedef dolunca ödül açılır. Müşteri ve işletme **yalnız Google hesabıyla**
girer. Harita, Cheabby geçen bütün işletmeleri gösterir.

Depo: `git@github.com:mmeekh/qrsadakat.git`. 25-26 Eyl 2026'da Codex ile "Mahalle Kartı"
adıyla başladı (jobfind deposunda izlenmeyen `loyalty_v1/` klasörü), 27 Eyl 2026'da
Claude'a devredildi ve Cheabby adını aldı. Görsel tema demo içindir, değişecek.

## Akış

1. İşletme sahibi Google ile girer; işletme adı, kategori, ödül, damga hedefi ve
   haritadaki yerini (adres araması, "konumumu kullan" veya haritaya dokunma) girer.
2. **QR** sekmesi kategoriye göre temalı kasa QR'ını gösterir (kafe → kahve fincanı,
   fırın → ekmek, berber → berber direği...). Kod her dakika yenilenir, ekran açık kalır.
3. Müşteri QR'ı okutur; damga **girişsiz** hemen işlenir (misafir kartı). Hemen ardından
   "Google ile kaydet" önerisi çıkar. Misafir kuralları:
   - Damga sunucuda tutulur; telefonda yalnız rastgele bir anahtar çerezi (`loyalty_customer`,
     HttpOnly, 1 yıl) vardır. Değiştirilen ya da uydurulan çerez yeni boş misafir olur.
   - Girişsiz yalnız **bir işletme**. İkinci işletmede Google girişi istenir; QR o anda
     doğrulanıp 10 dakika tutulur, Google'dan dönünce damga işlenir.
   - **Ödül kullanmak** Google girişi ister.
   - Girişte misafir kartı hesaba taşınır. Hesapta o işletmenin kartı zaten varsa iki
     kart **toplanmaz** (gizli sekmeyle damga çoğaltmaya karşı).
   - Çerez silinir ya da QR okuyucu uygulama kendi tarayıcısında açarsa kaydedilmemiş
     misafir kartı kaybolur; ödülün girişe bağlı olmasının nedeni bu.
4. Hedef dolunca müşteri "Ödülümü kullan" der, işletme panelde teslimi onaylar.
5. **Harita** sekmesi bütün işletmeleri, müşterinin her birindeki damga durumunu ve
   Google Haritalar yol tarifi bağlantısını gösterir.

Alt sekme çubuğu: işletme için QR · Panel · Harita · Kartlarım · Hesap; müşteri için
Harita · Kartlarım · Hesap; kartı olan misafir için Harita · Kartlarım · Giriş; ilk kez
gelen için Keşfet · Harita · Giriş.

## Mimari

Ek paket yok (Python standart kitaplığı + SQLite; tarayıcıda derleme adımı yok).
Her alan kendi dosyasında; hiçbir dosya ~250 satırı geçmez.

```
cheabby/                 sunucu (python -m cheabby)
  config.py              ortam ayarları (CHEABBY_*, GOOGLE_*)
  web.py                 ince HTTP katmanı: Router, Request, Response, statik dosya, CSP
  db.py                  SQLite + numaralı göçler (PRAGMA user_version)
  accounts.py            kullanıcı, oturum, müşteri kaydı
  auth.py                Google girişi (authorization code + PKCE), /api/me
  merchants.py           işletme profili ve harita iğnesi
  loyalty.py             kasa QR'ı, damga, ödül, işletme paneli
  places.py              harita listesi, adres araması (Nominatim)
  demo.py                demo işletmeler (CHEABBY_DEMO_MODE=1)
  app.py                 modülleri birleştirir (FEATURES)
static/
  index.html, styles.css, app.css
  js/main.js             açılış; js/nav.js görünüm değiştirme + alt sekme çubuğu
  js/api.js, state.js, ui.js, map-kit.js, qr-themes.js
  js/views/*.js          her ekran bir modül (home, card, map, cards, account, setup, merchant)
  vendor/                qrcode.min.js (QR-LICENSE), leaflet 1.9.4 (BSD-2)
tests/                   gerçek sunucu + sahte Google token uç noktası
deploy/                  Dockerfile, compose, Caddy, DuckDNS, test-in-image.sh
```

**Yeni özellik eklemek (v2 vitrin, v3 sipariş...):** `cheabby/<alan>.py` içinde
`routes = Router()` ile uç noktalar, `app.py`'deki `FEATURES`'a ekleme, şema
gerekiyorsa `db.py`'de yeni `m00N_...` göçü (eskiye dokunulmaz), arayüzde
`static/js/views/<ekran>.js` + `defineView()`, ve `tests/test_<alan>.py`.
Tek yerde toplanan kurallar: oturum `accounts.require_user`, işletme yetkisi
`merchants.require_merchant`, yazma işlemleri `db.write()` bloğunda.

## Çalıştır ve doğrula

```bash
cd /root/projects/qrsadakat
CHEABBY_DEMO_MODE=1 python3 -m cheabby          # http://127.0.0.1:8088
python3 -m unittest discover -s tests -t .      # hızlı, host Python'uyla
./deploy/test-in-image.sh                       # asıl kontrol: canlı imajın Python/SQLite'ı
```

Host'taki SQLite (3.34) canlı imajdakinden (3.46) eski; yeni SQLite'ta ayrılmış
kelimeler farklı. Deploy öncesi `test-in-image.sh` şart.

Ortam: `CHEABBY_DB`, `CHEABBY_HOST`, `CHEABBY_PORT`, `CHEABBY_PUBLIC_URL`
(Google redirect adresi bundan kurulur), `CHEABBY_DEMO_MODE`, `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`. Google anahtarları yoksa giriş kapalıdır, demo çalışır.

## Google girişi kurulumu (bir kez)

1. Google Cloud Console → yeni proje (ör. "Cheabby") → **OAuth consent screen**:
   External, uygulama adı Cheabby, kapsamlar yalnız `openid`, `email`, `profile`
   (hassas kapsam yok, Google doğrulaması gerekmez).
2. **Credentials → OAuth client ID → Web application**, Authorized redirect URI:
   `https://qrsadakat.duckdns.org/auth/google/callback`
3. `/root/secrets/qrsadakat-google.env` (0600):
   ```
   GOOGLE_CLIENT_ID=...apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=...
   ```
   compose bu dosyayı okur; dosya yoksa giriş kapalı kalır.

Güvenlik: `state` tek kullanımlık ve tarayıcı çerezine bağlı, PKCE S256, `nonce`,
`aud`/`iss`/`exp`/`email_verified` denetlenir; ID token Google'ın token uç noktasından
TLS ile doğrudan geldiği için imza ayrıca doğrulanmaz (OIDC Core 3.1.3.7). Oturum
ve eski müşteri çerezlerinin veritabanında yalnız SHA-256 özeti tutulur; geri dönüş
adresindeki kod loglara yazılmaz.

İlk pilottan geçiş: e-posta/şifreyle açılmış işletme, sahibi aynı e-postayla Google'dan
girince hesabına bağlanır. Eski tarayıcı çerezli müşteri kartı, o tarayıcıdan Google'la
girilince hesaba taşınır.

## Canlı ortam

`https://qrsadakat.duckdns.org` — Caddy (`/root/caddy/sites/qrsadakat.duckdns.org.Caddyfile`)
`qrsadakat-app:8088` konteynerine yönlendirir ve şimdilik **tüm siteye** Basic Auth
uygular (kullanıcı `admin`; depodaki [`deploy/Caddyfile`](deploy/Caddyfile) parola
özeti yerine yer tutucu taşır). Bu koruma açıkken müşteriler de QR sonrası parola
penceresi görür; gerçek müşteriyle denemeden önce kaldırılmalı.

DuckDNS anahtarı `/root/secrets/qrsadakat-duckdns-token`; `qrsadakat-duckdns.timer`
beş dakikada bir `deploy/update_duckdns.py` çalıştırır. Veri `qrsadakat_qrsadakat_data`
biriminde (`/data/pilot.sqlite3`); göçler açılışta kendiliğinden çalışır.

```bash
./deploy/test-in-image.sh
docker compose -f deploy/compose.yml build app
docker compose -f deploy/compose.yml up -d app
```

## Temalı QR

`static/js/qr-themes.js`, `qrcode.min.js`'in modül ızgarasını alıp SVG'yi kendisi
çizer. Okunabilirlik kuralı: kodun karesi açık zeminde koyu modül, 4 modül sessiz
bölge, üç konum işareti sağlam; tema resmi (fincan, tabak, ekmek, poşet, berber
direği) karenin **dışında**. İçeride yalnız modül biçimi, renk ve konum işaretlerinin
şekli değişir (kafe: kahve çekirdeği). Hata düzeltme Q. 27 Eyl 2026'da altı tema da
zxing-cpp ile 788, 394 ve 275 piksel genişlikte çözüldü (18/18). Yeni tema ekleyince
aynı denetimi tekrarla.

## Yol haritası: v1 → v2 → v3

Kaynak: "QR Sadakatten Tam Ticarete" sunumu (8 slayt,
`lingering-surf-b93c.reymisteryo3393.workers.dev`, Cloudflare Access arkasında).
Her sürüm bir öncekinin üzerine eklenir.

### v1 · QR Sadakat + Harita (ilk açılış)

| Sunumdaki madde | Durum |
|---|---|
| İşletme kaydı, kart ve ödül tanımı (N damga → ödül) | ✅ |
| Süreli kasa QR'ı (dakikada yenilenir), müşteri kendi telefonuyla okutur | ✅ |
| Otomatik damga + animasyon, ödül teslimi işletme onayıyla | ✅ |
| Panel: damga alan müşteri, tekrar gelen müşteri, müşteri adı (Elif K.) | ✅ |
| Google ile giriş (müşteri + işletme), kart hesaba bağlı, cihazlar arası | ✅ kod canlıda, Google anahtarı bekleniyor |
| Girişsiz ilk damga (misafir kartı, sonra Google ile kaydet) | ✅ |
| Haritada Cheabby geçen yerler, damga durumum, yol tarifi | ✅ |
| Kategoriye göre temalı QR | ✅ |
| Mobil öncelikli arayüz, alt sekme çubuğu | ✅ |
| Tek tıkla demo (Nora Café + haritada 3 demo yer) | ✅ (`CHEABBY_DEMO_MODE=1`) |
| Puan ve para iadesi (şimdilik yalnız damga) | ⏳ |
| Kısa süreli anlık kampanyalar (ör. "18:00'e kadar 2 kat puan") | ⏳ |
| Kartın telefon cüzdanına eklenmesi (Apple / Google Wallet) | ⏳ |
| Yapay zekâ ile otomatik kurulum (ad/adres/foto → profil + ilk kampanya) | ⏳ |

Başarı ölçütü: 10–20 işletmelik pilotta müşterilerin kartı **ikinci kez**
kullanıp kullanmadığı (panelde "tekrar gelen").

### v2 · Yerel Market (sonraki adım)

Sadakat kartının üzerine satış vitrini. Görünürlük reklam bütçesine değil, yakınlık
ve sadakate göre.

- İşletme vitrini: ürün / hizmet / menü gösterimi
- Kategoriye göre keşif
- Rezervasyon ve ön sipariş
- Müşteri yorumları
- Müşteriye özel öneriler
- Gelişmiş işletme paneli
- Ücretli öne çıkarma (isteğe bağlı, zorunlu değil)

### v3 · Tam Ticaret Altyapısı (uzun vadeli hedef)

Vitrinin üzerine sepet, ödeme ve teslimat; işletme pazaryerine ihtiyaç duymadan satar.

- Sepet ve sipariş sistemi
- İnternetten ödeme
- Gel-al ve teslimat
- İşletmeye özel internet mağazası
- Müşteri yönetimi ve gruplama
- Gelişmiş sadakat ve üyelik
- Otomatik kampanyalar
- Yapay zekâ ile büyüme önerileri
- Çok şubeli işletme yönetimi
- Detaylı raporlama

**v3 sonrası (sunumdaki projeksiyon):** yerel kurye ağı, düşük ve şeffaf komisyon,
yerli ticaret altyapısı.

## Bilinen sınırlar

- Ekrandaki güncel QR'ın fotoğrafı ~90 saniye içinde paylaşılırsa başkası da damga
  alabilir (aynı karta saatte bir damga sınırı var); fiziksel alışveriş doğrulaması yok.
- Harita karoları OpenStreetMap'in ücretsiz sunucusundan gelir; trafik büyüyünce
  ücretli bir karo sağlayıcısına geçilmeli (OSM kullanım politikası).
- Adres araması Nominatim'e saniyede en çok bir istek atar (yalnız girişli kullanıcı).
- Demo modu açıkken demo yerleri haritada görünür; lansmanda `CHEABBY_DEMO_MODE=0`.
