"""Собирает templates/viewer.html — интерактивный просмотр STL-модели и шаблонов (один файл)."""
import base64, os
import geometry as g

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

PAGE = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer_template.html"), encoding="utf-8").read()


def svg_for(part):
    x0, y0, x1, y1 = part.bbox()
    w, h = x1 - x0, y1 - y0
    pad = 0.04 * max(w, h)
    def d(verts):
        pts = g.sample(verts, 1.0)
        return "M" + "L".join("%.2f %.2f" % (x - x0, y1 - y) for x, y in pts) + "Z"
    paths = '<path class="cut" d="%s"/>' % d(part.verts)
    for hole in part.holes:
        paths += '<path class="cut" d="%s"/>' % d(hole)
    return ('<svg viewBox="%.1f %.1f %.1f %.1f" role="img" aria-label="%s">%s</svg>'
            % (-pad, -pad, w + 2 * pad, h + 2 * pad, part.title, paths)), w, h


def main():
    stl = base64.b64encode(open(os.path.join(ROOT, "source", "table_model.stl"), "rb").read()).decode()
    cards = []
    for p in g.all_parts():
        svg, w, h = svg_for(p)
        cards.append('<article class="tpl"><div class="draw">%s</div><h3>%s</h3>'
                     '<p class="meta"><span>%.1f × %.1f мм</span><span>%s</span></p></article>'
                     % (svg, p.title, w, h, p.qty))
    html = PAGE.replace("__STL_B64__", stl).replace("__TEMPLATES__", "\n".join(cards))
    out = os.path.join(ROOT, "templates", "viewer.html")
    open(out, "w", encoding="utf-8").write(html)
    print(out, len(html) // 1024, "KB")


if __name__ == "__main__":
    main()
