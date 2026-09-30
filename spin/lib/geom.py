"""Геометрия поверхности кресла: подразделение, сечения, симметризация."""
import numpy as np
from shapely.geometry import Polygon, LineString, Point


# ---------------------------------------------------------------- subdivision
def catmull_clark(V, F):
    """Один шаг Catmull–Clark (аналог TurboSmooth) для замкнутой сетки."""
    V = np.asarray(V, float)
    nv = len(V)
    fp = np.array([V[f].mean(0) for f in F])
    edge_id, edges, edge_faces, face_edges = {}, [], [], []
    for fi, f in enumerate(F):
        fe = []
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            key = (a, b) if a < b else (b, a)
            e = edge_id.get(key)
            if e is None:
                e = len(edges)
                edge_id[key] = e
                edges.append(key)
                edge_faces.append([])
            edge_faces[e].append(fi)
            fe.append(e)
        face_edges.append(fe)
    E = np.array(edges)
    ne = len(E)
    mid = (V[E[:, 0]] + V[E[:, 1]]) / 2
    ep = mid.copy()
    for e in range(ne):
        fs = edge_faces[e]
        if len(fs) == 2:
            ep[e] = (V[E[e, 0]] + V[E[e, 1]] + fp[fs[0]] + fp[fs[1]]) / 4
    fsum = np.zeros((nv, 3))
    fcnt = np.zeros(nv)
    for fi, f in enumerate(F):
        fsum[f] += fp[fi]
        fcnt[f] += 1
    rsum = np.zeros((nv, 3))
    rcnt = np.zeros(nv)
    np.add.at(rsum, E[:, 0], mid)
    np.add.at(rsum, E[:, 1], mid)
    np.add.at(rcnt, E[:, 0], 1)
    np.add.at(rcnt, E[:, 1], 1)
    n = rcnt[:, None]
    newv = (fsum / fcnt[:, None] + 2 * rsum / n + (n - 3) * V) / n
    V2 = np.vstack([newv, ep, fp])
    Q = []
    for fi, f in enumerate(F):
        fe = face_edges[fi]
        for j in range(len(f)):
            Q.append([f[j], nv + fe[j], nv + ne + fi, nv + fe[j - 1]])
    return V2, np.array(Q)


def triangulate(F):
    F = np.asarray(F)
    return np.vstack([F[:, [0, 1, 2]], F[:, [0, 2, 3]]])


def vertex_normals(V, T):
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, T[:, k], n)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)


# ---------------------------------------------------------------- sections
class Surface:
    """Треугольная поверхность обивки с сечениями и знаковым расстоянием."""

    def __init__(self, V, T):
        self.V = np.asarray(V, float)
        self.T = np.asarray(T)
        self._cache = {}
        self._tree = None

    def loops(self, axis, value):
        V, T = self.V, self.T
        d = V[:, axis] - value
        d = np.where(d == 0, 1e-7, d)
        dt = d[T]
        tris = T[~((dt > 0).all(1) | (dt < 0).all(1))]
        adj, pts = {}, {}
        for tri in tris:
            es = []
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                if (d[a] > 0) != (d[b] > 0):
                    k = (a, b) if a < b else (b, a)
                    if k not in pts:
                        i, j = k
                        t = d[i] / (d[i] - d[j])
                        pts[k] = V[i] + t * (V[j] - V[i])
                    es.append(k)
            if len(es) == 2:
                adj.setdefault(es[0], []).append(es[1])
                adj.setdefault(es[1], []).append(es[0])
        keep = [i for i in range(3) if i != axis]
        out, seen = [], set()
        for start in adj:
            if start in seen:
                continue
            loop, prev, cur = [start], None, start
            seen.add(start)
            while True:
                nxt = [q for q in adj[cur] if q != prev and q not in seen]
                if not nxt:
                    break
                prev, cur = cur, nxt[0]
                loop.append(cur)
                seen.add(cur)
            closed = start in adj[cur] and len(loop) > 2
            out.append((np.array([pts[k][keep] for k in loop]), closed))
        return out

    def section(self, axis, value, min_area=100.0):
        key = (axis, round(float(value), 3))
        if key in self._cache:
            return self._cache[key]
        polys = [Polygon(a).buffer(0) for a, c in self.loops(axis, value) if c and len(a) > 3]
        polys = sorted((p for p in polys if p.area > min_area), key=lambda p: -p.area)
        region = Polygon()
        for p in polys:
            region = region.symmetric_difference(p)
        self._cache[key] = region
        return region

    def plan(self, z):
        return self.section(2, z)

    def hull(self, z):
        """Наружный контур в плане на высоте z (выпуклая оболочка сечения)."""
        s = self.plan(z)
        return s.convex_hull if not s.is_empty else s

    # ---------------------------------------------------------- distances
    def _build_tree(self):
        from scipy.spatial import cKDTree
        # центры треугольников + вершины — плотная выборка поверхности
        c = self.V[self.T].mean(1)
        pts = np.vstack([self.V, c])
        nv = vertex_normals(self.V, self.T)
        fn = np.cross(self.V[self.T[:, 1]] - self.V[self.T[:, 0]],
                      self.V[self.T[:, 2]] - self.V[self.T[:, 0]])
        fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
        self._pts = pts
        self._nrm = np.vstack([nv, fn])
        self._tree = cKDTree(pts)

    def signed_distance(self, P, zstep=3.0):
        """>0 — точка внутри обивки (глубина), <0 — снаружи (выступ).
        Расстояние — до ближайшей точки поверхности; «внутри/снаружи» — по
        плановому сечению на высоте точки (надёжно и у складок обивки)."""
        from shapely import contains_xy
        if self._tree is None:
            self._build_tree()
        P = np.atleast_2d(P)
        dist, _ = self._tree.query(P)
        inside = np.zeros(len(P), bool)
        zk = np.round(P[:, 2] / zstep) * zstep
        for z in np.unique(zk):
            m = zk == z
            sec = self.plan(float(z))
            if not sec.is_empty:
                inside[m] = contains_xy(sec, P[m, 0], P[m, 1])
        return np.where(inside, dist, -dist)


# ---------------------------------------------------------------- 2D helpers
def symmetrize(poly, n=720):
    """Симметрия относительно оси x=0: усреднение радиусов r(θ) и r(π−θ).
    Годится для звёздных относительно центра контуров (наружные контуры)."""
    if poly.is_empty:
        return poly
    c = poly.centroid
    cx, cy = 0.0, c.y
    R = 5000
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    b = poly.exterior

    def radius(t):
        ray = LineString([(cx, cy), (cx + R * np.cos(t), cy + R * np.sin(t))])
        inter = ray.intersection(b)
        if inter.is_empty:
            return 0.0
        geoms = getattr(inter, "geoms", [inter])
        return max(Point(cx, cy).distance(g) if g.geom_type == "Point"
                   else max(Point(cx, cy).distance(Point(q)) for q in g.coords)
                   for g in geoms)

    r = np.array([radius(t) for t in th])
    rm = np.array([radius(np.pi - t) for t in th])
    ra = (r + rm) / 2
    return Polygon(np.c_[cx + ra * np.cos(th), cy + ra * np.sin(th)]).buffer(0)


def rounded_rect(x0, y0, x1, y1, r):
    from shapely.geometry import box
    return box(x0 + r, y0 + r, x1 - r, y1 - r).buffer(r, quad_segs=16)


def largest(geom):
    if geom.geom_type in ("MultiPolygon", "GeometryCollection"):
        polys = [g for g in geom.geoms if g.geom_type == "Polygon"]
        return max(polys, key=lambda g: g.area) if polys else Polygon()
    return geom
