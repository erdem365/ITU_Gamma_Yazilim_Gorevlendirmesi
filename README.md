# İTÜ Gamma Takımı – Yazılım Ekibi Görevlendirmesi

İki ayrı Python sürecinin (A.py = gönderici, B.py = alıcı) TCP soketiyle haberleşmesi ve
görüntüdeki hedef x koordinatından yatay sapma açısının hesaplanması. Teorik cevaplar `RAPOR.md` içindedir.

## Gereksinimler
- Python **3.8 veya üzeri** (Python 3.12.3 / Linux üzerinde test edildi)
- **Harici paket yok** (`requirements.txt` yalnızca bunu belirten bir nottur; `pip install` gerekmez)

## Dosyalar
| Dosya | Açıklama |
|---|---|
| `A.py` | Gönderici ("Görüntü İşleme Simülatörü"): `input()` ile sayı alır, B.py'ye yollar |
| `B.py` | Alıcı ("Uçuş Kontrolcüsü"): sayıyı alır, yazdırır / sapma açısını hesaplar |
| `RAPOR.md` | Yöntem gerekçesi, formül türetimi, testler, teorik cevaplar, kaynakça |

## Çalıştırma (iki ayrı terminal gerekir)

**Önce B.py (alıcı), sonra A.py (gönderici)** başlatılır. (A.py, B.py henüz açılmadıysa 10 kez, 1 sn arayla yeniden dener.)

### Linux / macOS / WSL
```bash
# Terminal 1
python3 B.py            # 2. aşama (varsayılan)
# Terminal 2
python3 A.py
```

### Windows (CMD veya PowerShell)
```bat
:: Terminal 1
py B.py
:: Terminal 2
py A.py
```
(`py` çalışmazsa `python` deneyin. WSL kullanıyorsanız iki terminali de aynı WSL ortamında açın.)

### 1. aşama (yalnızca sayı gönder/al)
```bash
python3 B.py --stage 1
python3 A.py --stage 1
```
B.py çıktısı: `Alınan sayı: 42`

### 2. aşama (varsayılan)
A.py'ye `0–640` arasında x koordinatı yazın. B.py çıktısı:
```
Alınan piksel: 400, Hesaplanan Sapma: 10.00 derece
```
Çıkış: A.py'de `q` (veya Ctrl+C / Ctrl+D). B.py'yi durdurmak için Ctrl+C.

## Sorun giderme
- `B.py ... dinlenemedi`: 5005 portu doluysa (ör. başka bir B.py açık) onu kapatın ya da `A.py` ve `B.py` içindeki `PORT` değerini **ikisinde de** değiştirin.
- `A.py: B.py'ye bağlanılamadı`: B.py çalışmıyor demektir; önce B.py'yi başlatın.
- Güvenlik duvarı uyarısı çıkarsa yalnızca yerel (127.0.0.1) bağlantı kullanıldığını unutmayın; dışarıya açmaya gerek yoktur.

## Test durumu
Testler Linux (Python 3.12.3) üzerinde gerçekten ayrı süreçlerle çalıştırıldı. **Windows ve gerçek donanım/İHA üzerinde test edilmedi.** Ayrıntı: `RAPOR.md` §4.
