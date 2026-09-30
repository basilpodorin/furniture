"""Чертёж наконечника (лист 1) и карта наладки ЧПУ (лист 2), формат А3.

Листы рисуются matplotlib в масштабе 1 мм бумаги = 1 единица осей.
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Circle, Polygon  # noqa: E402

from geom import (Params, Profile, dome_x, end_heightmap, end_silhouette, end_x, fixture_layout,  # noqa: E402
                  index_layout, radius_table, reed_d, reed_v)

PT = 72 / 25.4
NSHEETS = 4
THICK = 0.5 * PT
THIN = 0.25 * PT
CENTER_LS = (0, (14, 3, 2, 3))
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["hatch.linewidth"] = 0.3
plt.rcParams["pdf.fonttype"] = 42


def num(v: float) -> str:
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


class Sheet:
    W, H = 420.0, 297.0

    def __init__(self):
        self.fig = plt.figure(figsize=(self.W / 25.4, self.H / 25.4))
        ax = self.fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, self.W)
        ax.set_ylim(0, self.H)
        ax.set_aspect("equal")
        ax.axis("off")
        self.ax = ax

    # --- примитивы ---
    def poly(self, pts, lw=THICK, ls="-", color="k", closed=False, z=3):
        pts = np.asarray(pts)
        if closed:
            pts = np.vstack([pts, pts[:1]])
        self.ax.plot(pts[:, 0], pts[:, 1], lw=lw, ls=ls, color=color, zorder=z,
                     solid_capstyle="round", solid_joinstyle="round")

    def line(self, p0, p1, **kw):
        self.poly([p0, p1], **kw)

    def center(self, p0, p1, color="k"):
        self.line(p0, p1, lw=THIN, ls=CENTER_LS, color=color)

    def hatch(self, pts, hatch="////", z=1, lw=THICK):
        self.ax.add_patch(Polygon(pts, closed=True, fill=False, hatch=hatch, lw=0, zorder=z))
        self.poly(pts, closed=True, lw=lw)

    def text(self, x, y, s, h=3.0, ha="center", va="center", rot=0, weight="normal", color="k", z=5,
             bg=False):
        t = self.ax.text(x, y, s, fontsize=h / 0.72 * PT, ha=ha, va=va, rotation=rot, weight=weight,
                         color=color, zorder=z, rotation_mode="anchor")
        if bg:
            t.set_bbox(dict(facecolor="white", edgecolor="none", pad=0.6))
        return t

    def arrow(self, tip, direction, L=2.8, w=0.95, color="k"):
        d = np.asarray(direction, float)
        d /= np.linalg.norm(d)
        n = np.array([-d[1], d[0]])
        tip = np.asarray(tip, float)
        b = tip - L * d
        self.ax.add_patch(Polygon([tip, b + n * w / 2, b - n * w / 2], closed=True, color=color,
                                  lw=0, zorder=4))

    # --- размеры ---
    def dim_h(self, p1, p2, y, text, above=True, h=3.0, ext=True):
        x1, x2 = sorted([p1[0], p2[0]])
        if ext:
            for p in (p1, p2):
                s = 1 if y > p[1] else -1
                self.line((p[0], p[1] + s * 1.0), (p[0], y + s * 2.0), lw=THIN)
        inside = x2 - x1 > 9
        if inside:
            self.line((x1, y), (x2, y), lw=THIN)
            self.arrow((x1, y), (-1, 0))
            self.arrow((x2, y), (1, 0))
            tx = (x1 + x2) / 2
        else:
            self.line((x1 - 7, y), (x2 + 7, y), lw=THIN)
            self.arrow((x1, y), (1, 0))
            self.arrow((x2, y), (-1, 0))
            tx = x2 + 3 + 0.9 * len(text)
        self.text(tx, y + (0.8 if above else -0.8), text, h=h, va="bottom" if above else "top", bg=True)

    def dim_v(self, p1, p2, x, text, h=3.0, ext=True, left=True):
        y1, y2 = sorted([p1[1], p2[1]])
        if ext:
            for p in (p1, p2):
                s = 1 if x > p[0] else -1
                self.line((p[0] + s * 1.0, p[1]), (x + s * 2.0, p[1]), lw=THIN)
        inside = y2 - y1 > 9
        if inside:
            self.line((x, y1), (x, y2), lw=THIN)
            self.arrow((x, y1), (0, -1))
            self.arrow((x, y2), (0, 1))
            ty = (y1 + y2) / 2
        else:
            self.line((x, y1 - 7), (x, y2 + 7), lw=THIN)
            self.arrow((x, y1), (0, 1))
            self.arrow((x, y2), (0, -1))
            ty = y2 + 3 + 0.9 * len(text)
        self.text(x - 0.8 if left else x + 0.8, ty, text, h=h, rot=90, va="bottom" if left else "top", bg=True)

    def leader(self, tip, knee, text, h=3.0, arrow=True, right=True):
        """Выноска: стрелка в точке tip, полка с текстом после knee."""
        tip, knee = np.asarray(tip, float), np.asarray(knee, float)
        self.line(tip, knee, lw=THIN)
        if arrow:
            self.arrow(tip, tip - knee)
        wtxt = 0.62 * h * len(text) + 1.5
        end = knee + np.array([wtxt if right else -wtxt, 0])
        self.line(knee, end, lw=THIN)
        self.text((knee[0] + end[0]) / 2, knee[1] + 0.7, text, h=h, va="bottom")

    def radius(self, c, r, ang, text, L=9.0, toward_center=False, right=None, h=3.0):
        """Радиус дуги: стрелка на дуге, выноска наружу (или к центру — для вогнутых)."""
        u = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
        a = np.asarray(c, float) + r * u
        d = -u if toward_center else u
        knee = a + L * d
        if right is None:
            right = d[0] >= 0
        self.line(a, knee, lw=THIN)
        self.arrow(a, -d)
        self.leader(knee, knee, text, h=h, arrow=False, right=right)

    def caption(self, x, y, s, h=3.5):
        self.text(x, y, s, h=h, weight="bold")

    def frame(self, title, subtitle, sheet_no, sheets, P: Params, scale):
        W, H = self.W, self.H
        self.poly([(20, 5), (W - 5, 5), (W - 5, H - 5), (20, H - 5)], closed=True, lw=THICK)
        # штамп в стиле листа 1 кровати
        y0, y1, y2 = 5, 17, 41
        self.line((20, y2), (W - 5, y2))
        cols = [20, 150, 222, 268, 298, 326, 352, 384, W - 5]
        for x in cols[1:-1]:
            self.line((x, y0), (x, y2))
        self.line((20, y1), (cols[1], y1))
        self.text(85, 32, title[0], h=4.2)
        self.text(85, 25, title[1], h=4.2)
        self.text(24, 11, subtitle, h=2.8, ha="left")
        heads = ["МАТЕРИАЛ:", "ПОКРЫТИЕ:", "МАСШТАБ:", "ФОРМАТ:", "ЛИСТ:", "ДАТА:", "ДИЗАЙНЕР:"]
        vals = ["Массив ясеня\nволокна вдоль оси", "Масло / лак\nматовый", scale, "А3",
                f"{sheet_no}/{sheets}", "", ""]
        for i, (hd, v) in enumerate(zip(heads, vals)):
            xa, xb = cols[i + 1], cols[i + 2]
            self.text(xa + 2 if i < 2 else (xa + xb) / 2, 35, hd, h=2.4, ha="left" if i < 2 else "center")
            self.text(xa + 2 if i < 2 else (xa + xb) / 2, 24, v, h=2.4, ha="left" if i < 2 else "center",
                      va="center")
        self.line((cols[-2] + 3, 14), (cols[-1] - 3, 14), lw=THIN)


# ----------------------------------------------------------------------------
# Лист 1 — деталь
# ----------------------------------------------------------------------------
def groove_lines(P: Params, prof: Profile, n=300):
    """Линии дна каннелюр на виде сбоку: (x, z) для видимых канавок."""
    if not P.reeds:
        return []
    x = np.linspace(*prof.reed_x, n)
    R = radius_table(prof, x)
    d = reed_d(P, prof, x, R)
    m = d > 0.12 * d.max()
    out = []
    for k in range(P.reeds // 2):
        phi = math.pi / P.reeds + k * 2 * math.pi / P.reeds   # канавки на передней половине
        z = (R - d) * math.cos(phi)
        out.append(np.c_[x[m], z[m]])
    return out


def outline(P: Params, prof: Profile, rosette: bool, xmin=None):
    """Верхняя половина силуэта (x, z) на виде сбоку; с розеткой — реальный силуэт торца."""
    pts = prof.sample(tol=0.002)
    if xmin is not None:
        pts = pts[pts[:, 0] >= xmin]
    if not (rosette and P.rosette):
        return pts
    R = P.rosette_r + 0.6
    m = prof.marks
    keep = ~((pts[:, 0] > m["xe"]) & (pts[:, 1] < R))
    zs = np.linspace(R, 0, 160)
    xs = end_silhouette(P, prof, zs)
    return np.vstack([pts[keep], np.c_[xs, zs]])


def draw_part_view(sh: Sheet, P: Params, prof: Profile, ox, oy, k, lines=True, lw=THICK, tangent=True,
                   rosette=False, vertical=False, reeds=True, xmin=None):
    """Вид детали сбоку. vertical=True — ось вертикально, торец вверх (кондуктор).
    reeds=False — шейка ещё гладкая; xmin — не рисовать левее (шип спрятан в оправке)."""
    m = prof.marks
    if vertical:
        T = lambda x, z: (ox - k * z, oy + k * x)
    else:
        T = lambda x, z: (ox + k * x, oy + k * z)
    pts = outline(P, prof, rosette, xmin)
    for s_ in (1, -1):
        sh.poly([T(x, s_ * z) for x, z in pts], lw=lw)
    if lines:
        # контурные окружности, видимые линиями
        sh.line(T(0, -m["face_r"]), T(0, m["face_r"]), lw=lw)
        sh.line(T(m["Lc"], -m["face_r"]), T(m["Lc"], m["face_r"]), lw=lw)
        if prof.segs[1].p0[0] == prof.segs[0].p0[0] and xmin is None:   # есть фаска шипа
            xc = -P.tenon_l + P.tenon_chamfer
            sh.line(T(xc, -m["rt"]), T(xc, m["rt"]), lw=lw)
    if tangent:
        for x, r in ((m["e"], m["Rc"]), (m["Lc"] - m["e"], m["Rc"]), (m["xs"], m["Rcap"]),
                     (m["xe"], m["Rcap"])):
            sh.line(T(x, -r), T(x, r), lw=THIN)
        for g in (groove_lines(P, prof) if reeds else []):
            sh.poly([T(x, z) for x, z in g], lw=THIN)
        if rosette and P.rosette:
            R = P.rosette_r
            xr = float(dome_x(prof, R))
            sh.line(T(xr, -R), T(xr, R), lw=THIN)


def sheet_part(P: Params, prof: Profile, L: dict, render_png: Path | None) -> Sheet:
    sh = Sheet()
    m = prof.marks
    sh.frame(("НАКОНЕЧНИК ШТАНГИ ИЗГОЛОВЬЯ", "КРОВАТЬ ИЗ МАССИВА ЯСЕНЯ"),
             "ЛИСТ Н1. НАКОНЕЧНИК — ЧЕРТЁЖ ДЕТАЛИ (2 шт.)", 1, NSHEETS, P, "2:1; 2,5:1; 1:1")
    e, fr, Lc = m["e"], m["face_r"], m["Lc"]

    # ---------------- 1. Вид сбоку, М 2:1 ----------------
    k = 2.0
    ox, oy = 108.0, 203.0
    T = lambda x, z: (ox + k * x, oy + k * z)
    sh.caption(68, 286, "1. ВИД СБОКУ (М 2:1)")
    draw_part_view(sh, P, prof, ox, oy, k, rosette=True)
    if P.rosette:   # вид Б — на торец
        ya = oy + k * 12
        sh.line((ox + k * P.length + 12, ya), (ox + k * P.length + 3, ya), lw=THIN)
        sh.arrow((ox + k * P.length + 2, ya), (-1, 0), L=4, w=1.4)
        sh.text(ox + k * P.length + 8, ya + 4, "Б", h=4)
    sh.center(T(-P.tenon_l - 5, 0), T(P.length + 5, 0))
    sh.center(T(m["xn"], -m["rn"] - 3), T(m["xn"], m["rn"] + 3))

    # длины: снизу
    yb = oy - k * m["Rc"]
    sh.dim_h(T(-P.tenon_l, -m["rt"] + P.tenon_chamfer), T(0, -fr), yb - 10, num(P.tenon_l))
    sh.dim_h(T(0, -fr), T(P.length, 0), yb - 10, num(P.length))
    sh.dim_h(T(-P.tenon_l, 0), T(P.length, 0), yb - 20, num(P.tenon_l + P.length))
    # сверху
    yt = oy + k * m["Rc"]
    sh.dim_h(T(0, fr), T(Lc, fr), yt + 8, num(Lc))
    sh.dim_h(T(m["xs"], m["Rcap"]), T(m["xe"], m["Rcap"]), yt + 8, num(P.cap_band))
    sh.dim_h(T(0, m["Rc"]), T(m["xs"], m["Rcap"]), yt + 17, f"{num(m['xs'])}*")
    # диаметры
    xl = ox + k * (-P.tenon_l) - 10
    sh.dim_v(T(-P.tenon_l + 6, -m["rt"]), T(-P.tenon_l + 6, m["rt"]), xl, f"⌀{num(P.tenon_d)}")
    sh.dim_v(T(0, -fr), T(0, fr), xl - 12, f"⌀{num(2 * fr)}")
    xr = ox + k * P.length + 16
    sh.dim_v(T(m["xe"], -m["Rcap"]), T(m["xe"], m["Rcap"]), xr, f"⌀{num(P.cap_d)}")
    sh.dim_v(T(Lc - e, -m["Rc"]), T(Lc - e, m["Rc"]), xr + 11, f"⌀{num(P.collar_d)}")
    # радиусы
    sh.radius(T(e, fr), k * e, 160, f"R{num(e)}", L=9)
    sh.radius(T(Lc - e, fr), k * e, 20, f"R{num(e)}", L=9)
    sh.radius(T(m["xn"], fr), k * m["Rcv"], 215, f"R{num(m['Rcv'])}", L=8, toward_center=True)
    sh.radius(T(*m["Cr"]), k * m["Rr"], -40, f"R{num(m['Rr'])}", L=8, toward_center=True, right=True)
    sh.radius(T(*m["Cs"]), k * m["Rs"], 118, f"R{num(m['Rs'])}", L=7)
    sh.radius(T(m["xe"], m["ye"]), k * m["Re"], 55, f"R{num(m['Re'])}", L=8)
    if not P.rosette:
        sh.radius(T(m["xd"], 0), k * m["Rd"], -8, f"R{num(m['Rd'])}*", L=8)
    sh.radius(T(-m["f"], m["rt"] + m["f"]), k * m["f"], -60, f"R{num(m['f'])}", L=9, toward_center=True,
              right=False)

    # ---------------- 2. Сечение шейки, М 3:1 ----------------
    ks = 2.5
    cx, cy = 335.0, 212.0
    xa = m["xn"]
    sh.caption(cx, 286, f"2. СЕЧЕНИЕ ШЕЙКИ В УЗКОМ МЕСТЕ (М 2,5:1)")
    sh.text(cx, 280, f"в {num(xa)} мм от опорного торца", h=2.6)
    R0 = float(radius_table(prof, np.array([xa]))[0])
    d = float(reed_d(P, prof, np.array([xa]), np.array([R0]))[0])
    phi = np.linspace(0, 2 * np.pi, 721)
    r = R0 - d * reed_v(P, phi)
    sh.hatch(np.c_[cx + ks * r * np.sin(phi), cy + ks * r * np.cos(phi)], hatch="/////")
    sh.line((cx - ks * R0 - 22, cy), (cx + ks * R0 + 10, cy), lw=THIN * 1.4, ls=CENTER_LS, color="tab:red")
    sh.center((cx, cy - ks * R0 - 6), (cx, cy + ks * R0 + 6))
    sh.text(cx - ks * R0 - 22, cy + 1.5, "плоскость", h=2.4, ha="left", va="bottom", color="tab:red")
    sh.text(cx - ks * R0 - 22, cy - 1.5, "разъёма", h=2.4, ha="left", va="top", color="tab:red")
    sh.dim_h((cx - ks * R0, cy), (cx + ks * R0, cy), cy - ks * R0 - 12, f"⌀{num(2 * R0)} (по гребням)")
    if P.reeds:
        a = math.pi / P.reeds
        rb = R0 - d
        tip = (cx - ks * rb * math.sin(a), cy + ks * rb * math.cos(a))
        sh.leader(tip, (cx - 36, cy + ks * R0 + 16), f"{P.reeds} острых канавок, глубина {num(P.reed_depth)}",
                  right=False, h=2.6)
        for ang in (0, 2 * a):
            p0 = (cx + ks * (R0 + 0.8) * math.sin(ang), cy + ks * (R0 + 0.8) * math.cos(ang))
            p1 = (cx + ks * (R0 + 7) * math.sin(ang), cy + ks * (R0 + 7) * math.cos(ang))
            sh.line(p0, p1, lw=THIN)
        rr = ks * (R0 + 5)
        arc = np.linspace(0, 2 * a, 40)
        sh.poly(np.c_[cx + rr * np.sin(arc), cy + rr * np.cos(arc)], lw=THIN)
        sh.arrow((cx, cy + rr), (-1, 0))
        sh.arrow((cx + rr * math.sin(2 * a), cy + rr * math.cos(2 * a)), (math.cos(2 * a), -math.sin(2 * a)))
        sh.text(cx + (rr + 3.5) * math.sin(a), cy + (rr + 3.5) * math.cos(a), f"{num(360 / P.reeds)}°", h=2.8,
                bg=True)
        sh.text(cx - ks * R0 - 5, cy - ks * R0 - 20,
                "Валики — дуги, канавки острые (как на штанге).\n"
                "Режутся в установке 4, в делительной оправке (лист Н4).",
                h=2.3, ha="left", va="top")

    # ---------------- 3. Узел соединения, М 1:1 ----------------
    jx, jy = 340.0, 88.0
    sh.caption(342, 132, "3. СОЕДИНЕНИЕ СО ШТАНГОЙ (М 1:1)")
    Rr_ = P.rod_d / 2
    hd, hl, ch = P.rod_hole_d / 2, P.rod_hole_depth, P.rod_hole_chamfer
    tipx = -hl - hd / math.tan(math.radians(59))
    xl_ = -58
    rod = [(xl_, Rr_), (0, Rr_), (0, hd + ch), (-ch, hd), (-hl, hd), (tipx, 0), (-hl, -hd), (-ch, -hd),
           (0, -hd - ch), (0, -Rr_), (xl_, -Rr_)]
    J = lambda p: (jx + p[0], jy + p[1])
    zz = np.linspace(-Rr_, Rr_, 60)
    brk = [(xl_ + 1.6 * math.sin(z * 0.35), z) for z in zz[::-1]]
    sh.hatch([J(p) for p in rod + brk[1:-1]], hatch="\\\\\\\\")
    sh.line(J((0, hd + ch)), J((0, -hd - ch)), lw=THIN)
    draw_part_view(sh, P, prof, jx, jy, 1.0, tangent=False, rosette=True)
    sh.center(J((xl_ - 4, 0)), J((P.length + 4, 0)))
    sh.dim_v(J((-hl + 2.5, -hd)), J((-hl + 2.5, hd)), jx - hl + 2.5, f"⌀{num(P.rod_hole_d)}", ext=False)
    sh.dim_h(J((0, -Rr_)), J((-hl, -hd)), jy - Rr_ - 8, num(hl))
    sh.dim_v(J((xl_ + 3, -Rr_)), J((xl_ + 3, Rr_)), jx + xl_ - 7, f"⌀{num(P.rod_d)}")
    sh.leader(J((-ch / 2, hd + ch / 2)), J((-14, Rr_ + 7)), f"{num(ch)}×45°", right=False, h=2.6)
    sh.text(jx + xl_ - 12, jy - Rr_ - 17, f"Штанга ⌀{num(P.rod_d)} — разрез; наконечник — вид.", h=2.3,
            ha="left")

    # ---------------- ТТ ----------------
    tt = [
        "ТЕХНИЧЕСКИЕ ТРЕБОВАНИЯ",
        "1. Массив ясеня, влажность 8±2 %, волокна вдоль оси детали.",
        "2. * Размеры для справок. Форма — по 3D-модели finial.stl;",
        "    неуказанные предельные отклонения ±0,3 мм.",
        f"3. Вогнутые радиусы ≥ R{num(min(P.tenon_fillet, m['Rcv'], m['Rr']))} — под сферу ⌀{num(P.ball_d)} (или ⌀6).",
        "4. Уст. 1–2 — лист Н2; розетка (вид Б) — уст. 3, лист Н3;",
        f"    каннелюры — уст. 4, лист Н4. Фаска на шипе {num(P.tenon_chamfer)}×45°.",
        "5. Шлифовать P150–P240. Покрытие — как у кровати.",
        f"6. Шип вклеить (ПВА D3) в отверстие ⌀{num(P.rod_hole_d)}×{num(hl)}, фаска {num(ch)}×45°;",
        f"    торец ⌀{num(2 * fr)} прилегает к штанге без зазора.",
        f"7. При габарите 1900 длина штанги 1900 − 2×{num(P.length)} = {num(1900 - 2 * P.length)}.",
    ]
    for i, s in enumerate(tt):
        sh.text(25, 110 - i * 5.9, s, h=2.5 if i else 2.9, ha="left", va="top",
                weight="bold" if i == 0 else None)

    if render_png and render_png.exists():
        img = plt.imread(render_png)
        h_, w_ = img.shape[:2]
        wmm = 68.0
        hmm = wmm * h_ / w_
        x0, y0 = 170.0, 46.0
        sh.ax.imshow(img, extent=(x0, x0 + wmm, y0, y0 + hmm), zorder=0)
        sh.text(x0 + wmm / 2, y0 + hmm + 2.5, "3D-вид (справочно)", h=2.5)
    return sh


# ----------------------------------------------------------------------------
# Лист 2 — заготовка и обработка
# ----------------------------------------------------------------------------
def sheet_cnc(P: Params, cnc: Profile, L: dict, checks: dict) -> Sheet:
    sh = Sheet()
    sh.frame(("НАКОНЕЧНИК ШТАНГИ ИЗГОЛОВЬЯ", "КАРТА НАЛАДКИ ЧПУ (3 ОСИ)"),
             "ЛИСТ Н2. УСТАНОВКИ 1–2: ЗАГОТОВКА НА 2 ДЕТАЛИ, ОБРАБОТКА С ПЕРЕВОРОТОМ", 2, NSHEETS, P, "1:1")
    m = cnc.marks
    Lx, Ly, T = L["Lx"], L["Ly"], L["T"]
    rb = P.ball_d / 2
    z_floor = T / 2 - rb - 1
    fw = (Ly - L["pocket_y"]) / 2

    # ---------------- План заготовки ----------------
    ox, oy = 122.0, 164.0      # X0Y0 станка (центр заготовки)
    Pm = lambda x, y: (ox + x, oy + y)
    sh.caption(ox, 286, "1. ЗАГОТОВКА — ВИД СВЕРХУ (М 1:1)")
    sh.poly([Pm(-Lx / 2, -Ly / 2), Pm(Lx / 2, -Ly / 2), Pm(Lx / 2, Ly / 2), Pm(-Lx / 2, Ly / 2)], closed=True)
    px, py = L["pocket_x"] / 2, L["pocket_y"] / 2
    sh.poly([Pm(-px, -py), Pm(px, -py), Pm(px, py), Pm(-px, py)], closed=True, lw=THIN, ls=(0, (4, 2)),
            color="tab:blue")
    sh.text(ox + px - 1, oy - py + 1.5, "граница обработки", h=2.2, ha="right", va="bottom", color="tab:blue")
    for i, sy in enumerate((1, -1)):
        yc = sy * L["y_axis"]
        draw_part_view(sh, P, cnc, ox + L["dx"], oy + yc, 1.0, reeds=False)
        sh.center(Pm(-Lx / 2 - 4, yc), Pm(Lx / 2 + 4, yc))
        sh.text(ox + L["dx"] + P.length - 14, oy + yc, str(i + 1), h=4, weight="bold", bg=True)
    sh.text(ox + L["dx"] - P.tenon_l / 2 - 3, oy + L["y_axis"] + P.tenon_d / 2 + 3, "шип = перемычка", h=2.1)
    sh.text(ox + L["dx"] + P.length + P.gap / 2, oy + L["y_axis"] + 7.5, f"⌀{num(P.bridge_tip_d)}", h=2.1)
    # ось переворота и штифты
    sh.line(Pm(-Lx / 2 - 8, 0), Pm(Lx / 2 + 8, 0), lw=THIN * 1.4, ls=CENTER_LS, color="tab:red")
    sh.text(ox - px + 2, oy + 1.2, "ОСЬ ПЕРЕВОРОТА", h=2.3, ha="left", va="bottom", color="tab:red")
    for (x, y), dpin, lab in ((L["pin_a"], P.pin_d, "Ш1"), (L["pin_b"], P.pin2_d, "Ш2")):
        sh.ax.add_patch(Circle(Pm(x, y), dpin / 2, fill=False, lw=THICK, color="tab:red", zorder=4))
        sh.line(Pm(x - dpin / 2 - 2, y), Pm(x + dpin / 2 + 2, y), lw=THIN, color="tab:red")
        sh.line(Pm(x, y - dpin / 2 - 2), Pm(x, y + dpin / 2 + 2), lw=THIN, color="tab:red")
        sh.text(ox + x, oy - dpin / 2 - 5, f"{lab} ⌀{num(dpin)}", h=2.3, color="tab:red")
    sh.ax.add_patch(Circle(Pm(0, 0), 1.4, fill=True, color="k", zorder=5))
    sh.line(Pm(0, 0), Pm(0, 10), lw=THIN)
    sh.arrow(Pm(0, 12), (0, 1))
    sh.text(ox + 2.5, oy + 11, "Y", h=2.6)
    sh.text(ox + 2, oy - 4.5, "X0 Y0", h=2.3, ha="left")
    sh.text(ox + Lx / 2 + 10, oy + 3, "X→", h=2.6, ha="left")
    sh.text(ox - Lx / 2 + fw / 2, oy + Ly / 2 - 8, "метка\n«А»", h=2.3, weight="bold")
    # размеры
    sh.dim_h(Pm(-Lx / 2, Ly / 2), Pm(Lx / 2, Ly / 2), oy + Ly / 2 + 12, num(Lx))
    sh.dim_h(Pm(-px, py), Pm(px, py), oy + Ly / 2 + 5, num(L["pocket_x"]))
    sh.dim_v(Pm(-Lx / 2, -Ly / 2), Pm(-Lx / 2, Ly / 2), ox - Lx / 2 - 18, num(Ly))
    sh.dim_v(Pm(-Lx / 2, 0), Pm(-Lx / 2, L["y_axis"]), ox - Lx / 2 - 8, num(L["y_axis"]))
    sh.dim_v(Pm(-Lx / 2, 0), Pm(-Lx / 2, -L["y_axis"]), ox - Lx / 2 - 8, num(L["y_axis"]))
    sh.dim_h(Pm(L["pin_a"][0], 0), Pm(0, 0), oy - Ly / 2 - 8, num(-L["pin_a"][0]))
    sh.dim_h(Pm(0, 0), Pm(L["pin_b"][0], 0), oy - Ly / 2 - 8, num(L["pin_b"][0]))
    sh.dim_h(Pm(L["dx"], -L["y_axis"] - m["face_r"]), Pm(0, -Ly / 2), oy - Ly / 2 - 16,
             f"{num(-L['dx'])} (торец воротника)")

    # ---------------- Сечение (половина) ----------------
    cx, cy = 336.0, 204.0            # Y = 0, Z = 0 станка
    Q = lambda y, z: (cx + y, cy + z)
    sh.caption(cx - 30, 286, "2. СЕЧЕНИЕ ПО ВОРОТНИКАМ, ПОЛОВИНА (М 1:1)")
    sh.hatch([Q(-Ly / 2, 0), Q(-Ly / 2 + fw, 0), Q(-Ly / 2 + fw, T), Q(-Ly / 2, T)], hatch="\\\\\\\\")
    c = Q(-L["y_axis"], T / 2)
    sh.ax.add_patch(Circle(c, m["Rc"], fill=False, hatch="////", lw=THICK, zorder=2))
    sh.center((c[0], c[1] - m["Rc"] - 3), (c[0], c[1] + m["Rc"] + 3))
    sh.center(Q(0, -3), Q(0, T + 3))
    sh.poly([Q(-Ly / 2 + fw, T), Q(2, T)], lw=THIN, ls=(0, (2, 2)))
    sh.line(Q(-Ly / 2 - 22, T / 2), Q(6, T / 2), lw=THIN * 1.4, ls=CENTER_LS, color="tab:red")
    sh.text(cx - Ly / 2 - 23, cy + T / 2 + 1.2, "разъём", h=2.3, ha="left", va="bottom", color="tab:red")
    sh.line(Q(-Ly / 2 - 22, 0), Q(6, 0), lw=THICK)
    sh.text(cx - Ly / 2 - 23, cy - 1.2, "стол, Z0", h=2.3, ha="left", va="top")
    # фреза у экватора, в зазоре между деталью и рамкой
    yb_ = -L["y_axis"] - m["Rc"] - rb
    ang = np.linspace(np.pi, 2 * np.pi, 40)
    tool = ([Q(yb_ - rb, T + 9)] + [Q(yb_ + rb * math.cos(t), T / 2 + rb * math.sin(t)) for t in ang]
            + [Q(yb_ + rb, T + 9)])
    sh.poly(tool, lw=THIN * 1.3, color="tab:blue")
    sh.text(cx + yb_, cy + T + 12, f"сфера ⌀{num(P.ball_d)}", h=2.3, color="tab:blue")
    sh.line(Q(-L["y_axis"] + m["Rc"] - 2, z_floor), Q(-1, z_floor), lw=THIN, color="tab:blue")
    sh.dim_v(Q(-3, T), Q(-3, z_floor), cx - 3, num(T - z_floor), ext=False, left=False)
    sh.dim_v(Q(-Ly / 2, 0), Q(-Ly / 2, T), cx - Ly / 2 - 5, num(T))
    sh.dim_v(Q(-Ly / 2 + fw, 0), Q(-Ly / 2 + fw, T / 2), cx - Ly / 2 + fw + 6, num(T / 2), ext=False,
             left=False)
    sh.dim_v(Q(-L["y_axis"], T / 2 - m["Rc"]), Q(-L["y_axis"], T / 2 + m["Rc"]), cx - L["y_axis"],
             f"⌀{num(P.collar_d)}", ext=False)
    notes_s = [
        "Сторона А — сверху. После",
        "переворота сторона Б — той же УП.",
        "Глубина с каждой стороны",
        f"T/2 + R + 1 = {num(T - z_floor)} мм: карман",
        "сквозной, детали держатся",
        "только на перемычках.",
    ]
    for i, s in enumerate(notes_s):
        sh.text(cx + 12, cy + T - 2 - i * 4.6, s, h=2.3, ha="left", va="top")

    # ---------------- Таблица операций ----------------
    x0, y0 = 214.0, 182.0
    sh.caption(x0 + 100, y0 + 5, "3. ПОРЯДОК ОБРАБОТКИ")
    rows = [
        ("№", "Операция", "Инструмент / режим (ясень)"),
        ("1", f"Брус ясеня {num(Lx)}×{num(Ly)}×{num(T)} (строганый), волокна\n"
              "вдоль X. Замерить толщину T — ввести в УП.", "—"),
        ("2", "Стол отфрезеровать в плоскость, Z0 — по столу.\n"
              f"Сверлить насквозь в стол Ш1 ⌀{num(P.pin_d)} и Ш2 ⌀{num(P.pin2_d)} на оси X,\n"
              "вставить штифты, прикрутить заготовку по рамке.", "сверло или\nфреза ⌀8"),
        ("3", f"Сторона А — черновая 3D, припуск 0,5 мм,\nдо Z = T/2 − {num(rb + 1)}.",
         f"концевая ⌀8, вылет ≥ {num(T - z_floor + 6)}\nn 18000, F 3000, 4 мм/прох."),
        ("4", "Сторона А — чистовая: растр вдоль X (вдоль оси и\nканнелюр), затем растр вдоль Y.",
         f"сфера ⌀{num(P.ball_d)} R{num(rb)}, цилиндр.\nn 18000, F 3500, шаг 0,4"),
        ("5", "Перевернуть брус вокруг оси X, «А» остаётся слева.\n"
              "Разные штифты не дают ошибиться.", "—"),
        ("6", "Сторона Б — те же УП 3 и 4 без изменений.", "как 3, 4"),
        ("7", "Отпилить перемычки (на куполе оставить ≤ 1 мм),\nфаска на шипе. Далее — уст. 3 (Н3) и 4 (Н4).",
         "ножовка"),
    ]
    colx = [x0, x0 + 8, x0 + 124, 415]
    rh = [6.5, 11, 14, 11, 11, 11, 7.5, 11]
    y = y0
    sh.line((colx[0], y), (colx[-1], y), lw=THICK)
    for row, h_ in zip(rows, rh):
        for j, cell in enumerate(row):
            sh.text(colx[j] + (4 if j == 0 else 1.5), y - h_ / 2, cell, h=2.25,
                    ha="center" if j == 0 else "left", weight="bold" if row[0] == "№" else None)
        y -= h_
        sh.line((colx[0], y), (colx[-1], y), lw=THIN)
    for xx in colx:
        sh.line((xx, y0), (xx, y), lw=THIN)

    notes = [
        "ПРОВЕРЕНО РАСЧЁТОМ",
        f"• Шейка и купол здесь гладкие (каннелюры — уст. 4, розетка — уст. 3). Вогнутые",
        f"  радиусы ≥ R{num(checks['min_concave_profile'])}, тело вращения — поднутрений нет.",
        f"• Симуляция чистовой по карте высот: недорез ≤ {checks[f'ball_{P.ball_d:g}_max_leftover']:.2f} мм"
        f" (⌀{num(P.ball_d)}), ≤ {checks['ball_6_max_leftover']:.2f} мм (⌀6).",
        f"• Сфера должна доставать до Z = T/2 − {num(rb)} у экватора: хвостовик того же ⌀,",
        "  конусные фрезы не подходят (зарежут бока у разъёма).",
        "• Файлы: cnc_setup1-2_2pcs.stl — обе детали с перемычками в координатах",
        "  станка (купол гладкий); cnc_setup1-2_layout.dxf — контуры, карман, штифты.",
    ]
    for i, s in enumerate(notes):
        sh.text(x0, y - 4 - i * 4.7, s, h=2.25, ha="left", va="top", weight="bold" if i == 0 else None)
    return sh


# ----------------------------------------------------------------------------
# Лист 3 — розетка и установка 3
# ----------------------------------------------------------------------------
def hillshade(Z, step, light=(-0.55, 0.55, 0.65)):
    gy, gx = np.gradient(np.nan_to_num(Z, nan=np.nanmin(Z)), step)
    n = np.dstack([-gx, gy, np.ones_like(Z)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    L = np.asarray(light, float)
    L /= np.linalg.norm(L)
    v = 0.30 + 0.70 * np.clip(n @ L, 0, 1)
    img = np.dstack([v * 0.97, v * 0.95, v * 0.92, np.where(np.isnan(Z), 0.0, 1.0)])
    return np.clip(img, 0, 1)


def sheet_rosette(P: Params, prof: Profile) -> Sheet:
    sh = Sheet()
    sh.frame(("НАКОНЕЧНИК ШТАНГИ ИЗГОЛОВЬЯ", "РОЗЕТКА НА ТОРЦЕ"),
             "ЛИСТ Н3. УСТАНОВКА 3: РОЗЕТКА, ДЕТАЛЬ ТОРЦОМ ВВЕРХ В КОНДУКТОРЕ", 3, NSHEETS, P, "4:1; 1:1")
    m = prof.marks
    R = P.rosette_r
    rp = P.pearl_d / 2
    rho_p = R - 1.4 - rp
    D = P.rosette_depth

    # ---------------- 1. Вид Б, М 4:1 ----------------
    k = 4.0
    cx, cy = 112.0, 190.0
    half = 21.5
    sh.caption(cx, 286, "1. ВИД Б — РОЗЕТКА (М 4:1)")
    g, Z = end_heightmap(P, prof, half=half, step=0.03)
    rr = np.hypot(*np.meshgrid(g, g))
    Z = np.where(rr > half, np.nan, Z)
    sh.ax.imshow(hillshade(Z, 0.03), extent=(cx - k * half, cx + k * half, cy - k * half, cy + k * half),
                 zorder=1, interpolation="bilinear")
    tang = m["ye"] + m["Re"] * math.sin(math.radians(m["a_t"]))
    th = np.linspace(0, 2 * np.pi, 400)
    sh.poly(np.c_[cx + k * tang * np.cos(th), cy + k * tang * np.sin(th)], lw=THIN)
    sh.center((cx - k * half - 5, cy), (cx + k * half + 5, cy))
    sh.center((cx, cy - k * half - 5), (cx, cy + k * half + 5))
    xt = cx + k * half + 3
    P_ = lambda rho, ang: (cx + k * rho * math.sin(math.radians(ang)), cy + k * rho * math.cos(math.radians(ang)))
    items = [
        (P_(rho_p, 60), 64, f"{P.pearls} бусин ⌀{num(P.pearl_d)} по ⌀{num(2 * rho_p)}"),
        (P_(10.0, 90 - 4), 44, f"{P.petals} лепестков"),
        (P_(12.9, 67.5), 54, f"{P.petals} листков"),
        (P_(1.5, 120), 34, f"пуговка ⌀{num(P.button_d)}"),
        (P_(R - 0.3, 145), 24, "поясок"),
        (P_(15.0, 180 - 22.5), 14, f"фон −{num(D)}"),
    ]
    for tip, dy, text in items:
        if text is None:
            continue
        sh.leader(tip, (xt, cy + dy - 40), text, h=2.5)
    sh.text(cx - k * half, cy + k * half + 3, f"резная зона ⌀{num(2 * R)}", h=2.5, ha="left")

    # ---------------- 2. Разрез В–В, М 4:1 ----------------
    x0 = 47.0
    oy = 52.0
    sh.caption(cx, 97, "2. РАЗРЕЗ ПО ОСИ ЛЕПЕСТКОВ (М 4:1)")
    rho = np.linspace(-22, 22, 2201)
    thv = np.where(rho >= 0, 0.0, np.pi)
    xe_ = end_x(P, prof, np.abs(rho), thv)
    arc = m["xe"] + np.sqrt(np.clip(m["Re"] ** 2 - (np.abs(rho) - m["ye"]) ** 2, 0, None))
    xe_ = np.where(np.abs(rho) > tang, arc, xe_)
    top = np.c_[cx + k * rho, oy + k * (xe_ - x0)]
    sh.hatch(np.vstack([top, [[cx + k * 22, oy], [cx - k * 22, oy]]]), hatch="////")
    dom = np.linspace(-tang, tang, 300)
    sh.poly(np.c_[cx + k * dom, oy + k * (dome_x(prof, np.abs(dom)) - x0)], lw=THIN, ls=(0, (4, 2)),
            color="tab:blue")
    sh.center((cx, oy - 3), (cx, oy + k * (P.length - x0) + 5))
    sh.leader((cx - k * 11, oy + k * (float(dome_x(prof, 11)) - x0)),
              (cx - k * 16, oy + k * (P.length - x0) + 2), f"купол после уст. 1–2, R{num(m['Rd'])}",
              right=False, h=2.3)
    # глубина фона
    rg = rho_p - rp - 0.45
    zb = float(dome_x(prof, rg)) - D
    sh.dim_v((cx + k * rg, oy + k * (zb - x0)), (cx + k * rg, oy + k * (float(dome_x(prof, rg)) - x0)),
             cx + k * rg, num(D), ext=False, left=False)
    sh.text(cx + k * 22 + 2, oy + k * (P.length - x0), f"Z {num(P.length)}", h=2.3, ha="left")
    sh.line((cx + 2, oy + k * (P.length - x0)), (cx + k * 22 + 1, oy + k * (P.length - x0)), lw=THIN)

    # ---------------- 3. Кондуктор, М 1:1 ----------------
    F = fixture_layout(P)
    fx, fy = 322.0, 205.0        # X0, Z0 кондуктора
    sh.caption(fx, 286, "3. УСТАНОВКА 3 — КОНДУКТОР (М 1:1)")
    lx, T = F["Lx"] / 2, F["T"]
    hr, hd_ = F["hole_d"] / 2, F["hole_depth"]
    board = [(-lx, 0)]
    for hx, _ in F["holes"]:
        board += [(hx - hr, 0), (hx - hr, -hd_), (hx + hr, -hd_), (hx + hr, 0)]
    board += [(lx, 0), (lx, -T), (-lx, -T)]
    sh.hatch([(fx + x, fy + z) for x, z in board], hatch="\\\\\\\\")
    for hx, _ in F["holes"]:
        draw_part_view(sh, P, prof, fx + hx, fy, 1.0, rosette=True, vertical=True, reeds=False)
        sh.center((fx + hx, fy - T - 3), (fx + hx, fy + P.length + 6))
    # фреза над левой деталью
    hx0 = F["holes"][0][0]
    tipz = P.length + 0.3
    tool = [(fx + hx0 - 3, fy + tipz + 18), (fx + hx0 - 0.5, fy + tipz + 0.5),
            (fx + hx0 + 0.5, fy + tipz + 0.5), (fx + hx0 + 3, fy + tipz + 18)]
    sh.poly(tool, lw=THIN * 1.3, color="tab:blue")
    sh.text(fx + hx0 + 5, fy + tipz + 14, "конусная\nсфера R0,5", h=2.2, ha="left", color="tab:blue")
    hx1 = F["holes"][1][0]
    zr = float(dome_x(prof, F["zone_r"]))
    sh.dim_h((fx + hx1 - F["zone_r"], fy + zr), (fx + hx1 + F["zone_r"], fy + zr), fy + P.length + 9,
             f"⌀{num(2 * F['zone_r'])} зона")
    sh.dim_h((fx + hx0, fy - T), (fx + hx1, fy - T), fy - T - 8, num(P.fixture_pitch))
    sh.dim_v((fx - lx, fy - T), (fx - lx, fy), fx - lx - 5, num(T))
    sh.dim_v((fx + lx, fy), (fx + lx, fy + P.length), fx + lx + 6, num(P.length), left=False)
    sh.dim_v((fx + hx1 + hr, fy - hd_), (fx + hx1 + hr, fy), fx + hx1 + hr + 5, num(hd_), ext=True,
             left=False)
    sh.text(fx - lx - 2, fy + 2, "Z0", h=2.4, ha="right", va="bottom")
    sh.leader((fx + hx1 - hr, fy - 10), (fx + hx1 - 22, fy - 16), f"гнездо ⌀{num(F['hole_d'])}",
              right=False, h=2.3)

    # ---------------- 4. Порядок ----------------
    x0t, y0t = 222.0, 150.0
    sh.caption(x0t + 96, y0t + 5, "4. ПОРЯДОК ОБРАБОТКИ (УСТАНОВКА 3)")
    rows = [
        ("№", "Операция", "Инструмент / режим"),
        ("1", f"Кондуктор — брус или фанера ≥ {num(T)} мм, прикрутить к столу.\n"
              f"Гнёзда ⌀{num(F['hole_d'])} гл. {num(hd_)}, шаг {num(P.fixture_pitch)}: посадка плотная,\n"
              "по месту по шипу.", "концевая ⌀6,\nспиральное врезание"),
        ("2", "Z0 — верх кондуктора, X0Y0 — между гнёздами.\nВставить детали шипом вниз до упора торцом.",
         "при люфте — скотч\nна шип / термоклей"),
        ("3", f"Черновая в зоне ⌀{num(2 * F['zone_r'])} от Z {num(P.length + 2)} (остаток\n"
              "перемычки) до рельефа, припуск 0,2.", "концевая ⌀3,\nшаг Z 1, F 1500"),
        ("4", "Чистовая рельефа, растр под 45°.", "конусная сфера R0,5\nшаг 0,1, F 1500"),
        ("5", "Зачистить розетку щёткой, не заваливая бусины.", "—"),
    ]
    colx = [x0t, x0t + 8, x0t + 125, 415]
    rh = [6.5, 14, 11, 11, 11, 7.5]
    y = y0t
    sh.line((colx[0], y), (colx[-1], y), lw=THICK)
    for row, h_ in zip(rows, rh):
        for j, cell in enumerate(row):
            sh.text(colx[j] + (4 if j == 0 else 1.5), y - h_ / 2, cell, h=2.25,
                    ha="center" if j == 0 else "left", weight="bold" if row[0] == "№" else None)
        y -= h_
        sh.line((colx[0], y), (colx[-1], y), lw=THIN)
    for xx in colx:
        sh.line((xx, y0t), (xx, y), lw=THIN)
    notes = [
        "ПОЧЕМУ ОТДЕЛЬНАЯ УСТАНОВКА",
        "При обработке с переворотом торец — вертикальная стенка: по ±Z на нём можно",
        "получить только кольца. Розетка — рельеф, его режем сверху, деталь торцом вверх.",
        "ФАЙЛЫ",
        "• cnc_setup3_rosette_1pc.stl — шляпка с розеткой, ось = Z, опорный торец Z = 0:",
        f"  поставить дважды, в X = ±{num(P.fixture_pitch / 2)}.",
        "• cnc_setup3_fixture.dxf — гнёзда и границы зон; rosette_heightmap_16bit.png —",
        "  карта высот для «рельефа из изображения» (масштаб — в rosette_heightmap.txt).",
    ]
    for i, s_ in enumerate(notes):
        bold = s_.isupper()
        sh.text(x0t, y - 4 - i * 4.6, s_, h=2.25, ha="left", va="top", weight="bold" if bold else None)
    return sh



# ----------------------------------------------------------------------------
# Лист 4 — каннелюры в делительной оправке
# ----------------------------------------------------------------------------
def sheet_flutes(P: Params, prof: Profile, checks: dict) -> Sheet:
    sh = Sheet()
    sh.frame(("НАКОНЕЧНИК ШТАНГИ ИЗГОЛОВЬЯ", "КАННЕЛЮРЫ НА ШЕЙКЕ"),
             "ЛИСТ Н4. УСТАНОВКА 4: КАННЕЛЮРЫ, ДЕТАЛЬ В ДЕЛИТЕЛЬНОЙ ОПРАВКЕ, 4 ПОВОРОТА", 4, NSHEETS, P,
             "1:1; 2,5:1")
    m = prof.marks
    I = index_layout(P)
    B, h, pk = I["B"], I["h"], I["pocket"]
    tr = P.flute_tool_r

    # ---------------- 1. Схема установки, М 1:1 ----------------
    ox, oy = 92.0, 205.0            # X0 (опорный торец), Z0 (верх ложемента)
    T = lambda x, z: (ox + x, oy + z)
    sh.caption(ox + 5, 286, "1. СХЕМА УСТАНОВКИ 4 (М 1:1)")
    a0, a1 = I["trough_x"]
    c0, c1 = I["cradle_x"]
    zt, zc = h - I["trough_r"], h - I["cradle_r"]
    plate = [(I["x0"], -I["t"]), (I["x0"], 0), (-B - 0.2, 0), (-B - 0.2, -pk), (a0, -pk), (a0, zt), (a1, zt),
             (a1, zc), (c1, zc), (c1, 0), (I["x1"], 0), (I["x1"], -I["t"])]
    sh.hatch([T(*p) for p in plate], hatch="\\\\\\\\")
    # оправка и шип внутри неё
    sh.poly([T(-B, -pk), T(0, -pk), T(0, B - pk), T(-B, B - pk)], closed=True)
    sh.line(T(-B, h), T(0, h), lw=THIN)
    for z in (h - I["chan_r"], h + I["chan_r"]):
        sh.line(T(-B, z), T(0, z), lw=THIN, ls=(0, (3, 1.5)))
    sh.line(T(-P.tenon_l, h - I["chan_r"]), T(-P.tenon_l, h + I["chan_r"]), lw=THIN, ls=(0, (3, 1.5)))
    sh.text(ox - B / 2, oy + B - pk - 6, "оправка", h=2.3)
    # прижимная планка
    sh.poly([T(-B + 8, B - pk), T(-8, B - pk), T(-8, B - pk + 5), T(-B + 8, B - pk + 5)], closed=True, lw=THIN)
    sh.text(ox - B / 2, oy + B - pk + 8, "прижим", h=2.2)
    draw_part_view(sh, P, prof, ox, oy + h, 1.0, rosette=True, xmin=0.0)
    sh.center(T(-B - 6, h), T(P.length + 6, h))
    # фреза над канавкой
    xt = m["xn"]
    ztip = h + m["rn"] - P.reed_depth * 0.9
    b = math.radians(P.flute_tool_angle)
    top = ztip + 24
    sh.poly([T(xt - tr - (top - ztip) * math.tan(b), top), T(xt - tr, ztip + tr), T(xt + tr, ztip + tr),
             T(xt + tr + (top - ztip) * math.tan(b), top)], lw=THIN * 1.3, color="tab:blue")
    sh.text(ox + xt + 6, oy + top - 4, f"конусная сфера R{num(tr)}, {num(2 * P.flute_tool_angle)}°", h=2.2,
            ha="left", color="tab:blue")
    # размеры
    sh.dim_v(T(I["x1"], 0), T(I["x1"], h), ox + I["x1"] + 6, num(h), left=False)
    sh.dim_v(T(-B, -pk), T(-B, B - pk), ox - B - 8, num(B))
    sh.dim_v(T(I["x0"], -pk), T(I["x0"], 0), ox + I["x0"] - 4, num(pk), ext=False)
    sh.line(T(I["x0"] - 1, -pk), T(-B - 0.2, -pk), lw=THIN)
    sh.text(ox + I["x1"] + 2, oy - 1.5, "Z0", h=2.4, ha="left", va="top")
    sh.text(ox, oy + h + m["Rc"] + 4, "X0", h=2.4)
    sh.leader(T((c0 + c1) / 2 + 6, zc + 1.2), T(c1 + 4, -I["t"] + 8), f"ложе R{num(I['cradle_r'])}", h=2.2)

    # ---------------- 2. Оправка, М 1:1 ----------------
    ex, ey = 262.0, 232.0            # центр торца оправки
    sh.caption(318, 286, "2. ДЕЛИТЕЛЬНАЯ ОПРАВКА (М 1:1)")
    sh.poly([(ex - B / 2, ey - B / 2), (ex + B / 2, ey - B / 2), (ex + B / 2, ey + B / 2), (ex - B / 2, ey + B / 2)],
            closed=True)
    sh.line((ex - B / 2, ey), (ex + B / 2, ey), lw=THIN)
    sh.ax.add_patch(Circle((ex, ey), I["chan_r"], fill=False, lw=THICK, zorder=3))
    sh.center((ex - B / 2 - 4, ey), (ex + B / 2 + 4, ey))
    sh.center((ex, ey - B / 2 - 4), (ex, ey + B / 2 + 4))
    for s_ in (1, -1):
        yb = s_ * (B / 2 - 6)
        sh.line((ex + yb - 2.25, ey - B / 2), (ex + yb - 2.25, ey + B / 2), lw=THIN, ls=(0, (3, 1.5)))
        sh.line((ex + yb + 2.25, ey - B / 2), (ex + yb + 2.25, ey + B / 2), lw=THIN, ls=(0, (3, 1.5)))
    for k_, (dx, dy) in enumerate(((0, -1), (1, 0), (0, 1), (-1, 0))):
        sh.text(ex + dx * (B / 2 - 4), ey + dy * (B / 2 - 4), str(k_ + 1), h=3.2, weight="bold", bg=True)
    th = np.linspace(math.radians(200), math.radians(250), 30)
    rr = B / 2 + 9
    sh.poly(np.c_[ex + rr * np.cos(th), ey + rr * np.sin(th)], lw=THIN)
    sh.arrow((ex + rr * math.cos(th[-1]), ey + rr * math.sin(th[-1])), (math.sin(th[-1]), -math.cos(th[-1])))
    sh.text(ex - rr - 2, ey - rr + 2, "90°", h=2.5, ha="right")
    sh.dim_h((ex - B / 2, ey + B / 2), (ex + B / 2, ey + B / 2), ey + B / 2 + 8, num(B))
    sh.leader((ex + I["chan_r"] * 0.7, ey + I["chan_r"] * 0.7), (ex + B / 2 + 6, ey + B / 2 + 4),
              f"R{num(I['chan_r'])} (шип ⌀{num(P.tenon_d)})", h=2.3)
    txt = [
        f"Две одинаковые половины {num(B)}×{num(B)}×{num(B / 2)}",
        "(fixture_setup4_index_half), вдоль —",
        f"полуканавка R{num(I['chan_r'])}. Стянуть на шипе",
        "2 винтами M4×35 с гайками (цековки",
        "⌀9×3 с обеих сторон). Торец детали —",
        "вплотную к торцу оправки.",
        "Грани пометить 1–4 (нижняя грань",
        "в гнезде = номер позиции).",
    ]
    for i, t_ in enumerate(txt):
        sh.text(ex + B / 2 + 14, ey + 10 - i * 4.4, t_, h=2.25, ha="left", va="top")

    # ---------------- 3. Сечение шейки, М 4:1 ----------------
    ks = 2.5
    cx, cy = 115.0, 104.0
    sh.caption(cx, 160, "3. СЕЧЕНИЕ ШЕЙКИ — СЕКТОРЫ ПОЗИЦИЙ (М 2,5:1)")
    xa = m["xn"]
    R0 = float(radius_table(prof, np.array([xa]))[0])
    d = float(reed_d(P, prof, np.array([xa]), np.array([R0]))[0])
    phi = np.linspace(0, 2 * np.pi, 1441)
    r = R0 - d * reed_v(P, phi)
    sh.hatch(np.c_[cx + ks * r * np.sin(phi), cy + ks * r * np.cos(phi)], hatch="/////")
    sec = 2 * math.pi / P.reeds
    for k_ in range(4):
        base = -k_ * math.pi / 2          # позиция k+1: этот сектор сверху после поворотов
        for s_ in (-1, 1):
            a = base + s_ * sec
            sh.line((cx, cy), (cx + ks * (R0 + 5) * math.sin(a), cy + ks * (R0 + 5) * math.cos(a)),
                    lw=THIN, ls=(0, (4, 2)), color="tab:blue")
        lab = (cx + ks * (R0 + 3.5) * math.sin(base), cy + ks * (R0 + 3.5) * math.cos(base))
        sh.text(*lab, str(k_ + 1), h=3.6, weight="bold", color="tab:blue", bg=True)
    arc = np.linspace(-sec, sec, 60)
    sh.poly(np.c_[cx + ks * (R0 + 1.2) * np.sin(arc), cy + ks * (R0 + 1.2) * np.cos(arc)], lw=THICK * 1.6,
            color="tab:blue")
    # фреза в канавке позиции 1
    av = math.pi / P.reeds
    rv = R0 - d
    tip = np.array([math.sin(av), math.cos(av)]) * rv
    ttop = tip[1] + 9
    tool = [(tip[0] - tr - (ttop - tip[1]) * math.tan(b), ttop), (tip[0] - tr, tip[1] + tr),
            (tip[0] + tr, tip[1] + tr), (tip[0] + tr + (ttop - tip[1]) * math.tan(b), ttop)]
    sh.poly([(cx + ks * x, cy + ks * z) for x, z in tool], lw=THIN * 1.3, color="tab:blue")
    sh.center((cx - ks * R0 - 8, cy), (cx + ks * R0 + 8, cy))
    sh.center((cx, cy - ks * R0 - 8), (cx, cy + ks * R0 + 8))
    sh.dim_h((cx - ks * R0, cy), (cx + ks * R0, cy), cy - ks * R0 - 16, f"⌀{num(2 * R0)} по гребням")
    sh.leader((cx - ks * rv * math.sin(av), cy + ks * rv * math.cos(av)), (cx - ks * R0 - 12, cy + ks * R0 + 4),
              f"канавка {num(P.reed_depth)}, острая", right=False, h=2.3)
    sh.text(cx + ks * R0 + 10, cy + 20,
            "Позиция 1: сверху сектор ±45°\n(синяя дуга) — 2 канавки и\nвалики до гребней. Поворот\n"
            "оправки на 90° выводит наверх\nследующий сектор.",
            h=2.25, ha="left", va="top")

    # ---------------- 4. Порядок ----------------
    x0t, y0t = 222.0, 184.0
    sh.caption(x0t + 96, y0t + 5, "4. ПОРЯДОК ОБРАБОТКИ (УСТАНОВКА 4)")
    rows = [
        ("№", "Операция", "Инструмент / режим"),
        ("1", "Ложемент — плита ≥ 30 мм на столе, фрезеровать по модели\n"
              "fixture_setup4_nest. Z0 — верх ложемента, X0 — торец\n"
              "гнезда оправки, Y0 — между гнёздами.", "концевая ⌀6 + сфера ⌀6"),
        ("2", f"Оправки: 4 половины из бруска {num(B / 2)} мм, полуканавка — сферой.\n"
              "Зажать шип, торец детали — к торцу оправки.", "сфера ⌀6"),
        ("3", "Оправку гранью «1» вниз в гнездо, шляпку — в ложе,\nприжать планкой.", "—"),
        ("4", "УП каннелюр в границе FLUTE_ZONE: 2 прохода по Z\n(припуск 0,3), чистовая — растр вдоль X.",
         f"конусная сфера R{num(tr)},\n{num(2 * P.flute_tool_angle)}°, шаг 0,1, F 1500"),
        ("5", "Повернуть оправку на 90° (грани 2, 3, 4) и повторить\nту же УП. Итого 4 прохода на деталь.", "как 4"),
        ("6", "Канавки не шлифовать бруском — только сложенной\nшкуркой вдоль, чтобы грани остались острыми.",
         "P240"),
    ]
    colx = [x0t, x0t + 8, x0t + 125, 415]
    rh = [6.5, 14, 11, 11, 11, 11, 11]
    y = y0t
    sh.line((colx[0], y), (colx[-1], y), lw=THICK)
    for row, h_ in zip(rows, rh):
        for j, cell in enumerate(row):
            sh.text(colx[j] + (4 if j == 0 else 1.5), y - h_ / 2, cell, h=2.25,
                    ha="center" if j == 0 else "left", weight="bold" if row[0] == "№" else None)
        y -= h_
        sh.line((colx[0], y), (colx[-1], y), lw=THIN)
    for xx in colx:
        sh.line((xx, y0t), (xx, y), lw=THIN)
    notes = [
        "ПОЧЕМУ ОТДЕЛЬНАЯ УСТАНОВКА",
        "При обработке с переворотом канавки у линии разъёма стоят почти вертикально",
        "и выходят размытыми. В оправке каждая пара канавок по очереди оказывается",
        "сверху: стенки чёткие (угол канавки ≈ 90°), дно — радиус кончика фрезы.",
        "ПРОВЕРЕНО РАСЧЁТОМ",
        f"• Запас между стенками канавок и конусом фрезы {num(checks.get('index_draft', 0))}°.",
        f"• Симуляция: недорез на валиках ≤ {checks.get('flute_max_leftover', 0):.2f} мм.",
        "ФАЙЛЫ: cnc_setup4_flutes_2pcs.stl, cnc_setup4_nest.dxf,",
        "fixture_setup4_nest.step/.stl, fixture_setup4_index_half.step/.stl",
    ]
    for i, s_ in enumerate(notes):
        sh.text(x0t, y - 4 - i * 4.6, s_, h=2.25, ha="left", va="top", weight="bold" if s_.isupper() else None)
    return sh


def make(P: Params, prof: Profile, cnc: Profile, L: dict, checks: dict, out: Path):
    sheets = [sheet_part(P, prof, L, out / "render_tip.png"), sheet_cnc(P, cnc, L, checks)]
    names = ["sheet1_part.png", "sheet2_setup1-2.png"]
    if P.rosette:
        sheets.append(sheet_rosette(P, prof))
        names.append("sheet3_rosette_setup3.png")
    if P.reeds:
        sheets.append(sheet_flutes(P, prof, checks))
        names.append("sheet4_flutes_setup4.png")
    with PdfPages(out / "finial_drawing.pdf") as pdf:
        for s in sheets:
            pdf.savefig(s.fig)
    for s, n in zip(sheets, names):
        s.fig.savefig(out / n, dpi=150)
    plt.close("all")
    print("finial_drawing.pdf,", ", ".join(names))
