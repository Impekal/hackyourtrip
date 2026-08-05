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
