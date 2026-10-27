"""Uji gerbang manual + tombol HUD.

Menjalankan scan.py --page 1 --max-pages 2 dengan `wait_gate` yang disimulasikan
seolah-olah user menekan tombol LANJUT di HUD, lalu menyimpan screenshot
saat status gerbang tampil.

    OV_NO_WDA=1 python _tmp_test_gate.py
"""
import os
import sys
import time

from PIL import ImageGrab

import scan

shots = {"n": 0}
gates = {"n": 0}
orig_wait = scan.CTRL.wait_gate


def fake_wait(poll=0.15):
    gates["n"] += 1
    print(f"[simulasi] gerbang #{gates['n']} -> tampil status, lalu tekan LANJUT")
    time.sleep(1.6)                      # beri waktu HUD menampilkan status
    p = f"output/debug/gate{gates['n']}.png"
    ImageGrab.grab().save(p)
    print(f"[simulasi] screenshot tersimpan: {p}")
    scan.CTRL.gate.set()                 # "menekan" tombol LANJUT
    return orig_wait(poll)


scan.CTRL.wait_gate = fake_wait

sys.argv = ["scan.py", "--page", "1", "--max-pages", "2"]
rc = scan.main()
print(f"return={rc} gerbang_dipakai={gates['n']} excluded={scan.CTRL.stop.is_set()}")
print("HASIL:", "OK" if rc == 0 and gates["n"] == 1 else "PERIKSA LAGI")
