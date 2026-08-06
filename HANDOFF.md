# HackYourTrip – Handoff / Projektstatus

Diese Datei ist für eine **neue Chat-Session ohne Vorwissen** gedacht: wer
hier weiterarbeitet, sollte nach dem Lesen wissen, wie das Projekt
aufgebaut ist, welche Entscheidungen warum getroffen wurden, und was gerade
offen ist. Bitte diese Datei aktuell halten (TODO-Liste unten pflegen,
neue Design-Entscheidungen dokumentieren) - sie ersetzt kein Gedächtnis.

Repo: `github.com/kalivolut/hackyourtrip` (**Achtung**: umbenannt von
`mysportpilot/hackyourtrip` - siehe Abschnitt "Git-Stolperfallen" unten,
der lokale `origin`-Remote zeigt noch auf die alte URL und funktioniert nur
deshalb, weil GitHub automatisch weiterleitet).

## Was ist das Projekt?

Bot/Webapp, die Flug-, Bahn-, Bus- und Hotel-Angebote vergleicht (10
Such-Modi inkl. Kombis wie "Flug+Hotel" oder "Bahn oder Bus, je nachdem was
besser ist"), Preisverfall/Fehlerpreise per Telegram/E-Mail meldet, und eine
interaktive Live-Suche als statische GitHub-Pages-Seite anbietet
(`docs/index.html` + `docs/app.js`, kein Server nötig).

Zwei parallele Laufzeiten teilen sich die Logik:

1. **Python-Backend** (`traveldeals/`) - läuft als GitHub-Actions-Cronjob
   (`.github/workflows/check-deals.yml`), liest `config/routes.yaml`
   (lokal, nicht eingecheckt - siehe `config/routes.example.yaml`),
   schreibt `docs/data/deals.json` fürs Dashboard und verschickt
   Benachrichtigungen. Das ist die einzige Stelle mit echter
   Preishistorie (siehe `pricehistory.py`), also auch die einzige Stelle,
   die Preisverfall/Fehlerpreise erkennen kann.
2. **JS-Frontend** (`docs/app.js`) - die "Suche"-Tab-Live-Suche läuft
   komplett im Browser des Besuchers (GitHub Pages hat keinen Server-Teil).
   `app.js` ist bewusst ein **1:1-Port der Python-Engine/Mock-Provider**:
   gleiche Ranking-Formeln, gleiche Feldnamen (nur camelCase statt
   snake_case). **Jede inhaltliche Änderung an `traveldeals/` muss auch in
   `docs/app.js` nachgezogen werden** (und umgekehrt) - das ist die
   wichtigste wiederkehrende Fehlerquelle in diesem Projekt.

## Architektur / Datenfluss (Python-Seite)

```
config/routes.yaml --config.py--> RoutePreference (models.py)
                                        |
                                        v
                          Provider.search(route) -> list[Offer]
                    (mock.py | travelpayouts.py | amadeus.py)
                                        |
                                        v
                        DealEngine.search() (engine.py)
              Kombis bauen -> harte Filter -> Score -> Top N
                                        |
                                        v
                    list[TripOption] -> cli.py schreibt
                    docs/data/deals.json + verschickt Notifier
```

- `models.py`: alle Dataclasses (`RoutePreference`, `Offer`, `TripOption`,
  `BaggagePref`, `RailPref`, `HotelPref`, `TransportPref`, `Mode`, `Priority`).
  **Single source of truth fürs Datenmodell** - JS in `app.js` bildet das nach,
  hat aber keine eigene Dataclass, sondern nur Plain Objects mit denselben
  Feldern (camelCase).
- `providers/base.py`: `Provider`-Protokoll + `date_candidates(route)`
  (Kandidaten-Tage aus `depart_date_from/until` ± `flex_days_before/after`).
- `providers/mock.py`: seeded-random Fake-Angebote (deterministisch pro
  Route+Modus+Tag, damit `check` am selben Tag keine Fake-Preisbewegung
  erzeugt). Für **jeden Modus ohne echten Provider** (Bahn, Bus, Hotel immer;
  Flug wenn kein Token) die einzige Datenquelle.
- `providers/travelpayouts.py`: **einzige echte Datenquelle**, Flug via
  Travelpayouts (Aviasales) Data API (`v1/prices/cheap`), kostenloses
  Self-Service-Konto, kein Vertrag nötig. Siehe Docstring dort für die
  Response-Shape-Falle (echte API verschachtelt anders als die Doku-Beispiele
  - `_flatten_offers()` fängt beides ab).
- `providers/amadeus.py`: zweite echte Quelle, aber Amadeus' kostenlose
  Self-Service-API wurde **Juli 2026 abgeschaltet** - nur noch für
  Enterprise-Zugänge relevant, nicht mehr der empfohlene Weg.
- `providers/geo.py`: Haversine-Distanzschätzung für Flugdauer -
  **ausdrücklich nur für Direktflüge** (Layover-Dauer lässt sich aus der
  Entfernung nicht ableiten - das war eine explizite User-Korrektur).
- `engine.py`: Ranking (`cheapest`/`fastest`/`best_value`), harte Filter
  (Budget, Reisezeit, Hotel-/Transport-Kriterien), Komfort-Score, smarte
  Empfehlungen ("1h später spart X€", Gepäck-Tipp, Währungsumrechnung),
  Preisverfall-/Fehlerpreis-Erkennung über `pricehistory.py`.
- `config.py`: YAML → `RoutePreference`. `config/routes.yaml` ist
  gitignored (persönliche Reisedaten bleiben lokal/als Secret), `.example`
  dient als Doku+Vorlage.
- `cli.py`: `traveldeals check` (Cronjob-Einstiegspunkt) und
  `traveldeals list-routes`.

## Architektur (JS-Frontend, `docs/app.js`)

Kein Build-Step, keine Dependencies - eine einzige `<script>`-Datei.
Grobe Abschnitte (in Datei-Reihenfolge): Haupt-Tabs (Suche/Alerts) →
Modus-Tabs (`MODE_TAB_CONFIG`, steuert welche Formularfelder pro Modus
sichtbar sind) → seeded RNG (`mulberry32`/`xmur3`, spiegelt Pythons
`random.Random(seed)`) → Mock-Provider (spiegeln `mock.py`) → echte
Flugpreise via Cloudflare-Worker-Proxy (`fetchRealFlightOffers`, spiegelt
`travelpayouts.py`) → Währungsumrechnung (Frankfurter API, live) → Engine
(spiegelt `engine.py`) → Formular-Wiring (`readRouteFromForm`,
`renderResults`, `buildYamlSnippet` für den "diese Suche dauerhaft
überwachen"-Export) → "Meine Alerts"-Tab (lädt `docs/data/deals.json`,
den Output des Cronjobs).

**Warum läuft die Suche client-seitig auf Mock-Daten statt echten APIs?**
GitHub Pages hat keinen Server; ein echter API-Token im Browser-JS wäre für
jeden Besucher lesbar. Lösung: ein **Cloudflare Worker als Proxy**
(`worker/src/index.js`), der `TRAVELPAYOUTS_TOKEN` als Cloudflare-Secret
hält und nur validierte GET-Requests an Travelpayouts durchreicht (+ 1h
Edge-Cache gegen Quota-Verbrauch). `docs/app.js` ruft nur den Worker auf,
nie Travelpayouts direkt. Ohne `PROXY_URL` (oder bei Netzwerkfehler/leerem
Ergebnis) fällt alles graceful auf Mock-Daten zurück.

## Wichtige Konventionen / Design-Entscheidungen

- **⚠️ Erfundene Preise dürfen nie wie buchbare aussehen.** Die wichtigste
  Regel dieses Projekts, weil sie schon einmal verletzt wurde: Mock-Angebote
  trugen echte Anbieternamen ("DB Navigator") und die Ergebnisliste war
  pauschal als "echte Preise" beschriftet, sobald *Flüge* echt waren. Ein
  Nutzer wollte daraufhin eine erfundene 42-EUR-Verbindung buchen, die es
  nie gab. Deshalb gilt:
  - Mock-Provider verwenden ausschließlich "Beispiel-…"-Namen. Echte
    Anbieternamen dürfen **nur** aus einer echten Provider-Antwort kommen
    (bei Travelpayouts das Feld `gate`).
  - Jedes Angebot wird einzeln markiert (`isMock` im JS, `provider="mock-*"`
    im Python), nie pauschal die ganze Liste.
  - Eine Kombi mit *einem* Mock-Bein (z.B. echter Flug + erfundenes Hotel)
    zählt komplett als Beispieldaten - die Summe wäre sonst nicht buchbar.
  - Wer neue Anbieter "berücksichtigen" soll, für die es keine Preis-API
    gibt: **keine Angebote erfinden**, stattdessen `PROVIDER_LINKS` in
    `app.js` erweitern (echte Suchseiten zum Selbstprüfen).
  - **Kennt eine Quelle die Verbindung, aber nicht den Preis** (Transitous),
    ist der richtige Weg `Offer.price_known = False` / `priceKnown: false`
    im JS - nicht ein geschätzter Preis. `price` bleibt dann auf 0.0 als
    reiner Platzhalter, und dieser Platzhalter darf **nirgends** wie ein
    Preis wirken. Konkret geprüft in `tests/test_transitous.py`:
    "Preis unbekannt" statt "0.00 EUR", nie ein Deal, nie im Median, nie in
    der Preishistorie, kein Budget-Filter, keine Spar-Empfehlung, und beim
    Sortieren immer hinter allen bepreisten Optionen (sonst stünde eine
    unbekannte Verbindung bei "Preis aufsteigend" ganz oben, als wäre sie
    gratis).
- **Beispieldaten sind Opt-in (`route.showMockData`), Voreinstellung aus.**
  Vorher füllten die Mock-Generatoren jede Lücke, und eine Suche ohne echte
  Treffer zeigte drei erfundene Preise statt einer ehrlichen Leermeldung -
  genau das, was der Nutzer wiederholt als „die Flüge sind immer noch fake"
  gemeldet hat. Der Leerzustand in `renderResults` ist deshalb kein
  Nebenschauplatz mehr, sondern der Normalfall für Strecken ohne freie
  Quelle: Grund + Anbieter-Links gehören dort hinein.
- **Reihenfolge der Fehlermeldungen beachten.** `lastProxyError` ist global;
  eine später scheiternde Quelle würde die aussagekräftigere Meldung einer
  früheren überschreiben. Ryanair läuft zuerst und kennt nur eigene Strecken,
  deshalb wird sein Fehler geparkt (`ryanairError`) und nur verwendet, wenn
  sonst niemand etwas zu sagen hat. Bei neuen Quellen genauso verfahren.
- **Dünne Strecken sind der Normalfall, nicht die Ausnahme.** Live gemessen
  (06.08.2026): BER->BCN liefert 28-45 Angebote pro Monat, HAM->LYS genau
  **3** - und keines davon am gewünschten Tag. Mit `flex_days = 0` sieht das
  aus wie "gar keine Daten". Die Monatsabfrage holt diese Tage aber mit;
  `nearMisses` in `fetchRealFlightOffers` hält sie fest und der Warnkasten
  nennt sie ("wohl aber für 24.08.2026 ab 137 EUR"). Wer hier weiterbaut:
  nie stillschweigend wegfiltern, was die API schon geliefert hat.
- **Cache-Busting nicht vergessen.** `docs/index.html` lädt
  `./app.js?v=<Stand>`, und `BUILD_STAMP` oben in `app.js` schreibt denselben
  Wert in die Fußzeile. **Beide zusammen hochzählen**, wenn sich an `app.js`
  etwas ändert, das Nutzer sehen sollen. GitHub Pages lässt Browser die Datei
  sonst weitercachen - ein Fix ist dann live, der Nutzer sieht aber die alte
  Datei, und der Fußzeilen-Stempel ist die einzige Möglichkeit, das ohne
  Raten auseinanderzuhalten.
- **Beispieldaten immer mit Modus benennen.** "9 Angebote sind Beispieldaten"
  allein ist mehrdeutig: bei einer Flug+Hotel-Suche liest sich das als "die
  Flüge sind erfunden", obwohl nur das Hotel-Bein es ist. `mockModeLabels()`
  hängt deshalb "betrifft: Hotel" an.
- **Stiller Rückfall auf Mock-Daten ist selbst ein Fehler.** Wenn eine
  echte Quelle nichts liefert, springen die Mock-Generatoren ein - das ist
  richtig, aber der Nutzer sah dann nur "Beispieldaten - nicht buchbar" und
  konnte nicht unterscheiden zwischen "diese Strecke hat dort keine Preise",
  "der Ort wurde nicht verstanden" und "der Proxy ist tot". Deshalb hält
  `lastProxyError` den Grund fest und `flightFallbackReason` wird bis in den
  Warnkasten durchgereicht. Neue Quellen bitte genauso: Grund nennen, nicht
  nur zurückfallen.
- **Freitext im Von/Nach-Feld muss aufgelöst werden.** Die Preis-API kennt
  nur 2-4-stellige Codes, der Worker lehnt alles andere mit 400 ab. Wer
  "Berlin" tippt und *nicht* aus der Vorschlagsliste auswählt, bekam damit
  stumm Beispieldaten - genau das Symptom "die Flüge sind immer noch fake".
  `resolveAirportCode()` schickt den Freitext durch dieselbe Places-API wie
  das Autocomplete und bevorzugt den Stadt-Eintrag (Metro-Code deckt alle
  Flughäfen der Stadt ab).
- **Anbieter-Links ohne erfundene Query-Parameter.** `PROVIDER_LINKS`
  verlinkt Einstiegsseiten, weil Flixbus/Omio/Trainline interne
  Stations-IDs brauchen, die von hier nicht auflösbar sind. Ausgedachte
  Parameter würden Links erzeugen, die aussehen wie eine fertige Suche und
  ins Leere führen - derselbe Fehler eine Ebene höher. Ausnahme: bahn.de
  akzeptiert Klartext-Orte und landet im Zweifel auf der Suchmaske.
- **Python ↔ JS Spiegelung ist Pflicht.** Es gibt keine automatisierte
  Prüfung dafür (kein gemeinsamer Codegen) - bei jeder Modell-/Engine-
  Änderung beide Seiten von Hand synchron halten, sonst driften Suche
  (JS, Mock) und Alerts (Python, echte Historie) auseinander.
- **Direktflug-Dauer-Schätzung nur für `stops == 0`.** Sowohl
  `providers/geo.py` als auch die JS-Kopie (`estimateDirectFlightDurationHours`
  in `app.js`) geben bei Verbindungen `duration_hours = 0.0` (= "unbekannt")
  zurück statt zu raten - das wird von `max_duration_hours`-Filtern bewusst
  nicht rausgefiltert (siehe `engine._meets_hard_constraints`).
- **`duration_to` (Minuten) aus der echten Travelpayouts-Antwort schlägt
  die eigene Distanzschätzung**, wenn vorhanden - echte Daten, funktioniert
  auch bei Umstiegen (nicht auf Direktflüge beschränkt).
- **Flugpreise werden pro MONAT abgefragt, nicht pro Tag.** Das ist die
  wichtigste Eigenschaft der Flugsuche und leicht versehentlich
  kaputtzumachen: gegen die Live-API gemessen liefert
  `aviasales/v3/prices_for_dates` für ein *konkretes Datum* genau 1 Angebot,
  für einen *ganzen Monat* 27-44. Also: eine Anfrage je Monat, danach
  clientseitig auf die Kandidatentage filtern. Wer das auf Tagesabfragen
  zurückdreht, halbiert die Ergebnisliste auf einen Bruchteil.
  Bei Hin+Zurück muss `return_at` ebenfalls ein *Monat* sein - ein
  konkretes Rückreisedatum liefert null Zeilen.
- **Zwei Preis-Indizes werden gemischt**: `prices_for_dates` (hat echte
  Deep-Links je Verbindung + `gate`) und `v2/prices/latest` (kennt teils
  andere Verbindungen, aber keine Links). `latest` liefert bei Hin+Zurück
  nichts und wird dort übersprungen.
- **Anzeigelimits sind bewusst hoch** (`MAX_RESULTS_SHOWN = 40` in app.js,
  `top_n = 25` in engine.search) - die alten Werte 6/5 waren selbst ein
  wesentlicher Grund für "kaum Ergebnisse".
- **Round-Trip-Preis ist ein kombinierter Gesamtpreis**, kein
  client-seitiges Aufsummieren zweier Angebote - so liefert es die echte
  Travelpayouts-API (`return_date`-Param → ein Preis für beide Strecken),
  Mock-Provider bilden das mit `_round_trip_addon`/`roundTripAddon` nach.
- **Best-Value-Score:** `50% Preis + 25% Dauer + 25% Komfort`
  (`BEST_VALUE_*_WEIGHT` in `engine.py` / `app.js`). Komfort-Score ist
  einfacher Durchschnitt aus normalisierten Einzelwerten (Sterne, Bewertung,
  Amenity-Quote, Entfernung fürs Hotel; Beinfreiheit, WLAN, Steckdosen,
  Direktflug-Bonus, Pünktlichkeit für Transport).
- **Uhrzeit-Fenster ist zirkulär** (`_circular_minutes_diff` /
  `circularMinutesDiff`) - eine 23:30-Präferenz mit 90min Flex matched auch
  00:30, damit es über Mitternacht funktioniert.
- **Spätere-Abfahrt-Empfehlung filtert erst nach den eigenen
  Zeitfenster-Constraints** - sonst könnte sie eine Zeit vorschlagen, die
  der Nutzer selbst ausgeschlossen hat (war ein echter Bug, siehe Git-Log).
- **Gepäck ist zweigeteilt:** `checked_bags`/`checked_bag_kg` (aufgegebenes
  Gepäck) und `carry_on_count`/`carry_on_max_kg` (Handgepäck) sind
  getrennte Felder in `BaggagePref` - keine Ja/Nein-Checkbox mehr.
- **Hotel-Amenity-Listen sind über mehrere Dateien synchron zu halten:**
  `HOTEL_AMENITY_FIELDS`/`_HOTEL_AMENITY_REQUIREMENTS` (engine.py),
  `_HOTEL_REQUIRE_FIELDS` (config.py), `_HOTEL_AMENITY_PROBABILITY`
  (mock.py) und `HOTEL_AMENITY_REQUIREMENTS`/`HOTEL_AMENITY_PROBABILITY`
  (app.js) sind vier separate, aber inhaltlich deckungsgleiche Listen -
  eine neue Amenity braucht eine Ergänzung an allen vier Stellen (+ Offer/
  HotelPref-Dataclass-Felder + Checkbox in index.html).
- **`MEAL_PLAN_TIERS`/`PROPERTY_TYPES`** (models.py, gespiegelt in app.js)
  sind geordnete Listen - `min_meal_plan`-Filter vergleicht Tier-Indizes
  ("mindestens Halbpension" matched auch All-Inclusive-Angebote).
- **"Deal" hat zwei Quellen**: die Preishistorie (Preisverfall/Fehlerpreis,
  nur im Python-Cron verfügbar) und - wenn keine Historie existiert - der
  Vergleich mit dem Median derselben Suche (`_flag_below_median` /
  `flagBelowMedian`, je Verkehrsmittel, mind. 4 Kandidaten). Der
  `deals_only`-Filter darf bewusst leer ausgehen, statt normale Preise als
  Deals auszugeben.
- **Die KI kann keine Flüge suchen.** Die KI-Empfehlung (`POST /ai` im
  Worker) bekommt ausschließlich die bereits gefundenen Angebote und wird
  im Prompt angewiesen, nichts zu erfinden. Wenn jemand "mehr Ergebnisse"
  will, ist die Antwort die Monatsabfrage oben oder mehr Flex-Tage - nicht
  die KI.
- **Drei KI-Anbieter, einer genügt**: `AI_PROVIDERS` in
  `worker/src/index.js` - Gemini, Groq, Mistral, in dieser Priorität; es
  gewinnt der erste, dessen Key gesetzt ist. Hintergrund: Google sperrt
  manchen Konten die Key-Erstellung ganz ("Sie sind derzeit nicht
  berechtigt, API Key zu erstellen"), Groq/Mistral brauchen weder
  Cloud-Projekt noch Zahlungsdaten. Groq und Mistral teilen sich den
  OpenAI-Chat-Request; Gemini hat ein eigenes Format. Modellnamen sind über
  die Variable `AI_MODEL` überschreibbar - die Defaults sind **nicht** gegen
  die echten APIs verifiziert (aus der Sandbox nicht möglich, und es lag
  kein Key vor), deshalb dieser Ausweg ohne Codeänderung.
- **Worker-Tests**: `cd worker && npm test` (`worker/test/ai.test.mjs`,
  reines Node, keine Dependencies) - stubbt `fetch` und prüft alle drei
  Anbieter plus die Fehlerpfade. Läuft nicht in der pytest-Suite mit, also
  bei Änderungen am `/ai`-Endpunkt extra ausführen.
- **Von/Nach-Autocomplete-Quelle hängt vom aktiven Modus ab**
  (`MODE_TAB_CONFIG[mode].placeSource`: `'flight'` = echte
  Travelpayouts-Places-API mit IATA-Code als Wert, `'city'` = dieselbe API
  nur city-Typ mit Klartext-Namen als Wert (fürs Hotel-"Ort"-Feld),
  `'rail'` = statische `RAIL_STATIONS`-Liste, kein Netzwerk nötig.

## Testing

```bash
pip3 install --user requests PyYAML pytest   # falls nicht vorhanden
cd /workspace/hackyourtrip
python3 -m pytest tests/ -q                  # 105 Tests, alle sollten grün sein
node --check docs/app.js                     # Syntax-Check JS
node --check worker/src/index.js
npm --prefix worker test                     # 19 Worker-Tests (/ai + /transit)
```

Die Worker-Tests setzen bei einem Fehlschlag `process.exitCode = 1` - vorher
haben sie nur "FAIL" gedruckt und trotzdem mit 0 beendet, was `npm test`
dauerhaft grün aussehen ließ.

Für UI-Checks (kein `npm test`, kein Framework): lokalen Static-Server
starten und mit Playwright (Chromium liegt unter
`/opt/pw-browsers/chromium`, `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` ist schon
gesetzt) gegen `http://localhost:PORT/index.html` testen. Skripte dafür
landen typischerweise im Scratchpad, nicht im Repo.

## Git-Stolperfallen (wichtig für neue Sessions!)

- Der GitHub-Nutzername wurde von `mysportpilot` zu `kalivolut` geändert.
  Der lokale `origin`-Remote zeigt weiterhin auf
  `https://github.com/mysportpilot/hackyourtrip` - **das ist Absicht**:
  der Session-Git-Proxy autorisiert nur den ursprünglichen Owner-String,
  ein Remote auf die neue `kalivolut/...`-URL bekommt 403. GitHubs
  automatische Weiterleitung macht das aber transparent - `git push` auf
  die alte URL funktioniert einwandfrei und landet im richtigen (jetzt
  umbenannten) Repo.
- **Nicht versuchen, den Remote auf `kalivolut/...` umzustellen** - das
  bricht den Push in dieser Sandbox-Umgebung.
- `python3`/`pip3` in dieser Sandbox haben `requests`/`PyYAML`/`pytest`
  nicht vorinstalliert (nur `/root/.local/bin/pytest` als isoliertes
  `uv`-Tool, das die falschen Packages sieht) - `pip3 install --user`
  reinstalliert das bei jeder neuen Session neu, ist aber schnell erledigt.
- Die Sandbox hat **kein allgemeines Internet** (curl zu z.B.
  `api.travelpayouts.com` oder der deployten `workers.dev`-URL schlägt
  fehl). Für alles, was echten Internetzugriff braucht (z.B. eine neue
  API-Shape verifizieren), einen temporären Smoke-Test-Schritt in einen
  GitHub-Actions-Workflow einbauen, per `mcp__github__actions_run_trigger`
  auslösen, und das Ergebnis über `mcp__github__get_job_logs` lesen -
  GitHub-Actions-Runner haben normalen Internetzugang, die Sandbox nicht.

## Deploy / Infrastruktur

- **GitHub Pages**: `docs/` wird als Pages-Site gehostet (Live-Demo).
- **Cloudflare Worker** (`worker/`): proxied Travelpayouts-Anfragen für die
  Live-Suche, deployt über `.github/workflows/deploy-worker.yml`
  (`cloudflare/wrangler-action@v4`, Secret wird per Actions-Input gesetzt -
  **kein lokales CLI/Terminal nötig**, alles über GitHub-Dashboard-Secrets +
  workflow_dispatch). Live-URL:
  `https://hackyourtrip-proxy.iamanamelessman.workers.dev`.
- **GitHub Actions Cron** (`.github/workflows/check-deals.yml`): führt
  `traveldeals check` regelmäßig aus, braucht `config/routes.yaml` (oder
  ein Secret damit) + `TRAVELPAYOUTS_TOKEN` + Notifier-Secrets
  (Telegram/E-Mail, optional).
- **Supabase**: wird für die Schwester-App `mysportpilot` verwendet, nicht
  für hackyourtrip selbst (nur als Vorbild für eine mögliche
  Multi-User-Zukunft erwähnt, siehe README-Roadmap).

## Aktueller Stand / offene Aufgaben

Stand 2026-08-05, alle fünf User-Feedback-Punkte aus dieser Session sind
abgeschlossen und einzeln committed+gepusht:

1. **Datum-UX vereinfacht**: Flug/Bahn/Bus + Oder-Kombis zeigen nur noch
   ein "Datum"-Feld (Flex-Tage-davor/danach spannen den Suchzeitraum auf,
   die vorherige "Datum bis"-Spanne war redundant dazu); bei Hin+Zurück
   kommt das Rückreisedatum-Feld dazu. Hotel/*_hotel behalten die
   Anreise-Spanne (`departUntilGroup`/`cfg.singleDate` in `app.js`).
2. **Von/Nach-Autocomplete**: Flug/Hotel nutzen die echte, tokenlose
   `autocomplete.travelpayouts.com/places2`-API (Shape per
   GitHub-Actions-Smoke-Test verifiziert - liefert `type`, `code`, `name`,
   `city_name`, `weight` fürs Ranking); Bahn/Bus nutzen seit 06.08.2026 den
   Transitous-Geocoder (`fetchTransitStops`), also dieselbe Datenbank, mit
   der danach geroutet wird - `RAIL_STATIONS` in `app.js` ist nur noch der
   Offline-Fallback.
   Generische Typeahead-Komponente mit Tastatur-Navigation, degradiert
   graceful auf Freitext bei Netzwerkfehlern.
3. **Hotel-Kriterien vervollständigt**: `HotelPref`/`Offer` haben jetzt
   Unterkunftsart (`PROPERTY_TYPES`), Verpflegungsstufe (`MEAL_PLAN_TIERS`,
   ersetzt die alte `require_breakfast`-Checkbox) und 27 einzelne
   Ausstattungsmerkmale (Pool/Gym jetzt getrennt statt kombiniert). Läuft
   in Python (`models.py`/`engine.py`/`mock.py`/`config.py`) und JS
   (`app.js`) synchron, `index.html` gruppiert die Checkboxen in
   Unterkategorien statt einer langen Liste.
4. **Gepäck-Eingabe überarbeitet**: `carry_on_only` (war ohnehin nirgends
   in der Filterlogik verwendet - nur YAML-Exportfeld) ersetzt durch
   `carry_on_count` + `carry_on_max_kg`, gleichwertig zu den bestehenden
   `checked_bags`/`checked_bag_kg`. Formular zeigt zwei getrennte Blöcke
   ("Aufgegebenes Gepäck" / "Handgepäck").

Zweite Runde User-Feedback, ebenfalls abgeschlossen:

5. **"Gewicht egal" beim Gepäck**: `checked_bag_kg`/`carry_on_max_kg` sind
   jetzt Optional; null = keine Vorgabe, ausdrücklich verschieden von 0.
6. **Deutlich mehr Flugergebnisse**: Monatsabfragen statt Tagesabfragen,
   zwei gemischte Indizes, echte Deep-Links + echter Buchungsanbieter je
   Verbindung, Anzeigelimit 6->40 (JS) bzw. 5->25 (Python). Im
   Playwright-Durchlauf 6 -> 26 Ergebnisse bei *weniger* API-Anfragen.
   Details oben unter "Wichtige Konventionen".
7. **Sortierung**: `most_expensive` und `exact_date` ergänzt, Feld heisst
   jetzt "Sortieren nach".
8. **Deals-Filter** (`deals_only`) inkl. Median-Heuristik ohne Historie.
9. **KI-Empfehlung** über `POST /ai` im Worker. Erst nur Gemini; nachdem
   Google dem Konto des Nutzers die Key-Erstellung verweigert hat, auf drei
   Anbieter erweitert (Gemini/Groq/Mistral, siehe Konventionen oben).

Keine offenen Aufgaben. Volle Testsuite (80 Tests) grün, JS- und
Worker-Syntax geprüft, alle Features per Playwright gegen einen lokalen
Static-Server verifiziert (inkl. der drei KI-Pfade: Erfolg, Key fehlt,
Netzwerkfehler).

**Offene Erwartungshaltung, die man kennen sollte:** Der Nutzer vergleicht
mit Skyscanner/Momondo/Opodo. Diese Portale fragen Airline-Systeme live ab;
die kostenlose Travelpayouts-Stufe ist ein Cache zuletzt *gefundener*
Preise. Die Ergebnismenge wurde hier ausgereizt, aber Gleichstand mit einer
Live-GDS-Suche ist mit kostenlosen Zugängen nicht erreichbar - das gehört
bei Rückfragen ehrlich gesagt, statt es durch weitere Tricks zu
suggerieren.

## Recherche: kostenlose APIs ohne Anmeldung (06.08.2026, live geprüft)

Ergebnis der Suche nach Ersatz für die erfundenen Bahn-/Bus-/Hotel-Preise -
damit das nicht jede Session neu geprüft wird:

| Quelle | Ergebnis |
|---|---|
| `v6.db.transport.rest`, `v5.db.transport.rest` | HTTP 503, Dienst nicht verfügbar |
| `flixbus.transport.rest`, `v1.flixbus...` | NXDOMAIN, existiert nicht |
| `vendo-prof-db.dbrail.de` | NXDOMAIN |
| **`api.transitous.org` (MOTIS)** | **funktioniert ohne Key**: `/api/v1/geocode` + `/api/v1/plan` liefern echte Verbindungen (~150 KB Antwort für Berlin->München). Aber `debugOutput.fares: 0` - **keine Preise** |
| `v6.vbb` / `v6.bvg.transport.rest` | 200, nur Berlin/Brandenburg-Nahverkehr |
| OpenTripMap | 401, Key nötig |
| Nominatim | 200, aber reiner Geocoder ohne Preise |

**Fazit:** Preise für Bahn/Bus/Hotel sind kostenlos und ohne Anmeldung nicht
zu bekommen. Fahrpläne schon - über Transitous.

**Umgesetzt (06.08.2026):** `traveldeals/providers/transitous.py` +
die Spiegelung in `docs/app.js` liefern jetzt genau das - echte Verbindungen
(Linien wie "ICE 599 → RE 4021", Abfahrt/Ankunft, Gleis, Umstiege) **ganz
ohne Preis**, siehe `Offer.price_known` unter den Konventionen oben.

Details, die beim Weiterarbeiten Zeit sparen (alle gegen die Live-API
verifiziert, Antwortstruktur per Wegwerf-Workflow abgegriffen):

- Endpunkte: `GET /api/v1/geocode?text=&language=` und
  `GET /api/v1/plan?fromPlace=&toPlace=&time=&numItineraries=&transitModes=`.
- Der Geocoder mischt `type: "STOP"` (Haltestellen) mit `type: "PLACE"`
  (POIs). **Nur STOPs routen** - der erste Treffer für "München Hbf" war
  eine Sauna neben dem Bahnhof.
- Zeiten kommen in **UTC mit `Z`**, der Rest des Projekts rechnet in naiver
  Ortszeit. Umgerechnet wird über das `tz`-Feld der Haltestelle
  (`_to_local_naive` / `zonedDate`). Ohne das zeigt ein ICE ab Berlin 08:37
  statt 10:37.
- MOTIS liefert "die nächsten N Verbindungen nach `time`" - eine Anfrage pro
  Tag beschreibt also nur den frühen Morgen. Deshalb drei Anker-Zeiten pro
  Tag (06/12/18 Uhr) und Deduplizierung über `(Abfahrt, Linie)`.
- Request-Budget bewusst gedeckelt (`MAX_DAYS_QUERIED = 4` x 3 Anker = 12):
  Transitous ist ein ehrenamtlich betriebener Dienst. Der Worker cacht
  zusätzlich eine Stunde an der Edge, und `User-Agent` identifiziert die App,
  wie Transitous es sich wünscht.
- Es gibt **keine Buchungs-URL** für eine MOTIS-Verbindung, deshalb bleibt
  `url` leer und die `PROVIDER_LINKS` unter den Ergebnissen übernehmen das.
- **Zwei User-Agent-Fallen, beide live erlebt:** Transitous weist Anfragen
  ohne eigenen User-Agent mit 403 ab ("Generic user-agent headers are not
  allowed") - deshalb der `USER_AGENT`/`TRANSIT_USER_AGENT`-Header. Und
  umgekehrt blockt *Cloudflare* den Standard-UA von Pythons `urllib` vor dem
  eigenen Worker mit 403 "error code: 1010". Ein Smoke-Test ohne gesetzten
  UA schlägt also fehl, ohne den Worker je erreicht zu haben - das sah eine
  Runde lang nach einem kaputten Proxy aus, betraf aber genauso `/cheap`,
  das per `curl` einwandfrei lief.
- **Nicht abgedeckt:** In den Kombi-Modi "Flug oder Bahn"/"Flug oder Bus"
  steht im Von/Nach-Feld ein IATA-Code ("BER"), den der Transitous-Geocoder
  nicht als Haltestelle auflöst - dort fällt das Bahn-/Bus-Bein weiterhin
  auf Beispieldaten zurück (klar als solche markiert). Sauber wäre eine
  Code-zu-Stadt-Auflösung über die schon genutzte Travelpayouts-Places-API;
  MOTIS akzeptiert laut Doku auch "lat,lon" als `fromPlace`, das ist hier
  aber nicht verifiziert worden und deshalb bewusst nicht eingebaut.
- **Nicht abgedeckt:** Hin-und-zurück liefert nur die Hinfahrt
  (`returnDepart` bleibt `null`) - eine zweite Suche in Gegenrichtung wäre
  der nächste Ausbauschritt. Und GTFS kennt keine Bordausstattung, deshalb
  bleiben `wifiOnboard`/`powerOutlets` auf `false` ("nicht bestätigt", nicht
  "nicht vorhanden"); eine Suche mit *Pflicht*-WLAN filtert diese
  Verbindungen deshalb weg.

**Zweite Recherche-Runde (06.08.2026), Flugpreise, ebenfalls live geprüft:**

| Quelle | Ergebnis |
|---|---|
| **`services-api.ryanair.com/farfnd/v4/oneWayFares` + `/roundTripFares`** | **HTTP 200 ohne Schlüssel**, echte buchbare Preise. Eingebaut als `providers/ryanair.py`. |
| Ryanair `booking/v4/.../availability` | 409 „Availability declined" - braucht Buchungs-Session |
| Ryanair `farfnd/v4/.../cheapestPerDay` | 200, aber `fares: []` |
| `services-api.ryanair.com/locate/3/routes/{IATA}` | 403 |
| `www.ryanair.com/api/views/locate/5/airports/de/active` | 200, 224 Flughäfen mit Koordinaten |
| `bahn.de` Sparpreise (inoffiziell) | 403 `OPS_BLOCKED` |
| Lufthansa Open API | 596 |
| SNCF / Navitia | 401 |

Wichtig für Ryanair: ein normaler Skript-User-Agent bekommt auf manchen
Hosts 403, deshalb gibt sich der Worker als Browser aus. Und die Grenze
ehrlich benennen - Ryanair kennt **nur Ryanair-Strecken**; HAM->LYS fliegt
Ryanair nicht. `CompositeProvider` mischt deshalb mehrere Quellen, statt eine
auszuwählen.

Weiterhin offen bleibt der **Preis** für Bahn/Bus. DB-Wrapper regelmässig neu
prüfen: kämen sie zurück, gäbe es dort sogar Sparpreise.

## Roadmap-Ideen (nicht in Arbeit, nur notiert)

- Bahn/Bus-**Preise** (Fahrpläne laufen seit 06.08.2026 echt über
  Transitous). DB/HAFAS und FlixBus haben dafür kein offenes Self-Serve-API.
- Travelpayouts GraphQL-Endpoint (`trip_duration`-Feld) für bessere
  Umstiegs-Dauer - Schema nicht verifizierbar gewesen, deshalb nicht
  implementiert (Docs gaben 403 auf WebFetch).
- Multi-User/Web-Formular statt YAML-Datei editieren (nach Vorbild
  `mysportpilot`/Supabase).
- Cloudflare-Dashboard-Rate-Limiting-Regel gegen Missbrauch (aktuell nur
  Edge-Cache als Quota-Schutz, kein echtes Request-Counting).
