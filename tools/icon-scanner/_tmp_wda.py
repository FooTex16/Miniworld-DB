"""Uji: apakah SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) membuat jendela
hilang dari screenshot PIL.ImageGrab?"""
import ctypes
import time

import numpy as np

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # pixel = pixel fisik
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

from PIL import ImageGrab

WDA_EXCLUDEFROMCAPTURE = 0x00000011
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

u = ctypes.windll.user32


def main():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.geometry("600x60+200+300")
    root.configure(bg="#ff00ff")              # magenta mencolok
    root.attributes("-topmost", True)
    root.update()

    hwnd = u.GetParent(root.winfo_id()) or root.winfo_id()
    st = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
    u.SetWindowLongW(hwnd, GWL_EXSTYLE,
                     st | WS_EX_LAYERED | WS_EX_TRANSPARENT
                     | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
    root.deiconify()
    root.update()
    time.sleep(0.6)

    # baseline: cari jendela magenta di SELURUH layar
    full = np.array(ImageGrab.grab())
    m = ((full[:, :, 0] > 200) & (full[:, :, 1] < 80) & (full[:, :, 2] > 200))
    n = int(m.sum())
    print(f"baseline layar penuh: {n} piksel magenta", end="")
    if n:
        ys, xs = np.where(m)
        print(f" | bbox x{xs.min()}..{xs.max()} y{ys.min()}..{ys.max()}")
    else:
        print("  -> jendela TIDAK tampil di screenshot")
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if n \
        else (200, 300, 800, 360)

    ok_aff = u.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
    err = ctypes.GetLastError()
    print(f"SetWindowDisplayAffinity -> {ok_aff} (GetLastError={err})")
    time.sleep(0.6)

    a = np.array(ImageGrab.grab(bbox=bbox))
    magenta = ((a[:, :, 0] > 200) & (a[:, :, 1] < 80) & (a[:, :, 2] > 200)).sum()
    print(f"piksel magenta setelah affinity: {magenta}")
    print("HASIL:", "TIDAK TERCATAT (aman)" if magenta == 0 else "MASIH TERCATAT")

    # uji kedua: tanpa affinity (kontrol) -> harus tercatat
    u.SetWindowDisplayAffinity(hwnd, 0)
    time.sleep(0.5)
    b = np.array(ImageGrab.grab(bbox=bbox))
    magenta2 = ((b[:, :, 0] > 200) & (b[:, :, 1] < 80) & (b[:, :, 2] > 200)).sum()
    print(f"kontrol (tanpa affinity): {magenta2} piksel magenta")
    root.destroy()


if __name__ == "__main__":
    main()
