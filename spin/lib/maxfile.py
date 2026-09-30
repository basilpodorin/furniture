"""Минимальный читатель файлов 3ds Max (.max) — только геометрия Editable Poly.

Формат .max — это OLE-контейнер; поток "Scene" состоит из вложенных чанков
(uint16 тип, uint32/uint64 размер, старший бит размера = контейнер).
Для объектов Editable Poly (класс 0x1bf8338d/0x192f6098) внутри чанка 0x08FE:
  0x0100 — вершины: uint32 N, далее N × (uint32 флаги, float32 x, y, z)
  0x011A — полигоны: uint32 N, далее для каждого полигона
           uint32 k, k × uint32 индексов, uint16 флаги и необязательные поля
           (0x01: uint32, 0x08: uint16, 0x10: uint32 группа сглаживания,
            0x20: 2·(k−3) × uint32 — диагонали триангуляции).
Трансформации узлов не читаются — объект берётся в локальных координатах.
"""
import struct
import zlib

import numpy as np
import olefile


class Chunk:
    __slots__ = ("type", "children", "data")

    def __init__(self, t):
        self.type = t
        self.children = None
        self.data = None


def parse_chunks(data):
    off, out, n = 0, [], len(data)
    while off + 6 <= n:
        t, siz = struct.unpack_from("<HI", data, off)
        hdr = 6
        if siz == 0:
            siz, = struct.unpack_from("<Q", data, off + 6)
            hdr = 14
            cont = bool(siz & 0x8000000000000000)
            siz &= 0x7FFFFFFFFFFFFFFF
        else:
            cont = bool(siz & 0x80000000)
            siz &= 0x7FFFFFFF
        if siz < hdr or off + siz > n:
            raise ValueError(f"повреждённый чанк 0x{t:04X} по смещению {off}")
        body = data[off + hdr: off + siz]
        c = Chunk(t)
        if cont:
            c.children = parse_chunks(body)
        else:
            c.data = body
        out.append(c)
        off += siz
    return out


def _stream(ole, name):
    d = ole.openstream(name).read()
    if d[:2] in (b"\x78\x9c", b"\x78\xda", b"\x78\x01"):
        d = zlib.decompress(d)
    return d


def _verts(d):
    n, = struct.unpack_from("<I", d)
    return np.frombuffer(d[4:4 + 16 * n], dtype="<f4").reshape(n, 4)[:, 1:].astype(float)


def _faces(d):
    n, = struct.unpack_from("<I", d)
    off, faces = 4, []
    for _ in range(n):
        k, = struct.unpack_from("<I", d, off)
        off += 4
        faces.append(list(struct.unpack_from("<%dI" % k, d, off)))
        off += 4 * k
        fl, = struct.unpack_from("<H", d, off)
        off += 2
        if fl & 0x01:
            off += 4
        if fl & 0x08:
            off += 2
        if fl & 0x10:
            off += 4
        if fl & 0x20:
            off += 8 * (k - 3)
        if fl & ~0x3F:
            raise ValueError("неизвестный флаг полигона 0x%X" % fl)
    if off != len(d):
        raise ValueError("полигоны прочитаны не полностью")
    return faces


def read_editable_polys(path):
    """Список (vertices Nx3, faces[list[int]]) всех Editable Poly в сцене."""
    ole = olefile.OleFileIO(path)
    scene = parse_chunks(_stream(ole, "Scene"))
    result = []
    for obj in scene[0].children:
        for p in obj.children or ():
            if p.type == 0x08FE and p.children:
                ch = {x.type: x for x in p.children}
                if 0x0100 in ch and 0x011A in ch:
                    result.append((_verts(ch[0x0100].data), _faces(ch[0x011A].data)))
    return result
