# -*- coding: utf-8 -*-
"""
Генератор музыки и звуковых эффектов — без внешних файлов и без интернета.

Всё синтезируется на чистом Python в WAV: фанфары, аплодисменты, барабанная
дробь, а также зацикленные фоновые треки в разных настроениях. Файлы
создаются один раз при первом запуске и кладутся в static/sound/.

Почему синтез, а не готовые mp3: любая скачанная музыка — это чужие права,
а на мероприятии это реальный риск. Здесь всё своё.
"""
import io
import math
import os
import struct
import wave

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOUND_DIR = os.path.join(BASE_DIR, "static", "sound")
os.makedirs(SOUND_DIR, exist_ok=True)

RATE = 22050

# --- ноты ---
A4 = 440.0
NOTES = {"C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4,
         "F#": -3, "G": -2, "G#": -1, "A": 0, "A#": 1, "B": 2}


def freq(note: str, octave: int = 4) -> float:
    return A4 * (2 ** ((NOTES[note] + (octave - 4) * 12) / 12))


def chord(root: str, octave: int, kind="maj"):
    """Трезвучие: тоника, терция, квинта."""
    steps = {"maj": (0, 4, 7), "min": (0, 3, 7), "maj7": (0, 4, 7, 11),
             "dom7": (0, 4, 7, 10), "sus4": (0, 5, 7)}[kind]
    base = freq(root, octave)
    return [base * (2 ** (s / 12)) for s in steps]


class Track:
    """Буфер сэмплов, в который подмешиваются ноты."""

    def __init__(self, seconds):
        self.n = int(RATE * seconds)
        self.buf = [0.0] * self.n

    def add(self, f, start, dur, amp=0.25, wave_kind="sine",
            attack=0.02, release=0.25, vibrato=0.0):
        i0 = int(start * RATE)
        length = int(dur * RATE)
        for i in range(length):
            idx = i0 + i
            if idx >= self.n or idx < 0:
                continue
            t = i / RATE
            # огибающая: атака, спад, релиз
            if t < attack:
                env = t / attack
            elif t > dur - release:
                env = max(0.0, (dur - t) / release)
            else:
                env = 1.0
            env *= env  # мягче на слух
            ff = f * (1 + vibrato * math.sin(2 * math.pi * 5.5 * t)) if vibrato else f
            ph = 2 * math.pi * ff * t
            if wave_kind == "sine":
                v = math.sin(ph)
            elif wave_kind == "tri":
                v = 2 / math.pi * math.asin(math.sin(ph))
            elif wave_kind == "saw":
                v = 2 * ((ff * t) % 1) - 1
            elif wave_kind == "brass":     # пила + октава, звучит «духовой»
                v = 0.6 * (2 * ((ff * t) % 1) - 1) + 0.4 * math.sin(2 * ph)
            elif wave_kind == "bell":
                v = math.sin(ph) + 0.5 * math.sin(2.76 * ph) + 0.25 * math.sin(5.4 * ph)
                v /= 1.75
            else:
                v = math.sin(ph)
            self.buf[idx] += v * env * amp

    def add_chord(self, notes, start, dur, amp=0.16, **kw):
        for f in notes:
            self.add(f, start, dur, amp=amp, **kw)

    def add_noise(self, start, dur, amp=0.2, decay=True, seed=1):
        """Шум — для аплодисментов и щётки барабана."""
        i0 = int(start * RATE)
        length = int(dur * RATE)
        state = seed
        for i in range(length):
            idx = i0 + i
            if idx >= self.n:
                break
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            r = (state / 0x7FFFFFFF) * 2 - 1
            env = (1 - i / length) if decay else 1.0
            self.buf[idx] += r * env * amp

    def normalize(self, peak=0.86):
        m = max((abs(v) for v in self.buf), default=0.0)
        if m > 0:
            k = peak / m
            self.buf = [v * k for v in self.buf]

    def fade_edges(self, seconds=0.05):
        """Чтобы луп не щёлкал на стыке."""
        f = int(RATE * seconds)
        for i in range(min(f, self.n)):
            k = i / f
            self.buf[i] *= k
            self.buf[self.n - 1 - i] *= k

    def save(self, path):
        self.normalize()
        data = struct.Struct("<%dh" % self.n).pack(
            *(max(-32767, min(32767, int(v * 32767))) for v in self.buf))
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(data)


# ---------------------------------------------------------------- эффекты

def make_fanfare(path):
    """Торжественные фанфары — выход юбиляра, награждение."""
    t = Track(3.2)
    mel = [("G", 4, 0.0, 0.28), ("C", 5, 0.30, 0.28), ("E", 5, 0.60, 0.28),
           ("G", 5, 0.90, 0.85), ("E", 5, 1.80, 0.22), ("G", 5, 2.05, 1.05)]
    for note, octv, st, d in mel:
        t.add(freq(note, octv), st, d, amp=0.30, wave_kind="brass", attack=0.015, release=0.12)
        t.add(freq(note, octv - 1), st, d, amp=0.14, wave_kind="brass", attack=0.015)
    t.add_chord(chord("C", 4, "maj"), 2.05, 1.10, amp=0.10, wave_kind="brass")
    t.fade_edges(0.03)
    t.save(path)


def make_applause(path):
    """Аплодисменты: много коротких хлопков + гул зала."""
    t = Track(4.0)
    state = 7
    for i in range(230):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        pos = (state / 0x7FFFFFFF) * 3.5
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        amp = 0.05 + (state / 0x7FFFFFFF) * 0.10
        t.add_noise(pos, 0.05, amp=amp, seed=state & 0xFFFF)
    t.add_noise(0.0, 3.9, amp=0.035, decay=False, seed=99)
    t.fade_edges(0.25)
    t.save(path)


def make_drumroll(path):
    """Барабанная дробь перед объявлением победителя."""
    t = Track(3.0)
    hit = 0.0
    step = 0.055
    while hit < 2.55:
        speed = 1 - (hit / 3.4)
        t.add_noise(hit, 0.05, amp=0.10 + 0.20 * (hit / 3.0), seed=int(hit * 9173) + 3)
        hit += step * (0.45 + 0.55 * speed)
    t.add_noise(2.62, 0.5, amp=0.55, seed=555)
    t.add_chord(chord("C", 4, "maj"), 2.62, 0.6, amp=0.16, wave_kind="brass")
    t.fade_edges(0.03)
    t.save(path)


def make_ding(path):
    """Мягкий колокольчик — привлечь внимание, старт конкурса."""
    t = Track(1.8)
    for f, st, d, a in [(freq("C", 6), 0.0, 1.6, 0.30), (freq("G", 6), 0.09, 1.4, 0.16)]:
        t.add(f, st, d, amp=a, wave_kind="bell", attack=0.005, release=1.2)
    t.fade_edges(0.02)
    t.save(path)


def make_wrong(path):
    """Шуточный «не угадал»."""
    t = Track(1.1)
    t.add(freq("E", 3), 0.0, 0.28, amp=0.30, wave_kind="saw", release=0.1)
    t.add(freq("D#", 3), 0.28, 0.55, amp=0.30, wave_kind="saw", release=0.3)
    t.fade_edges(0.02)
    t.save(path)


def make_tada(path):
    """Короткое «та-дам» — правильный ответ, сюрприз."""
    t = Track(1.7)
    t.add_chord(chord("C", 5, "maj"), 0.0, 0.22, amp=0.20, wave_kind="brass")
    t.add_chord(chord("G", 5, "maj"), 0.22, 1.35, amp=0.20, wave_kind="brass", release=0.7)
    t.add_noise(0.22, 0.25, amp=0.10, seed=42)
    t.fade_edges(0.02)
    t.save(path)


# ---------------------------------------------------------------- фон (лупы)

def _loop(path, prog, bpm, seconds, style):
    """Зацикленная фоновая дорожка по аккордовой прогрессии."""
    beat = 60.0 / bpm
    bar = beat * 4
    t = Track(seconds)
    pos = 0.0
    i = 0
    while pos < seconds - 0.01:
        root, octv, kind = prog[i % len(prog)]
        ch = chord(root, octv, kind)
        if style == "lounge":
            t.add_chord(ch, pos, bar * 0.96, amp=0.085, wave_kind="sine",
                        attack=0.25, release=0.7)
            t.add(ch[0] / 2, pos, beat * 0.9, amp=0.13, wave_kind="tri", release=0.3)
            t.add(ch[0] / 2, pos + beat * 2, beat * 0.9, amp=0.11, wave_kind="tri", release=0.3)
            for k, b in enumerate((0.5, 1.5, 2.5, 3.5)):
                t.add(ch[(k + 1) % len(ch)] * 2, pos + beat * b, beat * 0.4,
                      amp=0.045, wave_kind="bell", attack=0.005, release=0.35)
        elif style == "warm":
            t.add_chord(ch, pos, bar * 0.98, amp=0.10, wave_kind="tri",
                        attack=0.5, release=1.0)
            t.add(ch[0] / 2, pos, bar * 0.9, amp=0.09, wave_kind="sine", attack=0.3)
            t.add(ch[2] * 2, pos + beat * 1.5, beat * 1.2, amp=0.05,
                  wave_kind="bell", release=0.8)
        elif style == "upbeat":
            for b in range(4):
                t.add_chord(ch, pos + beat * b, beat * 0.42, amp=0.075,
                            wave_kind="tri", attack=0.01, release=0.15)
                t.add(ch[0] / 2, pos + beat * b, beat * 0.35, amp=0.14,
                      wave_kind="saw", attack=0.005, release=0.1)
                t.add_noise(pos + beat * b + beat * 0.5, 0.04, amp=0.05,
                            seed=int((pos + b) * 733) + 1)
            t.add(ch[2] * 2, pos + beat * 2.5, beat * 0.9, amp=0.06,
                  wave_kind="bell", release=0.5)
        elif style == "solemn":
            t.add_chord(ch, pos, bar * 0.99, amp=0.11, wave_kind="brass",
                        attack=0.6, release=1.2)
            t.add(ch[0] / 2, pos, bar * 0.99, amp=0.10, wave_kind="sine", attack=0.5)
        pos += bar
        i += 1
    t.fade_edges(0.12)
    t.save(path)


BACKGROUNDS = [
    {"id": "lounge", "label": "Лаунж — сбор гостей", "bpm": 84, "sec": 22.86, "style": "lounge",
     "prog": [("C", 3, "maj7"), ("A", 2, "min"), ("F", 2, "maj7"), ("G", 2, "dom7")]},
    {"id": "warm", "label": "Тёплый фон — тосты, поздравления", "bpm": 72, "sec": 26.67, "style": "warm",
     "prog": [("F", 2, "maj7"), ("C", 3, "maj"), ("D", 3, "min"), ("A", 2, "min")]},
    {"id": "upbeat", "label": "Бодрый — конкурсы, квиз", "bpm": 112, "sec": 17.14, "style": "upbeat",
     "prog": [("A", 2, "min"), ("F", 2, "maj"), ("C", 3, "maj"), ("G", 2, "maj")]},
    {"id": "solemn", "label": "Торжественный — выход, финал", "bpm": 66, "sec": 29.09, "style": "solemn",
     "prog": [("C", 3, "maj"), ("G", 2, "maj"), ("A", 2, "min"), ("F", 2, "maj")]},
]

EFFECTS = [
    {"id": "fanfare", "label": "Фанфары", "make": make_fanfare},
    {"id": "applause", "label": "Аплодисменты", "make": make_applause},
    {"id": "drumroll", "label": "Барабанная дробь", "make": make_drumroll},
    {"id": "tada", "label": "Та-дам (верно)", "make": make_tada},
    {"id": "ding", "label": "Внимание", "make": make_ding},
    {"id": "wrong", "label": "Не угадал", "make": make_wrong},
]

EFFECT_IDS = {e["id"] for e in EFFECTS}
BACKGROUND_IDS = {b["id"] for b in BACKGROUNDS}


def ensure_all(force=False):
    """Генерируем недостающие файлы. Первый запуск ~10-20 секунд."""
    created = []
    for e in EFFECTS:
        path = os.path.join(SOUND_DIR, f"fx_{e['id']}.wav")
        if force or not os.path.exists(path):
            e["make"](path)
            created.append(os.path.basename(path))
    for b in BACKGROUNDS:
        path = os.path.join(SOUND_DIR, f"bg_{b['id']}.wav")
        if force or not os.path.exists(path):
            _loop(path, b["prog"], b["bpm"], b["sec"], b["style"])
            created.append(os.path.basename(path))
    return created


def catalog():
    return {
        "effects": [{"id": e["id"], "label": e["label"],
                     "url": f"/static/sound/fx_{e['id']}.wav"} for e in EFFECTS],
        "backgrounds": [{"id": b["id"], "label": b["label"],
                         "url": f"/static/sound/bg_{b['id']}.wav"} for b in BACKGROUNDS],
    }
