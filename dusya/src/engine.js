const STORAGE_KEY = 'dusya-installed';

export function loadInstalled() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return ['time', 'date', 'weather'];
}

export function saveInstalled(ids) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
}

export function normalize(s) {
  return (s || '')
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function hasWake(text) {
  const t = normalize(text);
  return /(окей |ок |эй )?(дуся|дюся|dusia)/.test(t);
}

export function stripWake(text) {
  return normalize(text).replace(/^(окей |ок |эй )?(дуся|дюся)\s*/, '').trim();
}

export function matchPlugin(text, plugins) {
  const t = stripWake(text);
  if (!t) return null;
  for (const p of plugins) {
    for (const ph of p.phrases || []) {
      if (t.includes(normalize(ph)) || normalize(ph).includes(t)) return p;
    }
  }
  return null;
}

export async function runPlugin(plugin) {
  switch (plugin.action) {
    case 'time': {
      const now = new Date();
      const h = now.getHours();
      const m = String(now.getMinutes()).padStart(2, '0');
      return `Сейчас ${h}:${m}`;
    }
    case 'date': {
      const now = new Date();
      const d = now.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });
      return `Сегодня ${d}`;
    }
    case 'weather':
      return 'Офлайн-режим: за окном ясно, плюс двадцать. Это эмуляция, сеть не нужна.';
    case 'http': {
      try {
        const r = await fetch(plugin.url || 'https://httpbin.org/get', { method: 'GET' });
        return r.ok ? 'Сервис ответил, связь есть.' : `Сервис вернул код ${r.status}`;
      } catch {
        return 'Сеть недоступна — HTTP-плагин не смог достучаться.';
      }
    }
    case 'open': {
      const map = {
        карты: 'https://maps.google.com',
        почту: 'mailto:',
        приложение: 'https://'
      };
      window.open(map['карты'], '_blank');
      return 'Открываю карты.';
    }
    default:
      return 'Плагин не знает, что делать.';
  }
}

export function speak(text) {
  return new Promise((resolve) => {
    if (!window.speechSynthesis) {
      resolve();
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'ru-RU';
    u.rate = 1;
    u.onend = () => resolve();
    u.onerror = () => resolve();
    window.speechSynthesis.speak(u);
  });
}

export function getRecognition() {
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.lang = 'ru-RU';
  rec.interimResults = true;
  rec.continuous = true;
  return rec;
}
