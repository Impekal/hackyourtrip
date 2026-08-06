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

globalThis.fetch = realFetch;
if (failures) process.exitCode = 1;
