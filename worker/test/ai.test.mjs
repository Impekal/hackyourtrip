// Exercises the Worker's /ai handler against a stubbed fetch, once per
// provider, to confirm request shape + response parsing.
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('../src/index.js', import.meta.url), 'utf8');
const mod = await import('data:text/javascript;base64,' + Buffer.from(src).toString('base64'));
const worker = mod.default;

const realFetch = globalThis.fetch;
function stubFetch(responder) {
  globalThis.fetch = async (url, init) => {
    const captured = { url, init };
    const { status, body } = responder(captured);
    globalThis.__last = captured;
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  };
}

function aiRequest(prompt = 'Test-Prompt') {
  return new Request('https://proxy.test/ai', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });
}
const ctx = { waitUntil() {} };

// Counted so a failure actually fails the run - printing FAIL while exiting 0
// would make `npm test` green no matter what broke.
let failures = 0;
function report(ok, label) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) failures += 1;
}

async function check(label, env, responder, expect) {
  stubFetch(responder);
  const resp = await worker.fetch(aiRequest(), env, ctx);
  const body = await resp.json();
  const last = globalThis.__last;
  const ok = expect(resp.status, body, last);
  report(ok, label);
  if (!ok) console.log('   status', resp.status, '\n   body', JSON.stringify(body), '\n   url', last?.url);
}

// 1. No key at all -> 501, no upstream call
await check('no provider configured -> 501', { TRAVELPAYOUTS_TOKEN: 'x' },
  () => ({ status: 200, body: {} }),
  (status, body) => status === 501 && body.configured === false && /GEMINI_API_KEY/.test(body.error));

// 2. Gemini
await check('gemini: key in URL, text from candidates',
  { GEMINI_API_KEY: 'g-key' },
  () => ({ status: 200, body: { candidates: [{ content: { parts: [{ text: 'Empfehlung A' }] } }] } }),
  (status, body, last) => status === 200 && body.text === 'Empfehlung A'
    && body.provider === 'gemini' && last.url.includes('gemini-2.0-flash')
    && last.url.includes('key=g-key'));

// 3. Groq (OpenAI-shaped)
await check('groq: bearer auth, text from choices',
  { GROQ_API_KEY: 'q-key' },
  () => ({ status: 200, body: { choices: [{ message: { content: 'Empfehlung B' } }] } }),
  (status, body, last) => status === 200 && body.text === 'Empfehlung B'
    && body.provider === 'groq' && last.url.includes('api.groq.com')
    && last.init.headers.Authorization === 'Bearer q-key'
    && JSON.parse(last.init.body).model === 'llama-3.3-70b-versatile');

// 4. Mistral
await check('mistral: bearer auth, correct host',
  { MISTRAL_API_KEY: 'm-key' },
  () => ({ status: 200, body: { choices: [{ message: { content: 'Empfehlung C' } }] } }),
  (status, body, last) => status === 200 && body.provider === 'mistral'
    && last.url.includes('api.mistral.ai')
    && last.init.headers.Authorization === 'Bearer m-key');

// 5. Priority when several are set
await check('priority: gemini wins over groq+mistral',
  { GEMINI_API_KEY: 'g', GROQ_API_KEY: 'q', MISTRAL_API_KEY: 'm' },
  () => ({ status: 200, body: { candidates: [{ content: { parts: [{ text: 'x' }] } }] } }),
  (status, body) => body.provider === 'gemini');

// 6. AI_MODEL override
await check('AI_MODEL overrides the default model',
  { GROQ_API_KEY: 'q', AI_MODEL: 'llama-3.1-8b-instant' },
  () => ({ status: 200, body: { choices: [{ message: { content: 'x' } }] } }),
  (status, body, last) => JSON.parse(last.init.body).model === 'llama-3.1-8b-instant'
    && body.model === 'llama-3.1-8b-instant');

// 7. Upstream error is surfaced, not swallowed
await check('upstream error -> 502 with provider message',
  { GROQ_API_KEY: 'q' },
  () => ({ status: 400, body: { error: { message: 'model_decommissioned' } } }),
  (status, body) => status === 502 && body.error.includes('model_decommissioned'));

// 8. Empty completion is treated as failure
await check('empty text -> 502 rather than blank recommendation',
  { GROQ_API_KEY: 'q' },
  () => ({ status: 200, body: { choices: [{ message: { content: '   ' } }] } }),
  (status, body) => status === 502 && /no usable text/.test(body.error));

// 9. Missing prompt
stubFetch(() => ({ status: 200, body: {} }));
{
  const resp = await worker.fetch(new Request('https://proxy.test/ai', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
  }), { GROQ_API_KEY: 'q' }, ctx);
  report(resp.status === 400, 'missing prompt -> 400');
}

// 10. GET on /ai is rejected
{
  const resp = await worker.fetch(new Request('https://proxy.test/ai'), { GROQ_API_KEY: 'q' }, ctx);
  report(resp.status === 405, 'GET /ai -> 405');
}

globalThis.fetch = realFetch;
if (failures) process.exitCode = 1;
