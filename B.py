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
