# -*- coding: utf-8 -*-
"""Своя музыка (папка с файлами) и интернет-радио.

Три источника фоновой музыки, все живут в одном пространстве id:

    gen:lounge          — синтезированный трек из audio_lib (был раньше)
    file:трек.mp3       — файл из папки music/
    radio:retro         — интернет-радиостанция

Голый id без префикса считается синтезированным — так продолжают работать
старые сценарии, где написано просто "bg": "lounge".
"""
import os
import urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = os.path.join(BASE, "music")

# Что умеет играть браузер. mp3 и m4a — самые надёжные.
EXTS = {".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".flac", ".webm"}

README = """\
Сюда складывайте свою музыку — mp3, m4a, ogg, wav, flac.

Файлы появятся в пульте ведущего в списке «Фоновая музыка» сразу после
кнопки «Обновить список» — перезапускать программу не нужно.

Как назовёте файл, так он и будет называться в списке, поэтому имя вроде
«01 - Track 01.mp3» лучше переименовать в «Лаунж — сбор гостей.mp3».

Можно раскладывать по подпапкам, например:
    music/Сбор гостей/...
    music/Танцы/...
Подпапка станет группой в списке.
"""

# --------------------------------------------------------------- радио
#
# Только потоки по https — страница пульта открывается по https, а браузер
# блокирует http-поток внутри https-страницы («смешанное содержимое»).
RADIO = [
    {"id": "retro",     "label": "Ретро FM",              "genre": "Хиты 70–90-х",
     "url": "https://retro.hostingradio.ru:8043/retro256.mp3"},
    {"id": "montecarlo", "label": "Радио Монте-Карло",    "genre": "Лаунж, спокойное",
     "url": "https://montecarlo.hostingradio.ru/montecarlo128.mp3"},
    {"id": "energy",    "label": "Energy (NRJ)",          "genre": "Танцевальное",
     "url": "https://pub0301.101.ru:8443/stream/air/aac/64/99"},
    {"id": "dorojnoe",  "label": "Дорожное радио",        "genre": "Русские хиты",
     "url": "https://dorognoe.hostingradio.ru/dorognoe"},
    {"id": "shanson",   "label": "Радио Шансон",          "genre": "Шансон",
     "url": "https://chanson.hostingradio.ru:8041/chanson256.mp3"},
    {"id": "avtoradio", "label": "Авторадио",             "genre": "Популярное",
     "url": "https://pub0201.101.ru:8443/stream/air/aac/64/102"},
    {"id": "europaplus", "label": "Европа Плюс",          "genre": "Поп, свежее",
     "url": "https://ep128.hostingradio.ru:8030/ep128"},
    {"id": "russkoe",   "label": "Русское радио",         "genre": "Русская эстрада",
     "url": "https://rusradio.hostingradio.ru/rusradio128.mp3"},
    {"id": "jazz",      "label": "Радио Jazz",            "genre": "Джаз, фон под тосты",
     "url": "https://nashe1.hostingradio.ru/jazz-128.mp3"},
    {"id": "relax",     "label": "Радио Рекорд — Chill",  "genre": "Спокойный электронный",
     "url": "https://radiorecord.hostingradio.ru/chil96.aacp"},
    {"id": "nashe",     "label": "Наше радио",            "genre": "Русский рок",
     "url": "https://nashe1.hostingradio.ru/nashe-128.mp3"},
    {"id": "vesna",     "label": "Весна FM",              "genre": "Лёгкое, для танцев",
     "url": "https://vesna.hostingradio.ru/vesnafm128.mp3"},
    {"id": "hitfm",     "label": "Хит FM",                "genre": "Только хиты",
     "url": "https://hitfm.hostingradio.ru/hitfm96.aacp"},
    {"id": "love",      "label": "Love Radio",            "genre": "Медленное, романтичное",
     "url": "https://loveradio.hostingradio.ru:8000/loveradio128.mp3"},
]

RADIO_BY_ID = {r["id"]: r for r in RADIO}


def ensure_dir():
    """Создаёт папку music/ и кладёт туда подсказку, если её ещё нет."""
    os.makedirs(MUSIC_DIR, exist_ok=True)
    hint = os.path.join(MUSIC_DIR, "ПРОЧТИ-МЕНЯ.txt")
    if not os.path.exists(hint):
        try:
            with open(hint, "w", encoding="utf-8") as f:
                f.write(README)
        except OSError:
            pass


def _safe(rel):
    """Не выпускаем путь за пределы music/ (защита от «../../etc/passwd»)."""
    full = os.path.normpath(os.path.join(MUSIC_DIR, rel))
    root = os.path.normpath(MUSIC_DIR)
    return full if full == root or full.startswith(root + os.sep) else None


def scan():
    """Список своих треков. Пустой список — значит папка пуста."""
    ensure_dir()
    out = []
    for root, dirs, files in os.walk(MUSIC_DIR):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.startswith("."):
                continue
            if os.path.splitext(name)[1].lower() not in EXTS:
                continue
            rel = os.path.relpath(os.path.join(root, name), MUSIC_DIR)
            rel = rel.replace(os.sep, "/")
            group = os.path.dirname(rel) or ""
            try:
                size = os.path.getsize(os.path.join(root, name))
            except OSError:
                size = 0
            out.append({
                "id": "file:" + rel,
                "label": os.path.splitext(os.path.basename(rel))[0],
                "group": group,
                "size_mb": round(size / 1024 / 1024, 1),
                "url": "/music/" + urllib.parse.quote(rel),
            })
    return out


def file_path(rel):
    """Абсолютный путь к своему треку или None, если такого файла нет."""
    if not rel:
        return None
    full = _safe(rel)
    if full and os.path.isfile(full):
        return full
    return None


def radio_list():
    return [{"id": "radio:" + r["id"], "label": r["label"],
             "genre": r["genre"], "url": r["url"]} for r in RADIO]


def resolve(bg_id):
    """По id фона возвращает, что и откуда играть.

    Возвращает (kind, url, label, error):
      kind  — 'gen' | 'file' | 'radio'
      error — текст проблемы, если играть нечего (файл удалили и т.п.)
    """
    if not bg_id:
        return None, None, "", None

    if bg_id.startswith("file:"):
        rel = bg_id[5:]
        if not file_path(rel):
            return "file", None, rel, f"Файл «{rel}» не найден в папке music/"
        return ("file", "/music/" + urllib.parse.quote(rel),
                os.path.splitext(os.path.basename(rel))[0], None)

    if bg_id.startswith("radio:"):
        st = RADIO_BY_ID.get(bg_id[6:])
        if not st:
            return "radio", None, bg_id[6:], "Такой радиостанции нет в списке"
        return "radio", st["url"], st["label"], None

    # голый id или gen:xxx — синтезированный трек
    gen = bg_id[4:] if bg_id.startswith("gen:") else bg_id
    return "gen", f"/static/sound/bg_{gen}.wav", gen, None


def status():
    """Короткая сводка для пульта: есть ли своя музыка."""
    ensure_dir()
    tracks = scan()
    return {
        "dir": MUSIC_DIR,
        "count": len(tracks),
        "empty": not tracks,
        "hint": ("Папка music/ пуста. Скопируйте туда свои mp3 — "
                 "и нажмите «Обновить список»."),
    }
