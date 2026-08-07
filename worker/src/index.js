/**
 * HackYourTrip proxy: hides API credentials from the public "Suche" tab.
 *
 * The interactive search runs entirely in the visitor's browser (docs/app.js)
 * so it can't hold real API credentials itself - anyone could open dev tools
 * and steal them. This Worker is the one place they actually live (as
 * Cloudflare secrets, never in source):
 *
 *   GET  /cheap   -> Travelpayouts aviasales/v3/prices_for_dates
 *   GET  /latest  -> Travelpayouts v2/prices/latest
 *   POST /ai      -> whichever AI provider has its key set, for the optional
 *                    "KI-Empfehlung" (see AI_PROVIDERS; with none set the
 *                    endpoint reports itself unconfigured and the UI says so)
 *
 * Deliberately thin: no business logic here beyond auth-hiding, input
 * validation, CORS, and edge caching - month fan-out, duration estimation,
 * and ranking all stay in docs/app.js, mirroring the same split
 * traveldeals/providers/travelpayouts.py has on the Python side.
 *
 * Edge caching (Cache API, ~1h TTL) matters here specifically because this
 * runs behind a public GitHub Pages site: without it, enough visitors
 * searching the same popular route could burn through the free Travelpayouts
 * quota fast. For additional protection against abusive traffic, consider
 * adding a Cloudflare dashboard rate-limiting rule (Free plan includes basic
 * ones) - not implemented in code here since reliable request counting
 * across Cloudflare's distributed edge needs Durable Objects/KV, overkill for
 * a hobby project's quota protection.
 */

// Two upstream endpoints, both queried per *month* rather than per day:
// asking prices_for_dates for one date returns a single offer, asking for
// the month returns dozens (measured against the live API). `latest` is a
// separate index that surfaces partly different itineraries, so the client
// merges both. See traveldeals/providers/travelpayouts.py for the same
// split on the Python side.
const UPSTREAM = {
  prices_for_dates: "https://api.travelpayouts.com/aviasales/v3/prices_for_dates",
  latest: "https://api.travelpayouts.com/v2/prices/latest",
};
const CACHE_TTL_SECONDS = 3600;

// Transitous (MOTIS): free, community-run public-transport routing, no key
// and no account - which is why the browser search can use it at all. It is
// proxied here anyway for two reasons: the client stops depending on
// Transitous' CORS policy, and the edge cache spares a volunteer-funded
// service from answering the same popular route for every single visitor.
//
// It serves timetables, never fares - see traveldeals/providers/transitous.py.
// The client marks those offers as price-less instead of inventing a number.
const TRANSIT_UPSTREAM = {
  geocode: "https://api.transitous.org/api/v1/geocode",
  plan: "https://api.transitous.org/api/v1/plan",
};
const TRANSIT_FORWARDABLE_PARAMS = {
  geocode: ["text", "language"],
  plan: ["fromPlace", "toPlace", "time", "numItineraries", "transitModes", "arriveBy"],
};
// Transitous asks API consumers to identify themselves, so they can get in
// touch about traffic rather than just blocking it.
const TRANSIT_USER_AGENT = "HackYourTrip/1.0 (+https://github.com/kalivolut/hackyourtrip)";

// Ryanair's own fare finder: public, no key, no account - and unlike the
// Travelpayouts index these are *live, bookable* fares straight from the
// airline. Verified against the live service (HTTP 200 with real fares for
// BER->BCN); `availability` needs a booking session and is deliberately not
// used, `cheapestPerDay` came back empty and is skipped too.
//
// Obvious limit: Ryanair only knows Ryanair routes. It is merged with the
// Travelpayouts results rather than replacing them.
const RYANAIR_UPSTREAM = {
  oneWayFares: "https://services-api.ryanair.com/farfnd/v4/oneWayFares",
  roundTripFares: "https://services-api.ryanair.com/farfnd/v4/roundTripFares",
  airports: "https://www.ryanair.com/api/views/locate/5/airports/de/active",
};
const RYANAIR_FORWARDABLE_PARAMS = [
  "departureAirportIataCode", "arrivalAirportIataCode",
  "outboundDepartureDateFrom", "outboundDepartureDateTo",
  "inboundDepartureDateFrom", "inboundDepartureDateTo",
  "currency", "language", "limit", "market", "offset",
];
// A plain script user-agent gets 403 on some of Ryanair's hosts, so the
// proxy presents itself as an ordinary browser - the same request a visitor
// clicking through ryanair.com would make.
const RYANAIR_HEADERS = {
  "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
  Accept: "application/json, text/plain, */*",
  "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
};

// FlixBus' own search backend: public, keyless, and - unlike Transitous -
// it carries real bookable prices, seat counts and transfer info. The
// X-API-Authentication constant below is the one their web client ships to
// every visitor; it is not a credential of ours and not a secret.
//
// Verified live: Berlin -> Munich returned 21.48 EUR (22.47 with booking
// fee). Note that city *UUIDs* are required - the numeric legacy_id in the
// autocomplete response is rejected with "Signature ... is invalid".
const FLIXBUS_UPSTREAM = {
  cities: "https://global.api.flixbus.com/search/autocomplete/cities",
  search: "https://global.api.flixbus.com/search/service/v4/search",
};
const FLIXBUS_FORWARDABLE_PARAMS = {
  cities: ["q", "lang"],
  search: ["from_city_id", "to_city_id", "departure_date", "products",
            "currency", "locale", "search_by", "include_after_midnight_rides"],
};
const FLIXBUS_HEADERS = {
  "X-API-Authentication": "3vJKYJVSDF9ZLcTAKX4V",
  "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
  Accept: "application/json, text/plain, */*",
  "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
};

// Deutsche Bahn. This is the API bahn.de's own website calls, and it is the
// only known source that returns actual train *fares* rather than just a
// timetable (Transitous gives us the timetable already). It is protected by
// a bot wall: a GitHub Actions runner gets 403 OPS_BLOCKED. Whether a
// Cloudflare Worker's egress fares better is exactly what the /bahn/status
// endpoint below is there to answer - so a failure here is a measurement,
// not a bug, and the client is told which of the two it is.
const BAHN_UPSTREAM = {
  orte: "https://www.bahn.de/web/api/reiseloesung/orte",
  fahrplan: "https://www.bahn.de/web/api/angebote/fahrplan",
  bestpreis: "https://www.bahn.de/web/api/angebote/tagesbestpreis",
};
// Measured 07.08.2026: from a Cloudflare Worker the GET station search
// answers 200 with real data, while the POST fare search answers 403. The
// IP is therefore not the problem - the request shape is. bahn.de's own
// frontend sends a correlation ID on every call, so it goes out here too.
const BAHN_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
  Accept: "application/json",
  "Accept-Language": "de-DE,de;q=0.9",
  "Content-Type": "application/json; charset=UTF-8",
  Origin: "https://www.bahn.de",
  Referer: "https://www.bahn.de/buchung/fahrplan/suche",
};

// The site's format is two UUIDs joined by an underscore.
function bahnCorrelationId() {
  return `${crypto.randomUUID()}_${crypto.randomUUID()}`;
}
// All products, i.e. don't silently hide regional trains - the cheap fare is
// often exactly the slow connection.
const BAHN_PRODUCTS = ["ICE", "EC_IC", "IR", "REGIONAL", "SBAHN", "BUS",
                        "SCHIFF", "UBAHN", "TRAM", "ANRUFPFLICHTIG"];

function bahnSearchBody(from, to, dateTime, klasse) {
  return {
    abfahrtsHalt: from,
    ankunftsHalt: to,
    anfrageZeitpunkt: dateTime,
    ankunftSuche: "ABFAHRT",
    klasse: klasse === "1" ? "KLASSE_1" : "KLASSE_2",
    produktgattungen: BAHN_PRODUCTS,
    reisende: [{
      typ: "ERWACHSENER",
      ermaessigungen: [{ art: "KEINE_ERMAESSIGUNG", klasse: "KLASSENLOS" }],
      alter: [],
      anzahl: 1,
    }],
    schnelleVerbindungen: true,
    sitzplatzOnly: false,
    bikeCarriage: false,
    reservierungsKontingenteVorhanden: false,
  };
}

// Skiplagged: covers the full-service carriers Ryanair doesn't fly and the
// Travelpayouts cache misses. Quotes in USD (evidenced: the site renders "$",
// and BER->BCN was 62.00 there where Ryanair said 53.36 EUR - ratio 0.86, the
// EUR/USD rate) - the client converts, see providers/skiplagged.py.
const SKIPLAGGED_UPSTREAM = "https://skiplagged.com/api/search.php";
const SKIPLAGGED_FORWARDABLE_PARAMS = ["from", "to", "depart", "return", "sort"];

// Deal and error-fare feeds: plain RSS, free, key-less. Proxied because a
// browser cannot read cross-origin XML, and converted to JSON here so the
// client doesn't need an XML parser. Cached hard - these update hourly at
// most, and every visitor pulling three feeds directly would be rude.
const DEAL_FEEDS = [
  ["Urlaubspiraten", "https://www.urlaubspiraten.de/feed"],
  ["Travelfree", "https://travelfree.info/feed/"],
  ["Fly4free", "https://www.fly4free.com/feed/"],
];
const DEAL_MAX_ITEMS_PER_FEED = 12;

// Only these may be forwarded upstream - keeps the proxy from being turned
// into an open relay for arbitrary Travelpayouts query parameters.
const FORWARDABLE_PARAMS = [
  "departure_at", "return_at", "one_way", "sorting", "limit",
  "period_type", "beginning_of_period",
];

// Providers for the optional AI recommendation, in priority order: the
// first one with its key present wins. Several are supported on purpose -
// Google blocks API-key creation for some accounts entirely (age, region,
// or Workspace policy), and that shouldn't be the end of the feature. Groq
// and Mistral hand out keys without a cloud project or billing setup.
//
// Whichever runs, it only ever sees the offers the search already found -
// none of them can look up flights, so they analyse and recommend rather
// than search.
//
// Each model can be overridden with the AI_MODEL secret/var without a code
// change, since providers retire model names on their own schedule.
const AI_PROVIDERS = [
  {
    name: "gemini",
    keyVar: "GEMINI_API_KEY",
    defaultModel: "gemini-2.0-flash",
    buildRequest(key, model, prompt) {
      return {
        url: `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(key)}`,
        headers: { "Content-Type": "application/json" },
        body: {
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { temperature: 0.3, maxOutputTokens: 700 },
        },
      };
    },
    extractText: (payload) => (payload?.candidates?.[0]?.content?.parts || [])
      .map((p) => p.text || "").join(""),
    extractError: (payload) => payload?.error?.message,
  },
  // Groq and Mistral both speak the OpenAI chat-completions shape, so they
  // share buildRequest/extractText and differ only in URL and model.
  {
    name: "groq",
    keyVar: "GROQ_API_KEY",
    defaultModel: "llama-3.3-70b-versatile",
    url: "https://api.groq.com/openai/v1/chat/completions",
  },
  {
    name: "mistral",
    keyVar: "MISTRAL_API_KEY",
    defaultModel: "mistral-small-latest",
    url: "https://api.mistral.ai/v1/chat/completions",
  },
];

function openAiStyleRequest(key, model, prompt, url) {
  return {
    url,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
    body: {
      model,
      messages: [{ role: "user", content: prompt }],
      temperature: 0.3,
      max_tokens: 700,
    },
  };
}

// Every provider that has a key, in priority order. It is deliberately a
// list and not a single pick: a key that is present can still be refused
// (quota used up, billing lapsed, key revoked), and when that happens the
// next configured provider should answer instead of the whole feature
// going dark. AI_MODEL, if set, only applies to the first provider - it
// names one specific model and would be nonsense passed to the others.
function availableAiProviders(env) {
  return AI_PROVIDERS.filter((p) => env[p.keyVar]).map((provider, index) => {
    const model = (index === 0 && env.AI_MODEL) || provider.defaultModel;
    return {
      name: provider.name,
      model,
      prepare: (prompt) => (provider.buildRequest
        ? provider.buildRequest(env[provider.keyVar], model, prompt)
        : openAiStyleRequest(env[provider.keyVar], model, prompt, provider.url)),
      readText: provider.extractText
        || ((payload) => payload?.choices?.[0]?.message?.content || ""),
      readError: provider.extractError
        || ((payload) => payload?.error?.message || payload?.message),
    };
  });
}

const AI_MAX_BODY_BYTES = 32 * 1024;

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

function jsonResponse(body, status, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders(origin) },
  });
}

function isValidIataLike(code) {
  return typeof code === "string" && /^[A-Za-z]{2,4}$/.test(code);
}

// Accepts both "YYYY-MM" (a whole month, what the search actually uses) and
// "YYYY-MM-DD".
function isValidDateOrMonth(value) {
  return typeof value === "string" && /^\d{4}-\d{2}(-\d{2})?$/.test(value);
}

/**
 * POST /ai - forward a prepared prompt to whichever AI provider is
 * configured and hand back just the text. The prompt is built client-side
 * from offers the search already found; nothing here fetches travel data.
 */
async function handleAiRequest(request, env, allowedOrigin) {
  if (request.method !== "POST") {
    return jsonResponse({ error: "Use POST for /ai." }, 405, allowedOrigin);
  }
  const providers = availableAiProviders(env);
  if (!providers.length) {
    // Not an error: the AI recommendation is optional, and the UI says so
    // rather than showing a failure.
    return jsonResponse({
      configured: false,
      error: `No AI provider configured. Set one of: ${AI_PROVIDERS.map((p) => p.keyVar).join(", ")}.`,
    }, 501, allowedOrigin);
  }

  let body;
  try {
    const raw = await request.text();
    if (raw.length > AI_MAX_BODY_BYTES) {
      return jsonResponse({ error: "Prompt too large." }, 413, allowedOrigin);
    }
    body = JSON.parse(raw);
  } catch (err) {
    return jsonResponse({ error: "Body must be JSON." }, 400, allowedOrigin);
  }
  const prompt = typeof body?.prompt === "string" ? body.prompt.trim() : "";
  if (!prompt) {
    return jsonResponse({ error: "Missing 'prompt'." }, 400, allowedOrigin);
  }

  // Try each configured provider in turn. The first one that answers wins;
  // the reasons the others gave are kept so a total failure still says what
  // went wrong with each, instead of only naming the last one tried.
  const failures = [];
  for (const provider of providers) {
    const spec = provider.prepare(prompt);
    let upstreamResponse;
    try {
      upstreamResponse = await fetch(spec.url, {
        method: "POST",
        headers: spec.headers,
        body: JSON.stringify(spec.body),
      });
    } catch (err) {
      failures.push(`${provider.name}: request failed: ${err.message}`);
      continue;
    }

    const payload = await upstreamResponse.json().catch(() => null);
    if (!upstreamResponse.ok) {
      failures.push(`${provider.name}: ${provider.readError(payload) || `status ${upstreamResponse.status}`}`);
      continue;
    }
    const text = (provider.readText(payload) || "").trim();
    if (!text) {
      failures.push(`${provider.name}: returned no usable text`);
      continue;
    }
    return jsonResponse({
      configured: true,
      provider: provider.name,
      model: provider.model,
      // Named only when an earlier provider had to be skipped, so the page
      // can say why the answer came from somewhere else.
      ...(failures.length ? { fallbackFrom: failures } : {}),
      text,
    }, 200, allowedOrigin);
  }
  return jsonResponse({ error: `All AI providers failed. ${failures.join(" | ")}` }, 502, allowedOrigin);
}

/**
 * GET /transit/geocode and GET /transit/plan - Transitous passthrough.
 *
 * Needs no secret, so it deliberately sits in front of the
 * TRAVELPAYOUTS_TOKEN check: real train and bus timetables must keep working
 * even on a deployment that has no flight token at all.
 */
async function handleTransitRequest(incoming, request, ctx, allowedOrigin) {
  const kind = incoming.pathname.replace(/^\/+|\/+$/g, "").slice("transit/".length);
  if (!TRANSIT_UPSTREAM[kind]) {
    return jsonResponse({ error: "Unknown transit endpoint. Use /transit/geocode or /transit/plan." }, 404, allowedOrigin);
  }

  const upstream = new URL(TRANSIT_UPSTREAM[kind]);
  for (const name of TRANSIT_FORWARDABLE_PARAMS[kind]) {
    const value = incoming.searchParams.get(name);
    if (value) upstream.searchParams.set(name, value);
  }
  // Without these two the plan endpoint has nothing to route between and
  // would answer 400 - catch it here rather than passing the noise upstream.
  if (kind === "plan" && !(upstream.searchParams.get("fromPlace") && upstream.searchParams.get("toPlace"))) {
    return jsonResponse({ error: "plan needs fromPlace and toPlace." }, 400, allowedOrigin);
  }
  if (kind === "geocode" && !upstream.searchParams.get("text")) {
    return jsonResponse({ error: "geocode needs text." }, 400, allowedOrigin);
  }

  const cache = caches.default;
  const cacheKey = new Request(incoming.toString(), request);
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  let upstreamResponse;
  try {
    upstreamResponse = await fetch(upstream.toString(), {
      headers: { "User-Agent": TRANSIT_USER_AGENT, Accept: "application/json" },
    });
  } catch (err) {
    return jsonResponse({ error: `Transitous request failed: ${err.message}` }, 502, allowedOrigin);
  }

  const response = new Response(await upstreamResponse.text(), {
    status: upstreamResponse.status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": `public, max-age=${CACHE_TTL_SECONDS}`,
      ...corsHeaders(allowedOrigin),
    },
  });
  if (upstreamResponse.ok) {
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
  }
  return response;
}

/**
 * GET /ryanair/{oneWayFares|roundTripFares|airports} - Ryanair passthrough.
 *
 * Like /transit/*, this needs no secret and therefore sits in front of the
 * TRAVELPAYOUTS_TOKEN check: real airline fares must work on a deployment
 * that has no Travelpayouts token at all.
 */
async function handleRyanairRequest(incoming, request, ctx, allowedOrigin) {
  const kind = incoming.pathname.replace(/^\/+|\/+$/g, "").slice("ryanair/".length);
  if (!RYANAIR_UPSTREAM[kind]) {
    return jsonResponse({
      error: "Unknown Ryanair endpoint. Use /ryanair/oneWayFares, /ryanair/roundTripFares or /ryanair/airports.",
    }, 404, allowedOrigin);
  }

  const upstream = new URL(RYANAIR_UPSTREAM[kind]);
  if (kind !== "airports") {
    for (const name of RYANAIR_FORWARDABLE_PARAMS) {
      const value = incoming.searchParams.get(name);
      if (value) upstream.searchParams.set(name, value);
    }
    if (!(upstream.searchParams.get("departureAirportIataCode")
          && upstream.searchParams.get("arrivalAirportIataCode"))) {
      return jsonResponse({
        error: "Fare lookup needs departureAirportIataCode and arrivalAirportIataCode.",
      }, 400, allowedOrigin);
    }
  }

  const cache = caches.default;
  const cacheKey = new Request(incoming.toString(), request);
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  let upstreamResponse;
  try {
    upstreamResponse = await fetch(upstream.toString(), { headers: RYANAIR_HEADERS });
  } catch (err) {
    return jsonResponse({ error: `Ryanair request failed: ${err.message}` }, 502, allowedOrigin);
  }

  const response = new Response(await upstreamResponse.text(), {
    status: upstreamResponse.status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": `public, max-age=${CACHE_TTL_SECONDS}`,
      ...corsHeaders(allowedOrigin),
    },
  });
  if (upstreamResponse.ok) {
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
  }
  return response;
}

/**
 * GET /bahn/{orte|fahrplan|bestpreis} - Deutsche Bahn passthrough.
 *
 * The client always sends GET; the two fare endpoints are POST upstream, so
 * the request body is assembled here from whitelisted params. That keeps the
 * "only GET reaches the proxy" rule intact and stops the caller from posting
 * an arbitrary body to bahn.de through us.
 *
 * A 403 from upstream is passed on as 403 with `blocked: true`, so the page
 * can say "DB blocks automated queries" rather than showing a generic
 * failure - and never invents a price to fill the gap.
 */
async function handleBahnRequest(incoming, request, ctx, allowedOrigin) {
  const kind = incoming.pathname.replace(/^\/+|\/+$/g, "").slice("bahn/".length);
  if (!BAHN_UPSTREAM[kind]) {
    return jsonResponse({
      error: "Unknown Bahn endpoint. Use /bahn/orte, /bahn/fahrplan or /bahn/bestpreis.",
    }, 404, allowedOrigin);
  }

  let upstreamUrl = BAHN_UPSTREAM[kind];
  let init = { headers: BAHN_HEADERS };

  if (kind === "orte") {
    const q = incoming.searchParams.get("q");
    if (!q) return jsonResponse({ error: "orte needs q." }, 400, allowedOrigin);
    upstreamUrl += `?suchbegriff=${encodeURIComponent(q)}&typ=ALL&limit=`
      + encodeURIComponent(incoming.searchParams.get("limit") || "6");
  } else {
    const from = incoming.searchParams.get("from");
    const to = incoming.searchParams.get("to");
    const date = incoming.searchParams.get("date");
    if (!(from && to && date)) {
      return jsonResponse({
        error: `${kind} needs from, to and date (from/to are IDs from /bahn/orte).`,
      }, 400, allowedOrigin);
    }
    // Date must be a full local timestamp; a bare day is accepted and
    // widened rather than rejected, since that is what a date input gives.
    const stamp = /^\d{4}-\d{2}-\d{2}$/.test(date)
      ? `${date}T${kind === "bestpreis" ? "00:00:00" : "08:00:00"}`
      : date;
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(stamp)) {
      return jsonResponse({ error: "date must be YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS." }, 400, allowedOrigin);
    }
    init = {
      method: "POST",
      headers: { ...BAHN_HEADERS, "X-Correlation-ID": bahnCorrelationId() },
      body: JSON.stringify(bahnSearchBody(from, to, stamp, incoming.searchParams.get("class"))),
    };
  }

  const cache = caches.default;
  const cacheKey = new Request(incoming.toString(), new Request(incoming.toString()));
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  let upstreamResponse;
  try {
    upstreamResponse = await fetch(upstreamUrl, init);
  } catch (err) {
    return jsonResponse({ error: `Bahn request failed: ${err.message}` }, 502, allowedOrigin);
  }

  const text = await upstreamResponse.text();
  if (upstreamResponse.status === 403) {
    return jsonResponse({
      blocked: true,
      error: "Deutsche Bahn blocked this query (bot protection). No price available from this source.",
    }, 403, allowedOrigin);
  }

  const response = new Response(text, {
    status: upstreamResponse.status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": `public, max-age=${CACHE_TTL_SECONDS}`,
      ...corsHeaders(allowedOrigin),
    },
  });
  if (upstreamResponse.ok) {
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
  }
  return response;
}

/**
 * GET /flixbus/{cities|search} - FlixBus passthrough. No secret needed, so
 * like /transit/* and /ryanair/* it runs in front of the token check.
 */
async function handleFlixbusRequest(incoming, request, ctx, allowedOrigin) {
  const kind = incoming.pathname.replace(/^\/+|\/+$/g, "").slice("flixbus/".length);
  if (!FLIXBUS_UPSTREAM[kind]) {
    return jsonResponse({ error: "Unknown FlixBus endpoint. Use /flixbus/cities or /flixbus/search." }, 404, allowedOrigin);
  }

  const upstream = new URL(FLIXBUS_UPSTREAM[kind]);
  for (const name of FLIXBUS_FORWARDABLE_PARAMS[kind]) {
    const value = incoming.searchParams.get(name);
    if (value) upstream.searchParams.set(name, value);
  }
  if (kind === "cities" && !upstream.searchParams.get("q")) {
    return jsonResponse({ error: "cities needs q." }, 400, allowedOrigin);
  }
  if (kind === "search" && !(upstream.searchParams.get("from_city_id")
                              && upstream.searchParams.get("to_city_id")
                              && upstream.searchParams.get("departure_date"))) {
    return jsonResponse({
      error: "search needs from_city_id, to_city_id and departure_date.",
    }, 400, allowedOrigin);
  }

  const cache = caches.default;
  const cacheKey = new Request(incoming.toString(), request);
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  let upstreamResponse;
  try {
    upstreamResponse = await fetch(upstream.toString(), { headers: FLIXBUS_HEADERS });
  } catch (err) {
    return jsonResponse({ error: `FlixBus request failed: ${err.message}` }, 502, allowedOrigin);
  }

  const response = new Response(await upstreamResponse.text(), {
    status: upstreamResponse.status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": `public, max-age=${CACHE_TTL_SECONDS}`,
      ...corsHeaders(allowedOrigin),
    },
  });
  if (upstreamResponse.ok) ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

/** GET /skiplagged?from=&to=&depart= - passthrough, no secret needed. */
async function handleSkiplaggedRequest(incoming, request, ctx, allowedOrigin) {
  const upstream = new URL(SKIPLAGGED_UPSTREAM);
  for (const name of SKIPLAGGED_FORWARDABLE_PARAMS) {
    const value = incoming.searchParams.get(name);
    if (value !== null) upstream.searchParams.set(name, value);
  }
  upstream.searchParams.set("poll", "true");
  if (!(upstream.searchParams.get("from") && upstream.searchParams.get("to")
        && upstream.searchParams.get("depart"))) {
    return jsonResponse({ error: "skiplagged needs from, to and depart." }, 400, allowedOrigin);
  }

  const cache = caches.default;
  const cacheKey = new Request(incoming.toString(), request);
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  let upstreamResponse;
  try {
    upstreamResponse = await fetch(upstream.toString(), { headers: RYANAIR_HEADERS });
  } catch (err) {
    return jsonResponse({ error: `Skiplagged request failed: ${err.message}` }, 502, allowedOrigin);
  }
  const response = new Response(await upstreamResponse.text(), {
    status: upstreamResponse.status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": `public, max-age=${CACHE_TTL_SECONDS}`,
      ...corsHeaders(allowedOrigin),
    },
  });
  if (upstreamResponse.ok) ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

// Feeds wrap their HTML twice: once as markup, once escaped as entities.
// Decoding has to come first, otherwise "&lt;p&gt;" survives tag-stripping
// and lands in the page as visible gibberish.
const HTML_ENTITIES = {
  amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ",
  // The feeds are German, French and Polish - accented names are the rule,
  // not the exception, and "g&uuml;nstig" must not reach the page as-is.
  auml: "ä", ouml: "ö", uuml: "ü", Auml: "Ä", Ouml: "Ö", Uuml: "Ü", szlig: "ß",
  eacute: "é", egrave: "è", ecirc: "ê", agrave: "à", acirc: "â", ccedil: "ç",
  iacute: "í", oacute: "ó", uacute: "ú", ntilde: "ñ", aacute: "á",
  euro: "€", pound: "£", hellip: "…", ndash: "–", mdash: "—", rsquo: "’", lsquo: "‘",
};
function decodeEntities(value) {
  return value
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCharCode(parseInt(code, 16)))
    // Case matters here: &Uuml; and &uuml; are different characters.
    .replace(/&([a-zA-Z]+);/g, (match, name) => HTML_ENTITIES[name] ?? HTML_ENTITIES[name.toLowerCase()] ?? match);
}

/** Minimal RSS <item> reader - enough for title/link/pubDate/description. */
function parseRssItems(xml, source, limit) {
  const pick = (block, tag) => {
    const m = block.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`, "i"));
    if (!m) return "";
    const withoutCdata = m[1].replace(/<!\[CDATA\[|\]\]>/g, "");
    // Decode, then strip: markup can hide inside the decoded text too.
    return decodeEntities(withoutCdata).replace(/<[^>]+>/g, "").trim();
  };
  const items = [];
  const blocks = xml.match(/<item[\s\S]*?<\/item>/gi) || [];
  for (const block of blocks) {
    const title = pick(block, "title");
    const url = pick(block, "link");
    if (!title || !url) continue;
    items.push({
      source, title: title.slice(0, 200), url,
      published: pick(block, "pubDate"),
      summary: pick(block, "description").slice(0, 240),
    });
    if (items.length >= limit) break;
  }
  return items;
}

/** GET /deals - the three RSS feeds, merged and handed over as JSON. */
async function handleDealsRequest(incoming, request, ctx, allowedOrigin) {
  const cache = caches.default;
  const cacheKey = new Request(incoming.toString(), request);
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  const posts = [];
  // One dead feed must not take the others down - deals are a bonus, never
  // a reason for the whole search to fail.
  await Promise.all(DEAL_FEEDS.map(async ([source, url]) => {
    try {
      const resp = await fetch(url, { headers: { "User-Agent": TRANSIT_USER_AGENT } });
      if (!resp.ok) return;
      posts.push(...parseRssItems(await resp.text(), source, DEAL_MAX_ITEMS_PER_FEED));
    } catch (err) { /* skip this feed */ }
  }));

  const response = new Response(JSON.stringify({ posts }), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": `public, max-age=${CACHE_TTL_SECONDS}`,
      ...corsHeaders(allowedOrigin),
    },
  });
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

export default {
  async fetch(request, env, ctx) {
    const allowedOrigin = env.ALLOWED_ORIGIN || "*";

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders(allowedOrigin) });
    }
    if (new URL(request.url).pathname.replace(/^\/+|\/+$/g, "") === "ai") {
      return handleAiRequest(request, env, allowedOrigin);
    }
    if (request.method !== "GET") {
      return jsonResponse({ error: "Only GET is supported." }, 405, allowedOrigin);
    }
    const requestUrl = new URL(request.url);
    const path = requestUrl.pathname.replace(/^\/+/, "");
    if (path.startsWith("transit/")) {
      return handleTransitRequest(requestUrl, request, ctx, allowedOrigin);
    }
    if (path.startsWith("ryanair/")) {
      return handleRyanairRequest(requestUrl, request, ctx, allowedOrigin);
    }
    if (path.startsWith("flixbus/")) {
      return handleFlixbusRequest(requestUrl, request, ctx, allowedOrigin);
    }
    if (path.startsWith("bahn/")) {
      return handleBahnRequest(requestUrl, request, ctx, allowedOrigin);
    }
    if (path === "skiplagged") {
      return handleSkiplaggedRequest(requestUrl, request, ctx, allowedOrigin);
    }
    if (path === "deals") {
      return handleDealsRequest(requestUrl, request, ctx, allowedOrigin);
    }
    if (!env.TRAVELPAYOUTS_TOKEN) {
      return jsonResponse({ error: "Proxy is not configured (missing TRAVELPAYOUTS_TOKEN secret)." }, 500, allowedOrigin);
    }

    const incoming = new URL(request.url);
    // /cheap is the historical path and still maps to the (now richer)
    // default endpoint, so older cached clients keep working.
    const endpointKey = incoming.pathname.replace(/^\/+|\/+$/g, "") === "latest"
      ? "latest" : "prices_for_dates";
    const origin = incoming.searchParams.get("origin") || "";
    const destination = incoming.searchParams.get("destination") || "";
    const currency = (incoming.searchParams.get("currency") || "eur").toLowerCase();

    if (!isValidIataLike(origin) || !isValidIataLike(destination)) {
      return jsonResponse({
        error: "origin/destination must be 2-4 letter airport/city codes.",
      }, 400, allowedOrigin);
    }
    for (const name of ["departure_at", "return_at", "beginning_of_period"]) {
      const value = incoming.searchParams.get(name);
      if (value && !isValidDateOrMonth(value)) {
        return jsonResponse({ error: `${name} must be YYYY-MM or YYYY-MM-DD.` }, 400, allowedOrigin);
      }
    }

    const cache = caches.default;
    const cacheKey = new Request(incoming.toString(), request);
    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    const upstream = new URL(UPSTREAM[endpointKey]);
    upstream.searchParams.set("origin", origin.toUpperCase());
    upstream.searchParams.set("destination", destination.toUpperCase());
    upstream.searchParams.set("currency", currency);
    for (const name of FORWARDABLE_PARAMS) {
      const value = incoming.searchParams.get(name);
      if (value) upstream.searchParams.set(name, value);
    }

    let upstreamResponse;
    try {
      upstreamResponse = await fetch(upstream.toString(), {
        headers: { "X-Access-Token": env.TRAVELPAYOUTS_TOKEN },
      });
    } catch (err) {
      return jsonResponse({ error: `Upstream request failed: ${err.message}` }, 502, allowedOrigin);
    }

    const upstreamBody = await upstreamResponse.text();
    const response = new Response(upstreamBody, {
      status: upstreamResponse.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": `public, max-age=${CACHE_TTL_SECONDS}`,
        ...corsHeaders(allowedOrigin),
      },
    });

    if (upstreamResponse.ok) {
      ctx.waitUntil(cache.put(cacheKey, response.clone()));
    }
    return response;
  },
};
