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

function pickAiProvider(env) {
  const provider = AI_PROVIDERS.find((p) => env[p.keyVar]);
  if (!provider) return null;
  const model = env.AI_MODEL || provider.defaultModel;
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
  const provider = pickAiProvider(env);
  if (!provider) {
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

  const spec = provider.prepare(prompt);
  let upstreamResponse;
  try {
    upstreamResponse = await fetch(spec.url, {
      method: "POST",
      headers: spec.headers,
      body: JSON.stringify(spec.body),
    });
  } catch (err) {
    return jsonResponse({ error: `${provider.name} request failed: ${err.message}` }, 502, allowedOrigin);
  }

  const payload = await upstreamResponse.json().catch(() => null);
  if (!upstreamResponse.ok) {
    const detail = provider.readError(payload) || `status ${upstreamResponse.status}`;
    return jsonResponse({ error: `${provider.name} error: ${detail}` }, 502, allowedOrigin);
  }
  const text = (provider.readText(payload) || "").trim();
  if (!text) {
    return jsonResponse({ error: `${provider.name} returned no usable text.` }, 502, allowedOrigin);
  }
  return jsonResponse({ configured: true, provider: provider.name, model: provider.model, text }, 200, allowedOrigin);
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
