"""Пересобрать out/eris_3d.html с новым шаблоном без пересчёта данных."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.viewer import build_html  # noqa: E402

p = Path(__file__).resolve().parents[1] / "out" / "eris_3d.html"
s = p.read_text(encoding="utf-8")
a = s.index('<script type="application/json" id="data">') + len('<script type="application/json" id="data">')
b = s.index("</script>", a)
data = json.loads(s[a:b].replace("<\\/", "</"))
p.write_text(build_html(data), encoding="utf-8")
print("ok", p)
