"""Извлечь корпус кресла из Spin.max в data/spin_cage.npz.

    python tools/extract_model.py /путь/к/Spin.max

Берётся самый крупный объект Editable Poly (обивка корпуса) — управляющая сетка
до TurboSmooth. Сглаживание выполняется при сборке (lib.geom.catmull_clark).
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.maxfile import read_editable_polys  # noqa: E402


def main(path):
    polys = read_editable_polys(path)
    V, F = max(polys, key=lambda p: len(p[0]))
    counts = np.array([len(f) for f in F], dtype=np.int32)
    flat = np.concatenate([np.asarray(f, dtype=np.int32) for f in F])
    out = Path(__file__).resolve().parents[1] / "data" / "spin_cage.npz"
    np.savez_compressed(out, V=V.astype(np.float32), counts=counts, faces=flat)
    print(f"{out}: {len(V)} вершин, {len(F)} полигонов, габарит {np.ptp(V, 0).round(1)}")


if __name__ == "__main__":
    main(sys.argv[1])
