"""3D-экспорт: STEP сборки каркаса (CadQuery/OCC), STL поверхности обивки,
JSON для веб-просмотрщика."""
import base64
from pathlib import Path

import numpy as np

import params as P


# ------------------------------------------------------------------ размещение деталей
def placements(part):
    """Список (origin, direction, mirror) для всех экземпляров детали."""
    if part.kind == "plate":
        return [None]
    if part.instances:
        out = []
        for (ox, oy), (dx, dy) in part.instances:
            out += [((ox, oy), (dx, dy), False), ((-ox, oy), (-dx, dy), True)]
        return out
    ox, oy = part.origin
    dx, dy = part.direction
    if part.code == "ПГ1":
        return [((ox, oy), (dx, dy), False), ((-ox, oy), (dx, dy), False)]
    if part.qty == 2:
        return [((ox, oy), (dx, dy), False), ((-ox, oy), (-dx, dy), True)]
    return [((ox, oy), (dx, dy), False)]


def rib_matrix(origin, direction):
    """Матрица 3×4: локальные (u, z, n) → мировые (x, y, z); собственное вращение (det=+1)."""
    ox, oy = origin
    dx, dy = direction
    nx, ny = dy, -dx
    return np.array([[dx, 0, nx, ox],
                     [dy, 0, ny, oy],
                     [0, 1, 0, 0]], float)


# ------------------------------------------------------------------ STEP
def export_step(frame, path: Path):
    import cadquery as cq

    def solid_from(poly, t):
        def wire(coords):
            pts = [(float(x), float(y)) for x, y in coords[:-1]]
            return cq.Wire.makePolygon([cq.Vector(x, y, 0) for x, y in pts], close=True)
        outer = wire(list(poly.exterior.coords))
        inners = [wire(list(r.coords)) for r in poly.interiors]
        face = cq.Face.makeFromWires(outer, inners)
        return cq.Solid.extrudeLinear(face, cq.Vector(0, 0, t))

    assy = cq.Assembly(name="SPIN_karkas")
    colors = {"П": (0.85, 0.72, 0.52), "Р": (0.80, 0.62, 0.40), "ПГ": (0.72, 0.55, 0.36)}
    for part in frame.parts:
        base = solid_from(part.shape.simplify(1.0, preserve_topology=True), part.thickness)
        for k, pl in enumerate(placements(part)):
            if pl is None:
                s = base.translate(cq.Vector(0, 0, part.z0))
            else:
                (ox, oy), (dx, dy), _ = pl
                ln = float(np.hypot(dx, dy))
                dx, dy = dx / ln, dy / ln
                t = part.thickness
                nx, ny = dy, -dx
                # плоскость ребра: X — вдоль u, нормаль — толщина (симметрично ±t/2)
                plane = cq.Plane(origin=(ox - nx * t / 2, oy - ny * t / 2, 0),
                                 xDir=(dx, dy, 0), normal=(nx, ny, 0))
                s = base.moved(cq.Location(plane))
            key = "ПГ" if part.code.startswith("ПГ") else part.code[0]
            name = part.code + (f"_{k + 1}" if k else "")
            assy.add(s, name=name, color=cq.Color(*colors.get(key, (0.8, 0.7, 0.5))))
    # основание и механизм
    disc = cq.Workplane("XY").circle(P.DISC_D / 2).extrude(P.DISC_T).translate((0, 0, P.PAD_H))
    assy.add(disc, name="Disk_osnovaniya", color=cq.Color(0.15, 0.15, 0.15))
    a = P.SWIVEL_SIZE
    sw = cq.Workplane("XY").rect(a, a).extrude(3).translate((0, 0, P.PAD_H + P.DISC_T))
    sw = sw.union(cq.Workplane("XY").circle(a * 0.42).extrude(P.SWIVEL_H - 6)
                  .translate((0, 0, P.PAD_H + P.DISC_T + 3)))
    sw = sw.union(cq.Workplane("XY").rect(a, a).extrude(3)
                  .translate((0, 0, P.Z_P1 - 3)))
    assy.add(sw, name="Povorotnyy_mekhanizm", color=cq.Color(0.1, 0.1, 0.1))
    path.parent.mkdir(parents=True, exist_ok=True)
    assy.export(str(path), exportType="STEP")


# ------------------------------------------------------------------ STL поверхности
def export_stl(surface, path: Path):
    V, T = surface.V, surface.T
    tri = V[T]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(T), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"] = n
    rec["v"] = tri
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"SPIN upholstery surface, mm".ljust(80, b" "))
        f.write(np.uint32(len(T)).tobytes())
        f.write(rec.tobytes())


# ------------------------------------------------------------------ данные для просмотрщика
def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


def viewer_data(frame, soft, cage_level_mesh):
    V, Q = cage_level_mesh
    Vq = np.round(V).astype("<i2")
    T = np.vstack([Q[:, [0, 1, 2]], Q[:, [0, 2, 3]]]).astype("<u2" if len(V) < 65535 else "<u4")
    parts = []
    for p in frame.parts:
        g = p.shape
        inst = []
        for pl in placements(p):
            inst.append(None if pl is None else dict(m=rib_matrix(pl[0], pl[1]).round(5).tolist()))
        parts.append(dict(code=p.code, name=p.name, kind=p.kind, t=p.thickness, z0=p.z0,
                          outer=np.round(np.array(g.exterior.coords), 1).tolist(),
                          holes=[np.round(np.array(r.coords), 1).tolist() for r in g.interiors],
                          inst=inst))
    foam = []
    sp = soft.seat_profile
    foam.append(dict(code="С", name="Сиденье (С1+С2+С3)", kind="yz", x0=-soft.seat_half_w,
                     x1=soft.seat_half_w, outer=np.round(np.array(sp.exterior.coords), 1).tolist()))
    zt = P.Z_P4 + P.PLY
    for f in soft.pieces:
        if f.code in ("В1", "В2"):
            z0 = zt + (0 if f.code == "В1" else 50)
            foam.append(dict(code=f.code, name=f.name, kind="xy", z0=z0, t=50,
                             outer=np.round(np.array(f.pattern.exterior.coords), 1).tolist()))
    # подлокотники (внутр. поролон) и спинка — упрощённые плиты
    # поролон подлокотника изнутри: профиль по обшивке ОП (+ заход 40 на торец), в пределах обивки
    from shapely.geometry import Polygon as _Poly, box as _box
    from .foam import WRAP
    from .frame import S as _S
    zt, z4 = P.Z_P3 + P.PLY, P.Z_P4 + P.PLY
    xm = P.ARM_SKIN_X - 20
    sec = _S.section(0, xm).buffer(-WRAP)
    front = [(y - 40, z) for y, z in frame.skin_front]
    y_back = P.BACK_BELT_Y0 - P.CAVITY_R + 20
    zone = _Poly(front + [(y_back, z4), (y_back, zt)]).buffer(0)
    arm = sec.intersection(zone).intersection(_box(-600, zt, y_back, z4))
    arm = max(getattr(arm, "geoms", [arm]), key=lambda g: g.area)
    for sx in (-1, 1):
        a, b = sx * (P.ARM_SKIN_X - 40), sx * P.ARM_SKIN_X
        foam.append(dict(code="Пл1", name="Подлокотник внутр. (Пл1)", kind="yz", x0=min(a, b),
                         x1=max(a, b), outer=np.round(np.array(arm.exterior.coords), 1).tolist()))
    bp = soft.back_profile
    wback = P.ARM_SKIN_X - P.CAVITY_R
    foam.append(outer_foam_mesh(V, Q))
    foam.append(dict(code="Сп", name="Спинка (Сп1+Сп2)", kind="yz", x0=-wback, x1=wback,
                     outer=np.round(np.array(bp.exterior.coords), 1).tolist()))
    data_belts = belt_ribbons(frame, soft)
    data = dict(
        surface=dict(v=b64(Vq), i=b64(T), itype=str(T.dtype)),
        parts=parts, foam=foam, belts=data_belts,
        params=dict(DISC_D=P.DISC_D, DISC_T=P.DISC_T, PAD_H=P.PAD_H, SW=P.SWIVEL_SIZE,
                    SWH=P.SWIVEL_H, Z_P1=P.Z_P1, Z_P3=P.Z_P3, Z_P4=P.Z_P4, PLY=P.PLY,
                    ARM_SKIN_X=P.ARM_SKIN_X, BACK_BELT_Y0=P.BACK_BELT_Y0,
                    BACK_BELT_Y1=P.BACK_BELT_Y1, SEAT_OPEN_X=P.SEAT_OPEN_X,
                    BACK_PART_Y=P.BACK_PART_Y, Z_SEAT_BACK=P.Z_SEAT_BACK,
                    front_rail_in=frame.front_rail_in, CAVITY_R=P.CAVITY_R))
    return data


def outer_foam_mesh(V, Q):
    """Наружный поролон стенок (Н1, Н2 и завороты под дно): поверхность обивки, смещённая
    внутрь на толщину обёртки, без зон сиденья, спинки, подлокотников изнутри и валика."""
    from .foam import WRAP
    from .geom import triangulate, vertex_normals
    T = triangulate(Q)
    n = vertex_normals(V, T)
    c = V.mean(0)
    if np.einsum("ij,ij->i", n, V - c).mean() < 0:
        n = -n
    W = V - n * WRAP
    cen = W[T].mean(1)
    zt = P.Z_P3 + P.PLY
    x, y, z = cen[:, 0], cen[:, 1], cen[:, 2]
    in_cavity = (np.abs(x) < P.ARM_SKIN_X) & (y < P.BACK_BELT_Y1 + 10) & (z > zt - 5)
    on_top = z > P.Z_P4 + P.PLY
    keep = ~(in_cavity | on_top)
    T = T[keep]
    used = np.unique(T)
    remap = -np.ones(len(W), int)
    remap[used] = np.arange(len(used))
    Wq = np.round(W[used]).astype("<i2")
    Ti = remap[T].astype("<u2" if len(used) < 65535 else "<u4")
    return dict(code="Н", name="Наружные стенки Н1, Н2 (ST 2536, 40 мм)", kind="mesh",
                v=b64(Wq), i=b64(Ti), itype=str(Ti.dtype))


def belt_ribbons(frame, soft):
    """Ремни как отрезки (a, b) шириной 50 мм с направлением ширины w."""
    from shapely.geometry import LineString, box
    from .geom import rounded_rect
    from .frame import back_belt_y
    zt = P.Z_P3 + P.PLY
    out = []
    ya, yb = frame.front_rail_in - 50, P.BACK_PART_Y + P.PLY / 2
    zb = P.Z_SEAT_BACK

    def zseat(y):
        if y <= frame.front_rail_in:
            return zt
        t = (y - frame.front_rail_in) / (yb - frame.front_rail_in)
        return zt + t * (zb - zt)
    for x in np.arange(-200, 201, 100):
        out.append(dict(a=[float(x), ya, zt + 1], b=[float(x), yb, zb + 1], w=[1, 0, 0]))
    for y in (-150.0, -20.0):
        z = zseat(y) + 3
        out.append(dict(a=[-P.SEAT_OPEN_X - 40, y, z], b=[P.SEAT_OPEN_X + 40, y, z], w=[0, 1, 0]))
    z0, z1 = zt, P.Z_P4 + P.PLY

    def curve(z):
        yb_ = back_belt_y(z)
        c = rounded_rect(-P.ARM_SKIN_X, -2000, P.ARM_SKIN_X, yb_, P.CAVITY_R)
        ring = LineString(c.exterior.coords).intersection(box(-2000, yb_ - P.CAVITY_R - 20, 2000, 2000))
        pts = np.array(ring.coords)
        if pts[0, 0] > pts[-1, 0]:
            pts = pts[::-1]
        return LineString(pts)
    cb, ct = curve(z0), curve(z1)
    n = soft.info["belts"]["back"]
    for k in range(n):
        s = cb.length / 2 + (k - (n - 1) / 2) * 100
        pb = cb.interpolate(s)
        pt = ct.interpolate(ct.length / 2 + (k - (n - 1) / 2) * 100)
        q1, q2 = cb.interpolate(s - 5), cb.interpolate(s + 5)
        tx, ty = q2.x - q1.x, q2.y - q1.y
        ln = float(np.hypot(tx, ty))
        out.append(dict(a=[pb.x, pb.y, z0 + 1], b=[pt.x, pt.y, z1 + 1], w=[tx / ln, ty / ln, 0]))
    return out
