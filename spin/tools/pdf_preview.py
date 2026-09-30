"""Быстрая сборка только PDF (для отладки чертежей) + PNG-превью страниц."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.frame import Frame
from lib.foam import Soft
from lib import export_cnc as X
from lib.drawings import make_pdf
import build
t = time.time()
F = Frame(); Sf = Soft(F)
summ = build.summary(F, Sf)
out = Path(__file__).resolve().parents[1] / "out"
placed, sheets = X.export_frame(F, Path(__file__).resolve().parents[1] / ".cache" / "cnc_tmp")
build.write_bom(F, Sf, summ, out / "specifikaciya.csv", sheets)
make_pdf(F, Sf, summ, placed, sheets, out / "spin_chertezhi.pdf")
print("pdf", round(time.time() - t, 1), "s")
