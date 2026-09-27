# Mahalle Kartı — QR sadakat pilotu

Sunumdaki ilk aşamanın daraltılmış, çalışan v1'i. Depo: `git@github.com:mmeekh/qrsadakat.git`
(27 Eyl 2026'ya kadar jobfind deposunda izlenmeyen `loyalty_v1/` klasörüydü).
İşletme kart ve ödül oluşturur; müşteri kasadaki süreli QR'ı okuttuğunda damga
otomatik işlenir. Damga hedefinde ödül açılır, ödül teslimi personel onayıyla
kaydedilir. Panel, damga alan müşteri sayısını ve tekrar gelenleri
gösterir.

Canlı pilotta `LOYALTY_DEMO_MODE=1` açıktır: ana sayfadaki **Hazır demoyu aç**
düğmesi Nora Café hesabına tek tıkla girer. Üç örnek müşteri, on ziyaret ve iki
tekrar gelen müşteri ilk kurulumda bir kez eklenir; yeniden başlatma demo
verilerini sıfırlamaz. Gerçek lansmanda bu bayrak kapatılmalıdır.

## Yol haritası: v1 → v2 → v3

Kaynak: "QR Sadakatten Tam Ticarete" sunumu (8 slayt,
`lingering-surf-b93c.reymisteryo3393.workers.dev`, Cloudflare Access arkasında).
Sunumdaki üç aşama sürümlere karşılık gelir; her sürüm bir öncekinin üzerine
eklenir. 27 Eyl 2026'da Codex'ten (ChatGPT) Claude'a devredildi.

### v1 · QR Sadakat + Harita (ilk açılış)

Uygulama indirmeden sadakat: müşteri QR okutur, web kartı açılır.
İşletme ilk günden kullanır; v2 ve v3 bunun üzerine kurulur.

| Sunumdaki madde | Durum |
|---|---|
| İşletme kaydı, kart ve ödül tanımı (N damga → ödül) | ✅ canlı |
| İşletme ekranında süreli QR (dakikada yenilenir), müşteri kendi telefonuyla okutur | ✅ canlı |
| Otomatik damga + damga animasyonu, ödül teslimi personel onayıyla | ✅ canlı |
| Panel: damga alan müşteri, tekrar gelen müşteri | ✅ canlı |
| Tek tıkla demo işletme (Nora Café) | ✅ canlı (`LOYALTY_DEMO_MODE=1`) |
| Müşterinin e-posta ile girişi (kart cihazlar arası taşınır) | ⏳ yok; kart şimdilik tarayıcı çerezinde |
| İşletme şifre sıfırlama, e-posta doğrulaması | ⏳ yok, halka açılış öncesi şart |
| Puan ve para iadesi (şimdilik yalnız damga var) | ⏳ yok |
| Haritada yakındaki işletmeler/fırsatlar | ⏳ yok |
| Kısa süreli anlık kampanyalar (ör. "18:00'e kadar 2 kat puan") | ⏳ yok |
| Kartın telefon cüzdanına eklenmesi (Apple Wallet / Google Wallet) | ⏳ yok |
| Yapay zekâ ile otomatik kurulum (ad/adres/foto → profil + ilk kampanya) | ⏳ yok |

Başarı ölçütü: 10–20 işletmelik pilotta müşterilerin kartı **ikinci kez**
kullanıp kullanmadığı (panelde "tekrar gelen" sayısı).

### v2 · Yerel Market (sonraki adım)

v1'e işletmeler ve müşteriler alıştıktan sonra açılır; sadakat kartının üzerine
satış vitrini gelir. Görünürlük reklam bütçesine değil, yakınlık ve sadakate
göre belirlenir.

- İşletme vitrini: ürün / hizmet / menü gösterimi
- Kategoriye göre keşif
- Rezervasyon ve ön sipariş
- Müşteri yorumları
- Müşteriye özel öneriler
- Gelişmiş işletme paneli
- Ücretli öne çıkarma (isteğe bağlı, zorunlu değil)

### v3 · Tam Ticaret Altyapısı (uzun vadeli hedef)

v2 vitrininin üzerine sepet, ödeme ve teslimat eklenir; işletme pazaryerine
ihtiyaç duymadan satar.

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

**v3 sonrası (sunumdaki projeksiyon, sürüme bağlanmadı):** yerel kurye ağı
(esnaflar arası ortak teslimat), düşük ve şeffaf komisyon, yerli ticaret altyapısı.

## Çalıştır

Python 3.9+ yeterlidir; ek Python paketi gerekmez.

```bash
cd /root/projects/qrsadakat
python3 server.py
```

`http://127.0.0.1:8088` adresini aç. Veriler varsayılan olarak
`pilot.sqlite3` dosyasına yazılır. `LOYALTY_DB`, `LOYALTY_HOST` ve
`LOYALTY_PORT` ortam değişkenleriyle konum ve dinleme adresi değişir.
Telefondan QR denemek için sunucunun telefondan erişilebilen bir adresle
sunulması gerekir; QR, panelin açıldığı adresi kullanır. İnternete açarken HTTPS
ve ters proxy kullan.

## Caddy için hazırlanan pilot koruması

[`deploy/Caddyfile`](deploy/Caddyfile) `qrsadakat.duckdns.org` alan adını
ayrı Docker konteynerindeki `qrsadakat-app:8088` uygulamasına yönlendirir ve **tüm siteye** HTTP Basic Auth
uygular. Kullanıcı adı `admin`; parola özeti depoda yer tutucudur, gerçek özet yalnız
canlı kopyada (`/root/caddy/sites/qrsadakat.duckdns.org.Caddyfile`). Bu koruma açıkken müşteriler de QR sonrası giriş penceresi
görür; yalnız kapalı test için uygundur.

Mevcut Caddy `web` Docker ağına bağlıdır. Ayrı uygulama konteyneri
`deploy/compose.yml` ile aynı ağa katılır; 8088 host'a açılmaz. Site bloğu
mevcut Caddy'nin `/root/caddy/sites/` dizinine ayrı dosya olarak eklenir;
var olan site bloklarına dokunulmaz. Caddy otomatik HTTPS kullanır.

Canlı adres: `https://qrsadakat.duckdns.org`. DuckDNS anahtarı depoda değil,
`/root/secrets/qrsadakat-duckdns-token` dosyasında (0600). `qrsadakat-duckdns.timer`
beş dakikada bir `deploy/update_duckdns.py` çalıştırır; IP'yi DuckDNS isteğin
geldiği sunucudan otomatik algılar. Uygulama güncellemesi:

```bash
docker compose -f deploy/compose.yml build app
docker compose -f deploy/compose.yml up -d app
```

## Pilot akışı

1. İşletme kaydolur; adını, ödülünü ve gereken damga sayısını girer.
2. İşletme panelde QR gösterir; ekran açıkken kod her dakika yenilenir.
3. Müşteri kendi telefonuyla güncel QR'ı okutur; damga anında işlenir ve animasyon görünür.
4. Hedef dolunca müşteri ödül kullanım isteği yollar; personel teslimi onaylar.

QR, işletmeye bağlı ve kısa süreli imzalı bir kod taşır. Eski veya başka
işletmenin kodu damga vermez. Aynı karta iki damga arasında en az bir saat
olmalıdır. Şifreler scrypt ile saklanır; oturum ve müşteri çerezlerinin
veritabanında yalnız SHA-256 özeti tutulur.

## Pilotun sınırları

- Müşteri kartı aynı tarayıcıya bağlıdır. Çerez silinirse kart geri alınamaz.
  Pilot sonrası kalıcı hesap için e-posta doğrulaması gerekir.
- İşletme şifresi sıfırlama ve e-posta doğrulaması henüz yoktur. Bunlar halka
  açık lansmandan önce tamamlanmalıdır.
- Ekrandaki güncel QR'ın fotoğrafı kısa geçerlilik süresi içinde paylaşılırsa
  başkası da kullanabilir; bu pilotta fiziksel alışveriş doğrulaması yoktur.
- Harita, cüzdan kartı, kampanya otomasyonu, ödeme ve yapay zekâ kurulumu bu
  pilotun kapsamına dahil değildir.
- `qrcode.min.js` yerel olarak sunulur; kütüphane lisansı `QR-LICENSE` dosyasında.

## Doğrulama

```bash
python3 -m unittest test_server -v
node --check static/app.js
```
