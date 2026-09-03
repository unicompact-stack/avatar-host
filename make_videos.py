# -*- coding: utf-8 -*-
"""
Оффлайн-перегенерация видео аватара.
- awaiting.mp4  — idle (дыхание + моргание)
- speaking.mp4  — демо-ролик lip-sync на вымышленных таймингах (для предпросмотра)
"""
import avatar_lib

V = avatar_lib.V

# idle
avatar_lib.render_video(avatar_lib.gen_awaiting(8), f"{V}/awaiting.mp4")
print("OK awaiting.mp4")

# demo speaking (8 c, вымышленные слова с паузами)
demo_words = [
    (0.3, 0.55, "Привет"),
    (1.0, 0.45, "меня"),
    (1.6, 0.75, "зовут"),
    (2.5, 0.95, "Аватар"),
    (3.9, 0.5, "и"),
    (4.5, 0.7, "сегодня"),
    (5.3, 0.9, "отличный"),
    (6.3, 0.8, "день"),
]
avatar_lib.render_video(avatar_lib.gen_speaking(demo_words, 7.4), f"{V}/speaking.mp4")
print("OK speaking.mp4")
