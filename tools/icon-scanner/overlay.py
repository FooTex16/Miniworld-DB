#!/usr/bin/env python3
"""HUD layar penuh + outline area grid + tombol kontrol.

Tiga jendela, SEMUANYA memakai SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)
sehingga tidak ikut terekam oleh screenshot (PIL.ImageGrab) -> capture ikon,
deteksi grid, diff tooltip, dan OCR breadcrumb tetap bersih walaupun HUD
menutupi area tersebut.

  A. pita atas   (0, 0, 1920, 109)    kategori, halaman, sel, status, counters
                                       -> click-through (klik menembus ke game)
  B. pita bawah  (0, 911, 1920, 168)  ikon, ID, nama, daftar terakhir + TOMBOL
                                       -> TIDAK click-through (tombol bisa diklik)
  C. outline     kotak di area grid    patokan user saat scroll manual
                                       -> click-through

Alur:
    ov = Overlay(ctrl=Ctrl())
    ov.set(phase="scanning", state="scanning")
    ...
    ov.set_grid(bbox_sel)             # pasang outline
    ov.show_grid(True)
    ...
    if ctrl.wait_gate(): ...          # berhenti sampai tombol LANJUT/STOP

Tombol:
    LANJUT -> buka gerbang halaman berikutnya / lanjut dari jeda
    JEDA   -> tahan scan di antara sel
    STOP   -> hentikan scan total
"""
from __future__ import annotations

import os
import queue
import threading
import time

TRANS = "#010203"          # warna ini dibuat benar-benar transparan oleh Tk
PLATE = "#0d1216"
PLATE2 = "#161d24"
BTN = "#1e2831"
BTN_ACT = "#2c8f89"
ACCENT = "#39c5bb"         # warna teal ala game
TEXT = "#e8eef3"
MUTED = "#93a3b0"
WARN = "#e6a23c"
BAD = "#d9564f"

TOP_H = 109                # pita atas   -> y 0..108
BOT_Y = 911                # pita bawah  -> y 911..1078
BOT_H = 168
FRAME = 4                  # ketebalan outline grid

MONO = "Consolas"
SANS = "Segoe UI"

WDA_EXCLUDEFROMCAPTURE = 0x00000011
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

# Set OV_NO_WDA=1 -> HUD sengaja ikut terekam (hanya untuk cek tampilan)
NO_WDA = bool(os.environ.get("OV_NO_WDA"))


class Ctrl:
    """Sinyal tombol HUD -> dipakai thread scan (aman dipanggil dari Tk)."""

    def __init__(self) -> None:
        self.stop = threading.Event()      # STOP ditekan
        self.pause = threading.Event()     # JEDA aktif
        self.gate = threading.Event()      # LANJUT menunggu di gerbang halaman
        self.grid_q: "queue.Queue[dict]" = queue.Queue()   # setting grid
        self.mem_q: "queue.Queue[str]" = queue.Queue()     # alamat pick-id

    # --- callback tombol ---
    def go(self) -> None:
        self.pause.clear()
        self.gate.set()

    def jeda(self) -> None:
        self.pause.set()

    def stop_now(self) -> None:
        self.stop.set()
        self.pause.clear()
        self.gate.set()

    # --- dipakai scanner ---
    def hold_if_paused(self, poll: float = 0.2) -> bool:
        """Tahan di antara sel selama JEDA. -> False bila STOP ditekan."""
        while self.pause.is_set() and not self.stop.is_set():
            time.sleep(poll)
        return not self.stop.is_set()

    def open_gate(self) -> None:
        self.gate.clear()

    def wait_gate(self, poll: float = 0.15, on_tick=None) -> bool:
        """Tunggu tombol LANJUT/STOP di akhir halaman. -> False bila STOP.

        `on_tick` dipanggil tiap siklus (dipakai scanner untuk memproses
        permintaan pengaturan grid selagi menunggu)."""
        while not self.gate.is_set() and not self.stop.is_set():
            if on_tick is not None:
                try:
                    on_tick()
                except Exception as e:
                    print(f"[grid] gagal terapkan setting: {e}")
            time.sleep(poll)
        self.gate.clear()
        return not self.stop.is_set()

    # ---------------------------------------------------- setting grid --
    def grid_op(self, **op) -> None:
        """Kirim permintaan ubah setting grid dari tombol HUD.
        Kunci yang dikenali: cols, rows, fit (pasang ke grid), normal."""
        self.grid_q.put(dict(op))

    def take_grid(self) -> dict | None:
        """Scanner ambil (dan kosongkan) antrean setting grid. -> None bila kosong."""
        out: dict | None = None
        while True:
            try:
                item = self.grid_q.get_nowait()
            except queue.Empty:
                break
            out = item if out is None else {**out, **item}
        return out

    # --------------------------------------------------------- alamat pick --
    def set_mem(self, addr: str) -> None:
        """Kirim alamat pick-id baru dari kolom isian HUD (tombol SET)."""
        self.mem_q.put(str(addr))

    def take_mem(self) -> str | None:
        """Scanner ambil (dan kosongkan) antrean alamat. -> None bila kosong.

        Bila ada beberapa, dipakai yang terakhir (yang terbaru)."""
        out: str | None = None
        while True:
            try:
                out = self.mem_q.get_nowait()
            except queue.Empty:
                break
        return out


def _checker(size=150, cell=15):
    """Papan catur abu/putih -> latar supaya ikon transparan kelihatan."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    d = ImageDraw.Draw(im)
    for i in range(0, size, cell):
        for j in range(0, size, cell):
            if ((i // cell) + (j // cell)) % 2:
                d.rectangle([i, j, i + cell - 1, j + cell - 1],
                            fill=(196, 204, 212, 255))
    return im


class Overlay:
    """HUD + outline grid; jalan penuh di thread Tk sendiri."""

    def __init__(self, enabled: bool = True, size=(1920, 1080),
                 ctrl: "Ctrl | None" = None):
        self.ctrl = ctrl
        self.size = size
        self.excluded = False        # True bila WDA sukses (HUD tak ikut terekam)
        self._alive = False
        self._th = None
        self._ready = threading.Event()
        self._q: "queue.Queue[dict]" = queue.Queue()
        if not enabled:
            self._ready.set()
            return
        self._th = threading.Thread(target=self._run, daemon=True,
                                    args=(size,), name="hud")
        self._th.start()
        self._alive = True
        # tunggu jendela + WDA siap supaya `excluded` sudah benar saat scan mulai
        if not self._ready.wait(8.0):
            print("[overlay] jendela HUD tidak siap dalam 8s")

    # ------------------------------------------------------------- api --
    def set(self, **fields) -> None:
        """Perbarui teks/ikon HUD (non-blocking, aman dari thread scan)."""
        if self._alive:
            self._q.put(fields)

    def set_grid(self, spec) -> None:
        """Terima setting grid dari scanner -> outline ikut diubah.

        spec = {"x","y","w","h","cols","rows"} (sudah dihitung scanner)."""
        if self._alive and spec:
            self._q.put({"_gspec": dict(spec)})

    def show_grid(self, on: bool) -> None:
        if self._alive:
            self._q.put({"_grid_on": bool(on)})

    def close(self) -> None:
        """Berhenti memperbarui. Jendela sengaja TIDAK dihancurkan dari thread
        ini (destroy dari thread lain memicu fatal Tcl_AsyncDelete)."""
        if self._alive:
            self._alive = False
            self._q.put({"__stop__": True})

    # ----------------------------------------------------------- win32 --
    @staticmethod
    def _hwnd(win) -> int:
        import ctypes
        u = ctypes.windll.user32
        return u.GetParent(win.winfo_id()) or win.winfo_id()

    @classmethod
    def _style(cls, win, click_through: bool, exclude: bool) -> bool:
        """Set gaya jendela: click-through opsional + sembunyi dari screenshot."""
        try:
            import ctypes
            u = ctypes.windll.user32
            hwnd = cls._hwnd(win)
            st = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            add = WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            if click_through:
                add |= WS_EX_TRANSPARENT
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, st | add)
            if exclude and not NO_WDA:
                return bool(u.SetWindowDisplayAffinity(
                    hwnd, WDA_EXCLUDEFROMCAPTURE))
        except Exception as e:
            print(f"[overlay] gaya jendela gagal: {e}")
        return False

    # ------------------------------------------------------------- tk --
    def _run(self, size) -> None:
        try:
            import tkinter as tk
            from PIL import Image, ImageTk
        except Exception as e:
            print(f"[overlay] tidak bisa dijalankan: {e}")
            self._alive = False
            self._ready.set()
            return

        W, H = size
        ctrl = self.ctrl or Ctrl()

        def mk_toplevel(x, y, w, h):
            t = tk.Toplevel(self.root)
            t.overrideredirect(True)
            t.geometry(f"{w}x{h}+{x}+{y}")
            t.configure(bg=TRANS)
            t.attributes("-topmost", True)
            try:
                t.wm_attributes("-transparentcolor", TRANS)
            except Exception:
                pass
            t.update()
            return t

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.geometry(f"{W}x{TOP_H}+0+0")
        self.root.configure(bg=TRANS)
        self.root.attributes("-topmost", True)
        try:
            self.root.wm_attributes("-transparentcolor", TRANS)
        except Exception as e:
            print(f"[overlay] transparansi tidak didukung: {e}")
        self.root.update()

        # ---------------------------------------------------- pita atas --
        top = tk.Frame(self.root, bg=PLATE)
        top.place(x=0, y=0, width=W, height=TOP_H)

        l_cat = tk.Label(top, text="SCANNER SIAP", bg=PLATE, fg=ACCENT,
                         font=(SANS, 14, "bold"), anchor="w")
        l_cat.place(x=14, y=8, width=760, height=28)
        l_cell = tk.Label(top, text="", bg=PLATE, fg=TEXT,
                          font=(MONO, 12), anchor="w")
        l_cell.place(x=790, y=8, width=380, height=28)
        l_cnt = tk.Label(top, text="", bg=PLATE, fg=MUTED,
                         font=(MONO, 11), anchor="e")
        l_cnt.place(x=1180, y=8, width=725, height=28)
        l_phase = tk.Label(top, text="", bg=PLATE, fg=WARN,
                           font=(SANS, 12), anchor="w")
        l_phase.place(x=14, y=40, width=1100, height=30)
        l_prog = tk.Label(top, text="", bg=PLATE, fg=MUTED,
                          font=(MONO, 11), anchor="e")
        l_prog.place(x=1400, y=44, width=505, height=26)

        prog_bg = tk.Frame(top, bg=PLATE2)
        prog_bg.place(x=14, y=82, width=W - 28, height=14)
        prog_fill = tk.Frame(prog_bg, bg=ACCENT)
        prog_fill.place(x=0, y=0, width=1, height=14)

        # -------------------------------------------------- pita bawah --
        bot = mk_toplevel(0, BOT_Y, W, BOT_H)
        bbot = tk.Frame(bot, bg=PLATE)
        bbot.place(x=0, y=0, width=W, height=BOT_H)

        checker = _checker(150, 15)
        l_icon = tk.Label(bbot, bg=PLATE2)
        l_icon.place(x=16, y=9, width=150, height=150)

        l_id = tk.Label(bbot, text="ID -", bg=PLATE, fg=ACCENT,
                        font=(MONO, 26, "bold"), anchor="w")
        l_id.place(x=184, y=10, width=300, height=38)
        l_name = tk.Label(bbot, text="-", bg=PLATE, fg=TEXT,
                          font=(SANS, 15, "bold"), anchor="w",
                          justify="left", wraplength=480)
        l_name.place(x=184, y=52, width=500, height=54)
        l_ocr = tk.Label(bbot, text="", bg=PLATE, fg=MUTED,
                         font=(MONO, 11), anchor="w", justify="left",
                         wraplength=500)
        l_ocr.place(x=184, y=110, width=500, height=48)

        l_rec_hdr = tk.Label(bbot, text="TERAKHIR TERSIMPAN", bg=PLATE,
                             fg=WARN, font=(SANS, 10, "bold"), anchor="w")
        l_rec_hdr.place(x=700, y=8, width=300, height=22)
        l_recent = []
        for i in range(5):
            lb = tk.Label(bbot, text="", bg=PLATE, fg=MUTED,
                          font=(MONO, 11), anchor="w")
            lb.place(x=700, y=32 + i * 25, width=456, height=23)
            l_recent.append(lb)

        # ------------------------------------------------------ tombol --
        # kolom kontrol = x 1400..1910 (lebar 510)
        def bstyle(b, color=BTN, size=13):
            b.configure(bg=color, fg=TEXT, activebackground=BTN_ACT,
                        activeforeground="#ffffff", relief="flat",
                        bd=0, font=(SANS, size, "bold"), cursor="hand2",
                        takefocus=False)

        b_go = tk.Button(bbot, text="LANJUT  ▶", command=ctrl.go)
        bstyle(b_go, BTN_ACT)
        b_go.place(x=1400, y=6, width=510, height=42)

        b_pause = tk.Button(bbot, text="JEDA  ||", command=ctrl.jeda)
        bstyle(b_pause, "#25323c")
        b_pause.place(x=1400, y=52, width=250, height=42)

        b_stop = tk.Button(bbot, text="STOP  ■", command=ctrl.stop_now)
        bstyle(b_stop, "#3a2422")
        b_stop.place(x=1656, y=52, width=254, height=42)

        # ------------------------------------------- kolom alamat pick-id --
        # Sengaja dipasang di pita bawah (satu-satunya jendela HUD yang TIDAK
        # click-through) supaya bisa diklik. WS_EX_NOACTIVATE yang dipasang
        # _style() mencegah jendela jadi foreground, akibatnya ketikan tidak
        # sampai ke Entry -> diangkat sesaat saat kolom difokuskan.
        import ctypes
        u32 = ctypes.windll.user32
        AX, AW = 1168, 222                   # x & lebar kolom (1168..1390)

        l_addr_hdr = tk.Label(bbot, text="ALAMAT PICK ID", bg=PLATE, fg=WARN,
                              font=(SANS, 10, "bold"), anchor="w")
        l_addr_hdr.place(x=AX, y=8, width=AW, height=20)

        a_ent = tk.Entry(bbot, bg=PLATE2, fg=TEXT, insertbackground=TEXT,
                         font=(MONO, 14), relief="flat", bd=4,
                         justify="center")
        a_ent.place(x=AX, y=30, width=AW, height=34)

        b_mem = tk.Button(bbot, text="SET ALAMAT", command=lambda: op_mem())
        bstyle(b_mem, "#25323c", 10)
        b_mem.place(x=AX, y=68, width=AW, height=30)

        l_mem_msg = tk.Label(bbot, text="", bg=PLATE, fg=MUTED,
                             font=(MONO, 9), anchor="w", justify="left",
                             wraplength=AW)
        l_mem_msg.place(x=AX, y=100, width=AW, height=24)

        l_mem_val = tk.Label(bbot, text="nilai = -", bg=PLATE, fg=MUTED,
                             font=(MONO, 11), anchor="w", justify="left",
                             wraplength=AW)
        l_mem_val.place(x=AX, y=126, width=AW, height=32)

        mem_focus = {"on": False}            # kolom sedang difokuskan
        mem_pending = {"v": None}            # alamat aktif menunggu kolom dilepas

        def _hud_noact(on: bool) -> None:
            """Nyalakan/matikan WS_EX_NOACTIVATE di jendela pita bawah."""
            try:
                h = Overlay._hwnd(bot)
                st = u32.GetWindowLongW(h, GWL_EXSTYLE)
                st = (st | WS_EX_NOACTIVATE) if on else (st & ~WS_EX_NOACTIVATE)
                u32.SetWindowLongW(h, GWL_EXSTYLE, st)
            except Exception as e:
                print(f"[overlay] WS_EX_NOACTIVATE gagal diubah: {e}")

        def _to_foreground() -> bool:
            """Angkat pita bawah jadi foreground (untuk ketikan).

            SetForegroundWindow dibatasi sistem, jadi antrian input ditempel
            dulu ke thread foreground yang sekarang. Tanpa langkah ini ketikan
            tidak akan sampai ke kolom alamat."""
            try:
                k32 = ctypes.windll.kernel32
                h = ctypes.c_void_p(Overlay._hwnd(bot))
                fg = u32.GetForegroundWindow()
                me = k32.GetCurrentThreadId()
                tid = u32.GetWindowThreadProcessId(
                    ctypes.c_void_p(fg), None) if fg else 0
                attached = bool(tid) and tid != me
                if attached:
                    u32.AttachThreadInput(me, tid, True)
                try:
                    if u32.SetForegroundWindow(h):
                        return True
                    u32.SetWindowPos(h, 0, 0, 0, 0, 0,
                                     0x0001 | 0x0002)     # TOP, NOMOVE|NOSIZE
                    return bool(u32.SetForegroundWindow(h))
                finally:
                    if attached:
                        u32.AttachThreadInput(me, tid, False)
            except Exception as e:
                print(f"[overlay] foreground gagal: {e}")
            return False

        def _ent_focus(ev=None) -> None:
            """Entry diklik -> pita bawah diangkat sebentar jadi foreground,
            kalau tidak ketikan tidak akan sampai (WS_EX_NOACTIVATE)."""
            mem_focus["on"] = True
            _hud_noact(False)
            ok = _to_foreground()
            if not ok:
                print("[overlay] pita bawah TIDAK jadi foreground -> ketikan "
                      "mungkin tidak masuk (klik kolom sekali lagi)")
            try:
                a_ent.focus_force()
                a_ent.select_range(0, "end")
            except Exception as e:
                print(f"[overlay] fokus kolom gagal: {e}")

        def _ent_blur(ev=None) -> None:
            """Kolom dilepas -> sembunyikan lagi + tulis alamat yang benar-benar
            dipakai (supaya isi kolom tidak beda dengan alamat aktif)."""
            mem_focus["on"] = False
            _hud_noact(True)
            v = mem_pending["v"]
            mem_pending["v"] = None
            if v is not None and a_ent.get().strip() != v:
                a_ent.delete(0, "end")
                a_ent.insert(0, v)

        def op_mem() -> None:
            """Kirim isi kolom ke thread scan untuk divalidasi & dipakai."""
            v = a_ent.get().strip()
            if not v:
                l_mem_msg.configure(text="isi alamat dulu (mis. 0x2C00EA08)",
                                    fg=BAD)
                return
            l_mem_msg.configure(text=f"memeriksa {v} …", fg=WARN)
            ctrl.set_mem(v)

        a_ent.bind("<Button-1>", _ent_focus)
        a_ent.bind("<FocusIn>", _ent_focus)
        a_ent.bind("<FocusOut>", _ent_blur)
        a_ent.bind("<Return>", lambda ev: op_mem())

        # --- pengaturan grid: aktif bila grid tidak 10x4 / kepotong kategori --
        def _note(txt: str) -> None:
            state["phase"] = f"PENGATURAN GRID: {txt}"
            paint()

        def op_cols(d: int) -> None:
            n = max(4, min(16, gs["cols"] + d))
            if n == gs["cols"]:
                _note(f"sudah di batas ({n} kolom)")
                return
            gs["cols"] = n
            build_grid(grid_rect())
            ctrl.grid_op(cols=n)
            _note(f"{n} kolom -> kotak {grid_rect()[2]}px "
                  f"(tekan SESUAIKAN bila sel belum pas)")

        def op_rows(d: int) -> None:
            n = max(1, min(8, gs["rows"] + d))
            if n == gs["rows"]:
                _note(f"sudah di batas ({n} baris)")
                return
            gs["rows"] = n
            build_grid(grid_rect())
            ctrl.grid_op(rows=n)
            _note(f"{n} baris -> kotak {grid_rect()[3]}px")

        def op_fit() -> None:
            ctrl.grid_op(fit=True)
            _note("pasang kotak ke grid yang terbaca, lalu tekan LANJUT")

        def op_normal() -> None:
            gs["cols"], gs["rows"] = gs["cols0"], gs["rows0"]
            build_grid(grid_rect())
            ctrl.grid_op(normal=True)
            _note(f"kembali ke ukuran normal {gs['cols0']}x{gs['rows0']}")

        sm = 10                                          # font tombol kecil
        b_kol_m = tk.Button(bbot, text="KOL  −",
                            command=lambda: op_cols(-1))
        bstyle(b_kol_m, "#25323c", sm)
        b_kol_m.place(x=1400, y=98, width=120, height=30)
        b_kol_p = tk.Button(bbot, text="KOL  +",
                            command=lambda: op_cols(+1))
        bstyle(b_kol_p, "#25323c", sm)
        b_kol_p.place(x=1526, y=98, width=120, height=30)
        b_bar_m = tk.Button(bbot, text="BARIS  −",
                            command=lambda: op_rows(-1))
        bstyle(b_bar_m, "#25323c", sm)
        b_bar_m.place(x=1652, y=98, width=126, height=30)
        b_bar_p = tk.Button(bbot, text="BARIS  +",
                            command=lambda: op_rows(+1))
        bstyle(b_bar_p, "#25323c", sm)
        b_bar_p.place(x=1784, y=98, width=126, height=30)

        b_fit = tk.Button(bbot, text="SESUAIKAN GRID", command=op_fit)
        bstyle(b_fit, "#25323c", sm)
        b_fit.place(x=1400, y=132, width=250, height=30)
        b_norm = tk.Button(bbot, text="UKURAN NORMAL", command=op_normal)
        bstyle(b_norm, "#25323c", sm)
        b_norm.place(x=1656, y=132, width=254, height=30)

        # ------------------------------------------------ outline grid --
        grid = mk_toplevel(0, 0, 40, 40)
        # WDA dipasang saat jendela masih tampil -> pastikan berlaku
        ok_grd = self._style(grid, click_through=True, exclude=True)
        self._ok = {"top": False, "bot": False, "grid": bool(ok_grd)}
        grid.withdraw()
        gx, gy, gw, gh = 0, 0, 10, 10           # posisi jendela outline
        gbars = []
        gtag = tk.Label(grid, text="AREA DETEKSI PICK", bg=TRANS,
                        fg=WARN, font=(SANS, 10, "bold"))
        gtag.place(x=0, y=0)

        # setting grid -> kotak outline. cols/rows boleh diubah dari HUD.
        gs = {"x": 0, "y": 0, "cols": 10, "rows": 4,
              "cw": 141.0, "pitch": 141.0,
              "cols0": 10, "rows0": 4, "first": False}

        def grid_rect():
            """(x, y, w, h) kotak deteksi menurut setting grid saat ini."""
            return (int(gs["x"]), int(gs["y"]),
                    int(round(gs["cols"] * gs["cw"])),
                    int(round(gs["rows"] * gs["pitch"])))

        def set_gs(spec: dict) -> None:
            """Terima setting dari scanner (termasuk posisi setelah snap)."""
            try:
                cols, rows = int(spec["cols"]), int(spec["rows"])
                cw = float(spec["w"]) / max(1, cols)
                pitch = float(spec["h"]) / max(1, rows)
                ox, oy = int(spec["x"]), int(spec["y"])
            except Exception as e:
                print(f"[overlay] spec grid tidak valid: {e}")
                return
            gs["x"], gs["y"] = ox, oy
            gs["cols"], gs["rows"] = cols, rows
            gs["cw"], gs["pitch"] = cw, pitch
            if not gs["first"]:                 # spec pertama = ukuran normal
                gs["cols0"], gs["rows0"], gs["first"] = cols, rows, True
            build_grid(grid_rect())

        def build_grid(rect):
            """Bangun ulang bingkai outline sesuai rect (x,y,w,h) layar."""
            nonlocal gx, gy, gw, gh, gbars
            x, y, w, h = rect
            pad_l, pad_t = 6, 26
            nx, ny = x - pad_l, y - pad_t
            nw, nh = w + 2 * pad_l, h + pad_t + 6
            nx, ny = max(0, nx), max(0, ny)
            gx, gy, gw, gh = nx, ny, nw, nh
            grid.geometry(f"{nw}x{nh}+{nx}+{ny}")
            for b in gbars:
                b.destroy()
            gbars = []
            spec = [                    # (x, y, w, h) relatif jendela outline
                (pad_l, pad_t, w, FRAME),                              # atas
                (pad_l, pad_t + h - FRAME, w, FRAME),                  # bawah
                (pad_l, pad_t, FRAME, h),                              # kiri
                (pad_l + w - FRAME, pad_t, FRAME, h),                  # kanan
            ]
            for sx, sy, sw, sh in spec:
                b = tk.Frame(grid, bg=ACCENT)
                b.place(x=sx, y=sy, width=sw, height=sh)
                gbars.append(b)
            gtag.place(x=pad_l, y=2)

        # ------------------------------------------------------ polling --
        state: dict = {}
        recent: list[str] = []

        def paint() -> None:
            cat = state.get("cat") or "-"
            pg = state.get("page")
            cell = state.get("cell")
            cs = f"sel {cell[0]},{cell[1]}" if cell else "sel -,-"
            l_cat.configure(text=f"{cat}")
            l_cell.configure(text=f"halaman {pg if pg is not None else '-'}"
                                  f"   |   {cs}")
            c = state.get("counts") or {}
            l_cnt.configure(
                text=f"scan {c.get('done', 0)}   lewati {c.get('skip', 0)}   "
                     f"dup {c.get('dup', 0)}   terkunci {c.get('lock', 0)}   "
                     f"gagal {c.get('fail', 0)}")
            p, t = int(c.get("page_done", 0)), int(c.get("page_total", 0))
            frac = (p / t) if t else 0.0
            prog_fill.place(width=max(1, int((W - 28) * frac)))
            l_prog.configure(text=f"{p}/{t} sel")

            bid = state.get("bid")
            l_id.configure(text=("ID -" if not bid else f"ID {bid}"))
            l_name.configure(text=state.get("name") or "-")
            l_ocr.configure(text=f"OCR : {state.get('ocr') or '-'}")

            img = state.pop("icon", None)      # dipakai sekali lalu dibuang
            if img is not None:
                try:
                    base = checker.copy()
                    ic = img.convert("RGBA").resize((150, 150), Image.LANCZOS)
                    base.alpha_composite(ic, (0, 0))
                    state["_photo"] = ImageTk.PhotoImage(base)
                    l_icon.configure(image=state["_photo"])
                except Exception as e:
                    print(f"[overlay] ikon gagal: {e}")

            for i, lb in enumerate(l_recent):
                lb.configure(text=recent[i] if i < len(recent) else "")

            mode = state.get("btn") or ""
            if mode == "gate":
                b_go.configure(text="LANJUT  ▶", state="normal", bg=BTN_ACT)
                b_pause.configure(state="disabled", bg="#25323c")
                b_stop.configure(state="normal", bg="#3a2422")
            elif mode == "pause":
                b_go.configure(text="LANJUT  ▶", state="normal", bg=BTN_ACT)
                b_pause.configure(state="disabled", bg="#25323c")
                b_stop.configure(state="normal", bg="#3a2422")
            elif mode == "stop":
                b_go.configure(state="disabled", bg="#25323c")
                b_pause.configure(state="disabled", bg="#25323c")
                b_stop.configure(state="disabled", bg="#3a2422")
            else:                               # scanning
                b_go.configure(text="LANJUT  ▶", state="normal", bg=BTN)
                b_pause.configure(state="normal", bg="#25323c")
                b_stop.configure(state="normal", bg="#3a2422")

            # baris status: pakai phase dari scanner, atau teks bawaan mode
            phase = state.get("phase") or ""
            if not phase:
                if mode == "gate":
                    phase = ("Scroll manual sampai baris masuk kotak, "
                             "lalu tekan LANJUT.")
                elif mode == "pause":
                    phase = "JEDA — tekan LANJUT untuk lanjut."
                elif mode == "stop":
                    phase = "STOP — proses berakhir."
            l_phase.configure(text=phase)

            # --- kolom alamat pick-id ---
            na = state.pop("mem_addr", None)
            if na is not None:
                if mem_focus["on"]:
                    mem_pending["v"] = str(na)   # ditulis saat kolom dilepas
                elif a_ent.get().strip() != str(na):
                    a_ent.delete(0, "end")
                    a_ent.insert(0, str(na))
            mm = state.get("mem_msg")
            if mm is not None:
                l_mem_msg.configure(text=mm, fg=state.get("mem_fg") or MUTED)
            mv = state.get("mem_val")
            if mv is not None:
                l_mem_val.configure(text=mv, fg=state.get("mem_vfg") or MUTED)

            if state.get("_gspec") is not None:
                set_gs(state.pop("_gspec"))
            if state.get("_grid_on") is not None:
                on = state.pop("_grid_on")
                if on:
                    grid.deiconify()
                    grid.lift()
                    self._ok["grid"] = self._style(
                        grid, click_through=True, exclude=True)
                    self.excluded = all(self._ok.values())
                else:
                    grid.withdraw()

        def poll() -> None:
            stop, dirty = False, False
            for _ in range(64):
                try:
                    item = self._q.get_nowait()
                except queue.Empty:
                    break
                if item.get("__stop__"):
                    stop = True
                    continue
                for k, v in item.items():
                    if k == "recent":
                        recent.clear()
                        recent.extend(str(x) for x in v)
                        dirty = True
                    else:
                        state[k] = v
                        dirty = True
            if dirty:
                paint()
            if stop:
                return                    # biarkan thread Tk hidup s/d proses selesai
            self.root.after(70, poll)

        # ----------------------------------------------------- pasang --
        # root masih tersembunyi -> deiconify dulu baru pakai WDA
        self.root.deiconify()
        self.root.update()
        self._ok["top"] = self._style(
            self.root, click_through=True, exclude=True)
        self._ok["bot"] = self._style(bot, click_through=False, exclude=True)
        self.excluded = all(self._ok.values())
        if not self.excluded:
            print("[overlay] WDA_EXCLUDEFROMCAPTURE gagal di "
                  f"{[k for k, v in self._ok.items() if not v]} -> outline "
                  "hanya ditampilkan saat scanner berhenti (jangan tutupi "
                  "capture)")

        bot.lift()
        self.root.after(70, poll)
        self._ready.set()
        try:
            self.root.mainloop()
        finally:
            self._alive = False
            self._ready.set()
