'use strict';

// Stamped into the footer so a support question can be answered without
// guessing: if this doesn't match, the browser is running a cached old
// app.js and any "the fix didn't work" report is about the old file. Bump
// together with the ?v= in index.html.
const BUILD_STAMP = '2026-08-09-6';
document.getElementById('buildStamp').textContent = BUILD_STAMP;

/* =========================================================================
 * Main tabs (Suche / Meine Alerts)
 * ===================================================================== */
const tabSearch = document.getElementById('tab-search');
const tabAlerts = document.getElementById('tab-alerts');
const panelSearch = document.getElementById('panel-search');
const panelAlerts = document.getElementById('panel-alerts');

function activateMainTab(tab) {
  const isSearch = tab === 'search';
  tabSearch.classList.toggle('active', isSearch);
  tabAlerts.classList.toggle('active', !isSearch);
  tabSearch.setAttribute('aria-selected', String(isSearch));
  tabAlerts.setAttribute('aria-selected', String(!isSearch));
  panelSearch.classList.toggle('active', isSearch);
  panelAlerts.classList.toggle('active', !isSearch);
  if (!isSearch) loadAlerts();
}
tabSearch.addEventListener('click', () => activateMainTab('search'));
tabAlerts.addEventListener('click', () => activateMainTab('alerts'));

/* =========================================================================
 * Mode tabs (Flug / Bahn / Bus / Hotel / ...) - each tab is a search
 * "vertical" like on a real deal platform, so only the fields relevant to
 * that mode are shown: e.g. Hotel has no "Von", pure transport tabs have no
 * Naechte/Hotel-Kriterien.
 * ===================================================================== */
// singleDate: true means "just one departure date, flex_before/after already
// define the search window" (pure transport + OR-combos) - the from/until
// range stays for Hotel/*_hotel, where a real check-in window makes sense
// alongside min/max nights.
// placeSource picks the autocomplete data source for Von/Nach: 'flight' hits
// the live Travelpayouts places API (real airports+cities, value = IATA
// code), 'rail' filters the static RAIL_STATIONS list (value = station
// name), 'city' hits the same live API but city-only (value = city name,
// for the Hotel "Ort" field where a code makes no sense).
const MODE_TAB_CONFIG = {
  flight:          { origin: true,  nights: false, duration: true,  flight: true,  train: false, hotel: false, transportExtra: true,  roundTrip: true,  singleDate: true,  placeSource: 'flight', modes: ['flight'] },
  train:           { origin: true,  nights: false, duration: true,  flight: false, train: true,  hotel: false, transportExtra: true,  roundTrip: true,  singleDate: true,  placeSource: 'rail',   modes: ['train'] },
  bus:             { origin: true,  nights: false, duration: true,  flight: false, train: false, hotel: false, transportExtra: true,  roundTrip: true,  singleDate: true,  placeSource: 'rail',   modes: ['bus'] },
  hotel:           { origin: false, nights: true,  duration: false, flight: false, train: false, hotel: true,  transportExtra: false, roundTrip: false, singleDate: false, placeSource: 'city',   modes: ['hotel'] },
  train_or_bus:    { origin: true,  nights: false, duration: true,  flight: false, train: true,  hotel: false, transportExtra: true,  roundTrip: true,  singleDate: true,  placeSource: 'rail',   modes: ['train_or_bus'] },
  flight_or_train: { origin: true,  nights: false, duration: true,  flight: true,  train: true,  hotel: false, transportExtra: true,  roundTrip: true,  singleDate: true,  placeSource: 'flight', modes: ['flight_or_train'] },
  flight_or_bus:   { origin: true,  nights: false, duration: true,  flight: true,  train: false, hotel: false, transportExtra: true,  roundTrip: true,  singleDate: true,  placeSource: 'flight', modes: ['flight_or_bus'] },
  flight_hotel:    { origin: true,  nights: true,  duration: true,  flight: true,  train: false, hotel: true,  transportExtra: true,  roundTrip: false, singleDate: false, placeSource: 'flight', modes: ['flight_hotel'] },
  train_hotel:     { origin: true,  nights: true,  duration: true,  flight: false, train: true,  hotel: true,  transportExtra: true,  roundTrip: false, singleDate: false, placeSource: 'rail',   modes: ['train_hotel'] },
  // Fly out, take the bus back - or any other pairing. No booking portal
  // offers this, because each of them sells one mode; a personal tool has
  // no such constraint, and the saving can be substantial.
  mixed_return:    { origin: true,  nights: false, duration: true,  flight: true,  train: true,  hotel: false, transportExtra: true,  roundTrip: true,  singleDate: true,  placeSource: 'flight', modes: ['mixed_return'] },
  bus_hotel:       { origin: true,  nights: true,  duration: true,  flight: false, train: false, hotel: true,  transportExtra: true,  roundTrip: false, singleDate: false, placeSource: 'rail',   modes: ['bus_hotel'] },
};

let activeMode = 'flight';
const modeTabsEl = document.getElementById('modeTabs');

function applyModeVisibility(mode) {
  const cfg = MODE_TAB_CONFIG[mode];
  const groupVisible = {
    originGroup: cfg.origin, nightsGroup: cfg.nights, durationGroup: cfg.duration,
    flightGroup: cfg.flight, trainGroup: cfg.train, hotelGroup: cfg.hotel,
    transportExtraGroup: cfg.transportExtra, roundTripGroup: cfg.roundTrip,
    // Only flight offers carry a low-cost flag, so the selector would
    // guarantee zero results on train/bus/hotel tabs.
    lowCostGroup: cfg.flight,
    departUntilGroup: !cfg.singleDate,
  };
  for (const [group, visible] of Object.entries(groupVisible)) {
    document.querySelectorAll(`[data-group="${group}"]`).forEach(el => { el.hidden = !visible; });
  }
  document.getElementById('origin').required = cfg.origin;
  document.getElementById('departUntil').required = !cfg.singleDate;
  updateReturnDateVisibility();
  const isHotelOnly = mode === 'hotel';
  document.getElementById('destinationLabel').textContent = isHotelOnly ? 'Ort' : 'Nach';
  document.getElementById('departFromLabel').textContent =
    cfg.singleDate ? 'Datum' : (cfg.hotel && !cfg.origin ? 'Anreise ab' : 'Datum von');
  document.getElementById('departUntilLabel').textContent = cfg.hotel && !cfg.origin ? 'Anreise bis' : 'Datum bis';
}

modeTabsEl.addEventListener('click', (ev) => {
  const btn = ev.target.closest('.modetab');
  if (!btn) return;
  activeMode = btn.dataset.mode;
  modeTabsEl.querySelectorAll('.modetab').forEach(b => b.classList.toggle('active', b === btn));
  applyModeVisibility(activeMode);
});

function updateReturnDateVisibility() {
  const cfg = MODE_TAB_CONFIG[activeMode];
  const roundTripEl = document.getElementById('roundTrip');
  const isRoundTrip = Boolean(cfg.roundTrip && roundTripEl && roundTripEl.checked);
  const returnDateGroup = document.querySelector('[data-group="returnDateGroup"]');
  if (returnDateGroup) returnDateGroup.hidden = !isRoundTrip;
  // Zweites Reisezeit-Limit nur, wenn es auch einen Rückweg gibt - und dann
  // heißt das erste ausdrücklich "hin", damit klar ist, welches welches ist.
  const returnLimitGroup = document.querySelector('[data-group="maxDurationReturnGroup"]');
  if (returnLimitGroup) returnLimitGroup.hidden = !(isRoundTrip && cfg.duration);
  const label = document.getElementById('maxDurationLabel');
  if (label) label.textContent = isRoundTrip ? 'Max. Reisezeit hin (h)' : 'Max. Reisezeit (h)';
}
document.getElementById('roundTrip')?.addEventListener('change', updateReturnDateVisibility);

/* Eine Rückreise vor der Hinreise ist keine Reise.
 *
 * `min` allein reicht dafür nicht - und das war der Fehler in der ersten
 * Fassung. Chrome graut frühere Tage im Kalender aus, aber Firefox lässt
 * sie anklicken, und tippen kann man sie überall. `min` bleibt also als
 * erste Hürde, die eigentliche Garantie ist die Korrektur unten: ein
 * früheres Datum wird auf den Hinreisetag zurückgesetzt, sobald die
 * Eingabe steht - in jedem Browser gleich.
 *
 * Die Korrektur wird am Feld erklärt. Ein Wert, der sich ohne Erklärung
 * von selbst ändert, wirkt wie ein Fehler; ein erklärter nicht.
 *
 * Dasselbe gilt für "Datum bis" gegenüber "Datum von": ein Zeitraum, der
 * vor seinem Anfang endet, findet nie etwas. */
function showFieldHint(id, text) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
}

function syncDateBounds({ pushFollowers = true } = {}) {
  const fromEl = document.getElementById('departFrom');
  const untilEl = document.getElementById('departUntil');
  const returnEl = document.getElementById('returnDate');
  const from = fromEl.value;
  if (!from) return;

  // Gleicher Tag ist erlaubt - ein Tagesausflug hin und zurück ist üblich.
  returnEl.min = from;
  untilEl.min = from;
  if (!pushFollowers) return;
  if (returnEl.value && returnEl.value < from) {
    returnEl.value = from;
    showFieldHint('returnDateHint',
      `Rückreise kann nicht vor der Hinreise liegen – auf ${fmtDay(new Date(from))} gesetzt.`);
  }
  if (untilEl.value && untilEl.value < from) {
    untilEl.value = from;
    showFieldHint('departUntilHint',
      `„Datum bis" kann nicht vor „Datum von" liegen – auf ${fmtDay(new Date(from))} gesetzt.`);
  }
}

// Die eigentliche Garantie: was der Browser durchgelassen hat, wird hier
// zurechtgerückt - egal ob geklickt, getippt oder eingefügt.
function enforceDateOrder(fieldId, hintId, label) {
  const el = document.getElementById(fieldId);
  const fromEl = document.getElementById('departFrom');
  const fix = () => {
    const from = fromEl.value;
    if (!el.value || !from) return;
    if (el.value < from) {
      el.value = from;
      showFieldHint(hintId, `${label} – auf ${fmtDay(new Date(from))} gesetzt.`);
    } else {
      showFieldHint(hintId, '');
    }
  };
  // Bewusst nur `change`/`blur`, nicht `input`: beim Bearbeiten eines
  // bestehenden Datums feuert `input` in Chrome nach jedem Segment und
  // würde mitten in der Eingabe dazwischenfunken.
  el.addEventListener('change', fix);
  el.addEventListener('blur', fix);
  return fix;
}
// Die Rueckgabewerte sind der Riegel vor der Suche: was auch immer im Feld
// steht, wird vor dem Absenden zurechtgerueckt.
const fixReturnDate = enforceDateOrder('returnDate', 'returnDateHint',
  'Rückreise kann nicht vor der Hinreise liegen');
const fixDepartUntil = enforceDateOrder('departUntil', 'departUntilHint',
  '„Datum bis" kann nicht vor „Datum von" liegen');

document.getElementById('departFrom').addEventListener('change', () => syncDateBounds());
// input feuert auch beim Tippen: die Grenzen mitziehen, aber ein halb
// getipptes Datum nicht schon umschreiben.
document.getElementById('departFrom').addEventListener('input', () => syncDateBounds({ pushFollowers: false }));

applyModeVisibility(activeMode);

// "Gewicht egal" greys out the matching kg field, so it's obvious the number
// no longer counts (readRouteFromForm sends null for it either way).
for (const [anyId, fieldId] of [['checkedBagKgAny', 'checkedBagKg'], ['carryOnMaxKgAny', 'carryOnMaxKg']]) {
  const anyEl = document.getElementById(anyId);
  const fieldEl = document.getElementById(fieldId);
  const sync = () => { fieldEl.disabled = anyEl.checked; fieldEl.style.opacity = anyEl.checked ? 0.5 : 1; };
  anyEl.addEventListener('change', sync);
  sync();
}

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
function rngBool(rng, pTrue) { return rng() < pTrue; }
function rngChoice(rng, arr) { return arr[Math.floor(rng() * arr.length)]; }
function rngWeighted(rng, items, weights) {
  const total = weights.reduce((a, b) => a + b, 0);
  let r = rng() * total;
  for (let i = 0; i < items.length; i++) { r -= weights[i]; if (r <= 0) return items[i]; }
  return items[items.length - 1];
}
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
 * including the hotel-amenity and transport-comfort fields, just running
 * client-side so the search tab needs no backend at all.
 * ===================================================================== */
// Deliberately NOT real booking-site names any more. Mock offers used to be
// labelled "DB Navigator", "FlixBus" etc., which made an invented price look
// like a bookable fare - a user went to DB Navigator to book a 42 EUR
// connection this app had made up, and of course found nothing. Generic
// placeholder names plus the per-offer "Beispiel" badge make the difference
// impossible to miss. Real booking-site names may only come from a real
// provider response (see travelpayoutsRawToOffer, which uses the actual
// `gate` field).
const BOOKING_SITES = {
  flight: ['Beispiel-Airline A', 'Beispiel-Airline B', 'Beispiel-Airline C'],
  train: ['Beispiel-Bahnanbieter A', 'Beispiel-Bahnanbieter B'],
  bus: ['Beispiel-Busanbieter A', 'Beispiel-Busanbieter B'],
  hotel: ['Beispiel-Hotelportal A', 'Beispiel-Hotelportal B'],
};
// IATA codes of low-cost carriers. Needed because the real price API only
// returns an airline code - without this table every real offer would count
// as non-low-cost and "Nur Low-Cost" would silently match nothing.
// Mirrored in traveldeals/providers/travelpayouts.py.
const LOW_COST_CARRIERS = new Set([
  // Europa
  'FR', 'RK', 'U2', 'EZY', 'EC', 'W6', 'W9', 'W4', 'VY', 'PC', 'DE', 'HV',
  'TO', 'X3', 'EW', '0B', 'BY', 'LS', 'DY', 'D8', 'IW', 'V7', 'ZB', 'FH',
  // Naher Osten / Asien
  'G9', 'E5', 'XY', 'J9', 'FZ', '6E', 'SG', 'IX', 'AK', 'FD', 'D7', 'TR',
  'JQ', '3K', 'GK', 'MM', 'ZG', 'VJ', 'VZ', '5J', 'Z2',
  // Amerika
  'WN', 'NK', 'F9', 'G4', 'Y4', 'VB', 'H2', 'P5', 'G3',
]);

const BAHNCARD_DISCOUNT = { '25': 0.25, '50': 0.5, '100': 1.0, '': 0.0 };
const LEGROOM_RANGE = { flight: [66, 96], train: [85, 120], bus: [70, 100] };

// Mirrors traveldeals/models.py's MEAL_PLAN_TIERS/PROPERTY_TYPES and
// providers/mock.py's amenity-probability table - same order, same weights.
const MEAL_PLAN_TIERS = ['none', 'breakfast', 'half_board', 'full_board', 'all_inclusive'];
const MEAL_PLAN_WEIGHTS = [0.35, 0.35, 0.15, 0.10, 0.05];
const PROPERTY_TYPES = ['hotel', 'apartment', 'hostel', 'resort', 'bnb', 'guesthouse', 'villa'];
const PROPERTY_TYPE_WEIGHTS = [0.45, 0.25, 0.10, 0.05, 0.08, 0.05, 0.02];
const HOTEL_AMENITY_PROBABILITY = {
  pool: 0.35, gym: 0.40, spa: 0.15, restaurant: 0.50, bar: 0.40,
  roomService: 0.30, frontDesk24h: 0.55, businessFacilities: 0.25,
  laundryService: 0.30, elevator: 0.60, balconyOrTerrace: 0.40,
  kitchen: 0.30, beachfront: 0.10, disabledAccess: 0.35,
  evCharging: 0.15, bicycleRental: 0.20, babysitting: 0.12,
  sauna: 0.15, hotTub: 0.10, nonSmoking: 0.80, familyRooms: 0.30,
  airportShuttle: 0.20,
};
// Every HotelPref.require_X flag: [formCheckboxId/prefKey, offerField, yamlKey]
// - mirrors engine.py's _HOTEL_AMENITY_REQUIREMENTS + config.py's
// _HOTEL_REQUIRE_FIELDS. Single source of truth for meetsHotelPrefs,
// readRouteFromForm, and buildYamlSnippet.
const HOTEL_AMENITY_REQUIREMENTS = [
  ['requireWifi', 'wifi', 'require_wifi'],
  ['requireFreeCancellation', 'freeCancellation', 'require_free_cancellation'],
  ['requireParking', 'parking', 'require_parking'],
  ['requireAirConditioning', 'airConditioning', 'require_air_conditioning'],
  ['requirePetsAllowed', 'petsAllowed', 'require_pets_allowed'],
  ['requirePool', 'pool', 'require_pool'],
  ['requireGym', 'gym', 'require_gym'],
  ['requireSpa', 'spa', 'require_spa'],
  ['requireRestaurant', 'restaurant', 'require_restaurant'],
  ['requireBar', 'bar', 'require_bar'],
  ['requireRoomService', 'roomService', 'require_room_service'],
  ['require24hFrontDesk', 'frontDesk24h', 'require_24h_front_desk'],
  ['requireBusinessFacilities', 'businessFacilities', 'require_business_facilities'],
  ['requireLaundryService', 'laundryService', 'require_laundry_service'],
  ['requireElevator', 'elevator', 'require_elevator'],
  ['requireBalconyOrTerrace', 'balconyOrTerrace', 'require_balcony_or_terrace'],
  ['requireKitchen', 'kitchen', 'require_kitchen'],
  ['requireBeachfront', 'beachfront', 'require_beachfront'],
  ['requireDisabledAccess', 'disabledAccess', 'require_disabled_access'],
  ['requireEvCharging', 'evCharging', 'require_ev_charging'],
  ['requireBicycleRental', 'bicycleRental', 'require_bicycle_rental'],
  ['requireBabysitting', 'babysitting', 'require_babysitting'],
  ['requireSauna', 'sauna', 'require_sauna'],
  ['requireHotTub', 'hotTub', 'require_hot_tub'],
  ['requireNonSmoking', 'nonSmoking', 'require_non_smoking'],
  ['requireFamilyRooms', 'familyRooms', 'require_family_rooms'],
  ['requireAirportShuttle', 'airportShuttle', 'require_airport_shuttle'],
];

// Mirrors traveldeals/providers/mock.py's _round_trip_addon: one combined
// price for both legs (like the real Travelpayouts API does), plus a
// synthesized return-leg departure time on route.returnDate.
function roundTripAddon(rng, route, outboundPrice, departHourPool, outboundHours) {
  if (!(route.roundTrip && route.returnDate)) return [outboundPrice, null, null];
  const returnPrice = round2(outboundPrice * rngFloat(rng, 0.8, 1.2));
  const hour = rngChoice(rng, departHourPool);
  const returnDt = atHour(route.returnDate, hour, rngChoice(rng, [0, 15, 30, 45]));
  // Der Rueckweg dauert selten exakt so lang wie der Hinweg - sonst waere
  // die getrennte Anzeige zweimal dieselbe Zahl.
  const returnHours = outboundHours == null ? null : round1(outboundHours * rngFloat(rng, 0.85, 1.2));
  return [round2(outboundPrice + returnPrice), returnDt, returnHours];
}

function transportComfortFields(rng, mode, stopWeights) {
  const [lo, hi] = LEGROOM_RANGE[mode];
  return {
    stops: rngWeighted(rng, [0, 1, 2], stopWeights),
    wifiOnboard: rngBool(rng, 0.6),
    powerOutlets: rngBool(rng, 0.55),
    legroomCm: round1(rngFloat(rng, lo, hi)),
    punctualityPct: round1(rngFloat(rng, 70, 99)),
  };
}

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
      const isLowCost = rngBool(rng, 0.5);
      const bagFee = isLowCost ? round2(rngFloat(rng, 25, 55)) : 0;
      const depart = atHour(day, hour, rngChoice(rng, [0, 15, 30, 45]));
      const [finalPrice, returnDepart, returnDurationHours] = roundTripAddon(rng, route, price, hours, duration);
      offers.push({
        mode: 'flight', isMock: true, bookingSite: rngChoice(rng, BOOKING_SITES.flight),
        price: finalPrice, currency: route.currency, depart, durationHours: duration,
        bagFee, isLowCost, returnDepart, returnDurationHours,
        // Beispieldaten, wie alles hier: Billigflieger nur Handgepäck,
        // Linienflug zusätzlich ein Koffer. Die Zeile trägt ohnehin das
        // "Beispieldaten"-Abzeichen.
        includedCarryOnKg: 8, includedCheckedBags: isLowCost ? 0 : 1,
        includedCheckedBagKg: isLowCost ? null : 23, baggageSource: 'Beispieldaten',
        ...transportComfortFields(rng, 'flight', [0.55, 0.35, 0.10]),
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
  const hours = Array.from({ length: 17 }, (_, i) => i + 5);
  for (const day of dayCandidates(route)) {
    for (const hour of rngSample(rng, hours, 3)) {
      const price = round2(basePrice * rngFloat(rng, 0.8, 1.3) * (1 - discount));
      const duration = round1(rngFloat(rng, 2.0, 7.0));
      const depart = atHour(day, hour, rngChoice(rng, [0, 15, 30, 45]));
      const basePrice2 = route.bahncard === '100' ? 0 : price;
      const [finalPrice, returnDepart, returnDurationHours] = roundTripAddon(rng, route, basePrice2, hours, duration);
      offers.push({
        mode: 'train', isMock: true, bookingSite: rngChoice(rng, BOOKING_SITES.train),
        price: finalPrice, currency: route.currency,
        depart, durationHours: duration, bagFee: 0, isLowCost: false, returnDepart, returnDurationHours,
        ...transportComfortFields(rng, 'train', [0.75, 0.20, 0.05]),
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
      const [finalPrice, returnDepart, returnDurationHours] = roundTripAddon(rng, route, price, hours, duration);
      offers.push({
        mode: 'bus', isMock: true, bookingSite: rngChoice(rng, BOOKING_SITES.bus),
        price: finalPrice, currency: route.currency, depart, durationHours: duration,
        bagFee: 0, isLowCost: false, returnDepart, returnDurationHours,
        ...transportComfortFields(rng, 'bus', [0.65, 0.30, 0.05]),
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
        mode: 'hotel', isMock: true, bookingSite: rngChoice(rng, BOOKING_SITES.hotel),
        price: round2(perNight * nights), currency: route.currency,
        depart: checkin, durationHours: nights * 24, bagFee: 0, isLowCost: false,
        nights,
        stars: rngWeighted(rng, [2, 3, 4, 5], [0.1, 0.35, 0.4, 0.15]),
        rating: round1(rngFloat(rng, 6.0, 9.8)),
        propertyType: rngWeighted(rng, PROPERTY_TYPES, PROPERTY_TYPE_WEIGHTS),
        mealPlan: rngWeighted(rng, MEAL_PLAN_TIERS, MEAL_PLAN_WEIGHTS),
        wifi: rngBool(rng, 0.85),
        freeCancellation: rngBool(rng, 0.6),
        distanceKm: round1(rngFloat(rng, 0.1, 8.0)),
        parking: rngBool(rng, 0.4),
        airConditioning: rngBool(rng, 0.7),
        petsAllowed: rngBool(rng, 0.3),
        ...Object.fromEntries(Object.entries(HOTEL_AMENITY_PROBABILITY).map(([k, p]) => [k, rngBool(rng, p)])),
      });
    }
  }
  return offers;
}

/* =========================================================================
 * Real flight prices via the HackYourTrip proxy (worker/) - optional.
 *
 * The Suche tab runs in the visitor's browser, so it can never hold the
 * real Travelpayouts token itself (anyone could read it from dev tools).
 * PROXY_URL points at a small Cloudflare Worker (see worker/README or the
 * repo README's "Live-Suche mit echten Preisen" section) that hides the
 * token server-side and proxies GET /v1/prices/cheap. Leave PROXY_URL empty
 * to keep the Suche tab on mock data only - everything below degrades
 * gracefully (empty string, network error, non-2xx response, or an empty
 * result all just fall back to mockFlightOffers()).
 * ===================================================================== */
const PROXY_URL = 'https://hackyourtrip-proxy.iamanamelessman.workers.dev';
// Requests are per month, not per day - see monthsCovering() below and the
// same reasoning in traveldeals/providers/travelpayouts.py.
const REAL_FLIGHT_MAX_MONTHS = 6;
// Base for the relative per-itinerary `link` the API returns
// ("/search/BER1809BCN1?t=..."), which points at that exact flight.
const AVIASALES_BASE = 'https://www.aviasales.com';

// Mirrors traveldeals/providers/geo.py: distance-based duration estimate,
// direct flights only - a connection's layover length has nothing to do
// with origin-destination distance, so it stays unknown (0) rather than
// guessed. Kept intentionally small (dense in Europe, sparse worldwide
// hubs) to match the routes this tool is realistically used for.
const AVERAGE_BLOCK_SPEED_KMH = 750;
const FIXED_OVERHEAD_HOURS = 0.5;
const AIRPORT_COORDS = {
  BER: [52.3667, 13.5033], MUC: [48.3538, 11.7861], FRA: [50.0379, 8.5622],
  DUS: [51.2895, 6.7668], HAM: [53.6304, 9.9882], STR: [48.6899, 9.2220],
  CGN: [50.8659, 7.1427], HAJ: [52.4611, 9.6851], NUE: [49.4987, 11.0669],
  LEJ: [51.4239, 12.2364], DTM: [51.5183, 7.6122], BRE: [53.0475, 8.7867],
  VIE: [48.1103, 16.5697], ZRH: [47.4647, 8.5492], GVA: [46.2381, 6.1090],
  SZG: [47.7933, 13.0043], INN: [47.2602, 11.3440], BSL: [47.5896, 7.5299],
  LHR: [51.4700, -0.4543], LGW: [51.1537, -0.1821], STN: [51.8860, 0.2389],
  LTN: [51.8747, -0.3683], MAN: [53.3537, -2.2750], EDI: [55.9500, -3.3725],
  GLA: [55.8642, -4.4331], DUB: [53.4213, -6.2701],
  CDG: [49.0097, 2.5479], ORY: [48.7233, 2.3794], NCE: [43.6584, 7.2159],
  LYS: [45.7256, 5.0811], MRS: [43.4393, 5.2214], TLS: [43.6291, 1.3638],
  BOD: [44.8283, -0.7156], NTE: [47.1532, -1.6110],
  AMS: [52.3086, 4.7639], BRU: [50.9014, 4.4844],
  MAD: [40.4983, -3.5676], BCN: [41.2971, 2.0785], PMI: [39.5517, 2.7388],
  VLC: [39.4893, -0.4816], SVQ: [37.4180, -5.8931], BIO: [43.3011, -2.9106],
  IBZ: [38.8729, 1.3731], AGP: [36.6749, -4.4991],
  FCO: [41.8003, 12.2389], MXP: [45.6306, 8.7281], LIN: [45.4451, 9.2767],
  VCE: [45.5053, 12.3519], NAP: [40.8860, 14.2908],
  LIS: [38.7813, -9.1359], OPO: [41.2481, -8.6814],
  CPH: [55.6180, 12.6560], ARN: [59.6519, 17.9186], OSL: [60.1976, 11.1004],
  HEL: [60.3172, 24.9633], KEF: [63.9850, -22.6056],
  WAW: [52.1657, 20.9671], PRG: [50.1008, 14.2600], BUD: [47.4298, 19.2610],
  OTP: [44.5711, 26.0850], SOF: [42.6952, 23.4062], ZAG: [45.7429, 16.0688],
  LJU: [46.2237, 14.4576], RIX: [56.9236, 23.9711], TLL: [59.4133, 24.8328],
  VNO: [54.6341, 25.2858], BEG: [44.8184, 20.3091],
  ATH: [37.9364, 23.9445], SKG: [40.5197, 22.9709], IST: [41.2753, 28.7519],
  DXB: [25.2532, 55.3657], DOH: [25.2731, 51.6081], AUH: [24.4330, 54.6511],
  SIN: [1.3644, 103.9915], HKG: [22.3080, 113.9185], NRT: [35.7720, 140.3929],
  HND: [35.5494, 139.7798], ICN: [37.4602, 126.4407], BKK: [13.6900, 100.7501],
  KUL: [2.7456, 101.7099], DEL: [28.5562, 77.1000], BOM: [19.0887, 72.8679],
  CAI: [30.1219, 31.4056], JNB: [-26.1392, 28.2460], CPT: [-33.9715, 18.6021],
  SYD: [-33.9399, 151.1753], MEL: [-37.6690, 144.8410], AKL: [-37.0082, 174.7850],
  JFK: [40.6413, -73.7781], EWR: [40.6895, -74.1745], LAX: [33.9416, -118.4085],
  ORD: [41.9742, -87.9073], MIA: [25.7959, -80.2870], SFO: [37.6213, -122.3790],
  YYZ: [43.6777, -79.6248], YUL: [45.4706, -73.7408],
  GRU: [-23.4356, -46.4731], EZE: [-34.8222, -58.5358],
};

function haversineKm([lat1, lon1], [lat2, lon2]) {
  const r = 6371;
  const toRad = d => (d * Math.PI) / 180;
  const dphi = toRad(lat2 - lat1);
  const dlambda = toRad(lon2 - lon1);
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dlambda / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

function estimateDirectFlightDurationHours(origin, destination) {
  const a = AIRPORT_COORDS[origin.toUpperCase()];
  const b = AIRPORT_COORDS[destination.toUpperCase()];
  if (!a || !b) return null;
  return round1(haversineKm(a, b) / AVERAGE_BLOCK_SPEED_KMH + FIXED_OVERHEAD_HOURS);
}

function sessionCacheGet(key) {
  try { const v = sessionStorage.getItem(key); return v ? JSON.parse(v) : null; } catch (e) { return null; }
}
function sessionCacheSet(key, value) {
  try { sessionStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* private mode etc. - fine to skip caching */ }
}

// Distinct "YYYY-MM" months the candidate dates fall into. Mirrors
// _months_covering() in travelpayouts.py: one request per month rather than
// per day, because a single-date request returns one offer while a
// month request returns dozens.
function monthsCovering(route) {
  const months = [];
  for (const day of dayCandidates(route)) {
    const m = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}`;
    if (!months.includes(m)) months.push(m);
  }
  return months;
}

// Documented Aviasales search-results deep link (named query params, not the
// fragile compact "MOW1502BKK1"-style code some older docs mention):
// https://support.travelpayouts.com/hc/en-us/articles/5711895629714
function buildBookingUrl(route, departIso, returnAt) {
  const params = new URLSearchParams({
    origin_iata: route.origin, destination_iata: route.destination,
    depart_date: departIso.slice(0, 10),
    adults: '1', children: '0', infants: '0', trip_class: '0', locale: 'de',
  });
  if (returnAt) {
    params.set('return_date', returnAt.slice(0, 10));
    params.set('one_way', 'false');
  } else {
    params.set('one_way', 'true');
  }
  return `https://search.aviasales.com/flights/?${params.toString()}`;
}

function travelpayoutsRawToOffer(raw, currency, route) {
  // Strip a trailing "Z" or "+HH:MM"/"-HH:MM" offset - keeps the naive
  // local-time convention the mock providers use (new Date(y,m,d,h,...)).
  const departIso = raw.departure_at.slice(0, 19);
  const depart = new Date(departIso);
  const stops = Number(raw.transfers ?? 0);
  let durationHours = 0;
  let arrive = depart;
  if (raw.duration_to != null) {
    // Real data (observed in practice, though not in the official docs
    // example) beats a distance guess - and unlike our own estimate, it
    // isn't limited to non-stop offers.
    durationHours = round2(raw.duration_to / 60);
    arrive = new Date(depart.getTime() + raw.duration_to * 60000);
  } else if (stops === 0) {
    const estimate = estimateDirectFlightDurationHours(route.origin, route.destination);
    if (estimate !== null) {
      durationHours = estimate;
      arrive = new Date(depart.getTime() + estimate * 3600000);
    }
  }
  const link = raw.link;
  return {
    mode: 'flight',
    // The real booking gate (Kiwi.com, Trip.com, ...) rather than a generic
    // "Aviasales" label.
    bookingSite: `${raw.gate || 'Aviasales'} (${raw.airline ?? '?'}${raw.flight_number ?? ''})`,
    price: Number(raw.price), currency, depart, durationHours,
    bagFee: 0, isLowCost: LOW_COST_CARRIERS.has((raw.airline || '').toUpperCase()), stops,
    wifiOnboard: false, powerOutlets: false, legroomCm: null, punctualityPct: null,
    // The per-itinerary link goes straight to this exact flight; only fall
    // back to the generic search URL when it's missing.
    url: link ? AVIASALES_BASE + link : buildBookingUrl(route, departIso, raw.return_at),
    returnDepart: raw.return_at ? new Date(raw.return_at.slice(0, 19)) : null,
    // Gegenstueck zu duration_to. Fehlt es, bleibt die Rueckwegdauer
    // unbekannt - null heisst hier "keine Angabe", nicht "0 Stunden", und
    // wird als solche angezeigt statt geschaetzt.
    returnDurationHours: raw.duration_back != null ? round2(raw.duration_back / 60) : null,
  };
}

// v2/prices/latest rows: date-only (no clock time), price in `value`,
// stops in `number_of_changes`, minutes in `duration`, and no link.
function latestRawToOffer(raw, currency, route) {
  const departIso = `${raw.depart_date}T00:00:00`;
  const depart = new Date(departIso);
  const minutes = Number(raw.duration || 0);
  return {
    mode: 'flight',
    bookingSite: raw.gate || 'Aviasales',
    price: Number(raw.value), currency, depart,
    durationHours: minutes ? round2(minutes / 60) : 0,
    bagFee: 0, isLowCost: false, stops: Number(raw.number_of_changes ?? 0),
    wifiOnboard: false, powerOutlets: false, legroomCm: null, punctualityPct: null,
    url: buildBookingUrl(route, departIso, null),
    returnDepart: null,
  };
}

// Why the last proxy call failed. Callers keep going on a null, but a
// silent fallback to example data left users staring at
// "Beispieldaten - nicht buchbar" with no way to tell whether the route has
// no fares, the input wasn't understood, or the proxy is simply down. The
// reason is surfaced in the results header instead of being swallowed.
let lastProxyError = '';

async function fetchProxyJson(path, params) {
  const url = `${PROXY_URL.replace(/\/$/, '')}/${path}?${params.toString()}`;
  const cacheKey = `hyt:${url}`;
  const cached = sessionCacheGet(cacheKey);
  if (cached) return cached;
  try {
    const resp = await fetch(url);
    if (!resp.ok) {
      const detail = await resp.json().then(j => j && j.error).catch(() => null);
      lastProxyError = detail || `HTTP ${resp.status}`;
      return null;
    }
    const payload = await resp.json();
    sessionCacheSet(cacheKey, payload);
    return payload;
  } catch (e) {
    lastProxyError = 'Proxy nicht erreichbar';
    return null; // this request failed - callers keep going with the rest
  }
}

// The price API only knows 2-4 letter airport/city codes, and the proxy
// rejects anything else outright. Typing "Berlin" and hitting Suchen -
// instead of picking a suggestion - therefore produced a 400 and a silent
// fall back to example data, which is exactly what it looked like from the
// outside: "the flights are still fake". Resolve the free text through the
// same Places API the autocomplete uses, so typing the city is enough.
async function resolveAirportCode(term) {
  const text = (term || '').trim();
  if (/^[A-Za-z]{2,4}$/.test(text)) return text.toUpperCase(); // already a code
  if (text.length < 2) return null;
  const cacheKey = `hyt:code:${text.toLowerCase()}`;
  const cached = sessionCacheGet(cacheKey);
  if (cached) return cached;
  try {
    const params = new URLSearchParams({ term: text, locale: 'de' });
    params.append('types[]', 'city');
    params.append('types[]', 'airport');
    const resp = await fetch(`${PLACES_API_URL}?${params.toString()}`);
    if (!resp.ok) return null;
    const data = await resp.json();
    // Prefer the city entry: its code covers all airports of that city
    // ("BER" style metro codes), which is what a user typing a city wants.
    const ranked = (data || []).slice().sort((a, b) =>
      (a.type === b.type ? 0 : a.type === 'city' ? -1 : 1) || (b.weight || 0) - (a.weight || 0));
    const code = ranked.length && ranked[0].code ? String(ranked[0].code).toUpperCase() : null;
    if (code) sessionCacheSet(cacheKey, code);
    return code;
  } catch (e) {
    return null;
  }
}

// Mirrors providers/geo.nearby_airports: airports within `radiusKm`,
// nearest first. The saving lever a metasearch engine can't personalise -
// only the traveller knows what 100 km of driving is worth to them.
function nearbyAirports(code, radiusKm, limit = 2) {
  const origin = AIRPORT_COORDS[(code || '').toUpperCase()];
  if (!origin || radiusKm <= 0) return [];
  const found = [];
  for (const [other, coords] of Object.entries(AIRPORT_COORDS)) {
    if (other === code.toUpperCase()) continue;
    const km = haversineKm(origin, coords);
    if (km <= radiusKm) found.push([other, Math.round(km)]);
  }
  found.sort((a, b) => a[1] - b[1]);
  return found.slice(0, limit);
}

// Nearby *stations* work differently from nearby airports, and the
// difference matters: there is no static table of station coordinates here,
// and inventing one would put the shown detour off by however far a city's
// station sits from its airport. So AIRPORT_COORDS is used only as a grid of
// major cities to *propose* candidates; each candidate is then resolved
// through Transitous, which returns the real stop with real coordinates, and
// the distance is measured from those.
async function fetchNearbyStations(name, radiusKm, limit = 2) {
  if (!radiusKm || !PROXY_URL) return [];
  const origin = await transitResolveStop(name);
  if (!origin || origin.lat == null) return [];

  // Generous pre-filter on the city grid: a station can sit tens of km from
  // its city's airport, so candidates are collected wide and cut precisely
  // afterwards, on the real coordinates.
  const candidates = [];
  for (const [code, coords] of Object.entries(AIRPORT_COORDS)) {
    const cityName = AIRPORT_CITY_NAMES[code];
    if (!cityName) continue;
    const rough = haversineKm([origin.lat, origin.lon], coords);
    if (rough <= radiusKm + 60) candidates.push([cityName, rough]);
  }
  candidates.sort((a, b) => a[1] - b[1]);

  const found = [];
  const seen = new Set([origin.name]);
  for (const [cityName] of candidates.slice(0, 8)) {
    const stop = await transitResolveStop(cityName);
    if (!stop || stop.lat == null || seen.has(stop.name)) continue;
    const km = Math.round(haversineKm([origin.lat, origin.lon], [stop.lat, stop.lon]));
    if (km === 0 || km > radiusKm) continue;
    seen.add(stop.name);
    found.push([stop.name, km]);
    if (found.length >= limit) break;
  }
  return found;
}

/* =========================================================================
 * Lokaler Bahn-Preis-Server (bahn-local/server.py).
 *
 * Die DB sperrt Preisabfragen von Server-IPs, lässt sie von einer Wohn-IP
 * aber durch - und nur über curls Fingerabdruck, nicht Nodes/Pythons. Der
 * kleine lokale Server (curl-Unterprozess) läuft beim Nutzer und liefert
 * genau deshalb echte Sparpreise. Diese App fragt ihn, wenn er erreichbar
 * ist; ist er es nicht (Handy, Rechner aus), fällt alles lautlos auf den
 * Transitous-Fahrplan + D-Ticket-Logik zurück - nie ein erfundener Preis,
 * nie ein Bruch.
 *
 * Die Adresse ist über localStorage überschreibbar ('bahnLocalUrl'), damit
 * später ein Pi oder Tunnel ohne Code-Änderung eingehängt werden kann.
 * ===================================================================== */
const BAHN_LOCAL_DEFAULT = 'http://127.0.0.1:8899';

/**
 * Wo der lokale Bahn-Server zu erreichen ist - der Reihe nach probiert.
 *
 * Die eigene Herkunft steht zuerst, und darauf kommt es an: wird die Seite
 * vom Server ausgeliefert, ist er genau dort. Auf dem Handy heisst das die
 * Heimnetz-Adresse des Rechners (z.B. http://192.168.1.42:8899) -
 * `127.0.0.1` waere dort das Handy selbst und damit ins Leere gezielt.
 * Kommt die Seite von https (github.io), bleibt nur der Versuch ueber die
 * Loopback-Adresse.
 */
function bahnLocalCandidates() {
  let override = null;
  try { override = localStorage.getItem('bahnLocalUrl'); } catch (e) { /* egal */ }
  if (override) return [override.replace(/\/+$/, '')];
  const list = [];
  if (location.protocol === 'http:' && location.origin) list.push(location.origin);
  if (!list.includes(BAHN_LOCAL_DEFAULT)) list.push(BAHN_LOCAL_DEFAULT);
  return list;
}

// Welche der Adressen tatsaechlich geantwortet hat. Vorher ist es nur eine
// Vermutung, deshalb steht bis dahin die erste Kandidatin da.
let _bahnLocalFound = null;
function bahnLocalUrl() {
  return _bahnLocalFound || bahnLocalCandidates()[0];
}

// Ein *negatives* Ergebnis verfaellt nach kurzer Zeit: wer den Server erst
// nach dem Oeffnen der Seite startet, soll nicht neu laden muessen. Ein
// positives haelt fuer den Seitenaufruf - da ist nichts mehr zu pruefen.
const BAHN_LOCAL_RECHECK_MS = 15000;
let _bahnLocal = { ok: null, at: 0 };
let _bahnLocalLastError = '';

async function bahnLocalReachable() {
  const now = Date.now();
  if (_bahnLocal.ok === true) return true;
  if (_bahnLocal.ok === false && now - _bahnLocal.at < BAHN_LOCAL_RECHECK_MS) return false;

  const reasons = [];
  for (const base of bahnLocalCandidates()) {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 1500);
      const res = await fetch(base + '/health', { signal: ctrl.signal });
      clearTimeout(timer);
      const body = await res.json().catch(() => ({}));
      if (res.ok && body.ok === true) {
        _bahnLocalFound = base;
        _bahnLocal = { ok: true, at: now };
        _bahnLocalLastError = '';
        return true;
      }
      reasons.push(`${base}: HTTP ${res.status}`);
    } catch (e) {
      // Nicht gestartet, oder der Browser hat die Verbindung blockiert. Der
      // Grund wird festgehalten - in der App sehen beide Faelle gleich aus.
      reasons.push(`${base}: ${e.name}`);
    }
  }
  _bahnLocal = { ok: false, at: now };
  _bahnLocalLastError = reasons.join(' · ');
  return false;
}

// In der Browser-Konsole aufrufbar: zeigt Adresse, Erreichbarkeit und den
// letzten Fehlergrund, statt dass man raten muss, warum keine Live-Preise
// erscheinen.
window.bahnLocalStatus = async () => {
  _bahnLocal = { ok: null, at: 0 };
  _bahnLocalFound = null;
  const erreichbar = await bahnLocalReachable();
  const info = {
    geprueft: bahnLocalCandidates(),
    gefunden: _bahnLocalFound,
    erreichbar,
    letzterFehler: _bahnLocalLastError,
  };
  console.log('[HackYourTrip] Lokaler Bahn-Server:', info);
  return info;
};

async function bahnLocalJson(path, params) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 30000);
  try {
    const url = bahnLocalUrl() + path + (params ? '?' + params.toString() : '');
    const res = await fetch(url, { signal: ctrl.signal });
    return await res.json();
  } finally { clearTimeout(timer); }
}

/**
 * Stationssuche bei der Bahn - mehrere Schreibweisen der Reihe nach.
 *
 * In den Flug-Kombis (Flug oder Bahn, Hin/Rueck gemischt) steht in den
 * Feldern ein IATA-Code wie "BER", denn dort ist die Ergaenzung
 * flughafenbasiert. Fuer die Bahn ist das kein Ortsname - ohne Uebersetzung
 * findet sie nichts, und die Verbindung landet ohne Preis in der Liste,
 * obwohl der Server laeuft. Deshalb dieselbe Reihenfolge wie beim Bus.
 */
function bahnStopQueries(name) {
  const queries = [];
  const push = (q) => {
    q = (q || '').trim();
    if (q && !queries.includes(q)) queries.push(q);
  };
  // "BER" -> "Berlin": ein roher Code trifft bei der Bahn leicht daneben.
  push(AIRPORT_CITY_NAMES[(name || '').toUpperCase()]);
  push(name);
  // "Münster(Westf) Hbf" -> "Münster Hbf"
  push((name || '').replace(/\s*\([^)]*\)\s*/g, ' '));
  return queries;
}

async function bahnLocalResolveStop(name) {
  for (const query of bahnStopQueries(name)) {
    let list;
    try {
      list = await bahnLocalJson('/orte', new URLSearchParams({ q: query }));
    } catch (e) { continue; }
    if (!Array.isArray(list) || !list.length) continue;
    const needle = query.trim().toLowerCase();
    const exact = list.find(o => (o.name || '').trim().toLowerCase() === needle);
    const stop = exact || list[0];
    if (stop && stop.id) return stop;
  }
  return null;
}

/* --- Deutschland-Ticket auf dem Live-Pfad -------------------------------
 * Auf dem Fahrplan-Pfad (Transitous) heissen die Gattungen REGIONAL_RAIL &
 * Co.; die DB benennt dieselben Dinge anders. Deshalb hier eine eigene
 * Zuordnung - mit derselben Dreiwertigkeit: abgedeckt / nicht abgedeckt /
 * nicht entscheidbar. Alles Unbekannte landet bewusst beim dritten Fall.
 * --------------------------------------------------------------------- */
const D_TICKET_DB_PRODUCTS = ['REGIONAL', 'SBAHN', 'UBAHN', 'TRAM', 'BUS'];
// Definitiv nicht abgedeckt. ANRUFPFLICHTIG (Anrufsammeltaxi) steht in
// keiner der beiden Listen: dort gelten je nach Verbund eigene Regeln, also
// bleibt es unentscheidbar statt geraten.
const D_TICKET_DB_EXCLUDED = ['ICE', 'EC_IC', 'IR', 'SCHIFF'];

/**
 * Deutsche Station? Zwei unabhaengige Merkmale muessen zusammenpassen: der
 * UIC-Laenderschluessel `U=80` in der Orts-ID und die mit 80 beginnende
 * EVA-Nummer. Fehlt oder widerspricht eines, lautet die Antwort "nein" -
 * und es gibt keine D-Ticket-Aussage. Die Richtung des Irrtums ist bewusst
 * gewaehlt: lieber ein fehlender Hinweis als ein falsches "0 EUR".
 */
function isGermanDbStop(stop) {
  if (!stop) return false;
  const byCountry = /(^|@)U=80(@|$)/.test(stop.id || '');
  const byEva = /^80\d+$/.test(String(stop.extId || ''));
  return byCountry && byEva;
}

function dbTicketCoverage(legs, fromStop, toStop) {
  if (!isGermanDbStop(fromStop) || !isGermanDbStop(toStop)) return null;
  const products = (legs || []).map(l => l && l.product).filter(Boolean);
  if (!products.length) return null;
  if (products.some(p => D_TICKET_DB_EXCLUDED.includes(p))) return false;
  return products.every(p => D_TICKET_DB_PRODUCTS.includes(p)) ? true : null;
}

// One trimmed DB connection -> an Offer in this app's shape. A price the DB
// did not name stays priceKnown:false - never a fabricated 0.
function bahnConnectionToOffer(conn, route, stops = {}) {
  if (!conn || !conn.depart) return null;
  const depart = new Date(conn.depart);
  if (isNaN(depart)) return null;
  const dbPrice = typeof conn.price === 'number' ? conn.price : null;
  const covered = dbTicketCoverage(conn.legs, stops.origin, stops.destination);
  // Hier zahlt sich der Live-Preis doppelt aus: bei einer abgedeckten
  // Verbindung wissen wir jetzt nicht nur, dass sie mit dem D-Ticket nichts
  // kostet, sondern auch, was sie ohne kosten wuerde - also die tatsaechliche
  // Ersparnis, in Euro.
  const freeWithDTicket = covered === true && route.deutschlandticket === true;
  const priceKnown = freeWithDTicket || dbPrice !== null;
  const lineLabel = (conn.legs || []).map(l => l.line).filter(Boolean).join(' → ');
  return {
    mode: 'train',
    isMock: false,
    priceKnown,
    price: freeWithDTicket ? 0 : (dbPrice !== null ? dbPrice : 0),
    dTicketCovered: covered,
    // Der Normalpreis bleibt erhalten, auch wenn er wegen des Tickets nicht
    // gezahlt wird - sonst liesse sich die Ersparnis nicht mehr beziffern.
    priceWithoutDTicket: covered === true ? dbPrice : null,
    priceNote: freeWithDTicket ? 'im Deutschland-Ticket enthalten' : '',
    currency: conn.currency || route.currency,
    // A real, bookable fare from bahn.de - the deep link goes to the booking.
    bookingSite: 'bahn.de',
    url: 'https://www.bahn.de/buchung/fahrplan/suche',
    lineLabel,
    depart,
    durationHours: conn.durationSeconds ? round2(conn.durationSeconds / 3600) : null,
    bagFee: 0,
    isLowCost: false,
    returnDepart: null,
    stops: Number(conn.transfers || 0),
    wifiOnboard: false,
    powerOutlets: false,
    legroomCm: null,
    punctualityPct: null,
    track: '',
    // Marks the offer as coming from the live DB source, for a badge and so
    // nothing downstream mistakes it for the price-less timetable offers.
    priceSource: 'db-live',
  };
}

async function fetchLocalBahnOffers(route) {
  if (!(await bahnLocalReachable())) return null;
  let fromStop, toStop;
  try {
    [fromStop, toStop] = await Promise.all([
      bahnLocalResolveStop(route.origin),
      bahnLocalResolveStop(route.destination),
    ]);
  } catch (e) { return null; }
  if (!fromStop || !toStop) return null;
  const fromId = fromStop.id, toId = toStop.id;

  const offers = [];
  const seen = new Set();
  for (const day of dayCandidates(route).slice(0, TRANSIT_MAX_DAYS)) {
    let data;
    try {
      data = await bahnLocalJson('/fahrplan', new URLSearchParams({
        from: fromId, to: toId, date: isoDay(day),
        class: route.bahncard === '100' ? '1' : '2',
      }));
    } catch (e) { continue; }
    for (const conn of (data && data.connections) || []) {
      const offer = bahnConnectionToOffer(conn, route, { origin: fromStop, destination: toStop });
      if (!offer) continue;
      if (isoDay(offer.depart) !== isoDay(day)) continue; // rolled past midnight
      const key = offer.depart.toISOString() + '|' + offer.lineLabel;
      if (seen.has(key)) continue;
      seen.add(key);
      offers.push(offer);
    }
  }
  return offers;
}

// One direction, one mode, priced sources first - shared by the plain search
// and the nearby-station variants so both stay in step.
async function groundOffersFor(route, mode) {
  if (mode === 'train') {
    // Real DB fares when the local server is up; otherwise the timetable
    // (price-less, but with the Deutschland-Ticket logic) as before.
    const live = await fetchLocalBahnOffers(route);
    if (live && live.length) return live;
    return (await fetchRealTransitOffers(route, 'train')) || [];
  }
  const priced = mode === 'bus' ? await fetchFlixbusOffers(route) : [];
  const timetable = await fetchRealTransitOffers(route, mode);
  return [...priced, ...(timetable || [])];
}

async function fetchGroundOffersWithNeighbours(route, mode) {
  const base = await groundOffersFor(route, mode);
  if (!route.nearbyOriginKm && !route.nearbyDestinationKm) return base;

  const offers = [...base];
  const [origins, destinations] = await Promise.all([
    fetchNearbyStations(route.origin, route.nearbyOriginKm),
    fetchNearbyStations(route.destination, route.nearbyDestinationKm),
  ]);
  for (const [origin, originKm] of [[route.origin, 0], ...origins]) {
    for (const [destination, destinationKm] of [[route.destination, 0], ...destinations]) {
      if (!originKm && !destinationKm) continue;
      for (const offer of await groundOffersFor({ ...route, origin, destination }, mode)) {
        offer.altOrigin = originKm ? origin : '';
        offer.altDestination = destinationKm ? destination : '';
        offer.detourKm = originKm + destinationKm;
        offers.push(offer);
      }
    }
  }
  return offers;
}

// Wraps the single-airport search: runs it again for nearby airports and
// tags every extra offer with where it actually departs from, so nothing
// can silently look like a departure from the airport that was searched.
async function fetchFlightOffersWithNeighbours(route) {
  const base = await fetchRealFlightOffers(route);
  if (!route.nearbyOriginKm && !route.nearbyDestinationKm) return base;

  const offers = base ? [...base] : [];
  const origins = [[route.origin, 0], ...nearbyAirports(route.origin, route.nearbyOriginKm)];
  const destinations = [[route.destination, 0], ...nearbyAirports(route.destination, route.nearbyDestinationKm)];
  for (const [origin, originKm] of origins) {
    for (const [destination, destinationKm] of destinations) {
      if (!originKm && !destinationKm) continue; // already searched
      const found = await fetchRealFlightOffers({ ...route, origin, destination });
      for (const offer of found || []) {
        offer.altOrigin = originKm ? origin : '';
        offer.altDestination = destinationKm ? destination : '';
        offer.detourKm = originKm + destinationKm;
        offers.push(offer);
      }
    }
  }
  return offers;
}

async function fetchRealFlightOffers(route) {
  if (!PROXY_URL) return null; // not configured - caller falls back to mock
  lastProxyError = '';

  // Whatever stands in the Von/Nach fields has to become an airport code
  // first; free text is rejected by the price API (see resolveAirportCode).
  const [origin, destination] = await Promise.all([
    resolveAirportCode(route.origin),
    resolveAirportCode(route.destination),
  ]);
  if (!origin || !destination) {
    lastProxyError = `„${origin ? route.destination : route.origin}" nicht als Flughafen/Stadt erkannt`;
    return null;
  }
  // Everything downstream (query + booking links) must use the resolved
  // codes, not the raw text the user typed.
  route = { ...route, origin, destination };

  const roundTrip = Boolean(route.roundTrip && route.returnDate);
  const wantedDays = new Set(dayCandidates(route).map(isoDay));
  const offers = [];
  const seen = new Set();

  // Ryanair first: live bookable fares from the airline itself beat a cache
  // of fares somebody saw once. It only knows its own routes, so whatever it
  // returns is added to - never substituted for - the Travelpayouts results.
  for (const offer of await fetchRyanairOffers(route)) {
    if (!wantedDays.has(isoDay(offer.depart))) continue;
    seen.add(`${offer.depart.toISOString()}|${offer.bookingSite}|${offer.price}`);
    offers.push(offer);
  }
  // Skiplagged covers the carriers Ryanair doesn't - the two barely
  // overlap, so both get asked and the results merged.
  for (const offer of await fetchSkiplaggedOffers(route)) {
    if (!wantedDays.has(isoDay(offer.depart))) continue;
    const key = `${offer.depart.toISOString()}|${offer.bookingSite}|${offer.price}`;
    if (seen.has(key)) continue;
    seen.add(key);
    offers.push(offer);
  }
  // Ryanair and Skiplagged cover only part of the market, so their failures
  // are the least informative thing that could be reported. Park the reason
  // and let the other sources speak first - otherwise one hiccup at an
  // optional source replaces "keine Preise für dieses Datum" with "HTTP 500".
  const optionalSourceError = lastProxyError;
  lastProxyError = '';
  // Did a source actually answer? If one did and simply had nothing for this
  // route, "keine Preise hinterlegt" is the true reason - reporting another
  // source's transport error instead would misdirect the user.
  let answered = false;

  // Offers the API did return for this route, but on a day outside the flex
  // window. They used to be dropped without trace, which is why a search
  // with 0 Flex-Tagen on a thin route looked like "no data at all" - the
  // data existed, just two days over. Kept so the fallback message can name
  // the dates that would actually work.
  const nearMisses = [];

  const push = (offer) => {
    // The month query deliberately over-fetches; the flex window decides
    // what actually counts, and identical itineraries collapse to one.
    if (!wantedDays.has(isoDay(offer.depart))) {
      nearMisses.push(offer);
      return;
    }
    const key = `${offer.depart.toISOString()}|${offer.bookingSite}|${offer.price}`;
    if (seen.has(key)) return;
    seen.add(key);
    offers.push(offer);
  };

  for (const month of monthsCovering(route).slice(0, REAL_FLIGHT_MAX_MONTHS)) {
    const base = {
      origin: route.origin, destination: route.destination,
      currency: route.currency.toLowerCase(), limit: '1000', sorting: 'price',
    };
    const forDates = new URLSearchParams({
      ...base, departure_at: month, one_way: roundTrip ? 'false' : 'true',
    });
    if (roundTrip) {
      // A specific return date returns nothing from this API; the return
      // *month* is what works.
      const rd = route.returnDate;
      forDates.set('return_at', `${rd.getFullYear()}-${String(rd.getMonth() + 1).padStart(2, '0')}`);
    }
    const payload = await fetchProxyJson('cheap', forDates);
    if (payload && payload.success !== false) {
      answered = true;
      const currency = (payload.currency || route.currency).toUpperCase();
      for (const raw of payload.data || []) {
        if (raw && raw.price) push(travelpayoutsRawToOffer(raw, currency, route));
      }
    }

    // Second index, one-way only (it returns nothing for round trips).
    if (roundTrip) continue;
    const latest = await fetchProxyJson('latest', new URLSearchParams({
      ...base, one_way: 'true', period_type: 'month', beginning_of_period: `${month}-01`,
    }));
    if (latest && latest.success !== false) {
      answered = true;
      const currency = (latest.currency || route.currency).toUpperCase();
      for (const raw of latest.data || []) {
        if (raw && raw.value) push(latestRawToOffer(raw, currency, route));
      }
    }
  }

  // Nothing on the requested days, but something on nearby ones: say which,
  // instead of leaving the user with "keine echten Preise" for a route that
  // demonstrably has some. Thin routes often have fares on only a handful of
  // days per month, and with 0 Flex-Tagen that is easy to miss by two days.
  if (!offers.length && nearMisses.length) {
    const cheapestPerDay = new Map();
    for (const o of nearMisses) {
      const day = isoDay(o.depart);
      if (!cheapestPerDay.has(day) || o.price < cheapestPerDay.get(day).price) {
        cheapestPerDay.set(day, o);
      }
    }
    const target = dayCandidates(route)[0];
    const nearest = [...cheapestPerDay.values()]
      .sort((a, b) => Math.abs(a.depart - target) - Math.abs(b.depart - target))
      .slice(0, 3)
      .map(o => `${fmtDay(o.depart)} ab ${o.price.toFixed(0)} ${o.currency}`);
    lastProxyError = `Für dieses Datum sind dort keine Preise hinterlegt – wohl aber für ${nearest.join(', ')}`;
  }
  // The parked error is a last resort: only when nothing answered at all.
  if (!offers.length && !lastProxyError && !answered && optionalSourceError) {
    lastProxyError = optionalSourceError;
  }
  return offers;
}

/* =========================================================================
 * Real, bookable Ryanair fares - free, no key, no account.
 * Mirrors traveldeals/providers/ryanair.py.
 *
 * Unlike the Travelpayouts index (a cache of fares recently *seen*), these
 * come straight from the airline and are live and bookable. The catch is
 * stated rather than hidden: Ryanair only knows Ryanair routes, so this
 * complements Travelpayouts instead of replacing it - both pools are merged.
 *
 * One request covers the whole flex window, because the fare finder takes a
 * date range directly.
 * ===================================================================== */
const RYANAIR_FARES_PER_REQUEST = 200;
// The airline's own search URL, built from the parameters its site uses. A
// wrong guess lands on the search form rather than an error page - the same
// trade-off already documented for the bahn.de links.
const RYANAIR_BOOKING_BASE = 'https://www.ryanair.com/de/de/trip/flights/select';

function ryanairBookingUrl(route, departDay, returnDay) {
  const params = new URLSearchParams({
    adults: '1', teens: '0', children: '0', infants: '0',
    originIata: route.origin, destinationIata: route.destination,
    dateOut: departDay, isConnectedFlight: 'false', discount: '0',
    isReturn: returnDay ? 'true' : 'false',
  });
  if (returnDay) params.set('dateIn', returnDay);
  return `${RYANAIR_BOOKING_BASE}?${params.toString()}`;
}

function ryanairFareToOffer(fare, route, roundTrip) {
  const outbound = fare.outbound || {};
  if (!outbound.departureDate || !outbound.arrivalDate) return null;
  // For a round trip the combined total lives in summary.price; the per-leg
  // price would understate what the trip actually costs.
  const priceBlock = roundTrip ? ((fare.summary || {}).price || {}) : (outbound.price || {});
  if (priceBlock.value == null) return null;

  const inbound = fare.inbound || {};
  const depart = new Date(outbound.departureDate);
  const arrive = new Date(outbound.arrivalDate);
  // Der Rueckflug bringt seine eigenen Zeiten mit - sonst waere seine Dauer
  // im kombinierten Ticket unsichtbar.
  const returnDuration = (inbound.departureDate && inbound.arrivalDate)
    ? round2((new Date(inbound.arrivalDate) - new Date(inbound.departureDate)) / 3600000)
    : null;
  const flightNumber = outbound.flightNumber || 'FR';
  return {
    mode: 'flight',
    bookingSite: `Ryanair (${flightNumber})`,
    lineLabel: flightNumber,
    price: Number(priceBlock.value),
    currency: (priceBlock.currencyCode || route.currency).toUpperCase(),
    depart,
    durationHours: round2((arrive - depart) / 3600000),
    // Ryanair sells the seat only; the checked-bag fee depends on route and
    // season, so it stays 0 rather than being guessed at.
    bagFee: 0,
    isLowCost: true,
    stops: 0, // the fare finder returns non-stop fares only
    wifiOnboard: false, powerOutlets: false, legroomCm: null, punctualityPct: null,
    url: ryanairBookingUrl(route, outbound.departureDate.slice(0, 10),
                            inbound.departureDate ? inbound.departureDate.slice(0, 10) : null),
    returnDepart: inbound.departureDate ? new Date(inbound.departureDate) : null,
    returnDurationHours: returnDuration,
  };
}

async function fetchRyanairOffers(route) {
  if (!PROXY_URL) return [];
  const days = dayCandidates(route);
  if (!days.length) return [];
  const roundTrip = Boolean(route.roundTrip && route.returnDate);

  const params = new URLSearchParams({
    departureAirportIataCode: route.origin,
    arrivalAirportIataCode: route.destination,
    outboundDepartureDateFrom: isoDay(days[0]),
    outboundDepartureDateTo: isoDay(days[days.length - 1]),
    currency: route.currency.toUpperCase(),
    language: 'de', market: 'de-de', limit: String(RYANAIR_FARES_PER_REQUEST),
  });
  if (roundTrip) {
    params.set('inboundDepartureDateFrom', isoDay(route.returnDate));
    params.set('inboundDepartureDateTo', isoDay(route.returnDate));
  }
  const payload = await fetchProxyJson(roundTrip ? 'ryanair/roundTripFares' : 'ryanair/oneWayFares', params);
  const offers = [];
  for (const fare of (payload && payload.fares) || []) {
    const offer = ryanairFareToOffer(fare, route, roundTrip);
    if (offer) offers.push(offer);
  }
  return offers;
}

/* =========================================================================
 * Skiplagged - the full-service carriers Ryanair doesn't fly.
 * Mirrors traveldeals/providers/skiplagged.py.
 *
 * Quotes in USD: the API names no currency and ignores a `currency`
 * parameter, so it was established by evidence rather than assumed - the
 * site renders "$", and BER->BCN was 62.00 there where Ryanair said
 * 53.36 EUR (ratio 0.86, the EUR/USD rate). Converted, never relabelled.
 *
 * Hidden-city fares are deliberately not surfaced: they breach airline
 * conditions of carriage and can cost a traveller their frequent-flyer
 * account. Only the regular `depart` list is read.
 * ===================================================================== */
const SKIPLAGGED_SOURCE_CURRENCY = 'USD';
const SKIPLAGGED_MAX_DAYS = 3;
const SKIPLAGGED_MAX_PER_DAY = 40;

function skiplaggedEntryToOffer(entry, flights, airlines, route, day, rates) {
  // entry: [[price_cents], [], token, flight_id]
  const priceCents = entry && entry[0] && entry[0][0];
  const flight = flights[entry && entry[3]];
  if (priceCents == null || !flight) return null;
  const segments = flight[0] || [];
  const first = segments[0];
  const last = segments[segments.length - 1];
  if (!first || !last) return null;

  const flightNumber = first[0] || '';
  const airline = airlines[flightNumber.slice(0, 2)] || flightNumber.slice(0, 2) || 'Airline';
  return {
    mode: 'flight',
    bookingSite: `${airline} (${flightNumber})`,
    lineLabel: segments.map(seg => seg[0]).join(' → '),
    price: convert(round2(priceCents / 100), SKIPLAGGED_SOURCE_CURRENCY, route.currency, rates),
    currency: route.currency,
    depart: new Date(first[2].slice(0, 19)),
    durationHours: round2((flight[1] || 0) / 3600),
    bagFee: 0,
    isLowCost: LOW_COST_CARRIERS.has(flightNumber.slice(0, 2).toUpperCase()),
    stops: Math.max(segments.length - 1, 0),
    wifiOnboard: false, powerOutlets: false, legroomCm: null, punctualityPct: null,
    url: `https://skiplagged.com/flights/${route.origin}/${route.destination}/${day}`,
    returnDepart: null,
  };
}

async function fetchSkiplaggedOffers(route) {
  if (!PROXY_URL) return [];
  const rates = await getRatesPerEur();
  const offers = [];
  for (const day of dayCandidates(route).slice(0, SKIPLAGGED_MAX_DAYS)) {
    const iso = isoDay(day);
    const payload = await fetchProxyJson('skiplagged', new URLSearchParams({
      from: route.origin, to: route.destination, depart: iso, return: '', sort: 'cost',
    }));
    if (!payload) continue;
    const flights = payload.flights || {};
    const airlines = payload.airlines || {};
    for (const entry of (payload.depart || []).slice(0, SKIPLAGGED_MAX_PER_DAY)) {
      const offer = skiplaggedEntryToOffer(entry, flights, airlines, route, iso, rates);
      if (offer) offers.push(offer);
    }
  }
  return offers;
}

/* =========================================================================
 * Real, bookable FlixBus fares - free, no key, no account.
 * Mirrors traveldeals/providers/flixbus.py.
 *
 * This is what finally gives the *ground* modes a real price to compare
 * against a flight. Transitous knows the trains but not what they cost;
 * FlixBus knows both. Verified live: Berlin -> Munich 21.48 EUR fare /
 * 22.47 EUR with booking fee, 07:15 -> 17:35, 50 seats left.
 *
 * City UUIDs are mandatory - the numeric legacy_id from the same
 * autocomplete response is rejected with "Signature ... is invalid".
 * ===================================================================== */
const FLIXBUS_MAX_DAYS = 4;
const FLIXBUS_BOOKING_BASE = 'https://shop.flixbus.de/search';

/* FlixBus sucht *Städte* - der Bus-Tab schlägt aber Bahnhöfe vor ("Hamburg
 * Hbf"), und die Autocomplete antwortet auf alles irgendetwas. Live gemessen:
 *
 *   "Hamburg Hbf"        -> 1. Treffer Berlin      (Hamburg erst an 2.)
 *   "Köln Hbf"           -> 1. Treffer Berlin      (Köln erst an 2.)
 *   "Münster(Westf) Hbf" -> 1. Treffer Ascheberg   (Münster gar nicht dabei)
 *
 * Den ersten Treffer ungeprüft zu nehmen hieß also nicht bloß "keine
 * Buspreise", sondern: eine Suche Hamburg->Köln fragte FlixBus in Wahrheit
 * nach Berlin->Berlin. Deshalb zwei Dinge: die Anfrage wird auf den Stadtnamen
 * zurückgeschnitten, und der Treffer muss zur Anfrage passen. */
const FLIXBUS_STATION_SUFFIX = /\s*(hauptbahnhof|busbahnhof|bahnhof|hbf|zob|bf)\.?$/i;

// Vergleichsform: Groß/klein, Akzente, Umlaute und Satzzeichen weg, damit
// "München"/"Muenchen" und "Halle(Saale)"/"Halle (Saale)" dasselbe sind.
function foldPlaceName(name) {
  return (name || '').toLowerCase()
    // Vor der Unicode-Zerlegung: die wuerde aus "ü" ein blankes "u" machen,
    // und "München" passte dann nicht mehr zu "Muenchen".
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]/g, '');
}

// Anfragen von der genauesten zur gröbsten - die erste, die einen passenden
// Treffer liefert, gewinnt.
function flixbusCityQueries(name) {
  const queries = [];
  const push = (q) => {
    q = (q || '').trim();
    if (q && !queries.includes(q)) queries.push(q);
  };
  // IATA zuerst übersetzen: "BER" konkurriert sonst mit "Bergen".
  push(AIRPORT_CITY_NAMES[(name || '').toUpperCase()]);
  push(name);
  const stripped = (name || '').replace(FLIXBUS_STATION_SUFFIX, '');
  push(stripped);
  // "Münster(Westf)" -> "Münster"
  push(stripped.replace(/\s*\([^)]*\)\s*/g, ' '));
  return queries;
}

function flixbusPickCity(hits, query) {
  const wanted = foldPlaceName(query);
  if (!wanted) return null;
  let prefixHit = null;
  for (const hit of hits) {
    if (!hit || !hit.id || !hit.name) continue;
    const found = foldPlaceName(hit.name);
    if (!found) continue;
    if (found === wanted) return hit;  // exakter Treffer schlägt alles
    // "Berlin" zu "Berlin Hbf" und "BER" zu "Berlin" - aber nie "Berlin" zu
    // "Hamburg Hbf". "Berlin (Flughafen)" passt bewusst auch nicht.
    if (!prefixHit && (wanted.startsWith(found) || found.startsWith(wanted))) prefixHit = hit;
  }
  return prefixHit;
}

// Die Umkreis-Suche fragt dieselben Orte wieder und wieder ab.
const flixbusCityCache = new Map();

async function flixbusResolveCity(name) {
  if (flixbusCityCache.has(name)) return flixbusCityCache.get(name);
  let found = null;
  for (const query of flixbusCityQueries(name)) {
    const payload = await fetchProxyJson('flixbus/cities', new URLSearchParams({ q: query, lang: 'de' }));
    found = flixbusPickCity(Array.isArray(payload) ? payload : [], query);
    if (found) break;
  }
  flixbusCityCache.set(name, found);
  return found;
}

function flixbusResultToOffer(result, route, origin, destination, day) {
  // Sold out or otherwise unbookable rides are not offers.
  if (result.status !== 'available') return null;
  const price = result.price || {};
  // What the customer actually pays, not the headline fare - a price that
  // grows at checkout is exactly the surprise this project avoids.
  const total = price.total_with_platform_fee ?? price.total;
  const depart = (result.departure || {}).date;
  const arrive = (result.arrival || {}).date;
  if (total == null || !depart || !arrive) return null;

  const duration = result.duration || {};
  const legs = result.legs || [];
  const params = new URLSearchParams({
    departureCity: origin.id, arrivalCity: destination.id,
    rideDate: fmtDay(day), adult: '1',
  });
  return {
    mode: 'bus',
    bookingSite: `FlixBus (${(result.provider || 'flixbus')})`,
    price: Number(total),
    currency: route.currency.toUpperCase(),
    // The offset is already the stop's local time, which is the convention
    // everywhere else here - so it is dropped, not converted.
    depart: new Date(depart.slice(0, 19)),
    durationHours: round2((duration.hours || 0) + (duration.minutes || 0) / 60),
    bagFee: 0,
    isLowCost: true,
    stops: Math.max(legs.length - 1, 0),
    wifiOnboard: false, powerOutlets: false, legroomCm: null, punctualityPct: null,
    url: `${FLIXBUS_BOOKING_BASE}?${params.toString()}`,
    returnDepart: null,
    seatsLeft: (result.available || {}).seats ?? null,
  };
}

// Warum es für den Bus keinen Preis gab, in der Sprache des Nutzers - leer,
// wenn es einen gab. Ohne das steht bei jeder Zeile nur "Preis beim
// Anbieter", und das liest sich wie ein kaputtes Programm statt wie
// "FlixBus fährt hier nicht".
let lastFlixbusNote = '';

async function fetchFlixbusOffers(route) {
  lastFlixbusNote = '';
  if (!PROXY_URL) {
    lastFlixbusNote = 'Kein Proxy konfiguriert';
    return [];
  }
  const [origin, destination] = await Promise.all([
    flixbusResolveCity(route.origin),
    flixbusResolveCity(route.destination),
  ]);
  if (!origin || !destination) {
    const missing = [!origin ? route.origin : null, !destination ? route.destination : null].filter(Boolean);
    lastFlixbusNote = `FlixBus kennt ${missing.map(m => `„${m}"`).join(' und ')} nicht als Stadt`;
    return [];
  }

  const offers = [];
  for (const day of dayCandidates(route).slice(0, FLIXBUS_MAX_DAYS)) {
    const payload = await fetchProxyJson('flixbus/search', new URLSearchParams({
      from_city_id: origin.id, to_city_id: destination.id,
      departure_date: fmtDay(day), products: '{"adult":1}',
      currency: route.currency.toUpperCase(), locale: 'de',
      search_by: 'cities', include_after_midnight_rides: '1',
    }));
    for (const trip of (payload && payload.trips) || []) {
      // `results` is a dict keyed by trip uid, not a list.
      for (const result of Object.values(trip.results || {})) {
        const offer = flixbusResultToOffer(result, route, origin, destination, day);
        if (offer) offers.push(offer);
      }
    }
  }
  if (!offers.length) {
    lastFlixbusNote = `FlixBus fährt ${origin.name} → ${destination.name} an diesen Tagen nicht`;
  }
  return offers;
}

/* =========================================================================
 * Real train/bus connections via Transitous (MOTIS) - free, no key, no
 * account. Mirrors traveldeals/providers/transitous.py.
 *
 * These offers carry NO price: Transitous serves official timetable feeds,
 * which contain no fares. Every offer here is flagged priceKnown: false, and
 * the whole pipeline below - filtering, ranking, rendering - is written to
 * treat that as "unknown", never as "free" and never as a number to show.
 * Making one up instead is exactly how a 42 EUR train that did not exist
 * once ended up on screen.
 * ===================================================================== */
const TRANSIT_DEPART_ANCHORS = ['06:00', '12:00', '18:00'];
const TRANSIT_ITINERARIES_PER_REQUEST = 5;
// A free community service answers these requests; a wide flex window must
// not turn into dozens of them. Anchors x days is the real request count.
const TRANSIT_MAX_DAYS = 4;

// Which MOTIS leg modes actually count as the searched mode. Anything else
// (WALK, SUBWAY, ...) is fine as a connecting leg but doesn't make the
// itinerary a long-distance train or coach journey.
const TRANSIT_LEG_MODES = {
  train: ['HIGHSPEED_RAIL', 'LONG_DISTANCE', 'NIGHT_RAIL', 'REGIONAL_FAST_RAIL', 'REGIONAL_RAIL', 'RAIL'],
  bus: ['COACH', 'BUS'],
};
// Deliberately wider than the above: getting to the long-distance station
// usually needs a local leg, and forbidding those drops valid connections.
const TRANSIT_REQUEST_MODES = {
  train: 'HIGHSPEED_RAIL,LONG_DISTANCE,NIGHT_RAIL,REGIONAL_FAST_RAIL,REGIONAL_RAIL,SUBURBAN,SUBWAY,TRAM,WALK',
  bus: 'COACH,BUS,SUBURBAN,SUBWAY,TRAM,WALK',
};

/* ---------------------------------------------------------------------
 * Deutschland-Ticket coverage.
 *
 * DB blocks every automated fare lookup (measured 07.08.2026: the station
 * search answers 200, the fare endpoint 403), so a train price cannot be
 * fetched. But for one large class of journeys the fare does not need to be
 * fetched at all - it is *derivable*. The Deutschland-Ticket covers all
 * local and regional transport in Germany. So if every leg of a connection
 * is regional and the journey stays inside Germany, a ticket holder pays
 * nothing extra. That is a fact, not an estimate.
 *
 * This deliberately only answers where it can be sure: one long-distance
 * leg (ICE/IC/EC, night train, coach) makes it false, and anything touching
 * a non-German stop or an unfamiliar leg mode yields null - "cannot tell" -
 * rather than a guess. A wrong "0 EUR" would be worse than no answer.
 * ------------------------------------------------------------------- */
const D_TICKET_MODES = ['REGIONAL_FAST_RAIL', 'REGIONAL_RAIL', 'SUBURBAN',
                         'SUBWAY', 'TRAM', 'BUS', 'WALK'];
// Listed separately rather than derived as "not in D_TICKET_MODES", so an
// unfamiliar mode string from a new feed yields null instead of being
// silently declared covered.
const D_TICKET_EXCLUDED_MODES = ['HIGHSPEED_RAIL', 'LONG_DISTANCE', 'NIGHT_RAIL', 'COACH'];

function isGermanStop(stop) {
  const country = ((stop && stop.country) || '').trim().toLowerCase();
  return country === 'deutschland' || country === 'germany' || country === 'de';
}

/**
 * true  - every leg is regional and the journey stays in Germany
 * false - at least one leg is long-distance, so the ticket does not cover it
 * null  - not decidable (journey leaves Germany, or an unknown leg mode)
 */
function dTicketCoverage(itinerary, origin, destination) {
  if (!isGermanStop(origin) || !isGermanStop(destination)) return null;
  const legs = (itinerary.legs || []).filter(l => l && l.mode);
  if (!legs.length) return null;
  for (const leg of legs) {
    if (D_TICKET_EXCLUDED_MODES.includes(leg.mode)) return false;
  }
  return legs.every(l => D_TICKET_MODES.includes(l.mode)) ? true : null;
}

// MOTIS answers in UTC ("2026-09-15T08:37:00Z"); everything else in this app
// works with Date objects read in wall-clock terms (getHours() etc). So a
// timestamp is re-read in the *station's* timezone and rebuilt as a local
// Date with those wall-clock parts - a train leaving Berlin at 10:37 then
// reads as 10:37 no matter which timezone the visitor's browser is in.
function zonedWallClock(utcIso, tz) {
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(new Date(utcIso)); // "2026-09-15 10:37:00"
}

function zonedDate(utcIso, tz) {
  try {
    const [datePart, timePart] = zonedWallClock(utcIso, tz).split(' ');
    const [y, mo, d] = datePart.split('-').map(Number);
    const [h, mi] = timePart.split(':').map(Number);
    return new Date(y, mo - 1, d, h, mi);
  } catch (e) {
    return new Date(utcIso); // unknown timezone - browser-local is the best guess left
  }
}

// The reverse: a wall-clock time in `tz` -> the UTC instant to ask MOTIS for.
// Single-pass offset lookup, which can be an hour off exactly across a DST
// switch - the anchors are 06:00/12:00/18:00, never inside that 02:00-03:00
// window, and being an hour early on a search anchor costs nothing anyway.
function anchorToUtcIso(day, hhmm, tz) {
  const [h, mi] = hhmm.split(':').map(Number);
  const asIfUtc = Date.UTC(day.getFullYear(), day.getMonth(), day.getDate(), h, mi);
  let offsetMs = 0;
  try {
    const [datePart, timePart] = zonedWallClock(new Date(asIfUtc).toISOString(), tz).split(' ');
    const [y, mo, d] = datePart.split('-').map(Number);
    const [hh, mm, ss] = timePart.split(':').map(Number);
    offsetMs = Date.UTC(y, mo - 1, d, hh, mm, ss) - asIfUtc;
  } catch (e) {
    offsetMs = 0; // treat as UTC
  }
  return new Date(asIfUtc - offsetMs).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

function transitLegLabel(leg) {
  for (const key of ['displayName', 'tripShortName', 'routeShortName', 'routeLongName']) {
    const value = (leg[key] || '').trim();
    if (value) return value;
  }
  return (leg.mode || '').replace(/_/g, ' ');
}

// The geocoder mixes stations (type STOP) with POIs (type PLACE) - the top
// hit for "München Hbf" was a sauna next to the station. Only STOPs route.
async function transitResolveStop(text) {
  const payload = await fetchProxyJson('transit/geocode', new URLSearchParams({ text, language: 'de' }));
  const stops = (Array.isArray(payload) ? payload : []).filter(h => h && h.type === 'STOP' && h.id);
  if (!stops.length) return null;
  const needle = text.trim().toLowerCase();
  return stops.find(h => (h.name || '').trim().toLowerCase() === needle) || stops[0];
}

function transitItineraryToOffer(itinerary, mode, route, tz, stops = {}) {
  const legs = itinerary.legs || [];
  const transitLegs = legs.filter(l => TRANSIT_LEG_MODES[mode].includes(l.mode));
  // A pure walking/local-transport result is real but not the train or coach
  // the user is shopping for.
  if (!transitLegs.length || !itinerary.startTime || !itinerary.endTime) return null;

  const agencies = [];
  for (const leg of transitLegs) {
    const agency = (leg.agencyName || '').trim();
    if (agency && !agencies.includes(agency)) agencies.push(agency);
  }
  const covered = dTicketCoverage(itinerary, stops.origin, stops.destination);
  // Covered *and* the traveller holds the ticket: the marginal fare really
  // is zero, so this is a known price, not a missing one. Without the
  // ticket the coverage is shown as information only - the fare is still
  // unknown, and pretending otherwise is the exact failure this codebase
  // is built to avoid.
  const freeWithDTicket = covered === true && route.deutschlandticket === true;

  return {
    mode,
    isMock: false,
    // The one field that makes all the difference: this is a real
    // connection whose fare this source simply does not carry.
    priceKnown: freeWithDTicket,
    price: 0,
    dTicketCovered: covered,
    priceNote: freeWithDTicket ? 'im Deutschland-Ticket enthalten' : '',
    currency: route.currency,
    // An operator name from an official feed is a fact, and nothing here
    // claims a bookable price, so showing it verbatim is safe.
    bookingSite: agencies.join(' / ') || 'Transitous',
    lineLabel: transitLegs.map(transitLegLabel).join(' → '),
    depart: zonedDate(itinerary.startTime, tz),
    durationHours: round2((itinerary.duration || 0) / 3600),
    bagFee: 0,
    isLowCost: false,
    returnDepart: null,
    stops: Number(itinerary.transfers ?? 0),
    // Not "no wifi" but "not stated": GTFS carries no on-board amenities, so
    // these stay false and a search that *requires* them filters these out
    // rather than getting a claim nobody verified.
    wifiOnboard: false,
    powerOutlets: false,
    legroomCm: null,
    punctualityPct: null,
    url: '', // MOTIS itineraries have no booking URL - the operator links below do
    track: (legs[0]?.from || {}).track || '',
  };
}

async function fetchRealTransitOffers(route, mode) {
  if (!PROXY_URL) return null;
  const [origin, destination] = await Promise.all([
    transitResolveStop(route.origin),
    transitResolveStop(route.destination),
  ]);
  if (!origin || !destination) return null;
  const tz = origin.tz || 'UTC';

  const offers = [];
  const seen = new Set();
  for (const day of dayCandidates(route).slice(0, TRANSIT_MAX_DAYS)) {
    for (const anchor of TRANSIT_DEPART_ANCHORS) {
      const payload = await fetchProxyJson('transit/plan', new URLSearchParams({
        fromPlace: origin.id,
        toPlace: destination.id,
        time: anchorToUtcIso(day, anchor, tz),
        numItineraries: String(TRANSIT_ITINERARIES_PER_REQUEST),
        transitModes: TRANSIT_REQUEST_MODES[mode],
      }));
      for (const itinerary of (payload && payload.itineraries) || []) {
        const offer = transitItineraryToOffer(itinerary, mode, route, tz, { origin, destination });
        if (!offer) continue;
        // The anchors overlap on purpose, and MOTIS happily rolls past
        // midnight into a day that was never asked for.
        if (isoDay(offer.depart) !== isoDay(day)) continue;
        const key = `${offer.depart.toISOString()}|${offer.lineLabel}`;
        if (seen.has(key)) continue;
        seen.add(key);
        offers.push(offer);
      }
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
 * Engine - ranking + recommendations, mirroring traveldeals/engine.py,
 * including the comfort score (hotel amenities / transport comfort) that
 * feeds into best_value, and the hard filters for both. No price-history/
 * error-fare detection here: that needs data accumulated across real runs
 * (see the "Meine Alerts" tab), which a stateless in-browser search doesn't
 * have.
 * ===================================================================== */
// How many ranked options the results list shows. Was 6, which alone made
// searches look nearly empty once the providers started returning dozens of
// offers - the cap, not the data, was the bottleneck.
const MAX_RESULTS_SHOWN = 40;
// "Nur Deals": an option counts as a deal when it's at least this much
// below the median of the same search. The in-browser search has no price
// history (that lives in the "Meine Alerts" tab), so this batch-relative
// comparison is the only deal signal available here. Mirrors
// BELOW_MEDIAN_DEAL_RATIO / MIN_CANDIDATES_FOR_MEDIAN_DEAL in engine.py.
const BELOW_MEDIAN_DEAL_RATIO = 0.85;
const MIN_CANDIDATES_FOR_MEDIAN_DEAL = 4;
const BEST_VALUE_PRICE_WEIGHT = 0.5;
const BEST_VALUE_DURATION_WEIGHT = 0.25;
const BEST_VALUE_COMFORT_WEIGHT = 0.25;
const BAGGAGE_SAVINGS_THRESHOLD = 0.15;

const HOTEL_AMENITY_FIELDS = ['wifi', 'freeCancellation', 'parking', 'airConditioning', 'petsAllowed', ...Object.keys(HOTEL_AMENITY_PROBABILITY)];

function hotelComfortScore(o) {
  const starsNorm = ((o.stars ?? 3) - 1) / 4;
  const ratingNorm = (o.rating ?? 7.0) / 10;
  const amenityNorm = HOTEL_AMENITY_FIELDS.filter(f => o[f]).length / HOTEL_AMENITY_FIELDS.length;
  const distanceNorm = 1 - Math.min(o.distanceKm ?? 3.0, 10) / 10;
  const mealPlanNorm = MEAL_PLAN_TIERS.indexOf(o.mealPlan ?? 'none') / (MEAL_PLAN_TIERS.length - 1);
  return (starsNorm + ratingNorm + amenityNorm + distanceNorm + mealPlanNorm) / 5;
}
function transportComfortScore(o) {
  const [lo, hi] = LEGROOM_RANGE[o.mode] ?? [70, 100];
  const legroomNorm = Math.min(Math.max(((o.legroomCm ?? lo) - lo) / (hi - lo), 0), 1);
  const directBonus = { 0: 1.0, 1: 0.5 }[o.stops] ?? 0.0;
  const punctualityNorm = (o.punctualityPct ?? 80) / 100;
  return (legroomNorm + (o.wifiOnboard ? 1 : 0) + (o.powerOutlets ? 1 : 0) + directBonus + punctualityNorm) / 5;
}
function comfortScore(candidate) {
  const scores = candidate.offers
    .map(o => o.mode === 'hotel' ? hotelComfortScore(o) : (['flight', 'train', 'bus'].includes(o.mode) ? transportComfortScore(o) : null))
    .filter(s => s !== null);
  return scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 0.5;
}

function meetsHotelPrefs(o, p) {
  if (p.minStars != null && (o.stars ?? 0) < p.minStars) return false;
  if (p.minRating != null && (o.rating ?? 0) < p.minRating) return false;
  if (p.maxDistanceKm != null && (o.distanceKm ?? 0) > p.maxDistanceKm) return false;
  if (p.propertyTypes && p.propertyTypes.length && !p.propertyTypes.includes(o.propertyType)) return false;
  if (p.minMealPlan && MEAL_PLAN_TIERS.indexOf(o.mealPlan ?? 'none') < MEAL_PLAN_TIERS.indexOf(p.minMealPlan)) return false;
  for (const [prefFlag, offerField] of HOTEL_AMENITY_REQUIREMENTS) {
    if (p[prefFlag] && !o[offerField]) return false;
  }
  return true;
}
function minutesSinceMidnight(hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
}
function circularMinutesDiff(a, b) {
  const diff = Math.abs(a - b) % 1440;
  return Math.min(diff, 1440 - diff);
}
function offerTimeOfDay(offer) {
  return offer.depart.getHours() * 60 + offer.depart.getMinutes();
}
function meetsTransportPrefs(o, p) {
  if (p.directOnly && o.stops > 0) return false;
  if (p.requireWifiOnboard && !o.wifiOnboard) return false;
  if (p.requirePowerOutlets && !o.powerOutlets) return false;
  if (p.minPunctuality != null && (o.punctualityPct ?? 0) < p.minPunctuality) return false;
  if (p.preferredDepartTime) {
    const diff = circularMinutesDiff(offerTimeOfDay(o), minutesSinceMidnight(p.preferredDepartTime));
    if (diff > (p.departTimeFlexMinutes || 0)) return false;
  }
  return true;
}

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

// Mirrors engine.py's _flag_below_median: mark options notably cheaper than
// the median of this same search, compared per mode (a bus and a flight are
// not the same market).
function flagBelowMedian(candidates) {
  const byMode = {};
  for (const c of candidates) {
    // Price-less options have nothing to compare, and must not drag the
    // median towards zero for the ones that do.
    if (c.hasUnknownPrice) continue;
    (byMode[c.mode] ??= []).push(c);
  }
  for (const group of Object.values(byMode)) {
    if (group.length < MIN_CANDIDATES_FOR_MEDIAN_DEAL) continue;
    const prices = group.map(c => c.price).sort((a, b) => a - b);
    const mid = Math.floor(prices.length / 2);
    const median = prices.length % 2 ? prices[mid] : (prices[mid - 1] + prices[mid]) / 2;
    for (const c of group) c.isBelowMedian = c.price <= median * BELOW_MEDIAN_DEAL_RATIO;
  }
}

// Mirrors engine.py's _date_deviation_days: how far the departure sits
// outside the *exactly* requested window, ignoring the flex padding (that
// padding widens the search, but 'exact_date' ranks un-padded dates first).
function dateDeviationDays(candidate, route) {
  const depart = candidate.offers[0]?.depart;
  if (!depart) return 0;
  const day = new Date(depart.getFullYear(), depart.getMonth(), depart.getDate());
  const from = new Date(route.departFrom.getFullYear(), route.departFrom.getMonth(), route.departFrom.getDate());
  const until = new Date(route.departUntil.getFullYear(), route.departUntil.getMonth(), route.departUntil.getDate());
  const dayMs = 86400000;
  if (day < from) return Math.round((from - day) / dayMs);
  if (day > until) return Math.round((day - until) / dayMs);
  return 0;
}

const COMBO_TRANSPORT_MODE = { flight_hotel: 'flight', train_hotel: 'train', bus_hotel: 'bus' };
// Modes whose outbound and return legs may come from *different* transport
// modes - the combination no portal sells, because each portal sells one.
const MIXED_RETURN_MODES = ['flight', 'train', 'bus'];
const OR_COMBO_MODES = { train_or_bus: ['train', 'bus'], flight_or_train: ['flight', 'train'], flight_or_bus: ['flight', 'bus'] };

// A round trip is split into three independently sorted lists - "Nur
// Hinfahrt", "Nur Rückfahrt", "Hin + Zurück". Booking the two directions
// separately is regularly cheaper than any round-trip fare, but only if you
// can see both halves next to the package, which one merged list never
// showed.
//
// mixed_return builds two-leg options itself; for the single-direction
// sections it has to be broken back down into plain one-way modes.
function sectionModes(modes) {
  const out = [];
  for (const m of modes) {
    const expanded = m === 'mixed_return' ? MIXED_RETURN_MODES : [m];
    for (const e of expanded) if (!out.includes(e)) out.push(e);
  }
  return out;
}

// Which raw offer pools a set of tab modes needs fetched.
function baseModesFor(modes) {
  const need = [];
  const add = (m) => { if (!need.includes(m)) need.push(m); };
  for (const m of modes) {
    if (['flight', 'train', 'bus', 'hotel'].includes(m)) add(m);
    else if (COMBO_TRANSPORT_MODE[m]) { add(COMBO_TRANSPORT_MODE[m]); add('hotel'); }
    else if (OR_COMBO_MODES[m]) OR_COMBO_MODES[m].forEach(add);
  }
  return need;
}

// Fahrt-/Flugzeit je Richtung. Ein Rückflugticket bringt beide Legs in
// einem Angebot mit, eine zusammengesetzte Reise in zweien - die Anzeige
// soll trotzdem in beiden Fällen "2h hin · 5h zurück" sagen statt einer
// addierten Zahl, aus der sich keine der beiden Richtungen ablesen lässt.
//
// `back: null` heißt "die Quelle nennt die Rückwegdauer nicht" - dann steht
// das da, statt den Hinweg zu spiegeln oder eine Zahl zu erfinden.
function legDurations(option) {
  const back = returnLeg(option);
  if (back) return { out: option.offers[0].durationHours, back: back.durationHours };
  const single = option.offers[0];
  if (single && single.returnDepart) {
    return { out: single.durationHours, back: single.returnDurationHours ?? null };
  }
  return null;  // einfache Fahrt
}

// "2h hin · 5h zurück" statt "7h". Die Summe beantwortet nicht, wonach man
// bei einer Hin-und-Rückreise tatsächlich schaut - ob der Rückweg abends
// noch zumutbar ist, zum Beispiel.
function durationHtml(option) {
  const legs = legDurations(option);
  if (!legs) return `${option.durationHours}h`;
  const back = legs.back == null ? 'Rückweg ohne Dauerangabe' : `${legs.back}h zurück`;
  return `${legs.out}h hin · ${back}`;
}

// Two transport legs in one option (out + back) - as opposed to a single
// round-trip ticket, or a transport+hotel combo. Drives both the pairing
// below and the "· zurück ..." line in the results.
function returnLeg(option) {
  if (option.offers.length !== 2) return null;
  const [a, b] = option.offers;
  const transport = m => ['flight', 'train', 'bus'].includes(m);
  return transport(a.mode) && transport(b.mode) ? b : null;
}

// Pair each outbound with the cheapest return *per mode*, so "hin fliegen,
// zurück Bus" competes with "hin Bus, zurück fliegen". Every outbound x
// every return would be thousands of near-identical rows for no extra
// insight - the cheapest return per mode is the one that can win.
function pairLegs(outbound, inbound) {
  const singles = arr => arr.filter(c => c.offers.length === 1);
  const bestPerMode = {};
  for (const b of singles(inbound)) {
    const cur = bestPerMode[b.mode];
    // Among priced returns the cheapest wins. A mode that has no priced
    // return at all still gets one representative, so a timetable-only mode
    // (Bahn) isn't simply missing from this section.
    if (!cur) { bestPerMode[b.mode] = b; continue; }
    if (cur.hasUnknownPrice && !b.hasUnknownPrice) { bestPerMode[b.mode] = b; continue; }
    if (!b.hasUnknownPrice && !cur.hasUnknownPrice && b.price < cur.price) bestPerMode[b.mode] = b;
  }
  const returns = Object.values(bestPerMode);
  const pairs = [];
  for (const o of singles(outbound)) {
    for (const b of returns) {
      // A return that leaves before the outbound does is not a trip.
      if (b.offers[0].depart <= o.offers[0].depart) continue;
      const offers = [o.offers[0], b.offers[0]];
      pairs.push({
        mode: o.mode,
        offers,
        price: round2(o.price + b.price),
        durationHours: round2(o.durationHours + b.durationHours),
        hasUnknownPrice: offers.some(x => x.priceKnown === false),
      });
    }
  }
  return pairs;
}

async function runSearch(route) {
  // Keyed by route variant *and* mode: the outbound, the return and the
  // round-trip search are three different queries against the same sources.
  const poolCache = {};
  let usedRealFlightData = false;
  // Why flights fell back to example data, in the user's words - empty when
  // they didn't fall back at all.
  let flightFallbackReason = '';
  // Same for the bus: FlixBus is the only bus source with prices, so when it
  // has nothing the whole mode drops to timetables without a price.
  let busPriceReason = '';
  // Invented prices are opt-in now, and off by default. They exist to
  // exercise the ranking logic, not to fill a results list - and filling the
  // list was actively harmful: a search that found no real fares showed
  // three fabricated ones instead, so "keine echten Preise" arrived wrapped
  // in three prices that looked like an answer. Nothing beats an empty list
  // plus the reason.
  const allowMock = Boolean(route.showMockData);
  const mockFor = { flight: mockFlightOffers, train: mockTrainOffers, bus: mockBusOffers, hotel: mockHotelOffers };
  const fallback = (variant, mode) => (allowMock ? mockFor[mode](variant) : []);

  const variantKey = (v) => `${v.origin}>${v.destination}|${isoDay(v.departFrom)}..${isoDay(v.departUntil)}`
                          + `|${v.returnDate ? isoDay(v.returnDate) : '-'}`;

  async function pool(variant, mode) {
    const key = `${variantKey(variant)}|${mode}`;
    if (poolCache[key]) return poolCache[key];
    if (mode === 'flight') {
      const real = await fetchFlightOffersWithNeighbours(variant);
      if (real && real.length) {
        poolCache[key] = real;
        usedRealFlightData = true;
      } else {
        flightFallbackReason = !PROXY_URL
          ? 'Kein Proxy konfiguriert'
          : (lastProxyError || 'Für diese Strecke und diesen Zeitraum sind dort keine Preise hinterlegt');
        poolCache[key] = fallback(variant, 'flight');
      }
    } else if (mode === 'train' || mode === 'bus') {
      // FlixBus for real prices, Transitous for everything it doesn't run,
      // plus neighbouring stations when the user asked for them. Real
      // timetables without prices still beat invented prices; example data
      // only appears when explicitly switched on.
      const merged = await fetchGroundOffersWithNeighbours(variant, mode);
      // Only when FlixBus - the one bus source with prices - came up empty.
      if (mode === 'bus' && !merged.some(o => o.priceKnown !== false)) {
        busPriceReason = busPriceReason || lastFlixbusNote;
      }
      poolCache[key] = merged.length ? merged : fallback(variant, mode);
    } else {
      // No free hotel source exists at all, so this mode is empty unless
      // example data is switched on - the provider links below are the
      // honest answer for hotels.
      poolCache[key] = fallback(variant, 'hotel');
    }
    return poolCache[key];
  }

  // Mirrors TripOption.has_unknown_price: one price-less leg makes the whole
  // option's total meaningless, so `price` must not be shown or compared.
  const candidate = (mode, offers, price, durationHours) => ({
    mode, offers, price, durationHours,
    hasUnknownPrice: offers.some(o => o.priceKnown === false),
  });

  // One-way legs across every transport mode for one direction and date.
  // Deliberately bypasses the `pool` cache: mixed_return needs a *different*
  // route (reversed, other date) than the one the pools were built for.
  async function legsFor(variant) {
    const wanted = isoDay(variant.departFrom);
    const legs = [];
    for (const m of MIXED_RETURN_MODES) {
      let found = [];
      if (m === 'flight') found = (await fetchRealFlightOffers(variant)) || [];
      // groundOffersFor gives the train leg real DB prices when the local
      // server is up - a mixed trip only counts a leg it can price anyway.
      else found = (await groundOffersFor(variant, m)) || [];
      for (const offer of found) {
        // A round-trip fare can't be split, and a leg with no price can't be
        // added to a total.
        if (offer.returnDepart || offer.priceKnown === false) continue;
        if (isoDay(offer.depart) !== wanted) continue;
        legs.push(offer);
      }
    }
    return legs;
  }

  // Everything a section needs to rank and explain itself later: the raw
  // offer pools stay attached because the "1h später spart X" hint compares
  // against them at render time, not here.
  async function buildCandidates(variant, modes) {
    const pools = {};
    for (const m of baseModesFor(modes)) pools[m] = await pool(variant, m);
    const candidates = [];
    for (const mode of modes) {
      if (['flight', 'train', 'bus', 'hotel'].includes(mode)) {
        for (const offer of pools[mode]) candidates.push(candidate(mode, [offer], offer.price, offer.durationHours));
      } else if (COMBO_TRANSPORT_MODE[mode]) {
        for (const combo of buildCombos(pools[COMBO_TRANSPORT_MODE[mode]], pools.hotel)) {
          candidates.push(candidate(mode, [combo.transport, combo.hotel], combo.price, combo.transport.durationHours));
        }
      } else if (mode === 'mixed_return') {
        // Cheapest way out and cheapest way back, chosen independently - the
        // combination no portal sells, because each portal sells one mode.
        //
        // Two things this must get right, and both were wrong at first:
        // the return leg travels *destination -> origin*, not the same
        // direction again; and it departs on the return date, which the normal
        // pools (built from the outbound window) never cover.
        if (variant.returnDate) {
          const outward = { ...variant, departFrom: variant.departFrom, departUntil: variant.departFrom };
          const homeward = {
            ...variant, origin: variant.destination, destination: variant.origin,
            departFrom: variant.returnDate, departUntil: variant.returnDate,
            roundTrip: false, returnDate: null,
          };
          const [out, back] = await Promise.all([legsFor(outward), legsFor(homeward)]);
          const asSingles = legs => legs.map(o => candidate(o.mode, [o], o.price, o.durationHours));
          for (const pair of pairLegs(asSingles(out), asSingles(back))) {
            candidates.push(candidate(mode, pair.offers, pair.price, pair.durationHours));
          }
        }
      } else if (OR_COMBO_MODES[mode]) {
        const [modeA, modeB] = OR_COMBO_MODES[mode];
        for (const offer of [...pools[modeA], ...pools[modeB]]) {
          candidates.push(candidate(mode, [offer], offer.price, offer.durationHours));
        }
      }
    }
    return { candidates, pools };
  }

  // Reisezeit-Grenzen für einen Abschnitt: `out` gilt für den Hinweg, `back`
  // für den Rückweg. Bei einer reinen Hinfahrt gibt es nur `out`, und dann
  // greift es unverändert auf die Dauer der Option - genau wie vorher.
  function withinDurationLimits(c, out, back) {
    if (c.mode === 'hotel') return true;
    const backLeg = returnLeg(c);
    const backHours = backLeg ? backLeg.durationHours : (c.offers[0] || {}).returnDurationHours;
    if (backHours == null) {
      // Einfache Fahrt - oder ein Rückflugticket, dessen Rückwegdauer die
      // Quelle nicht nennt. Eine unbekannte Dauer ist kein Verstoß.
      return !(out != null && c.durationHours > out);
    }
    if (out != null && c.offers[0].durationHours > out) return false;
    if (back != null && backHours > back) return false;
    return true;
  }

  function applyFilters(candidates, limits = {}) {
    const outLimit = 'out' in limits ? limits.out : route.maxDuration;
    const backLimit = 'back' in limits ? limits.back : route.maxDurationReturn;
    return candidates.filter(c => {
      // An unknown price can't blow a budget. Dropping the option would hide a
      // real connection over a number nobody has.
      if (route.budget != null && !c.hasUnknownPrice && c.price > route.budget) return false;
      if (!withinDurationLimits(c, outLimit, backLimit)) return false;
      if (route.lowCost === 'exclude' && c.offers.some(o => o.isLowCost)) return false;
      if (route.lowCost === 'only') {
        // Only transport legs can be low-cost; a hotel leg in a combo must
        // not disqualify the option.
        const transport = c.offers.filter(o => ['flight', 'train', 'bus'].includes(o.mode));
        if (!transport.length || !transport.every(o => o.isLowCost)) return false;
      }
      for (const o of c.offers) {
        if (o.mode === 'hotel' && !meetsHotelPrefs(o, route.hotelPrefs)) return false;
        if (['flight', 'train', 'bus'].includes(o.mode) && !meetsTransportPrefs(o, route.transportPrefs)) return false;
      }
      return true;
    });
  }

  // A finished, still-unsorted result list. Sorting deliberately happens
  // later, at render time: it is a way of looking at these offers, not a
  // search parameter, and re-sorting must never cost another round of API
  // calls.
  function makeSection(id, label, variant, built, note = '', limits = {}) {
    let candidates = applyFilters(built.candidates, limits);
    flagBelowMedian(candidates);
    if (route.dealsOnly) candidates = candidates.filter(c => c.isBelowMedian);
    // Measured against this section's own dates - the return leg's "exact
    // date" is the return date, not the outbound one.
    for (const c of candidates) c.dateDeviation = dateDeviationDays(c, variant);
    return { id, label, note, variant, candidates, pools: built.pools };
  }

  const isRoundTrip = Boolean(route.roundTrip && route.returnDate);
  if (!isRoundTrip) {
    const built = await buildCandidates(route, route.modes);
    return {
      sections: [makeSection('all', '', route, built)],
      usedRealFlightData, flightFallbackReason, busPriceReason,
    };
  }

  const legModes = sectionModes(route.modes);
  const outboundRoute = { ...route, roundTrip: false, returnDate: null };
  const inboundRoute = {
    ...route, origin: route.destination, destination: route.origin,
    departFrom: route.returnDate, departUntil: route.returnDate,
    roundTrip: false, returnDate: null,
  };
  const outBuilt = await buildCandidates(outboundRoute, legModes);
  const backBuilt = await buildCandidates(inboundRoute, legModes);
  // Searched as a round trip, this returns the airlines' own return fares
  // (one ticket, one price). mixed_return pairs its legs itself.
  const wholeBuilt = await buildCandidates(route, route.modes);
  const combinedCandidates = route.modes.includes('mixed_return')
    ? wholeBuilt.candidates
    : [
        ...wholeBuilt.candidates.filter(c => c.offers.some(o => o.returnDepart)),
        // Jede Einzelfahrt gegen die Grenze ihrer eigenen Richtung, bevor
        // sie zu einer Reise zusammengesetzt wird.
        ...pairLegs(applyFilters(outBuilt.candidates, { out: route.maxDuration, back: null }),
                    applyFilters(backBuilt.candidates, { out: route.maxDurationReturn, back: null })),
      ];

  const sections = [
    makeSection('outbound', 'Nur Hinfahrt', outboundRoute, outBuilt,
      `Einzelpreise für ${route.origin} → ${route.destination} am ${fmtDay(route.departFrom)}.`,
      { out: route.maxDuration, back: null }),
    // Hier *ist* die einzelne Fahrt der Rückweg - also gilt dessen Grenze.
    makeSection('inbound', 'Nur Rückfahrt', inboundRoute, backBuilt,
      `Einzelpreise für ${route.destination} → ${route.origin} am ${fmtDay(route.returnDate)}.`,
      { out: route.maxDurationReturn, back: null }),
    makeSection('combined', 'Hin + Zurück', route,
      { candidates: combinedCandidates, pools: outBuilt.pools },
      'Gesamtpreis für beide Richtungen: echte Hin-/Rückflug-Tickets und aus zwei Einzelfahrten zusammengesetzte Reisen. '
      + 'Zwei Einzeltickets sind oft günstiger als ein Rückflugticket - vergleiche mit den beiden Reitern links.'),
  ];
  return { sections, usedRealFlightData, flightFallbackReason, busPriceReason };
}

/* Sorting - runs on the already-fetched candidates, never triggers a search. */
function sortCandidates(candidates, sortKey) {
  // Normalize against priced candidates only - a placeholder 0 would
  // otherwise become the price minimum and squash every real one.
  const priced = candidates.filter(c => !c.hasUnknownPrice);
  const basis = priced.length ? priced : candidates;
  const prices = basis.map(c => c.price);
  const durations = basis.map(c => c.durationHours);
  for (const c of candidates) {
    if (sortKey === 'cheapest') c.score = c.price;
    else if (sortKey === 'most_expensive') c.score = -c.price;  // sorted ascending, so negate
    else if (sortKey === 'fastest') c.score = c.durationHours;
    else if (sortKey === 'exact_date') {
      // Days outside the exactly requested window first; price breaks ties.
      c.score = (c.dateDeviation || 0) * 100000 + c.price;
    } else {
      const discomfort = 1 - comfortScore(c);
      c.score = BEST_VALUE_PRICE_WEIGHT * normalize(c.price, prices)
              + BEST_VALUE_DURATION_WEIGHT * normalize(c.durationHours, durations)
              + BEST_VALUE_COMFORT_WEIGHT * discomfort;
    }
  }
  // Price-less options sort behind every priced one in every price-based
  // order: their 0 is a placeholder, and letting it compete would park them
  // at the very top of a "Preis aufsteigend" list as though they were free.
  // "Dauer" is the exception - there the number they carry is real.
  const priceBased = sortKey !== 'fastest';
  return [...candidates].sort((a, b) =>
    (priceBased ? (a.hasUnknownPrice - b.hasUnknownPrice) : 0) || (a.score - b.score));
}

// Per-option hints. Runs on the handful of rows actually shown, so it is
// redone after each re-sort instead of for hundreds of candidates upfront.
async function addRecommendations(route, options, pools) {
  const rates = await getRatesPerEur();
  for (const c of options) {
    c.recommendations = [];
    const primary = c.offers[0];
    const samePool = (pools && pools[primary.mode]) || [];

    if (c.hasUnknownPrice) {
      // Everything below is about money - savings hints, currency
      // equivalents - and none of it may run on a placeholder price. Say
      // what is actually known and move on.
      c.recommendations.push(
        `🕓 Echte Verbindung laut Fahrplan (${primary.lineLabel || primary.bookingSite})` +
        `${primary.track ? `, Gleis ${primary.track}` : ''} – Preis liefert diese Quelle nicht, bitte beim Anbieter prüfen.`
      );
      continue;
    }

    if (['flight', 'train', 'bus'].includes(primary.mode)) {
      // Only compare against offers that also satisfy the route's own
      // transport constraints (esp. the depart-time window) - otherwise
      // this could suggest a time the user already said doesn't work.
      const eligiblePool = samePool.filter(o => o.priceKnown !== false && meetsTransportPrefs(o, route.transportPrefs));
      const sameDayLater = eligiblePool.filter(o =>
        isoDay(o.depart) === isoDay(primary.depart) && o.depart > primary.depart && o.price < primary.price
      );
      if (sameDayLater.length) {
        const best = sameDayLater.reduce((a, b) => (b.price < a.price ? b : a));
        const hoursLater = round1((best.depart - primary.depart) / 3600000);
        const savings = round2(primary.price - best.price);
        c.recommendations.push(`🕐 ${hoursLater}h später (${fmtHM(best.depart)} statt ${fmtHM(primary.depart)}) spart ${savings} ${primary.currency}.`);
      }
    }

    if (primary.bagFee > 0) {
      const bags = Math.max(route.checkedBags, 1);
      const savings = round2(primary.bagFee * bags);
      if (savings / c.price >= BAGGAGE_SAVINGS_THRESHOLD) {
        // Either weight can be "egal" (null) - then leave that detail out of
        // the sentence rather than printing "null kg".
        const carryOn = route.carryOnMaxKg != null ? ` (bis ${route.carryOnMaxKg}kg)` : '';
        const checked = route.checkedBagKg != null ? ` (${route.checkedBagKg}kg)` : '';
        c.recommendations.push(`🎒 Nur Handgepäck${carryOn} statt ${bags}x Koffer${checked} spart ${savings} ${primary.currency}.`);
      }
    }

    if (c.offers.some(o => o.mode === 'flight' || o.mode === 'hotel')) {
      const others = ['USD', 'GBP'].filter(cur => cur !== route.currency);
      const equivalents = others.map(cur => `${convert(c.price, route.currency, cur, rates)} ${cur}`);
      if (equivalents.length) {
        c.recommendations.push(`💱 Entspricht ca. ${equivalents.join(' / ')} – ob eine Buchung in anderer Landeswährung günstiger ist, prüft v1 noch nicht automatisch.`);
      }
    }
  }
  return options;
}

function fmtHM(date) { return date.toTimeString().slice(0, 5); }
function fmtDay(date) { return date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }); }
function fmtShort(date) { return date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }) + ' ' + fmtHM(date); }

// Mock offers either have no url at all (JS mocks) or a placeholder
// "https://example.invalid/..." (Python mocks, fed through data/deals.json) -
// only render a clickable booking link for a URL that could actually work.
function bookingSiteHtml(name, url) {
  const isReal = url && !url.includes('example.invalid');
  return isReal ? `<a href="${url}" target="_blank" rel="noopener">${name}</a>` : name;
}

// IATA -> city name, so a feed post saying "Hamburg" is matched against a
// search entered as "HAM". Only the codes in AIRPORT_COORDS need an entry.
const AIRPORT_CITY_NAMES = {
  BER: 'Berlin', MUC: 'München', FRA: 'Frankfurt', DUS: 'Düsseldorf', HAM: 'Hamburg',
  STR: 'Stuttgart', CGN: 'Köln', HAJ: 'Hannover', NUE: 'Nürnberg', LEJ: 'Leipzig',
  DTM: 'Dortmund', BRE: 'Bremen', VIE: 'Wien', ZRH: 'Zürich', GVA: 'Genf',
  SZG: 'Salzburg', INN: 'Innsbruck', BSL: 'Basel', LHR: 'London', LGW: 'London',
  STN: 'London', LTN: 'London', MAN: 'Manchester', EDI: 'Edinburgh', DUB: 'Dublin',
  CDG: 'Paris', ORY: 'Paris', NCE: 'Nizza', LYS: 'Lyon', MRS: 'Marseille',
  TLS: 'Toulouse', BOD: 'Bordeaux', NTE: 'Nantes', AMS: 'Amsterdam', BRU: 'Brüssel',
  MAD: 'Madrid', BCN: 'Barcelona', PMI: 'Mallorca', VLC: 'Valencia', SVQ: 'Sevilla',
  IBZ: 'Ibiza', AGP: 'Málaga', FCO: 'Rom', MXP: 'Mailand', LIN: 'Mailand',
  VCE: 'Venedig', NAP: 'Neapel', LIS: 'Lissabon', OPO: 'Porto', CPH: 'Kopenhagen',
  ARN: 'Stockholm', OSL: 'Oslo', HEL: 'Helsinki', KEF: 'Island', WAW: 'Warschau',
  PRG: 'Prag', BUD: 'Budapest', ATH: 'Athen', IST: 'Istanbul', DXB: 'Dubai',
  BKK: 'Bangkok', NRT: 'Tokio', HND: 'Tokio', JFK: 'New York', LAX: 'Los Angeles',
};

const MEAL_PLAN_LABELS = { breakfast: 'Frühstück', half_board: 'Halbpension', full_board: 'Vollpension', all_inclusive: 'All Inclusive' };
const PROPERTY_TYPE_LABELS = { apartment: 'Apartment', hostel: 'Hostel', resort: 'Resort', bnb: 'B&B', guesthouse: 'Gästehaus', villa: 'Villa' };
const HOTEL_AMENITY_LABELS = {
  pool: 'Pool', gym: 'Fitnessraum', spa: 'Spa', restaurant: 'Restaurant', bar: 'Bar',
  roomService: 'Zimmerservice', frontDesk24h: '24h-Rezeption', businessFacilities: 'Business-Ausstattung',
  laundryService: 'Wäscheservice', elevator: 'Aufzug', balconyOrTerrace: 'Balkon/Terrasse',
  kitchen: 'Küche', beachfront: 'Strandnähe', disabledAccess: 'Barrierefrei', evCharging: 'E-Ladestation',
  bicycleRental: 'Fahrradverleih', babysitting: 'Babysitting', sauna: 'Sauna', hotTub: 'Whirlpool',
  nonSmoking: 'Nichtraucher', familyRooms: 'Familienzimmer', airportShuttle: 'Flughafentransfer',
};

function offerChips(offer) {
  const chips = [];
  if (offer.mode === 'hotel') {
    if (offer.stars) chips.push('⭐'.repeat(offer.stars));
    if (offer.rating) chips.push(`${offer.rating}/10`);
    if (PROPERTY_TYPE_LABELS[offer.propertyType]) chips.push(PROPERTY_TYPE_LABELS[offer.propertyType]);
    if (offer.distanceKm != null) chips.push(`${offer.distanceKm} km`);
    if (offer.wifi) chips.push('WLAN');
    if (MEAL_PLAN_LABELS[offer.mealPlan]) chips.push(MEAL_PLAN_LABELS[offer.mealPlan]);
    if (offer.freeCancellation) chips.push('kostenlos stornierbar');
    if (offer.parking) chips.push('Parkplatz');
    if (offer.airConditioning) chips.push('Klimaanlage');
    if (offer.petsAllowed) chips.push('Haustiere ok');
    for (const [field, label] of Object.entries(HOTEL_AMENITY_LABELS)) {
      if (offer[field]) chips.push(label);
    }
  } else if (['flight', 'train', 'bus'].includes(offer.mode)) {
    chips.push(offer.stops === 0 ? 'Direkt' : `${offer.stops}x Umstieg`);
    // A real, bookable DB fare (not the price-less timetable) earns a badge,
    // so it's clear this price came live from bahn.de.
    if (offer.priceSource === 'db-live') chips.push('🟢 Live-Preis DB');
    // Only stated when it is decided. `null` means "not decidable" and gets
    // no chip at all - an absent claim, not a negative one.
    if (offer.dTicketCovered === true) {
      // Mit Live-Preis laesst sich die Ersparnis beziffern statt nur die
      // Abdeckung zu behaupten - genau das macht den Hinweis brauchbar.
      const saving = typeof offer.priceWithoutDTicket === 'number'
        ? ` (spart ${offer.priceWithoutDTicket.toFixed(2)} ${offer.currency})` : '';
      chips.push(offer.priceNote
        ? `🎫 im Deutschland-Ticket enthalten${saving}`
        : `🎫 mit Deutschland-Ticket 0 €${saving}`);
    }
    chips.push(...baggageChips(offer));
    if (offer.punctualityPct != null) chips.push(`${offer.punctualityPct}% pünktlich`);
    if (offer.legroomCm != null) chips.push(`${offer.legroomCm}cm Beinfreiheit`);
    if (offer.wifiOnboard) chips.push('WLAN an Bord');
    if (offer.powerOutlets) chips.push('Steckdosen');
  }
  return chips;
}

// Was im Preis an Gepäck drin ist - Symbol plus Gewicht, je einmal für
// Handgepäck und Koffer, beide zusammen wenn beides inklusive ist.
//
// Bewusst nur, wo es etwas zu belegen gibt: die meisten Preisquellen sagen
// zum Gepäck gar nichts, und "keine Angabe" ist nicht dasselbe wie "nicht
// enthalten". Ein erfundenes "🎒 8 kg" wäre genau der Fehler, den dieses
// Projekt schon zweimal gemacht hat - also erscheint dann gar kein Chip.
function baggageChips(offer) {
  const chips = [];
  if (offer.includedCarryOnKg != null) {
    chips.push(`🎒 Handgepäck ${fmtKg(offer.includedCarryOnKg)} inkl.`);
  } else if (offer.includedCarryOnNote) {
    // Manche Tarife nennen nur Maße statt Gewicht (Ryanair: kleine Tasche
    // unter dem Sitz). Dann steht das Maß da, keine erfundenen Kilo.
    chips.push(`🎒 Handgepäck ${offer.includedCarryOnNote} inkl.`);
  }
  if (offer.includedCheckedBags > 0) {
    const count = offer.includedCheckedBags > 1 ? `${offer.includedCheckedBags}x ` : '';
    const kg = offer.includedCheckedBagKg != null ? ` ${fmtKg(offer.includedCheckedBagKg)}` : '';
    chips.push(`🧳 ${count}Koffer${kg} inkl.`);
  }
  // Sagt die Quelle nichts, ist der Link zur Anbieterseite die einzige
  // ehrliche Antwort - besser als eine Leerstelle und besser als geraten.
  if (!chips.length) {
    const url = baggageRulesUrl(offer);
    if (url) chips.push(`🧳 <a href="${url}" target="_blank" rel="noopener">Gepäckregeln</a>`);
  }
  return chips;
}

/* Gepäckregeln des Anbieters - verlinkt, nicht abgeschrieben.
 *
 * Zweimal live geprüft (07.08.2026, siehe HANDOFF): weder Ryanair noch
 * FlixBus noch Skiplagged nennen in ihrer *API* ein Gepäckfeld, und ihre
 * veröffentlichten Gepäckseiten sind JS-gerendert bzw. bot-geschützt
 * (Ryanair 403, FlixBus-Hilfe eine leere Salesforce-Hülle). Es gibt also
 * keine Quelle, aus der sich "8 kg" belegen ließe - und aus dem Gedächtnis
 * geschriebene Kilos wären genau der Fehler, den dieses Projekt nicht
 * nochmal macht.
 *
 * Also der ehrliche Ersatz: ein Klick auf die Seite, die es wirklich weiß.
 * Nur für Anbieter, die im Angebot namentlich stehen - ein geratener Link
 * wäre auch wieder eine Behauptung.
 */
const BAGGAGE_RULES_LINKS = [
  ['FlixBus', 'https://www.flixbus.de/service/gepaeck'],
  ['Ryanair', 'https://www.ryanair.com/de/de/nuetzliche-infos/hilfe-center/faq-uebersicht/Gepack'],
];

function baggageRulesUrl(offer) {
  const site = offer.bookingSite || '';
  const hit = BAGGAGE_RULES_LINKS.find(([name]) => site.startsWith(name));
  return hit ? hit[1] : '';
}

// "7 kg", nicht "7.0 kg" - und 22,5 kg bleibt 22,5 kg.
function fmtKg(kg) {
  return `${Number.isInteger(kg) ? kg : round1(kg)} kg`;
}

// Dasselbe getrennt-je-Richtung wie oben, nur aus deals.json (snake_case).
function durationHtmlFromJson(opt) {
  const first = opt.offers[0] || {};
  if (!first.return_depart_time) {
    return opt.total_duration_hours > 0 ? `${opt.total_duration_hours}h` : 'Dauer unbekannt';
  }
  const out = first.duration_hours;
  const back = first.return_duration_hours;
  const outText = out > 0 ? `${round2(out)}h hin` : 'Hinweg ohne Dauerangabe';
  return `${outText} · ${back != null ? `${round2(back)}h zurück` : 'Rückweg ohne Dauerangabe'}`;
}

// deals.json (vom Python-Cronjob) benutzt snake_case. Umschluesseln statt
// die Chip-Logik ein zweites Mal zu schreiben - zwei Kopien laufen
// garantiert auseinander.
function baggageChipsFromJson(offer) {
  return baggageChips({
    includedCarryOnKg: offer.included_carry_on_kg,
    includedCarryOnNote: offer.included_carry_on_note,
    includedCheckedBags: offer.included_checked_bags,
    includedCheckedBagKg: offer.included_checked_bag_kg,
  });
}

/* =========================================================================
 * Von/Nach-Autocomplete - Stadt eintippen, Flughafen/Bahnhof auswählen, wie
 * auf gängigen Reiseplattformen.
 *
 * Für Flug/Hotel: echte, öffentliche Travelpayouts-Places-API
 * (autocomplete.travelpayouts.com/places2, kein Token nötig - Shape via
 * GitHub-Actions-Smoke-Test verifiziert, siehe Git-Historie), liefert reale
 * Flughafen-/Stadt-Daten inkl. Popularitäts-Gewicht. Für Bahn/Bus gibt es
 * keine bekannte freie Stations-API - stattdessen eine kuratierte statische
 * Liste großer DACH-/europäischer Bahnhöfe (siehe RAIL_STATIONS unten).
 * Beides degradiert graceful: bei Netzwerkfehler/leerer Liste bleibt die
 * Texteingabe weiterhin frei nutzbar, nur ohne Vorschläge.
 * ===================================================================== */
const PLACES_API_URL = 'https://autocomplete.travelpayouts.com/places2';

const RAIL_STATIONS = [
  'Berlin Hbf', 'München Hbf', 'Hamburg Hbf', 'Köln Hbf', 'Frankfurt(Main) Hbf', 'Stuttgart Hbf',
  'Düsseldorf Hbf', 'Leipzig Hbf', 'Dresden Hbf', 'Hannover Hbf', 'Nürnberg Hbf', 'Dortmund Hbf',
  'Essen Hbf', 'Bremen Hbf', 'Duisburg Hbf', 'Bochum Hbf', 'Wuppertal Hbf', 'Bielefeld Hbf',
  'Bonn Hbf', 'Münster(Westf) Hbf', 'Karlsruhe Hbf', 'Mannheim Hbf', 'Augsburg Hbf', 'Wiesbaden Hbf',
  'Mönchengladbach Hbf', 'Gelsenkirchen Hbf', 'Aachen Hbf', 'Braunschweig Hbf', 'Kiel Hbf', 'Chemnitz Hbf',
  'Halle(Saale)Hbf', 'Magdeburg Hbf', 'Freiburg(Breisgau) Hbf', 'Krefeld Hbf', 'Lübeck Hbf', 'Oberhausen Hbf',
  'Erfurt Hbf', 'Rostock Hbf', 'Mainz Hbf', 'Kassel-Wilhelmshöhe', 'Saarbrücken Hbf', 'Potsdam Hbf',
  'Ulm Hbf', 'Heidelberg Hbf', 'Darmstadt Hbf', 'Regensburg Hbf', 'Würzburg Hbf', 'Wolfsburg Hbf',
  'Göttingen', 'Koblenz Hbf',
  'Wien Hbf', 'Salzburg Hbf', 'Graz Hbf', 'Innsbruck Hbf', 'Linz Hbf',
  'Zürich HB', 'Basel SBB', 'Bern', 'Genf', 'Luzern', 'St. Gallen',
  'Paris Gare du Nord', 'Paris Gare de Lyon', 'Paris Est', 'Lyon Part-Dieu', 'Strasbourg',
  'Amsterdam Centraal', 'Rotterdam Centraal', 'Brüssel-Süd', 'Antwerpen-Centraal',
  'Prag hl.n.', 'Budapest Keleti', 'Warschau Centralna', 'Kraków Główny',
  'Kopenhagen H', 'Mailand Centrale', 'Rom Termini', 'Venedig Santa Lucia', 'Bologna Centrale',
  'Barcelona Sants', 'Madrid Atocha', 'Lissabon Santa Apolónia', 'London St Pancras',
];

function debounce(fn, ms) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

function filterRailStations(term) {
  const q = term.trim().toLowerCase();
  if (q.length < 2) return [];
  const starts = [], contains = [];
  for (const name of RAIL_STATIONS) {
    const n = name.toLowerCase();
    if (n.startsWith(q)) starts.push(name);
    else if (n.includes(q)) contains.push(name);
  }
  return [...starts, ...contains].slice(0, 8).map(name => ({ label: `🚉 ${name}`, value: name }));
}

async function fetchLivePlaces(term, { includeAirports }) {
  if (term.trim().length < 2) return [];
  try {
    const params = new URLSearchParams({ term, locale: 'de' });
    params.append('types[]', 'city');
    if (includeAirports) params.append('types[]', 'airport');
    const resp = await fetch(`${PLACES_API_URL}?${params.toString()}`);
    if (!resp.ok) return [];
    const data = await resp.json();
    const q = term.trim().toLowerCase();
    return data
      .filter(p => (p.name || '').toLowerCase().includes(q) || (p.city_name || '').toLowerCase().includes(q))
      .sort((a, b) => (b.weight || 0) - (a.weight || 0))
      .slice(0, 8)
      .map(p => includeAirports
        ? {
            label: p.type === 'airport'
              ? `✈️ ${p.name} (${p.code}) – ${p.city_name || p.country_name}`
              : `🏙️ ${p.name} (${p.code}) – ${p.country_name}${p.main_airport_name ? ', alle Flughäfen' : ''}`,
            value: p.code,
          }
        : { label: `🏙️ ${p.name} – ${p.country_name}`, value: p.name });
  } catch (e) {
    return []; // offline/geblockt - Freitext-Eingabe bleibt weiter möglich, nur ohne Vorschläge
  }
}

// Live station lookup through the same Transitous geocoder the search
// itself routes with - so a picked suggestion is guaranteed to resolve to a
// stop later on. RAIL_STATIONS stays as the offline fallback (and for when
// the proxy isn't configured at all).
async function fetchTransitStops(term) {
  if (term.trim().length < 2 || !PROXY_URL) return filterRailStations(term);
  const payload = await fetchProxyJson('transit/geocode', new URLSearchParams({ text: term, language: 'de' }));
  const stops = (Array.isArray(payload) ? payload : []).filter(h => h && h.type === 'STOP' && h.name);
  if (!stops.length) return filterRailStations(term);
  const seen = new Set();
  const suggestions = [];
  for (const stop of stops) {
    // The geocoder returns one entry per platform/feed for a big station;
    // the name is what gets typed back into the field, so collapse them.
    if (seen.has(stop.name)) continue;
    seen.add(stop.name);
    suggestions.push({ label: `🚉 ${stop.name}${stop.country ? ` – ${stop.country}` : ''}`, value: stop.name });
    if (suggestions.length === 8) break;
  }
  return suggestions;
}

function placeSuggestions(term) {
  const source = MODE_TAB_CONFIG[activeMode].placeSource;
  if (source === 'rail') return fetchTransitStops(term);
  if (source === 'city') return fetchLivePlaces(term, { includeAirports: false });
  return fetchLivePlaces(term, { includeAirports: true });
}

function wireAutocomplete(inputId, listId) {
  const input = document.getElementById(inputId);
  const list = document.getElementById(listId);
  let items = [];
  let activeIndex = -1;

  function render() {
    if (!items.length) { list.hidden = true; list.innerHTML = ''; return; }
    list.innerHTML = items.map((it, i) =>
      `<li class="autocomplete-item${i === activeIndex ? ' active' : ''}" data-index="${i}">${it.label}</li>`
    ).join('');
    list.hidden = false;
  }
  function hide() { items = []; activeIndex = -1; list.hidden = true; list.innerHTML = ''; }
  function select(item) { input.value = item.value; hide(); }

  const runSearchDebounced = debounce(async (term) => {
    const results = await placeSuggestions(term);
    items = results;
    activeIndex = -1;
    render();
  }, 250);

  input.addEventListener('input', () => runSearchDebounced(input.value));
  input.addEventListener('keydown', (ev) => {
    if (list.hidden || !items.length) return;
    if (ev.key === 'ArrowDown') { ev.preventDefault(); activeIndex = Math.min(activeIndex + 1, items.length - 1); render(); }
    else if (ev.key === 'ArrowUp') { ev.preventDefault(); activeIndex = Math.max(activeIndex - 1, 0); render(); }
    else if (ev.key === 'Enter' && activeIndex >= 0) { ev.preventDefault(); select(items[activeIndex]); }
    else if (ev.key === 'Escape') { hide(); }
  });
  list.addEventListener('mousedown', (ev) => {
    const li = ev.target.closest('.autocomplete-item');
    if (!li) return;
    ev.preventDefault();
    select(items[Number(li.dataset.index)]);
  });
  document.addEventListener('click', (ev) => {
    if (ev.target !== input && !list.contains(ev.target)) hide();
  });
  // Modus-Wechsel wechselt die Vorschlagsquelle (Flughafen vs. Bahnhof) -
  // alte Vorschläge für den vorigen Modus wegräumen.
  modeTabsEl.addEventListener('click', hide);
}
wireAutocomplete('origin', 'originSuggestions');
wireAutocomplete('destination', 'destinationSuggestions');

/* =========================================================================
 * Search form wiring
 * ===================================================================== */
const searchForm = document.getElementById('searchForm');
const searchResultsEl = document.getElementById('searchResults');
const searchMetaEl = document.getElementById('searchMeta');
const trackBox = document.getElementById('trackBox');
const trackYaml = document.getElementById('trackYaml');

function numOrNull(id) { const v = document.getElementById(id).value; return v === '' ? null : Number(v); }

// Rückreisedatum, aber nur wenn es überhaupt eines sein kann: Modus erlaubt
// Hin+Rück, Haken gesetzt, Datum da - und nicht vor der Hinreise.
function validReturnDate(cfg) {
  if (!(cfg.roundTrip && document.getElementById('roundTrip').checked)) return null;
  const value = document.getElementById('returnDate').value;
  if (!value) return null;
  const from = document.getElementById('departFrom').value;
  if (from && value < from) return null;  // Zeichenketten-Vergleich reicht bei ISO-Daten
  return new Date(value);
}

function readRouteFromForm() {
  const cfg = MODE_TAB_CONFIG[activeMode];
  return {
    mode: activeMode,
    modes: cfg.modes,
    origin: cfg.origin ? document.getElementById('origin').value.trim() : '',
    destination: document.getElementById('destination').value.trim(),
    departFrom: new Date(document.getElementById('departFrom').value),
    departUntil: cfg.singleDate
      ? new Date(document.getElementById('departFrom').value)
      : new Date(document.getElementById('departUntil').value),
    flexBefore: Number(document.getElementById('flexBefore').value || 0),
    flexAfter: Number(document.getElementById('flexAfter').value || 0),
    minNights: Number(document.getElementById('minNights').value || 0),
    maxNights: Number(document.getElementById('maxNights').value || 0),
    budget: numOrNull('budget'),
    currency: document.getElementById('currency').value,
    maxDuration: numOrNull('maxDuration'),
    // Nur bei Hin+Rück gefragt: 12 Stunden Nachtbus hin mag man hinnehmen,
    // zurück vor der Arbeit nicht.
    maxDurationReturn: (cfg.roundTrip && document.getElementById('roundTrip').checked)
      ? numOrNull('maxDurationReturn') : null,
    // Not a search input any more - the sort control lives at the results
    // (#sortBy). Kept on the route object because the YAML snippet and the
    // AI prompt still describe "how should this be ranked".
    priority: document.getElementById('sortBy').value,
    checkedBags: Number(document.getElementById('checkedBags').value || 0),
    // null = "egal": no weight preference stated, distinct from 0 kg.
    checkedBagKg: document.getElementById('checkedBagKgAny').checked
      ? null : Number(document.getElementById('checkedBagKg').value || 23),
    carryOnCount: Number(document.getElementById('carryOnCount').value || 1),
    carryOnMaxKg: document.getElementById('carryOnMaxKgAny').checked
      ? null : Number(document.getElementById('carryOnMaxKg').value || 8),
    bahncard: document.getElementById('bahncard').value,
    deutschlandticket: document.getElementById('deutschlandticket').checked,
    lowCost: document.getElementById('lowCost').value,
    dealsOnly: document.getElementById('dealsOnly').value === 'deals',
    // Off by default: invented prices are for exercising the ranking logic,
    // not for filling a results list. See the mock rule in HANDOFF.md.
    showMockData: document.getElementById('showMockData').value === 'mock',
    // Getrennt pro Seite: der Umweg zum Startflughafen (eigenes Auto) wiegt
    // anders als der am Ziel (Mietwagen, Bahn, Gepäck).
    nearbyOriginKm: Number(document.getElementById('nearbyOriginKm').value || 0),
    nearbyDestinationKm: Number(document.getElementById('nearbyDestinationKm').value || 0),
    roundTrip: cfg.roundTrip && document.getElementById('roundTrip').checked,
    // Zweiter Riegel hinter dem `min` des Datumsfeldes: über die Oberfläche
    // ist ein früheres Rückreisedatum nicht mehr erreichbar, aber ein Wert,
    // der es trotzdem hierher schafft, darf keine Suche "zurück vor hin"
    // auslösen. Dann lieber ohne Rückreise als mit einem erfundenen Datum.
    returnDate: validReturnDate(cfg),
    hotelPrefs: {
      minStars: document.getElementById('minStars').value ? Number(document.getElementById('minStars').value) : null,
      minRating: numOrNull('minRating'),
      maxDistanceKm: numOrNull('maxDistanceKm'),
      propertyTypes: Array.from(document.querySelectorAll('#hotelPropertyTypes input:checked')).map(el => el.value),
      minMealPlan: document.getElementById('minMealPlan').value || null,
      ...Object.fromEntries(HOTEL_AMENITY_REQUIREMENTS.map(([prefFlag]) => [prefFlag, document.getElementById(prefFlag).checked])),
    },
    transportPrefs: {
      directOnly: document.getElementById('directOnly').checked,
      requireWifiOnboard: document.getElementById('requireWifiOnboard').checked,
      requirePowerOutlets: document.getElementById('requirePowerOutlets').checked,
      minPunctuality: numOrNull('minPunctuality'),
      preferredDepartTime: document.getElementById('preferredDepartTime').value || null,
      departTimeFlexMinutes: Number(document.getElementById('departTimeFlexHours').value || 0) * 60
                           + Number(document.getElementById('departTimeFlexMinutes').value || 0),
    },
  };
}

/* =========================================================================
 * Direktlinks zu echten Anbietern.
 *
 * Für Bahn, Bus und Hotel gibt es keine frei nutzbare Preis-API - deshalb
 * erfindet diese App dort Beispielpreise (siehe BOOKING_SITES). Statt die
 * Fälschung realistischer zu machen, verlinkt dieser Block die echten
 * Anbieter, damit der tatsächliche Preis einen Klick entfernt ist.
 *
 * Bewusst nur Einstiegsseiten statt vorbefüllter Suchparameter: Flixbus,
 * Omio & Co. adressieren Orte über interne Stations-IDs, die sich von hier
 * aus nicht auflösen lassen. Erfundene Query-Parameter würden Links
 * erzeugen, die zwar aussehen wie eine fertige Suche, aber im Nichts landen
 * - exakt der Fehler, der bei den Beispielpreisen behoben wurde. Einzige
 * Ausnahme ist bahn.de, dessen Deep-Link Klartext-Ortsnamen akzeptiert und
 * im Zweifel auf der normalen Suchmaske landet.
 * ===================================================================== */
const PROVIDER_LINKS = {
  flight: [
    ['Skyscanner', 'https://www.skyscanner.de/'],
    ['Kayak', 'https://www.kayak.de/flights'],
    ['Google Flights', 'https://www.google.com/travel/flights'],
    ['Opodo', 'https://www.opodo.de/'],
    ['Lastminute', 'https://www.lastminute.de/'],
    ['FlyThisWeekend', 'https://flythisweekend.com/de/'],
  ],
  train: [
    ['DB (ICE & Co.)', 'https://www.bahn.de/'],
    ['SNCF Connect (TGV)', 'https://www.sncf-connect.com/'],
    ['Trainline (ICE + TGV kombiniert)', 'https://www.thetrainline.com/'],
    ['Omio', 'https://www.omio.com/'],
    ['Interrail/Eurail', 'https://www.interrail.eu/de'],
  ],
  bus: [
    ['FlixBus', 'https://global.flixbus.com/'],
    ['BlaBlaCar Bus', 'https://www.blablacar.de/bus'],
    ['Omio', 'https://www.omio.com/'],
  ],
  hotel: [
    ['Booking.com', 'https://www.booking.com/'],
    ['Trivago', 'https://www.trivago.de/'],
    ['Lastminute', 'https://www.lastminute.de/'],
    ['HRS', 'https://www.hrs.de/'],
  ],
};

// bahn.de accepts plain place names in its hash deep link; if the format
// ever changes the user still lands on the DB search page.
function bahnDeepLink(route) {
  if (!route.origin || !route.destination) return null;
  const day = isoDay(route.departFrom);
  const time = route.transportPrefs.preferredDepartTime || '09:00';
  const params = new URLSearchParams({
    sts: 'true', so: route.origin, zo: route.destination, hd: `${day}T${time}:00`,
  });
  return `https://www.bahn.de/buchung/fahrplan/suche#${params.toString()}`;
}

// Which provider groups are worth showing for the active mode.
const MODE_PROVIDER_GROUPS = {
  flight: ['flight'], train: ['train'], bus: ['bus'], hotel: ['hotel'],
  train_or_bus: ['train', 'bus'],
  flight_or_train: ['flight', 'train'],
  flight_or_bus: ['flight', 'bus'],
  flight_hotel: ['flight', 'hotel'],
  train_hotel: ['train', 'hotel'],
  bus_hotel: ['bus', 'hotel'],
};
const GROUP_TITLES = { flight: '✈️ Flug', train: '🚆 Bahn', bus: '🚌 Bus', hotel: '🏨 Hotel' };

function renderProviderLinks(route) {
  const groups = MODE_PROVIDER_GROUPS[route.mode] || [];
  if (!groups.length) return '';
  const routeLine = route.origin
    ? `${route.origin} → ${route.destination}, ${fmtDay(route.departFrom)}`
    : `${route.destination}, ab ${fmtDay(route.departFrom)}`;
  const bahn = bahnDeepLink(route);
  return `
    <div class="provider-links">
      <h3>Echte Preise direkt prüfen</h3>
      <p class="provider-note">Kein kostenloser Zugang deckt alle Anbieter ab - Ryanair und Travelpayouts liefern
      echte Flugpreise, Transitous echte Fahrpläne ohne Preis, für Hotels gibt es gar keine freie Quelle.
      Hier die Anbieter selbst, für <strong>${routeLine}</strong>:</p>
      ${groups.map(g => `
        <div class="provider-group">
          <span class="provider-title">${GROUP_TITLES[g]}</span>
          <span class="provider-list">${PROVIDER_LINKS[g].map(([name, url]) => {
            const href = (g === 'train' && name.startsWith('DB') && bahn) ? bahn : url;
            return `<a href="${href}" target="_blank" rel="noopener">${name}</a>`;
          }).join('')}</span>
        </div>
      `).join('')}
    </div>
  `;
}

// An option counts as example data if ANY of its legs is mock - a
// flight+hotel combo with a real flight but an invented hotel price is not a
// bookable total, so it must not look like one.
function isMockOption(opt) {
  return opt.offers.some(o => o.isMock);
}

const MODE_LABELS = { flight: 'Flug', train: 'Bahn', bus: 'Bus', hotel: 'Hotel' };

// Which modes the invented prices actually belong to. "9 Angebote sind
// Beispieldaten" alone is ambiguous - a user on a Flug+Hotel search reads it
// as "the flights are fake" when only the hotel leg is, and there was no way
// to tell the two apart from the outside.
function mockModeLabels(options) {
  const modes = [];
  for (const opt of options) {
    for (const offer of opt.offers) {
      if (!offer.isMock) continue;
      const label = MODE_LABELS[offer.mode];
      if (label && !modes.includes(label)) modes.push(label);
    }
  }
  return modes;
}

/* =========================================================================
 * Ergebnis-Ansicht.
 *
 * renderResults() läuft einmal pro Suche, renderActiveSection() bei jedem
 * Sortier- oder Reiterwechsel - ohne erneute Anbieter-Abfrage. Deshalb hält
 * `shownSearch` die vollständigen, unsortierten Kandidaten aller Abschnitte.
 * ===================================================================== */
const resultControlsEl = document.getElementById('resultControls');
const legTabsEl = document.getElementById('legTabs');
const sortByEl = document.getElementById('sortBy');
// Everything a search produced, kept for re-sorting and section switching.
let shownSearch = null;
// What is on screen right now - the AI recommendation reasons about exactly
// this list, so it follows the active section and sort order.
let lastSearch = null;

function renderResults(route, result) {
  shownSearch = {
    route,
    sections: result.sections,
    flightFallbackReason: result.flightFallbackReason,
    busPriceReason: result.busPriceReason,
    // The whole trip is what was searched for, so that is what opens; the
    // two single-direction lists are the comparison next to it.
    sectionId: (result.sections.find(s => s.id === 'combined') || result.sections[0]).id,
    dealsHtml: null,
  };

  // Real tabs, not just buttons: the list below is their panel, so it gets
  // the tabpanel role and the arrow keys move between them (see below).
  const multi = result.sections.length > 1;
  legTabsEl.hidden = !multi;
  legTabsEl.innerHTML = !multi ? '' : result.sections.map(s => {
    const on = s.id === shownSearch.sectionId;
    return `
    <button type="button" class="legtab${on ? ' active' : ''}" role="tab"
            id="legtab-${s.id}" data-section="${s.id}" aria-selected="${on}"
            aria-controls="searchResults" tabindex="${on ? '0' : '-1'}">
      ${s.label} <span class="count">(${s.candidates.length})</span>
    </button>`;
  }).join('');
  if (multi) searchResultsEl.setAttribute('role', 'tabpanel');
  else searchResultsEl.removeAttribute('role');
  // Nothing found anywhere: a sort control over an empty list is noise.
  resultControlsEl.hidden = !result.sections.some(s => s.candidates.length);
  return renderActiveSection();
}

function renderActiveSection() {
  const { route, sections, sectionId, flightFallbackReason, busPriceReason } = shownSearch;
  const section = sections.find(s => s.id === sectionId) || sections[0];
  for (const btn of legTabsEl.querySelectorAll('.legtab')) {
    const on = btn.dataset.section === section.id;
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-selected', String(on));
    // Roving tabindex: Tab jumps into the tab strip once, then the arrow
    // keys move within it - the usual behaviour for a tablist.
    btn.tabIndex = on ? 0 : -1;
  }
  searchResultsEl.setAttribute('aria-labelledby', `legtab-${section.id}`);
  const options = sortCandidates(section.candidates, sortByEl.value).slice(0, MAX_RESULTS_SHOWN);
  // Keep the "dauerhaft überwachen"-snippet describing the ranking the user
  // is actually looking at.
  route.priority = sortByEl.value;
  if (!trackBox.hidden) trackYaml.value = buildYamlSnippet(route);
  return renderOptionList(route, section, options, flightFallbackReason, busPriceReason);
}

async function renderOptionList(route, section, options, flightFallbackReason, busPriceReason) {
  await addRecommendations(route, options, section.pools);
  // The AI recommendation reasons about what is actually on screen.
  lastSearch = { route, options };
  const label = route.origin ? `${route.origin} → ${route.destination}` : route.destination;
  const mockCount = options.filter(isMockOption).length;
  const timetableCount = options.filter(o => o.hasUnknownPrice).length;
  const realCount = options.length - mockCount - timetableCount;
  // Report each bucket separately instead of one blanket label: the old
  // version said "echte Travelpayouts-Preise" for the whole list as soon as
  // *flights* were real, which mislabelled every invented train/bus/hotel
  // row. A real connection without a price is its own third category.
  const parts = [];
  if (realCount) parts.push(`${realCount} mit echten Preisen`);
  if (timetableCount) parts.push(`${timetableCount} echte Verbindungen ohne Preis`);
  if (mockCount) parts.push(`${mockCount} Beispieldaten`);
  const dealsLabel = route.dealsOnly ? ', nur Deals' : '';
  // The section, when there is more than one, is part of what the count
  // means: "12 Angebote" for a round trip is meaningless without saying
  // whether that is the outbound, the return, or both together.
  const sectionLabel = section.label ? `${section.label}: ` : '';
  // Say when the list is capped, instead of quietly reporting 40 where the
  // section tab says 312.
  const found = section.candidates.length;
  const shown = found > options.length ? `${options.length} von ${found}` : `${options.length}`;
  searchMetaEl.textContent = `${sectionLabel}${shown} Angebote für ${label} (${parts.join(', ')}${dealsLabel})`;
  const sectionNote = section.note ? `<p class="section-note">${section.note}</p>` : '';

  if (!options.length) {
    // With example data off (the default) this is the normal outcome for a
    // route no free source covers - so it has to be genuinely useful: the
    // reason, what to try, and links to check the price for real. Returning
    // just "keine Angebote" here would repeat the old mistake in reverse.
    // "Filter lockern" ist der falsche Rat, wenn in Wahrheit gar keine
    // Quelle etwas hatte - dann gehört der echte Grund hierhin.
    const why = route.dealsOnly
      ? 'Keine Angebote, die deutlich unter dem Durchschnitt dieser Suche liegen - auf "Alle Angebote" umstellen oder das Zeitfenster (Flex-Tage) erweitern.'
      : (flightFallbackReason
          ? `Keine echten Preise gefunden. ${flightFallbackReason}.`
          : (busPriceReason
              ? `Keine Busverbindung gefunden. ${busPriceReason}.`
              : 'Keine Angebote in diesem Budget/Zeitrahmen/Filter gefunden - Filter lockern und erneut suchen.'));
    searchResultsEl.innerHTML = `
      ${sectionNote}
      <p class="empty">${why}</p>
      <p class="empty">Es werden nur echte Daten angezeigt. Über <strong>Datenquelle → „Auch Beispieldaten"</strong>
      lassen sich erfundene Preise einblenden, um die Sortier- und Filterlogik zu testen - buchbar ist davon nichts.</p>
      ${renderProviderLinks(route)}
      <div id="dealsPanel"></div>
    `;
    renderDealsInto(route);
    return;
  }

  // Naming the reason matters: a flight search that quietly fell back looked
  // exactly like one that was never meant to be real - the only visible
  // message was "nicht buchbar", with no hint what to do about it.
  const flightReasonHtml = flightFallbackReason ? `
    <br><br><strong>Warum bei Flügen keine echten Preise?</strong> ${flightFallbackReason}.
    Tipp: Von/Nach aus der Vorschlagsliste auswählen, ein anderes Datum oder mehr Flex-Tage probieren -
    oder die Strecke unten direkt beim Anbieter prüfen.` : '';
  const mockModes = mockModeLabels(options);
  const affected = mockModes.length ? ` – betrifft: <strong>${mockModes.join(', ')}</strong>` : '';
  const warning = mockCount ? `
    <p class="mock-warning">⚠️ <strong>${mockCount === 1 ? 'Eines dieser Angebote enthält' : `${mockCount} dieser Angebote enthalten`} Beispieldaten</strong>${affected}.
    Erfundene Preise zum Testen der Vergleichslogik, keine buchbaren Verbindungen -
    beim jeweiligen Anbieter unten nachsehen.${flightReasonHtml}</p>` : '';
  // Beim Bus reicht "diese Quelle hat keine Preise" nicht: es gibt eine
  // Busquelle mit Preisen (FlixBus), und wenn die nichts liefert, will man
  // wissen warum - sonst liest sich jede Zeile wie ein Programmfehler.
  const busReasonHtml = (busPriceReason && options.some(o => o.offers.some(x => x.mode === 'bus'))) ? `
    <br><br><strong>Warum beim Bus kein Preis?</strong> ${busPriceReason}. Buspreise kommen hier von FlixBus -
    für Fernbusse anderer Anbieter gibt es keine frei zugängliche Preisquelle, deshalb stehen deren Fahrten
    ohne Preis in der Liste.` : '';
  // Fehlen Bahnpreise, weil der lokale Preis-Server nicht erreichbar war,
  // sagt das keine Zeile der Liste - "nicht gestartet" und "Browser hat
  // blockiert" sehen identisch aus. Genau diese Stille hat die Fehlersuche
  // einmal quaelend gemacht, deshalb steht der Grund jetzt da.
  // Ein preisloser Zug hat zwei ganz verschiedene Ursachen, und die Antwort
  // "warum" ist jeweils eine andere: Server nicht erreichbar, oder Server
  // laeuft und die DB kennt diese Verbindung nicht. Beides sah bisher gleich
  // aus - in den Kombis besonders, weil dort die Bahn oft aus dem Fahrplan
  // kommt, obwohl der Server laeuft.
  const trainWithoutPrice = options.some(
    o => o.hasUnknownPrice && o.offers.some(x => x.mode === 'train' && x.priceKnown === false));
  let bahnLiveHint = '';
  if (trainWithoutPrice && _bahnLocal.ok === false) {
    bahnLiveHint = `
    <br><br><strong>Bahnpreise fehlen?</strong> Der lokale Bahn-Preis-Server ist nicht erreichbar
    (<code class="mono">${bahnLocalUrl()}</code>${_bahnLocalLastError ? ` – ${_bahnLocalLastError}` : ''}).
    Läuft er, zeigt die Bahn hier echte Sparpreise. Zwei häufige Gründe: er ist nicht gestartet, oder
    diese Seite wurde über <code class="mono">https</code> geöffnet – dann verbietet der Browser den
    Zugriff auf den eigenen Rechner. Dann die App über
    <a href="${bahnLocalUrl()}/">${bahnLocalUrl()}/</a> öffnen; fürs Handy den Server mit
    <code class="mono">--lan</code> starten und dessen Heimnetz-Adresse benutzen.`;
  } else if (trainWithoutPrice && _bahnLocal.ok === true) {
    bahnLiveHint = `
    <br><br><strong>Warum bei diesen Zügen kein Preis?</strong> Der Bahn-Preis-Server läuft
    (<code class="mono">${bahnLocalUrl()}</code>), aber für diese Verbindung nennt die DB keinen Preis –
    meist, weil sie den Start- oder Zielort nicht als Bahnstation kennt (in den Flug-Kombis stehen dort
    Flughafen-Codes) oder für den Tag noch kein Angebot vorliegt. Die Zeiten stammen dann aus dem
    Fahrplan und stimmen; den Preis beim Anbieter unten prüfen.`;
  }

  const timetableNote = (timetableCount || bahnLiveHint) ? `
    <p class="timetable-note">${timetableCount ? `🕓 <strong>${timetableCount} echte Verbindungen ohne Preis</strong> - Fahrplandaten von
    <a href="https://transitous.org" target="_blank" rel="noopener">Transitous</a> (offizielle Verkehrsverbund-Feeds,
    kostenlos und ohne Anmeldung). Diese Quelle enthält keine Fahrpreise, deshalb steht hier kein Preis statt eines
    erfundenen. Zeiten, Linie und Umstiege stimmen - den Preis unten beim Anbieter prüfen.` : ''}${busReasonHtml}${bahnLiveHint}</p>` : '';

  searchResultsEl.innerHTML = `
    ${sectionNote}
    ${warning}
    ${timetableNote}
    <div class="route">
      ${options.map((opt, i) => {
        const mock = isMockOption(opt);
        const noPrice = Boolean(opt.hasUnknownPrice);
        // Never format the 0 placeholder as a price - that is the whole
        // reason priceKnown exists.
        const priceHtml = noPrice
          ? '<span class="price price-unknown">Preis unbekannt</span>'
          : `<span class="price mono">${opt.price.toFixed(2)} ${route.currency}</span>`;
        const line = opt.offers.map(o => o.lineLabel).filter(Boolean).join(', ');
        // Two transport legs = an option assembled from an outbound and a
        // return, which has to say so rather than show only the outbound.
        const back = returnLeg(opt);
        // Never let an offer from a neighbouring airport look like one from
        // the airport that was actually searched for.
        const detour = opt.offers.find(o => o.detourKm);
        const detourHtml = detour ? `<span class="badge info">ab ${detour.altOrigin || route.origin}${
          detour.altDestination ? ` nach ${detour.altDestination}` : ''} · +${detour.detourKm} km Anfahrt</span>` : '';
        // A 0.00 in the price slot needs its reason right next to it,
        // otherwise it reads as "free" or as a bug rather than as
        // "already paid for with a ticket you hold".
        const dTicket = opt.offers.some(o => o.priceNote === 'im Deutschland-Ticket enthalten')
          ? '<span class="badge good">🎫 im Deutschland-Ticket enthalten</span>' : '';
        return `
        <div class="option${mock ? ' is-mock' : ''}${noPrice ? ' is-timetable' : ''}">
          <span class="rank mono">${i + 1}</span>
          <div class="price-row">
            ${priceHtml}
            ${mock ? '<span class="badge warn">Beispieldaten – nicht buchbar</span>' : ''}
            ${noPrice ? '<span class="badge info">Echter Fahrplan – Preis beim Anbieter</span>' : ''}
            ${dTicket}
            ${detourHtml}
            ${opt.isBelowMedian ? '<span class="badge good">Deal</span>' : ''}
          </div>
          <span class="subline mono">${opt.mode}${line ? ` · ${line}` : ''} · ${fmtShort(opt.offers[0].depart)}${
            back
              ? ` (${opt.offers[0].mode}) · zurück ${fmtShort(back.depart)} (${back.mode})`
              : (opt.offers[0].returnDepart ? ` · zurück ${fmtShort(opt.offers[0].returnDepart)}` : '')
          } · ${durationHtml(opt)} · ${opt.offers.map(o => bookingSiteHtml(o.bookingSite, o.url)).join(', ')}</span>
          <div class="chips">${opt.offers.flatMap(offerChips).map(c => `<span class="chip">${c}</span>`).join('')}</div>
          ${opt.recommendations.length ? `<ul class="recs">${opt.recommendations.map(r => `<li>${r}</li>`).join('')}</ul>` : ''}
        </div>`;
      }).join('')}
    </div>
    ${renderProviderLinks(route)}
    <div id="dealsPanel"></div>
  `;
  renderDealsInto(route);
}

// Deals load after the results are already on screen: they are a bonus, and
// nobody should wait for three RSS feeds before seeing their flights. The
// result is cached per search, so re-sorting or switching between Hin- and
// Rückfahrt redraws the list without hitting the feeds again.
async function renderDealsInto(route) {
  const target = document.getElementById('dealsPanel');
  if (!target) return;
  if (shownSearch && shownSearch.dealsHtml !== null) {
    target.innerHTML = shownSearch.dealsHtml;
    return;
  }
  try {
    const html = renderDeals(await fetchRelevantDeals(route));
    if (shownSearch) shownSearch.dealsHtml = html;
    // Guard against a re-render having replaced the node while we waited.
    (document.getElementById('dealsPanel') || target).innerHTML = html;
  } catch (e) {
    target.innerHTML = ''; // deals are optional - never break the results
  }
}

// Sorting and section switching redraw the list from the candidates already
// in memory - no provider is asked anything a second time.
sortByEl.addEventListener('change', () => { if (shownSearch) renderActiveSection(); });
function selectSection(id) {
  if (!shownSearch || shownSearch.sectionId === id) return;
  shownSearch.sectionId = id;
  renderActiveSection();
}
legTabsEl.addEventListener('click', (ev) => {
  const btn = ev.target.closest('.legtab');
  if (btn) selectSection(btn.dataset.section);
});
// Pfeiltasten/Pos1/Ende innerhalb der Reiterleiste - ohne das ist eine
// role="tablist" nur behauptet, nicht eingelöst.
legTabsEl.addEventListener('keydown', (ev) => {
  const step = { ArrowLeft: -1, ArrowRight: 1, Home: 'first', End: 'last' }[ev.key];
  if (!step || !shownSearch) return;
  const tabs = [...legTabsEl.querySelectorAll('.legtab')];
  const at = tabs.findIndex(t => t.dataset.section === shownSearch.sectionId);
  const next = step === 'first' ? 0
             : step === 'last' ? tabs.length - 1
             : (at + step + tabs.length) % tabs.length;
  if (!tabs[next]) return;
  ev.preventDefault();
  selectSection(tabs[next].dataset.section);
  tabs[next].focus();
});

/* =========================================================================
 * Deal and error-fare feeds. A price API answers "what does this route
 * cost"; it cannot answer "where is something absurdly cheap right now" -
 * and that second question is where the real savings are.
 *
 * Shown as links with titles, never as priced rows: "Mallorca ab 39 EUR" is
 * an advertisement, not a bookable itinerary for the user's dates. Turning
 * it into an offer would repeat the mistake this project already made once.
 * ===================================================================== */
function dealMentions(post, places) {
  const haystack = `${post.title} ${post.summary || ''}`.toLowerCase();
  return places.some(place => place && place.length > 2 && haystack.includes(place.toLowerCase()));
}

async function fetchRelevantDeals(route) {
  if (!PROXY_URL) return [];
  const payload = await fetchProxyJson('deals', new URLSearchParams());
  const posts = (payload && payload.posts) || [];
  // Only what mentions this trip - an unrelated Mallorca offer is noise on
  // a Hamburg->Lyon search, and noise is what makes people stop reading.
  const places = [route.origin, route.destination,
                  AIRPORT_CITY_NAMES[(route.origin || '').toUpperCase()],
                  AIRPORT_CITY_NAMES[(route.destination || '').toUpperCase()]];
  return posts.filter(p => dealMentions(p, places.filter(Boolean))).slice(0, 6);
}

function renderDeals(posts) {
  if (!posts.length) return '';
  return `
    <div class="provider-links">
      <h3>🔥 Aktuelle Deals zu dieser Strecke</h3>
      <p class="provider-note">Aus den Feeds von Urlaubspiraten, Travelfree und Fly4free - Aktionen und
      Fehlerpreise, die keine Preis-API kennt. Das sind Artikel, keine buchbaren Angebote für deine Daten:
      Preis und Verfügbarkeit stehen erst beim Anbieter fest.</p>
      <ul class="recs">
        ${posts.map(p => `<li><a href="${p.url}" target="_blank" rel="noopener">${p.title}</a>
          <span class="subline"> · ${p.source}</span></li>`).join('')}
      </ul>
    </div>`;
}

function buildYamlSnippet(route) {
  const slug = `${route.origin || route.destination}-${route.destination}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
  const fmt = d => d.toISOString().slice(0, 10);
  const hp = route.hotelPrefs, tp = route.transportPrefs;
  // The `routes:` header is included so the snippet is a valid file on its
  // own - pasting it into an empty secret has to just work. Someone who
  // already tracks routes drops this one line, which the box says.
  return `routes:
  - id: ${slug}
    origin: ${route.origin || route.destination}
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
    max_duration_return_hours: ${route.maxDurationReturn ?? 'null'}
    priority: ${route.priority}
    modes: [${route.modes.join(', ')}]
    baggage:
      checked_bags: ${route.checkedBags}
      checked_bag_kg: ${route.checkedBagKg ?? 'null'}
      carry_on_count: ${route.carryOnCount}
      carry_on_max_kg: ${route.carryOnMaxKg ?? 'null'}
    rail:
      bahncard: ${route.bahncard ? `"${route.bahncard}"` : 'null'}
      deutschlandticket: ${route.deutschlandticket}
    hotel:
      min_stars: ${hp.minStars ?? 'null'}
      min_rating: ${hp.minRating ?? 'null'}
      max_distance_km: ${hp.maxDistanceKm ?? 'null'}
      property_types: [${(hp.propertyTypes || []).join(', ')}]
      min_meal_plan: ${hp.minMealPlan ? `"${hp.minMealPlan}"` : 'null'}
${HOTEL_AMENITY_REQUIREMENTS.map(([prefFlag, , yamlKey]) => `      ${yamlKey}: ${hp[prefFlag]}`).join('\n')}
    transport:
      direct_only: ${tp.directOnly}
      require_wifi_onboard: ${tp.requireWifiOnboard}
      require_power_outlets: ${tp.requirePowerOutlets}
      min_punctuality_pct: ${tp.minPunctuality ?? 'null'}
      preferred_depart_time: ${tp.preferredDepartTime ? `"${tp.preferredDepartTime}"` : 'null'}
      depart_time_flex_minutes: ${tp.departTimeFlexMinutes || 0}
    low_cost: ${route.lowCost}
    deals_only: ${route.dealsOnly || false}
    nearby_origin_km: ${route.nearbyOriginKm || 0}
    nearby_destination_km: ${route.nearbyDestinationKm || 0}
    round_trip: ${route.roundTrip || false}
    return_date: ${route.roundTrip && route.returnDate ? fmt(route.returnDate) : 'null'}
`;
}

/* =========================================================================
 * Optional KI-Empfehlung (Gemini), via the same Worker proxy that hides the
 * Travelpayouts token - a Gemini key can't live in browser JS either.
 *
 * Scope, deliberately: Gemini only ever sees the offers this search already
 * found. It cannot look up flights itself, so it explains and recommends
 * rather than searching - the actual "find more flights" work is the
 * month-wise provider querying, not this.
 * ===================================================================== */
const aiBox = document.getElementById('aiBox');
const aiButton = document.getElementById('aiButton');
const aiResultEl = document.getElementById('aiResult');

function buildAiPrompt(route, options) {
  const criteria = [
    `Strecke: ${route.origin || '-'} nach ${route.destination}`,
    `Modus: ${route.mode}`,
    `Reisedatum: ${isoDay(route.departFrom)}${route.roundTrip && route.returnDate ? `, zurück ${isoDay(route.returnDate)}` : ' (nur Hinreise)'}`,
    `Flexibilität: ${route.flexBefore} Tage davor, ${route.flexAfter} Tage danach`,
    route.budget != null ? `Budget: ${route.budget} ${route.currency}` : 'Budget: kein Limit',
    route.maxDuration != null
      ? `Max. Reisezeit${route.maxDurationReturn != null ? ' hin' : ''}: ${route.maxDuration}h`
      : 'Max. Reisezeit: kein Limit',
    route.maxDurationReturn != null ? `Max. Reisezeit zurück: ${route.maxDurationReturn}h` : null,
    `Sortierung: ${route.priority}`,
    route.dealsOnly ? 'Nur Deals/Aktionen' : 'Alle Angebote',
    route.transportPrefs.directOnly ? 'Nur Direktverbindungen' : null,
    route.transportPrefs.preferredDepartTime
      ? `Bevorzugte Abfahrt: ${route.transportPrefs.preferredDepartTime} (±${route.transportPrefs.departTimeFlexMinutes} Min.)`
      : null,
  ].filter(Boolean).join('\n');

  const offers = options.slice(0, 15).map((o, i) => {
    const p = o.offers[0];
    return `${i + 1}. ${o.price.toFixed(2)} ${route.currency} | ${o.mode} | ab ${fmtShort(p.depart)}`
      + `${p.returnDepart ? ` | zurück ${fmtShort(p.returnDepart)}` : ''}`
      + ` | ${o.durationHours > 0 ? o.durationHours + 'h' : 'Dauer unbekannt'}`
      + ` | ${p.stops === 0 ? 'direkt' : p.stops + 'x Umstieg'}`
      + ` | ${o.offers.map(x => x.bookingSite).join(' + ')}`
      + `${o.isBelowMedian ? ' | DEAL' : ''}`;
  }).join('\n');

  return `Du bist ein nüchterner Reise-Berater. Unten stehen die Kriterien einer Suche und die dazu gefundenen Angebote.

Kriterien:
${criteria}

Gefundene Angebote:
${offers}

Aufgabe: Empfiehl auf Deutsch 2-3 dieser Angebote und begründe kurz, warum sie zu den Kriterien passen (Preis, Dauer, Umstiege, Datum). Nenne jeweils die Nummer aus der Liste. Weise auf echte Nachteile hin, falls es welche gibt. Wenn ein Kompromiss lohnt (z.B. ein Tag später deutlich günstiger), sag das.

Wichtig: Bewerte ausschließlich die oben gelisteten Angebote. Erfinde keine Flüge, Preise oder Airlines. Maximal 200 Wörter, keine Einleitung.`;
}

async function requestAiRecommendation() {
  if (!lastSearch || !lastSearch.options.length) return;
  aiButton.disabled = true;
  aiResultEl.hidden = false;
  aiResultEl.textContent = 'Gemini denkt nach…';
  try {
    const resp = await fetch(`${PROXY_URL.replace(/\/$/, '')}/ai`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: buildAiPrompt(lastSearch.route, lastSearch.options) }),
    });
    const payload = await resp.json().catch(() => null);
    if (resp.status === 501) {
      // No provider key set up - say so plainly instead of pretending it failed.
      aiResultEl.textContent = 'KI-Empfehlung ist nicht eingerichtet: im Cloudflare-Worker fehlt ein Anbieter-Schlüssel '
        + '(GEMINI_API_KEY, GROQ_API_KEY oder MISTRAL_API_KEY - siehe README).';
    } else if (!resp.ok || !payload?.text) {
      aiResultEl.textContent = `KI-Empfehlung nicht möglich: ${payload?.error || `HTTP ${resp.status}`}`;
    } else {
      // Name the model, so it's obvious which provider actually answered.
      aiResultEl.textContent = payload.text + (payload.model ? `\n\n— ${payload.model}` : '');
    }
  } catch (e) {
    aiResultEl.textContent = `KI-Empfehlung nicht erreichbar: ${e.message}`;
  } finally {
    aiButton.disabled = false;
  }
}
aiButton.addEventListener('click', requestAiRecommendation);

searchForm.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  // Letzter Riegel: ein Datum, das Browser und Feld-Listener durchgelassen
  // haben (eingefügt, per Skript gesetzt, autovervollständigt), wird hier
  // korrigiert - sichtbar, bevor gesucht wird.
  fixReturnDate();
  fixDepartUntil();
  const route = readRouteFromForm();
  searchMetaEl.textContent = 'suche…';
  searchResultsEl.innerHTML = '';
  aiBox.hidden = true;
  aiResultEl.hidden = true;
  aiResultEl.textContent = '';
  resultControlsEl.hidden = true;
  const result = await runSearch(route);
  await renderResults(route, result);
  // Nothing to reason about without results, and no point offering it when
  // there's no proxy to reach Gemini through.
  const total = result.sections.reduce((n, s) => n + s.candidates.length, 0);
  aiBox.hidden = !(PROXY_URL && total);
  trackYaml.value = buildYamlSnippet(route);
  trackBox.hidden = false;
});

// Copy feedback matters here: the whole flow leaves the page after this
// click, and a silent button leaves you unsure whether to paste yet.
const copyYamlBtn = document.getElementById('copyYaml');
copyYamlBtn.addEventListener('click', async () => {
  trackYaml.select();
  const label = copyYamlBtn.textContent;
  try {
    await navigator.clipboard.writeText(trackYaml.value);
    copyYamlBtn.textContent = '✓ kopiert – jetzt ins Secret einfügen';
  } catch (err) {
    // execCommand is deprecated but still the only fallback where the
    // Clipboard API is blocked (older Safari, non-secure origins).
    copyYamlBtn.textContent = document.execCommand?.('copy')
      ? '✓ kopiert – jetzt ins Secret einfügen'
      : 'Bitte von Hand markieren und kopieren';
  }
  setTimeout(() => { copyYamlBtn.textContent = label; }, 4000);
});

/* The secret lives in the repo this page is published from, so the link is
 * derived from the GitHub Pages host rather than hard-coded - a fork gets
 * its own settings page instead of being sent to someone else's. Falls back
 * to the docs when the page is served from anywhere else (localhost, a
 * custom domain), where the owner/repo simply cannot be known. */
const secretLinkEl = document.getElementById('secretLink');
if (secretLinkEl) {
  const pagesHost = location.hostname.match(/^([\w-]+)\.github\.io$/);
  const repo = pagesHost && location.pathname.split('/').filter(Boolean)[0];
  secretLinkEl.href = repo
    ? `https://github.com/${pagesHost[1]}/${repo}/settings/secrets/actions`
    : 'https://docs.github.com/actions/security-guides/using-secrets-in-github-actions';
}

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
      ${!route.options.length ? '<p class="empty">Keine Angebote gefunden.</p>' : route.options.map((opt, i) => {
        // The cron writes provider="mock-*" for every generated offer, so
        // the dashboard can flag invented prices the same way the live
        // search does.
        const mock = opt.offers.some(o => (o.provider || '').startsWith('mock'));
        // Timetable sources (Transitous) write total_price 0.0 with
        // has_unknown_price set - printing that as "0.00 EUR" would be the
        // exact failure mode price_known exists to prevent.
        const noPrice = Boolean(opt.has_unknown_price);
        const line = opt.offers.map(o => o.line_label).filter(Boolean).join(', ');
        return `
        <div class="option${mock ? ' is-mock' : ''}${noPrice ? ' is-timetable' : ''}">
          <span class="rank mono">${i + 1}</span>
          <div class="price-row">
            ${noPrice
              ? '<span class="price price-unknown">Preis unbekannt</span>'
              : `<span class="price mono">${opt.total_price.toFixed(2)} ${opt.currency}</span>`}
            ${mock ? '<span class="badge warn">Beispieldaten – nicht buchbar</span>' : ''}
            ${noPrice ? '<span class="badge info">Echter Fahrplan – Preis beim Anbieter</span>' : ''}
            ${opt.is_error_fare ? '<span class="badge alert">Fehlerpreis</span>' : ''}
            ${opt.is_price_drop ? '<span class="badge good">Preis gefallen</span>' : ''}
          </div>
          <span class="subline mono">${opt.mode}${line ? ` · ${line}` : ''} · ${durationHtmlFromJson(opt)}${opt.offers[0].return_depart_time ? ` · zurück ${opt.offers[0].return_depart_time.slice(0, 16).replace('T', ' ')}` : ''} · ${opt.offers.map(o => bookingSiteHtml(o.booking_site, o.url)).join(', ')}</span>
          ${(() => {
            const bags = opt.offers.flatMap(baggageChipsFromJson);
            return bags.length ? `<div class="chips">${bags.map(c => `<span class="chip">${c}</span>`).join('')}</div>` : '';
          })()}
          ${opt.recommendations.length ? `<ul class="recs">${opt.recommendations.map(r => `<li>${r}</li>`).join('')}</ul>` : ''}
        </div>`;
      }).join('')}
    </div>
  `).join('');
}

/* default dates so the form is usable without typing: today+30 .. today+34 */
(function seedDefaultDates() {
  const from = addDays(new Date(), 30);
  const until = addDays(new Date(), 34);
  document.getElementById('departFrom').value = isoDay(from);
  document.getElementById('departUntil').value = isoDay(until);
  document.getElementById('returnDate').value = isoDay(addDays(until, 4));
  // Erst jetzt, wo die Felder Werte haben, greifen die Untergrenzen.
  syncDateBounds();
})();
