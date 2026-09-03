# -*- coding: utf-8 -*-
"""
Общий модуль анимации аватара.
- Грузит позы рта/глаз, выравнивает их по лицу (ECC affine на 512px).
- Умеет рендерить кадры с плавным морфингом рта и отдавать их в ffmpeg.
"""
import os
import math
import re
import subprocess

import numpy as np
import cv2
from PIL import Image
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
V = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "videos")
SIZE = 1024
FPS = 30

_VOWELS = set("аеёиоуыэюяaeiouy")


def _load_square(name):
    im = Image.open(os.path.join(V, name)).convert("RGB")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    im = im.resize((SIZE, SIZE), Image.LANCZOS)
    return np.asarray(im)


def _align(ref, im):
    """Выровнять im по ref (аффинно, ECC на 512px для скорости)."""
    ref_s = cv2.resize(ref, (512, 512))
    im_s = cv2.resize(im, (512, 512))
    refg = cv2.cvtColor(ref_s, cv2.COLOR_RGB2GRAY)
    img = cv2.cvtColor(im_s, cv2.COLOR_RGB2GRAY)
    warp = np.eye(2, 3, dtype=np.float32)
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 500, 1e-6)
    try:
        cv2.findTransformECC(refg, img, warp, cv2.MOTION_AFFINE, crit)
    except cv2.error:
        warp = np.eye(2, 3, dtype=np.float32)
    warp2 = warp.copy()
    warp2[0, 2] *= SIZE / 512.0
    warp2[1, 2] *= SIZE / 512.0
    return cv2.warpAffine(im, warp2, (SIZE, SIZE),
                          flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


# --- позы ---
_base = _load_square("avatar_source.png")
_closed = _align(_base, _load_square("eyes_closed.png"))

_MOUTH_LEVELS = [
    (_base, 0.0),
    (_align(_base, _load_square("mouth_quarter.png")), 0.30),
    (_align(_base, _load_square("mouth_mid.png")), 0.55),
    (_align(_base, _load_square("mouth_open.png")), 0.80),
    (_align(_base, _load_square("mouth_wide.png")), 1.00),
]

# кэш промежуточных уровней открытия рта (квантование 0..20)
_QSTEPS = 20
_mouth_cache = {}


def _blend_levels(o):
    for i in range(len(_MOUTH_LEVELS) - 1):
        a, la = _MOUTH_LEVELS[i]
        b, lb = _MOUTH_LEVELS[i + 1]
        if la <= o <= lb:
            f = (o - la) / (lb - la)
            return (a.astype(np.float32) * (1 - f) + b.astype(np.float32) * f).astype(np.uint8)
    return _MOUTH_LEVELS[-1][0].copy()


def mouth_image(o):
    """Полноразмерное изображение лица с ртом на уровне открытия o (0..1)."""
    o = min(1.0, max(0.0, o))
    q = int(round(o * _QSTEPS))
    if q not in _mouth_cache:
        _mouth_cache[q] = _blend_levels(q / float(_QSTEPS))
    return _mouth_cache[q]


def _crop_resize(img, zoom, dx, dy):
    s = SIZE
    cw = s / zoom
    cx = s / 2 + dx - cw / 2
    cy = s / 2 + dy - cw / 2
    cx = max(0.0, min(s - cw, cx))
    cy = max(0.0, min(s - cw, cy))
    x0, y0 = int(cx), int(cy)
    x1, y1 = int(cx + cw), int(cy + cw)
    if x1 <= x0:
        x1 = x0 + 1
    if y1 <= y0:
        y1 = y0 + 1
    crop = img[y0:y1, x0:x1]
    return cv2.resize(crop, (SIZE, SIZE), interpolation=cv2.INTER_LINEAR)


def render_video(frames, out_path, fps=FPS):
    cmd = [
        FF, "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{SIZE}x{SIZE}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path,
    ]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(f.tobytes())
    p.stdin.close()
    p.wait()
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {out_path}")


# ---------------- idle: дыхание + плавное моргание ----------------
_BLINK_EVERY = 3.0
_BLINK_LEN = 8


def gen_awaiting(dur, fps=FPS):
    n = int(dur * fps)
    for i in range(n):
        t = i / fps
        zoom = 1 + 0.02 * math.sin(2 * math.pi * t / 4.0)
        ph = (t % _BLINK_EVERY) * fps
        src = _base
        if ph < _BLINK_LEN:
            b = math.sin(math.pi * ph / _BLINK_LEN) ** 2
            if b > 0.02:
                src = (_base.astype(np.float32) * (1 - b) +
                       _closed.astype(np.float32) * b).astype(np.uint8)
        yield _crop_resize(src, zoom, 0, 0)


# ---------------- lip-sync по таймингам слов ----------------
def count_syllables(word):
    w = word.lower()
    n = 0
    prev = False
    for ch in w:
        if ch in _VOWELS:
            if not prev:
                n += 1
            prev = True
        else:
            prev = False
    return max(1, n)


def openness_envelope(words, duration, fps=FPS, tail=0.35):
    """words: [(start_s, dur_s, text), ...] -> массив открытия рта по кадрам."""
    n = int((duration + tail) * fps) + 1
    arr = np.zeros(n, dtype=np.float32)
    for (s, d, w) in words:
        nsyl = count_syllables(w)
        base_amp = 0.45 + 0.15 * min(len(w), 8) / 8.0
        for k in range(nsyl):
            ss = s + d * k / nsyl
            sl = d / nsyl
            i0 = int(ss * fps)
            i1 = int((ss + sl) * fps)
            if i1 <= i0:
                i1 = i0 + 1
            amp = min(1.0, base_amp + 0.12 * (k == 0))
            for i in range(i0, min(i1, n)):
                f = (i - i0) / float(i1 - i0)
                arr[i] = max(arr[i], amp * math.sin(math.pi * f) ** 2)
    return arr


def gen_speaking(words, duration, fps=FPS):
    env = openness_envelope(words, duration, fps)
    for i in range(len(env)):
        t = i / fps
        o = float(env[i])
        zoom = 1 + 0.02 * math.sin(2 * math.pi * t / 2.2) + 0.015 * o
        dx = 2.0 * math.sin(2 * math.pi * t / 2.0)
        dy = 3.0 * math.sin(2 * math.pi * t / 2.0) - 2.0 * o
        yield _crop_resize(mouth_image(o), zoom, dx, dy)


def get_media_duration(path):
    r = subprocess.run([FF, "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr)
    if m:
        h, mm, ss = m.groups()
        return int(h) * 3600 + int(mm) * 60 + float(ss)
    return None
