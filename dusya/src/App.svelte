<script>
  import { onMount } from 'svelte';
  import catalog from './catalog.json';
  import {
    loadInstalled, saveInstalled, matchPlugin, runPlugin, speak,
    getRecognition, hasWake, stripWake
  } from './engine.js';

  let tab = 'home';
  let status = 'Готово';
  let transcript = '';
  let log = 'Скажите «Дуся, который час» или нажмите кнопку.';
  let ttsText = 'Привет, я Дуся.';
  let installed = loadInstalled();
  let listening = false;
  let rec = null;
  let wakeArmed = true;

  $: plugins = catalog.filter((p) => installed.includes(p.id));

  onMount(() => {
    rec = getRecognition();
    if (!rec) {
      status = 'Web Speech STT недоступен в этом браузере (нужен Chrome/Edge).';
      return;
    }
    rec.onresult = async (ev) => {
      let text = '';
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        text += ev.results[i][0].transcript;
      }
      transcript = text;
      const final = ev.results[ev.results.length - 1].isFinal;
      if (!final) {
        status = 'Слушаю…';
        return;
      }
      await handleUtterance(text);
    };
    rec.onerror = (e) => {
      if (e.error !== 'no-speech') status = 'Ошибка микрофона: ' + e.error;
    };
    rec.onend = () => {
      if (listening) {
        try { rec.start(); } catch {}
      }
    };
  });

  function startListen() {
    if (!rec) return;
    listening = true;
    status = 'Слушаю…';
    try { rec.start(); } catch {}
  }

  function stopListen() {
    listening = false;
    status = 'Готово';
    try { rec.stop(); } catch {}
  }

  function toggleMic() {
    listening ? stopListen() : startListen();
  }

  async function handleUtterance(text) {
    const raw = text.trim();
    if (!raw) return;
    if (wakeArmed && !hasWake(raw) && listening) {
      log = 'Ожидаю «Дуся…»: ' + raw;
      status = 'Слушаю…';
      return;
    }
    const cmd = stripWake(raw) || raw;
    status = 'Думаю…';
    const plugin = matchPlugin(raw, plugins);
    let answer;
    if (!plugin) {
      answer = cmd ? `Не знаю команду «${cmd}». Откройте каталог скриптов.` : 'Слушаю.';
    } else {
      answer = await runPlugin(plugin);
    }
    log = `Вы: ${raw}\nДуся: ${answer}`;
    status = 'Ответ';
    await speak(answer);
    status = listening ? 'Слушаю…' : 'Готово';
  }

  async function sayTts() {
    status = 'Ответ';
    await speak(ttsText);
    status = 'Готово';
  }

  function toggleInstall(id) {
    if (installed.includes(id)) installed = installed.filter((x) => x !== id);
    else installed = [...installed, id];
    saveInstalled(installed);
  }
</script>

<div class="tabs">
  <button class="tab" class:active={tab === 'home'} on:click={() => (tab = 'home')}>Главная</button>
  <button class="tab" class:active={tab === 'mine'} on:click={() => (tab = 'mine')}>Мои скрипты</button>
  <button class="tab" class:active={tab === 'cat'} on:click={() => (tab = 'cat')}>Каталог</button>
</div>

{#if tab === 'home'}
  <div class="screen">
    <h1>Дуся</h1>
    <p class="hint">Офлайн PWA. Wake word: «Дуся». STT/TTS — Web Speech API.</p>
    <p class="status">{status}</p>
    <button class="mic" class:listening on:click={toggleMic}>{listening ? 'Стоп' : 'Старт'}</button>
    <div class="log">{log}{transcript ? '\n… ' + transcript : ''}</div>
    <div class="tts-row">
      <input bind:value={ttsText} placeholder="Текст для TTS" />
      <button class="install" on:click={sayTts}>Сказать</button>
    </div>
    <label class="hint" style="display:block;margin-top:12px">
      <input type="checkbox" bind:checked={wakeArmed} /> Требовать wake word «Дуся»
    </label>
  </div>
{/if}

{#if tab === 'mine'}
  <div class="screen">
    <h1>Мои скрипты</h1>
    {#each plugins as p}
      <div class="card">
        <div class="row">
          <div>
            <strong>{p.name}</strong>
            <div class="hint" style="text-align:left">{p.description}</div>
          </div>
          <button class="install off" on:click={() => toggleInstall(p.id)}>Выкл</button>
        </div>
      </div>
    {/each}
    {#if !plugins.length}
      <p class="hint">Ничего не установлено. Загляните в каталог.</p>
    {/if}
  </div>
{/if}

{#if tab === 'cat'}
  <div class="screen">
    <h1>Каталог скриптов</h1>
    {#each catalog as p}
      <div class="card">
        <div class="row">
          <div>
            <strong>{p.name}</strong>
            <div class="hint" style="text-align:left">{p.author} · {p.description}</div>
          </div>
          <button class="install" class:off={installed.includes(p.id)} on:click={() => toggleInstall(p.id)}>
            {installed.includes(p.id) ? 'Установлен' : 'Установить'}
          </button>
        </div>
      </div>
    {/each}
  </div>
{/if}
