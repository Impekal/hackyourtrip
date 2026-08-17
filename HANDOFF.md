# HackYourTrip – Handoff / Projektstatus

Diese Datei ist für eine **neue Chat-Session ohne Vorwissen** gedacht: wer
hier weiterarbeitet, sollte nach dem Lesen wissen, wie das Projekt
aufgebaut ist, welche Entscheidungen warum getroffen wurden, und was gerade
offen ist. Bitte diese Datei aktuell halten (TODO-Liste unten pflegen,
neue Design-Entscheidungen dokumentieren) - sie ersetzt kein Gedächtnis.

Repo: `github.com/Impekal/hackyourtrip` (**Achtung**: zweimal umbenannt -
`mysportpilot` → `kalivolut` → `Impekal`; siehe Abschnitt
"Git-Stolperfallen" unten, der lokale `origin`-Remote zeigt noch auf die
ursprüngliche URL und funktioniert nur deshalb, weil GitHub automatisch
weiterleitet). Stand 17.08.2026 ist das Repo **privat** - Folgen siehe
Git-Stolperfallen.

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
    gratis). Einzige Ausnahme: bei Sortierung nach "Dauer" zählt die Dauer,
    die diese Angebote mitbringen, und die ist echt.
- **Sortierung ist Ansichtssache, keine Sucheingabe.** `#sortBy` und die
  Abschnittsreiter (`#legTabs`) sitzen in `#resultControls`, außerhalb von
  `#searchResults`, damit die Listener einen Neuaufbau der Liste überleben.
  `runSearch()` liefert deshalb **unsortierte** Kandidaten je Abschnitt;
  `sortCandidates()` + `addRecommendations()` laufen erst in
  `renderActiveSection()`, auf den ~40 tatsächlich gezeigten Zeilen. Wer hier
  wieder vorsortiert oder in `runSearch` abschneidet, macht jeden
  Sortierwechsel wieder zu einer kompletten neuen Anbieter-Runde - genau das
  war der Grund für den Umbau. `ui_sections.py` prüft das explizit über die
  Zahl der abgesetzten Proxy-Requests.
- **Hin+Rück liefert drei Abschnitte** (`outbound` / `inbound` / `combined`),
  jeder mit eigenem Routen-Variant, eigenen Pools und eigenem
  `dateDeviation`-Bezug (die „exakte" Datumsnähe der Rückfahrt misst gegen
  das Rückreisedatum, nicht das Hinreisedatum). Voreingestellt ist
  `combined` - das ist die Reise, nach der gesucht wurde. Der Pool-Cache in
  `runSearch` ist deshalb nach Routen-Variante **und** Modus gekeyt: Hinweg,
  Rückweg und Rundreise sind drei verschiedene Abfragen an dieselben Quellen.
- **FlixBus-Autocomplete niemals ungeprueft nehmen.** Sie antwortet auf
  alles mit irgendetwas, und der erste Treffer ist regelmaessig falsch - live
  gemessen: `"Hamburg Hbf"` -> Berlin, `"Köln Hbf"` -> Berlin,
  `"Münster(Westf) Hbf"` -> Ascheberg. Der Bus-Tab schlaegt aber Bahnhoefe
  vor, FlixBus sucht Staedte. Das war kein "keine Buspreise", sondern: eine
  Suche Hamburg->Köln fragte FlixBus nach **Berlin->Berlin**. Deshalb
  `_city_queries()` (Bahnhofs-Suffix und Klammerzusatz abschneiden, IATA
  uebersetzen) plus `_pick_city()` (Treffer muss zur Anfrage passen, sonst
  None). Lieber keine Buspreise als Preise fuer die falsche Strecke.
  Spiegelbild im JS: `flixbusCityQueries` / `flixbusPickCity`. Test-Fixtures
  muessen seitdem auf die Anfrage antworten - eine feste Trefferliste faellt
  zu Recht durch.
- **Freigepaeck ist Angebots-, keine Suchangabe.** `Offer.included_carry_on_kg`
  / `included_checked_bags` / `included_checked_bag_kg` (+ `baggage_source`)
  sagen, was der *Tarif* enthaelt - `RoutePreference.baggage` sagt, was der
  Reisende *mitnehmen will*. Zwei verschiedene Dinge, nicht vermischen.
  `None` heisst **"keine Angabe"** und ist nicht "nicht enthalten": die
  meisten Preisquellen schweigen zum Gepaeck, und dann erzeugt
  `baggageChips()` bewusst gar keinen Chip. Wer hier eine Default-Zahl
  einsetzt, wiederholt den Fake-Preis-Fehler in neuer Form. Gefuellt wird
  nur, wo es eine Quelle gibt: ein API-Feld oder die veroeffentlichten
  Tarifbedingungen des Anbieters - und die gehoeren dann in
  `baggage_source`, damit eine veraltete Zahl nachvollziehbar bleibt.
  **Beantwortet (07.08.2026, probe-baggage.yml, live gemessen): KEINE der
  drei Preisquellen nennt Gepaeck.**
  - Ryanair `oneWayFares`: ein Fare hat genau `outbound` und `summary` -
    Flughaefen, Zeiten, Preis, flightKey. Kein Gepaeck-Feld.
  - FlixBus `search`: Trip-Schluessel sind arrival, available, departure,
    duration, legs, messages, price, provider, remaining, restrictions,
    status, transfer_type, transfer_type_key, uid. Kein Gepaeck-Feld.
  - Skiplagged: Top-Level airlines/airports/cities/depart/duration/flights/
    incomplete/info/return/show_loading; die Eintraege sind undurchsichtige
    Arrays. Kein Gepaeck-Feld.
  Aus der API kann die Angabe also nicht kommen - nicht nochmal durchsuchen.
  **Zweite Runde, die veroeffentlichten Gepaeckseiten (probe-baggage-rules.yml,
  07.08.2026): auch nicht auslesbar.**
  - `ryanair.com/.../Baggage` -> HTTP 403; die anderen Ryanair-Seiten liefern
    4-46 Zeichen Text ("Fees", "Book cheap flights...") - JS-gerendert.
  - `flixbus.de/service/gepaeck` und `.com/service/luggage` -> HTTP 200 mit
    ~6000 Zeichen, aber **keine einzige kg-/cm-Angabe im Text**; die Zahlen
    stehen in nachgeladenen Komponenten.
  - `help.flixbus.com` -> Salesforce-SPA, Text ist "FlixHelp Loading ...".
  Damit gibt es **keine belegbare Quelle** fuer Kilo-Zahlen. Der Ausweg ohne
  Erfindung: `BAGGAGE_RULES_LINKS` in app.js verlinkt die Gepaeckseite des
  Anbieters direkt aus der Angebotszeile ("🧳 Gepaeckregeln"). Wer spaeter
  echte Zahlen hat (vom Nutzer genannt, aus einem neuen Endpunkt), traegt
  sie in `included_*` ein - **immer mit Quelle und Stand in
  `baggage_source`**, nie aus dem Gedaechtnis.
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

- Der GitHub-Nutzername wurde zweimal geändert: `mysportpilot` →
  `kalivolut` → `Impekal` (Stand 17.08.2026). Der lokale `origin`-Remote
  zeigt weiterhin auf `https://github.com/mysportpilot/hackyourtrip` -
  **das ist Absicht**: der Session-Git-Proxy autorisiert nur den
  ursprünglichen Owner-String, ein Remote auf die neue URL bekommt 403.
  GitHubs automatische Weiterleitung macht das aber transparent -
  `git push` auf die alte URL funktioniert einwandfrei und landet im
  richtigen (jetzt umbenannten) Repo.
- **Nicht versuchen, den Remote auf `Impekal/...` umzustellen** - das
  bricht den Push in dieser Sandbox-Umgebung.
- Das Repo ist seit der Umbenennung zu `Impekal` **privat** (per
  `list_repos` gemessen: `visibility: private`; `raw.githubusercontent.com`
  antwortet unauthentifiziert mit 404). Zwei Dinge hängen an einem
  öffentlichen Repo: die GitHub-Pages-Seite (auf dem Free-Plan gibt es
  Pages nur für öffentliche Repos) und der App-Datei-Selbst-Update des
  lokalen Bahn-Servers (`APP_SOURCE` lädt `docs/` per raw-URL nach -
  privat heißt: der Server bleibt still auf seiner alten Fassung stehen).
  Solange das Repo privat ist, funktionieren beide Wege nicht.
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

Nachtrag 17.08.2026 (Build 2026-08-09-20):

- **Ganztags-Bahnsuche**: Eine DB-`/fahrplan`-Anfrage ist eine "Seite"
  (~6-10 Verbindungen ab dem Anfragezeitpunkt). Ein blankes Datum wurde
  früher auf `T08:00:00` geweitet → genau eine Seite, daher die echte
  Beschwerde "nur 6 Angebote auf einen ganzen Tag und die teuersten".
  Jetzt fächert `bahn-local/server.py` (`get_fahrplan_ganztag`,
  `DAY_ANCHORS`) den Tag über 6 Ankerzeiten auf, legt Dubletten zusammen
  (bei Preisunterschied gewinnt der günstigere - DB-Kontingente), filtert
  Folgetags-Verbindungen und sortiert nach Abfahrt. Volle Zeitstempel
  (Split-Ticket-Reststrecke) bleiben bewusst EINE Anfrage. Jeder Anker
  läuft durch den bestehenden Cache. **Achtung: der Nutzer muss
  `~/bahn-server.py` einmal neu herunterladen** - die Server-Datei
  aktualisiert sich nicht selbst (nur die App-Dateien tun das).
- **"Abfahrt ab (frühestens)"** (`#earliestDepartTime`, neben der
  bevorzugten Uhrzeit): Angebote mit früherer Abfahrt fliegen aus
  Empfehlung UND Spar-Tipps (beides läuft über `meetsTransportPrefs`).
  Ausdrückliche Ausnahme laut Nutzer: liegt die Abfahrt noch im
  ±-Zeitfenster um die bevorzugte Uhrzeit, bleibt sie erlaubt. Gespiegelt
  in Python (`TransportPref.earliest_depart_time`, engine, config,
  `routes.example.yaml`).

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

**Dritte Runde (06.08.2026), weltweit, ~25 Endpunkte:** Der einzige neue
Treffer ist **FlixBus** (`global.api.flixbus.com`, eingebaut als
`providers/flixbus.py`). Zwei Fallen dabei, beide live erlebt:

- Die Suche braucht die **City-UUID**; die `legacy_id` aus derselben
  Autocomplete-Antwort wird mit `Signature "88" ... is invalid` abgelehnt.
  Genau diese Fehlermeldung hat die Lösung verraten.
- `trips[].results` ist ein **Dict, keyed by trip uid**, keine Liste.
- Preis: `price.total` ist der Fahrpreis, `price.total_with_platform_fee`
  das, was an der Kasse steht. Verwendet wird letzteres.

Alles andere fiel durch: Kiwi skypicker 404 (abgeschaltet), Kiwi Tequila
braucht Key, Hotellook in allen Varianten 404, easyJet/Southwest 403,
Norwegian/Volotea Bot-Wall, Wizz/Vueling/AirAsia/Transavia 404,
IndiGo/Amtrak Timeout, SBB 403, SNCF 401.

**Die DB blockt hart:** `int.bahn.de`, `www.bahn.de` und die vendo-Hosts
antworten alle mit 403 `OPS_BLOCKED`. Das ist eine serverseitige Sperre, kein
Header-Problem - nicht weiter versuchen, ohne dass sich dort etwas ändert.

**Runden 4+5 (06.08.2026), Wiederverkäufer und Aggregatoren:** zwei neue
Treffer, beide eingebaut.

- **Skiplagged** (`providers/skiplagged.py`): deckt die Full-Service-Airlines
  ab, die Ryanair nicht fliegt. Antwortstruktur ist ungewöhnlich:
  `flights` ist ein Dict `{id: [[segmente...], dauer_sek, anzahl, token]}`,
  `depart` eine Liste `[[preis_cent], [], token, flight_id]` - der Preis
  steht also *nicht* beim Flug, sondern wird über die id verknüpft.
  **Währung:** die API nennt keine und ignoriert `currency`. Belegt statt
  geraten: die Seite rendert „$", und BER→BCN kostete 62,00, wo Ryanair
  53,36 EUR nannte (0,86 = EUR/USD). Wird über `currency.py` umgerechnet.
  Hidden-City-Tarife werden bewusst **nicht** angezeigt - nur die reguläre
  `depart`-Liste.
- **Deal-Feeds** (`dealfeeds.py`): Urlaubspiraten, Travelfree, Fly4free
  liefern sauberes RSS. Bewusst **nicht** in Offers mit Preisen umgewandelt -
  „Mallorca ab 39 EUR" ist eine Anzeige, keine buchbare Verbindung für die
  Daten des Nutzers.

Was weiterhin blockt: thetrainline/Omio/Busbud/Wanderu hinter DataDome-
Captcha, Rome2Rio-Domain tot, Kiwi skypicker abgeschaltet, Hotels überall
401/404.

**Umkreissuche** (`NearbyAirportsProvider` + `geo.nearby_airports`): seit
der Trennung zwei Felder, `nearby_origin_km` und `nearby_destination_km`
(JS: `nearbyOriginKm`/`nearbyDestinationKm`) - der Umweg am Start wiegt
anders als der am Ziel. `config.py` liest ein altes `nearby_km` weiterhin
als Wert für beide Seiten, damit bestehende `routes.yaml` gleich bleiben.
Läuft
als äußerster Wrapper um den Flug-Composite, damit *alle* Quellen auch die
Nachbarflughäfen bekommen. Jedes Angebot von dort trägt `alt_origin` /
`alt_destination` / `detour_km` - nie ungekennzeichnet, sonst sähe ein Flug
ab Bremen aus wie einer ab Hamburg.

**Runde 6 (06.08.2026) - Bahn über Wiederverkäufer, Hotels zum Zweiten:**
Die Hypothese "SNCF verkauft DB-Tickets, also kommt man dort an DB-Preise"
ist plausibel, hält aber nicht: SNCF Connect 401, B-Europe 404, RailEurope
DNS tot, Trenitalia 400, Italo SOAP-Fault, Renfe hinter Dynatrace, NS
Subscription-Key, Eurostar 403, ÖBB-Ticketshop 404, Interrail 404, Omio 404,
Trainline 404. Einziger 200er: `transport.opendata.ch` (SBB) - Fahrplan ohne
Preise, also derselbe Stand wie Transitous.
Hotels ebenso: Agoda/Trivago 404, Expedia/Hotels.com 429, Kayak liefert nur
ein Hotelmarken-Verzeichnis. **Nicht nochmal durchprobieren**, ohne dass sich
dort etwas ändert.

**Runde 7 (07.08.2026) - Vendo, Community-Frontends, BlaBlaCar, Hotellook:**
Alles negativ, und zwar endgültig genug, um es nicht zu wiederholen:
`app.vendo.noncd.db.de` und `int.vendo.noncd.db.de` haben **kein DNS mehr** -
die Mobil-API der DB-App, auf die praktisch jede Anleitung im Netz verweist,
existiert nicht mehr. `bahn.expert` antwortet 404 auf allen API-Pfaden,
`v6`/`v5.db.transport.rest` 503 (dauerhaft, kein Ausfall), `db-rest.bendix.dev`
DNS tot. Alle vier BlaBlaCar-Bus-Hosts (`api.idbus.com` v1+v2,
`api.blablacarbus.com`, `booking.blablacarbus.com`) DNS tot - **BlaBlaBus hat
keine offene API mehr**, der Deep-Link ist dort das Ende der Fahnenstange.
Hotellook: alle Endpunkte nginx-404.
Einziger Lichtblick: `dbf.finalrewind.org/journeys` lebt (HTTP 300
`"Ambiguous station name"`) - aber es ist eine Fahrplanquelle, keine Preisquelle,
also derselbe Stand wie Transitous.

**Runde 8 (07.08.2026) - der eigentliche Fund:**
`www.bahn.de/web/api/...` ist der Endpunkt, den die heutige bahn.de-Website
selbst benutzt, inklusive `angebote/fahrplan` und `angebote/tagesbestpreis` -
**das ist die Preisquelle**. Sie ist nicht tot, sie ist *bewacht*: vom GitHub-
Runner kommt `HTTP 403 {"status":"ERROR","code":"OPS_BLOCKED"}`. Das ist eine
IP-/Bot-Sperre gegen Rechenzentren, kein kaputter Pfad. Deshalb liegt der
Endpunkt jetzt als `/bahn/{orte,fahrplan,bestpreis}` im Worker: die offene
Frage ist nur noch, ob **Cloudflares** Ausgangs-IPs durchkommen, wo eine
GitHub-IP es nicht tut. Der Smoke-Test im Deploy-Workflow misst genau das und
lässt den Deploy bewusst *nicht* scheitern, wenn geblockt wird.
Travelpayouts-Hotels **mit** Token: 404/403 auf allen vier Pfaden - das
Hotel-Programm ist im Konto schlicht nicht freigeschaltet, kein Code-Problem.

**Ergebnis der Live-Messung vom Worker aus (07.08.2026) - hier ist die Grenze:**

| Aufruf | vom GitHub-Runner | vom Cloudflare-Worker |
|---|---|---|
| `GET /bahn/orte` (Stationssuche) | 403 OPS_BLOCKED | **200, echte Daten** |
| `POST /bahn/fahrplan` (Preise) | 403 OPS_BLOCKED | 403 |
| `POST /bahn/tagesbestpreis` | 403 OPS_BLOCKED | 403 |

Das ist die entscheidende Beobachtung: Cloudflares Ausgangs-IP ist **nicht**
gesperrt - sonst wäre auch die Ortssuche geblockt. Geschützt ist gezielt der
*Buchungs-/Preispfad*. `X-Correlation-ID` im Format der Website
(zwei UUIDs mit Unterstrich) wurde nachgereicht und ändert nichts.
Damit ist die Sache ausgereizt, was von einem Server aus geht: was noch
fehlt, wäre eine echte Browser-Sitzung samt Cookies und passendem
TLS-Fingerprint - Letzteren kann ein Worker gar nicht setzen, und es wäre
ein bewusstes Umgehen einer Schutzmassnahme. **Nicht weiter probieren.**

Die Route bleibt trotzdem im Worker: `/bahn/orte` liefert heute schon echte
DB-Stationen inklusive `extId` (EVA-Nummer) und Produktliste, und falls die
DB den Preispfad je öffnet, ist es ein Deploy und keine Neuentwicklung. Ein
403 kommt als `blocked: true` zurück, damit die Seite den Grund nennen kann,
statt stumm keinen Bahnpreis zu zeigen.

**Runde 9 (07.08.2026) - die Hotel-Frage ist entschieden, anders als gedacht.**
Runde 8 las sich wie "Hotel-Programm nicht freigeschaltet". Das war eine
Fehldiagnose, und Runde 9 hat sie widerlegt. Aufbau: eine **Kontrollabfrage**
auf dem Flugpfad, von dem wir wissen, dass Token und Konto stimmen, daneben
elf Hotel-Pfade.

- Kontrolle `aviasales/v3/prices_for_dates` → **200 mit echten Daten**.
- Alle elf Hotel-Pfade → **404** (nginx-404, S3 AccessDenied, Go-404),
  mit Token als Header *und* als Query-Parameter, mit und ohne `marker`.

Entscheidend ist, was **nicht** vorkam: kein einziges 401/403 mit
JSON-Begründung. Eine fehlende Freischaltung antwortet mit "keine
Berechtigung", nicht mit "diesen Pfad gibt es nicht". Die alte
Hotellook-API-Familie ist also **abgeschaltet, nicht gesperrt** - ein
Programmbeitritt bei Travelpayouts hätte diese Endpunkte nie zurückgebracht.
Deshalb gibt es im Katalog auch keinen "Beitreten"-Knopf: es gibt nichts
beizutreten, die Hotel-Seite dort vergibt heute Links und Widgets, keine
Preis-API. **Nicht weiter im Konto suchen.**

**Runde 10 (07.08.2026) - welche Hotel-API lebt heute?** Reihenfolge bewusst
umgedreht: erst messen, wer antwortet, dann sich anmelden. Ohne Key ist das
gesuchte Signal **401 mit JSON** (API lebt, vergibt Keys), nicht 200.

| Anbieter | Antwort | Bedeutung |
|---|---|---|
| **LiteAPI v3** (`api.liteapi.travel`) | 401 `{"error":{"code":401,"message":"unauthorized"}}` | **lebt, Keys selbst lösbar** |
| **Hotelbeds APItude Test** | 401 `{"error":"Authorization field missing"}` | **lebt, Test-Keys selbst lösbar** |
| RateHawk / worldota | 401 mit JSON | lebt, braucht Vertrag |
| Booking.com Demand API | 401 | lebt, braucht Partnerschaft |
| Hotellook (Gegenprobe) | 404 nginx | bestätigt tot |

Damit ist **LiteAPI der Weg für Hotels**, falls das Thema wieder aufgegriffen
wird: moderne REST-API, Sandbox- und Produktions-Key ohne Vertrag,
Provisionsmodell. Der Anschluss wäre ein Provider plus eine Worker-Route,
kein Umbau.

**Nachtrag (09.08.2026): „ohne Vertrag" heißt nicht „ohne Kreditkarte."**
Im Konto stehen zwei Schlüssel. Der **Sandbox-Key ist frei**, der
**Production-Key verlangt ein hinterlegtes Zahlungsmittel** („Add Payment
Method"). Das ist kein Abo: LiteAPI verdient an Buchungsprovision, die Karte
ist die Abrechnungshinterlegung. Für dieses Projekt ist die Unterscheidung
trotzdem zweitrangig, denn **wir buchen nichts** – wir zeigen Preise und
verlinken zum Anbieter. Gebraucht wird also nur die *Preisauskunft*, nicht
der Buchungsweg.

Damit stand und fiel alles an einer einzigen, messbaren Frage: **liefert
der Sandbox-Key echte Raten oder Testdaten?** Die Anbieter-Aussagen
widersprechen sich („Sandbox = production" gegen „simulierte Buchungen ohne
echte Daten"), also wird gemessen – `probe-round16.yml`. Ein einzelner
plausibler Betrag beweist nichts; entschieden wird über **Variation**:
dieselben Hotels an fünf verschiedenen Daten/Dauern/Belegungen. Echte Preise
reagieren darauf, erfundene nicht. Kommt überall derselbe Betrag, ist die
Quelle für uns wertlos – ein erfundener Hotelpreis ist schlimmer als gar
keiner.

**Runde 11 (08.08.2026) - db-prices / db-hafas / pyhafas: die Bibliotheken
leben, der Endpunkt dahinter nicht.**
Von aussen kam der Hinweis auf die Community-Projekte `db-prices`,
`db-hafas` und `pyhafas`, die die internen DB-Schnittstellen ansprechen.
Runde 7 hatte nur die *Wrapper* geprüft; der HAFAS-Endpunkt `mgate.exe`
selbst, den diese Projekte **direkt** aufrufen, war nie dran. Nachgeholt -
mit einer **Kontrolle**, ohne die das Ergebnis nicht deutbar gewesen wäre:
die ÖBB fährt dasselbe HAFAS, also wurde dieselbe Anfrageform dorthin
geschickt.

| Ziel | Ergebnis |
|---|---|
| **Kontrolle** `fahrplan.oebb.at/bin/mgate.exe` | **200, `err=OK`, 5 Treffer** ("Wien Hbf (U)" …) |
| `reiseauskunft.bahn.de/bin/mgate.exe` | **DNS existiert nicht** |
| `hafas.db.de/bin/mgate.exe` | DNS existiert nicht |
| `fahrplan.bahn.de/bin/mgate.exe` | DNS existiert nicht |
| `reiseauskunft.bahn.de/bin/query.exe` (db-prices, alt) | DNS existiert nicht |
| `ps.bahn.de` (Sparpreis-Suche, alt) | DNS existiert nicht |
| `v6`/`v5.db.transport.rest` | 503 (wie Runde 7) |

Die Kontrolle ist der Punkt: **identische Anfrage, identisches Client-Profil -
die ÖBB antwortet einwandfrei.** Es liegt also nicht an unserer Anfrage, an
den Zugangsdaten oder am Rechenzentrum. Die DB hat ihr HAFAS schlicht
abgeschaltet; sogar `reiseauskunft.bahn.de` löst nicht mehr auf. Die
genannten Bibliotheken sind echt und funktionierten - ihr Gegenüber gibt es
nicht mehr. Deshalb ist auch `db-rest` dauerhaft 503 und nicht nur gestört.

**Diese Spur ist damit abschliessend erledigt.** Wer sie erneut vorschlägt:
erst obige Tabelle lesen. Der einzige noch lebende DB-Preispfad ist
`www.bahn.de/web/api/angebote/*` - und der ist bewacht (Runde 8).

**Runde 12/13 (08.08.2026) - db-vendo-client: Quelltext gelesen, Ergebnis
unverändert.** Von aussen kam der Hinweis auf `db-vendo-client` und den
Endpunkt `app.vendo.noncd.db.de/mob/angebote/tagesbestpreis`.

*Runde 12 - existiert der Vendo-Host?* Beide Adressfamilien getrennt
abgefragt, mit `www.bahn.de` als Kontrolle:

| Host | A | AAAA |
|---|---|---|
| `www.bahn.de` (Kontrolle) | 23.216.147.196 | 2600:1405:1000:9::17d6:16e5 |
| `app.vendo.noncd.db.de` | – | – |
| `int.vendo.noncd.db.de` | – | – |
| `movas.noncd.db.de` | – | – |

Der Resolver liefert AAAA problemlos (Kontrolle beweist es), die
Vendo-Hosts sind für **beide** Familien NXDOMAIN. Kein IPv6-Thema - die
Namen existieren im öffentlichen DNS nicht. Das `dbnav`-Profil ist für uns
also unerreichbar.

*Runde 13 - was macht das `dbweb`-Profil anders?* Statt weiter Header zu
raten, den Quelltext gelesen. `p/dbweb/base.json`:

```
journeysEndpoint   https://int.bahn.de/web/api/angebote/fahrplan
bestpriceEndpoint  https://int.bahn.de/web/api/angebote/tagesbestpreis
recon              https://int.bahn.de/web/api/angebote/recon
locationsEndpoint  https://int.bahn.de/web/api/reiseloesung/orte
```

**`int.bahn.de`**, nicht `www.bahn.de` - und die Header sind minimal
(`Content-Type`, `Accept`, `Accept-Language`) plus ein *zufälliger*
User-Agent (`randomizeUserAgent`). Beides übernommen, `int.bahn.de` zuerst,
`www.bahn.de` als Ausweichhost, X-Correlation-ID (meine Erfindung) entfernt.

**Live gemessen nach dem Deploy: Ortssuche 200, Preissuche 403 - bei beiden
Hosts.** Damit benutzen wir exakt die Endpunktliste und den Header-Satz des
echten Clients und werden trotzdem abgewiesen. Das deckt sich mit dessen
eigener README, die für `dbweb` "aggressive blocking (IPv4/IPv6)" nennt und
als Alternative ausgerechnet **Transitous** empfiehlt - die Quelle, auf der
dieses Projekt ohnehin steht.

Fazit: die Endpunkte sind richtig und aktuell, die Sperre sitzt auf der
Netzreputation des Rechenzentrums. Von einem Server aus ist das nicht ohne
bewusstes Umgehen zu lösen. **Nicht erneut aufnehmen**, solange sich an der
Sperrpraxis nichts ändert; die Route bleibt im Worker, damit ein künftiger
Test eine Zeile statt einer Neuentwicklung ist.

**Runde 14 (09.08.2026) - der Durchbruch: Heim-IP kommt durch.**
Der Server-Weg ist tot (Cloudflare, GitHub, Ionos-VPS alle 403 OPS_BLOCKED -
die Sperre haengt an der Rechenzentrums-IP, nicht an der Anfrage). Aber vom
**MacBook des Nutzers im Heim-WLAN** liefert `int.bahn.de/web/api/angebote/fahrplan`
auf ein leeres `{}` ein **HTTP 422** (Inhalt unvollstaendig) statt 403 -
also *angenommen und verarbeitet*. Wohn-IPs stehen nicht auf der Sperrliste.

Damit ist der Weg zu echten DB-Live-Preisen: **db-vendo-client lokal beim
Nutzer laufen lassen**, die App holt die Bahnpreise von dort. Aus dem
Quelltext des Projekts (nicht geraten) verifiziert:

- Image: `ghcr.io/public-transport/db-vendo-client`, Port 3000
- `docker run -e DB_PROFILE=dbnav -e USER_AGENT="..." -p 3000:3000 <image>`
- Profil `dbnav` unterstuetzt Preise, `bestprice=true` (Tagesbestpreis,
  nach Preis sortiert) und Tickets
- serviert ueber hafas-rest-api → Routen `/locations`, `/journeys`;
  **CORS ist standardmaessig an**, der Browser darf `http://127.0.0.1:3000`
  direkt lesen, kein Tunnel noetig
- Antwort ist FPTF: `journeys[].price = {amount, currency}` (per Journey),
  plus Legs mit Zeiten/Linien
- Projekt-README **empfiehlt Caching** (HTTP-Proxy-Cache oder
  cached-hafas-client) - wichtig, weil dbnav ~60 Requests/min hat

**Architektur, die gebaut wird (interaktiv, MacBook):** der Browser probt
beim Bahn-Suchen `http://127.0.0.1:3000`; erreichbar → echte Preise +
Bestpreis, `price_known=true`; nicht erreichbar (Handy, Laptop aus) →
unveraendert Transitous-Fahrplan + D-Ticket-Logik + Deep-Link. Nie ein
erfundener Preis, nie ein Bruch ohne die lokale Quelle. Fuer naechtliche
Alarme spaeter ein immer-an-Geraet (Pi) mit derselben Konfiguration.

**Runde 15 (09.08.2026) - ES LÄUFT: echte DB-Live-Preise.**
Live auf dem MacBook des Nutzers gemessen, `int.bahn.de/web/api/angebote/fahrplan`
mit gueltigem Suchkoerper: **HTTP 201, echte Sparpreise** (`"betrag": 39.99`,
`49.99` fuer Berlin->Muenchen). Der Weg steht.

Zwei Dinge mussten stimmen, beide vom Nutzer gemessen:
1. **Wohn-IP** - der VPS/Server bleibt 403, das MacBook zuhause kommt durch.
2. **curl-Fingerabdruck** - db-vendo-client (Node) bekam von *derselben*
   Maschine 403, rohes `curl` 201. Die DB fingerprintet den TLS-/HTTP-Stack;
   curl sieht aus wie ein Browser, Node/Python nicht. Deshalb geht der Weg
   **nicht** ueber db-vendo-client, sondern ueber curl.

**Gebaut:** `bahn-local/server.py` - ein nur-lokaler Python-Stdlib-Server
(kein pip, kein Docker), der die DB per `curl`-Unterprozess fragt und der App
`/health`, `/orte`, `/fahrplan` bereitstellt. CORS offen (nur-lokal,
oeffentliche Fahrplandaten), 5-Minuten-Cache. Antwort-Parser gegen die echte
Struktur getestet: `check_server.py`, 24 checks. Anleitung: `bahn-local/README.md`.

**App-Anbindung (docs/app.js):** `groundOffersFor(route,'train')` probt beim
Suchen `http://127.0.0.1:8899/health` (1,5s Timeout, einmal pro Seitenaufruf
gecacht). Erreichbar -> echte DB-Preise mit `priceSource:'db-live'` und Chip
"🟢 Live-Preis DB". Nicht erreichbar -> unveraendert Transitous-Fahrplan +
D-Ticket. Adresse ueber `localStorage['bahnLocalUrl']` umstellbar (Pi/Tunnel
spaeter, ohne Code-Aenderung). Auch der mixed_return-Zugschenkel laeuft jetzt
ueber `groundOffersFor`, bekommt also live-Preise.
Tests: `ui_bahn_live.py` (9 checks, beide Faelle - Server an *und* aus).

**Runde 16 (09.08.2026) - D-Ticket und Live-Preis zusammengefuehrt.**
Jetzt gilt die D-Ticket-Logik auch fuer live bepreiste Verbindungen - und
wird dort sogar *besser*: weil der Normalpreis bekannt ist, steht nicht mehr
nur "abgedeckt" da, sondern die Ersparnis in Euro
("🎫 mit Deutschland-Ticket 0 € (spart 29,90 EUR)").

Eigene Zuordnung noetig, weil die DB ihre Gattungen anders benennt als
Transitous: `REGIONAL/SBAHN/UBAHN/TRAM/BUS` abgedeckt,
`ICE/EC_IC/IR/SCHIFF` nicht, alles andere (u.a. `ANRUFPFLICHTIG`, wo je
Verbund eigene Regeln gelten) **unentscheidbar** - siehe
`dbTicketCoverage()` in app.js, dieselbe Dreiwertigkeit wie im
Fahrplan-Pfad.

Deutschland-Erkennung ueber **zwei** Merkmale, die beide stimmen muessen:
UIC-Laenderschluessel `U=80` in der Orts-ID *und* eine mit 80 beginnende
EVA-Nummer (beides aus der Live-Antwort abgelesen). Fehlt oder widerspricht
eines, gibt es keine Aussage. Die Richtung des Irrtums ist bewusst gewaehlt:
lieber ein fehlender Hinweis als ein falsches "0 EUR". Tests dazu in
`ui_dticket_live.py` (23 checks), inklusive der teuren Irrtuemer - ICE wird
nicht kostenlos, Auslandsfahrt wird nicht kostenlos.

**Offen / Verfeinerungen (nicht dringend):**
- Bestpreissuche (`/angebote/tagesbestpreis`) ist im Server noch nicht als
  Route; `/fahrplan` liefert bereits `angebotsPreis` pro Verbindung, das deckt
  den Kernbedarf.
- Safari blockt teils `http://localhost` von einer https-Seite; Chrome nicht.
  Im README vermerkt.
- Dauerbetrieb fuer Alarme = server.py auf einem immer-an-Geraet (Pi).

## Hotels: gelöst (09.08.2026) - der freie Sandbox-Key liefert echte Raten

**Probe 16 - sind die Preise echt?** Ein einzelner plausibler Betrag beweist
nichts, deshalb wurde über *Variation* entschieden: dieselben drei Berliner
Hotels über fünf Abfragevarianten.

| Variante | Meliá | NH Collection | Steigenberger |
|---|---|---|---|
| 30 Tage, 1 Nacht, 2 Erw. | 260,45 | 284,68 | 245,04 |
| Nachbartag | 253,27 | 223,06 | 253,49 |
| 3 Nächte | 958,08 | 841,02 | 659,73 |
| 1 Erwachsener | 252,06 | 278,45 | 252,57 |
| 240 Tage Vorlauf | 110,45 | 103,31 | 129,81 |

Fünf von fünf verschieden, bei allen drei Hotels. Gegenprobe: dieselbe
Anfrage ohne Schlüssel → 401, die Messung misst also wirklich den Schlüssel.
**Testdaten hätten fünfmal dieselbe Zahl geliefert.** Damit ist die
Kreditkartenfrage erledigt: der Production-Key ist der *Buchungsweg*, und
wir buchen nichts.

**Probe 17 - welcher der drei Beträge ist der Preis?** Das war die
gefährlichste offene Stelle, und Runde 16 hatte sie mit einem `ODER`
überdeckt (`offerRetailRate` *oder* `suggestedSellingPrice`).

| Feld | Betrag | Bedeutung |
|---|---|---|
| `offerRetailRate.amount` | 260,45 | **was der Reisende zahlt** |
| `suggestedSellingPrice.amount` | 333,13 | Preis desselben Zimmers, `source: booking.com` |
| `offerInitialPrice.amount` | 260,45 | Preis vor Rabatt |
| `retailRate.taxesAndFees[]` | City Tax 19,56 **`included: false`**, VAT 17,04 `included: true` | |

Zwei Folgen, beide im Code festgeschrieben und getestet:

1. **260,45 ist nicht der Preis der Nacht - 280,01 ist es.** Die City Tax
   fehlt im genannten Betrag. Deshalb sucht `trimHotelRates` (Worker) und
   `_cheapest_offer` (Python) das günstigste Zimmer nach *Gesamtpreis*: eine
   Rate, die eine Gebühr verschweigt, würde sonst gegen eine gewinnen, die
   sie enthält - genau falsch herum.
2. **Der booking.com-Vergleich ist geschenkt.** LiteAPI nennt ihn samt
   Herkunft, also ist die Ersparnis belegt statt geschätzt.

**Probe 18 - was weiß die Quelle über ein Hotel?** Gefragt, weil beim Bau
der Worker-Route aus drei gemessenen Feldern stillschweigend sieben
angenommene geworden waren (der `sollzeit`-Fehler). Ergebnis: `stars`,
`rating` (0-10), `reviewCount`, `address`, `zip`, `chain`, `latitude`,
`longitude`, `thumbnail` sind alle befüllt - die Annahme stimmte, ist aber
jetzt gemessen. **Ausstattung dagegen nicht:** `facilityIds` sind nackte
Zahlen (`[47, 107, 2]`) ohne Namenstabelle.

Daraus folgt die dritte, weitreichendste Änderung: **unbekannt ist nicht
nein.** `_meets_hotel_constraints` (Python) und `meetsHotelPrefs` (JS)
schließen nur noch bei einem ausdrücklichen `false` aus; die
Ausstattungsfelder in `models.py` sind auf `Optional[bool] = None`
umgestellt. Vorher hätte ein Haken bei „WLAN" **jedes echte Hotel**
aussortiert - und das Ergebnis hätte ausgesehen wie „dort gibt es keine
Hotels". Was offen bleibt, sagt die App am Angebot dazu
(`unverifiedHotelPrefs`), damit aus „ungeprüft" nie stillschweigend
„erfüllt" wird. `hotel_comfort_score` wertet Schweigen als Mittelwert, nicht
als Mangel - sonst landete jedes echte Hotel hinter jedem erfundenen.

**Bekannte Grenze, ehrlich benannt: die Auswahl kann eine Steuer nicht
erzwingen, die nicht dasteht.** Der Live-Rauchtest nach dem Deploy lieferte
für alle drei Berliner Hotels `extraTax = 0`, während Probe 17 an derselben
Strecke eine City Tax von 19,56 EUR zeigte - schlicht, weil diesmal andere
Raten gewonnen haben. Daraus folgt eine Frage, die die Daten nicht
beantworten: Ist eine Rate ohne ausgewiesene Steuer wirklich
steuerfrei/all-inclusive, oder schweigt sie nur? Wenn Letzteres, bevorzugt
„günstigster Gesamtpreis" systematisch die schweigsame Rate.

Bewusst **nicht** wegoptimiert, weil jede Gegenmaßnahme geraten wäre. Was
stattdessen gilt: Die App behauptet nie, es kämen keine Kosten mehr dazu -
der Hinweis „inkl. X Steuer vor Ort" erscheint nur, wenn eine Steuer
ausgewiesen ist, und Schweigen bleibt Schweigen. Wer das verbessern will,
bräuchte zuerst eine Messung, ob LiteAPI je Rate zuverlässig
`taxesAndFees` füllt - nicht eine Heuristik.

Offen geblieben (kein Blocker): `/data/facilities` könnte die
`facilityIds` in Namen auflösen und damit WLAN/Parkplatz/Pool beantwortbar
machen. Nicht gemessen, deshalb nicht gebaut.

## VPS-Frage: beantwortet und vorbereitet (09.08.2026)

„Alles auf den VPS, inklusive DB-Preise?" - **direkt: nein, gemessen.**
Derselbe curl, der von der Wohn-IP 201 bekommt, bekommt vom Ionos-VPS
`403 OPS_BLOCKED` (Nutzer-Experiment, Runde 13). Die Sperre haengt an der
IP-Herkunft.

Was geht: **VPS als https-Front, Heimrechner/Pi als Ausgang** ueber
WireGuard/Tailscale-Tunnel - nur die /bahn-Anfragen laufen durch den Tunnel
und verlassen das Internet ueber die Wohn-IP. Kauft Bahn-Preise von
ueberall (auch Handy unterwegs), eine https-Adresse ohne Mixed-Content und
Bahn-Preisalarme rund um die Uhr. Loest nicht: das Heimgeraet muss an sein.

Die App ist seit Build 2026-08-09-17 darauf vorbereitet:
`bahnLocalCandidates()` akzeptiert die eigene Herkunft auch ueber https
(nur github.io ist ausgenommen; die /health-Probe prueft ohnehin), und
`normaliseLocalUrl()` klebt an https-Adressen kein `:8899` mehr an.
Architektur-Skizze in bahn-local/README.md. Residential-Proxy-Dienste
(fremde Wohn-IPs mieten) sind benannt und bewusst verworfen.

## Deutschland-Ticket: der einzige echte Bahnpreis, den wir bekommen

Die DB gibt keine Tarife heraus (siehe Messtabelle oben). Für eine grosse
Klasse von Fahrten muss sie das auch nicht: das Deutschland-Ticket deckt den
gesamten Nahverkehr in Deutschland ab. Besteht eine Verbindung **nur** aus
Nahverkehrsabschnitten und bleibt sie **in Deutschland**, zahlt ein
Ticketinhaber nichts extra. Das folgt aus dem Fahrplan allein - es ist eine
Tatsache, keine Schätzung. Damit wird aus unserer reinen Fahrplanquelle
(Transitous) für genau diese Fahrten eine echte Preisaussage.

Implementiert doppelt und wortgleich: `dTicketCoverage()` in `docs/app.js`,
`d_ticket_coverage()` in `providers/transitous.py`. **Beide zusammen halten.**

Dreiwertig, und das ist der Kern:

| Ergebnis | wann | Folge |
|---|---|---|
| `true` | alle Abschnitte Nahverkehr, Start+Ziel in Deutschland | mit Haken: Preis 0, `price_known=True` |
| `false` | mindestens ein ICE/IC/EC/Nachtzug/Fernbus | nie 0, Preis bleibt unbekannt |
| `null` | Fahrt verlässt Deutschland **oder** unbekannte Gattung | nie 0, kein Chip, keine Aussage |

`null` ist bewusst **nicht** `false`: fehlendes Wissen ist keine Verneinung -
dieselbe Unterscheidung, die `price_known` bei Preisen trifft. Und die
Ausschlussliste ist explizit aufgezählt statt als "nicht in der
Abdeckungsliste" abgeleitet, damit eine unbekannte Gattung aus einem neuen
Feed `null` ergibt statt stillschweigend als abgedeckt zu gelten.

Ohne Haken (`has_deutschland_ticket`) bleibt der Preis **unbekannt** und die
Abdeckung ist nur ein Hinweis - wer das Ticket nicht hat, für den kostet die
Fahrt sehr wohl etwas. Der gefährliche Fehler wäre ein "0 €" an einem ICE
oder an einer Auslandsfahrt; genau darauf zielen die meisten Tests
(`tests/test_transitous.py`, `ui_dticket.py`).

## Was diese App kann, das die grossen Portale nicht koennen

Der Vorsprung liegt nicht in der Preisabdeckung - dort gewinnt Skyscanner mit
bezahlten GDS-Zugaengen. Er liegt in dem, was ein *persoenliches* Werkzeug
darf und ein Portal nicht:

- **Modi gegeneinander in einer Liste.** Flug, Bahn und Bus nach denselben
  Kriterien gerankt. Jedes Portal verkauft einen Modus und rankt entsprechend.
- **`mixed_return`: Hin- und Rueckweg unabhaengig.** Hin fliegen, zurueck Bus.
  Zwei Fallen dabei, beide waren zuerst falsch: die Rueckfahrt muss
  *Ziel -> Start* gesucht werden, und sie liegt auf dem Rueckreisedatum, das
  die normalen Pools (aus dem Hinreise-Fenster gebaut) nicht abdecken. Siehe
  `legsFor()` in app.js.
- **Umkreis fuer Start *und* Ziel**, Flughaefen wie Bahnhoefe. Fuer Bahnhoefe
  gibt es bewusst keine Koordinatentabelle: die Flughafentabelle schlaegt nur
  Kandidaten vor, aufgeloest wird ueber Transitous (echte Haltestelle, echte
  Koordinaten), gemessen wird an denen. Eine gebastelte Tabelle haette den
  angezeigten Umweg um zig Kilometer danebengelegt.
- **Deal-Feeds** beantworten die Frage, die keine Preis-API kann: *wo ist
  gerade etwas absurd billig*.

## Spar-Berater: die Schwellen und warum sie so hoch sind

`SAVING_RULES` in `docs/app.js` entscheidet, ob ein Kompromiss ueberhaupt
vorgeschlagen wird. Die Zahlen sind kein Bauchgefuehl, sondern eine Ansage
des Nutzers: **eine zusaetzliche Reisestunde ist Mindestlohn wert.**

| Last | noetige Ersparnis |
| --- | --- |
| je zusaetzlicher Stunde | 15 EUR |
| je zusaetzlichem Umstieg | 10 EUR |
| anderer Reisetag | 40 EUR |
| gar keine Last (guenstiger *und* gleich schnell) | 5 EUR |

Die Regeln werden mit `Math.max` kombiniert, nicht addiert - es zaehlt die
groesste Zumutung, nicht ihre Summe. Wer das aendern will, sollte vorher
`ui_savings.py` lesen: dort steht zu jeder Kategorie ein Paar aus einem Fall,
der kommen muss, und einem, der schweigen muss. Genau dieses Paar macht die
Schwelle ueberhaupt pruefbar.

Wichtig: **auch der Spar-Trick (Fahrkarte teilen) faellt unter dieselbe
Regel.** Er hatte anfangs eine eigene, laxere Schwelle (3 EUR, egal wie viel
Mehrzeit) - das war inkonsistent und haette 4-EUR-Vorschlaege fuer drei
Stunden Umweg erzeugt. `findSplitTicketOffers` ruft jetzt `savingIsWorthIt`
mit `transfers: 1` auf, weil das Teilen immer einen Umstieg kostet.
`SPLIT_MIN_SAVING_EUR` ist nur noch ein billiger Vorfilter, bevor die
Mehrzeit ueberhaupt bekannt ist.

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
