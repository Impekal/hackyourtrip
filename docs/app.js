'use strict';

/* =========================================================================
 * Tabs
 * ===================================================================== */
const tabSearch = document.getElementById('tab-search');
const tabAlerts = document.getElementById('tab-alerts');
const panelSearch = document.getElementById('panel-search');
const panelAlerts = document.getElementById('panel-alerts');

function activateTab(tab) {
  const isSearch = tab === 'search';
  tabSearch.classList.toggle('active', isSearch);
  tabAlerts.classList.toggle('active', !isSearch);
  tabSearch.setAttribute('aria-selected', String(isSearch));
  tabAlerts.setAttribute('aria-selected', String(!isSearch));
  panelSearch.classList.toggle('active', isSearch);
  panelAlerts.classList.toggle('active', !isSearch);
  if (!isSearch) loadAlerts();
}
tabSearch.addEventListener('click', () => activateTab('search'));
tabAlerts.addEventListener('click', () => activateTab('alerts'));

/* =========================================================================
 * Seeded RNG - the live "Suche" tab has no server, so every result has to
 * come from something deterministic-per-day running in the visitor's own
 * browser. xmur3 turns the route+mode+date into a seed, mulberry32 turns
 * that seed into a repeatable stream of "random" numbers: same search on
 * the same day gives the same offers, a new day shuffles them.
 * ===================================================================== */
function xmur3(str) {
  let h = 1779033703 ^ str.length;
  for (let i = 0; i < str.length; i++) {
    h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return function seed() {
    h = Math.imul(h ^ (h >>> 16), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return (h ^= h >>> 16) >>> 0;
  };
}
function mulberry32(seed) {
  return function rng() {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function makeRng(seedStr) { return mulberry32(xmur3(seedStr)()); }
function rngFloat(rng, min, max) { return rng() * (max - min) + min; }
function rngChoice(rng, arr) { return arr[Math.floor(rng() * arr.length)]; }
function rngSample(rng, arr, k) {
  const pool = arr.slice();
  const out = [];
  for (let i = 0; i < k && pool.length; i++) out.push(pool.splice(Math.floor(rng() * pool.length), 1)[0]);
  return out;
}
const round2 = n => Math.round(n * 100) / 100;
const round1 = n => Math.round(n * 10) / 10;

/* =========================================================================
 * Date helpers
 * ===================================================================== */
function addDays(date, n) { const d = new Date(date); d.setDate(d.getDate() + n); return d; }
function dayCandidates(route) {
  const start = addDays(route.departFrom, -route.flexBefore);
  const end = addDays(route.departUntil, route.flexAfter);
  const days = [];
  for (let d = new Date(start); d <= end; d = addDays(d, 1)) days.push(new Date(d));
  return days.length ? days : [start];
}
function atHour(date, hour, minute) { const d = new Date(date); d.setHours(hour, minute || 0, 0, 0); return d; }
function isoDay(date) { return date.toISOString().slice(0, 10); }

/* =========================================================================
 * Mock providers - same shape/parameters as traveldeals/providers/mock.py,
 * just running client-side so the search tab needs no backend at all.
 * ===================================================================== */
const BOOKING_SITES = {
  flight: ['Skyscanner', 'Google Flights', 'Kiwi.com', 'Airline direct'],
  train: ['DB Navigator', 'Trainline', 'Omio'],
  bus: ['FlixBus', 'Omio'],
  hotel: ['Booking.com', 'Trivago', 'Hotels.com', 'Airbnb'],
};
const BAHNCARD_DISCOUNT = { '25': 0.25, '50': 0.5, '100': 1.0, '': 0.0 };

function mockFlightOffers(route) {
  const rng = makeRng(`${route.origin}>${route.destination}:flight:${isoDay(new Date())}`);
  const offers = [];
  const basePrice = rngFloat(rng, 60, 320);
  const hours = [6, 9, 12, 15, 18, 21];
  for (const day of dayCandidates(route)) {
    for (const hour of rngSample(rng, hours, Math.min(3, hours.length))) {
      const peak = (hour === 6 || hour === 18) ? 1.35 : 1.0;
      const price = round2(basePrice * peak * rngFloat(rng, 0.85, 1.25));
      const duration = round1(rngFloat(rng, 1.5, 4.5));
      const isLowCost = rng() < 0.5;
      const bagFee = isLowCost ? round2(rngFloat(rng, 25, 55)) : 0;
      const depart = atHour(day, hour, rngChoice(rng, [0, 15, 30, 45]));
      offers.push({
        mode: 'flight', bookingSite: rngChoice(rng, BOOKING_SITES.flight),
        price, currency: route.currency, depart, durationHours: duration,
        bagFee, isLowCost,
      });
    }
  }
  return offers;
}

function mockTrainOffers(route) {
  const rng = makeRng(`${route.origin}>${route.destination}:train:${isoDay(new Date())}`);
  const offers = [];
  const basePrice = rngFloat(rng, 20, 140);
  const discount = BAHNCARD_DISCOUNT[route.bahncard] ?? 0;
  const hours = Array.from({ length: 17 }, (_, i) => i + 5); // 5..21
  for (const day of dayCandidates(route)) {
    for (const hour of rngSample(rng, hours, 3)) {
      const price = round2(basePrice * rngFloat(rng, 0.8, 1.3) * (1 - discount));
      const duration = round1(rngFloat(rng, 2.0, 7.0));
      const depart = atHour(day, hour, rngChoice(rng, [0, 15, 30, 45]));
      offers.push({
        mode: 'train', bookingSite: rngChoice(rng, BOOKING_SITES.train),
        price: route.bahncard === '100' ? 0 : price, currency: route.currency,
        depart, durationHours: duration, bagFee: 0, isLowCost: false,
      });
    }
  }
  return offers;
}

function mockBusOffers(route) {
  const rng = makeRng(`${route.origin}>${route.destination}:bus:${isoDay(new Date())}`);
  const offers = [];
  const basePrice = rngFloat(rng, 9, 50);
  const hours = Array.from({ length: 24 }, (_, i) => i);
  for (const day of dayCandidates(route)) {
    for (const hour of rngSample(rng, hours, 3)) {
      const price = round2(basePrice * rngFloat(rng, 0.8, 1.2));
      const duration = round1(rngFloat(rng, 3.0, 11.0));
      const depart = atHour(day, hour, rngChoice(rng, [0, 30]));
      offers.push({
        mode: 'bus', bookingSite: rngChoice(rng, BOOKING_SITES.bus),
        price, currency: route.currency, depart, durationHours: duration,
        bagFee: 0, isLowCost: false,
      });
    }
  }
  return offers;
}

function mockHotelOffers(route) {
  const rng = makeRng(`${route.origin}>${route.destination}:hotel:${isoDay(new Date())}`);
  const offers = [];
  const nights = Math.max(route.minNights, 1);
  const basePerNight = rngFloat(rng, 45, 220);
  for (const checkin of dayCandidates(route).slice(0, 5)) {
    for (let i = 0; i < 3; i++) {
      const perNight = round2(basePerNight * rngFloat(rng, 0.85, 1.3));
      offers.push({
        mode: 'hotel', bookingSite: rngChoice(rng, BOOKING_SITES.hotel),
        price: round2(perNight * nights), currency: route.currency,
        depart: checkin, durationHours: nights * 24, bagFee: 0, isLowCost: false,
        nights,
      });
    }
  }
  return offers;
}

/* =========================================================================
 * Currency - live rate via the free Frankfurter API when reachable
 * (this page is a real hosted site, not a sandboxed artifact, so the fetch
 * is allowed), falling back to a static table otherwise.
 * ===================================================================== */
const FALLBACK_RATES_PER_EUR = { EUR: 1.0, USD: 1.08, GBP: 0.85, CHF: 0.94 };
let ratesPerEurPromise = null;
function getRatesPerEur() {
  if (!ratesPerEurPromise) {
    ratesPerEurPromise = fetch('https://api.frankfurter.app/latest?from=EUR')
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(j => ({ ...FALLBACK_RATES_PER_EUR, ...j.rates, EUR: 1.0 }))
      .catch(() => ({ ...FALLBACK_RATES_PER_EUR }));
  }
  return ratesPerEurPromise;
}
function convert(amount, from, to, rates) {
  if (from === to || !rates[from] || !rates[to]) return amount;
  return round2((amount / rates[from]) * rates[to]);
}

/* =========================================================================
 * Engine - ranking + recommendations, mirroring traveldeals/engine.py.
 * No price-history/error-fare detection here: that needs data accumulated
 * across real runs (see the "Meine Alerts" tab), which a stateless
 * in-browser search doesn't have.
 * ===================================================================== */
const BEST_VALUE_PRICE_WEIGHT = 0.6;
const BEST_VALUE_DURATION_WEIGHT = 0.4;
const BAGGAGE_SAVINGS_THRESHOLD = 0.15;

function buildCombos(transportOffers, hotelOffers) {
  const hotelsByCheckin = {};
  for (const h of hotelOffers) (hotelsByCheckin[isoDay(h.depart)] ??= []).push(h);
  const combos = [];
  for (const t of transportOffers) {
    const sameDay = hotelsByCheckin[isoDay(t.depart)];
    if (!sameDay || !sameDay.length) continue;
    const cheapestHotel = sameDay.reduce((a, b) => (b.price < a.price ? b : a));
    combos.push({ transport: t, hotel: cheapestHotel, price: round2(t.price + cheapestHotel.price) });
  }
  return combos;
}

function normalize(value, all) {
  const lo = Math.min(...all), hi = Math.max(...all);
  return hi === lo ? 0 : (value - lo) / (hi - lo);
}

async function runSearch(route) {
  const pools = {};
  const pool = mode => (pools[mode] ??= ({ flight: mockFlightOffers, train: mockTrainOffers, bus: mockBusOffers, hotel: mockHotelOffers }[mode](route)));

  let candidates = [];
  const comboTransport = { flight_hotel: 'flight', train_hotel: 'train', bus_hotel: 'bus' };

  for (const mode of route.modes) {
    if (['flight', 'train', 'bus', 'hotel'].includes(mode)) {
      for (const offer of pool(mode)) candidates.push({ mode, offers: [offer], price: offer.price, durationHours: offer.durationHours });
    } else if (comboTransport[mode]) {
      const tMode = comboTransport[mode];
      for (const combo of buildCombos(pool(tMode), pool('hotel'))) {
        candidates.push({ mode, offers: [combo.transport, combo.hotel], price: combo.price, durationHours: combo.transport.durationHours });
      }
    } else if (mode === 'train_or_bus') {
      for (const offer of [...pool('train'), ...pool('bus')]) {
        candidates.push({ mode: 'train_or_bus', offers: [offer], price: offer.price, durationHours: offer.durationHours });
      }
    }
  }

  candidates = candidates.filter(c => {
    if (route.budget != null && c.price > route.budget) return false;
    if (route.maxDuration != null && c.durationHours > route.maxDuration && c.mode !== 'hotel') return false;
    if (!route.lowCostOk && c.offers.some(o => o.isLowCost)) return false;
    return true;
  });

  const prices = candidates.map(c => c.price);
  const durations = candidates.map(c => c.durationHours);
  for (const c of candidates) {
    if (route.priority === 'cheapest') c.score = c.price;
    else if (route.priority === 'fastest') c.score = c.durationHours;
    else c.score = BEST_VALUE_PRICE_WEIGHT * normalize(c.price, prices) + BEST_VALUE_DURATION_WEIGHT * normalize(c.durationHours, durations);
  }
  candidates.sort((a, b) => a.score - b.score);
  const top = candidates.slice(0, 6);

  const rates = await getRatesPerEur();
  for (const c of top) {
    c.recommendations = [];
    const transportOffer = c.offers[0];
    const samePool = pools[transportOffer.mode] || [];

    if (['flight', 'train', 'bus'].includes(transportOffer.mode)) {
      const sameDayLater = samePool.filter(o =>
        isoDay(o.depart) === isoDay(transportOffer.depart) &&
        o.depart > transportOffer.depart &&
        o.price < transportOffer.price
      );
      if (sameDayLater.length) {
        const best = sameDayLater.reduce((a, b) => (b.price < a.price ? b : a));
        const hoursLater = round1((best.depart - transportOffer.depart) / 3600000);
        const savings = round2(transportOffer.price - best.price);
        c.recommendations.push(`🕐 ${hoursLater}h später (${fmtHM(best.depart)} statt ${fmtHM(transportOffer.depart)}) spart ${savings} ${transportOffer.currency}.`);
      }
    }

    if (transportOffer.bagFee > 0) {
      const bags = Math.max(route.checkedBags, 1);
      const savings = round2(transportOffer.bagFee * bags);
      if (savings / c.price >= BAGGAGE_SAVINGS_THRESHOLD) {
        c.recommendations.push(`🎒 Nur Handgepäck statt ${bags}x Koffer (${route.checkedBagKg}kg) spart ${savings} ${transportOffer.currency}.`);
      }
    }

    if (['flight', 'flight_hotel', 'hotel'].includes(c.mode)) {
      const others = ['USD', 'GBP'].filter(cur => cur !== route.currency);
      const equivalents = others.map(cur => `${convert(c.price, route.currency, cur, rates)} ${cur}`);
      if (equivalents.length) {
        c.recommendations.push(`💱 Entspricht ca. ${equivalents.join(' / ')} – ob eine Buchung in anderer Landeswährung günstiger ist, prüft v1 noch nicht automatisch.`);
      }
    }
  }
  return top;
}

function fmtHM(date) { return date.toTimeString().slice(0, 5); }
function fmtShort(date) { return date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }) + ' ' + fmtHM(date); }

/* =========================================================================
 * Search form wiring
 * ===================================================================== */
const searchForm = document.getElementById('searchForm');
const searchResultsEl = document.getElementById('searchResults');
const searchMetaEl = document.getElementById('searchMeta');
const trackBox = document.getElementById('trackBox');
const trackYaml = document.getElementById('trackYaml');

function readRouteFromForm() {
  const modes = Array.from(document.querySelectorAll('input[name="modes"]:checked')).map(el => el.value);
  return {
    origin: document.getElementById('origin').value.trim(),
    destination: document.getElementById('destination').value.trim(),
    departFrom: new Date(document.getElementById('departFrom').value),
    departUntil: new Date(document.getElementById('departUntil').value),
    flexBefore: Number(document.getElementById('flexBefore').value || 0),
    flexAfter: Number(document.getElementById('flexAfter').value || 0),
    minNights: Number(document.getElementById('minNights').value || 0),
    maxNights: Number(document.getElementById('maxNights').value || 0),
    budget: document.getElementById('budget').value ? Number(document.getElementById('budget').value) : null,
    currency: document.getElementById('currency').value,
    maxDuration: document.getElementById('maxDuration').value ? Number(document.getElementById('maxDuration').value) : null,
    priority: document.getElementById('priority').value,
    modes: modes.length ? modes : ['flight'],
    carryOnOnly: document.getElementById('carryOnOnly').checked,
    checkedBags: Number(document.getElementById('checkedBags').value || 0),
    checkedBagKg: Number(document.getElementById('checkedBagKg').value || 23),
    bahncard: document.getElementById('bahncard').value,
    deutschlandticket: document.getElementById('deutschlandticket').checked,
    lowCostOk: document.getElementById('lowCostOk').checked,
  };
}

function renderResults(route, options) {
  searchMetaEl.textContent = `${options.length} Angebote gefunden für ${route.origin} → ${route.destination} (Mock-Daten, Stand heute)`;
  if (!options.length) {
    searchResultsEl.innerHTML = '<p class="empty">Keine Angebote in diesem Budget/Zeitrahmen gefunden - Filter lockern und erneut suchen.</p>';
    return;
  }
  searchResultsEl.innerHTML = `
    <div class="route">
      ${options.map((opt, i) => `
        <div class="option">
          <span class="rank mono">${i + 1}</span>
          <div class="price-row">
            <span class="price mono">${opt.price.toFixed(2)} ${route.currency}</span>
          </div>
          <span class="subline mono">${opt.mode} · ${fmtShort(opt.offers[0].depart)} · ${opt.durationHours}h · ${opt.offers.map(o => o.bookingSite).join(', ')}</span>
          ${opt.recommendations.length ? `<ul class="recs">${opt.recommendations.map(r => `<li>${r}</li>`).join('')}</ul>` : ''}
        </div>
      `).join('')}
    </div>
  `;
}

function buildYamlSnippet(route) {
  const slug = `${route.origin}-${route.destination}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
  const fmt = d => d.toISOString().slice(0, 10);
  return `  - id: ${slug}
    origin: ${route.origin}
    destination: ${route.destination}
    depart_date_from: ${fmt(route.departFrom)}
    depart_date_until: ${fmt(route.departUntil)}
    flex_days_before: ${route.flexBefore}
    flex_days_after: ${route.flexAfter}
    min_nights: ${route.minNights}
    max_nights: ${route.maxNights}
    budget: ${route.budget ?? 'null'}
    currency: ${route.currency}
    max_duration_hours: ${route.maxDuration ?? 'null'}
    priority: ${route.priority}
    modes: [${route.modes.join(', ')}]
    baggage:
      carry_on_only: ${route.carryOnOnly}
      checked_bags: ${route.checkedBags}
      checked_bag_kg: ${route.checkedBagKg}
    rail:
      bahncard: ${route.bahncard ? `"${route.bahncard}"` : 'null'}
      deutschlandticket: ${route.deutschlandticket}
    low_cost_airlines_ok: ${route.lowCostOk}
`;
}

searchForm.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const route = readRouteFromForm();
  searchMetaEl.textContent = 'suche…';
  searchResultsEl.innerHTML = '';
  const options = await runSearch(route);
  renderResults(route, options);
  trackYaml.value = buildYamlSnippet(route);
  trackBox.hidden = false;
});

document.getElementById('copyYaml').addEventListener('click', () => {
  trackYaml.select();
  navigator.clipboard?.writeText(trackYaml.value);
});

/* =========================================================================
 * "Meine Alerts" tab - reads the result of the last GitHub Actions cron
 * run (traveldeals.cli check), which does have real accumulated price
 * history and can flag error fares/drops - unlike the live search above.
 * ===================================================================== */
let alertsLoaded = false;
async function loadAlerts() {
  if (alertsLoaded) return;
  alertsLoaded = true;
  const metaEl = document.getElementById('alertsMeta');
  const routesEl = document.getElementById('alertsRoutes');
  let data;
  try {
    const resp = await fetch('./data/deals.json', { cache: 'no-store' });
    data = await resp.json();
  } catch (e) {
    metaEl.textContent = 'Konnte data/deals.json nicht laden.';
    return;
  }
  metaEl.textContent = data.generated_at
    ? `Zuletzt aktualisiert: ${new Date(data.generated_at).toLocaleString('de-DE')}`
    : 'Noch kein Lauf - config/routes.yaml anlegen und den GitHub-Actions-Cron auslösen (oder lokal `python -m traveldeals.cli check`).';
  if (!data.routes || !data.routes.length) {
    routesEl.innerHTML = '<p class="empty">Keine Strecken konfiguriert.</p>';
    return;
  }
  routesEl.innerHTML = data.routes.map(route => `
    <div class="route">
      <div class="route-head"><h2>${route.origin} → ${route.destination}</h2></div>
      ${route.notes ? `<p class="notes">${route.notes}</p>` : ''}
      ${!route.options.length ? '<p class="empty">Keine Angebote gefunden.</p>' : route.options.map((opt, i) => `
        <div class="option">
          <span class="rank mono">${i + 1}</span>
          <div class="price-row">
            <span class="price mono">${opt.total_price.toFixed(2)} ${opt.currency}</span>
            ${opt.is_error_fare ? '<span class="badge alert">Fehlerpreis</span>' : ''}
            ${opt.is_price_drop ? '<span class="badge good">Preis gefallen</span>' : ''}
          </div>
          <span class="subline mono">${opt.mode} · ${opt.total_duration_hours}h · ${opt.booking_sites.join(', ')}</span>
          ${opt.recommendations.length ? `<ul class="recs">${opt.recommendations.map(r => `<li>${r}</li>`).join('')}</ul>` : ''}
        </div>
      `).join('')}
    </div>
  `).join('');
}

/* default dates so the form is usable without typing: today+30 .. today+34 */
(function seedDefaultDates() {
  const from = addDays(new Date(), 30);
  const until = addDays(new Date(), 34);
  document.getElementById('departFrom').value = isoDay(from);
  document.getElementById('departUntil').value = isoDay(until);
})();
