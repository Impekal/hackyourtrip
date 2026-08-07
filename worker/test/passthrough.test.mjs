// Exercises the Worker's key-less passthroughs against a stubbed fetch:
// /transit/* (Transitous timetables) and /ryanair/* (real airline fares).
// Checks parameter whitelisting, validation, the outgoing headers each
// upstream demands, and that both work without any secret at all.
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('../src/index.js', import.meta.url), 'utf8');
const mod = await import('data:text/javascript;base64,' + Buffer.from(src).toString('base64'));
const worker = mod.default;

const realFetch = globalThis.fetch;
// The handler edge-caches; Node has no Cache API, so stand one in that always
// misses. Caching behaviour itself is Cloudflare's, not ours to test.
globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };
const ctx = { waitUntil() {} };

let failures = 0;
function report(ok, label, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) {
    failures += 1;
    if (detail) console.log('   ', detail);
  }
}

function stubFetch(body, status = 200) {
  globalThis.fetch = async (url, init) => {
    globalThis.__last = { url, init };
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  };
}

async function call(path, env = {}) {
  const resp = await worker.fetch(new Request(`https://proxy.test${path}`), env, ctx);
  return { resp, body: await resp.json().catch(() => null), last: globalThis.__last };
}

// 1. Works with no secrets configured at all - trains must not depend on a
//    flight token the deployment may not have.
stubFetch([{ type: 'STOP', name: 'Berlin Hauptbahnhof', id: 'stop-1' }]);
{
  const { resp, body, last } = await call('/transit/geocode?text=Berlin%20Hbf&language=de');
  report(resp.status === 200 && Array.isArray(body) && body[0].id === 'stop-1'
    && last.url.startsWith('https://api.transitous.org/api/v1/geocode')
    && new URL(last.url).searchParams.get('text') === 'Berlin Hbf',
    'geocode works without TRAVELPAYOUTS_TOKEN', last?.url);
}

// 2. Identifies itself, as Transitous asks API consumers to.
{
  const { last } = await call('/transit/geocode?text=Berlin');
  report(/HackYourTrip/.test(last.init.headers['User-Agent']),
    'sends an identifying User-Agent', JSON.stringify(last?.init?.headers));
}

// 3. Only whitelisted params are forwarded - not an open relay.
{
  const { last } = await call('/transit/geocode?text=Berlin&evil=1&placeTypes=SECRET');
  const forwarded = new URL(last.url).searchParams;
  report(forwarded.get('text') === 'Berlin' && !forwarded.has('evil') && !forwarded.has('placeTypes'),
    'drops non-whitelisted query params', last?.url);
}

// 4. plan forwards exactly the routing params the client sends.
stubFetch({ itineraries: [{ duration: 14940, startTime: '2026-09-15T08:37:00Z' }] });
{
  const { resp, body, last } = await call(
    '/transit/plan?fromPlace=stop-1&toPlace=stop-2&time=2026-09-15T04:00:00Z&numItineraries=5&transitModes=HIGHSPEED_RAIL');
  const params = new URL(last.url).searchParams;
  report(resp.status === 200 && body.itineraries.length === 1
    && last.url.startsWith('https://api.transitous.org/api/v1/plan')
    && params.get('fromPlace') === 'stop-1' && params.get('toPlace') === 'stop-2'
    && params.get('numItineraries') === '5' && params.get('transitModes') === 'HIGHSPEED_RAIL',
    'plan forwards routing params', last?.url);
}

// 5./6. Missing required params are rejected here rather than upstream.
{
  const { resp } = await call('/transit/plan?fromPlace=stop-1');
  report(resp.status === 400, 'plan without toPlace -> 400');
}
{
  const { resp } = await call('/transit/geocode');
  report(resp.status === 400, 'geocode without text -> 400');
}

// 7. Unknown sub-path is a 404, not a blind proxy.
{
  const { resp } = await call('/transit/anything-else?text=x');
  report(resp.status === 404, 'unknown /transit/* endpoint -> 404');
}

// 8. Upstream failure surfaces as 502 with a readable reason.
globalThis.fetch = async () => { throw new Error('network down'); };
{
  const { resp, body } = await call('/transit/geocode?text=Berlin');
  report(resp.status === 502 && /network down/.test(body.error), 'upstream failure -> 502');
}

// 9. A flight request still needs the token - the transit route must not have
//    opened a hole in that check.
stubFetch({ success: true, data: [] });
{
  const { resp } = await call('/cheap?origin=BER&destination=BCN');
  report(resp.status === 500, 'flight endpoint still requires the token');
}

// ---- Ryanair passthrough -------------------------------------------------

stubFetch({ fares: [{ outbound: { flightNumber: 'FR132', price: { value: 53.36 } } }] });
{
  const { resp, body, last } = await call(
    '/ryanair/oneWayFares?departureAirportIataCode=BER&arrivalAirportIataCode=BCN'
    + '&outboundDepartureDateFrom=2026-09-01&outboundDepartureDateTo=2026-09-30&currency=EUR&limit=200');
  const params = new URL(last.url).searchParams;
  report(resp.status === 200 && body.fares.length === 1
    && last.url.startsWith('https://services-api.ryanair.com/farfnd/v4/oneWayFares')
    && params.get('departureAirportIataCode') === 'BER'
    && params.get('outboundDepartureDateTo') === '2026-09-30',
    'ryanair oneWayFares forwards the date range', last?.url);
}

{
  const { last } = await call(
    '/ryanair/roundTripFares?departureAirportIataCode=BER&arrivalAirportIataCode=BCN'
    + '&inboundDepartureDateFrom=2026-09-21&inboundDepartureDateTo=2026-09-21');
  report(last.url.includes('/roundTripFares')
    && new URL(last.url).searchParams.get('inboundDepartureDateFrom') === '2026-09-21',
    'ryanair roundTripFares forwards the inbound window', last?.url);
}

{
  // A plain script UA gets 403 on some Ryanair hosts.
  const { last } = await call('/ryanair/oneWayFares?departureAirportIataCode=BER&arrivalAirportIataCode=BCN');
  report(/Mozilla/.test(last.init.headers['User-Agent']),
    'ryanair request looks like a browser', JSON.stringify(last?.init?.headers));
}

{
  const { last } = await call('/ryanair/oneWayFares?departureAirportIataCode=BER&arrivalAirportIataCode=BCN&evil=1');
  report(!new URL(last.url).searchParams.has('evil'),
    'ryanair drops non-whitelisted params', last?.url);
}

{
  const { resp } = await call('/ryanair/oneWayFares?departureAirportIataCode=BER');
  report(resp.status === 400, 'ryanair fare lookup without destination -> 400');
}

{
  const { resp } = await call('/ryanair/somethingElse');
  report(resp.status === 404, 'unknown /ryanair/* endpoint -> 404');
}

{
  // Works with no secrets at all - same rule as /transit/*.
  const { resp } = await call('/ryanair/airports');
  report(resp.status === 200, 'ryanair airports works without TRAVELPAYOUTS_TOKEN');
}

// ---- FlixBus passthrough -------------------------------------------------

stubFetch([{ name: 'Berlin', legacy_id: 88, id: '40d8f682-8646-11e6-9066-549f350fcb0c' }]);
{
  const { resp, body, last } = await call('/flixbus/cities?q=Berlin&lang=de');
  report(resp.status === 200 && body[0].id.startsWith('40d8f682')
    && last.url.startsWith('https://global.api.flixbus.com/search/autocomplete/cities')
    && last.init.headers['X-API-Authentication'] === '3vJKYJVSDF9ZLcTAKX4V',
    'flixbus cities forwards q and the public API header', last?.url);
}

stubFetch({ trips: [{ results: { 'uid-1': { status: 'available', price: { total: 21.48 } } } }] });
{
  const { resp, body, last } = await call(
    '/flixbus/search?from_city_id=40d8f682-8646-11e6-9066-549f350fcb0c'
    + '&to_city_id=40d901a5-8646-11e6-9066-549f350fcb0c&departure_date=15.09.2026'
    + '&currency=EUR&locale=de&search_by=cities');
  const params = new URL(last.url).searchParams;
  report(resp.status === 200 && body.trips.length === 1
    && params.get('departure_date') === '15.09.2026'
    && params.get('search_by') === 'cities',
    'flixbus search forwards the routing params', last?.url);
}

{
  const { last } = await call('/flixbus/cities?q=Berlin&evil=1');
  report(!new URL(last.url).searchParams.has('evil'), 'flixbus drops non-whitelisted params', last?.url);
}

{
  const { resp } = await call('/flixbus/search?from_city_id=a&to_city_id=b');
  report(resp.status === 400, 'flixbus search without a date -> 400');
}

{
  const { resp } = await call('/flixbus/nope?q=x');
  report(resp.status === 404, 'unknown /flixbus/* endpoint -> 404');
}

// ---- Skiplagged + Deals --------------------------------------------------

stubFetch({ flights: {}, depart: [], airlines: {} });
{
  const { resp, last } = await call('/skiplagged?from=HAM&to=LYS&depart=2026-09-15');
  const params = new URL(last.url).searchParams;
  report(resp.status === 200
    && last.url.startsWith('https://skiplagged.com/api/search.php')
    && params.get('from') === 'HAM' && params.get('depart') === '2026-09-15'
    && params.get('poll') === 'true',
    'skiplagged forwards the route and forces poll=true', last?.url);
}

{
  const { resp } = await call('/skiplagged?from=HAM&to=LYS');
  report(resp.status === 400, 'skiplagged without a date -> 400');
}

{
  const { last } = await call('/skiplagged?from=HAM&to=LYS&depart=2026-09-15&evil=1');
  report(!new URL(last.url).searchParams.has('evil'), 'skiplagged drops unknown params', last?.url);
}

// RSS -> JSON, including the double-escaped HTML these feeds ship.
globalThis.fetch = async () => new Response(
  '<rss><channel><item><title>G&uuml;nstig nach Lyon ab 39 &euro;</title>'
  + '<link>https://x/1</link><pubDate>Thu, 06 Aug 2026</pubDate>'
  + '<description>&lt;p&gt;Fl&uuml;ge im September&lt;/p&gt;</description></item></channel></rss>',
  { status: 200, headers: { 'Content-Type': 'application/rss+xml' } });
{
  const { resp, body } = await call('/deals');
  const post = body.posts && body.posts[0];
  report(resp.status === 200 && body.posts.length >= 1
    && post.title === 'Günstig nach Lyon ab 39 €'
    && post.summary === 'Flüge im September'
    && post.url === 'https://x/1',
    'deals: RSS becomes JSON with entities decoded and tags stripped',
    JSON.stringify(post));
}

// A dead feed must not take the endpoint down - deals are a bonus.
globalThis.fetch = async () => { throw new Error('feed down'); };
{
  const { resp, body } = await call('/deals');
  report(resp.status === 200 && Array.isArray(body.posts) && body.posts.length === 0,
    'deals: a dead feed yields an empty list, not an error');
}

// --- /bahn/* -------------------------------------------------------------
// The only known source of real DB *fares*. Upstream wants POST; the proxy
// only ever accepts GET, so the body is built here from whitelisted params.
stubFetch([{ id: 'A=1@O=Berlin Hbf@L=8011160@', name: 'Berlin Hbf' }]);
{
  const { resp, body, last } = await call('/bahn/orte?q=Berlin%20Hbf');
  report(resp.status === 200 && body[0].name === 'Berlin Hbf'
    && last.url.startsWith('https://www.bahn.de/web/api/reiseloesung/orte')
    && new URL(last.url).searchParams.get('suchbegriff') === 'Berlin Hbf',
    'bahn orte forwards the search term', last?.url);
}

stubFetch({ verbindungen: [{ angebotsPreis: { betrag: 39.9, waehrung: 'EUR' } }] });
{
  const { resp, body, last } = await call(
    '/bahn/fahrplan?from=A%3D1%40L%3D8011160%40&to=A%3D1%40L%3D8000261%40&date=2026-09-15T08:00:00');
  const sent = JSON.parse(last.init.body);
  report(resp.status === 200 && body.verbindungen[0].angebotsPreis.betrag === 39.9
    && last.init.method === 'POST'
    && sent.abfahrtsHalt === 'A=1@L=8011160@' && sent.ankunftsHalt === 'A=1@L=8000261@'
    && sent.anfrageZeitpunkt === '2026-09-15T08:00:00'
    && sent.klasse === 'KLASSE_2',
    'bahn fahrplan turns GET params into the upstream POST body',
    JSON.stringify(sent).slice(0, 200));
}

// A bare day is what a date input produces; widen it rather than reject it.
{
  const { last } = await call('/bahn/fahrplan?from=a&to=b&date=2026-09-15');
  report(JSON.parse(last.init.body).anfrageZeitpunkt === '2026-09-15T08:00:00',
    'a bare date is widened to a timestamp');
  const { last: best } = await call('/bahn/bestpreis?from=a&to=b&date=2026-09-15');
  report(JSON.parse(best.init.body).anfrageZeitpunkt === '2026-09-15T00:00:00'
    && best.url.endsWith('/tagesbestpreis'),
    'bestpreis scans from midnight, not from 08:00', best?.url);
}

{
  const { last } = await call('/bahn/fahrplan?from=a&to=b&date=2026-09-15&class=1');
  report(JSON.parse(last.init.body).klasse === 'KLASSE_1', 'first class is passed through');
}

// bahn.de's own frontend sends a correlation ID on every call, and the fare
// endpoint is the one that refuses requests without it.
{
  const { last } = await call('/bahn/fahrplan?from=a&to=b&date=2026-09-15');
  const id = last.init.headers['X-Correlation-ID'];
  report(typeof id === 'string' && /^[0-9a-f-]{36}_[0-9a-f-]{36}$/.test(id),
    'the fare search sends a correlation ID in the site\'s format', id);
  const { last: again } = await call('/bahn/fahrplan?from=a&to=b&date=2026-09-16');
  report(again.init.headers['X-Correlation-ID'] !== id,
    'each fare search gets its own correlation ID');
}

// Regional trains must stay in: the cheap fare is often the slow connection.
{
  const { last } = await call('/bahn/fahrplan?from=a&to=b&date=2026-09-15');
  const products = JSON.parse(last.init.body).produktgattungen;
  report(products.includes('REGIONAL') && products.includes('ICE'),
    'all product types are searched, not just long distance');
}

{
  const { resp } = await call('/bahn/fahrplan?from=a&to=b');
  report(resp.status === 400, 'bahn fahrplan without a date -> 400');
  const { resp: noQ } = await call('/bahn/orte');
  report(noQ.status === 400, 'bahn orte without q -> 400');
  const { resp: bad } = await call('/bahn/fahrplan?from=a&to=b&date=15.09.2026');
  report(bad.status === 400, 'a malformed date is rejected before it reaches DB');
  const { resp: nope } = await call('/bahn/nope?q=x');
  report(nope.status === 404, 'unknown /bahn/* endpoint -> 404');
}

// The bot wall is the expected outcome from a datacenter IP. It has to be
// distinguishable from a generic failure, so the page can say what happened
// instead of quietly showing no train price at all.
stubFetch({ status: 'ERROR', code: 'OPS_BLOCKED' }, 403);
{
  const { resp, body } = await call('/bahn/fahrplan?from=a&to=b&date=2026-09-15');
  report(resp.status === 403 && body.blocked === true && /bot protection/i.test(body.error),
    'a DB block is reported as blocked, not as an empty result', JSON.stringify(body));
}

globalThis.fetch = realFetch;
if (failures) process.exitCode = 1;
