"""Render the plugin's LEDs page to an SVG, with demo levels on each channel.

    python3 tools/preview.py [out.svg] [--channels 8] [--scheme "..."] [--shape Square]

Uses the real plugin code (design-time layout + runtime metering) through the
mock in test/qsys_mock.py, so the picture matches what the plugin produces.
"""
import argparse
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "test"))
from qsys_mock import Plugin  # noqa: E402

DEMO = [-100, -70, -58, -44, -24, -12, -4, 0, -40, -18, -6, -1]


def rgb(t):
    v = list(t.values())
    return f"rgb({v[0]},{v[1]},{v[2]})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="preview.svg")
    ap.add_argument("--channels", type=int, default=8)
    ap.add_argument("--shape", default="Round")
    ap.add_argument("--scheme", default="Blue to Red")
    a = ap.parse_args()

    p = Plugin()
    opts = dict(Channels=a.channels, Color_Scheme=a.scheme, LED_Shape=a.shape)
    layout, graphics = p.layout(p.props(**opts))

    c = p.boot(**opts)
    for ch in range(1, a.channels + 1):
        db = DEMO[(ch - 1) % len(DEMO)]
        c[f"level_{ch}"].Value = db
        c[f"name_{ch}"].String = "off" if db <= -100 else f"{db:+d} dB" if db else "0 dB"
    p.tick()

    box = graphics[0]
    w, h = box.Size[1], box.Size[2]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w * 2}" height="{h * 2}" '
           f'viewBox="0 0 {w} {h}" font-family="Arial, sans-serif">']
    for g in graphics:
        x, y = g.Position[1], g.Position[2]
        gw, gh = g.Size[1], g.Size[2]
        if g.Type == "GroupBox":
            out.append(f'<rect x="{x}" y="{y}" width="{gw}" height="{gh}" '
                       f'rx="{g.CornerRadius or 0}" fill="{rgb(g.Fill)}"/>')
        elif g.Type == "Text":
            anchor = {"Right": "end", "Center": "middle"}.get(g.HTextAlign, "start")
            tx = x + gw if anchor == "end" else x + gw / 2 if anchor == "middle" else x
            out.append(f'<text x="{tx}" y="{y + gh / 2}" dominant-baseline="middle" '
                       f'text-anchor="{anchor}" font-size="{g.FontSize}" '
                       f'fill="{rgb(g.Color) if g.Color else "#ccc"}">{escape(g.Text)}</text>')
    for name, l in layout.items():
        x, y = l.Position[1], l.Position[2]
        lw, lh = l.Size[1], l.Size[2]
        if l.Style == "Led":
            fill = c[name].Color if c[name].Boolean else rgb(l.OffColor)
            out.append(f'<rect x="{x}" y="{y}" width="{lw}" height="{lh}" rx="{l.CornerRadius}" '
                       f'fill="{fill}" stroke="{rgb(l.StrokeColor)}" stroke-width="{l.StrokeWidth}"/>')
        elif l.Style == "Text":
            out.append(f'<rect x="{x}" y="{y}" width="{lw}" height="{lh}" rx="2" fill="{rgb(l.Color)}"/>')
            out.append(f'<text x="{x + lw / 2}" y="{y + lh / 2}" dominant-baseline="middle" '
                       f'text-anchor="middle" font-size="{l.FontSize}" fill="{rgb(l.TextColor)}">'
                       f'{escape(c[name].String)}</text>')
    out.append("</svg>")
    Path(a.out).write_text("\n".join(out))
    print(f"wrote {a.out} ({w}x{h})")


if __name__ == "__main__":
    main()
