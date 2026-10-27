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
