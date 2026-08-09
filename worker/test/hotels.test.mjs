// Hotelpreise ueber LiteAPI - der einzige lebende Weg zu echten Hotelraten.
//
// Die Fixture ist KEIN Wunschbild: sie ist die Antwort aus Probe 17
// (Melia Berlin, 08.09.2026, 1 Nacht, 2 Erwachsene), Feldnamen und Betraege
// 1:1 uebernommen. Genau daran haengt der Sinn dieser Tests - beim
// Bahn-Server hatte eine erfundene Fixture (`zeit` statt `sollzeit`) den
// Parser bestaetigt, der in echt nichts gefunden hat.
//
// Der teuerste denkbare Fehler steht hier im Mittelpunkt: LiteAPI liefert
// DREI Betraege pro Zimmer, und die City Tax ist ausdruecklich NICHT im
// Preis enthalten. Wer 260,45 als Uebernachtungspreis anzeigt, luegt um
// 19,56 EUR.
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('../src/index.js', import.meta.url), 'utf8');
const mod = await import('data:text/javascript;base64,' + Buffer.from(src).toString('base64'));
const worker = mod.default;

const realFetch = globalThis.fetch;
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

const ENV = { LITEAPI_KEY: 'sand_test' };
async function call(path, env = ENV) {
  const resp = await worker.fetch(new Request(`https://proxy.test${path}`), env, ctx);
  return { resp, body: await resp.json().catch(() => null), last: globalThis.__last };
}

// Aus Probe 17, ungekuerzt in den Feldern, die wir lesen.
const RATE_SHAPE = {
  data: [{
    hotelId: 'lp394f5',
    roomTypes: [
      {
        offerId: 'x'.repeat(900),
        offerRetailRate: { amount: 260.45, currency: 'EUR' },
        suggestedSellingPrice: { amount: 333.13, currency: 'EUR', source: 'booking.com' },
        offerInitialPrice: { amount: 260.45, currency: 'EUR' },
        priceType: 'commission',
        rates: [{
          name: 'Deluxe Room City View',
          boardType: 'RO',
          boardName: 'Room Only',
          maxOccupancy: 2,
          retailRate: {
            total: [{ amount: 260.45, currency: 'EUR' }],
            suggestedSellingPrice: [{ amount: 333.13, currency: 'EUR', source: 'booking.com' }],
            initialPrice: [{ amount: 260.45, currency: 'EUR' }],
            taxesAndFees: [
              { included: false, description: 'City Tax', amount: 19.56, currency: 'EUR' },
              { included: true, description: 'VAT', amount: 17.04, currency: 'EUR' },
            ],
          },
          cancellationPolicies: { refundableTag: 'NRFN' },
        }],
      },
      {
        // Billiger auf dem Papier (250), aber mit 40 EUR nicht enthaltener
        // Steuer teurer in Wahrheit (290) als das Zimmer oben (280,01).
        offerRetailRate: { amount: 250.00, currency: 'EUR' },
        suggestedSellingPrice: { amount: 260.00, currency: 'EUR', source: 'booking.com' },
        rates: [{
          name: 'Falle',
          boardName: 'Room Only',
          retailRate: {
            total: [{ amount: 250.00, currency: 'EUR' }],
            taxesAndFees: [{ included: false, description: 'Resort Fee', amount: 40.00, currency: 'EUR' }],
          },
          cancellationPolicies: { refundableTag: 'RFN' },
        }],
      },
    ],
  }],
};

// --- Der Kern: welcher Betrag wird zum Preis? ------------------------------
stubFetch(RATE_SHAPE);
{
  const { resp, body } = await call('/hotels/rates?ids=lp394f5&checkin=2026-09-08&checkout=2026-09-09');
  const o = (body.offers || [])[0] || {};
  report(resp.status === 200 && body.offers.length === 1,
    'ein Hotel -> genau ein (das guenstigste) Angebot', JSON.stringify(body));
  report(o.total === 280.01,
    'der Gesamtpreis enthaelt die NICHT enthaltene City Tax (260,45 + 19,56)',
    `total=${o.total}`);
  report(o.price === 260.45 && o.extraTax === 19.56,
    'Grundpreis und Zusatzsteuer bleiben einzeln sichtbar, nicht vermischt',
    JSON.stringify(o));
  report(o.compareAt === 333.13 && o.compareSource === 'booking.com',
    'der Vergleichspreis von booking.com kommt mit - das ist die Ersparnis',
    JSON.stringify(o));
  report(o.roomName === 'Deluxe Room City View' && o.boardName === 'Room Only',
    'Zimmername und Verpflegung kommen mit');
  report(o.refundable === false,
    'NRFN wird als "nicht erstattbar" gelesen', String(o.refundable));
}

// Die Falle: das billigere Angebot ist mit versteckter Gebuehr das teurere.
// Wer nach dem angezeigten Betrag sortiert, empfiehlt hier das Falsche.
{
  const { body } = await call('/hotels/rates?ids=lp394f5&checkin=2026-09-08&checkout=2026-09-09');
  const o = body.offers[0];
  report(o.roomName !== 'Falle',
    'das guenstigste Angebot wird nach Gesamtpreis gewaehlt, nicht nach Schaufensterpreis',
    JSON.stringify(o));
}

// Kein Vergleichspreis, wenn er nicht hoeher ist - sonst steht da eine
// "Ersparnis" von 0 oder eine negative.
{
  stubFetch({ data: [{ hotelId: 'h', roomTypes: [{
    offerRetailRate: { amount: 100, currency: 'EUR' },
    suggestedSellingPrice: { amount: 90, currency: 'EUR', source: 'booking.com' },
    rates: [{ name: 'R', retailRate: { taxesAndFees: [] } }],
  }] }] });
  const { body } = await call('/hotels/rates?ids=h&checkin=2026-09-08&checkout=2026-09-09');
  report(body.offers[0].compareAt === null,
    'ein Vergleichspreis unter unserem Preis wird verworfen, nicht als Ersparnis verkauft',
    JSON.stringify(body.offers[0]));
}

// Ohne lesbaren Betrag lieber gar kein Angebot als eine 0.
{
  stubFetch({ data: [{ hotelId: 'h', roomTypes: [{ rates: [{ name: 'R' }] }] }] });
  const { body } = await call('/hotels/rates?ids=h&checkin=2026-09-08&checkout=2026-09-09');
  report((body.offers || []).length === 0,
    'ein Zimmer ohne lesbaren Preis faellt raus - kein Angebot mit 0 EUR',
    JSON.stringify(body));
}

// --- Anfrage an LiteAPI ---------------------------------------------------
stubFetch(RATE_SHAPE);
{
  const { last } = await call('/hotels/rates?ids=a,b&checkin=2026-09-08&checkout=2026-09-11&adults=3&currency=eur');
  const sent = JSON.parse(last.init.body);
  report(last.url === 'https://api.liteapi.travel/v3.0/hotels/rates' && last.init.method === 'POST',
    'die Ratenabfrage geht als POST an den richtigen Endpunkt', last.url);
  report(JSON.stringify(sent.hotelIds) === '["a","b"]' && sent.occupancies[0].adults === 3
    && sent.currency === 'EUR' && sent.checkin === '2026-09-08' && sent.checkout === '2026-09-11',
    'IDs, Belegung, Waehrung und Daten landen im Body', JSON.stringify(sent));
  report(!('children' in sent.occupancies[0]),
    'ohne Kinderalter wird kein children-Feld erfunden', JSON.stringify(sent.occupancies));
}

// Kinder werden ueber ihr Alter bepreist, nicht ueber ihre Anzahl: je nach
// Haus zahlt ein Dreijaehriger nichts und ein Elfjaehriger voll. Ein
// geratenes Alter waere ein geratener Preis.
{
  const { last } = await call('/hotels/rates?ids=a&checkin=2026-09-08&checkout=2026-09-09'
    + '&adults=2&childAges=8,10');
  const occ = JSON.parse(last.init.body).occupancies[0];
  report(occ.adults === 2 && JSON.stringify(occ.children) === '[8,10]',
    'Kinderalter gehen als Alter mit, nicht als blosse Anzahl', JSON.stringify(occ));
}
{
  const { last } = await call('/hotels/rates?ids=a&checkin=2026-09-08&checkout=2026-09-09'
    + '&adults=2&childAges=acht,10,99');
  const occ = JSON.parse(last.init.body).occupancies[0];
  report(JSON.stringify(occ.children) === '[10]',
    'unlesbare und unmoegliche Altersangaben fliegen raus', JSON.stringify(occ));
  report(last.init.headers['X-API-Key'] === 'sand_test',
    'der Schluessel geht als X-API-Key raus - und nur von hier, nie aus dem Browser');
}

// --- Hotelliste -----------------------------------------------------------
// Feldnamen aus Probe 18, 1:1 - inklusive der Felder, die wir bewusst
// wegwerfen.
stubFetch({ data: [{ id: 'lp6aeac', name: 'Steigenberger Hotel Am Kanzleramt',
                     city: 'Berlin', country: 'de', zip: '10557',
                     address: 'Ella-Trebe-Straße 5', stars: 5, rating: 9,
                     reviewCount: 10360, chain: 'Steigenberger Hotels & Resorts',
                     latitude: 52.523885, longitude: 13.368183,
                     thumbnail: 'https://static.cupid.travel/hotels/thumbnail/1.jpg',
                     facilityIds: [47, 107, 2],
                     hotelDescription: 'x'.repeat(5000) }] });
{
  const { resp, body, last } = await call('/hotels/list?city=Berlin&country=de&limit=5');
  const h = body.hotels[0];
  report(resp.status === 200 && h.id === 'lp6aeac' && h.stars === 5,
    'die Hotelliste kommt eingedampft zurueck', JSON.stringify(body));
  report(h.rating === 9 && h.reviewCount === 10360,
    'Bewertung und Anzahl der Bewertungen kommen mit - danach wird gefiltert',
    JSON.stringify(h));
  report(!('hotelDescription' in h),
    'der kilobyteschwere Beschreibungstext wird nicht durchgereicht - das Handy dankt');
  report(!('facilityIds' in h),
    'die nackten Ausstattungs-IDs fliegen raus: [47,107,2] beantwortet kein '
    + '"hat WLAN?" und wuerde nur zum Raten verleiten');
  report(new URL(last.url).searchParams.get('countryCode') === 'DE',
    'das Laenderkuerzel wird gross geschrieben weitergegeben');
}

// --- Validierung ----------------------------------------------------------
{
  const { resp } = await call('/hotels/list?city=Berlin');
  report(resp.status === 400, 'Liste ohne Land -> 400');
  const { resp: r2 } = await call('/hotels/rates?checkin=2026-09-08&checkout=2026-09-09');
  report(r2.status === 400, 'Raten ohne IDs -> 400');
  const { resp: r3 } = await call('/hotels/rates?ids=a&checkin=08.09.2026&checkout=2026-09-09');
  report(r3.status === 400, 'ein krummes Datum wird abgefangen, bevor es rausgeht');
  const { resp: r4 } = await call('/hotels/nope');
  report(r4.status === 404, 'unbekannter /hotels/*-Pfad -> 404');
}

// Ohne Schluessel muss der Worker das sagen - nicht so tun, als gaebe es
// keine Hotels. Das ist der Unterschied zwischen "nicht eingerichtet" und
// "nichts gefunden".
{
  const { resp, body } = await call('/hotels/list?city=Berlin&country=DE', {});
  report(resp.status === 501 && body.unconfigured === true,
    'ohne LITEAPI_KEY: 501 mit Begruendung, kein stilles Nichts', JSON.stringify(body));
}

// Ein 401 von LiteAPI heisst: unser Schluessel taugt nicht. Das darf nicht
// als 401 an den Browser durchschlagen, sonst sieht es aus, als muesse sich
// der Nutzer anmelden.
{
  stubFetch({ error: { code: 401, message: 'unauthorized' } }, 401);
  const { resp, body } = await call('/hotels/list?city=Berlin&country=DE');
  report(resp.status === 502 && /401/.test(body.error),
    'ein abgelehnter Schluessel wird als 502 mit Grund gemeldet', JSON.stringify(body));
}

globalThis.fetch = realFetch;
if (failures) process.exitCode = 1;
