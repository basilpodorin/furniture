"""Диагностика: планы плит с рёбрами и профили нескольких рёбер поверх сечений."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
t = time.time()
from lib.frame import Frame, S, plane_section
import params as P
F = Frame()
print("frame built", round(time.time() - t, 1), "s;", len(F.parts), "parts")

def draw(ax, g, **kw):
    for p in getattr(g, "geoms", [g]):
        if p.is_empty: continue
        x, y = p.exterior.xy; ax.plot(x, y, **kw)
        for i in p.interiors:
            x, y = i.xy; ax.plot(x, y, **kw)

fig, axs = plt.subplots(1, 3, figsize=(30, 11))
for ax, (name, z, plate) in zip(axs, [("П1+нижние рёбра", 200, "П1"), ("П3", 330, "П3"), ("П4+верхние рёбра", 470, "П4")]):
    draw(ax, S.plan(z).convex_hull if name!="П4+верхние рёбра" else S.plan(z), color="#bbb", lw=1)
    for pt in F.parts:
        if pt.code == plate:
            draw(ax, pt.shape, color="k", lw=1)
    ribs = F.lower_ribs if plate in ("П1", "П3") else F.upper_ribs
    for r in ribs:
        u0, _, u1, _ = r.shape.bounds
        for sx in ((1,) if r.qty == 1 else (1, -1)):
            ox, oy = sx * r.origin[0], r.origin[1]; dx, dy = sx * r.direction[0], r.direction[1]
            ax.plot([ox + u0 * dx, ox + u1 * dx], [oy + u0 * dy, oy + u1 * dy], "r", lw=3, alpha=.6)
    if plate != "П4":
        for p in F.partitions:
            u0, _, u1, _ = p.shape.bounds
            for sx in ((1, -1) if p.code == "ПГ1" else (1,)):
                ox, oy = sx * p.origin[0], p.origin[1]; dx, dy = p.direction
                ax.plot([ox + u0 * dx, ox + u1 * dx], [oy + u0 * dy, oy + u1 * dy], "b", lw=3, alpha=.6)
    ax.set_aspect("equal"); ax.grid(True, lw=.3); ax.set_title(name)
plt.tight_layout(); plt.savefig(".cache/diag_plans.png", dpi=55); plt.close()

sel = [F.lower_ribs[0], F.lower_ribs[len(F.lower_ribs)//2], F.lower_ribs[-1],
       F.upper_ribs[0], F.upper_ribs[len(F.upper_ribs)//2], F.upper_ribs[-2], F.upper_ribs[-1]]
fig, axs = plt.subplots(1, len(sel), figsize=(5 * len(sel), 9))
for ax, r in zip(axs, sel):
    sec = plane_section(r.origin, r.direction)
    draw(ax, sec, color="#999", lw=1)
    draw(ax, r.shape, color="r", lw=1.2)
    for z in (P.Z_P1, P.Z_P1 + P.PLY, P.Z_P3, P.Z_P3 + P.PLY, P.Z_P4, P.Z_P4 + P.PLY):
        ax.axhline(z, color="b", lw=.4)
    ax.set_xlim(-200, 500); ax.set_ylim(0, 760); ax.set_aspect("equal"); ax.grid(True, lw=.3)
    ax.set_title(f"{r.code} o={np.round(r.origin,0)} d={np.round(r.direction,2)}", fontsize=8)
plt.tight_layout(); plt.savefig(".cache/diag_ribs.png", dpi=55); plt.close()
for p in F.parts:
    b = p.shape.bounds
    print(f"{p.code:5s} {p.name:45s} qty={p.qty} {b[2]-b[0]:6.0f}×{b[3]-b[1]:5.0f}  {p.mass_kg:5.2f} кг")
print("масса фанеры, кг:", round(sum(p.mass_kg for p in F.parts), 1))
