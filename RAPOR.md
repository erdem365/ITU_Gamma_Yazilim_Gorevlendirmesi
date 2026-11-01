# İTÜ Gamma Takımı – Yazılım Ekibi Görevlendirmesi: Rapor

**Görevlendirme tarihi:** 25 Ekim 2026 · **Son teslim:** 28 Ekim 2026 Çarşamba 23:59

## 0. Kapsam ve dürüstlük notu

Bu rapor PDF'deki dört bölümün tamamını kapsar: (1) süreçler arası haberleşme ve hedef sapma açısı (A.py/B.py), (2) PX4/MAVLink/sürü teorik soruları, (3) GNSS'siz konumlandırma ve görsel takip, (4) gecikme ve jitter analizi.

Neyin nasıl doğrulandığı baştan açıkça ayrılmıştır:

| Alan | Durum |
|---|---|
| A.py / B.py kodu | **Çalıştırıldı ve test edildi** (Linux, Python 3.12.3, ayrı süreçler). §4'e bakın. |
| Windows üzerinde çalışma | **Test edilmedi.** Kod yalnızca standart kütüphane kullanıyor; talimatlar yazıldı ama denenmedi. |
| Gerçek İHA / PX4 donanımı | **Hiç test edilmedi.** Teorik kısımlar yalnızca anlatımdır. |
| PX4 SITL | Bu çalışmada **çalıştırılmadı**; SITL anlatımı belgelere dayanır. |
| Kaynaklar | Hangi kaynağın bu çalışma sırasında gerçekten açılıp okunduğu §8'de ayrıca belirtilmiştir. |
| Gecikme/jitter bölümü | Gerçek ölçüm yapılmadı; **hipotez ve ölçüm planıdır**, sayısal değerler örnek/hesap amaçlıdır. |

Kaynak atıfları `[K1]`, `[K2]` ... biçimindedir ve §8'deki listeye gider.

---

## 1. Süreçler arası haberleşme: yöntem seçimi

### 1.1 Seçenekler

| Yöntem | Artıları | Eksileri | Bu görev için |
|---|---|---|---|
| **TCP soketi (localhost)** | Standart kütüphane, güvenilir ve sıralı akış, platformdan bağımsız (Windows/Linux/WSL), iki süreç gerçekten ayrı ve eşzamanlı, ileride başka bilgisayara taşınabilir | Bağlantı kurma adımı (bir taraf dinler) ve satır sınırlarını (framing) elle yönetme gerekir | **Seçildi** |
| UDP soketi | Bağlantısız, gecikmesi düşük | Paket kaybı/sıra bozulması olabilir; "tek sayı iletildi mi?" garantisi yok | Bu görevde gereksiz risk |
| Dosya okuma/yazma | En basit | Eşzamanlılık sorunları (yarım yazılmış dosya), yoklama (polling) gecikmesi, disk | Gerçek zamanlı akış için uygun değil |
| `multiprocessing.shared_memory` | Çok hızlı | Senkronizasyon (kilit/bayrak) gerekir; iki bağımsız `python A.py`/`python B.py` için kurulumu daha karmaşık | Gereksiz karmaşıklık |
| Named pipe / FIFO | Basit | Windows ve Linux'ta farklı API'ler | Taşınabilirlik zayıf |
| ROS 2 (topic) | Robotikte standart, esnek | Kurulum ağır, harici bağımlılık; görev "harici paket gerekmedikçe ekleme" diyor | Bu ölçekte aşırı |

### 1.2 Gerekçe (kısa)
TCP soketi, hem Windows hem Linux/WSL'de standart kütüphaneyle çalışır, mesajları **kayıpsız ve sıralı** taşır ve iki scriptin gerçekten ayrı süreçler olmasını doğal biçimde sağlar. Görev yalnızca tek bir sayıyı iletmeyi gerektirdiği için en küçük çözüm budur. Gerçek sistemde de görüntü işleme süreci ile uçuş kontrol süreci benzer biçimde soket/ROS/MAVLink gibi mesajlaşma katmanlarıyla ayrılır.

**Dezavantaj (bilerek kabul edildi):** TCP akış tabanlıdır; mesaj sınırını korumaz. Bu yüzden her mesaj `\n` ile biten bir metin satırı yapıldı ve B.py satır sonuna kadar tampon biriktirir. Yüksek frekanslı gerçek zamanlı akışta (ör. 30 Hz sınırlayıcı kutu verisi) UDP + zaman damgası daha uygun olabilir; bunun gerekçesi §7'de açıklanır.

### 1.3 Mimari ve başlangıç sırası

```
 A.py (istemci)  ──TCP 127.0.0.1:5005──►  B.py (sunucu)
 input() → doğrula → "400\n"               satır oku → doğrula → hesapla → yazdır
```

1. **B.py önce başlar:** `bind` + `listen`, `accept` ile bekler.
2. **A.py başlar:** `connect`. B.py henüz açık değilse 10 kez, 1 sn arayla yeniden dener (başlangıç sırası hatasını affeder).
3. A.py her girişte bir satır gönderir; B.py satırı alır ve yazdırır.
4. A.py kapanırsa B.py "yeni bağlantı bekleniyor" der, kapanmaz. B.py kapanırsa A.py bir sonraki gönderimde bağlantı kopmasını yakalar.

### 1.4 Hata durumları

| Durum | Davranış |
|---|---|
| B.py açık değil | A.py yeniden dener; olmazsa "önce `python B.py` çalıştırın" yazıp çıkış kodu 1 ile biter |
| Port dolu | B.py anlamlı mesaj verip çıkar |
| Sayısal olmayan giriş (`abc`, boş, `nan`, `inf`) | A.py reddeder, tekrar sorar |
| 0–640 dışı (2. aşama) | A.py reddeder; B.py de bağımsız olarak tekrar kontrol eder (savunmalı tasarım) |
| Bozuk/parçalı/yapışık paket | B.py satır tamponu ile doğru ayırır; bozuk satırı yok sayar |
| Çok uzun, satır sonsuz veri | B.py 1024 baytı aşınca bağlantıyı keser |
| B.py ortada kapanırsa | A.py `OSError` yakalar, mesaj verip çıkar *(TCP'nin doğası gereği ilk gönderim bazen "başarılı" görünür, kopma sonraki gönderimde fark edilir)* |
| Ctrl+C / Ctrl+D / `q` | Temiz çıkış |

---

## 2. İki aşamanın kodu

İkisi aynı iki dosyada birleştirildi: `--stage 1` yalnızca sayıyı iletir, `--stage 2` (varsayılan) x koordinatını gönderir ve sapmayı hesaplar. **İlk aşamadaki altyapı (soket, satır protokolü, hata yönetimi) hiç değişmeden ikinci aşamada kullanılır;** fark yalnızca iki yerdedir: A.py giriş aralığını (0–640) denetler, B.py gelen sayıyı yazdırmak yerine `compute_deviation_deg()` fonksiyonuna verir.

### 2.1 `A.py`

```python
#!/usr/bin/env python3
"""A.py - Gönderici ("Görüntü İşleme Simülatörü").

Kullanıcıdan input() ile bir sayı alır ve TCP soketi üzerinden B.py'ye gönderir.
Her mesaj, sonu '\\n' ile biten bir metin satırıdır.

Kullanım:
    python A.py              # 2. aşama (varsayılan): x koordinatı, 0-640 aralığı
    python A.py --stage 1    # 1. aşama: herhangi bir sayı

Çıkmak için 'q' yazın (veya Ctrl+C / Ctrl+D). Python 3.8+ gerekir, harici paket yok.
"""
import argparse
import math
import socket
import sys
import time

HOST = "127.0.0.1"
PORT = 5005
IMAGE_WIDTH = 640        # 2. aşama: geçerli x aralığı 0..640
QUIT_WORDS = ("q", "quit", "exit")


def parse_number(text):
    """Geçerli sayıyı döndürür; geçersizse (harf, boş, nan, inf) None."""
    text = text.strip().replace(",", ".")
    if not text or "_" in text:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def format_number(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def connect(retries, delay):
    """B.py henüz başlamadıysa kısa aralıklarla birkaç kez yeniden dener."""
    for attempt in range(1, retries + 1):
        try:
            return socket.create_connection((HOST, PORT), timeout=3)
        except OSError:
            print("[A] B.py'ye bağlanılamadı (%d/%d). B.py başlatıldı mı? %g sn sonra tekrar denenecek..."
                  % (attempt, retries, delay))
            time.sleep(delay)
    return None


def main():
    parser = argparse.ArgumentParser(description="Gönderici (Görüntü İşleme Simülatörü)")
    parser.add_argument("--stage", type=int, choices=(1, 2), default=2,
                        help="1: herhangi bir sayı, 2: x koordinatı 0-640 (varsayılan 2)")
    parser.add_argument("--retries", type=int, default=10, help="bağlantı deneme sayısı")
    parser.add_argument("--delay", type=float, default=1.0, help="denemeler arası saniye")
    args = parser.parse_args()

    sock = connect(args.retries, args.delay)
    if sock is None:
        print("[A] B.py'ye bağlanılamadı. Önce başka bir terminalde 'python B.py' çalıştırın.")
        return 1
    print("[A] B.py'ye bağlanıldı.")

    if args.stage == 1:
        prompt = "Bir sayı girin (çıkış: q): "
    else:
        prompt = "Hedefin x koordinatını girin (0-%d, çıkış: q): " % IMAGE_WIDTH

    with sock:
        while True:
            try:
                text = input(prompt)
            except (EOFError, KeyboardInterrupt):
                print("\n[A] Çıkılıyor.")
                return 0
            if text.strip().lower() in QUIT_WORDS:
                print("[A] Çıkılıyor.")
                return 0
            value = parse_number(text)
            if value is None:
                print("[A] Geçersiz giriş: lütfen sayısal bir değer girin.")
                continue
            if args.stage == 2 and not 0 <= value <= IMAGE_WIDTH:
                print("[A] x koordinatı 0 ile %d arasında olmalı." % IMAGE_WIDTH)
                continue
            try:
                sock.sendall((format_number(value) + "\n").encode("utf-8"))
            except OSError:
                print("[A] B.py ile bağlantı koptu. B.py kapanmış olabilir.")
                return 1


if __name__ == "__main__":
    sys.exit(main())
```

### 2.2 `B.py`

```python
#!/usr/bin/env python3
"""B.py - Alıcı ("Uçuş Kontrolcüsü").

Yöntem: TCP soketi (localhost). B.py sunucu olarak dinler, A.py istemci olarak bağlanır.
Mesaj biçimi: her sayı, sonu '\\n' ile biten bir metin satırıdır (örn. "400\\n").

Kullanım:
    python B.py              # 2. aşama (varsayılan): piksel -> sapma açısı
    python B.py --stage 1    # 1. aşama: gelen sayıyı olduğu gibi yazdır

Python 3.8+ gerekir, harici paket gerekmez.
"""
import argparse
import math
import socket
import sys

HOST = "127.0.0.1"
PORT = 5005

# --- 2. aşama sabitleri (PDF'deki varsayımlar) ---
IMAGE_WIDTH = 640        # piksel (yükseklik 480, bu aşamada kullanılmıyor)
HFOV_DEG = 80.0          # toplam yatay görüş açısı (derece)
CENTER_X = 320.0         # görüntü merkezinin x koordinatı
DEG_PER_PIXEL = HFOV_DEG / IMAGE_WIDTH   # 80 / 640 = 0.125 derece/piksel

MAX_LINE_BYTES = 1024    # satır sonu gelmeden bu kadar veri gelirse bağlantı reddedilir


def parse_number(text):
    """Metni sayıya çevirir; geçersizse (nan, inf, boş, harf...) None döndürür.
    Virgüllü ondalık ('400,5') da kabul edilir."""
    text = text.strip().replace(",", ".")
    if not text or "_" in text:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def format_number(value):
    """Tam sayı değerli sayıları '400' olarak, diğerlerini '400.5' olarak gösterir."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def compute_deviation_deg(x):
    """Hedefin görüntü merkezinden yatay sapmasını derece olarak döndürür.

    Doğrusal orantı: sapma = (x - 320) * (80 / 640)
    Sağ taraf (x > 320) pozitif, sol taraf (x < 320) negatif.
    x, [0, 640] aralığında değilse ValueError fırlatır.
    """
    if not 0 <= x <= IMAGE_WIDTH:
        raise ValueError("x koordinatı 0-%d aralığında olmalı" % IMAGE_WIDTH)
    return (x - CENTER_X) * DEG_PER_PIXEL


def process_line(line, stage):
    value = parse_number(line)
    if value is None:
        print("[B] Geçersiz veri alındı, yok sayıldı: %r" % line)
        return
    if stage == 1:
        print("Alınan sayı: %s" % format_number(value))
        return
    try:
        deviation = compute_deviation_deg(value)
    except ValueError as err:
        print("[B] %s (alınan: %s), yok sayıldı." % (err, format_number(value)))
        return
    deviation = round(deviation, 2) + 0.0   # '-0.00' görünmesin
    print("Alınan piksel: %s, Hesaplanan Sapma: %.2f derece"
          % (format_number(value), deviation))


def handle_client(conn, stage):
    """Bağlı istemciden satır satır veri okur; istemci kapanınca döner."""
    conn.settimeout(1.0)   # Ctrl+C'nin (özellikle Windows'ta) çalışabilmesi için
    buffer = b""
    while True:
        try:
            chunk = conn.recv(4096)
        except socket.timeout:
            continue
        except OSError as err:
            print("[B] Bağlantı hatası: %s" % err)
            return
        if not chunk:          # karşı taraf bağlantıyı kapattı
            return
        buffer += chunk
        while b"\n" in buffer:
            raw, buffer = buffer.split(b"\n", 1)
            process_line(raw.decode("utf-8", errors="replace"), stage)
        if len(buffer) > MAX_LINE_BYTES:
            print("[B] Satır sonu olmadan çok fazla veri geldi; bağlantı kesiliyor.")
            return


def serve(stage):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((HOST, PORT))
        except OSError as err:
            print("[B] %s:%d dinlenemedi (%s). Başka bir B.py açık olabilir." % (HOST, PORT, err))
            return 1
        server.listen(1)
        server.settimeout(1.0)
        print("[B] %s:%d üzerinde dinleniyor (aşama %d). Durdurmak için Ctrl+C." % (HOST, PORT, stage))
        while True:
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                continue
            print("[B] A.py bağlandı.")
            with conn:
                handle_client(conn, stage)
            print("[B] A.py bağlantıyı kapattı; yeni bağlantı bekleniyor...")


def main():
    parser = argparse.ArgumentParser(description="Alıcı (Uçuş Kontrolcüsü)")
    parser.add_argument("--stage", type=int, choices=(1, 2), default=2,
                        help="1: sayıyı yazdır, 2: sapma açısını hesapla (varsayılan 2)")
    args = parser.parse_args()
    try:
        return serve(args.stage)
    except KeyboardInterrupt:
        print("\n[B] Kapatıldı.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

### 2.3 Neden böyle yazıldı?
- `parse_number` ve `format_number` iki dosyada aynıdır: göndericide ve alıcıda aynı doğrulama (bir taraf bozulsa bile diğeri korur).
- `isfinite` kontrolü: Python `float("nan")` ve `float("inf")` değerlerini sorunsuz çevirir; bunlar açıyı bozacağı için reddedilir.
- B.py `settimeout(1.0)` kullanır: bloklayan `accept`/`recv` çağrıları Windows'ta Ctrl+C'yi geciktirebildiği için kısa zaman aşımıyla döngü kurulur. *(Bu davranış bu çalışmada Windows'ta denenmedi.)*
- `-0.00` yazılmasını önlemek için sonuç `round(x, 2) + 0.0` ile düzeltilir.

---

## 3. Hedef sapma açısı

### 3.1 Varsayımlar (PDF'den)
Çözünürlük 640×480, yatay görüş açısı (HFOV) 80°, görüntü merkezi x = 320, x ∈ [0, 640]. Merkezin sağı pozitif, solu negatif.

### 3.2 Doğrusal model (temel çözüm)
Görüntünün sol ve sağ kenarı optik eksene göre sırasıyla −40° ve +40° kabul edilir. Piksel başına düşen açı sabit varsayılır:

```
derece_per_piksel = HFOV / genişlik = 80 / 640 = 0.125 °/piksel
sapma(x) = (x − 320) · 0.125 = (x − 320) · 80 / 640
```

Tutarlılık kontrolü: `x = 0 → (−320)(0.125) = −40°`, `x = 640 → +40°`. Yani formül ±HFOV/2 varsayımıyla birebir tutarlıdır.

### 3.3 Sonuçlar (B.py ile doğrulandı)

| x (piksel) | Sapma (°) | Yorum |
|---|---|---|
| 320 | 0.00 | Merkez |
| 0 | −40.00 | Sol uç |
| 640 | +40.00 | Sağ uç |
| 400 | +10.00 | Merkezin 80 px sağı |
| 240 | −10.00 | Simetri kontrolü |

İşaret kontrolü: x > 320 ise pozitif, x < 320 ise negatif; x = 320 ise sıfır. Testlerde doğrulandı.

### 3.4 Bu neden bir *yaklaşımdır*? (perspektif/tanjant karşılaştırması)
Pinhole (iğne deliği) kamera modelinde, görüntü düzlemindeki piksel konumu açının **tanjantıyla** orantılıdır, açının kendisiyle değil. Odak uzaklığı piksel cinsinden `f = (W/2) / tan(HFOV/2)` olur:

```
f = 320 / tan(40°) ≈ 381.36 piksel
açı_gerçek(x) = atan( (x − 320) / f )
```

| x | Doğrusal (°) | Tanjant (°) | Fark (°) |
|---|---|---|---|
| 0 | −40.00 | −40.00 | 0.00 |
| 80 | −30.00 | −32.18 | 2.18 |
| 160 | −20.00 | −22.76 | 2.76 |
| 240 | −10.00 | −11.85 | 1.85 |
| 320 | 0.00 | 0.00 | 0.00 |
| 400 | +10.00 | +11.85 | −1.85 |
| 480 | +20.00 | +22.76 | −2.76 |
| 560 | +30.00 | +32.18 | −2.18 |
| 640 | +40.00 | +40.00 | 0.00 |

İki model **uçlarda ve merkezde aynı**, arada farklıdır; en büyük fark yaklaşık 2.8° (x ≈ 149 ve simetriği). Doğrusal model, hedef merkeze yakınken ve düşük hassasiyet yeterliyken makul bir ilk yaklaşımdır; gerçek bir kontrolcüde, kamera kalibre edilmişse tanjant modeli (veya kalibrasyonla düzeltilmiş görüntü) tercih edilir. Bu karşılaştırma yalnızca açıklama amaçlıdır; B.py PDF'nin istediği doğrusal modeli kullanır. *Not: Tanjant sonuçları bu çalışmada Python ile hesaplandı, B.py'nin içinde yoktur.*

Ek not: "80° yatay FoV" çoğu zaman kamera üreticisinin verdiği bir değerdir; lens bozulması (distorsiyon) ve kırpma/yeniden ölçekleme bu değeri etkileyebilir. Gerçek sistemde kalibrasyon gerekir.

### 3.5 İlk aşama ile ikinci aşamanın birleşimi
İlk aşamada A.py → B.py arası "bir sayı + satır sonu" protokolü kuruldu. İkinci aşamada **protokol aynı kaldı**: A.py yine yalnızca bir sayı (x) yollar, B.py yine satırı okur. Eklenen şeyler: A.py'de aralık kontrolü, B.py'de `compute_deviation_deg()` ve çıktı biçimi. Böylece görüntü işleme (A) ile uçuş kontrolü (B) arasındaki sınır, gerçek sistemdeki gibi küçük ve net bir arayüze indirgenmiş olur.

---

## 4. Testler (gerçekten çalıştırıldı)

**Ortam:** Linux, Python 3.12.3. Bütün entegrasyon testlerinde `A.py` ve `B.py` **ayrı süreçler** olarak `subprocess` ile başlatıldı; B.py'nin çıktısı yakalanıp beklenen metinle karşılaştırıldı. Toplam test sonucu: **tüm kontroller geçti** (formül, ayrıştırma, 1. ve 2. aşama, başlangıç sırası, B yokken A, B ortada ölünce A, parçalı/yapışık/bozuk paket, aşırı uzun satır).

Örnek oturum (2. aşama; A.py'ye sırasıyla `320, 0, 640, 400, 100, abc, 700, -5, nan, (boş), 400,5, q` girildi). **B.py çıktısı:**

```
[B] 127.0.0.1:5005 üzerinde dinleniyor (aşama 2). Durdurmak için Ctrl+C.
[B] A.py bağlandı.
Alınan piksel: 320, Hesaplanan Sapma: 0.00 derece
Alınan piksel: 0, Hesaplanan Sapma: -40.00 derece
Alınan piksel: 640, Hesaplanan Sapma: 40.00 derece
Alınan piksel: 400, Hesaplanan Sapma: 10.00 derece
Alınan piksel: 100, Hesaplanan Sapma: -27.50 derece
Alınan piksel: 400.5, Hesaplanan Sapma: 10.06 derece
[B] A.py bağlantıyı kapattı; yeni bağlantı bekleniyor...
```

`abc`, `nan` ve boş giriş A.py'de "Geçersiz giriş" ile; `700` ve `-5` "0 ile 640 arasında olmalı" ile reddedildi ve B.py'ye hiç ulaşmadı.

1. aşama (`python B.py --stage 1`, A.py'ye `42, 3.14, -7, 12345678901234567890`): 
```
Alınan sayı: 42
Alınan sayı: 3.14
Alınan sayı: -7
Alınan sayı: 12345678901234567890
```

**Test edilmeyenler:** Windows, WSL, farklı bilgisayarlar arası bağlantı, gerçek kamera/İHA.

---

## 5. Teorik sorular (PDF Bölüm 2)

### Soru 1 – PX4 Autopilot ve SITL

**a) PX4 nedir, SITL ne demektir?**
PX4, drone ve diğer insansız araçlar için açık kaynaklı bir uçuş kontrol yazılımıdır (autopilot). Sensör verilerini okur, aracın durumunu kestirir (konum, hız, yönelim), kontrol döngüleriyle motor/servo komutları üretir ve MAVLink ile yer istasyonu veya yardımcı bilgisayarla konuşur. *(Genel tanım; "açık kaynak" ve "MAVLink ile haberleşme" ifadeleri PX4 belgeleriyle uyumludur [K1][K2], ancak "autopilot nedir" tanımının kendisi bu çalışmada belgeden birebir doğrulanmadı.)*

**SITL (Software In The Loop):** PX4 uçuş yazılımının gerçek uçuş kartı yerine **bir bilgisayarda** (aynı bilgisayarda veya aynı ağdaki başka bir bilgisayarda) çalıştırılmasıdır; sensör verilerini ve fiziksel dünyayı bir simülatör (ör. Gazebo, jMAVSim) sağlar [K1].

**b) Gerçek donanım ve simülasyondaki rolü**

| | Gerçek donanım | SITL |
|---|---|---|
| PX4'ün çalıştığı yer | Uçuş kontrol kartı (gömülü) | Geliştirme bilgisayarı |
| Sensör girişi | Gerçek IMU, barometre, GNSS vb. | Simülatörün ürettiği sanal sensör verisi (MAVLink ile) |
| Çıkış | Motor/servo sinyalleri | Simülatöre giden aktüatör komutları (MAVLink ile) |
| Fizik | Gerçek dünya | Simülatörün fizik motoru |
| Risk | Kaza, donanım hasarı | Güvenli |

PX4 belgesi, SITL yapısında PX4'ün simülatöre yerel bir TCP bağlantısıyla (bağlantı noktası 4560) bağlandığını ve simülatör mesajlarını işleyen ayrı bir modül kullandığını belirtir; HITL'de ise (Hardware In The Loop) gerçek karta simülasyon yazılımı yüklenir [K1]. SITL ile simülasyon, kodun "gerçek kart" davranışının tam kopyası değildir (bkz. dezavantajlar).

**c) SITL'in geliştiriciye avantajları**
- **Güvenlik:** Hatalı kod gerçek aracı düşürmez; belge de simülasyonu "gerçek dünyada uçmadan önce değişiklik denemenin hızlı, kolay ve güvenli yolu" olarak tanımlar [K1].
- **Maliyet ve erişilebilirlik:** Donanım olmadan yazılım geliştirilebilir.
- **Tekrarlanabilirlik:** Aynı senaryo defalarca çalıştırılabilir; otomatik testlere/CI'a uygundur *(genel mühendislik bilgisi)*.
- **Hız:** Simülatöre bağlı olarak gerçek zamandan hızlı koşturulabilir (belge: jMAVSim ve Gazebo Classic için) [K1].
- **Hata ayıklama:** Hata ayıklayıcı, günlük ve yer istasyonu aynı bilgisayarda kullanılabilir.
- **Çoklu araç:** Sürü senaryoları donanım olmadan denenebilir.

**Sınırlamalar:** Simülatör gerçek sensör gürültüsü, titreşim, rüzgâr, haberleşme kayıpları ve aerodinamiği tam yansıtmaz (sim-to-real farkı). SITL'de geçen bir test gerçek uçuş güvenliğini **garanti etmez**.

---

### Soru 2 – MAVLink

**a) MAVLink nedir, nasıl kullanılır?**
MAVLink, drone ekosistemi için tasarlanmış çok hafif bir mesajlaşma protokolüdür; hem yer istasyonu–araç hem de araç içi bileşenler arası haberleşmede kullanılır [K3][K2]. Bir **yayın/abonelik (publish-subscribe)** ve **noktadan noktaya** karma modeli izler: sürekli veri akışları (ör. konum, tutum) "topic" gibi yayınlanır; görev ve parametre alışverişi gibi yapılandırma işlemleri yeniden iletimli noktadan noktaya alt protokollerle yapılır [K3]. MAVLink 2'de başlık/ek yük 12 bayttır [K3]. Mesajların kendisi bilerek hafif tutulmuştur ve gönderim onayı/yeniden gönderim anlamı taşımaz; bunun için komut protokolü gibi **mikroservisler** mesajların üzerine kurulur [K2].

Tipik kullanım: Araç düzenli `HEARTBEAT` yayınlar; yer istasyonu veya yardımcı bilgisayar telemetri alır, komut (arm, kalkış, mod değişikliği) ve konum/hız hedefi gönderir. Seri hat, UDP veya TCP üzerinden taşınabilir. *(Örnek mesaj adları ve taşıma seçenekleri genel bilgidir; mesaj listesi için [K3] kullanılmalıdır.)*

**b) MAVSDK ve pymavlink farkı**

| | MAVSDK | pymavlink |
|---|---|---|
| Seviye | **Yüksek seviyeli API:** "arm, kalk, git, offboard hız komutu" gibi işlevler | **Düşük seviyeli:** MAVLink mesajlarını kendiniz oluşturur/ayrıştırırsınız |
| Mimari | C++ çekirdek + dil istemcileri; Python istemcisi, `mavsdk_server` ile gRPC üzerinden konuşur [K4] | MAVLink protokolünün Python uygulaması; kod üretici (`mavgen`) de içerir [K5] |
| Kolaylık | Hızlı başlangıç, senkron/asenkron API [K4] | Daha fazla emek; heartbeat, onay (ACK), yeniden deneme gibi şeyleri siz yönetirsiniz |
| Esneklik | API'de olmayan şeyler zor olabilir | Her MAVLink mesajına erişim, her şeyi kontrol |
| Ek maliyet | Ekstra süreç (`mavsdk_server`) | Yok (saf Python) |
| Uygun durum | Hızlı otonom uçuş senaryoları/prototip | Telemetri/log analizi, özel mesaj, ince ayar |

*(pymavlink'in ArduPilot ekibi tarafından sürdürüldüğü ve ArduPilot'a ağırlıklı odaklı olduğu bilgisi kaynağın sahipliğinden gelir [K5]; PX4 ile de MAVLink üzerinden kullanılabilir, ancak bu bağlamda ayrıca test edilmedi.)*

**c) Sürü sistemlerinde merkezi ve dağıtık kontrol**

| | Merkezi (yer istasyonu/lider planlar) | Dağıtık (her araç kendi karar verir, komşularla konuşur) |
|---|---|---|
| Koordinasyon | Kolay, global görüş | Zor; yerel bilgiye dayalı |
| Haberleşme | Hepsi merkezle konuşur (yıldız topoloji) | Araçlar arası (çoğunlukla yerel) |
| Ölçeklenebilirlik | Düşük: merkez darboğaz olur | Yüksek |
| Hata toleransı | Zayıf: merkez veya bağlantı kopunca tüm sürü etkilenir | Güçlü: tek bir araç kaybı sürüyü durdurmaz |
| Gecikme | Merkez üzerinden gidip gelmek gecikmeyi artırır | Yerel kararlar daha hızlı |
| Uygun durum | Küçük sürü, kontrollü ortam, görev planlama | Büyük sürü, bağlantısı güvenilmez ortam |

Bu görevdeki sistemde İHA'lar birbirleriyle doğrudan konuşamıyor ve veri YKİ üzerinden geçiyor (§7); yani mevcut mimari **merkezi/yıldız** bir yapıdır. Hibrit çözüm (merkez görev komutu verir, araçlar yerel güvenliği kendileri yönetir) pratikte sık tercih edilir.

---

### Soru 3 – Sürü koordinasyonu

**a) Tanımlar**
- **Leader–follower (lider–takipçi):** Bir araç lider seçilir; diğerleri lidere göre belirli göreli konumu korur. Liderin hareketi, formasyonu tanımlar.
- **Virtual structure (sanal yapı):** Formasyon, tek bir **katı sanal gövde** olarak düşünülür; her araç bu gövde üzerindeki bir "slot" noktasını izler. Sanal yapı hareket ettirilince tüm araçlar kendi slotlarına gitmeye çalışır [K12].
- **Behaviour-based (davranış tabanlı):** Her araç bir dizi basit davranışı (hedefe git, komşudan uzak dur, formasyonu koru, engelden kaçın) ağırlıklarla birleştirir; sürü davranışı bunların toplamından ortaya çıkar [K11][K13].

**Karşılaştırma**

| Ölçüt | Leader–follower | Virtual structure | Behaviour-based |
|---|---|---|---|
| Koordinasyon | Basit; formasyon hassasiyeti liderin hassasiyetine bağlı | Çok iyi, hassas formasyon | Esnek, hassasiyet daha düşük |
| Ölçeklenebilirlik | Orta | Düşük/orta (sanal yapı bilgisi paylaşılmalı) | Yüksek |
| Haberleşme ihtiyacı | Lider → takipçiler | Sanal yapı durumu herkese | Çoğunlukla yerel/komşu |
| Hata toleransı | **Lider kaybı kritik** | Yapı merkezi tutulursa tek hata noktası olabilir | **En dayanıklı** |
| Karmaşıklık | Düşük | Orta | Davranış ağırlıklarını ayarlamak zor, öngörülebilirlik düşük |

*(Karşılaştırma tablosu genel literatür bilgisine dayanır [K11][K12][K13]; her hücre ilgili kaynakta birebir doğrulanmadı.)*

**b) Basit sürü kaldırma operasyonu için önerim**
Yerden belirli bir yüksekliğe **koordineli** çıkış için **sanal yapı mantığına yakın, zaman/yükseklik planlı bir hibrit** öneririm: merkez (YKİ) ortak bir kalkış profili ve her araç için slot (yatay konum + yükseklik katmanı) tanımlar; araçlar bu profili kendi otopilotlarıyla izler ve yerel güvenlik davranışları (ayrım mesafesi, kayıp bağlantı) araçta çalışır.

Gerekçeler:
1. **Basitlik ve öngörülebilirlik:** Kalkış dikey ve önceden planlanabilir; hassas formasyon (sanal yapı) burada davranış tabanlı belirsizlikten daha değerlidir.
2. **Güvenli kalkış ve çarpışma önleme:** Her araca **farklı yükseklik katmanı veya farklı zaman aralığı** verilerek aynı hacmi aynı anda paylaşmaları önlenir; ayrıca her araçta minimum ayrım mesafesi kontrolü ("separation" davranışı) çalışır.
3. **Zamanlama:** Ortak bir "başla" komutu ve ortak zaman referansı (veya YKİ'den gelen aşama komutları: "hazır → kalk → sabit tut") senkronizasyonu sağlar. Hangi araç hazır değilse tüm sürü bekler (go/no-go).
4. **Haberleşme kaybı:** Çok kritik. Kalkış sırasında bir araç YKİ'den belirli süre mesaj alamazsa **kendi başına güvenli davranışa** geçmelidir (yerinde tutma/iniş). PX4'te veri bağlantısı kaybı zaman aşımı için `COM_DL_LOSS_T` parametresi vardır [K1]; hangi eylemin tetikleneceği ve varsayılanlar sürüme göre değiştiği için kullanılan PX4 sürümünün belgesine bakılmalıdır *(bu çalışmada doğrulanmadı)*.
5. **Neden saf lider–takipçi değil?** Lider arızalanırsa veya iletişim koparsa tüm sürü etkilenir; bu kalkışta kabul edilemez bir tek hata noktasıdır.

**Dezavantaj:** Merkeze bağımlılık; bu yüzden araç tarafındaki yerel güvenlik mantığı (kayıp bağlantı, ayrım mesafesi) mutlaka bulunmalı. Uygulama bu çalışmada yazılmadı/test edilmedi.

---

## 6. GNSS'siz konumlandırma ve görsel takip (PDF Bölüm 3)

### A. GNSS olmadan uçuş

**Uçabilir mi?** Evet; bir İHA, GNSS olmadan **uçabilir** (pilotun elle kontrol ettiği kararlı modlar, iç mekân uçuşları, yerel konum kestirimi sağlayan sistemlerle otonom uçuş). Ancak **otonom konum tabanlı modlar** için bir konum kestirimi gerekir. PX4 belgesi, otomatik uçuş modlarının (Mission, Return, Land, Hold, Orbit) normalde GNSS'ten gelen **global konum kestirimi** gerektirdiğini belirtir [K7]; GNSS yoksa yerel konum bilgisi başka kaynaklardan (görsel sistemler, optik akış vb.) sağlanmalıdır [K6][K7].

**GNSS destekli ve GNSS'siz farkları**

| | GNSS destekli | GNSS'siz |
|---|---|---|
| Konum | Mutlak (global) konum | Genellikle **göreli/yerel** (başlangıç noktasına göre) |
| Hata davranışı | Sınırlı (hata birikmez) | **Sürüklenme (drift)** zamanla birikir |
| Home/RTH | Doğrudan | Referans/harita veya özel mantık gerekir |
| Bağımlılık | Uydu görünürlüğü, parazit/sahteleme riski | Çevre dokusu, ışık, sensör kalitesi |
| Kurulum | Basit | Ek sensör ve hesaplama (VIO, optik akış, LiDAR) |

**Zorluklar:** Konum sürüklenmesi; sensörlerin çevreye duyarlılığı (karanlık, dokusuz zemin, camsı yüzey, toz); işlem yükü ve gecikme; ölçeğin kestirimi (tek kamerada); koordinat çerçevelerinin (yön/heading) eşleştirilmesi (PX4 belgesi, dış sistemin referans çerçevesi ile kestirici çerçevesinin yönünün çoğu zaman uyuşmadığını belirtir [K7]); ve mutlak referans olmadığı için görev/geri dönüş konumunun tanımı.

### B. Konum ve oryantasyon kestirimi

**Önemli ilke:** Tek bir sensör tek başına **mutlak konum** sağlamaz (bilinen bir referans/harita yoksa); çoğu yöntem göreli ölçüm verir. Bu yüzden **sensör füzyonu** (ör. genişletilmiş Kalman filtresi) kullanılır. PX4'ün varsayılan kestiricisi EKF2'dir [K7].

| Yöntem/sensör | Ne sağlar? | Sınırlamalar | Neyle birleştirilir? |
|---|---|---|---|
| **IMU** (ivmeölçer + jiroskop) | Yönelim (jiroskop entegrasyonu), ivme | Entegrasyon hatası hızla büyür (konum için çift entegrasyon), yaşlanma/sapma | Her şeyle; filtrenin temeli |
| **Manyetometre** | Yön (heading) | Metal/motor/manyetik parazit | IMU, görsel yön |
| **Barometre** | Göreli yükseklik | Hava/sıcaklık/pervane akımı etkisi, sürüklenme | IMU, mesafe sensörü |
| **Optik akış** | **2B hız** (aşağı bakan kamera + mesafe sensörü ile) [K6] | Dokusuz/karanlık zemin, mesafe sensörü şart; konum sürüklenir | IMU, mesafe sensörü |
| **Kamera tabanlı görsel odometri (VO)** | Ardışık karelerden **göreli hareket** [K9] | Tek kamerada ölçek belirsizliği; hızlı hareket/bulanıklık; birikimli sürüklenme | IMU (→ VIO), stereo/derinlik |
| **VIO** | Kamera + IMU ile 3B pozisyon, yönelim ve hız; **başlangıç noktasına göre** [K6][K10] | İyi aydınlatma/doku ister; başlatma ve kalibrasyon hassas | EKF2'ye dış görüş verisi olarak [K7] |
| **Visual SLAM** | Eş zamanlı **harita + konum**; aynı yeri tekrar görünce (loop closure) sürüklenmeyi düzeltir [K8][K14] | Hesaplama yükü; dinamik nesnelerde zorlanır | IMU, derinlik |
| **LiDAR / derinlik sensörü** | Mesafe, engel, yükseklik; tarama eşleştirme ile göreli hareket | Ağırlık/güç/maliyet; yansıtıcı/saydam yüzeyler | IMU, kamera |
| **Sensör füzyonu (EKF)** | Hepsini tutarlı bir tahminde birleştirir | Yanlış gürültü modeli/zaman uyumsuzluğu tahmini bozar | — |

PX4 belgesine göre VIO, 3B pozu ve hızı **yerel başlangıca göre** tahmin eder; optik akış ise aşağı bakan kamera ve mesafe sensörüyle **2B hız** verir. Belge, GNSS'siz dış mekân için VIO'yu; yalnız iç mekân ve düşük maliyet için optik akışı önerir [K6]. Dış konum bilgisinin EKF2'ye MAVLink mesajlarıyla verildiği ve mesaj hızı çok düşükse EKF2'nin bu veriyi kullanmayacağı da belgededir [K7].

### C. Görüntü bilgisinden uçuş komutlarına (görsel hedef takibi)

**Çerçeve:** Bu bölüm yalnızca **güvenli, simülasyon bağlamında genel görsel hedef takibini** anlatır. Amaç, hedefe zarar vermek veya engellemek değil, hedefi görüntüde tutup **güvenli bir göreli mesafeyi** korumaktır. Görüntüdeki konum, gerçek dünya koordinatı **değildir**; bounding box boyutu da tek başına **kesin mesafe vermez** (aşağıda açıklanmıştır).

Girdi: kutu merkezi (c_x, c_y), kutu eni w, boyu h; görüntü genişliği W, yüksekliği H.

**Adım 1 – Hedef merkezi.** Kutu merkezi doğrudan (c_x, c_y) alınır. Piksel koordinatında y ekseni **aşağı** doğrudur.

**Adım 2 – Hatalar.**
```
e_x = c_x − W/2      (pozitif: hedef sağda)
e_y = c_y − H/2      (pozitif: hedef aşağıda)
```
Normalleştirme (ör. e_x/(W/2) ∈ [−1, 1]) kazançları çözünürlükten bağımsız yapar. Açıya çevirmek için §3'teki model kullanılır (doğrusal ya da `atan(e/f)`); dikey açı için dikey FoV veya `f_y` gerekir (PDF vermiyor; kare piksel varsayımıyla `f_y = f_x` alınabilir, **doğrulanması gerekir**).

**Adım 3 – Kutu boyutu ve göreli yakınlık.** Pinhole modelinde bir cismin görüntü boyutu mesafeyle ters orantılıdır: `h ≈ f · H_gerçek / Z`. Bu nedenle kutu *büyüdükçe hedef yaklaşıyor*, *küçüldükçe uzaklaşıyor* denebilir. Ancak:
- Gerçek boyut `H_gerçek` bilinmiyorsa **mutlak mesafe bulunamaz**.
- Hedefin duruşu/dönüşü, kısmi görünürlük ve dedektör kutu gürültüsü boyutu değiştirir.
- Bu yüzden mutlak mesafe yerine **göreli boyut hatası** kullanmak daha sağlamdır: `e_s = (h_ref − h) / h_ref` (h_ref: istenen boyuttaki kutu). Pozitif `e_s` hedef çok uzakta demektir.

**Adım 4 – Hataları komuta çevirme (gövde çerçevesinde):**

| Hata | Komut | Not |
|---|---|---|
| e_x (sağ/sol) | **Yaw hızı** (kamerayı hedefe çevir) veya yanal hız | Yaw tercih edilirse kamera hedefi merkezde tutar |
| e_y (yukarı/aşağı) | **Dikey hız** | Görüntü y aşağı olduğu için işaret ters çevrilir |
| e_s (yakınlık) | **İleri/geri hız** | Hedef küçülürse yaklaş, çok büyürse uzaklaş/dur |

**Adım 5 – PID'nin rolü.** Her kanal için basit bir PD/PID kontrolcü: `komut = Kp·e + Ki·∫e + Kd·de/dt`.
- **P:** hatayla orantılı düzeltme.
- **D:** hatanın değişimini söndürerek aşmayı azaltır; gürültüye duyarlıdır, bu yüzden filtrelenmiş türev kullanılır.
- **I:** kalıcı hatayı giderir, fakat doyum (integral windup) riski taşır; sınırlandırma ve anti-windup gerekir. Birçok görsel takip uygulamasında P veya PD yeterlidir.
Kazançlar simülasyonda ayarlanır; kamera gecikmesi arttıkça kazanç düşürülmelidir.

**Adım 6 – Sınırlama, filtreleme, gecikme, hedef kaybı.**
- **Sınırlama:** Maksimum hız/yaw hızı, ivme (rate limiter) ve ölü bölge (deadband) ile titremeyi önle.
- **Filtreleme:** Kutu merkezini/boyutunu düşük geçiren filtre veya Kalman filtresiyle yumuşat; Kalman, kısa süreli ölçüm kaybında hedefi **tahmin** de edebilir.
- **Gecikme:** Görüntü yakalama → işleme → komut arasındaki gecikme (§7) kararlılığı bozar; ölçüm zaman damgası kullanılmalı, gerekirse kestirimle telafi edilmeli, kazanç düşürülmelidir. Aracın kendi dönmesi görüntü konumunu da değiştirir; IMU'dan yönelim bilgisiyle telafi edilebilir.
- **Hedef kaybı:** Birkaç kare için son tahmini kullan; süre dolarsa komutları **yumuşakça sıfıra** indir, aracı sabit tut ve arama davranışına (ör. yavaş yaw) geç; belirli süre bulunamazsa güvenli duruma (bekleme/dönüş) geç.
- **Güvenlik sınırları:** Minimum güvenli mesafe, hız/ivme/yükseklik sınırı, geofence ve operatör müdahalesi (kolayca iptal/moda dönüş) şart.

**Adım 7 – Döngü ve kararlılık.** Her yeni kutu geldiğinde adımlar tekrarlanır. Kararlılık için: sabit ve ölçülmüş bir döngü frekansı, bütün gecikmelerin hesabı, kazançların kademeli artırılması (önce simülasyon), saturasyonlar ve hata-bayrağı (watchdog) mantığı gerekir. Otonom hız komutlarını PX4'e göndermek için sürekli akış (offboard tarzı kontrol) kullanılabilir; bunun için gerekli minimum komut hızı ve zaman aşımı davranışı kullanılan PX4 sürümü belgesinden **doğrulanmalıdır** (bu çalışmada doğrulanmadı).

Bu anlatım yalnızca kavramsal bir tasarımdır; kod yazılmadı ve test edilmedi.

---

## 7. Sistem mimarisi, gecikme ve jitter analizi (PDF Bölüm 4)

> **Yöntem notu:** Bu bölüm gerçek ölçüm içermez. Her madde bir **hipotez** ve **nasıl doğrulanacağının planıdır**. "Düşünme sürecim" = gözlemlenebilir mühendislik yaklaşımı: sistemi ayır → her aşamayı ölç → en büyük gecikme/titreşim kaynağına öncelik ver → bir değişiklik yap → tekrar ölç.

### 7.1 Sistemi bileşenlerine ayırma

```
[1] İHA1 Kamera → [2] İHA1 Bilgisayarı: yakalama tamponu
      → [3] Görüntü işleme (bounding box) → [4] Mesaj üretme/gönderme
      → [5] Wi-Fi (yukarı hat) → [6] YKİ (al, işle, ilet)
      → [7] Wi-Fi (aşağı hat) → [8] İHA2 Bilgisayarı (al, ayrıştır)
      → [9] Seri/UDP bağlantısı → [10] İHA2 otopilot kartı
```

Toplam gecikme **toplamdır**: `T = Σ T_i`. Jitter ise bileşenlerin bağımsız olduğu varsayımıyla varyansların toplamı (`σ² = Σ σ_i²`) gibi büyür; pratikte kuyruk (p99) daha da kötü olabilir. Kayıp da bileşiktir: iki Wi-Fi hattında kayıp olasılıkları p₁ ve p₂ ise mesajın ulaşma olasılığı `(1−p₁)(1−p₂)`. (Örnek hesap: her hat %5 kayıpsa ≈ %90.25.)

**Önemli gözlem (hesapla):** Sınırlayıcı kutu mesajı küçüktür. Örneğin kutu merkezi, en, boy, güven, sınıf, sıra no ve zaman damgasından oluşan sabit bir ikili (binary) mesaj kabaca **birkaç on bayttır**; 30 Hz'de saniyede yaklaşık **1 KB** eder. Ham bir 640×480 RGB kare ise 921.600 bayttır. Dolayısıyla *bant genişliği* bu mesaj için sorun olmaz; asıl sorun **erişim gecikmesi, yeniden iletim, kuyruklar ve zamanlama düzensizliğidir**. Bu yüzden "mesajı küçült" önceliği düşüktür; ancak görüntünün kendisini YKİ'ye akıtıyorsanız durum tamamen değişir.

### 7.2 Önceliklendirilmiş inceleme sırası

Sıralama **hipotezdir**; ölçümler sırayı değiştirebilir.

| Öncelik | Bileşen | Neden önce? |
|---|---|---|
| 0 | **Ölçüm altyapısı** (zaman damgası, sıra no) | Ölçemediğin şeyi iyileştiremezsin; diğer her adımı mümkün kılar |
| 1 | **Wi-Fi hatları (×2) ve YKİ yönlendirmesi** | Genellikle en yüksek değişkenlik: parazit, yeniden iletim, kanal yoğunluğu; iki ardışık hat |
| 2 | **Kuyruklar ve tamponlar** (kamera/yakalama, işleme hattı, soketler, YKİ) | Eski verinin yeni verinin önüne geçmesi, gecikmeyi kalıcı biçimde büyütür |
| 3 | **Görüntü işleme süresi ve yükü** | Büyük ve değişken olabilir (GPU/CPU yükü, termal kısıtlama) |
| 4 | **Kamera kare hızı ve yakalama gecikmesi** | Tabanı belirler (ör. 30 fps → 33 ms kare aralığı) |
| 5 | **Taşıma protokolü seçimi (TCP/UDP) ve mesaj biçimi** | Kayıp durumunda davranışı belirler |
| 6 | **İHA2 tarafı: bilgisayar → otopilot hattı** | Genelde küçük ve kararlı, ama bitmeden doğrulanmalı |

Bu sıranın gerekçesi: (i) önce **ölçüm** (0), (ii) sonra **büyük ve değişken** kaynaklar (1–3), (iii) en son **sabit/küçük** olanlar (4–6). Wi-Fi'yi başa koymam varsayımdır; işlem süresi ölçülürse ve ağır çıkarsa 3 öne geçer.

### 7.3 Bileşen bileşen analiz

Her bileşen için: neden önemli, nasıl ölçülür, iyileştirme, dezavantaj, diğerleriyle ilişki.

#### 0) Ölçüm altyapısı (zaman damgaları, sıra numarası)
- **Neden:** Gecikmenin hangi aşamada oluştuğunu görmeden iyileştirme körlemesine olur.
- **Nasıl:** Her mesaja `seq` (sıra no) ve `t_capture` (kare yakalama anı, mümkünse kamera/sürücü zaman damgası) ekle; YKİ `t_rx`, `t_tx` ekler; İHA2 `t_rx_uav2`, `t_to_autopilot` ekler. **Monotonik saat** kullan. Uçtan uca *tek yönlü* gecikme için saatler senkron olmalı (NTP/chrony/PTP); aksi halde yalnızca aynı makinedeki farklar (ör. YKİ girişi–çıkışı) ve gidiş-dönüş süresi (RTT) güvenilir sayılır. **Yaş (age)** = `şimdi − t_capture` ölçüsü, "karar anında veri ne kadar eski" sorusunun cevabıdır.
- **İyileştirme:** Küçük, sabit başlıklı bir telemetri kaydı; günlükleme (log) ve otomatik rapor.
- **Dezavantaj:** Ek yük (küçük), saat senkronizasyonu hatası ölçümü yanıltabilir.
- **İlişki:** Tüm diğer bileşenlerin ölçümünün temeli.

**Hangi ölçütler?** Ortalama tek başına yanıltıcıdır. Gecikme dağılımı için **medyan (p50), p95, p99, maksimum** ve histogram; jitter için hem standart sapma hem de RTP'de tanımlı **RFC 3550 interarrival jitter**: `J ← J + (|D| − J) / 16`, burada `D` ardışık iki paketin varış aralığı ile gönderim aralığı farkıdır [K16] *(formül, RFC metninin alıntılandığı ikincil kaynaklardan doğrulandı; RFC'nin birincil sayfası açılmadı)*. Ayrıca **kayıp oranı**, **sıra bozulması** (seq atlamaları) ve **yaş** ölçülür. Kontrol için en önemli şey çoğu zaman **p99 gecikme ve yaş**dır; çünkü kontrolcü en kötü anlara göre tasarlanır.

#### 1) Wi-Fi hatları (iki hat) ve YKİ
- **Neden:** Kablosuz ortak ortamdır: kanal yoğunluğu, parazit (komşu ağlar, Bluetooth, mikrodalga, diğer drone Wi-Fi'ları), zayıf sinyal, çoklu yol, MAC katmanı yeniden iletimleri ve hız adaptasyonu **değişken gecikme (jitter) ve kayıp** üretir. **İki ardışık hat** (İHA1→YKİ, YKİ→İHA2) gecikmeyi ve kaybı bileşik yapar. YKİ tek bir **toplanma noktasıdır**: yükü, işletim sistemi zamanlaması ve ağ kartı ayarları sonuca yansır. *(İki hattın aynı erişim noktası/kanal üzerinden geçip geçmediği PDF'de belirtilmemiş; aynı kanaldaysa yukarı ve aşağı akış havayı paylaşır ve birbirini yavaşlatabilir.)*
- **Nasıl ölçülür:** (a) Sürekli `ping` ile RTT dağılımı; (b) UDP trafik testi (ör. `iperf3 -u`) ile jitter ve kayıp *(araç özellikleri genel bilgidir, bu çalışmada doğrulanmadı)*; (c) kendi `seq/timestamp`li prob paketleri ile **her hattı ayrı** ölç; (d) Wi-Fi sinyal gücü (RSSI), kanal doluluğu, yeniden iletim sayaçlarını kaydet; (e) uçuş sırasındaki hareket/mesafe ile korelasyona bak.
- **İyileştirme:** Daha az kalabalık kanal (ör. 5 GHz, boş kanal), anten yerleşimi/mesafe, sabit iletim gücü ve hız ayarı, güç tasarrufu modunu kapatma, QoS/öncelik, **tek yönlü** hat için uygun ağ topolojisi, gerekiyorsa daha uygun bir telemetri radyosu.
- **Dezavantaj:** 5 GHz'in menzili/duvar geçişi kısadır; sabit hız/güç batarya ve uyumluluğu etkiler; ağ kartı ayarları sürücüye bağlıdır.
- **İlişki:** Kuyruklar (2) ve protokol (5) ile iç içe: kablosuz kayıp TCP'de kuyruğu büyütür; UDP'de veri kaybı olur.

#### 2) Kuyruklar ve tamponlar
- **Neden:** Bir aşama diğerinden yavaşsa tamponlar dolar ve **eski veri güncel verinin önüne geçer**; sistem "çalışıyor ama 2 sn geriden geliyor" hâline gelir. Kamera yakalama tamponu, işleme kuyruğu, soket tamponları ve YKİ yeniden iletim kuyruğu tipik yerlerdir.
- **Nasıl ölçülür:** Kuyruk uzunluğunu ve her mesajın **kuyrukta geçirdiği süreyi** günlükle; **yaş** metriğini her aşamada hesapla; frame drop sayısı ve seq sıçramaları.
- **İyileştirme:** **Sınırlı kuyruk (boyut 1–2) ve "en yeniyi tut" politikası** (eskiyi at), yakalama tamponunu küçült, TCP kullanılıyorsa Nagle'ı kapat (`TCP_NODELAY`), soket gönderme/alma tamponlarını makul tut, yeni veri geldiğinde eski kutuyu **yok say** (seq karşılaştırması).
- **Dezavantaj:** Eskiyi atmak bazı mesajların kaybı demektir; kutu serisi seyrelir. Kontrol tarafı bu seyrekliği tolere edecek şekilde (tahmin/filtre) tasarlanmalı.
- **İlişki:** Ağ hatlarındaki (1) kayıp/yavaşlamayı **birikimli gecikmeye** çeviren veya önleyen katmandır. En ucuz ve etkili iyileştirmelerden biridir.

#### 3) Görüntü işleme süresi ve işlemci/GPU yükü
- **Neden:** Nesne dedektörü kare başına onlarca ms alabilir; süre sabit değildir (GPU/CPU yükü, termal kısıtlama, diğer süreçler). Yük arttıkça kare atlanır, gecikme ve jitter artar.
- **Nasıl ölçülür:** Her karede `t_capture`, `t_infer_start`, `t_infer_end` kaydet; **süre dağılımını** (p50/p95/p99) çıkar; CPU/GPU kullanımı, sıcaklık ve saat frekansı kayıtları; işlem süresi ile yük korelasyonu.
- **İyileştirme:** Daha hafif/niceliklendirilmiş (quantized) model, daha düşük giriş çözünürlüğü, ilgi alanı kırpma, donanım hızlandırma, işlem hattının **asenkron** ve tamponsuz olması, süreç öncelikleri ve çekirdek bağlama.
- **Dezavantaj:** Doğruluk düşebilir (küçük model/düşük çözünürlük); termal sınırlama sistemin başka kısımlarını etkileyebilir.
- **İlişki:** Kamera hızı (4) ile uyumlu olmalı (işlem süresi kare aralığından uzunsa kuyruk (2) büyür); çıktı hızı ağ yüküne (1) doğrudan yansır.

#### 4) Kamera kare hızı ve yakalama gecikmesi
- **Neden:** Tabanı belirler: 30 fps → kareler arası ≈ 33.3 ms; pozlama, sensör okuma ve ISP/USB/CSI aktarımı da ek gecikme katar. Düşük ışıkta pozlama uzar, kare hızı düşebilir.
- **Nasıl ölçülür:** Kare zaman damgaları arasındaki aralık dağılımı (kare düşürme, düzensizlik); mümkünse "cam-to-algorithm" gecikmesini (ör. ekranda bir olayı gösterip yakalanma anıyla karşılaştırma).
- **İyileştirme:** Uygun kare hızı/pozlama (sabit pozlama), uygun arabirim ve sürücü ayarları, global shutter *(hızlı hareketlerde bulanıklık/çarpıklık azaltır)*.
- **Dezavantaj:** Yüksek kare hızı işlem yükünü ve ağ yükünü artırır; kısa pozlama düşük ışıkta gürültü artırır.
- **İlişki:** Dedektör yükü (3) ve kuyruklarla (2) birlikte ayarlanmalı: kamera hızı, işlemin yetişebileceği hızdan yüksekse tampon dolar.

#### 5) Taşıma protokolü (TCP/UDP) ve mesaj biçimi
- **TCP:** Güvenilir ve sıralıdır; ancak kayıp olunca **yeniden iletim** ve **sıra-başı bloklaması (head-of-line blocking)** yüzünden sonraki (daha yeni) mesajlar da **bekler**; yani gecikme ve jitter artar [K17]. Gerçek zamanlı kutu verisi için bu istenmeyen bir davranıştır: yeniden gönderilen eski kutunun faydası genelde yoktur, çünkü yenisi zaten gelmiştir.
- **UDP:** Yeniden iletim/sıralama yoktur; kayıp **tolere edilir**, gecikme düşük kalır [K17]. Bedeli: kayıp ve sıra bozulmasını **uygulama katmanında** (seq numarası, zaman damgası, "eskiyi at") yönetmek gerekir. Kutu verisi gibi **sık ve her mesajın kendisini geçersiz kıldığı** akışlar için uygundur. Başlat/iptal gibi **mutlaka ulaşması gereken** komutlar için ise onaylı (ACK) ve yeniden denemeli ayrı bir kanal tercih edilir (MAVLink'in komut protokolü bu mantıkla çalışır [K2]).
- **Mesaj biçimi:** Küçük, sabit uzunluklu ikili kayıt (örn. `seq, t_capture, cx, cy, w, h, conf`); JSON/metin daha okunur ama daha büyük ve ayrıştırması daha yavaştır. Ancak §7.1'e göre bant genişliği asıl darboğaz değildir; biçim kararı daha çok **ayrıştırma maliyeti ve sürüm/doğrulama** açısından önemlidir.
- **Nasıl ölçülür:** Aynı koşulda TCP ve UDP ile gecikme p95/p99, yaş ve kayıp karşılaştırması; kayıp enjeksiyonu (ağ emülasyonu) ile davranış testi.
- **Dezavantaj:** UDP'de veri kaybı kontrolcüye yansır, filtre/tahmin gerekir; ikili biçim hata ayıklamayı zorlaştırır.
- **İlişki:** Kuyruk (2) ve Wi-Fi (1) ile doğrudan bağlantılı: Wi-Fi kaybı arttıkça TCP'nin dezavantajı büyür.

#### 6) İHA2 tarafı: bilgisayar → otopilot
- **Neden:** Son adımdır; seri bağlantı hızı, ayrıştırma ve komut oranı burada sınırlanır. Örneğin 57600 baud'da bayt başına ≈ 10 bit → ≈ 5760 B/s; 50 baytlık bir MAVLink mesajı ≈ 8.7 ms sürer (aritmetik hesap). 921600 baud'da ihmal edilebilir.
- **Nasıl ölçülür:** `t_rx_uav2` ile otopilota yazma anı arasındaki fark; otopilot tarafında mesajın alındığını doğrulayan günlükler.
- **İyileştirme:** Yüksek baud/UDP, mesaj sıklığını kontrol döngüsüne uydurma, eski mesajı atma.
- **Dezavantaj:** Yüksek baud hızı kablolama/EMI kaynaklı hataya daha duyarlı olabilir.
- **İlişki:** Kontrol kararlılığı (§6C) bu hattın toplam gecikmesine duyarlıdır.

### 7.4 Genel uygulama planı (öncelik sırasıyla)
1. Her mesaja `seq` + `t_capture` ekle; her aşamada zaman damgasını kaydet (bileşen 0).
2. İki Wi-Fi hattını ve YKİ'yi ayrı ayrı ölç: RTT/jitter/kayıp dağılımı, p50/p95/p99, yaş.
3. Her tamponda sınırlı kuyruk + "en yeni kazanır" uygula; etkiyi tekrar ölç.
4. Dedektör süre dağılımını ve yükü incele; gerekiyorsa modeli/çözünürlüğü küçült.
5. Kamera kare hızı/pozlama ve işleme hızı uyumunu doğrula.
6. TCP'ye karşı UDP+seq deneyi; kritik komutlar için ayrı onaylı kanal.
7. Hepsini bir arada, farklı yük/mesafe/parazit altında, **önce simülasyonda/sabit zeminde** tekrar test et.

**Varsayımlar / doğrulanması gerekenler:** (1) Wi-Fi'nin baskın darboğaz olduğu varsayımı ölçümle doğrulanmalı. (2) İki hattın aynı kanal/AP'yi paylaşıp paylaşmadığı. (3) YKİ'nin yalnızca iletici mi, yoksa veriyi dönüştüren/yeniden kodlayan bir bileşen mi olduğu. (4) Saat senkronizasyonu yöntemi. (5) Hedef gecikme bütçesi (ms) ve kabul edilebilir kayıp oranı görev tarafından belirlenmeli.

---

## 8. Kaynakça ve doğrulama durumu

**Doğrulama notu:** Aşağıdaki "Doğrulama" sütunu **bu çalışma sırasında** ne yapıldığını gösterir. "Açıldı/okundu" = web araması sonucunda içerik gerçekten döndü. "Açılmadı" = kaynak gerçek ve iyi bilinen bir yayındır, ancak bu çalışmada içeriği ya da bağlantıyı **doğrudan doğrulayamadım**; teslimden önce kontrol edilmelidir. Hiçbir kaynağa, içeriğinde bulunmadığını düşündüğüm bir iddia atfedilmemeye çalışıldı; yine de her cümle bire bir kontrol edilmedi.

### Resmî dokümantasyon

| No | Kaynak | Yayımlayan | Bağlantı | Kullanıldığı yer | Doğrulama |
|---|---|---|---|---|---|
| K1 | PX4 User Guide – *Simulation* | PX4 / Dronecode | https://docs.px4.io/main/en/simulation/ | Soru 1, Soru 3b (COM_DL_LOSS_T) | **Okundu** (arama sonucu içeriği). Sürüm farkları olabilir (main/v1.15/v1.16) |
| K2 | PX4 User Guide – *MAVLink Messaging* | PX4 / Dronecode | https://docs.px4.io/main/en/mavlink/ | Soru 2a, §7.3(5) | **Okundu** |
| K3 | *MAVLink Developer Guide* | MAVLink / Dronecode | https://mavlink.io/en/ | Soru 2a | **Okundu** |
| K4 | *MAVSDK* (README ve dokümantasyon) | MAVSDK / Dronecode | https://github.com/mavlink/MAVSDK (belge sitesi: https://mavsdk.mavlink.io/) | Soru 2b | README içeriği **fork/yansılar üzerinden okundu**; resmî depo ve belge sitesi doğrudan açılmadı |
| K5 | *pymavlink* | ArduPilot | https://github.com/ArduPilot/pymavlink | Soru 2b | **Okundu** |
| K6 | PX4 User Guide – *Computer Vision (Optical Flow, MoCap, VIO, Avoidance)* | PX4 / Dronecode | https://docs.px4.io/main/ko/advanced/computer_vision.html (aynı sayfanın İngilizce sürümü: .../main/en/... yolu değişmiş olabilir) | §6A–B | **Okundu** (Korece/Çince sayfa içeriği; İngilizce bölümler aynıydı). İngilizce URL doğrulanmadı |
| K7 | PX4 User Guide – *External Position Estimation* | PX4 / Dronecode | https://docs.px4.io/main/zh/ros/external_position_estimation.html | §6A–B | **Okundu** (zh sayfa; ilgili bölümler İngilizce). İngilizce URL doğrulanmadı |

### Akademik ve standart kaynaklar (bu çalışmada **açılmadı**; hafızadan, teslimden önce DOI'leri kontrol edin)

| No | Kaynak | Yayımlayan/Yazar | Bağlantı | Kullanıldığı yer |
|---|---|---|---|---|
| K8 | *Past, Present, and Future of Simultaneous Localization and Mapping* | Cadena ve ark., IEEE Trans. Robotics 32(6), 2016 | https://doi.org/10.1109/TRO.2016.2624754 | SLAM (§6B) |
| K9 | *Visual Odometry [Tutorial]* | Scaramuzza & Fraundorfer, IEEE Robotics & Automation Magazine 18(4), 2011 | https://doi.org/10.1109/MRA.2011.943233 | Görsel odometri (§6B) |
| K10 | *VINS-Mono: A Robust and Versatile Monocular Visual-Inertial State Estimator* | Qin, Li, Shen, IEEE Trans. Robotics 34(4), 2018 | https://doi.org/10.1109/TRO.2018.2853729 | VIO (§6B) |
| K11 | *A Survey on Aerial Swarm Robotics* | Chung, Paranjape, Dames, Shen, Kumar, IEEE Trans. Robotics 34(4), 2018 | https://doi.org/10.1109/TRO.2018.2857475 | Soru 3 |
| K12 | *High Precision Formation Control of Mobile Robots Using Virtual Structures* | Lewis & Tan, Autonomous Robots 4, 1997 | https://doi.org/10.1023/A:1008814708459 | Soru 3a (virtual structure) |
| K13 | *Behavior-Based Formation Control for Multirobot Teams* | Balch & Arkin, IEEE Trans. Robotics and Automation 14(6), 1998 | https://doi.org/10.1109/70.736776 | Soru 3a (behaviour-based) |
| K14 | *ORB-SLAM2: An Open-Source SLAM System for Monocular, Stereo, and RGB-D Cameras* | Mur-Artal & Tardós, IEEE Trans. Robotics 33(5), 2017 | https://doi.org/10.1109/TRO.2017.2705103 | Visual SLAM (§6B) |
| K16 | *RTP: A Transport Protocol for Real-Time Applications* (RFC 3550) | IETF | https://www.rfc-editor.org/rfc/rfc3550 | Jitter tanımı (§7.3) |
| K17 | *User Datagram Protocol* (RFC 768); *Transmission Control Protocol (TCP)* (RFC 9293) | IETF | https://www.rfc-editor.org/rfc/rfc768 ; https://www.rfc-editor.org/rfc/rfc9293 | TCP/UDP farkları (§7.3) |

K16 için: jitter formülü (`J = J + (|D| − J)/16`) RFC metninden alıntılayan ikincil kaynaklarda (Wireshark e-posta listesi, ns-3 belgesi) görüldü; RFC'nin kendi sayfası açılmadı. K17'deki "sıra-başı bloklaması" ifadesi RFC'de bu adla geçmeyebilir; TCP'nin sıralı teslim ve yeniden iletim özelliğinden çıkan **genel mühendislik yorumudur**. Sürü yöntemlerinin karşılaştırma tablosu (§5, Soru 3) genel literatür bilgisidir.

---

## 9. Sınırlamalar ve açık noktalar
- Kod yalnızca **Linux** üzerinde (Python 3.12.3) test edildi; Windows ve WSL talimatları yazıldı ama denenmedi.
- PX4 SITL, MAVSDK, pymavlink, ROS 2, kamera veya gerçek İHA ile **hiçbir test yapılmadı**.
- Gecikme/jitter bölümü gerçek ölçüm içermez; öncelik sırası bir hipotezdir.
- Akademik kaynaklar (K8–K14) ve RFC'ler (K16–K17) bu çalışmada açılmadı; DOI/başlıklar doğrulanmalıdır.
- PX4'ün offboard komut hızı ve veri bağlantısı kaybı eylemleri gibi sürüme bağlı ayrıntılar doğrulanmadı.
