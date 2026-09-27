# bikıyak — QR sadakat (v1 → v2 → v3)

Mahalle işletmeleri için uygulama indirmeden dijital sadakat kartı. İşletme kasada
dakikada yenilenen QR'ı gösterir, müşteri kendi telefonuyla okutur, damga anında
işlenir; hedef dolunca ödül açılır. Müşteri ve işletme **yalnız Google hesabıyla**
girer. Harita, bikıyak geçen bütün işletmeleri gösterir.

Depo: `git@github.com:mmeekh/qrsadakat.git`. 25-26 Eyl 2026'da Codex ile "Mahalle Kartı"
adıyla başladı (jobfind deposunda izlenmeyen `loyalty_v1/` klasörü), 27 Eyl 2026'da
Claude'a devredildi; aynı gün önce "Cheabby", sonra **bikıyak** adını aldı (alan adı
`bikıyak.com`, teknik adı `xn--bikyak-r9a.com`).

## Akış

1. **Sitede herkes müşteri olarak başlar; işletmeleri operatör ekler** (27 Eyl 2026 kararı). Sitede
   "işletme aç" girişi yok. İşletme şöyle eklenir; sahibi o e-postayla Google'dan ilk girdiğinde
   işletme paneline düşer (daha önce müşteri olarak girmişse hemen bağlanır):
   ```bash
   docker exec qrsadakat-app python -m bikiyak.admin add-merchant isletme@gmail.com "Nora Café" Kafe "Moda Cd. 12, Kadıköy/İstanbul"
   docker exec qrsadakat-app python -m bikiyak.admin add-merchant isletme@gmail.com "Nora Café" Kafe "Moda" 40.9837 29.0268
   docker exec qrsadakat-app python -m bikiyak.admin merchants    # kim girdi, kaç aktif kartı var
   ```
   Koordinat verilmezse adres OpenStreetMap'te aranır; iğneyi sahibi sonra "İşletme bilgileri"nden
   düzeltir. Kategori: Kafe, Restoran, Fırın & pastane, Market, Berber & kuaför, Diğer.
   `BIKIYAK_OPEN_SIGNUP=1` sitede kendi işletmesini açmayı yeniden açar. (Aynı gün denenen davet
   akışı bunun yerine geçti; `merchant_invites` tablosu duruyor ama okunmuyor.)
2. **Kartlar (programlar):** bir işletme en fazla **5 aktif** kart çalıştırır (ör. kahve
   kartı + tatlı kartı). Her kartın damga hedefi (2–20, sonradan değişmez) ve ödülü var:
   **bedava ürün** ("6 damga topla, 1 kahve bedava"), **yüzde indirim** (%5–100),
   **tutar indirimi** (1–10.000 ₺) ya da **kendi metni**. Kart metnini sunucu kurar
   (`programs.reward_title`). Kart silinmez, **arşivlenir**: yeni damga vermez, kazanılmış
   ödüller yine teslim edilir.
3. İşletme **Kartlarım**'da bir karta dokununca o kartın kasa QR'ı tam ekran açılır
   ("← Kartlarım" ile döner). QR kategoriye göre temalıdır (kafe → kahve fincanı, fırın →
   ekmek, berber → berber direği...), her dakika yenilenir, açıkken ekran kararmaz.
   Damga, okutulan QR'ın kartına işlenir.
4. Müşteri QR'ı okutur; damga **girişsiz** hemen işlenir (misafir kartı). Hemen ardından
   "Google ile kaydet" önerisi çıkar. Misafir kuralları:
   - Damga sunucuda tutulur; telefonda yalnız rastgele bir anahtar çerezi (`loyalty_customer`,
     HttpOnly, 1 yıl) vardır. Değiştirilen ya da uydurulan çerez yeni boş misafir olur.
   - Girişsiz yalnız **bir işletme** (o işletmenin birden çok kartı olabilir). İkinci işletmede Google girişi istenir; QR o anda
     doğrulanıp 10 dakika tutulur, Google'dan dönünce damga işlenir.
   - **Ödül kullanmak** Google girişi ister.
   - Girişte misafir kartı hesaba taşınır. Hesapta o işletmenin kartı zaten varsa iki
     kart **toplanmaz** (gizli sekmeyle damga çoğaltmaya karşı).
   - Çerez silinir ya da QR okuyucu uygulama kendi tarayıcısında açarsa kaydedilmemiş
     misafir kartı kaybolur; ödülün girişe bağlı olmasının nedeni bu.
5. Hedef dolunca müşteri "Ödülümü kullan" der, işletme panelde teslimi onaylar
   (panel hangi kartın ödülü olduğunu, "Verilecek: …" diye yazar).
6. **Harita** ilk açılışta bir kez konum ister ve kullanıcının çevresinde açılır (izin yoksa
   İstanbul, şehir ölçeği). Sağ alttaki yuvarlak düğme konuma döner. Harita bütün işletmeleri, her birinin aktif kartlarını, müşterinin her karttaki
   damga durumunu ve Google Haritalar yol tarifi bağlantısını gösterir.

Alt sekme çubuğu: işletme için Kartlarım · Panel · Harita · Hesap (işletme sahibinin kendi
müşteri kartları Hesap altında); müşteri için
Harita · Kartlarım · Hesap; kartı olan misafir için Harita · Kartlarım · Giriş; ilk kez
gelen için Keşfet · Harita · Giriş.

## Mimari

Ek paket yok (Python standart kitaplığı + SQLite; tarayıcıda derleme adımı yok).
Her alan kendi dosyasında; hiçbir dosya ~250 satırı geçmez.

```
bikiyak/                 sunucu (python -m bikiyak)
  config.py              ortam ayarları (BIKIYAK_*, GOOGLE_*)
  web.py                 ince HTTP katmanı: Router, Request, Response, statik dosya, CSP
  db.py                  SQLite + numaralı göçler (PRAGMA user_version)
  accounts.py            kullanıcı, oturum, müşteri kaydı
  auth.py                Google girişi (authorization code + PKCE), /api/me
  merchants.py           işletme profili ve harita iğnesi
  programs.py            işletmenin kartları: ödül türü, damga hedefi, 5 aktif sınırı, arşiv
  loyalty.py             kartın kasa QR'ı, damga, ödül, işletme paneli
  places.py              harita listesi, adres araması (Nominatim)
  demo.py                demo işletmeler (BIKIYAK_DEMO_MODE=1)
  app.py                 modülleri birleştirir (FEATURES)
static/
  index.html, styles.css, app.css
  js/main.js             açılış; js/nav.js görünüm değiştirme + alt sekme çubuğu
  js/api.js, state.js, ui.js, map-kit.js, qr-themes.js
  js/views/*.js          her ekran bir modül (home, card, map, cards, account, setup,
                         programs, program + reward-picker, merchant: QR ve panel)
  vendor/                qrcode.min.js (QR-LICENSE), leaflet 1.9.4 (BSD-2)
tests/                   gerçek sunucu + sahte Google token uç noktası
deploy/                  Dockerfile, compose, Caddy, DuckDNS, test-in-image.sh
```

**Yeni özellik eklemek (v2 vitrin, v3 sipariş...):** `bikiyak/<alan>.py` içinde
`routes = Router()` ile uç noktalar, `app.py`'deki `FEATURES`'a ekleme, şema
gerekiyorsa `db.py`'de yeni `m00N_...` göçü (eskiye dokunulmaz), arayüzde
`static/js/views/<ekran>.js` + `defineView()`, ve `tests/test_<alan>.py`.
Tek yerde toplanan kurallar: oturum `accounts.require_user`, işletme yetkisi
`merchants.require_merchant`, yazma işlemleri `db.write()` bloğunda.

## Çalıştır ve doğrula

```bash
cd /root/projects/qrsadakat
BIKIYAK_DEMO_MODE=1 python3 -m bikiyak          # http://127.0.0.1:8088
python3 -m unittest discover -s tests -t .      # hızlı, host Python'uyla
./deploy/test-in-image.sh                       # asıl kontrol: canlı imajın Python/SQLite'ı
```

Host'taki SQLite (3.34) canlı imajdakinden (3.46) eski; yeni SQLite'ta ayrılmış
kelimeler farklı. Deploy öncesi `test-in-image.sh` şart.

Ortam: `BIKIYAK_DB`, `BIKIYAK_HOST`, `BIKIYAK_PORT`, `BIKIYAK_PUBLIC_URL`
(Google redirect adresi bundan kurulur), `BIKIYAK_DEMO_MODE`, `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET`. Google anahtarları yoksa giriş kapalıdır, demo çalışır.

## Google girişi kurulumu (bir kez)

1. Google Cloud Console → yeni proje (ör. "bikıyak") → **OAuth consent screen**:
   External, uygulama adı bikıyak, kapsamlar yalnız `openid`, `email`, `profile`
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

`https://bikıyak.com`: Cloudflare → Caddy (`/root/caddy/sites/bikiyak.com.Caddyfile`) →
`qrsadakat-app:8088` konteyneri. Site herkese açık (Basic Auth 27 Eyl 2026'da kaldırıldı);
`X-Robots-Tag: noindex` duruyor, arama motorları pilotu dizine eklemez. Demo modu açıkken
"Hazır demoyu aç" ile herkes Nora Café panelini görebilir; bu yalnız demo verisidir.

DuckDNS anahtarı `/root/secrets/qrsadakat-duckdns-token`; `qrsadakat-duckdns.timer` beş
dakikada bir `deploy/update_duckdns.py` çalıştırır (eski adresin yönlendirmesi için).
Veri `qrsadakat_qrsadakat_data` biriminde (`/data/pilot.sqlite3`); göçler açılışta
kendiliğinden çalışır. Tablo yeniden kuran göçlerden önce `/data` yedeklenir.

```bash
./deploy/test-in-image.sh
docker compose -f deploy/compose.yml build app
docker compose -f deploy/compose.yml up -d app
```

## Alan adı: bikıyak.com

**27 Eyl 2026'dan beri canlı.** Türkçe "ı" içerdiği için teknik adı (punycode)
`xn--bikyak-r9a.com`; tarayıcıda `bikıyak.com` görünür. DNS Cloudflare'de:

| Tür | Ad | Değer | Proxy |
|---|---|---|---|
| A | `bikıyak.com` | `136.243.228.36` | Proxied (turuncu) |
| CNAME | `www` | `bikıyak.com` | Proxied (turuncu) |

- Cloudflare TLS'i kendi ucunda sonlandırır; sunucuda Caddy `tls internal` kullanır
  (atjobfind.com ile aynı kurulum, `deploy/bikiyak.com.Caddyfile`).
- Cloudflare **SSL/TLS modu "Full" olmalı.** Flexible sonsuz yönlendirme döngüsü, Full (strict)
  525 hatası verir. Bu ayar değiştirilirse site kapanır.
- AAAA kaydı yok: sunucunun genel IPv6 adresi yok.
- `www` → ana adrese 308 yönlendirme. Eski `qrsadakat.duckdns.org` 27 Eyl 2026'dan beri her isteği
  bikıyak.com'a 308 ile yönlendirir (`deploy/Caddyfile`); DuckDNS zamanlayıcısı bu yüzden açık kalır.

`BIKIYAK_PUBLIC_URL` = `https://xn--bikyak-r9a.com`; Google OAuth istemcisindeki yönlendirme
adresi `https://xn--bikyak-r9a.com/auth/google/callback` olmalı.

Öneri: `bikiyak.com` (i ile) da alınıp buraya yönlendirilsin.

## Hoş geldin maili

`bikiyak/mail.py`: yeni **müşteriye** ilk Google girişinde **bir kez** gider (işletmecilere, eski
kullanıcılara ve ikinci girişte gitmez). Başka otomatik mail yok. Gönderen
`bikıyak <merhaba@bikıyak.com>`, yanıt adresi `iletisim@bikıyak.com`; kanal Resend (anahtar
`/root/secrets/bikiyak-resend.env`, yalnız gönderim yetkili). `sent_mails` (göç 006) kullanıcı ve
tür başına tek satır tutar; başarısızlık orada görünür, otomatik yeniden deneme yok.

**Kapalı başlar:** metin ve görsel onaylanınca compose'a `BIKIYAK_WELCOME_MAIL: "1"` eklenir, aynı
anda gizlilik sayfasının aktarımlar bölümüne Resend yazılır. Üst görsel `static/brand/mail-banner.jpg`
(1120×448); dosya yoksa mavi bant ve bilet logosu çıkar, kırık resim olmaz.
```bash
docker exec qrsadakat-app python -m bikiyak.admin welcome-preview > onizleme.html
docker exec qrsadakat-app python -m bikiyak.admin welcome-test adres@gmail.com "Ayşe Yılmaz"
```

## Gizlilik sayfası

`static/gizlilik.html` (`/gizlilik`, 27 Eyl 2026'dan beri yayında) KVKK aydınlatma metnidir. Sistemin
gerçekte işlediği veriler, 3 çerez, aktarımlar (Google, Cloudflare, Hetzner/Almanya,
OpenStreetMap/Nominatim) ve Google "Limited Use" beyanı yazılıdır. Veri sorumlusu olarak "bikıyak"
ve iletişim olarak iletisim@bikıyak.com yazılı (kullanıcı kararı). Bu posta adresi Cloudflare Email
Routing ile Gmail'e yönlenmeli; şirket kurulunca unvanla güncellenmeli. Hukukçuya okutulması
önerilir. Ana sayfanın dipnotunda ve Hesap ekranında bağlantısı var. Veri işleyişi değişirse
bu metin de güncellenmeli.

## Tema ve marka

**Kobalt & Güneş, modern cüzdan / fintech** (27 Eyl 2026 kullanıcı seçimi). Mobil öncelikli;
bir sonraki adım mobil uygulama olduğu için bütün değerler `static/styles.css` başındaki
değişkenlerde durur ve uygulamaya aynen taşınır:

| Değişken | Değer | Kullanım |
|---|---|---|
| `--primary` | `#2447F5` | ana düğmeler, seçili sekme, bağlantılar |
| `--ink` | `#0B1433` | metin, logo yazısı |
| `--accent` | `#FFC933` | damga, ödül, logo bileti |
| `--bg` / `--surface` | `#F2F4FA` / `#FFFFFF` | zemin / kartlar |
| `--cat-*` | kafe `#7A4B2E`, restoran `#C8452F`, fırın `#D9892B`, market `#2F8F5B`, berber `#26335C`, diğer `#2447F5` | cüzdan kartları, harita iğneleri |

- Yazı tipleri: **Sora** (başlıklar, logo) ve **Plus Jakarta Sans** (metin), `static/fonts/` altında
  yerel (CSP dış kaynağa izin vermez; OFL lisansları yanında). Türkçe harfler latin-ext dosyasında.
- Logo: **kıyak bileti**, yani sarı çentikli bilet, içinde "bikıyak" ve gülümseme. Üst çubukta satır içi
  SVG olarak çizilir (yazı tipini sayfadan alır). İkon: sarı kare, lacivert "b" ve gülümseme.
- `static/brand/`: `icon-512/192/32.png`, `icon-180.png` (iOS), `icon-maskable-512.png` (Android),
  `google-logo-120.png` (Google giriş ekranı), `logo-ticket.png`. Tarayıcıda Sora ile çizilip
  PNG'ye alındı; logo değişirse aynı yolla yeniden üretilir.
- PWA: `static/manifest.webmanifest`, yani site telefonda "Ana ekrana ekle" ile uygulama gibi açılır.

## Temalı QR

`static/js/qr-themes.js`, `qrcode.min.js`'in modül ızgarasını alıp SVG'yi kendisi
çizer. Okunabilirlik kuralı: kodun karesi açık zeminde koyu modül, 4 modül sessiz
bölge, üç konum işareti sağlam; tema resmi (fincan, tabak, ekmek, poşet, berber
direği) karenin **dışında**. İçeride yalnız modül biçimi, renk ve konum işaretlerinin
şekli değişir (kafe: kahve çekirdeği). Hata düzeltme Q. 27 Eyl 2026'da altı tema da
zxing-cpp ile 788, 394 ve 275 piksel genişlikte çözüldü (18/18); marka renklerine geçişten sonra yeniden: 18/18. Yeni tema ekleyince
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
| Haritada bikıyak geçen yerler, damga durumum, yol tarifi | ✅ |
| Kategoriye göre temalı QR | ✅ |
| İşletme ödül türünü seçer: bedava ürün, % indirim, ₺ indirim, kendi metni | ✅ |
| Bir işletmede birden çok kart (en fazla 5 aktif, arşiv), karta dokununca QR | ✅ |
| Mobil öncelikli arayüz, alt sekme çubuğu | ✅ |
| Demo (Nora Café + 13 hayali yer) | 27 Eyl 2026 ciddi başlangıçta kapatıldı (`BIKIYAK_DEMO_MODE=0`) |
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
- Demo modu açıkken demo yerleri haritada görünür; lansmanda `BIKIYAK_DEMO_MODE=0`.
