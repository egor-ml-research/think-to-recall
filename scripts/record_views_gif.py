"""Record the README GIF of the viewer: «Live memory» (trees, pulses of a replayed call log), then Cosmos.

    python scripts/record_views_gif.py PAGE_URL OUT.gif [--lang en|ru]

Needs `playwright` and `Pillow` (a scratch venv is fine) and Microsoft Edge or Chrome installed: Playwright drives the
installed browser (channel msedge / chrome), nothing is downloaded. The page must be served over http (the demo HTML
from scripts/demo_views.py, e.g. `python -m http.server` in its folder). Frames are taken in real time.
"""

from __future__ import annotations

import argparse
import io
import time

from PIL import Image
from playwright.sync_api import sync_playwright

W, H, FPS, SCALE = 1100, 620, 12, 0.72


def grab(page, secs: float, frames: list, durs: list) -> None:
    """Frames as the page renders them (CDP screencast), resampled to FPS."""
    import base64

    cdp = page.context.new_cdp_session(page)
    got: list = []

    def on(ev):
        got.append((ev["metadata"].get("timestamp", time.time()), ev["data"]))
        cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})

    cdp.on("Page.screencastFrame", on)
    cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 85, "maxWidth": W, "maxHeight": H, "everyNthFrame": 1})
    page.wait_for_timeout(int(secs * 1000))
    cdp.send("Page.stopScreencast")
    if not got:
        return
    t0, step, k = got[0][0], 1 / FPS, 0
    for i in range(int(secs * FPS)):  # the latest frame at each tick of a steady clock
        t = t0 + i * step
        while k + 1 < len(got) and got[k + 1][0] <= t:
            k += 1
        frames.append(Image.open(io.BytesIO(base64.b64decode(got[k][1]))).convert("RGB"))
        durs.append(int(1000 / FPS))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--lang", default="en")
    a = ap.parse_args()
    frames: list = []
    durs: list = []
    with sync_playwright() as p:
        b = None
        for ch in ("msedge", "chrome"):
            try:
                b = p.chromium.launch(channel=ch, headless=True, args=["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"])
                break
            except Exception:  # noqa: BLE001 - try the next installed browser
                continue
        page = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        sep = "&" if "?" in a.url else "?"
        page.goto(f"{a.url}{sep}lang={a.lang}")
        page.wait_for_timeout(1500)
        page.evaluate("setMode('live'); document.querySelector('#fSpd').value = '4'; document.querySelector('#fRe').click();")
        page.wait_for_timeout(700)
        grab(page, 9.5, frames, durs)
        page.evaluate("setMode('cosmos')")
        page.wait_for_timeout(600)
        grab(page, 5.0, frames, durs)
        b.close()
    # smaller frames and one palette for the whole GIF (built from a few frames): a few MB instead of tens
    small = [f.resize((int(W * SCALE), int(H * SCALE)), Image.LANCZOS) for f in frames]
    strip = Image.new("RGB", (small[0].width, small[0].height * 4))
    for i, f in enumerate(small[:: max(1, len(small) // 4)][:4]):
        strip.paste(f, (0, i * f.height))
    pal0 = strip.quantize(colors=128, method=Image.Quantize.FASTOCTREE)
    pal = [f.quantize(palette=pal0, dither=Image.Dither.NONE) for f in small]
    pal[0].save(a.out, save_all=True, append_images=pal[1:], duration=durs, loop=0, optimize=True, disposal=1)
    print(a.out, len(frames), "frames")


if __name__ == "__main__":
    main()
