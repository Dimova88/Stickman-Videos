"""Render every pose in the library to one sheet, for eyeballing anatomy."""
from __future__ import annotations

import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from PIL import Image, ImageDraw  # noqa: E402

from fight.draw import Canvas, Cam, draw_figure  # noqa: E402
from fight.poses import LIBRARY, to_pose  # noqa: E402

W, H = 260, 330
GROUND = 300.0


def sheet(names=None, out="/tmp/poses.png", cols=7):
    names = names or list(LIBRARY)
    rows = (len(names) + cols - 1) // cols
    img = Image.new("RGB", (W * cols, H * rows), (248, 248, 246))
    d = ImageDraw.Draw(img)
    for i, name in enumerate(names):
        cv = Canvas(W, H, Cam(130, 215, 1.55))
        draw_figure(cv, to_pose(LIBRARY[name], 130, GROUND), accent=(186, 54, 50))
        cv.flush()
        img.paste(cv.img, ((i % cols) * W, (i // cols) * H))
        d.text(((i % cols) * W + 6, (i // cols) * H + 4), name, fill=(90, 90, 90))
    img.save(out)
    print(out)


if __name__ == "__main__":
    names = sys.argv[1].split(",") if len(sys.argv) > 1 else None
    sheet(names)
