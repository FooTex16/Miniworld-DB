"""Uji overlay.

  OV_NO_WDA=1 python _tmp_test_overlay.py   -> HUD ikut terekam (cek tampilan)
  python _tmp_test_overlay.py               -> WDA aktif (cek capture aman)
"""
import os
import time

import numpy as np
from PIL import ImageGrab

from overlay import Ctrl, Overlay


def main():
    ctrl = Ctrl()
    ov = Overlay(ctrl=ctrl)
    time.sleep(0.8)

    ov.set(cat="Blocks > Terrain", page=1, cell=(0, 3),
           phase="scan halaman 1 - melacak ikon block...",
           counts={"done": 12, "dup": 3, "lock": 1, "fail": 0, "skip": 0,
                   "page_done": 30, "page_total": 40},
           bid=200402, name="Grass [草原]", ocr="Grass",
           btn="gate",
           recent=["200402  Grass", "11422   Dirt", "333     Stone",
                   "200391  Sand", "350     Water"])
    ov.set_grid({"x": 364, "y": 270, "w": 1409, "h": 563,
                 "cols": 10, "rows": 4})
    ov.show_grid(True)
    time.sleep(1.0)

    tag = "noview" if os.environ.get("OV_NO_WDA") else "wda"
    out = f"output/debug/ov_{tag}.png"
    ImageGrab.grab().save(out)
    a = np.array(ImageGrab.grab())

    PLATE = np.array([13, 18, 22])
    k_bawah = int((np.abs(a[911:1079].astype(int) - PLATE).sum(axis=2) <= 3).sum())
    k_atas = int((np.abs(a[0:109].astype(int) - PLATE).sum(axis=2) <= 3).sum())
    teal = np.array([57, 197, 187])
    k_outline = int((np.abs(a[240:850, 350:1790].astype(int) - teal)
                     .sum(axis=2) <= 40).sum())

    print(f"excluded={ov.excluded} | pita_bawah={k_bawah} pita_atas={k_atas} "
          f"outline={k_outline} -> file {out}")
    print("tampil di screenshot:", "YA (mode debug)" if k_bawah > 100000
          else "TIDAK (WDA aman)")

    # cek logika tombol
    ctrl.jeda()
    assert ctrl.pause.is_set(), "JEDA tidak menahan"
    ctrl.go()
    assert not ctrl.pause.is_set() and ctrl.gate.is_set(), "LANJUT tidak buka"
    ctrl.open_gate()
    assert not ctrl.gate.is_set(), "open_gate gagal"
    ctrl.stop_now()
    assert not ctrl.hold_if_paused(0.05), "hold harus False saat STOP"
    assert ctrl.wait_gate(0.01) is False, "STOP harus mengembalikan False"
    print("logika tombol: OK")

    ov.close()
    time.sleep(0.4)
    print("done")


if __name__ == "__main__":
    main()
