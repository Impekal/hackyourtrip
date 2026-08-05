'use strict';

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
  const returnDateGroup = document.querySelector('[data-group="returnDateGroup"]');
  if (returnDateGroup) returnDateGroup.hidden = !(cfg.roundTrip && roundTripEl && roundTripEl.checked);
}
document.getElementById('roundTrip')?.addEventListener('change', updateReturnDateVisibility);
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
const BOOKING_SITES = {
  flight: ['Skyscanner', 'Google Flights', 'Kiwi.com', 'Airline direct'],
  train: ['DB Navigator', 'Trainline', 'Omio'],
  bus: ['FlixBus', 'Omio'],
  hotel: ['Booking.com', 'Trivago', 'Hotels.com', 'Airbnb'],
};
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
function roundTripAddon(rng, route, outboundPrice, departHourPool) {
  if (!(route.roundTrip && route.returnDate)) return [outboundPrice, null];
  const returnPrice = round2(outboundPrice * rngFloat(rng, 0.8, 1.2));
  const hour = rngChoice(rng, departHourPool);
  const returnDt = atHour(route.returnDate, hour, rngChoice(rng, [0, 15, 30, 45]));
  return [round2(outboundPrice + returnPrice), returnDt];
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
      const [finalPrice, returnDepart] = roundTripAddon(rng, route, price, hours);
      offers.push({
        mode: 'flight', bookingSite: rngChoice(rng, BOOKING_SITES.flight),
        price: finalPrice, currency: route.currency, depart, durationHours: duration,
        bagFee, isLowCost, returnDepart, ...transportComfortFields(rng, 'flight', [0.55, 0.35, 0.10]),
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
      const [finalPrice, returnDepart] = roundTripAddon(rng, route, basePrice2, hours);
      offers.push({
        mode: 'train', bookingSite: rngChoice(rng, BOOKING_SITES.train),
        price: finalPrice, currency: route.currency,
        depart, durationHours: duration, bagFee: 0, isLowCost: false, returnDepart,
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
      const [finalPrice, returnDepart] = roundTripAddon(rng, route, price, hours);
      offers.push({
        mode: 'bus', bookingSite: rngChoice(rng, BOOKING_SITES.bus),
        price: finalPrice, currency: route.currency, depart, durationHours: duration,
        bagFee: 0, isLowCost: false, returnDepart,
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
        mode: 'hotel', bookingSite: rngChoice(rng, BOOKING_SITES.hotel),
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
    bagFee: 0, isLowCost: false, stops,
    wifiOnboard: false, powerOutlets: false, legroomCm: null, punctualityPct: null,
    // The per-itinerary link goes straight to this exact flight; only fall
    // back to the generic search URL when it's missing.
    url: link ? AVIASALES_BASE + link : buildBookingUrl(route, departIso, raw.return_at),
    returnDepart: raw.return_at ? new Date(raw.return_at.slice(0, 19)) : null,
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

async function fetchProxyJson(path, params) {
  const url = `${PROXY_URL.replace(/\/$/, '')}/${path}?${params.toString()}`;
  const cacheKey = `hyt:${url}`;
  const cached = sessionCacheGet(cacheKey);
  if (cached) return cached;
  try {
    const resp = await fetch(url);
    if (!resp.ok) return null;
    const payload = await resp.json();
    sessionCacheSet(cacheKey, payload);
    return payload;
  } catch (e) {
    return null; // this request failed - callers keep going with the rest
  }
}

async function fetchRealFlightOffers(route) {
  if (!PROXY_URL) return null; // not configured - caller falls back to mock
  const roundTrip = Boolean(route.roundTrip && route.returnDate);
  const wantedDays = new Set(dayCandidates(route).map(isoDay));
  const offers = [];
  const seen = new Set();

  const push = (offer) => {
    // The month query deliberately over-fetches; the flex window decides
    // what actually counts, and identical itineraries collapse to one.
    if (!wantedDays.has(isoDay(offer.depart))) return;
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
      const currency = (latest.currency || route.currency).toUpperCase();
      for (const raw of latest.data || []) {
        if (raw && raw.value) push(latestRawToOffer(raw, currency, route));
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
const OR_COMBO_MODES = { train_or_bus: ['train', 'bus'], flight_or_train: ['flight', 'train'], flight_or_bus: ['flight', 'bus'] };

async function runSearch(route) {
  const pools = {};
  let usedRealFlightData = false;
  async function pool(mode) {
    if (pools[mode]) return pools[mode];
    if (mode === 'flight') {
      const real = await fetchRealFlightOffers(route);
      if (real && real.length) {
        pools[mode] = real;
        usedRealFlightData = true;
      } else {
        pools[mode] = mockFlightOffers(route);
      }
    } else {
      pools[mode] = { train: mockTrainOffers, bus: mockBusOffers, hotel: mockHotelOffers }[mode](route);
    }
    return pools[mode];
  }

  let candidates = [];
  for (const mode of route.modes) {
    if (['flight', 'train', 'bus', 'hotel'].includes(mode)) {
      for (const offer of await pool(mode)) candidates.push({ mode, offers: [offer], price: offer.price, durationHours: offer.durationHours });
    } else if (COMBO_TRANSPORT_MODE[mode]) {
      const tMode = COMBO_TRANSPORT_MODE[mode];
      for (const combo of buildCombos(await pool(tMode), await pool('hotel'))) {
        candidates.push({ mode, offers: [combo.transport, combo.hotel], price: combo.price, durationHours: combo.transport.durationHours });
      }
    } else if (OR_COMBO_MODES[mode]) {
      const [modeA, modeB] = OR_COMBO_MODES[mode];
      for (const offer of [...(await pool(modeA)), ...(await pool(modeB))]) {
        candidates.push({ mode, offers: [offer], price: offer.price, durationHours: offer.durationHours });
      }
    }
  }

  candidates = candidates.filter(c => {
    if (route.budget != null && c.price > route.budget) return false;
    if (route.maxDuration != null && c.durationHours > route.maxDuration && c.mode !== 'hotel') return false;
    if (!route.lowCostOk && c.offers.some(o => o.isLowCost)) return false;
    for (const o of c.offers) {
      if (o.mode === 'hotel' && !meetsHotelPrefs(o, route.hotelPrefs)) return false;
      if (['flight', 'train', 'bus'].includes(o.mode) && !meetsTransportPrefs(o, route.transportPrefs)) return false;
    }
    return true;
  });

  const prices = candidates.map(c => c.price);
  const durations = candidates.map(c => c.durationHours);
  for (const c of candidates) {
    if (route.priority === 'cheapest') c.score = c.price;
    else if (route.priority === 'most_expensive') c.score = -c.price;  // sorted ascending, so negate
    else if (route.priority === 'fastest') c.score = c.durationHours;
    else if (route.priority === 'exact_date') {
      // Days outside the exactly requested window first; price breaks ties.
      c.score = dateDeviationDays(c, route) * 100000 + c.price;
    }
    else {
      const discomfort = 1 - comfortScore(c);
      c.score = BEST_VALUE_PRICE_WEIGHT * normalize(c.price, prices)
              + BEST_VALUE_DURATION_WEIGHT * normalize(c.durationHours, durations)
              + BEST_VALUE_COMFORT_WEIGHT * discomfort;
    }
  }
  candidates.sort((a, b) => a.score - b.score);
  const top = candidates.slice(0, MAX_RESULTS_SHOWN);

  const rates = await getRatesPerEur();
  for (const c of top) {
    c.recommendations = [];
    const primary = c.offers[0];
    const samePool = pools[primary.mode] || [];

    if (['flight', 'train', 'bus'].includes(primary.mode)) {
      // Only compare against offers that also satisfy the route's own
      // transport constraints (esp. the depart-time window) - otherwise
      // this could suggest a time the user already said doesn't work.
      const eligiblePool = samePool.filter(o => meetsTransportPrefs(o, route.transportPrefs));
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
  return { options: top, usedRealFlightData };
}

function fmtHM(date) { return date.toTimeString().slice(0, 5); }
function fmtShort(date) { return date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }) + ' ' + fmtHM(date); }

// Mock offers either have no url at all (JS mocks) or a placeholder
// "https://example.invalid/..." (Python mocks, fed through data/deals.json) -
// only render a clickable booking link for a URL that could actually work.
function bookingSiteHtml(name, url) {
  const isReal = url && !url.includes('example.invalid');
  return isReal ? `<a href="${url}" target="_blank" rel="noopener">${name}</a>` : name;
}

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
    if (offer.punctualityPct != null) chips.push(`${offer.punctualityPct}% pünktlich`);
    if (offer.legroomCm != null) chips.push(`${offer.legroomCm}cm Beinfreiheit`);
    if (offer.wifiOnboard) chips.push('WLAN an Bord');
    if (offer.powerOutlets) chips.push('Steckdosen');
  }
  return chips;
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

function placeSuggestions(term) {
  const source = MODE_TAB_CONFIG[activeMode].placeSource;
  if (source === 'rail') return Promise.resolve(filterRailStations(term));
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
    priority: document.getElementById('priority').value,
    checkedBags: Number(document.getElementById('checkedBags').value || 0),
    // null = "egal": no weight preference stated, distinct from 0 kg.
    checkedBagKg: document.getElementById('checkedBagKgAny').checked
      ? null : Number(document.getElementById('checkedBagKg').value || 23),
    carryOnCount: Number(document.getElementById('carryOnCount').value || 1),
    carryOnMaxKg: document.getElementById('carryOnMaxKgAny').checked
      ? null : Number(document.getElementById('carryOnMaxKg').value || 8),
    bahncard: document.getElementById('bahncard').value,
    deutschlandticket: document.getElementById('deutschlandticket').checked,
    lowCostOk: document.getElementById('lowCostOk').checked,
    roundTrip: cfg.roundTrip && document.getElementById('roundTrip').checked,
    returnDate: (cfg.roundTrip && document.getElementById('roundTrip').checked && document.getElementById('returnDate').value)
      ? new Date(document.getElementById('returnDate').value) : null,
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

function renderResults(route, options, usedRealFlightData) {
  const label = route.origin ? `${route.origin} → ${route.destination}` : route.destination;
  const sourceLabel = usedRealFlightData ? 'echte Travelpayouts-Preise' : 'Mock-Daten, Stand heute';
  searchMetaEl.textContent = `${options.length} Angebote gefunden für ${label} (${sourceLabel})`;
  if (!options.length) {
    searchResultsEl.innerHTML = '<p class="empty">Keine Angebote in diesem Budget/Zeitrahmen/Filter gefunden - Filter lockern und erneut suchen.</p>';
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
          <span class="subline mono">${opt.mode} · ${fmtShort(opt.offers[0].depart)}${opt.offers[0].returnDepart ? ` · zurück ${fmtShort(opt.offers[0].returnDepart)}` : ''} · ${opt.durationHours}h · ${opt.offers.map(o => bookingSiteHtml(o.bookingSite, o.url)).join(', ')}</span>
          <div class="chips">${opt.offers.flatMap(offerChips).map(c => `<span class="chip">${c}</span>`).join('')}</div>
          ${opt.recommendations.length ? `<ul class="recs">${opt.recommendations.map(r => `<li>${r}</li>`).join('')}</ul>` : ''}
        </div>
      `).join('')}
    </div>
  `;
}

function buildYamlSnippet(route) {
  const slug = `${route.origin || route.destination}-${route.destination}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
  const fmt = d => d.toISOString().slice(0, 10);
  const hp = route.hotelPrefs, tp = route.transportPrefs;
  return `  - id: ${slug}
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
    low_cost_airlines_ok: ${route.lowCostOk}
    round_trip: ${route.roundTrip || false}
    return_date: ${route.roundTrip && route.returnDate ? fmt(route.returnDate) : 'null'}
`;
}

searchForm.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const route = readRouteFromForm();
  searchMetaEl.textContent = 'suche…';
  searchResultsEl.innerHTML = '';
  const { options, usedRealFlightData } = await runSearch(route);
  renderResults(route, options, usedRealFlightData);
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
          <span class="subline mono">${opt.mode} · ${opt.total_duration_hours > 0 ? opt.total_duration_hours + 'h' : 'Dauer unbekannt'}${opt.offers[0].return_depart_time ? ` · zurück ${opt.offers[0].return_depart_time.slice(0, 16).replace('T', ' ')}` : ''} · ${opt.offers.map(o => bookingSiteHtml(o.booking_site, o.url)).join(', ')}</span>
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
  document.getElementById('returnDate').value = isoDay(addDays(until, 4));
})();
