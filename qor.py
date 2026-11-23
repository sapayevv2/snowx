# -*- coding: utf-8 -*-
"""
❄ Yangi yil qori — realistik qor simulyatsiyasi (Windows)

  * Mayda, shakli notekis qor zarralari (uzoq/yaqin qatlamlar, shamol).
  * Qor yerda, ochiq oynalar tepasida va ish stoli ikonkalari ustida to'planadi.
    Ikonkadagi qor ikonka shakliga moslashadi.
  * Oyna yoki ikonka siljitilsa, ustidagi qor sirpanib tushadi va pastdagi qorga
    sakramasdan qo'shiladi.
  * Chap tugma: qorni sudrab sharcha yasash, ko'tarish, otish.
  * Sharcha qattiq urilsa bo'laklarga ajraladi. 3 ta sharcha = qorbobo.
  * O'ng tugma: qorbobo, sharcha yoki qor uyumini parchalaydi.
  * Tepada realistik Yangi yil chiroqlari.

Ishga tushirish:  python qor.py
Xato yoki ma'lumot:  foydalanuvchi papkasidagi qor_xato.txt va qor_log.txt
"""
import ctypes
import gc
import math
import os
import random
import sys
import time
import tkinter as tk

KEY = "#010203"          # shaffof qilinadigan rang
WHITE = "#ffffff"
EDGE = "#b7d1ec"
PILE_BODY = "#dae7f6"      # qor qatlami: pastki to'q ko'kimtir
PILE_TOP = "#f1f7fd"       # qor qatlami: ustki yorug' qism
GRAVITY = 0.6
MAX_BALL = 56
GAIN = 4.2               # qor parchasi maydoni -> qatlam maydoni
BALL_GAIN = 4.0          # sharcha maydoni = olingan qor maydoni * BALL_GAIN
MAX_CHUNKS = 650
APP_NAME = "YangiYilQori"
FLAKE_FILL = ["#c3d4e7", "#dae7f4", "#eef5fb", "#ffffff"]
SKIP_CLASSES = ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                "Windows.UI.Core.CoreWindow", "NotifyIconOverflowWindow")

_errs = 0
_logs = 0


def _write(name, text):
    try:
        p = os.path.join(os.path.expanduser("~"), name)
        with open(p, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass


def log_error():
    global _errs
    _errs += 1
    if _errs <= 5:
        import traceback
        _write("qor_xato.txt", traceback.format_exc())


def log_info(msg):
    global _logs
    _logs += 1
    if _logs <= 25:
        _write("qor_log.txt", msg)


def covers_screen(rect, W, H, tol=2):
    """Oyna butun ekranni qoplaydimi (to'liq ekranli o'yin/video)?"""
    l, t, r, b = rect
    return l <= tol and t <= tol and r >= W - tol and b >= H - tol


def interaction_allowed(mode, ctrl_down):
    """Sichqoncha bilan o'ynash rejimi: always | ctrl | off."""
    return mode == "always" or (mode == "ctrl" and bool(ctrl_down))


def next_flake_cap(cap, avg_ms, lo=100, hi=600, slow=26.0, fast=14.0):
    """Kadr uzoq cho'zilsa qor zarralari sonini kamaytiradi, bo'sh bo'lsa qaytaradi."""
    if avg_ms > slow:
        return max(lo, int(cap * 0.88))
    if avg_ms < fast and cap < hi:
        return min(hi, int(cap * 1.06) + 1)
    return cap


def frame_delay(elapsed_ms, target=33.0):
    """Kadr sarflagan vaqtni hisobga olib, keyingi kadrgacha kutish (ms)."""
    return max(1, int(round(target - elapsed_ms)))


def pace(deadline, now, target):
    """Kadr vaqtini 'muddat' bo'yicha tekis ushlaydi (kechikish yig'ilib qolmaydi).
    Qaytaradi: (keyingi muddat, kutish ms). Kechiksak, quvib yetishga urinmaymiz."""
    nxt = deadline + target
    if nxt < now:
        nxt = now
    return nxt, max(1, int((nxt - now) * 1000.0))


def timer_begin(ms=1):
    """Windows taymeri odatda ~15.6 ms qadamda ishlaydi: after(33) kadrlari notekis
    (31/47 ms) chiqib, qotish bo'lib ko'rinadi. 1 ms aniqlik buni tuzatadi."""
    try:
        return ctypes.windll.winmm.timeBeginPeriod(ms) == 0
    except Exception:
        return False


def timer_end(ms=1):
    try:
        ctypes.windll.winmm.timeEndPeriod(ms)
    except Exception:
        pass


def wind_label(wn):
    p = int(round(abs(wn) * 100))
    if p < 3:
        return "Shamol yo'q"
    return ("O'ngga" if wn > 0 else "Chapga") + "  \u2022  %d%%" % p


def wind_arrow(wn, w, h):
    """Shamol ko'rsatkichi: markazdan yo'nalish tomonga o'q (chiziq va uchi nuqtalari)."""
    cx, cy = w / 2.0, h / 2.0
    L = wn * (w / 2.0 - 14)
    ex = cx + L
    head = []
    if abs(L) > 6:
        sg = 1 if L > 0 else -1
        head = [ex, cy, ex - sg * 9, cy - 6, ex - sg * 9, cy + 6]
    return [cx, cy, ex, cy], head


def blend(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# =====================================================================
#  Windows bilan ishlash
# =====================================================================
def dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


def cursor_pos():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def button_down(vk):
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def work_area():
    try:
        r = RECT()
        ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(r), 0)
        return r.l, r.t, r.r, r.b
    except Exception:
        return None


def autostart_get():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Run")
        winreg.QueryValueEx(k, APP_NAME)
        return True
    except Exception:
        return False


def autostart_set(on):
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Run",
                           0, winreg.KEY_SET_VALUE)
        if on:
            if getattr(sys, "frozen", False):
                cmd = '"%s"' % sys.executable
            else:
                cmd = '"%s" "%s"' % (sys.executable, os.path.abspath(sys.argv[0]))
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass
    except Exception:
        pass


_api_ready = False


def setup_api():
    """ctypes funksiyalari uchun to'g'ri turlarni o'rnatadi (64-bit uchun muhim)."""
    global _api_ready
    from ctypes import wintypes
    u = ctypes.windll.user32
    d = ctypes.windll.dwmapi
    if _api_ready:
        return u, d
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.IsIconic.argtypes = [wintypes.HWND]
    u.IsZoomed.argtypes = [wintypes.HWND]
    u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    u.GetWindowLongW.restype = ctypes.c_long
    u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    u.SetWindowLongW.restype = ctypes.c_long
    u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.c_void_p]
    u.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    u.GetAncestor.restype = wintypes.HWND
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.FindWindowW.restype = wintypes.HWND
    u.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR,
                                wintypes.LPCWSTR]
    u.FindWindowExW.restype = wintypes.HWND
    u.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_size_t,
                               ctypes.c_ssize_t]
    u.SendMessageW.restype = ctypes.c_ssize_t
    u.SendMessageTimeoutW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_size_t,
                                      ctypes.c_ssize_t, ctypes.c_uint, ctypes.c_uint,
                                      ctypes.c_void_p]
    u.SendMessageTimeoutW.restype = ctypes.c_ssize_t
    u.ClientToScreen.argtypes = [wintypes.HWND, ctypes.c_void_p]
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    u.GetForegroundWindow.restype = wintypes.HWND
    u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    u.SetWindowPos.argtypes = [wintypes.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    u.GetDC.argtypes = [wintypes.HWND]
    u.GetDC.restype = ctypes.c_void_p
    u.ReleaseDC.argtypes = [wintypes.HWND, ctypes.c_void_p]
    d.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                        ctypes.c_void_p, wintypes.DWORD]
    g = ctypes.windll.gdi32
    g.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    g.CreateCompatibleDC.restype = ctypes.c_void_p
    g.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    g.CreateCompatibleBitmap.restype = ctypes.c_void_p
    g.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    g.SelectObject.restype = ctypes.c_void_p
    g.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                         wintypes.DWORD]
    g.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                            ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_uint]
    g.DeleteObject.argtypes = [ctypes.c_void_p]
    g.DeleteDC.argtypes = [ctypes.c_void_p]
    _api_ready = True
    return u, d


def grab_screen(x, y, w, h):
    """Ekranning (x,y,w,h) qismini BGRA baytlar sifatida oladi (qor oynasisiz)."""
    u = ctypes.windll.user32
    g = ctypes.windll.gdi32
    hdc = u.GetDC(None)
    if not hdc:
        return None
    try:
        mdc = g.CreateCompatibleDC(hdc)
        bmp = g.CreateCompatibleBitmap(hdc, w, h)
        old = g.SelectObject(mdc, bmp)
        ok = g.BitBlt(mdc, 0, 0, w, h, hdc, x, y, 0x00CC0020)   # SRCCOPY
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth, bi.biHeight = w, -h
        bi.biPlanes, bi.biBitCount = 1, 32
        buf = ctypes.create_string_buffer(w * h * 4)
        g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        g.SelectObject(mdc, old)
        g.DeleteObject(bmp)
        g.DeleteDC(mdc)
        return buf.raw if ok else None
    finally:
        u.ReleaseDC(None, hdc)


def compute_profile(buf, w, h_total, margin, thresh=30, skip_first=False):
    """Ikonka siluetining yuqori chegarasi (piksel aniqligida).
    buf — BGRA baytlar (yuqoridan pastga), tepada `margin` qator ikonkadan tashqarida.
    Har bir ustunda keskin rang sakrashi (ikonka cheti) qidiriladi; fon gradienti
    sekin o'zgargani uchun xalaqit bermaydi. Yumshoq (yarim shaffof) chet qatorlari
    ham hisobga olinadi.
    skip_first=True: ikonka tanlangan (ko'k fon), birinchi sakrash (fon cheti)
    o'tkazib yuboriladi.
    Qaytaradi: har bir ustun uchun ikonka to'rtburchagi tepasidan masofa (px,
    manfiy bo'lishi ham mumkin) yoki None."""
    rows = h_total - margin
    end = margin + int(rows * 0.75)

    def diff(x, r):
        i = (r * w + x) * 4
        j = ((r - 2) * w + x) * 4
        return abs(buf[i] - buf[j]) + abs(buf[i + 1] - buf[j + 1]) + abs(buf[i + 2] - buf[j + 2])

    prof = []
    for x in range(w):
        found = None
        streak = 0
        stage = 0 if skip_first else 1
        r = 2 if stage else margin
        while r < end:
            if diff(x, r) > thresh:
                streak += 1
                if streak >= 2:
                    if stage == 0:
                        stage = 1
                        streak = 0
                        r += 3
                        continue
                    r1 = r - 1
                    for _ in range(2):          # yumshoq chetning birinchi qatori
                        if r1 - 1 >= 2 and diff(x, r1 - 1) > 12:
                            r1 -= 1
                        else:
                            break
                    found = r1 - margin
                    break
            else:
                streak = 0
            r += 1
        prof.append(found)
    out = []
    for x in range(w):
        win = [prof[j] for j in range(max(0, x - 1), min(w, x + 2))]
        vals = sorted(v for v in win if v is not None)
        if len(vals) * 2 <= len(win):
            out.append(None)
        else:
            out.append(vals[len(vals) // 2])
    return out


def profile_ok(prof, min_solid=0.4):
    solid = [p for p in prof if p is not None]
    if len(solid) < min_solid * len(prof):
        return False
    flat = sum(1 for p in solid if p <= 1)
    if flat >= 0.85 * len(solid) and len(solid) > 0.9 * len(prof):
        return False          # tanlangan (ko'k fon) ikonka — to'g'ri chegara emas
    return True


class IconDrag:
    """Ikonka chap tugma bilan sudralganda, ustidagi qorni sudrash tomoniga sachratadi."""

    def __init__(self, S):
        self.S = S
        self.cur = None
        self.prev = None
        self.prev_down = False

    def update(self, mx, my, down, icons, covered, fling):
        S = self.S
        if down and not self.prev_down:
            self.cur = None
            if not covered(mx, my):
                for (i, l, t, rr, bb, prof) in icons:
                    if l - 8 * S <= mx <= rr + 8 * S and t <= my <= bb + 36 * S:
                        self.cur = [i, mx, my, False]
                        break
        if not down:
            self.cur = None
        elif self.cur is not None and not self.cur[3]:
            i, sx, sy, _ = self.cur
            d = math.hypot(mx - sx, my - sy)
            if d > 8 * S:
                px, py = self.prev if self.prev else (sx, sy)
                sp = max(9 * S, math.hypot(mx - px, my - py) * 1.8)
                fling(i, (mx - sx) / d * sp, (my - sy) / d * sp)
                self.cur[3] = True
        self.prev = (mx, my)
        self.prev_down = down


class WinScanner:
    """Ochiq oynalarning joylashuvini (z-tartibda, tepadan pastga) o'qiydi."""

    def __init__(self, own_hwnd, S):
        self.own = own_hwnd
        self.S = S
        self.ok = True
        try:
            self.u, self.dwm = setup_api()
        except Exception:
            self.ok = False

    def scan(self, W, H, ground):
        if not self.ok:
            return []
        from ctypes import wintypes
        u, dwm, S = self.u, self.dwm, self.S
        res = []
        buf = ctypes.create_unicode_buffer(80)
        own = int(self.own) if self.own else -1

        def cb(hwnd, lp):
            try:
                if hwnd is None or int(hwnd) == own:
                    return True
                if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
                    return True
                ex = u.GetWindowLongW(hwnd, -20)
                if ex & 0x80 or ex & 0x08000000:      # TOOLWINDOW | NOACTIVATE
                    return True
                cloaked = wintypes.DWORD(0)
                dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)
                if cloaked.value:
                    return True
                u.GetClassNameW(hwnd, buf, 80)
                if buf.value in SKIP_CLASSES:
                    return True
                if u.GetWindowTextLengthW(hwnd) == 0:
                    return True
                r = RECT()
                if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r),
                                             ctypes.sizeof(r)) != 0:
                    u.GetWindowRect(hwnd, ctypes.byref(r))
                w, h = r.r - r.l, r.b - r.t
                if w < 100 * S or h < 50 * S:
                    return True
                ok = (r.t >= 8 * S and r.t < ground - 40 * S and not u.IsZoomed(hwnd)
                      and r.r > 0 and r.l < W)
                res.append((int(hwnd), r.l, r.t, r.r, r.b, ok))
            except Exception:
                pass
            return True

        try:
            proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb)
            u.EnumWindows(proc, 0)
        except Exception:
            return []
        return res


class DesktopIcons:
    """Ish stoli ikonkalari joylashuvi va siluetini o'qiydi."""

    def __init__(self, S, W, H):
        self.S, self.W, self.H = S, W, H
        self.ok = False
        self.lv = None
        self.why = ""
        self.cache = {}
        self.nq = 0
        self.logged = False
        self.last_out = []
        self.skip = 0
        try:
            self.u, _ = setup_api()
            from ctypes import wintypes
            k = ctypes.windll.kernel32
            k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k.OpenProcess.restype = ctypes.c_void_p
            k.VirtualAllocEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
            k.VirtualAllocEx.restype = ctypes.c_void_p
            k.WriteProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                             ctypes.c_void_p, ctypes.c_size_t,
                                             ctypes.c_void_p]
            k.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                            ctypes.c_void_p, ctypes.c_size_t,
                                            ctypes.c_void_p]
            self.k = k
            self.find()
        except Exception as e:
            self.ok = False
            self.why = "boshlash xatosi: %r" % (e,)
        if not self.ok:
            log_info("Ikonkalar: o'qib bo'lmadi (%s)" % self.why)

    def find(self):
        u = self.u
        defview = None
        prog = u.FindWindowW("Progman", None)
        if prog:
            defview = u.FindWindowExW(prog, None, "SHELLDLL_DefView", None)
        if not defview:
            ww = None
            while True:
                ww = u.FindWindowExW(None, ww, "WorkerW", None)
                if not ww:
                    break
                defview = u.FindWindowExW(ww, None, "SHELLDLL_DefView", None)
                if defview:
                    break
        if not defview:
            self.why = "SHELLDLL_DefView topilmadi"
            return
        lv = u.FindWindowExW(defview, None, "SysListView32", None)
        if not lv:
            self.why = "SysListView32 topilmadi"
            return
        pid = ctypes.c_ulong(0)
        u.GetWindowThreadProcessId(lv, ctypes.byref(pid))
        proc = self.k.OpenProcess(0x38, False, pid.value)   # VM_OPERATION|READ|WRITE
        if not proc:
            self.why = "explorer jarayoniga kirib bo'lmadi"
            return
        remote = self.k.VirtualAllocEx(proc, None, 64, 0x3000, 0x04)
        if not remote:
            self.why = "explorer xotirasini ajratib bo'lmadi"
            return
        self.lv, self.proc, self.remote = lv, proc, remote
        self.ok = True

    def send(self, msg, wp, lp):
        """Explorer'ga xabar yuboradi; u javob bermasa (qotsa) 30 ms dan keyin voz kechadi."""
        res = ctypes.c_size_t(0)
        ok = self.u.SendMessageTimeoutW(self.lv, msg, wp, lp, 0x2, 30, ctypes.byref(res))
        if not ok:
            raise TimeoutError("explorer javob bermadi")
        return res.value

    def capture(self, l, t, r, b, sel=False):
        S = self.S
        m = 4
        w, h = int(r - l), int(b - t)
        if w < 8 or h < 8 or w > 400 or h > 400:
            return None
        if l < 0 or t - m < 0 or r > self.W or b > self.H:
            return None
        buf = grab_screen(int(l), int(t - m), w, h + m)
        if buf is None:
            return None
        prof = compute_profile(buf, w, h + m, m)
        if profile_ok(prof):
            return prof
        if sel:        # ko'k tanlov foni bor: uning chetini o'tkazib yuboramiz
            prof = compute_profile(buf, w, h + m, m, skip_first=True)
            if profile_ok(prof, 0.5):
                return prof
        return None

    def query(self, covered, mouse):
        """[(indeks, l, t, r, b, profil)] — ikonka rasmi to'rtburchagi va silueti."""
        if not self.ok:
            self.nq += 1
            if self.nq % 25 == 1:
                try:
                    self.find()
                except Exception:
                    pass
            if not self.ok:
                return []
        u, k, S = self.u, self.k, self.S
        mx, my, down = mouse
        if self.skip > 0:             # explorer band edi: biroz kutamiz, eski natijani saqlaymiz
            self.skip -= 1
            return self.last_out
        try:
            if not u.IsWindowVisible(self.lv):
                return []
            count = self.send(0x1004, 0, 0)                     # LVM_GETITEMCOUNT
            if count <= 0 or count > 300:
                return []
            org = POINT(0, 0)
            u.ClientToScreen(self.lv, ctypes.byref(org))
            out = []
            captures = 0
            self.nq += 1
            for i in range(count):
                r = RECT(1, 0, 0, 0)                            # LVIR_ICON
                k.WriteProcessMemory(self.proc, self.remote, ctypes.byref(r), 16, None)
                if not self.send(0x100E, i, self.remote):
                    continue
                k.ReadProcessMemory(self.proc, self.remote, ctypes.byref(r), 16, None)
                l, t = org.x + r.l, org.y + r.t
                rr, bb = org.x + r.r, org.y + r.b
                if rr - l < 10 * S or rr < 0 or l > self.W:
                    continue
                key = (l, t, rr, bb)
                ent = self.cache.get(i)
                if ent is None or ent[0] != key:
                    ent = [key, None, 0, self.nq]
                    self.cache[i] = ent
                want = ent[1] is None and self.nq >= ent[3]
                if want and captures < 3 and not down:
                    pts = ((l + 2, t + 2), (rr - 2, t + 2), ((l + rr) / 2, (t + bb) / 2),
                           (l + 2, bb - 2), (rr - 2, bb - 2))
                    near = (l - 12 * S <= mx <= rr + 12 * S and t - 12 * S <= my <= bb + 12 * S)
                    state = self.send(0x102C, i, 0x000A)         # SELECTED|DROPHILITED
                    if not near and not any(covered(x, y) for x, y in pts):
                        captures += 1
                        prof = self.capture(l, t, rr, bb, bool(state))
                        if prof is not None:
                            ent[1] = prof
                        else:
                            ent[2] += 1
                            ent[3] = self.nq + 25
                out.append((i, l, t, rr, bb, ent[1]))
            if not self.logged and out:
                self.logged = True
                log_info("Ikonkalar topildi: %d ta" % len(out))
            self.last_out = out
            return out
        except TimeoutError:
            self.skip = 20
            return self.last_out
        except Exception:
            self.ok = False
            self.why = "so'rov xatosi"
            log_error()
            return []


# =====================================================================
#  O'yin dunyosi (tkinter'siz — faqat hisob-kitob)
# =====================================================================
def rot(pts, ang, cx, cy, k=1.0):
    ca, sa = math.cos(ang), math.sin(ang)
    out = []
    for px, py in pts:
        out.append(cx + (px * ca - py * sa) * k)
        out.append(cy + (px * sa + py * ca) * k)
    return out


def rough_shape(n_lo, n_hi, lo, hi, stretch=1.0):
    n = random.randint(n_lo, n_hi)
    pts = []
    for k in range(n):
        a = 6.283 * k / n + random.uniform(-0.45, 0.45)
        rr = random.uniform(lo, hi)
        pts.append((math.cos(a) * rr, math.sin(a) * rr * stretch))
    return pts


def dendrite_shape(rnd, pairs=2):
    """Olti nurli qor kristali (dendrit): har bir nurda yon shoxchalar. Birlik radiusli kontur."""
    w = 0.055
    ps = [0.34, 0.62][:pairs]
    ls = [rnd.uniform(0.22, 0.29), rnd.uniform(0.16, 0.24)][:pairs]   # qo'shni nurga tegmasin
    lower = [(0.10, -w)]
    for p, l in zip(ps, ls):
        lower += [(p - 0.03, -w), (p + l * 0.5, -l * 0.87), (p + 0.05, -w)]
    upper = [(x, -y) for (x, y) in reversed(lower)]
    arm = lower + [(1.0, 0.0)] + upper
    pts = []
    for k in range(6):
        a = k * math.pi / 3
        ca, sa = math.cos(a), math.sin(a)
        pts += [(x * ca - y * sa, x * sa + y * ca) for (x, y) in arm]
    return pts


def star_shape(inner):
    """Oddiy olti nurli yulduzcha yoki (inner~0.6) burchakli olti qirrali plastinka."""
    pts = []
    for k in range(6):
        a = k * math.pi / 3
        pts.append((math.cos(a), math.sin(a)))
        a2 = a + math.pi / 6
        pts.append((inner * math.cos(a2), inner * math.sin(a2)))
    return pts


def _build_shapes():
    rnd = random.Random(5)
    return {
        "dendrite": [dendrite_shape(rnd, 2) for _ in range(6)],
        "small": [dendrite_shape(rnd, 1), dendrite_shape(rnd, 1), star_shape(0.30),
                  star_shape(0.38), star_shape(0.62)],
    }


SHAPES = _build_shapes()


# (tur, diametr px, tanlanish og'irligi): asosan juda mayda yumshoq nuqtalar, kamdan-kam kristallar
FLAKE_TYPES = [("dot", 2, 26), ("dot", 3, 24), ("dot", 4, 14), ("dot", 5, 6),
               ("clump", 5, 5), ("clump", 7, 2), ("plate", 6, 4), ("plate", 8, 2),
               ("star", 8, 3), ("star", 10, 2), ("star", 12, 1)]
FLAKE_WEIGHTS = [t[2] for t in FLAKE_TYPES]
HEX = [(math.cos(k * math.pi / 3), math.sin(k * math.pi / 3)) for k in range(6)]


class Flake:
    __slots__ = ("x", "y", "z", "tier", "r", "v", "ph", "fr", "wob", "ang", "spin",
                 "shape", "item", "px", "py", "k", "dr", "ri", "fill", "outline", "kind",
                 "ex", "ey")

    def __init__(self, W, H, S, anywhere=False):
        self.item = None
        kind, d, _ = random.choices(FLAKE_TYPES, weights=FLAKE_WEIGHTS)[0]
        self.kind = kind
        self.dr = d / 2.0 * S * random.uniform(0.85, 1.2)   # chizilgan radius (har biri biroz farq qiladi)
        self.r = (0.55 + 0.14 * d) * S              # qatlamga qo'shiladigan hisobiy o'lcham
        self.z = min(1.0, d / 12.0)
        self.tier = int(self.z * 3.999)
        self.v = (26 + 3.6 * d + random.uniform(-6, 10)) / 30.0 * S
        self.fr = random.uniform(0.02, 0.05)
        self.wob = random.uniform(0.25, 0.8)
        self.ang = random.uniform(0, 6.28)
        self.spin = random.uniform(-0.05, 0.05)
        self.outline = ""
        self.ri = 6
        if kind == "dot":
            self.fill = blend("#c3d4e7", "#f4f9fe", (d - 2) / 4.0)   # kichigi xiraroq
            if d <= 4:
                self.shape = None                   # eng mayda: oddiy yumshoq nuqta (oval)
                self.ri = 0
            else:
                self.shape = rough_shape(5, 7, 0.82, 1.18)
        elif kind == "clump":
            self.shape = rough_shape(8, 10, 0.55, 1.25)
            self.fill = "#f0f6fc"
        elif kind == "plate":
            self.shape = HEX
            self.fill = "#e8f2fc"
            self.outline = "#fafdff"
        else:
            self.shape = random.choice(SHAPES["small"][2:4] if d <= 8 else
                                       SHAPES["small"][:2] if d <= 10 else SHAPES["dendrite"])
            self.fill = "#f2f8ff"
        self.ex = self.ey = 0.0                     # kursor turtkisidan qo'shimcha tezlik
        self.k = random.randrange(4)
        self.place(W, H, anywhere)

    def place(self, W, H, anywhere=False):
        self.x = random.uniform(0, W)
        self.y = random.uniform(0, H) if anywhere else random.uniform(-0.25 * H, -4)
        self.ph = random.uniform(0, 6.28)
        self.px = None            # oxirgi chizilgan joy (None = to'liq qayta chizish)
        self.py = None
        self.ex = self.ey = 0.0

    def respawn(self, W, H, S, anywhere=False):
        self.place(W, H, anywhere)                  # tur va o'lcham o'zgarmaydi


class Chunk:
    """Qor bo'lagi: katta bo'lak (sharcha parchasi), chang yoki yumshoq zarra (soft)."""
    __slots__ = ("x", "y", "vx", "vy", "r", "dust", "soft", "item", "shape", "ph",
                 "vmax", "ang", "spin", "tier", "age", "px", "py")

    def __init__(self, x, y, vx, vy, r, dust):
        self.x, self.y, self.vx, self.vy, self.r = x, y, vx, vy, r
        self.dust = dust
        self.soft = False
        self.item = None
        self.shape = None if dust else rough_shape(5, 7, 0.65, 1.2)
        self.ph = self.vmax = self.ang = self.spin = 0.0
        self.tier = 3
        self.age = 0
        self.px = self.py = None


class Part:
    """Qorbobo qismlari (qalpoq, burun, shox, ko'mir, sharf)."""

    def __init__(self, kind, x, y, vx, vy, s, w=0.0):
        self.kind, self.x, self.y, self.vx, self.vy = kind, x, y, vx, vy
        self.s, self.w = s, w
        self.ang = random.uniform(-0.5, 0.5)
        self.vang = random.uniform(-0.35, 0.35)
        self.rest = 0
        self.k = 1.0
        self.ext = {"hat": 0.45, "nose": 0.1, "stick": 0.08, "scarf": 0.1,
                    "coal": 1.0}[kind] * (w if kind == "coal" else s)


class Pile:
    """Bir sirtda (yer, oyna tepasi, ikonka) to'planadigan qor qatlami."""
    def __init__(self, x0, x1, y, col, maxh, slope, open_edges, S, noise_k=1.0,
                 kind="ground", spread=20.0):
        self.kind = kind
        K = max(2, int(spread * S / col))
        self.K = K
        self.weights = [K + 1 - abs(d) for d in range(-K, K + 1)]
        self.col, self.maxh, self.slope = col, maxh, slope
        self.open, self.S, self.noise_k = open_edges, S, noise_k
        self.active = True
        self.h = []
        self.noise = []
        self.vis = None
        self.base = None          # ikonka silueti (har ustun uchun tepadan masofa yoki None)
        self.prof_id = -1
        self.moving = False       # oyna hozir siljiyaptimi (qor faqat boshida uchadi)
        self.still = 0
        self.items = []           # chizilgan [tana, ustki qatlam, ko'rinadimi] juftliklari
        self.dirty = True
        self.urgent = True        # shakl keskin o'zgardi: darhol chizish (qor o'sishi esa siyrak chiziladi)
        self.phase = random.randrange(6)
        self._bc = None           # (base, len) bo'yicha keshlangan tayanch/qattiq ro'yxatlar
        self.x0 = self.x1 = self.y = None
        self.move(x0, x1, y)

    def move(self, x0, x1, y):
        n = max(3, int((x1 - x0) // self.col) + 1)
        if n > len(self.h):
            add = n - len(self.h)
            self.h += [0.0] * add
            for _ in range(add):
                prev = self.noise[-1] if self.noise else 0.0
                self.noise.append(0.78 * prev + 0.22 * random.uniform(-1, 1) * 4.5 * self.S)
        elif n < len(self.h):
            del self.h[n:]
            del self.noise[n:]
        if (x0, x1, y) != (self.x0, self.x1, self.y):
            self.dirty = True
            self.urgent = True
        self.prev_y = self.y if self.y is not None else y
        self.x0, self.x1, self.y = x0, x1, y

    def set_profile(self, profile, wpx):
        S = self.S
        if profile is None:        # standart: yumaloq ikonka shakli
            hw = max(1.0, wpx / 2.0)
            profile = []
            for k in range(int(wpx) + 1):
                u = max(-1.0, min(1.0, (k + 0.5 - hw) / hw))
                profile.append(3 * S + (1 - math.sqrt(max(0.0, 1 - u * u))) * hw * 0.45)
        base = []
        for i in range(len(self.h)):
            k = min(len(profile) - 1, int(i * self.col + self.col / 2.0))
            p = profile[k]
            base.append(None if p is None else float(p))
        self.base = base
        self.dirty = True
        self.urgent = True

    def set_corners(self, R):
        """Oyna yuqori burchaklari yumaloq: qor burchak bo'ylab egilib, chetdan chiqmaydi."""
        n = len(self.h)
        w = self.x1 - self.x0
        base = []
        for i in range(n):
            xc = i * self.col + self.col / 2.0
            d = min(xc, w - xc)
            base.append(R - math.sqrt(max(0.0, R * R - (R - d) ** 2)) if d < R else 0.0)
        self.base = base
        self.dirty = True
        self.urgent = True

    def solid(self, i):
        return self.base is None or self.base[i] is not None

    def surf_y(self, i):
        if self.base is None or self.base[i] is None:
            return self.y
        return self.y + self.base[i]

    def top_at(self, i):
        return self.surf_y(i) - self.h[i]

    def idx(self, x):
        i = int((x - self.x0) // self.col)
        if i < 0:
            return 0
        if i >= len(self.h):
            return len(self.h) - 1
        return i

    def height_at(self, x):
        return self.h[self.idx(x)]

    def top_y_at(self, x):
        return self.top_at(self.idx(x))

    def area(self):
        return sum(self.h) * self.col

    def add(self, x, r):
        total = math.pi * r * r * GAIN / self.col
        sw = float(sum(self.weights))
        i = self.idx(x)
        h = self.h
        n = len(h)
        for k, w in enumerate(self.weights):
            j = i + k - self.K
            if 0 <= j < n and self.solid(j):
                v = h[j] + total * w / sw
                h[j] = v if v < self.maxh else self.maxh
        self.dirty = True

    def take(self, x, r, want_area):
        i = self.idx(x)
        k = max(3, int(r / self.col) + 2)
        per = want_area / ((2 * k + 1) * self.col)
        got = 0.0
        for j in range(i - k, i + k + 1):
            if 0 <= j < len(self.h):
                t = min(self.h[j], per)
                self.h[j] -= t
                got += t * self.col
        if got > 0:
            self.dirty = True
            self.urgent = True
        return got

    def _bcache(self):
        """Tayanch (None -> 0.0) va 'qattiq ustun' ro'yxatlari: relax() har safar qayta hisoblamaydi."""
        base = self.base
        c = self._bc
        if c is None or c[0] is not base or c[1] != len(base):
            c = (base, len(base), [b if b is not None else 0.0 for b in base],
                 [b is not None for b in base])
            self._bc = c
        return c[2], c[3]

    def relax(self):
        h = self.h
        n = len(h)
        lim = self.slope
        maxh = self.maxh
        base = self.base
        moved = False
        if base is None:
            # tez yo'l (yer): hamma ustun qattiq, tayanch yo'q
            for i in range(n - 1):
                a = h[i]
                b = h[i + 1]
                d = a - b
                if d > lim:
                    m = (d - lim) * 0.35
                    if m > a:
                        m = a
                    h[i] = a - m
                    b += m
                    h[i + 1] = b
                    moved = True
                elif d < -lim:
                    m = (-d - lim) * 0.35
                    if m > b:
                        m = b
                    h[i] = a + m
                    b -= m
                    h[i + 1] = b
                    moved = True
                if b > maxh:
                    h[i + 1] = maxh
        else:
            if len(base) != n:
                return
            bz, sol = self._bcache()
            for i in range(n - 1):
                si = sol[i]
                sj = sol[i + 1]
                if si and sj:
                    d = (h[i] - bz[i]) - (h[i + 1] - bz[i + 1])
                    if d > lim and h[i] > 0:
                        m = min((d - lim) * 0.35, h[i])
                        h[i] -= m
                        h[i + 1] += m
                        moved = True
                    elif d < -lim and h[i + 1] > 0:
                        m = min((-d - lim) * 0.35, h[i + 1])
                        h[i] += m
                        h[i + 1] -= m
                        moved = True
                    if h[i + 1] > maxh:
                        h[i + 1] = maxh
                elif si and h[i] > 0:          # qo'shni yo'q: qor sirpanib to'kiladi
                    h[i] *= 0.8
                    moved = True
                elif sj and h[i + 1] > 0:
                    h[i + 1] *= 0.8
                    moved = True
        if self.open:
            if h[0] > lim:
                h[0] -= (h[0] - lim) * 0.3
                moved = True
            if h[-1] > lim:
                h[-1] -= (h[-1] - lim) * 0.3
                moved = True
        if moved:
            self.dirty = True

    def _tops(self):
        """Har ustun uchun (x, qor yuzasi y, tayanch y)."""
        y, col, S = self.y, self.col, self.S
        h, nz, vis, base = self.h, self.noise, self.vis, self.base
        n = len(h)
        # tayanch chiziq: silueta bo'sh ustunlarda qo'shnidan olinadi
        bb = []
        last = None
        if base is not None:
            for b in base:
                if b is not None:
                    last = b
                bb.append(last)
            nxt = None
            for i in range(n - 1, -1, -1):
                if bb[i] is None:
                    bb[i] = nxt if nxt is not None else 0.0
                else:
                    nxt = bb[i]
        out = []
        x = self.x0
        for i in range(n):
            by = y + (bb[i] if base is not None else 0.0)
            if (vis is not None and not vis[i]) or (base is not None and base[i] is None):
                v = 0.0
            else:
                v = h[i] + nz[i] * self.noise_k * min(1.0, h[i] / (5 * S))
            out.append((x, by - v, by))
            x += col
        return out

    def runs(self):
        """Qor bor uzluksiz bo'laklar: [(tana nuqtalari, ustki oq qatlam nuqtalari)].
        Qor yo'q joylarda hech narsa chizilmaydi; qor sirt chegarasidan chiqmaydi."""
        if not self.active:
            return []
        S, col = self.S, self.col
        t = self._tops()
        n = len(t)
        thr = 0.3 * S
        lift = {"ground": 3.0, "win": 2.0 * S, "icon": 0.6 * S}[self.kind]
        out = []
        i = 0
        while i < n:
            if t[i][2] - t[i][1] < thr:
                i += 1
                continue
            j = i
            while j + 1 < n and t[j + 1][2] - t[j + 1][1] >= thr:
                j += 1
            seg = t[i:j + 1]
            i = j + 1
            if len(seg) < 2:
                continue
            xl = max(self.x0, seg[0][0] - col * 0.5)
            xr = min(self.x1, seg[-1][0] + col * 0.5)
            body = [xl, seg[0][2] + lift]
            for (x, ty, by) in seg:
                body += [x, ty]
            body += [xr, seg[-1][2] + lift]
            for (x, ty, by) in reversed(seg):
                body += [x, by + lift]
            top, low = [], []
            for (x, ty, by) in seg:
                top += [x, ty]
            for (x, ty, by) in reversed(seg):
                low += [x, ty + min((by - ty) * 0.55, 2.6 * S) + 0.5]
            out.append((body, top + low))
        return out

    def clear(self):
        self.h = [0.0] * len(self.h)
        self.dirty = True
        self.urgent = True


class Ball:
    __slots__ = ("x", "y", "r", "vx", "vy", "state", "under", "over")

    def __init__(self, x, y, r):
        self.x, self.y, self.r = x, y, r
        self.vx = self.vy = 0.0
        self.state = "free"      # free | rest | held | roll
        self.under = None
        self.over = None


class Snowman:
    def __init__(self, x, radii):
        self.x = x
        self.radii = radii
        self.age = 0
        self.dying = False
        self.gone = set()


class World:
    def __init__(self, W, H, ground, S):
        self.W, self.H, self.ground, self.S = W, H, ground, S
        self.col = max(2, int(round(4 * S)))
        self.slope = 1.4 * S
        self.ground_pile = Pile(0, W, ground, self.col, 22 * S, self.slope, False, S)
        self.xmin, self.xmax = 0, W          # ish maydoni chegaralari (taskbar yon tomonda bo'lsa)
        self.ground_target = ground
        self.low = False                     # kuchsiz kompyuter rejimi
        self.cursor_repel = True             # kursor yaqinida qor uchib ketadi
        self.mx = self.my = -1
        self.cvx = self.cvy = 0.0            # kursor tezligi (px/kadr)
        self.pm = None
        self.max_chunks = MAX_CHUNKS
        self.bw = 64 * S
        self.buckets = {}                    # x bo'yicha sirtlar (tez qidirish uchun)
        self.surfaces = {}
        self.surf_list = []
        self.n_flakes = 320
        self.snowing = True
        self.wind = 0.0                      # px/kadr (yaqin zarralar uchun)
        self.wind_n = 0.0                    # -1 (chapga) ... +1 (o'ngga)
        self.wind_base = 0.25                # slayder: yo'nalish va kuch (-1..1)
        self.wind_gust = 0.4                 # shamol zarbalari (0..1)
        self.wind_auto = True                # avtomatik: yo'nalish o'zi o'zgaradi
        self.flakes = [Flake(W, H, S, True) for _ in range(self.n_flakes)]
        self.chunks = []
        self.parts = []
        self.events = []
        self.dead = []           # o'chirilishi kerak bo'lgan canvas id lari
        self.balls = []
        self.snowmen = []
        self.held = None
        self.grab = (0.0, 0.0)
        self.roll_x = 0.0
        self.prev_down = False
        self.prev_rdown = False
        self.hist = []
        self.t = 0

    # ---------------- asosiy qadam ----------------
    def step(self, mx, my, down, rdown=False):
        self.t += 1
        t = self.t
        if self.pm is None or mx < 0 or self.pm[0] < 0:
            self.cvx = self.cvy = 0.0
        else:
            self.cvx = 0.6 * self.cvx + 0.4 * (mx - self.pm[0])
            self.cvy = 0.6 * self.cvy + 0.4 * (my - self.pm[1])
        self.pm = (mx, my)
        self.mx, self.my = mx, my
        if self.ground != self.ground_target:
            self._ease_ground()
        self.update_wind()
        self.update_flakes()
        self.update_mouse(mx, my, down, rdown)
        self.update_balls()
        self.update_chunks()
        self.update_parts()
        for sm in self.snowmen:
            sm.age += 1
        for ev in list(self.events):
            if t >= ev[0]:
                self.events.remove(ev)
                ev[1]()
        if t % (4 if self.low else 2) == 0:
            gp = self.ground_pile
            gp.relax()
            gp.h = [v * 0.9991 for v in gp.h]     # juda sekin erish: qor haddan oshmaydi
            for s in self.surf_list:
                if max(s.h) > 0.05:
                    s.relax()
        if t % 15 == 0:      # to'lib ketgan qor ba'zan o'zi sirpanib tushadi
            for s in self.surf_list:
                if s.maxh >= 12 * self.S and max(s.h) >= 0.85 * s.maxh \
                        and random.random() < 0.12:
                    self.shed(s, 0.25, maxn=5)

    WIND_MAX = 4.5

    def update_wind(self):
        """Shamol: qo'lda (slayder) yoki avtomatik, ustiga tasodifiy zarbalar; silliq o'zgaradi."""
        t = self.t
        if self.wind_auto:
            base = abs(self.wind_base) * (0.55 * math.sin(t * 0.0035) + 0.35 * math.sin(t * 0.0097 + 1.7))
        else:
            base = self.wind_base
        gust = (self.wind_gust * (0.6 * math.sin(t * 0.031 + 0.5) + 0.4 * math.sin(t * 0.083 + 2.1))
                * (0.25 + abs(base)))
        target = max(-1.0, min(1.0, base + gust))
        self.wind_n += (target - self.wind_n) * 0.08
        self.wind = self.wind_n * self.WIND_MAX

    def clear(self):
        self.ground_pile.clear()
        for s in self.surfaces.values():
            s.clear()
        for c in self.chunks:
            if c.item is not None:
                self.dead.append(c.item)
        self.chunks.clear()
        self.parts.clear()
        self.events.clear()
        self.balls.clear()
        self.snowmen.clear()
        self.held = None

    # ---------------- qor parchalari ----------------
    def update_flakes(self):
        S, W, H = self.S, self.W, self.H
        gp = self.ground_pile
        buckets = self.buckets
        bw = self.bw
        target = self.n_flakes if self.snowing else 0
        extra = len(self.flakes) - target
        alive = []
        wind = self.wind
        wn = self.wind_n
        t = self.t
        cx, cy, cvx, cvy = self.mx, self.my, self.cvx, self.cvy
        repel = (self.cursor_repel and not self.low and 0 <= cx < W and 0 <= cy < H)
        R = 90.0 * S
        R2 = R * R
        ytop = 1e9                       # eng baland sirt qatlami: undan yuqoridagi zarra hech narsaga tegmaydi
        for s_ in self.surf_list:
            v_ = s_.y - s_.maxh - 14 * S
            if v_ < ytop:
                ytop = v_
        gtop = gp.y - gp.maxh - 2 * S
        for f in self.flakes:
            oy = f.y
            f.y += f.v
            f.x += (wind * (0.4 + 0.8 * f.z)
                    + math.sin(f.ph + t * f.fr) * f.wob * (1.0 + 1.2 * abs(wn))) * S
            f.ang += f.spin
            if repel:                      # kursor yaqinlashsa qor undan uchib ketadi
                dx = f.x - cx
                dy = f.y - cy
                if -R < dx < R and -R < dy < R:
                    d2 = dx * dx + dy * dy
                    if d2 < R2:
                        d = math.sqrt(d2) + 1e-3
                        q = 1.0 - d / R
                        q *= q
                        f.ex += (dx / d * 0.8 * S + cvx * 0.08) * q
                        f.ey += (dy / d * 0.6 * S + cvy * 0.08) * q
            if f.ex or f.ey:
                lim = 12.0 * S
                f.ex = max(-lim, min(lim, f.ex))
                f.ey = max(-lim, min(lim, f.ey))
                f.x += f.ex
                f.y += f.ey
                f.ex *= 0.9
                f.ey *= 0.9
                if abs(f.ex) < 0.02 and abs(f.ey) < 0.02:
                    f.ex = f.ey = 0.0
            if f.x < 0:
                f.x += W
            elif f.x >= W:
                f.x -= W
            landed = None
            besttop = None
            if f.y >= ytop:
                for s in buckets.get(int(f.x // bw), ()):
                    if s.x0 <= f.x <= s.x1:
                        i = s.idx(f.x)
                        if (s.vis is not None and not s.vis[i]) or not s.solid(i):
                            continue
                        top = s.top_at(i)
                        if oy < top <= f.y and (besttop is None or top < besttop):
                            landed, besttop = s, top
            if landed is None and f.y >= gtop and f.y >= gp.y - gp.height_at(f.x):
                landed = gp
            if landed is not None:
                landed.add(f.x, f.r)
                if extra > 0:
                    extra -= 1
                    if f.item is not None:
                        self.dead.append(f.item)
                    continue
                f.respawn(W, H, S)
            alive.append(f)
        while len(alive) < target:
            alive.append(Flake(W, H, S, False))
        if len(alive) > target and target > 0:
            for f in alive[target:]:
                if f.item is not None:
                    self.dead.append(f.item)
            alive = alive[:target]
        self.flakes = alive

    # ---------------- bo'laklar (chunk) ----------------
    def spawn_chunk(self, x, y, vx, vy, r, dust=False):
        x = min(max(x, self.xmin + 1.0), self.xmax - 1.0)
        lim = 30 * self.S
        vx = max(-lim, min(lim, vx))
        if len(self.chunks) >= self.max_chunks:
            self.ground_pile.add(x, r)
            return
        self.chunks.append(Chunk(x, y, vx, vy, r, dust))

    def spawn_soft(self, x, y, vx, vy, r):
        """Mayda, shakli notekis, yumshoq tushadigan qor zarrasi."""
        S = self.S
        x = min(max(x, self.xmin + 1.0), self.xmax - 1.0)
        lim = 30 * S
        vx = max(-lim, min(lim, vx))
        if len(self.chunks) >= self.max_chunks:
            self.ground_pile.add(x, r)
            return
        c = Chunk(x, y, vx, vy, r, False)
        c.soft = True
        c.shape = rough_shape(4, 6, 0.6, 1.25, random.uniform(1.0, 1.5))
        c.ph = random.uniform(0, 6.28)
        c.vmax = random.uniform(1.8, 3.6) * S
        c.ang = random.uniform(0, 6.28)
        c.spin = random.uniform(-0.12, 0.12)
        c.tier = random.choice((2, 3, 3))
        self.chunks.append(c)

    def land_on(self, x, oy, y):
        """Tushayotgan qor oyna yoki ikonka ustiga tushsa, o'sha sirtni qaytaradi.
        Oyna qor ichiga qarab siljisa ham (yuqoriga yoki yon tomonga), qorni ushlab oladi."""
        best, bt = None, None
        for s in self.buckets.get(int(x // self.bw), ()):
            if s.x0 <= x <= s.x1:
                i = s.idx(x)
                if (s.vis is not None and not s.vis[i]) or not s.solid(i):
                    continue
                top = s.top_at(i)
                ref = top + (s.prev_y - s.y)
                if oy < max(top, ref) and y >= top and (bt is None or top < bt):
                    best, bt = s, top
        return best

    def update_chunks(self):
        S, W = self.S, self.W
        gp = self.ground_pile
        t = self.t
        alive = []
        for c in self.chunks:
            c.age += 1
            oy = c.y
            if (not c.dust and not c.soft and c.r > 2.6 * S and random.random() < 0.025
                    and len(alive) + len(self.chunks) < self.max_chunks * 1.5):
                # havoda katta qor bo'lagi yumshoq bo'laklarga ajraladi
                k = random.choice((2, 3))
                nr = c.r / math.sqrt(k) * 0.95
                for _ in range(k):
                    alive.append(Chunk(c.x + random.uniform(-c.r, c.r) * 0.6,
                                       c.y + random.uniform(-c.r, c.r) * 0.4,
                                       c.vx + random.uniform(-1.8, 1.8) * S,
                                       c.vy + random.uniform(-1.0, 0.6) * S, nr, False))
                for _ in range(2):
                    alive.append(Chunk(c.x, c.y, c.vx + random.uniform(-2.5, 2.5) * S,
                                       c.vy + random.uniform(-2, 1) * S,
                                       random.uniform(0.6, 1.2) * S, True))
                if c.item is not None:
                    self.dead.append(c.item)
                continue
            if c.soft:      # mayin: sekin, tebranib, shamolda suzib tushadi
                c.vy += 0.18 * S
                if c.vy > c.vmax:
                    c.vy = c.vmax + (c.vy - c.vmax) * 0.8
                c.vx *= 0.965
                c.vx += math.sin(c.ph + t * 0.09) * 0.12 * S + self.wind * 0.03
                c.ang += c.spin
            elif c.dust:
                c.vy += 0.18 * S
                c.vx += self.wind * 0.02
                c.vx *= 0.96
                c.vy *= 0.97
            else:
                c.vy += GRAVITY * S * 0.9
                c.vx *= 0.985
            c.x += c.vx
            c.y += c.vy
            if c.x < self.xmin:
                c.x, c.vx = float(self.xmin), abs(c.vx) * 0.3
            elif c.x > self.xmax:
                c.x, c.vx = float(self.xmax), -abs(c.vx) * 0.3
            target = self.land_on(c.x, oy, c.y) if c.age > 8 else None
            if target is None and c.y + c.r * 0.5 >= gp.y - gp.height_at(c.x):
                target = gp
            if target is not None:
                target.add(c.x, c.r)               # sakramasdan qatlamga qo'shiladi
                if c.item is not None:
                    self.dead.append(c.item)
                continue
            alive.append(c)
        self.chunks = alive

    def sphere_burst(self, cx, cy, R, bias, vscale, ndir, gain=BALL_GAIN):
        S = self.S
        n = max(8, min(34, int(R / S * 0.7) + 8))
        a = math.pi * R * R / gain * 0.85 / n
        rc = math.sqrt(a / (math.pi * GAIN))
        for _ in range(n):
            ang = random.uniform(0, 6.283)
            rad = R * math.sqrt(random.random()) * 0.8
            px, py = cx + math.cos(ang) * rad, cy + math.sin(ang) * rad
            if ndir is None:
                dx, dy = math.cos(ang), math.sin(ang)
            else:
                dx = ndir[0] + random.uniform(-1, 1) * 1.1
                dy = ndir[1] + random.uniform(-1, 1) * 1.1
                ln = math.hypot(dx, dy) or 1.0
                dx, dy = dx / ln, dy / ln
            sp = random.uniform(0.25, 1.0) * vscale
            self.spawn_chunk(px, py, bias[0] + dx * sp,
                             bias[1] + dy * sp - random.uniform(0, 2.4) * S,
                             rc * random.uniform(0.7, 1.3))
        for _ in range(n * 2):    # mayda qor changi
            ang = random.uniform(0, 6.283)
            rad = R * math.sqrt(random.random()) * 0.9
            px, py = cx + math.cos(ang) * rad, cy + math.sin(ang) * rad
            if ndir is None:
                dx, dy = math.cos(ang), math.sin(ang)
            else:
                dx = ndir[0] + random.uniform(-1, 1) * 1.4
                dy = ndir[1] + random.uniform(-1, 1) * 1.4
                ln = math.hypot(dx, dy) or 1.0
                dx, dy = dx / ln, dy / ln
            sp = random.uniform(0.3, 1.2) * vscale * 1.1
            self.spawn_chunk(px, py, bias[0] + dx * sp, bias[1] + dy * sp - S,
                             random.uniform(0.6, 1.3) * S, dust=True)

    def shatter_ball(self, b, normal, speed):
        S = self.S
        if b in self.balls:
            self.balls.remove(b)
        if b.under is not None:
            b.under.over = None
            b.under = None
        if b.over is not None:
            o = b.over
            o.under = None
            o.state = "free"
            b.over = None
        if self.held is b:
            self.held = None
        if normal is None:
            self.sphere_burst(b.x, b.y, b.r, (0.0, 0.0), 8 * S, None)
        else:
            nx, ny = normal
            vn = b.vx * nx + b.vy * ny
            rx, ry = b.vx - 2 * vn * nx, b.vy - 2 * vn * ny   # qaytgan tezlik
            self.sphere_burst(b.x, b.y, b.r, (rx * 0.3, ry * 0.3),
                              min(speed * 0.55, 15 * S), normal)

    def shed(self, p, frac, vx0=0.0, vy0=0.0, edge=None, maxn=10):
        """Qatlamning frac ulushini bo'laklar sifatida to'kib yuboradi."""
        S = self.S
        total = p.area()
        if total <= 1 or frac <= 0:
            return
        area = total * min(1.0, frac)
        n = max(1, min(maxn, int(area / 60) + 1))
        cols = len(p.h)
        for _ in range(n):
            if edge == "L":
                i = random.randint(0, min(cols - 1, 6))
            elif edge == "R":
                i = random.randint(max(0, cols - 7), cols - 1)
            else:
                i = random.choices(range(cols), weights=[v + 0.001 for v in p.h])[0]
            x = p.x0 + i * p.col
            got = p.take(x, 2 * p.col, area / n)
            if got < 2:
                continue
            self._spawn_group(x, p.top_y_at(x), got, vx0, vy0, 0.0, 2 * p.col)

    def release_snow(self, p, vx=0.0, vy=0.0, stagger=0):
        """Sirtdagi butun qorni bo'laklarga aylantirib uchirib yuboradi va sirtni tozalaydi.
        (vx, vy) — sirtning kadr boshiga tezligi: qor shu tomonga sachrab uchadi.
        stagger>0: qor birdaniga emas, shuncha kadr ichida bosqichma-bosqich to'kiladi."""
        S = self.S
        cols = len(p.h)
        g = 3
        groups = []
        for j in range(0, cols, g):
            area = sum(p.h[j:j + g]) * p.col
            if area >= 2:
                xc = p.x0 + (j + g / 2.0) * p.col
                groups.append((xc, p.top_y_at(xc), area))
            for k in range(j, min(j + g, cols)):
                p.h[k] = 0.0
        p.dirty = True
        p.urgent = True
        lift = min(9 * S, math.hypot(vx, vy) * 0.3)
        width = g * p.col
        for xc, ty, area in groups:
            delay = random.randint(0, stagger) if stagger else 0
            fn = (lambda xc=xc, ty=ty, area=area:
                  self._spawn_group(xc, ty, area, vx, vy, lift, width))
            if delay <= 0:
                fn()
            else:
                self.events.append([self.t + delay, fn])

    def _spawn_group(self, xc, ty, area, vx, vy, lift, width):
        S = self.S
        n = max(1, min(16, int(area / 22) + 1))
        r0 = math.sqrt(area / n / (math.pi * GAIN))
        for _ in range(n):
            r = min(2.4 * S, max(0.7 * S, r0 * random.uniform(0.75, 1.25)))
            self.spawn_soft(xc + random.uniform(-width / 2, width / 2),
                            ty - r + random.uniform(0, 3 * S),
                            vx * random.uniform(0.6, 1.25) + random.uniform(-1.2, 1.2) * S,
                            vy * 0.5 - random.uniform(0.2, 1.0) * lift
                            + random.uniform(-0.3, 0.8) * S, r)

    def set_low(self, flag):
        """Kuchsiz kompyuter rejimi: kamroq bo'lak va kamroq hisob-kitob."""
        self.low = bool(flag)
        self.max_chunks = 200 if flag else MAX_CHUNKS

    def set_bounds(self, xmin, xmax, ground, instant=False):
        """Ish maydoni (taskbar hisobga olingan) o'zgarsa yer va devorlar unga moslashadi."""
        if xmax - xmin < 200:
            return
        self.xmin, self.xmax = xmin, xmax
        self.ground_target = ground
        if instant:
            self.ground = ground
        self.ground_pile.move(xmin, xmax, self.ground)

    def _ease_ground(self):
        """Taskbar siljisa yoki yashirinsa, yer silliq ko'tarilib/tushadi: qor va sharchalar birga."""
        S = self.S
        d = self.ground_target - self.ground
        dy = d if abs(d) < 0.5 else max(-6 * S, min(6 * S, d * 0.25))
        self.ground += dy
        self.ground_pile.move(self.xmin, self.xmax, self.ground)
        for b in self.balls:
            b.y += dy

    def impact_puff(self, x, y, speed, r):
        """Sharcha yerga urilganda: qor ozgina botadi va mayda zarralar sachraydi."""
        S = self.S
        n = int(min(10, 2 + speed * 0.5 / S))
        got = self.ground_pile.take(x, r * 0.6, n * 18)
        pr = max(0.7 * S, math.sqrt(max(got, n * 10) / n / (math.pi * GAIN)))
        k = 0.5 + speed / (20 * S)
        for _ in range(n):
            px = x + random.uniform(-r * 0.6, r * 0.6)
            self.spawn_soft(px, self.ground_pile.top_y_at(px) - pr,
                            random.uniform(-3, 3) * S * k,
                            -random.uniform(0.8, 2.2) * S * (1 + speed / (12 * S)),
                            pr * random.uniform(0.7, 1.2))

    def fling_icon(self, idx, vx, vy):
        """Ikonka sudralayotganda ustidagi qor sudrash tomoniga sachrab uchadi."""
        s = self.surfaces.get(("i", idx))
        if s is None or s.area() < 2:
            return
        S = self.S
        s.moving = True
        s.still = 0
        self.release_snow(s, max(-28 * S, min(28 * S, vx)), max(-12 * S, min(12 * S, vy)))

    def burst_pile(self, p, mx):
        S = self.S
        R = (55 if p is self.ground_pile else 38) * S
        j0 = p.idx(mx - R)
        j1 = p.idx(mx + R)
        j = j0
        while j <= j1:
            area = 0.0
            for jj in range(j, min(j + 3, j1 + 1)):
                x = p.x0 + jj * p.col
                dx = abs(x - mx)
                if dx > R:
                    continue
                frac = 0.45 * (1 + math.cos(math.pi * dx / R)) * 0.95
                area += p.h[jj] * frac * p.col
                p.h[jj] -= p.h[jj] * frac
            if area >= 2:
                xc = p.x0 + (j + 1) * p.col
                pieces = int(area / (math.pi * GAIN * (6 * S) ** 2)) + 1
                r = math.sqrt(area / pieces / (math.pi * GAIN))
                ty = p.top_y_at(xc)
                for _ in range(pieces):
                    self.spawn_chunk(
                        xc + random.uniform(-p.col, p.col), ty - r,
                        (xc - mx) / R * 6 * S + random.uniform(-1.5, 1.5) * S,
                        -random.uniform(2.5, 8.5) * S, r)
                for _ in range(2):
                    self.spawn_chunk(xc, ty - S,
                                     (xc - mx) / R * 5 * S + random.uniform(-2, 2) * S,
                                     -random.uniform(2, 7) * S,
                                     random.uniform(0.6, 1.2) * S, dust=True)
            j += 3
        p.dirty = True
        p.urgent = True

    # ---------------- qorbobo qismlari ----------------
    def spawn_part(self, kind, x, y, vx, vy, s, w=0.0):
        if len(self.parts) < 80:
            self.parts.append(Part(kind, x, y, vx, vy, s, w))

    def update_parts(self):
        S = self.S
        gp = self.ground_pile
        alive = []
        for p in self.parts:
            p.vy += GRAVITY * S
            p.x += p.vx
            p.y += p.vy
            p.ang += p.vang
            if p.x < self.xmin or p.x > self.xmax:
                p.vx = -p.vx * 0.5
                p.x = min(max(p.x, float(self.xmin)), float(self.xmax))
            gy = gp.y - gp.height_at(p.x)
            if p.y + p.ext >= gy:
                p.y = gy - p.ext
                if p.vy > 3 * S:
                    p.vy = -p.vy * 0.35
                    p.vx *= 0.7
                    p.vang *= 0.6
                else:
                    p.vy = 0.0
                    p.vx *= 0.8
                    p.vang *= 0.7
                    p.rest += 1
            if p.rest > 100:
                p.k -= 0.05
                if p.k <= 0:
                    continue
            alive.append(p)
        self.parts = alive

    def snowman_circles(self, sm):
        r0, r1, r2 = sm.radii
        y0 = self.ground - r0
        y1 = y0 - (r0 + r1) * 0.82
        y2 = y1 - (r1 + r2) * 0.82
        return [(sm.x, y0, r0), (sm.x, y1, r1), (sm.x, y2, r2)]

    def destroy_snowman(self, sm, power=1.0):
        if sm.dying:
            return
        sm.dying = True
        circles = self.snowman_circles(sm)
        for idx, delay in ((2, 0), (1, 5), (0, 10)):
            self.events.append([self.t + delay,
                                lambda i=idx: self.burst_snowman_part(sm, i, circles, power)])

    def burst_snowman_part(self, sm, idx, circles, power):
        S = self.S
        cx, cy, cr = circles[idx]
        self.sphere_burst(cx, cy, cr, (0.0, 0.0), 8 * S * power, None)
        r0, r1, r2 = sm.radii
        rnd = random.uniform
        if idx == 2:
            hx, hy = circles[2][0], circles[2][1]
            self.spawn_part("hat", hx + 0.2 * r2, hy - 0.9 * r2, rnd(-3, 5) * S * power,
                            -rnd(6, 11) * S * power, r2)
            self.spawn_part("nose", hx + 0.5 * r2, hy + 0.1 * r2, rnd(2, 8) * S * power,
                            -rnd(3, 8) * S * power, r2 * 0.95)
            self.spawn_part("scarf", hx, hy + 0.82 * r2, rnd(-5, 5) * S * power,
                            -rnd(2, 6) * S * power, r2 * 1.6, max(4 * S, 0.28 * r2))
            for sx in (-0.33, 0.33):
                self.spawn_part("coal", hx + sx * r2, hy - 0.22 * r2, rnd(-6, 6) * S * power,
                                -rnd(3, 9) * S * power, 0, max(1.6 * S, 0.09 * r2))
            for k in range(-2, 3):
                self.spawn_part("coal", hx + k * 0.15 * r2, hy + 0.5 * r2,
                                rnd(-6, 6) * S * power, -rnd(2, 8) * S * power, 0,
                                max(1.3 * S, 0.045 * r2))
        elif idx == 1:
            for sign in (-1, 1):
                self.spawn_part("stick", cx + sign * r1 * 1.3, cy - r1 * 0.5,
                                sign * rnd(3, 9) * S * power, -rnd(3, 9) * S * power,
                                r1 * 1.2, max(3 * S, 0.1 * r1))
            for t in (-0.4, 0.0, 0.4):
                self.spawn_part("coal", cx, cy + t * r1, rnd(-6, 6) * S * power,
                                -rnd(2, 7) * S * power, 0, max(2 * S, 0.08 * r1))
        sm.gone.add(idx)
        if len(sm.gone) >= 3 and sm in self.snowmen:
            self.snowmen.remove(sm)

    # ---------------- sichqoncha ----------------
    def hit_test(self, mx, my):
        S = self.S
        for b in reversed(self.balls):
            if b.state in ("rest", "free") and b.over is None:
                if (mx - b.x) ** 2 + (my - b.y) ** 2 <= (b.r + 3 * S) ** 2:
                    return ("ball", b)
        for sm in reversed(self.snowmen):
            if sm.dying:
                continue
            for cx, cy, cr in self.snowman_circles(sm):
                if (mx - cx) ** 2 + (my - cy) ** 2 <= (cr + 3 * S) ** 2:
                    return ("snowman", sm)
        for s in self.surf_list:
            if s.x0 <= mx <= s.x1:
                i = s.idx(mx)
                if (s.vis is not None and not s.vis[i]) or not s.solid(i):
                    continue
                if s.h[i] >= 2.5 * S and s.top_at(i) - 4 * S <= my <= s.surf_y(i) + 2 * S:
                    return ("pile", s)
        gp = self.ground_pile
        if self.xmin <= mx < self.xmax and my <= gp.y:
            h = gp.height_at(mx)
            if h >= 3 * S and my >= gp.y - h - 4 * S:
                return ("pile", gp)
        return None

    def update_mouse(self, mx, my, down, rdown):
        S = self.S
        pressed = down and not self.prev_down
        rpressed = rdown and not self.prev_rdown
        self.prev_down, self.prev_rdown = down, rdown
        self.hist.append((mx, my))
        if len(self.hist) > 4:
            self.hist.pop(0)
        b = self.held
        if b is None:
            if pressed or rpressed:
                hit = self.hit_test(mx, my)
                if hit is not None:
                    kind, obj = hit
                    if rpressed:
                        if kind == "ball":
                            self.shatter_ball(obj, None, 10 * S)
                        elif kind == "snowman":
                            self.destroy_snowman(obj)
                        else:
                            self.burst_pile(obj, mx)
                    elif kind == "ball":
                        self.grab_ball(obj, mx, my)
                    elif kind == "pile" and obj is self.ground_pile:
                        r0 = 6 * S
                        nb = Ball(mx, self.ground - r0, r0)
                        nb.state = "roll"
                        self.balls.append(nb)
                        self.held = nb
                        self.roll_x = mx
            return
        if not down:
            self.release()
            return
        if b.state == "roll":
            dist = abs(mx - self.roll_x)
            self.roll_x = mx
            if dist > 0 and b.r < MAX_BALL * S:
                need = 2 * math.pi * b.r * (dist * 0.1) / BALL_GAIN
                got = self.ground_pile.take(mx, b.r, need)
                if got > 0:
                    b.r = min(MAX_BALL * S,
                              b.r + got * BALL_GAIN / (2 * math.pi * b.r))
            b.x = min(max(mx, self.xmin + b.r), self.xmax - b.r)
            b.y = self.ground - b.r
            if my < b.y - b.r - 25 * S:
                b.state = "held"
                self.grab = (b.x - mx, b.y - my)
        else:
            b.x = min(max(mx + self.grab[0], self.xmin + b.r), self.xmax - b.r)
            b.y = min(max(my + self.grab[1], b.r), self.ground - b.r)

    def grab_ball(self, b, mx, my):
        if b.under is not None:
            b.under.over = None
            b.under = None
        b.state = "held"
        b.vx = b.vy = 0.0
        self.held = b
        self.grab = (b.x - mx, b.y - my)
        self.hist = [(mx, my)]

    def release(self):
        b = self.held
        self.held = None
        S = self.S
        if b.state == "roll":
            if b.r < 9 * S:
                self.balls.remove(b)
                return
            b.state = "free"
            b.vx = b.vy = 0.0
            return
        n = len(self.hist) - 1
        vx = vy = 0.0
        if n >= 1:
            vx = (self.hist[-1][0] - self.hist[0][0]) / n
            vy = (self.hist[-1][1] - self.hist[0][1]) / n
        sp = math.hypot(vx, vy)
        if sp < 4 * S:
            vx = vy = 0.0
        elif sp > 45 * S:
            k = 45 * S / sp
            vx *= k
            vy *= k
        b.vx, b.vy = vx, vy
        b.state = "free"

    # ---------------- sharchalar fizikasi ----------------
    def update_balls(self):
        S = self.S
        for b in list(self.balls):
            if b.state != "free" or b not in self.balls:
                continue
            b.vy += GRAVITY * S
            b.x += b.vx
            b.y += b.vy
            r = b.r
            thr = max(14 * S, 21 * S - 0.15 * r)    # shu tezlikdan oshsa — parchalanadi
            sp = math.hypot(b.vx, b.vy)
            if b.x < self.xmin + r or b.x > self.xmax - r:
                sign = 1.0 if b.x < self.xmin + r else -1.0
                if abs(b.vx) > thr:
                    self.shatter_ball(b, (sign, 0.0), sp)
                    continue
                b.x = self.xmin + r if sign > 0 else self.xmax - r
                b.vx = sign * abs(b.vx) * 0.5
            if b.y < r:
                b.y = r
                b.vy = abs(b.vy) * 0.3
            gy = self.ground - r
            if b.y >= gy:
                b.y = gy
                if b.vy > thr:
                    self.shatter_ball(b, (0.0, -1.0), sp)
                    continue
                if b.vy > 5 * S:
                    self.impact_puff(b.x, self.ground, b.vy, b.r)
                b.vy = -b.vy * 0.25 if b.vy > 2.5 * S else 0.0
                b.vx *= 0.93
            done = False
            for o in list(self.balls):
                if o is b or o.state not in ("rest", "free"):
                    continue
                dx, dy = b.x - o.x, b.y - o.y
                mind = b.r + o.r
                d2 = dx * dx + dy * dy
                if d2 >= mind * mind:
                    continue
                if (o.state == "rest" and o.over is None and b.y < o.y
                        and abs(dx) < o.r * 0.85 and b.r <= o.r * 1.1
                        and 0 <= b.vy < thr):
                    self.snap(b, o)
                    done = True
                    break
                d = math.sqrt(d2)
                if d < 0.5:
                    nx, ny = random.choice((-0.3, 0.3)), -1.0
                    nl = math.hypot(nx, ny)
                    nx, ny = nx / nl, ny / nl
                    d = 1.0
                else:
                    nx, ny = dx / d, dy / d
                if abs(dx) < 1.0 and ny < 0:
                    nx += random.choice((-0.15, 0.15))
                vn = (b.vx - o.vx) * nx + (b.vy - o.vy) * ny
                if vn < -thr:
                    self.shatter_ball(b, (nx, ny), sp)
                    done = True
                    break
                pen = mind - d
                b.x += nx * pen
                b.y += ny * pen
                vn = b.vx * nx + b.vy * ny
                if vn < 0:
                    b.vx -= 1.2 * vn * nx
                    b.vy -= 1.2 * vn * ny
            if done:
                continue
            for sm in list(self.snowmen):
                if sm.dying:
                    continue
                for cx, cy, cr in self.snowman_circles(sm):
                    dx, dy = b.x - cx, b.y - cy
                    mind = b.r + cr
                    d2 = dx * dx + dy * dy
                    if d2 >= mind * mind:
                        continue
                    d = math.sqrt(d2) or 1.0
                    nx, ny = dx / d, dy / d
                    vn = b.vx * nx + b.vy * ny
                    if vn < -thr:
                        if vn < -thr * 1.9:
                            self.destroy_snowman(sm, 1.3)
                        self.shatter_ball(b, (nx, ny), sp)
                        done = True
                        break
                    pen = mind - d
                    b.x += nx * pen
                    b.y += ny * pen
                    if vn < 0:
                        b.vx -= 1.3 * vn * nx
                        b.vy -= 1.3 * vn * ny
                if done:
                    break
            if done:
                continue
            if b.y > gy:
                b.y = gy
                b.vy = min(b.vy, 0.0)
            if b.y >= gy - 0.01 and abs(b.vx) < 0.12 * S and abs(b.vy) < 0.01:
                b.state = "rest"
                b.vx = b.vy = 0.0

    def snap(self, b, o):
        b.under = o
        o.over = b
        b.x = o.x
        b.y = o.y - (o.r + b.r) * 0.92
        b.vx = b.vy = 0.0
        b.state = "rest"
        self.check_snowman(o)

    def check_snowman(self, ball):
        base = ball
        while base.under is not None:
            base = base.under
        chain = [base]
        while chain[-1].over is not None:
            chain.append(chain[-1].over)
        if len(chain) >= 3:
            radii = sorted([c.r for c in chain[:3]], reverse=True)
            x = base.x
            for c in chain:
                if c in self.balls:
                    self.balls.remove(c)
            self.snowmen.append(Snowman(x, radii))
            if len(self.snowmen) > 8:
                self.destroy_snowman(self.snowmen[0], 0.7)

    # ---------------- oyna va ikonkalar ustidagi qor ----------------
    def set_surfaces(self, wins, icons):
        """wins: [(key,x0,y0,x1,y1,pile_ok)] z-tartibda (tepadan pastga).
        icons: [(indeks,x0,y0,x1,y1,profil)] — y0 ikonka rasmining tepasi."""
        seen = set()
        higher = []
        for key, x0, y0, x1, y1, ok in wins:
            if ok:
                k = ("w", key)
                seen.add(k)
                self._upd_surface(k, "win", x0, x1, y0, higher, None)
            higher.append((x0, y0, x1, y1))
        for key, x0, y0, x1, y1, prof in icons:
            k = ("i", key)
            seen.add(k)
            self._upd_surface(k, "icon", x0, x1, y0, higher, prof)
        for k in list(self.surfaces):
            if k not in seen:
                s = self.surfaces.pop(k)
                self.release_snow(s, 0.0, 0.0, stagger=14)   # oyna yopildi: qor to'kiladi
                for pair in s.items:
                    self.dead.append(pair[0])
                    self.dead.append(pair[1])
        self.surf_list = [s for s in self.surfaces.values() if s.active]
        self.buckets = {}
        for s in self.surf_list:
            for k in range(int(s.x0 // self.bw), int(s.x1 // self.bw) + 1):
                self.buckets.setdefault(k, []).append(s)

    def _upd_surface(self, key, kind, x0, x1, y, higher, profile):
        S = self.S
        s = self.surfaces.get(key)
        if s is None:
            if kind == "win":
                s = Pile(x0, x1, y, max(2, int(round(2 * S))), 24 * S, 0.8 * S, True,
                         S, 1.0, "win", 12.0)
            else:
                s = Pile(x0, x1, y, max(1, int(round(S))), 8 * S, 0.45 * S, True, S, 0.0,
                         "icon", 8.0)
            self.surfaces[key] = s
        else:
            dx, dy = x0 - s.x0, y - s.y
            if abs(dx) > 3 * S or abs(dy) > 3 * S:
                s.still = 0
                if not s.moving:        # siljish boshlandi: qor sachrab uchadi
                    s.moving = True
                    if kind == "icon":      # ikonka sakrab ko'chadi: yo'nalishi muhim
                        d = math.hypot(dx, dy) or 1.0
                        sp = min(28 * S, max(6 * S, d / 8.0))
                        vx, vy = dx / d * sp, dy / d * sp
                    else:
                        vx, vy = dx / 2.0, dy / 2.0
                    self.release_snow(s, max(-28 * S, min(28 * S, vx)),
                                      max(-12 * S, min(12 * S, vy)),
                                      stagger=3 if kind == "win" else 0)
                # siljish davom etayotganda tushgan yangi qor oynada qoladi (ushlab olish)
            else:
                s.still += 1
                if s.still >= 6:
                    s.moving = False
            s.move(x0, x1, y)
        if kind == "win" and (s.base is None or len(s.base) != len(s.h)):
            s.set_corners(7 * S)
        if kind == "icon":
            if s.prof_id != id(profile) or s.base is None or len(s.base) != len(s.h):
                s.set_profile(profile, x1 - x0)
                s.prof_id = id(profile)
        nv = self._vis(s, higher)
        act = nv is None or any(nv)
        if nv != s.vis or act != s.active:
            s.dirty = True
            s.urgent = True
        s.vis, s.active = nv, act

    @staticmethod
    def _vis(s, higher):
        yy = s.y - 1
        cov = [(a0, a1) for (a0, b0, a1, b1) in higher
               if b0 <= yy < b1 and a1 > s.x0 and a0 < s.x1]
        if not cov:
            return None
        n = len(s.h)
        mask = [True] * n
        for a0, a1 in cov:
            i0 = max(0, int((a0 - s.x0) // s.col))
            i1 = min(n - 1, int((a1 - s.x0) // s.col))
            for i in range(i0, i1 + 1):
                mask[i] = False
        return mask


# =====================================================================
#  Ilova: oynalar va chizish
# =====================================================================
def make_wire(W, S, seed=11):
    """Mixchalar: [(x, kenglik, osilish)] — oraliqlari notekis, tabiiy."""
    rnd = random.Random(seed)
    pegs = []
    x = -rnd.uniform(0, 150) * S
    while x < W + 300 * S:
        seg = rnd.uniform(210, 300) * S
        pegs.append((x, seg, seg * rnd.uniform(0.09, 0.12)))
        x += seg
    return pegs


def egg_points(cx, cy, a, b, dx, dy, n=20):
    """Tuxum shaklidagi lampochka (soket tomoni torroq). (dx,dy) — soketdan uchiga yo'nalish."""
    pts = []
    for k in range(n):
        ang = 6.283185 * k / n
        t = math.cos(ang)
        w = math.sin(ang) * b * (0.8 + 0.2 * t)
        al = t * a
        pts += [cx + dx * al - dy * w, cy + dy * al + dx * w]
    return pts


class Rope:
    """Ikki uchi mahkamlangan osilgan chiroq simi (Verlet arqon fizikasi).
    Kursor, shamol va otilgan sharcha simni turtadi; sim tebranadi. Tinchlansa uxlaydi
    (hisob-kitob ham, chizish ham to'xtaydi). Tezliklar px/s, qadam = 1 kadr (1/30 s)."""
    DT = 1.0 / 30.0

    def __init__(self, x0, y0, x1, y1, sag, S, seed=0):
        chord = math.hypot(x1 - x0, y1 - y0)
        n = max(8, int(chord / (22.0 * S)))
        self.n, self.S = n, S
        self.x = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
        self.y = [y0 + (y1 - y0) * i / (n - 1) + 4.0 * sag * (i / (n - 1.0)) * (1 - i / (n - 1.0))
                  for i in range(n)]
        self.px, self.py = list(self.x), list(self.y)
        arc = sum(math.hypot(self.x[i + 1] - self.x[i], self.y[i + 1] - self.y[i])
                  for i in range(n - 1))
        self.rest = arc / (n - 1)
        self.ph = random.Random(seed).uniform(0, 6.28)
        self.awake = True
        self.calm = 0

    def settle(self, steps=160):
        for _ in range(steps):
            self.step(0.0, 0.0)
        self.px, self.py = list(self.x), list(self.y)
        self.awake = False
        self.calm = 0

    def energy(self):
        e = 0.0
        for i in range(1, self.n - 1):
            dx = self.x[i] - self.px[i]
            dy = self.y[i] - self.py[i]
            e += dx * dx + dy * dy
        return e

    def poke(self, x, y, rad, vx, vy, power):
        """Kursor yoki to'p simni (x,y) nuqtada turtadi; tezlik px/s."""
        h = self.DT * 0.5
        r2 = rad * rad
        hit = False
        for i in range(1, self.n - 1):
            dx, dy = self.x[i] - x, self.y[i] - y
            d2 = dx * dx + dy * dy
            if d2 < r2:
                q = 1.0 - math.sqrt(d2) / rad
                self.px[i] -= vx * power * q * h
                self.py[i] -= vy * power * q * h
                hit = True
        if hit:
            self.awake = True
            self.calm = 0
        return hit

    def step(self, wind, t):
        n = self.n
        x, y, px, py = self.x, self.y, self.px, self.py
        sub = 2
        h = self.DT / sub
        h2 = h * h
        rest = self.rest
        g = 900.0 * self.S
        for _ in range(sub):
            for i in range(1, n - 1):
                cx, cy = x[i], y[i]
                vx = (cx - px[i]) * 0.985
                vy = (cy - py[i]) * 0.985
                w = wind * (0.8 + 0.4 * math.sin(t * 1.3 + i * 0.7 + self.ph))
                ax = (w - vx / h) * 1.1
                fy = -1.1 * abs(wind) * (0.5 + 0.5 * math.sin(t * 1.1 + i * 0.5 + self.ph))
                px[i], py[i] = cx, cy
                x[i] = cx + vx + ax * h2
                y[i] = cy + vy + (g + fy) * h2
            for _ in range(6):
                for i in range(n - 1):
                    dx = x[i + 1] - x[i]
                    dy = y[i + 1] - y[i]
                    d = math.hypot(dx, dy)
                    if d < 1e-6:
                        continue
                    k = (d - rest) / d
                    if i == 0:
                        x[1] -= dx * k
                        y[1] -= dy * k
                    elif i == n - 2:
                        x[i] += dx * k
                        y[i] += dy * k
                    else:
                        x[i] += dx * k * 0.5
                        y[i] += dy * k * 0.5
                        x[i + 1] -= dx * k * 0.5
                        y[i + 1] -= dy * k * 0.5

    def polyline(self):
        """Tugunlardan silliqlangan egri chiziq va uning yig'indi uzunliklari."""
        p = list(zip(self.x, self.y))
        for _ in range(2):
            q = [p[0]]
            for i in range(len(p) - 1):
                a, b = p[i], p[i + 1]
                q.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
                q.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
            q.append(p[-1])
            p = q
        cum = [0.0]
        for i in range(1, len(p)):
            cum.append(cum[-1] + math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]))
        return p, cum

    @staticmethod
    def at(P, cum, f):
        """Sim uzunligining f ulushidagi nuqta (x, y) va yo'nalish (tx, ty)."""
        s = f * cum[-1] if f <= 1.0 else f
        j = 0
        last = len(cum) - 2
        while j < last and cum[j + 1] < s:
            j += 1
        seg = (cum[j + 1] - cum[j]) or 1e-9
        u = max(0.0, min(1.0, (s - cum[j]) / seg))
        dx, dy = P[j + 1][0] - P[j][0], P[j + 1][1] - P[j][1]
        return P[j][0] + dx * u, P[j][1] + dy * u, dx / seg, dy / seg


def strand_points(P, cum, S, step=3.0):
    """Ikki ipli o'ralgan sim: bir-biriga o'ralib turgan ikki chiziq nuqtalari."""
    L = cum[-1]
    n = max(2, int(L / step))
    pa, pb = [], []
    j = 0
    last = len(cum) - 2
    for k in range(n + 1):
        s = L * k / n
        while j < last and cum[j + 1] < s:
            j += 1
        seg = (cum[j + 1] - cum[j]) or 1e-9
        u = max(0.0, min(1.0, (s - cum[j]) / seg))
        dx, dy = P[j + 1][0] - P[j][0], P[j + 1][1] - P[j][1]
        x, y = P[j][0] + dx * u, P[j][1] + dy * u
        tx, ty = dx / seg, dy / seg
        tw = 1.4 * S * math.sin(s * 0.42)
        pa += [x - ty * tw, y + tx * tw]
        pb += [x + ty * tw, y - tx * tw]
    return pa, pb


def bulb_geom(x, y, th, S):
    """Lampochka qismlari nuqtalari. (x,y) — simga ulangan joy; th — soketdan uchiga burchak
    (0 = to'g'ri pastga, musbat = o'ngga)."""
    dx, dy = math.sin(th), math.cos(th)
    nx, ny = -dy, dx
    Ls, a, b = 4.5 * S, 8.5 * S, 5.0 * S
    cx, cy = x + dx * (Ls + a * 0.95), y + dy * (Ls + a * 0.95)
    sock = [x + nx * 1.7 * S, y + ny * 1.7 * S, x - nx * 1.7 * S, y - ny * 1.7 * S,
            x + dx * Ls - nx * 2.3 * S, y + dy * Ls - ny * 2.3 * S,
            x + dx * Ls + nx * 2.3 * S, y + dy * Ls + ny * 2.3 * S]
    rings = []
    for f in (0.4, 0.75):
        w_ = (1.7 + 0.6 * f) * S
        rings.append([x + dx * Ls * f + nx * w_, y + dy * Ls * f + ny * w_,
                      x + dx * Ls * f - nx * w_, y + dy * Ls * f - ny * w_])
    rim = egg_points(cx, cy, a, b, dx, dy)
    mid = egg_points(cx + dx * 0.3 * S, cy + dy * 0.3 * S, a * 0.84, b * 0.8, dx, dy, 18)
    core = egg_points(cx + dx * 0.6 * S, cy + dy * 0.6 * S, a * 0.62, b * 0.55, dx, dy, 16)
    hot = egg_points(cx + dx * 0.9 * S, cy + dy * 0.9 * S, a * 0.36, b * 0.3, dx, dy, 12)
    fo = b * 0.16
    fil = [cx - dx * a * 0.4 + nx * fo, cy - dy * a * 0.4 + ny * fo,
           cx + dx * a * 0.3 + nx * fo, cy + dy * a * 0.3 + ny * fo,
           cx + dx * a * 0.3 - nx * fo, cy + dy * a * 0.3 - ny * fo,
           cx - dx * a * 0.4 - nx * fo, cy - dy * a * 0.4 - ny * fo]
    return sock, rings, rim, mid, core, hot, fil, (cx, cy)


def make_rig(W, S):
    """Spanlar: [(arqon, [(sim ulushi f, og'ish burchagi, faza), ...])]. Arqonlar muvozanatga
    keltirilgan (boshida tebranmaydi); lampochkalar sim uzunligi bo'ylab teng taqsimlanadi."""
    rnd = random.Random(7)
    spans = []
    for si, (px, seg, sag) in enumerate(make_wire(W, S)):
        if px + seg < -10 or px > W + 10:
            continue
        rope = Rope(px, 3 * S, px + seg, 3 * S, sag * 0.85, S, si)   # osilish: eski ko'rinishdagidek
        rope.settle()
        P, cum = rope.polyline()
        L = cum[-1]
        specs = []
        s = rnd.uniform(14, 22) * S
        while s < L - 14 * S:
            x, y, tx, ty = rope.at(P, cum, s / L)
            if 6 <= x <= W - 6:
                sign = 1 if (len(specs) + si) % 2 == 0 else -1
                deg = rnd.uniform(5, 25) if rnd.random() < 0.4 else rnd.uniform(25, 62)
                specs.append((s / L, sign * math.radians(deg), rnd.uniform(0, 6.28)))
            s += 36 * S * rnd.uniform(0.9, 1.18)
        spans.append((rope, specs))
    return spans


class SpanView:
    __slots__ = ("rope", "sa", "sb", "bulbs", "x0", "x1")


class Bulb:
    __slots__ = ("sock", "r1", "r2", "rim", "mid", "core", "hot", "fil", "lvl", "k",
                 "f", "th0", "a", "av", "ax", "vxp", "cx", "cy")


class App:
    def __init__(self):
        dpi_aware()
        self.root = tk.Tk()
        root = self.root
        self.S = max(1.0, root.winfo_fpixels("1i") / 96.0)
        S = self.S
        self.W = root.winfo_screenwidth()
        self.H = root.winfo_screenheight()
        wa = work_area()
        self.ground = wa[3] if wa else self.H

        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry("%dx%d+0+0" % (self.W, self.H))
        root.config(bg=KEY)
        try:
            root.attributes("-transparentcolor", KEY)
        except tk.TclError:
            print("Bu dastur Windows uchun mo'ljallangan.")
            sys.exit(1)

        self.canvas = tk.Canvas(root, width=self.W, height=self.H,
                                bg=KEY, highlightthickness=0)
        self.canvas.pack()
        root.update()

        self.world = World(self.W, self.H, self.ground, S)
        if wa:
            self.world.set_bounds(wa[0], wa[2], wa[3], instant=True)
        self.sm_sig = None
        self.lights_on = tk.BooleanVar(value=True)
        self.snow_var = tk.BooleanVar(value=True)
        self.auto_var = tk.BooleanVar(value=autostart_get())
        self.win_snow = tk.BooleanVar(value=True)
        self.icon_snow = tk.BooleanVar(value=True)
        self.mode_var = tk.StringVar(value="always")    # always | ctrl | off
        self.repel_var = tk.BooleanVar(value=True)       # kursor qorni uchiradi
        self.sway_var = tk.BooleanVar(value=True)        # chiroqlar kursor/shamolda tebranadi
        self.wind_auto_var = tk.BooleanVar(value=True)   # avtomatik shamol
        self.bulbs = []
        self.spans = []
        self.twinkle = {}
        self.lights_t0 = 0
        self.lights_built = False

        self.hwnd = None
        self.click_through = False
        self.init_window_styles()
        self.set_click_through(True)

        self.scanner = WinScanner(self.hwnd, S)
        self.icon_reader = DesktopIcons(S, self.W, self.H)
        self.icons = []
        self.icon_drag = IconDrag(S)
        self.last_wins = []
        self.mouse = (-1, -1, False)
        self.refresh_n = 0
        self.user_flakes = 320
        self.flake_cap = 600
        self.avg_ms = 0.0
        self.low_perf = False
        self.slow_n = 0
        self.paused = False
        self.fs_votes = 0
        self.tick_n = 0
        self.avg_period = 33.0           # kadrlar orasidagi haqiqiy vaqt (Tk chizishi ham hisobda)
        self.deadline = time.perf_counter()
        self.last_t0 = 0.0
        self.last_per = 0.0
        self.ran_prev = False
        self.cap_ceiling = 600           # sekinlashganda o'rganilgan zarralar chegarasi
        self.ceil_t = 0
        self.slow_logs = 0
        self.phase = (0.0, 0.0, 0.0)
        self.bsig = None
        self.psig = None
        self.timer_ok = timer_begin(1)

        self.wind_panel = None
        self.wind_last = None
        self.panel = self.build_panel()
        self.wind_panel = self.build_wind_panel()
        try:                              # boshlang'ich obyektlar GC tekshiruvidan chiqariladi (uzun pauzalar kamayadi)
            gc.collect()
            gc.freeze()
            gc.set_threshold(5000, 20, 20)
        except Exception:
            pass
        self.root.after(30, self.tick)

    # ---------- Windows oyna uslublari ----------
    def init_window_styles(self):
        try:
            u, _ = setup_api()
            self.hwnd = u.GetAncestor(self.root.winfo_id(), 2) or \
                u.GetParent(self.root.winfo_id())
        except Exception:
            self.hwnd = None

    def set_click_through(self, on):
        try:
            u = ctypes.windll.user32
            st = u.GetWindowLongW(self.hwnd, -20)
            st |= 0x08000000 | 0x80 | 0x80000    # NOACTIVATE | TOOLWINDOW | LAYERED
            if on:
                st |= 0x20                        # TRANSPARENT
            else:
                st &= ~0x20
            u.SetWindowLongW(self.hwnd, -20, st)
        except Exception:
            pass
        self.click_through = on

    # ---------- Boshqaruv oynasi ----------
    def build_panel(self):
        S = self.S
        bg, fg = "#0f2742", "#e8f2ff"
        p = tk.Toplevel(self.root)
        p.title("Yangi yil qori")
        p.geometry("%dx%d+%d+%d" % (int(350 * S), int(560 * S), int(70 * S), int(40 * S)))
        p.resizable(False, False)
        p.configure(bg=bg)
        p.protocol("WM_DELETE_WINDOW", self.quit)

        tk.Label(p, text="❄  Yangi yil bilan!  ❄", font=("Segoe UI", 15, "bold"),
                 bg=bg, fg="white").pack(pady=(12, 2))
        help_text = ("Chap tugma: qorni sudrab sharcha yasang, ko'tarib otib yuboring; "
                     "3 ta sharcha ustma-ust = qorbobo. O'ng tugma: qorbobo, sharcha "
                     "yoki qor uyumini parchalaydi.")
        tk.Label(p, text=help_text, justify="left", wraplength=int(315 * S),
                 bg=bg, fg="#cfe3ff", font=("Segoe UI", 8)).pack(padx=14, pady=4)

        def on_scale(v):
            self.user_flakes = int(float(v))
            self.world.n_flakes = min(self.user_flakes, self.flake_cap)

        sc = tk.Scale(p, from_=20, to=600, orient="horizontal", label="Qor miqdori",
                      command=on_scale, bg=bg, fg=fg, troughcolor="#1d4e89",
                      highlightthickness=0, length=int(290 * S))
        sc.set(320)
        sc.pack(pady=2)

        def chk(text, var, cmd=None):
            tk.Checkbutton(p, text=text, variable=var, command=cmd, bg=bg, fg=fg,
                           selectcolor="#1d4e89", activebackground=bg,
                           activeforeground="white", font=("Segoe UI", 9)
                           ).pack(anchor="w", padx=24)

        chk("Qor yog'sin", self.snow_var,
            lambda: setattr(self.world, "snowing", self.snow_var.get()))
        chk("Oynalar tepasida qor to'plansin", self.win_snow)
        chk("Ish stoli ikonkalari ustida qor", self.icon_snow)
        chk("Kursor qorni uchirib yuboradi", self.repel_var,
            lambda: setattr(self.world, "cursor_repel", self.repel_var.get()))
        chk("Yangi yil chiroqlari (tepada)", self.lights_on)
        chk("Chiroqlar kursor/shamolda tebranadi", self.sway_var)
        chk("Kompyuter yonganda o'zi ishga tushsin", self.auto_var,
            lambda: autostart_set(self.auto_var.get()))

        tk.Label(p, text="Sichqoncha bilan o'ynash:", bg=bg, fg=fg,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=24, pady=(6, 0))
        mrow = tk.Frame(p, bg=bg)
        mrow.pack(anchor="w", padx=24)
        for text, val in (("Har doim", "always"), ("Ctrl bilan", "ctrl"), ("O'chiq", "off")):
            tk.Radiobutton(mrow, text=text, variable=self.mode_var, value=val, bg=bg, fg=fg,
                           selectcolor="#1d4e89", activebackground=bg,
                           activeforeground="white", font=("Segoe UI", 9)
                           ).pack(side="left", padx=(0, 8))

        row = tk.Frame(p, bg=bg)
        row.pack(pady=12)
        tk.Button(row, text="Shamol paneli", width=12, command=self.show_wind_panel,
                  bg="#1d6f8f", fg="white", relief="flat").pack(side="left", padx=4)
        tk.Button(row, text="Tozalash", width=9, command=self.world.clear,
                  bg="#2a6fb0", fg="white", relief="flat").pack(side="left", padx=4)
        tk.Button(row, text="Chiqish", width=9, command=self.quit,
                  bg="#b03a3a", fg="white", relief="flat").pack(side="left", padx=4)
        return p

    def build_wind_panel(self):
        """Shamolni boshqarish paneli: yo'nalish va kuch, zarbalar, avtomatik rejim, tayyor sozlamalar."""
        S = self.S
        bg, fg = "#0f2742", "#e8f2ff"
        p = tk.Toplevel(self.root)
        p.title("Shamol")
        p.geometry("%dx%d+%d+%d" % (int(330 * S), int(500 * S), int(440 * S), int(40 * S)))
        p.resizable(False, False)
        p.configure(bg=bg)
        p.protocol("WM_DELETE_WINDOW", p.withdraw)       # yopilsa yashiriladi, dastur ishlayveradi
        tk.Label(p, text="Shamol", font=("Segoe UI", 15, "bold"), bg=bg,
                 fg="white").pack(pady=(12, 2))
        self.wind_cv = tk.Canvas(p, width=int(290 * S), height=int(64 * S), bg="#0b1d33",
                                 highlightthickness=0)
        self.wind_cv.pack(pady=4)
        self.wind_txt = tk.Label(p, text="", bg=bg, fg=fg, font=("Segoe UI", 10, "bold"))
        self.wind_txt.pack()

        def on_dir(v):
            self.world.wind_base = float(v) / 100.0

        def on_gust(v):
            self.world.wind_gust = float(v) / 100.0

        self.wind_sc = tk.Scale(p, from_=-100, to=100, orient="horizontal",
                                label="Yo'nalish va kuch  (chapga  ←  0  →  o'ngga)",
                                command=on_dir, bg=bg, fg=fg, troughcolor="#1d4e89",
                                highlightthickness=0, length=int(290 * S))
        self.wind_sc.set(int(round(self.world.wind_base * 100)))
        self.wind_sc.pack(pady=2)
        self.gust_sc = tk.Scale(p, from_=0, to=100, orient="horizontal",
                                label="O'zgaruvchanlik (shamol zarbalari)",
                                command=on_gust, bg=bg, fg=fg, troughcolor="#1d4e89",
                                highlightthickness=0, length=int(290 * S))
        self.gust_sc.set(int(round(self.world.wind_gust * 100)))
        self.gust_sc.pack(pady=2)

        def on_auto():
            self.world.wind_auto = self.wind_auto_var.get()

        tk.Checkbutton(p, text="Avtomatik shamol: yo'nalish o'zi o'zgaradi (slayder — kuch)",
                       variable=self.wind_auto_var, command=on_auto, bg=bg, fg=fg,
                       selectcolor="#1d4e89", activebackground=bg, activeforeground="white",
                       font=("Segoe UI", 9), wraplength=int(290 * S), justify="left"
                       ).pack(anchor="w", padx=20, pady=4)

        def preset(base, gust):
            sign = -1 if self.wind_sc.get() < 0 else 1
            self.wind_auto_var.set(False)
            self.world.wind_auto = False
            self.wind_sc.set(sign * base)
            self.gust_sc.set(gust)

        tk.Label(p, text="Tayyor sozlamalar:", bg=bg, fg=fg,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20, pady=(6, 2))
        for r_ in ((("Shamolsiz", 0, 0), ("Yengil", 22, 25)),
                   (("Kuchli", 60, 45), ("Bo'ron", 95, 70))):
            row = tk.Frame(p, bg=bg)
            row.pack(pady=2)
            for text, base, gust in r_:
                tk.Button(row, text=text, width=13, command=lambda b=base, g=gust: preset(b, g),
                          bg="#2a6fb0", fg="white", relief="flat").pack(side="left", padx=4)
        return p

    def show_wind_panel(self):
        p = self.wind_panel
        if p is None:
            return
        try:
            p.deiconify()
            p.lift()
        except Exception:
            pass

    def update_wind_panel(self):
        """Shamol ko'rsatkichi (o'q va matn). Panel yashirin bo'lsa yoki o'zgarmasa ish qilmaydi."""
        p = self.wind_panel
        if p is None:
            return
        try:
            if p.state() != "normal":
                return
        except Exception:
            return
        wn = round(self.world.wind_n, 2)
        if wn == self.wind_last:
            return
        self.wind_last = wn
        S = self.S
        cv = self.wind_cv
        w_, h_ = int(290 * S), int(64 * S)
        cv.delete("all")
        cv.create_line(14, h_ / 2, w_ - 14, h_ / 2, fill="#1d4e89", dash=(3, 3))
        pts, head = wind_arrow(wn, w_, h_)
        cv.create_line(*pts, fill="#e8f2ff", width=max(2, int(3 * S)), capstyle="round")
        if head:
            cv.create_polygon(*head, fill="#e8f2ff", outline="")
        self.wind_txt.config(text=wind_label(wn))

    def quit(self):
        if getattr(self, "timer_ok", False):
            timer_end(1)
            self.timer_ok = False
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------- Asosiy sikl ----------
    def covered(self, x, y):
        for (k, a, b, c, d, ok) in self.last_wins:
            if a <= x < c and b <= y < d:
                return True
        return False

    def refresh_surfaces(self):
        wins = self.scanner.scan(self.W, self.H, self.world.ground)
        self.last_wins = wins
        if not self.win_snow.get():
            wins = [(k, a, b, c, d, False) for (k, a, b, c, d, ok) in wins]
        if self.refresh_n % 2 == 0:
            self.icons = (self.icon_reader.query(self.covered, self.mouse)
                          if self.icon_snow.get() else [])
        self.refresh_n += 1
        self.world.set_surfaces(wins, self.icons)

    def poll_work_area(self):
        """Taskbar siljisa, yashirinsa yoki o'lchami o'zgarsa yer va devorlar moslashadi."""
        wa = work_area()
        if wa:
            self.world.set_bounds(wa[0], wa[2], wa[3])

    def show_overlay(self, visible):
        try:
            u, _ = setup_api()
            u.ShowWindow(self.hwnd, 4 if visible else 0)         # SHOWNOACTIVATE | HIDE
            if visible:
                u.SetWindowPos(self.hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)
        except Exception:
            pass

    def check_fullscreen(self):
        """To'liq ekranli ilova (o'yin, video) ochiq bo'lsa, qor to'xtaydi va yashiriladi."""
        fs = False
        try:
            u, _ = setup_api()
            fg = u.GetForegroundWindow()
            if fg and int(fg) != int(self.hwnd or 0):
                cls = ctypes.create_unicode_buffer(80)
                u.GetClassNameW(fg, cls, 80)
                if cls.value not in SKIP_CLASSES and not u.IsZoomed(fg) and not u.IsIconic(fg):
                    r = RECT()
                    u.GetWindowRect(fg, ctypes.byref(r))
                    fs = covers_screen((r.l, r.t, r.r, r.b), self.W, self.H)
        except Exception:
            fs = False
        self.fs_votes = self.fs_votes + 1 if fs else 0
        want = (self.fs_votes >= 2) if not self.paused else (self.fs_votes > 0)
        if want != self.paused:
            self.paused = want
            self.show_overlay(not want)

    def load_ms(self):
        """Yuklama: kadr davri maqsaddan ancha uzun bo'lsa (Tk chizishi ham sekin) 'sekin' deb olinadi."""
        tgt = 40.0 if self.low_perf else 33.0
        if self.avg_period > tgt * 1.22:
            return max(self.avg_ms, 27.0)
        return self.avg_ms

    def govern(self):
        """Kompyuter sekin ishlasa, avval qor zarralari kamayadi, keyin yengil rejimga o'tadi
        (chiroqlar harakatsiz, kamroq bo'lak, kam kadr). Bo'shagach hammasi qaytadi.
        Kamaytirish haqiqiy ko'rinayotgan zarralar sonidan boshlanadi, qaytarish esa
        avval qotgan darajadan oshmaydi (tebranish bo'lmasin)."""
        load = self.load_ms()
        cur = min(self.flake_cap, self.user_flakes)
        if load > 26.0:
            cap = next_flake_cap(cur, load, lo=60)
            if cap < cur:
                self.cap_ceiling = max(60, int(cur * 0.97))
        else:
            self.ceil_t += 1
            if self.ceil_t >= 5:                       # ~10 soniyada chegara asta ko'tariladi
                self.ceil_t = 0
                self.cap_ceiling = min(600, int(self.cap_ceiling * 1.15) + 1)
            cap = next_flake_cap(self.flake_cap, load, lo=60, hi=self.cap_ceiling)
        if cap != self.flake_cap:
            self.flake_cap = cap
            self.world.n_flakes = min(self.user_flakes, cap)
        if load > 26.0 and self.flake_cap <= 70:
            self.slow_n += 1
        else:
            self.slow_n = 0
        if not self.low_perf and self.slow_n >= 2:
            self.low_perf = True
            self.world.set_low(True)
        elif self.low_perf and self.avg_ms < 12 and self.avg_period < 44:
            self.low_perf = False
            self.world.set_low(False)

    def run_frame(self):
        try:
            mx, my = cursor_pos()
            down = button_down(0x01)
            rdown = button_down(0x02)
        except Exception:
            mx, my, down, rdown = -1, -1, False, False
        mode = self.mode_var.get()
        allow = interaction_allowed(mode, button_down(0x11) if mode == "ctrl" else False)
        self.mouse = (mx, my, down)
        w = self.world
        p0 = time.perf_counter()
        if self.icon_snow.get():
            self.icon_drag.update(mx, my, down, self.icons, self.covered, w.fling_icon)
        if w.t % 15 == 0:
            self.poll_work_area()
        if w.t % 8 == 0:
            self.update_wind_panel()
        every = 2 if any(s.moving for s in w.surfaces.values()) else (8 if self.low_perf else 4)
        if w.t % every == 0:
            self.refresh_surfaces()
        p1 = time.perf_counter()
        if allow or w.held is not None:
            w.step(mx, my, down, rdown)
        else:
            w.step(mx, my, False, False)    # o'yin o'chiq: qor sichqonchaga javob bermaydi
        want = (w.held is not None) or (allow and w.hit_test(mx, my) is not None)
        if want == self.click_through:
            self.set_click_through(not want)
        p2 = time.perf_counter()
        self.draw()
        p3 = time.perf_counter()
        self.phase = ((p1 - p0) * 1000.0, (p2 - p1) * 1000.0, (p3 - p2) * 1000.0)

    def tick(self):
        t0 = time.perf_counter()
        delay = 33
        target = 0.040 if self.low_perf else 0.033
        try:
            self.tick_n += 1
            if self.tick_n == 1:
                self.deadline = t0
            self.last_per = 0.0
            if self.last_t0 and self.ran_prev:
                per = (t0 - self.last_t0) * 1000.0
                if per < 400.0:
                    self.last_per = per
                    self.avg_period = 0.9 * self.avg_period + 0.1 * per
            self.last_t0 = t0
            if self.tick_n == 1 or self.tick_n % (2 if self.paused else 10) == 0:
                self.check_fullscreen()
            if self.paused:
                self.ran_prev = False
                self.deadline = time.perf_counter() + 0.25
                delay = 250
            else:
                self.run_frame()
                self.ran_prev = True
                el = (time.perf_counter() - t0) * 1000.0
                self.avg_ms = 0.9 * self.avg_ms + 0.1 * el
                if self.tick_n % 60 == 0:
                    self.govern()
                if self.tick_n > 60 and (el > 60.0 or self.last_per > 110.0) and self.slow_logs < 12:
                    self.slow_logs += 1
                    a, b, c_ = self.phase
                    _write("qor_log.txt",
                           "Sekin kadr: davr %.0f ms, hisob %.0f ms (yuzalar+sichqoncha %.0f, "
                           "fizika %.0f, chizish %.0f); zarralar=%d, past rejim=%s"
                           % (self.last_per, el, a, b, c_, self.world.n_flakes, self.low_perf))
                self.deadline, delay = pace(self.deadline, time.perf_counter(), target)
        except Exception:
            log_error()
        finally:
            try:
                self.root.after(delay, self.tick)
            except Exception:
                pass

    # ---------- Chizish ----------
    def draw_sphere(self, x, y, r, tag):
        """Yumshoq soyalangan qor shari: yorug'lik chap-yuqoridan, kontur yo'q."""
        c = self.canvas
        for k, off, col in ((1.0, 0.0, "#c4d6ee"), (0.97, 0.03, "#d3e2f3"),
                            (0.86, 0.11, "#e0ecf8"), (0.68, 0.24, "#edf5fc"),
                            (0.46, 0.38, "#f8fbff")):
            cx_, cy_ = x - 0.6 * off * r, y - 0.8 * off * r
            kr = k * r
            c.create_oval(cx_ - kr, cy_ - kr, cx_ + kr, cy_ + kr, fill=col,
                          outline="", tags=tag)

    def draw(self):
        c, w = self.canvas, self.world
        for it in w.dead:
            c.delete(it)
        w.dead.clear()

        t = w.t
        still = self.low_perf               # yengil rejimda zarralar aylanmaydi
        made = 0                            # bir kadrda yangi elementlar soni cheklanadi (boshlanishda qotmasin)
        for f in w.flakes:
            if f.item is None:
                if made >= 60:
                    continue
                made += 1
            elif f.px is not None and ((t + f.k) & 1) and (f.shape is None or still):
                continue                    # mayda zarralar: ikki kadrda bir marta (siljish yig'indisi bilan)
            if f.shape is None:                              # eng mayda yumshoq nuqta
                r_ = f.dr
                if f.item is None:
                    f.item = c.create_oval(f.x - r_, f.y - r_, f.x + r_, f.y + r_,
                                           fill=f.fill, outline="")
                elif f.px is None:
                    c.coords(f.item, f.x - r_, f.y - r_, f.x + r_, f.y + r_)
                else:
                    c.move(f.item, f.x - f.px, f.y - f.py)
            elif f.item is None or f.px is None or (not still and (t + f.k) % f.ri == 0):
                pts = rot(f.shape, f.ang, f.x, f.y, f.dr)    # aylanish: har 6-kadrda
                if f.item is None:
                    f.item = c.create_polygon(*pts, fill=f.fill, outline=f.outline)
                else:
                    c.coords(f.item, *pts)
            else:
                c.move(f.item, f.x - f.px, f.y - f.py)       # qolgan kadrlarda faqat siljish
            f.px, f.py = f.x, f.y

        made = 0
        for ch in w.chunks:
            if ch.item is None:
                if made >= 90:
                    continue
                made += 1
            r = ch.r
            if ch.soft:
                if ch.item is None or ch.px is None or ch.age % 3 == 0:
                    pts = rot(ch.shape, ch.ang, ch.x, ch.y, r)
                    if ch.item is None:
                        ch.item = c.create_polygon(*pts, fill=FLAKE_FILL[ch.tier], outline="")
                    else:
                        c.coords(ch.item, *pts)
                else:
                    c.move(ch.item, ch.x - ch.px, ch.y - ch.py)
                ch.px, ch.py = ch.x, ch.y
            elif ch.dust:
                if ch.item is None:
                    ch.item = c.create_oval(0, 0, 0, 0, fill="#f4f9ff", outline="")
                c.coords(ch.item, ch.x - r, ch.y - r, ch.x + r, ch.y + r)
            else:
                pts = rot(ch.shape, 0.0, ch.x, ch.y, r)
                if ch.item is None:
                    ch.item = c.create_polygon(*pts, fill=WHITE, outline="")
                else:
                    c.coords(ch.item, *pts)

        gp = w.ground_pile
        redo = False                        # yangi element yaratildimi: shunda qatlamlar tartibi tiklanadi
        for p in [gp] + list(w.surfaces.values()):
            if not p.dirty:
                continue
            if not p.urgent and (t + p.phase) % (3 if p is gp else 6):
                continue                    # qor sekin o'sadi: har kadrda qayta chizish shart emas
            runs = p.runs()
            while len(p.items) < len(runs):
                redo = True
                p.items.append([c.create_polygon(0, 0, 0, 0, 0, 0, fill=PILE_BODY,
                                                 outline="", tags="pile"),
                                c.create_polygon(0, 0, 0, 0, 0, 0, fill=PILE_TOP,
                                                 outline="", tags="pile"), True])
            for k, pair in enumerate(p.items):
                if k < len(runs):
                    c.coords(pair[0], *runs[k][0])
                    c.coords(pair[1], *runs[k][1])
                    if not pair[2]:
                        c.itemconfigure(pair[0], state="normal")
                        c.itemconfigure(pair[1], state="normal")
                        pair[2] = True
                elif pair[2]:
                    c.itemconfigure(pair[0], state="hidden")
                    c.itemconfigure(pair[1], state="hidden")
                    pair[2] = False
            p.dirty = False
            p.urgent = False

        bsig = tuple((b.x, b.y, b.r) for b in w.balls)      # tinch turgan sharchalar qayta chizilmaydi
        if bsig != self.bsig:
            self.bsig = bsig
            c.delete("ball")
            for b in w.balls:
                self.draw_sphere(b.x, b.y, b.r, "ball")
            redo = True

        psig = tuple((p.x, p.y, p.ang, p.k) for p in w.parts)
        if psig != self.psig:
            self.psig = psig
            c.delete("part")
            for p in w.parts:
                self.draw_part(p)
            redo = True

        sig = (len(w.snowmen), sum(len(s.gone) for s in w.snowmen))
        if sig != self.sm_sig or any(s.age < 44 for s in w.snowmen):
            c.delete("snowman")
            for s in w.snowmen:
                self.draw_snowman(s)
            self.sm_sig = sig
            redo = True

        if self.lights_on.get():
            if not self.lights_built:
                self.build_lights()
            self.update_garland()
            if w.t % 3 == 0:
                self.update_lights()
        elif self.lights_built:
            c.delete("lights")
            self.bulbs = []
            self.spans = []
            self.twinkle = {}
            self.lights_built = False

        if redo:                    # har kadrda emas: aks holda Tk uyumlar maydonini har safar qayta chizadi
            c.tag_lower("ball")
            c.tag_lower("part")
            c.tag_lower("snowman")
            c.tag_lower("pile")

    def draw_part(self, p):
        c, S = self.canvas, self.S
        k, x, y, a = p.k, p.x, p.y, p.ang
        s, w = p.s, p.w
        if p.kind == "hat":
            c.create_polygon(rot([(-0.88 * s, 0.45 * s), (0.88 * s, 0.45 * s),
                                  (0.75 * s, -0.85 * s)], a, x, y, k),
                             fill="#d62828", outline="", tags="part")
            c.create_polygon(rot([(-0.95 * s, 0.28 * s), (0.95 * s, 0.28 * s),
                                  (0.95 * s, 0.62 * s), (-0.95 * s, 0.62 * s)],
                                 a, x, y, k), fill=WHITE, outline="", tags="part")
            px, py = rot([(0.75 * s, -0.85 * s)], a, x, y, k)
            rr = 0.22 * s * k
            c.create_oval(px - rr, py - rr, px + rr, py + rr, fill=WHITE,
                          outline="", tags="part")
        elif p.kind == "nose":
            c.create_polygon(rot([(-0.5 * s, -0.09 * s), (-0.5 * s, 0.09 * s),
                                  (0.5 * s, 0)], a, x, y, k),
                             fill="#ff8a1f", outline="", tags="part")
        elif p.kind == "stick":
            c.create_line(*rot([(-0.5 * s, 0), (0.5 * s, 0)], a, x, y, k), width=w * k,
                          fill="#6b4423", capstyle="round", tags="part")
            c.create_line(*rot([(0.1 * s, 0), (0.35 * s, -0.3 * s)], a, x, y, k),
                          width=max(1.5 * S, w * 0.6 * k), fill="#6b4423",
                          capstyle="round", tags="part")
        elif p.kind == "scarf":
            c.create_polygon(rot([(-0.5 * s, -w / 2), (0.5 * s, -w / 2),
                                  (0.5 * s, w / 2), (-0.5 * s, w / 2)], a, x, y, k),
                             fill="#2e9e4f", outline="", tags="part")
        else:
            rr = max(1.0, w * k)
            c.create_oval(x - rr, y - rr, x + rr, y + rr, fill="#222222",
                          outline="", tags="part")

    def draw_snowman(self, sm):
        c, S = self.canvas, self.S
        age = sm.age
        gone = sm.gone
        sc = 1.0 + (0.18 * math.sin(age / 16.0 * math.pi) if age < 16 else 0.0)
        r0, r1, r2 = [r * sc for r in sm.radii]
        x = sm.x
        y0 = self.world.ground - r0
        y1 = y0 - (r0 + r1) * 0.82
        y2 = y1 - (r1 + r2) * 0.82
        for k, (yy, rr) in enumerate(((y0, r0), (y1, r1), (y2, r2))):
            if k not in gone:
                self.draw_sphere(x, yy, rr, "snowman")

        def dot(px, py, rad, color):
            c.create_oval(px - rad, py - rad, px + rad, py + rad, fill=color,
                          outline="", tags="snowman")

        head = 2 not in gone
        mid = 1 not in gone
        if head and age >= 6:
            er = max(1.6 * S, 0.09 * r2)
            dot(x - 0.33 * r2, y2 - 0.22 * r2, er, "#222222")
            dot(x + 0.33 * r2, y2 - 0.22 * r2, er, "#222222")
        if head and age >= 12:
            c.create_polygon(x, y2 - 0.05 * r2, x, y2 + 0.17 * r2,
                             x + 0.95 * r2, y2 + 0.09 * r2, fill="#ff8a1f",
                             outline="", tags="snowman")
        if head and age >= 16:
            for k in range(-2, 3):
                dot(x + k * 0.15 * r2, y2 + (0.40 + 0.06 * (2 - abs(k))) * r2,
                    max(1.3 * S, 0.045 * r2), "#333333")
        if mid and age >= 20:
            for t in (-0.4, 0.0, 0.4):
                dot(x, y1 + t * r1, max(2 * S, 0.08 * r1), "#333333")
        if head and age >= 26:
            ny = y2 + r2 * 0.82
            wd = max(4 * S, 0.28 * r2)
            c.create_line(x - 0.8 * r2, ny, x + 0.8 * r2, ny, width=wd, fill="#2e9e4f",
                          capstyle="round", tags="snowman")
            c.create_rectangle(x + 0.25 * r2, ny, x + 0.25 * r2 + wd, ny + 0.9 * r1,
                               fill="#2e9e4f", outline="", tags="snowman")
        if mid and age >= 32:
            aw = max(3 * S, 0.1 * r1)
            for sign in (-1, 1):
                bx, by = x + sign * r1 * 0.88, y1 - r1 * 0.15
                ex, ey = bx + sign * r1 * 1.0, by - r1 * 0.8
                c.create_line(bx, by, ex, ey, width=aw, fill="#6b4423",
                              capstyle="round", tags="snowman")
                mx_, my_ = bx + (ex - bx) * 0.65, by + (ey - by) * 0.65
                for dy_ in (-0.35, 0.25):
                    c.create_line(mx_, my_, ex + sign * 0.1 * r1, ey + dy_ * r1,
                                  width=max(2 * S, aw * 0.6), fill="#6b4423",
                                  capstyle="round", tags="snowman")
        if head and age >= 40:
            hb = y2 - r2 * 0.62
            tipx, tipy = x + 0.75 * r2, hb - 1.3 * r2
            c.create_polygon(x - 0.88 * r2, hb, x + 0.88 * r2, hb, tipx, tipy,
                             fill="#d62828", outline="", tags="snowman")
            c.create_rectangle(x - 0.95 * r2, hb - 0.2 * r2, x + 0.95 * r2,
                               hb + 0.12 * r2, fill=WHITE, outline="", tags="snowman")
            c.create_oval(tipx - 0.22 * r2, tipy - 0.22 * r2, tipx + 0.22 * r2,
                          tipy + 0.22 * r2, fill=WHITE, outline="", tags="snowman")

    # ---------- Yangi yil chiroqlari: iliq oq lampochkalar, yashil soket, o'ralgan sim ----------
    # Faqat lampochkaning o'zi yonadi (atrofida nur doirasi yo'q). Yonib bo'lgach
    # chiroqlar harakatsiz turadi: kuchsiz kompyuterda ham hech narsa sarflamaydi.
    def build_lights(self):
        c, S, W = self.canvas, self.S, self.W
        c.delete("lights")
        self.bulbs = []
        self.spans = []
        self.twinkle = {}
        self.lights_t0 = self.world.t
        wd = max(2, int(2 * S))
        k = 0
        for rope, specs in make_rig(W, S):
            P, cum = rope.polyline()
            pa, pb = strand_points(P, cum, S)
            sv = SpanView()
            sv.rope = rope
            sv.sb = c.create_line(*pb, fill="#3d1c1c", width=wd, tags="lights")
            sv.sa = c.create_line(*pa, fill="#7f2a2a", width=wd, tags="lights")
            sv.x0, sv.x1 = min(rope.x), max(rope.x)
            sv.bulbs = []
            for (f, th0, ph) in specs:
                x, y, tx, ty = rope.at(P, cum, f)
                sock, rings, rim, mid, core, hot, fil, cen = bulb_geom(x, y, th0, S)
                bl = Bulb()
                bl.sock = c.create_polygon(*sock, fill="#1f5a2c", outline="#10381a", tags="lights")
                bl.r1 = c.create_line(*rings[0], fill="#2f7a40", width=1, tags="lights")
                bl.r2 = c.create_line(*rings[1], fill="#2f7a40", width=1, tags="lights")
                bl.rim = c.create_polygon(*rim, fill="#4a2f0e", outline="", tags="lights")
                bl.mid = c.create_polygon(*mid, fill="#6b4a18", outline="", tags="lights")
                bl.core = c.create_polygon(*core, fill="#8c6a2a", outline="", tags="lights")
                bl.hot = c.create_polygon(*hot, fill="#a58a4a", outline="", tags="lights")
                bl.fil = c.create_line(*fil, fill="#8c6a2a", width=1, tags="lights")
                bl.f, bl.th0, bl.a, bl.av = f, th0, 0.0, 0.0
                bl.ax, bl.vxp = x, 0.0
                bl.cx, bl.cy = cen
                bl.k = k
                bl.lvl = -1
                k += 1
                sv.bulbs.append(bl)
                self.bulbs.append(bl)
            self.spans.append(sv)
        self.lights_built = True

    def _place_bulb(self, bl, x, y, th):
        c = self.canvas
        sock, rings, rim, mid, core, hot, fil, cen = bulb_geom(x, y, th, self.S)
        c.coords(bl.sock, *sock)
        c.coords(bl.r1, *rings[0])
        c.coords(bl.r2, *rings[1])
        c.coords(bl.rim, *rim)
        c.coords(bl.mid, *mid)
        c.coords(bl.core, *core)
        c.coords(bl.hot, *hot)
        c.coords(bl.fil, *fil)
        bl.cx, bl.cy = cen

    def update_garland(self):
        """Chiroq simi fizikasi: kursor, shamol va otilgan sharcha simni turtadi, lampochkalar
        mayatnikdek tebranadi. Hammasi tinchlansa, hech narsa hisoblanmaydi va chizilmaydi."""
        if not self.spans or self.low_perf:
            return
        w, S, c = self.world, self.S, self.canvas
        sway = self.sway_var.get()
        mx, my, _ = self.mouse
        cvx, cvy = w.cvx, w.cvy                       # kursor tezligi, px/kadr
        top = 110.0 * S
        poke_c = (sway and 0 <= my < top and mx >= 0
                  and math.hypot(cvx, cvy) > 2.0 * S)
        wind_ps = w.wind_n * 30.0 if sway else 0.0
        gusty = sway and abs(w.wind_n) > 0.5          # kuchli shamol: sim tinmay tebranadi
        t = w.t / 30.0
        for sp in self.spans:
            rope = sp.rope
            if poke_c and sp.x0 - 60 * S < mx < sp.x1 + 60 * S:
                rope.poke(mx, my, 44 * S, cvx * 30.0, cvy * 30.0, 0.32)
                for bl in sp.bulbs:                   # kursor lampochkaning o'ziga tegsa
                    if abs(mx - bl.cx) < 14 * S and abs(my - bl.cy) < 16 * S:
                        bl.av += max(-0.08, min(0.08, cvx * 0.004))
                        rope.awake = True
                        rope.calm = 0
            if sway:
                for b in w.balls:                     # otilgan sharcha ham turtadi
                    if (b.y < top and abs(b.vx) + abs(b.vy) > 4 * S
                            and sp.x0 - 40 * S < b.x < sp.x1 + 40 * S):
                        rope.poke(b.x, b.y, b.r + 18 * S, b.vx * 30.0, b.vy * 30.0, 0.5)
            if gusty:
                rope.awake = True
                rope.calm = 0
            if not rope.awake:
                continue
            rope.step(wind_ps, t)
            P, cum = rope.polyline()
            pa, pb = strand_points(P, cum, S)
            c.coords(sp.sa, *pa)
            c.coords(sp.sb, *pb)
            quiet = rope.energy() < 0.15 * S * S
            for bl in sp.bulbs:
                x, y, tx, ty = rope.at(P, cum, bl.f)
                vx = x - bl.ax                        # ulangan nuqta tezligi va tezlanishi
                ax = vx - bl.vxp
                bl.vxp, bl.ax = vx, x
                th = bl.th0 + bl.a
                # mayatnik: tiklovchi kuch, so'nish va ulangan nuqta tezlanishidan turtki
                acc = (-0.038 * bl.a - 0.09 * bl.av - 0.3 * (ax / (13.0 * S)) * math.cos(th)
                       + (0.005 * w.wind_n if sway else 0.0))    # shamol lampochkani biroz og'diradi
                bl.av = max(-0.25, min(0.25, bl.av + acc))
                bl.a = max(-0.8, min(0.8, bl.a + bl.av))
                self._place_bulb(bl, x, y, bl.th0 + bl.a)
                if abs(bl.av) > 0.006 or abs(bl.a) > 0.02:
                    quiet = False
            rope.calm = rope.calm + 1 if quiet else 0
            if rope.calm >= 12:
                rope.awake = False

    def _paint_bulb(self, bl, b):
        c = self.canvas
        c.itemconfigure(bl.rim, fill=blend("#4a2f0e", "#ffb733", b))
        c.itemconfigure(bl.mid, fill=blend("#6b4a18", "#ffd35c", b))
        c.itemconfigure(bl.core, fill=blend("#8c6a2a", "#ffe99a", b))
        c.itemconfigure(bl.hot, fill=blend("#a58a4a", "#fffbe0", b))
        c.itemconfigure(bl.fil, fill=blend("#8c6a2a", "#fff3c0", b))

    def update_lights(self):
        t, tw = self.world.t, self.twinkle
        n = len(self.bulbs)
        if not n:
            return
        t0 = self.lights_t0
        if t - t0 < n * 2 + 24:                     # boshida birin-ketin yonadi
            for bl in self.bulbs:
                b = max(0.0, min(1.0, (t - t0 - bl.k * 2) / 18.0)) ** 1.5
                lvl = int(b * 14)
                if lvl != bl.lvl:
                    bl.lvl = lvl
                    self._paint_bulb(bl, b)
            return
        # yonib bo'ldi: harakatsiz. Ba'zan bitta lampa pirpirab o'tadi (yengil rejimda yo'q).
        if not self.low_perf and random.random() < 0.04:
            k = random.randrange(n)
            if k not in tw:
                tw[k] = t
        for k in list(tw):
            u = (t - tw[k]) / 24.0
            bl = self.bulbs[k]
            if u >= 1:
                del tw[k]
                b = 1.0
            else:
                b = 1 - 0.75 * math.sin(math.pi * u)
            lvl = int(b * 14)
            if lvl != bl.lvl:
                bl.lvl = lvl
                self._paint_bulb(bl, b)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
