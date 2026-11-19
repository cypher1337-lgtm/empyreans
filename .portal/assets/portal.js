'use strict';
(() => {
  const $ = (selector) => document.querySelector(selector);
  const state = { pages: [], category: 'Alle Werke', query: '', sort: 'recent', ready: false };
  const els = {
    gate: $('#gate'), form: $('#gate-form'), pin: $('#pin'), error: $('#gate-error'),
    submit: $('#unlock-button'), show: $('#show-pin'), cards: $('#cards'),
    filters: $('#filters'), controls: $('#controls'), search: $('#search'),
    sort: $('#sort'), empty: $('#empty-state'), counter: $('#results-counter'),
    lockedNote: $('#locked-note'), status: $('.status'), label: $('#state-label')
  };
  const enc = new TextEncoder();
  const decoder = new TextDecoder();
  let encryptedCatalog = null;

  const b64ToBytes = (encoded) => Uint8Array.from(atob(encoded), ch => ch.charCodeAt(0));
  async function decryptCatalog(pin) {
    if (!window.crypto?.subtle) throw new Error('Für die Entschlüsselung ist HTTPS erforderlich.');
    if (!encryptedCatalog) {
      const response = await fetch('./_empyreans/catalog.enc.json', {cache: 'no-store'});
      if (!response.ok) throw new Error('Katalog nicht erreichbar. Prüfe den GitHub-Actions-Deploy.');
      encryptedCatalog = await response.json();
    }
    if (encryptedCatalog.format !== 'EMPYREANS-PORTAL-v1') throw new Error('Unbekanntes Katalogformat.');
    const baseKey = await crypto.subtle.importKey('raw', enc.encode(pin), 'PBKDF2', false, ['deriveKey']);
    const cryptoKey = await crypto.subtle.deriveKey({
      name: 'PBKDF2', salt: b64ToBytes(encryptedCatalog.salt),
      iterations: encryptedCatalog.iterations, hash: 'SHA-256'
    }, baseKey, {name: 'AES-GCM', length: 256}, false, ['decrypt']);
    const plain = await crypto.subtle.decrypt({
      name: 'AES-GCM', iv: b64ToBytes(encryptedCatalog.iv),
      additionalData: enc.encode('EMPYREANS-PORTAL-v1')
    }, cryptoKey, b64ToBytes(encryptedCatalog.data));
    return JSON.parse(decoder.decode(plain));
  }

  const make = (tag, className, text) => {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const formatDate = (iso) => {
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('de-DE', {day: '2-digit', month: 'short', year: 'numeric'}).format(date);
  };
  const validRelativeUrl = (candidate) => {
    if (typeof candidate !== 'string') return false;
    if (!candidate || candidate.startsWith('/') || candidate.startsWith('//') || candidate.startsWith('#')) return false;
    if (candidate.includes('\\') || candidate.split('/').some(part => part === '..')) return false;
    return !/^[a-z][a-z\d+.-]*:/i.test(candidate);
  };

  function drawFilters() {
    els.filters.replaceChildren();
    const counts = new Map();
    for (const page of state.pages) counts.set(page.category, (counts.get(page.category) || 0) + 1);
    const items = [['Alle Werke', state.pages.length], ...[...counts].sort(([a],[b]) => a.localeCompare(b, 'de'))];
    for (const [name, count] of items) {
      const chip = make('button', `filter-chip${state.category === name ? ' active' : ''}`);
      chip.type = 'button';
      chip.setAttribute('aria-pressed', String(state.category === name));
      chip.append(document.createTextNode(name));
      chip.append(make('span', 'count', String(count).padStart(2, '0')));
      chip.addEventListener('click', () => {state.category = name; drawFilters(); drawCards();});
      els.filters.append(chip);
    }
  }

  function card(page, index) {
    const a = make('a', 'card-link');
    a.setAttribute('role', 'listitem');
    a.href = validRelativeUrl(page.path) ? `./${page.path}` : '#archive';
    a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.setAttribute('aria-label', `${page.title} öffnen`);
    const thumb = make('div', 'card-thumb');
    thumb.append(make('div', 'card-sky'), make('div', 'card-mountains'));
    if (validRelativeUrl(page.image)) {
      const img = make('img'); img.src = `./${page.image}`; img.loading = 'lazy'; img.alt = '';
      thumb.insertBefore(img, thumb.firstChild);
    }
    thumb.append(make('div', 'card-index', String(index + 1).padStart(2, '0')));
    thumb.append(make('div', 'card-type', page.kind === 'markdown' ? 'CHRONIK · 文' : 'KAPITEL · 章'));
    const body = make('div', 'card-body');
    const kicker = make('div', 'card-kicker');
    kicker.append(make('span', '', page.category));
    if (page.featured) kicker.append(make('span', 'featured', '✦ EMPFOHLEN'));
    const title = make('h3', 'card-title', page.title);
    const description = make('p', 'card-description', page.description);
    const bottom = make('div', 'card-bottom');
    const date = make('time', '', formatDate(page.updated)); date.dateTime = page.updated;
    const go = make('span', 'card-go'); go.append(document.createTextNode('ANSEHEN '), make('span', '', '↗'));
    bottom.append(date, go); body.append(kicker, title, description, bottom);
    a.append(thumb, body);
    return a;
  }

  function drawCards() {
    const q = state.query.toLocaleLowerCase('de').trim();
    let filtered = state.pages.filter(page => {
      if (state.category !== 'Alle Werke' && page.category !== state.category) return false;
      if (!q) return true;
      return [page.title, page.description, page.category, page.path, ...(page.tags || [])]
        .join(' ').toLocaleLowerCase('de').includes(q);
    });
    if (state.sort === 'title') filtered = filtered.sort((a,b) => a.title.localeCompare(b.title, 'de'));
    if (state.sort === 'category') filtered = filtered.sort((a,b) => a.category.localeCompare(b.category, 'de') || a.title.localeCompare(b.title, 'de'));
    if (state.sort === 'recent') filtered = filtered.sort((a,b) => (b.featured - a.featured) || b.updated.localeCompare(a.updated));
    const fragment = document.createDocumentFragment();
    filtered.forEach((page, i) => fragment.append(card(page, i)));
    els.cards.replaceChildren(fragment);
    els.empty.hidden = filtered.length > 0;
    els.counter.textContent = `${String(filtered.length).padStart(2, '0')} EINTRÄGE`;
  }

  function unlock(data) {
    state.pages = Array.isArray(data.pages) ? data.pages : [];
    state.ready = true;
    state.category = 'Alle Werke'; state.query = ''; state.sort = 'recent';
    els.search.value = ''; els.sort.value = 'recent';
    $('#hero-count').textContent = String(state.pages.length).padStart(2, '0');
    $('#hero-categories').textContent = String(new Set(state.pages.map(p => p.category)).size).padStart(2, '0');
    $('#hero-date').textContent = formatDate(data.builtAt).replace(/\s*\d{4}$/, '');
    els.status.classList.add('active'); els.label.textContent = 'GEÖFFNET';
    els.controls.hidden = false; els.filters.hidden = false;
    els.lockedNote.hidden = true;
    $('#lock-button').hidden = false;
    els.pin.value = '';
    drawFilters(); drawCards();
    $('#site-shell').inert = false;
    els.gate.classList.add('closed');
    els.gate.setAttribute('aria-hidden', 'true');
    els.gate.removeAttribute('aria-modal');
    $('#lock-button').focus({preventScroll:true});
  }

  function lock() {
    state.pages = []; state.ready = false; state.category = 'Alle Werke';
    els.cards.replaceChildren();
    els.controls.hidden = true; els.filters.hidden = true;
    els.lockedNote.hidden = false;
    $('#hero-count').textContent = '—'; $('#hero-categories').textContent = '—'; $('#hero-date').textContent = '—';
    els.counter.textContent = '— EINTRÄGE';
    els.status.classList.remove('active'); els.label.textContent = 'VERSIEGELT';
    $('#lock-button').hidden = true;
    els.error.textContent = '';
    $('#site-shell').inert = true;
    els.gate.classList.remove('closed');
    els.gate.removeAttribute('aria-hidden');
    els.gate.setAttribute('aria-modal', 'true');
    els.pin.focus({preventScroll:true});
  }

  els.form.addEventListener('submit', async event => {
    event.preventDefault();
    const pin = els.pin.value;
    if (!pin) {els.error.textContent = 'Bitte die PIN eingeben.';els.pin.focus();return;}
    els.submit.disabled = true;
    els.submit.firstElementChild.textContent = 'Das Siegel wird geprüft …';
    els.error.textContent = '';
    try {
      const data = await decryptCatalog(pin);
      unlock(data);
    } catch (err) {
      const text = err?.message || '';
      els.error.textContent = text.includes('Katalog nicht erreichbar') || text.includes('HTTPS') ? text : 'PIN nicht korrekt oder Katalog nicht lesbar.';
      els.pin.value = '';els.pin.focus();
    } finally {
      els.submit.disabled = false;
      els.submit.firstElementChild.textContent = 'Das Siegel brechen';
    }
  });
  els.show.addEventListener('click', () => {
    const visible = els.pin.type === 'text';
    els.pin.type = visible ? 'password' : 'text';
    els.show.textContent = visible ? 'ANZEIGEN' : 'VERBERGEN';
    els.show.setAttribute('aria-pressed', String(!visible));
    els.pin.focus();
  });
  $('#lock-button').addEventListener('click', lock);
  $('#open-unlock').addEventListener('click', lock);
  $('#reset-filters').addEventListener('click', () => {
    state.category = 'Alle Werke'; state.query = ''; els.search.value = '';
    drawFilters(); drawCards();
  });
  els.search.addEventListener('input', () => {state.query = els.search.value;drawCards();});
  els.sort.addEventListener('change', () => {state.sort = els.sort.value;drawCards();});
  document.addEventListener('keydown', e => {
    if (e.key === '/' && state.ready && !['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)) {
      e.preventDefault(); els.search.focus();
    }
  });
  $('#footer-year').textContent = String(new Date().getFullYear());
  els.pin.focus({preventScroll:true});
})();
