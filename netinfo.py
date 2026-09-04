# -*- coding: utf-8 -*-
"""
Сетевые адреса: по какому URL к нам придут гости с телефонов.

Задача — не угадать «правильный» IP, а показать ведущему все варианты,
чтобы он выбрал тот, что видят телефоны в зале.
"""
import socket


def primary_ip():
    """IP, который система выберет для выхода наружу — обычно это Wi-Fi адрес."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # пакет не отправляется, нужен только маршрут
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def all_ips():
    """Все локальные IPv4, кроме loopback."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    p = primary_ip()
    if not p.startswith("127."):
        ips.add(p)
    return sorted(ips, key=lambda i: (i != p, i))


def is_private(ip):
    return (ip.startswith("192.168.") or ip.startswith("10.")
            or any(ip.startswith(f"172.{i}.") for i in range(16, 32)))


def urls(port):
    """Готовые ссылки для печати и для QR."""
    ip = primary_ip()
    return {
        "lan_ip": ip,
        "all_ips": all_ips(),
        "is_private": is_private(ip),
        "host": f"http://{ip}:{port}/host",
        "admin": f"http://{ip}:{port}/admin",
        "connect": f"http://{ip}:{port}/connect",
    }


def banner(port, build, code, admin_pin):
    """Текст для консоли при запуске."""
    u = urls(port)
    lines = [
        "",
        f"=== Аватар-хост v{build} ===",
        "",
        "  НА ЭТОМ КОМПЬЮТЕРЕ (проектор):",
        f"    Экран      http://localhost:{port}/host",
        "",
        "  С ДРУГИХ УСТРОЙСТВ В ТОЙ ЖЕ WI-FI СЕТИ:",
        f"    Пульт      {u['admin']}      PIN: {admin_pin}",
        f"    Гости      {u['connect']}   код: {code}",
        "",
    ]
    if len(u["all_ips"]) > 1:
        lines.append(f"  Другие адреса этого компьютера: {', '.join(u['all_ips'][1:])}")
        lines.append("  Если телефон не открывает страницу — попробуйте их по очереди.")
        lines.append("")
    if not u["is_private"]:
        lines.append("  ! Похоже, вы не в локальной сети. Проверьте подключение к Wi-Fi.")
        lines.append("")
    lines.append("  Телефоны должны быть в ТОЙ ЖЕ Wi-Fi сети, что и этот компьютер.")
    lines.append("")
    return "\n".join(lines)
