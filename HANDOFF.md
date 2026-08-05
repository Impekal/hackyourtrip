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
- **`carry_on_only` (BaggagePref) wird aktuell nirgends zum Filtern
  verwendet** - nur als YAML-Exportfeld. Wird in der Gepäck-Überarbeitung
  (siehe TODO) ersetzt.

## Testing

```bash
pip3 install --user requests PyYAML pytest   # falls nicht vorhanden
cd /workspace/hackyourtrip
python3 -m pytest tests/ -q                  # ~59+ Tests, alle sollten grün sein
node --check docs/app.js                     # Syntax-Check JS
node --check worker/src/index.js
```

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

## Aktueller Stand / offene Aufgaben (diese Session)

Zuletzt abgeschlossen: Hin-/Rückreise-Auswahl (Flug/Bahn/Bus + Kombis),
echte klickbare Aviasales-Buchungslinks, Uhrzeit-Flexibilität,
Cloudflare-Worker-Proxy ohne CLI.

**Gerade in Arbeit** (User-Feedback vom 2026-08-05, alle vier parallel offen):

1. **Datum-UX vereinfachen**: Bei Nur-Hinflug nur EIN Datumsfeld zeigen
   (Flex-Tage bestimmen ja schon das Zeitfenster, "Datum bis" ist
   redundant); bei Hin+Zurück ein Hin-Datum + ein Rück-Datum. Betrifft nur
   Flug/Bahn/Bus + deren Oder-Kombis, nicht Hotel/*_hotel (da bleibt die
   Anreise-Spanne sinnvoll fürs Checkin-Fenster).
2. **Autocomplete für Von/Nach**: Stadt eintippen → Flughäfen (Flug) bzw.
   Bahnhöfe (Bahn/Bus) zur Auswahl vorschlagen, wie auf gängigen
   Reiseplattformen. Plan: für Flughäfen die öffentliche
   Travelpayouts-Autocomplete-API prüfen (echte Daten statt statischer
   Liste) - Shape vorher per GitHub-Actions-Smoke-Test verifizieren, da die
   Sandbox das nicht direkt erreichen kann. Für Bahn/Bus-Stationen gibt es
   keine bekannte freie API dafür - kuratierte statische Liste geplant.
3. **Hotel-Kriterien vervollständigen**: aktuell nur ~7 Amenities,
   soll ein "wirklich alles"-Set wie Trivago werden (Verpflegungsstufen,
   Objekttyp, Spa, Gym separat von Pool, Restaurant, Bar, Zimmerservice,
   24h-Rezeption, Business-Ausstattung, Wäscheservice, Aufzug,
   Balkon/Terrasse, Küche, Strandnähe, Barrierefreiheit, E-Ladestation,
   Fahrradverleih, Babysitting, Sauna, Whirlpool, Nichtraucher,
   Familienzimmer, Flughafentransfer, ...). Betrifft `HotelPref`/`Offer`
   in `models.py`, `engine.py` (Filter + Komfort-Score), `mock.py`,
   `config.py`, `routes.example.yaml`, und die komplette JS-Spiegelung in
   `app.js` + neue Checkboxen in `index.html`.
4. **Gepäck-Eingabe überarbeiten**: Koffer als "Gewicht pro Stück (z.B.
   23kg) + Anzahl" (existiert schon: `checked_bag_kg`/`checked_bags`),
   zusätzlich **Handgepäck separat** mit eigenem Gewichtslimit (z.B. 8kg)
   + Anzahl statt der aktuellen reinen Ja/Nein-Checkbox
   (`carry_on_only`, die ohnehin nirgends filtert). Neue Felder:
   `carry_on_max_kg`, `carry_on_count` in `BaggagePref`.

Reihenfolge in dieser Session: 2 (Datum) → 3 (Autocomplete) → 4 (Hotel) →
5 (Gepäck) als eigene Commits, danach diese Datei mit dem finalen Stand
aktualisieren.

## Roadmap-Ideen (nicht in Arbeit, nur notiert)

- Bahn/Bus durch echte APIs ersetzen (DB/HAFAS, FlixBus) - aktuell immer
  Mock-Daten.
- Travelpayouts GraphQL-Endpoint (`trip_duration`-Feld) für bessere
  Umstiegs-Dauer - Schema nicht verifizierbar gewesen, deshalb nicht
  implementiert (Docs gaben 403 auf WebFetch).
- Multi-User/Web-Formular statt YAML-Datei editieren (nach Vorbild
  `mysportpilot`/Supabase).
- Cloudflare-Dashboard-Rate-Limiting-Regel gegen Missbrauch (aktuell nur
  Edge-Cache als Quota-Schutz, kein echtes Request-Counting).
