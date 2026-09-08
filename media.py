# -*- coding: utf-8 -*-
"""
Медиатека: картинки, PDF-презентации и празднования на экране.

Идея из ТЗ: админ выбрал файл — он сразу на экране. Аватар при этом можно
скрыть (голос продолжает звучать), а на конкурсах вместо ведущего показать
салют. Никакой синхронизации состояний ведущего — просто слои поверх сцены.
"""
import os
import re
import time
import unicodedata

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "static", "media")
os.makedirs(MEDIA_DIR, exist_ok=True)

# Постоянные слайды, которые едут вместе с репозиторием (в отличие от
# static/media, куда ведущий загружает свои файлы и которая в .gitignore).
BUNDLED_DIR = os.path.join(BASE_DIR, "scenarios", "media")


def sync_bundled():
    """Копируем комплектные слайды в медиатеку, если их там ещё нет."""
    import shutil
    if not os.path.isdir(BUNDLED_DIR):
        return []
    copied = []
    for name in sorted(os.listdir(BUNDLED_DIR)):
        if name.startswith(".") or os.path.splitext(name)[1].lower() not in ALLOWED:
            continue
        dst = os.path.join(MEDIA_DIR, name)
        if not os.path.exists(dst):
            shutil.copy2(os.path.join(BUNDLED_DIR, name), dst)
            copied.append(name)
    return copied

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
DOC_EXT = {".pdf"}
ALLOWED = IMAGE_EXT | DOC_EXT
MAX_BYTES = 25 * 1024 * 1024

# Празднования — рисуются на фронте, файлы не нужны
CELEBRATIONS = [
    {"id": "fireworks", "label": "Салют"},
    {"id": "confetti", "label": "Конфетти"},
    {"id": "applause", "label": "Аплодисменты"},
    {"id": "stars", "label": "Звёзды"},
]
CELEBRATION_IDS = {c["id"] for c in CELEBRATIONS}

# Режимы сцены
STAGE_MODES = ("avatar", "media", "celebration", "black")


def safe_name(name: str) -> str:
    """Безопасное имя файла с сохранением кириллицы."""
    name = unicodedata.normalize("NFC", os.path.basename(name or "")).strip()
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    stem = re.sub(r"[^\w\s.-]", "", stem, flags=re.UNICODE).strip() or "файл"
    stem = re.sub(r"\s+", "_", stem)[:80]
    return stem + ext


def kind_of(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in DOC_EXT:
        return "doc"
    return "other"


def validate(filename: str, size: int):
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED:
        return f"Формат {ext or '—'} не поддерживается. Можно: {', '.join(sorted(ALLOWED))}"
    if size > MAX_BYTES:
        return f"Файл больше {MAX_BYTES // 1024 // 1024} МБ"
    return None


def save(storage) -> dict:
    """Сохраняет загруженный файл, при совпадении имени добавляет суффикс."""
    name = safe_name(storage.filename)
    stem, ext = os.path.splitext(name)
    path = os.path.join(MEDIA_DIR, name)
    i = 2
    while os.path.exists(path):
        name = f"{stem}_{i}{ext}"
        path = os.path.join(MEDIA_DIR, name)
        i += 1
    storage.save(path)
    return info(name)


def info(name: str):
    path = os.path.join(MEDIA_DIR, name)
    if not os.path.isfile(path):
        return None
    return {
        "name": name,
        "url": f"/static/media/{name}",
        "kind": kind_of(name),
        "size": os.path.getsize(path),
        "at": os.path.getmtime(path),
    }


def listing():
    items = []
    for name in os.listdir(MEDIA_DIR):
        if name.startswith("."):
            continue
        it = info(name)
        if it:
            items.append(it)
    items.sort(key=lambda i: -i["at"])
    return items


def delete(name: str) -> bool:
    name = safe_name(name)
    path = os.path.join(MEDIA_DIR, name)
    # защита от выхода за пределы папки
    if os.path.commonpath([os.path.abspath(path), MEDIA_DIR]) != MEDIA_DIR:
        return False
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False
