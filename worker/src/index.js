/**
 * HackYourTrip proxy: hides TRAVELPAYOUTS_TOKEN from the public "Suche" tab.
 *
 * The interactive search runs entirely in the visitor's browser (docs/app.js)
 * so it can't hold a real API token itself - anyone could open dev tools and
 * steal it. This Worker is the one place the token actually lives (as a
 * Cloudflare secret, never in source), proxying single requests to
 * Travelpayouts' `v1/prices/cheap` endpoint.
 *
 * Deliberately thin: no business logic here beyond auth-hiding, input
 * validation, CORS, and edge caching - date-candidate fan-out, duration
 * estimation, and ranking all stay in docs/app.js, mirroring the same split
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

const TRAVELPAYOUTS_URL = "https://api.travelpayouts.com/v1/prices/cheap";
const CACHE_TTL_SECONDS = 3600;

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, OPTIONS",
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

function isValidDate(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

export default {
  async fetch(request, env, ctx) {
    const allowedOrigin = env.ALLOWED_ORIGIN || "*";

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders(allowedOrigin) });
    }
    if (request.method !== "GET") {
      return jsonResponse({ error: "Only GET is supported." }, 405, allowedOrigin);
    }
    if (!env.TRAVELPAYOUTS_TOKEN) {
      return jsonResponse({ error: "Proxy is not configured (missing TRAVELPAYOUTS_TOKEN secret)." }, 500, allowedOrigin);
    }

    const incoming = new URL(request.url);
    const origin = incoming.searchParams.get("origin") || "";
    const destination = incoming.searchParams.get("destination") || "";
    const departDate = incoming.searchParams.get("depart_date") || "";
    const currency = (incoming.searchParams.get("currency") || "eur").toLowerCase();

    if (!isValidIataLike(origin) || !isValidIataLike(destination) || !isValidDate(departDate)) {
      return jsonResponse({
        error: "origin/destination must be 2-4 letter airport codes, depart_date must be YYYY-MM-DD.",
      }, 400, allowedOrigin);
    }

    const cache = caches.default;
    const cacheKey = new Request(incoming.toString(), request);
    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    const upstream = new URL(TRAVELPAYOUTS_URL);
    upstream.searchParams.set("origin", origin.toUpperCase());
    upstream.searchParams.set("destination", destination.toUpperCase());
    upstream.searchParams.set("depart_date", departDate);
    upstream.searchParams.set("currency", currency);

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
