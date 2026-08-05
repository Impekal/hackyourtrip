# HackYourTrip

Bot/Webapp, der Flug-, Bahn-, Bus- und Hotel-Angebote vergleicht, dich per
Telegram/E-Mail auf Preisverfall und mögliche Fehlerpreise hinweist und dir
auf einem Dashboard die besten aktuellen Optionen pro Strecke zeigt.

> **Stand v1:** Flug läuft auf **echten, aktuell beobachteten Preisen über
> die Travelpayouts (Aviasales) Data API**, sobald `TRAVELPAYOUTS_TOKEN`
> gesetzt ist (siehe "Travelpayouts einrichten" unten - kostenloses
> Selfservice-Konto, kein Vertrag). Amadeus wird als zweite echte Quelle
> weiterhin unterstützt, aber nur für Enterprise-Zugänge - die kostenlose
> Amadeus-Self-Service-API wurde im Juli 2026 abgeschaltet. Ohne eine dieser
> beiden Zugangsdaten - und Bahn/Bus/Hotel immer - läuft es auf
> **Mock-Providern** (siehe "Warum Mock-Daten?"). Die komplette Pipeline
> (Einstellungen, Ranking, Empfehlungen, Alerts, Dashboard, Cronjob)
> funktioniert so oder so Ende-zu-Ende. Nächster Schritt: Bahn/Bus/Hotel
> ebenfalls durch echte APIs ersetzen (Roadmap unten).

## Was der Bot kann

- **10 Such-Modi** (im Suche-Tab als eigene Reiter, weil z.B. bei "nur Hotel"
  eine Anreise irrelevant ist - jeder Modus zeigt nur die Felder, die für ihn
  Sinn ergeben): Flug, Bahn, Bus, Hotel, Bahn/Bus, Flug/Bahn, Flug/Bus (jeweils
  "was ist besser"), Flug+Hotel, Bahn+Hotel, Bus+Hotel.
- **Einstellungen pro Strecke** (`config/routes.yaml`): Start/Ziel, Datum +
  Flexibilität in Tagen davor/danach, Mindest-/Max-Aufenthalt (für Hotel),
  Budget, Währung, maximale Reisezeit, Priorität (`cheapest` / `fastest` /
  `best_value`), Gepäck (Handgepäck-only, Anzahl/Gewicht Koffer), Bahn-Extras
  (BahnCard 25/50/100, Deutschlandticket), ob Low-Cost-Airlines ok sind.
- **Hotel-Kriterien** (das volle Trivago-Filterset, siehe `HotelPref` in
  `traveldeals/models.py`): Min. Sterne, Mindestbewertung, max. Entfernung
  zu Zentrum/Bahnhof/Flughafen, Unterkunftsart (Hotel/Apartment/Hostel/
  Resort/B&B/Gästehaus/Villa), Verpflegungsstufe (Frühstück/Halb-/
  Vollpension/All-Inclusive), plus 27 einzelne Ausstattungsmerkmale (WLAN,
  Parkplatz, Klimaanlage, Pool, Fitnessraum, Spa, Sauna, Whirlpool,
  Restaurant, Bar, Zimmerservice, 24h-Rezeption, Wäscheservice,
  Business-Ausstattung, Flughafentransfer, Aufzug, Balkon/Terrasse, Küche,
  Strandnähe, Barrierefreiheit, E-Ladestation, Fahrradverleih, Babysitting,
  Nichtraucher, Familienzimmer, Haustiere erlaubt, kostenlose Stornierung) -
  fließen nicht nur als Filter, sondern auch als Komfort-Score ins
  `best_value`-Ranking ein (siehe unten).
- **Transport-Kriterien** (`TransportPref`): nur Direktverbindungen, WLAN an
  Bord, Steckdosen, Mindest-Pünktlichkeit, Beinfreiheit (mode-abhängig
  normalisiert) - ebenfalls Filter *und* Komfort-Score. Zusätzlich zur
  Tage-Flexibilität (`flex_days_before/after`, welche *Tage* infrage kommen)
  gibt es bei Bahn/Bus/Flug eine **Uhrzeit-Flexibilität**: bevorzugte
  Abfahrtszeit + Zeitfenster in Stunden/Minuten (z.B. "09:00 ± 90 Minuten"),
  zirkulär über Mitternacht hinweg berechnet. Angebote außerhalb des
  Fensters werden herausgefiltert - auch die "später fahren spart X€"-
  Empfehlung schlägt nie eine Zeit außerhalb dieses Fensters vor.
- **Von/Nach-Autocomplete:** Stadt eintippen, passenden Flughafen/Bahnhof
  auswählen - wie auf gängigen Reiseplattformen. Flug/Hotel nutzen die
  echte, öffentliche Travelpayouts-Places-API (`autocomplete.travelpayouts.com`,
  kein Token nötig), Bahn/Bus eine kuratierte statische Liste großer
  DACH-/europäischer Bahnhöfe (dafür ist keine freie API bekannt).
- **Hin- und Rückreise:** bei Flug/Bahn/Bus (und deren "was ist besser"-Kombis)
  lässt sich zwischen Nur-Hinfahrt und Hin+Rück wählen (`round_trip` +
  `return_date` in `RoutePreference`). Bei echten Travelpayouts-Daten liefert
  die API dafür einen kombinierten Gesamtpreis für beide Strecken (kein
  client-seitiges Aufsummieren nötig); die Mock-Provider bilden das mit einer
  synthetisierten Rückreise nach demselben Prinzip nach. Reine Hotel-Modi
  brauchen das nicht (Checkin+Nächte bilden die Aufenthaltsdauer schon ab).
- **Komfort-Score im `best_value`-Ranking:** `best_value` ist nicht mehr nur
  Preis/Dauer, sondern `50% Preis + 25% Dauer + 25% Komfort` (Gewichte in
  `engine.py` anpassbar) - eine 5€ teurere, aber deutlich komfortablere
  Option kann so gewinnen, wenn der Rest der Angebote eine echte Preisspanne
  hat (bei nur 2 Kandidaten verzerrt Min-Max-Normalisierung sonst stark).
- **Smarte Empfehlungen** (siehe `traveldeals/engine.py`):
  - 🕐 "1h später fliegen/fahren spart X€" - vergleicht alle Abfahrten am
    selben Tag.
  - 🎒 "Nur Handgepäck statt Koffer spart X€" - wenn die Gepäckgebühr einen
    nennenswerten Anteil des Preises ausmacht.
  - 💱 Preis-Umrechnung in USD/GBP bei internationalen Flügen (informativ;
    echte "in anderer Landeswährung buchen"-Ersparnis prüft v1 noch nicht,
    siehe Roadmap).
  - 🔥 Fehlerpreis-Verdacht / 📉 Preis gefallen - basierend auf der
    Preishistorie (`data/pricehistory.json`), nicht auf einem einzelnen Wert.
- **Alerts:** Telegram-Bot, E-Mail (SMTP), und ein statisches Dashboard
  (`docs/index.html`, per GitHub Pages hostbar) - alle drei gleichzeitig
  nutzbar, jeder Kanal ist optional und ohne Zugangsdaten einfach inaktiv.
- **Automatisierung:** `.github/workflows/check-deals.yml` lässt den Bot
  alle 3 Stunden per GitHub Actions laufen - kein eigener Server nötig.

## Zwei Ansichten auf `docs/index.html`

- **🔍 Suche** - interaktive Deal-Plattform-artige Suche direkt im Browser:
  10 Modus-Reiter (Flug/Bahn/Bus/Hotel/Kombis), jeweils nur mit den dazu
  passenden Feldern (z.B. kein "Von" im Hotel-Tab), Ergebnisse erscheinen
  sofort, weil `docs/app.js` dieselbe Mock-Provider- und Ranking-Logik
  (inkl. Komfort-Score und Hotel-/Transport-Filtern) wie `traveldeals/`
  clientseitig in JavaScript nachbildet. Für Flüge lässt sich das auf echte
  Travelpayouts-Preise umstellen, siehe "Live-Suche mit echten Preisen"
  unten - ohne dieses (optionale) Setup läuft alles auf Mock-Daten, ganz
  ohne Server. Kein Fehlerpreis/Preisfall hier, weil das eine echte
  Preishistorie über die Zeit braucht, die eine Browser-Suche nicht hat.
  Am Ende lässt sich die Suche als YAML-Block für `config/routes.yaml`
  kopieren, um sie in echte, dauerhafte Alerts zu verwandeln.
- **🔔 Meine Alerts** - das bisherige Dashboard: liest `docs/data/deals.json`,
  das Ergebnis des letzten `traveldeals.cli check`-Laufs (lokal oder per
  GitHub-Actions-Cron), inklusive Fehlerpreis-/Preisfall-Erkennung, weil das
  auf echter (wenn auch mit Mock-Preisen gefüllter) Historie basiert.

## Architektur

```
traveldeals/
  models.py         RoutePreference, Offer, TripOption, Enums
  config.py         lädt config/routes.yaml
  providers/
    base.py         Provider-Interface (search(route) -> list[Offer]) + date_candidates()
    mock.py         deterministische Fake-Angebote (v1, siehe unten)
    travelpayouts.py echter Flug-Provider (Travelpayouts Data API, empfohlen)
    amadeus.py      echter Flug-Provider (Amadeus API, nur Enterprise-Zugang)
    real.py         Stubs für DB/FlixBus/Booking - noch nicht implementiert
  engine.py         DealEngine: sammelt Angebote, baut Kombis, filtert
                     (Budget/Dauer/Low-Cost), rankt (cheapest/fastest/
                     best_value), hängt Empfehlungen an
  pricehistory.py   JSON-Preishistorie je Strecke+Modus -> Preisfall/Fehlerpreis
  currency.py       Wechselkurse (live via frankfurter.app, sonst Fallback-Tabelle)
  notifiers/        Telegram, E-Mail (SMTP), Konsole
  cli.py            `python -m traveldeals.cli check` - der komplette Lauf
docs/
  index.html        Tabs "Suche" (live) und "Meine Alerts" (Cron-Ergebnis)
  app.js            JS-Port von Mock-Providern + Ranking fürs Suche-Tab,
                     plus Fetch-Logik fürs Alerts-Tab und optional den
                     Live-Preis-Proxy (PROXY_URL)
data/               Preishistorie (wird vom Cronjob committet)
.github/workflows/  Scheduled Job, der `check` laufen lässt
worker/             Optionaler Cloudflare-Worker-Proxy, versteckt den
                     Travelpayouts-Token fürs Suche-Tab (siehe unten)
```

**Warum Mock-Daten?** Echte Preisvergleiche brauchen pro Modus eine reale
Datenquelle, und die sind fast alle kostenpflichtig oder erfordern ein
Partner-Konto (siehe Roadmap) - Flug ist die Ausnahme, siehe unten. Damit
trotzdem sofort die komplette Logik - Einstellungen, Ranking nach
`cheapest`/`fastest`/`best_value`, alle Empfehlungs-Regeln, Alert-Versand,
Dashboard, Cronjob - steht und getestet werden kann, generiert
`providers/mock.py` deterministische, aber plausible Angebote (inkl.
gelegentlich einem künstlichen "Fehlerpreis" zur Demo). Jeder verbleibende
Mock-Provider (Bahn/Bus/Hotel) hat in `providers/real.py` ein Gegenstück, das
nur noch die echte API anbinden muss - die Schnittstelle (`Provider.search`)
bleibt gleich.

## Travelpayouts einrichten (echte Flugpreise, empfohlen)

1. Kostenloses Konto auf [travelpayouts.com](https://www.travelpayouts.com),
   im Account-Bereich den API-Token kopieren (kein Vertrag, keine Freischaltung nötig).
2. Lokal: in `.env` (aus `.env.example` kopiert) `TRAVELPAYOUTS_TOKEN` eintragen.
3. Für den GitHub-Actions-Cron: als Repo-Secret hinterlegen (Settings ->
   Secrets and variables -> Actions) - `check-deals.yml` reicht ihn automatisch durch.
4. Ohne diesen Wert läuft `TravelpayoutsFlightProvider.search()` einfach mit
   `[]` weiter (kein Fehler) und `cli.py` fällt automatisch auf Amadeus
   (falls konfiguriert) oder sonst `MockFlightProvider` zurück - kein
   Code-Umbau nötig, um zwischen den dreien zu wechseln.

**Was die Daten wirklich sind:** Der Endpunkt `v1/prices/cheap` liefert den
günstigsten kürzlich für diese Strecke gefundenen Ticketpreis (von Aviasales
zwischengespeichert) - echte Preise, aber kein Live-Suchergebnis für exakt
heute. Er liefert außerdem **keine** Ankunftszeit/Flugdauer, nur Preis,
Airline, Abflugzeit und Anzahl Umstiege (`transfers`).

Für die Reisezeit gilt deshalb (`providers/geo.py`):
- **Direktflug (`transfers: 0`):** Dauer wird aus der Großkreis-Distanz
  zwischen den beiden Flughäfen geschätzt (Distanz ÷ 750 km/h + 30 Min.
  Zuschlag für Rollen/Start/Landung) - eine Näherung, aber ohne Umstieg
  gibt es nichts, was diese Schätzung verfälschen könnte.
- **Verbindung mit Umstieg (`transfers >= 1`):** Dauer bleibt bewusst
  unbekannt (`0.0`) - wie lange ein Umstieg dauert, hat nichts mit der
  Distanz Start-Ziel zu tun, eine Schätzung wäre nur eine erfundene Zahl
  mit Anschein von Genauigkeit.
- In beiden Fällen unbekannter Flughafen (nicht in der Tabelle in
  `geo.py`): ebenfalls `0.0`.

Die Engine behandelt `duration_hours == 0.0` genau wie bei Hotel-Angeboten
(siehe `engine._meets_hard_constraints`) - "maximale Reisezeit" greift dann
einfach nicht, statt falsch zu filtern.

**Warum nicht Amadeus?** Die kostenlose Amadeus-Self-Service-API wurde am
17. Juli 2026 abgeschaltet (nur noch Enterprise-Verträge). `providers/amadeus.py`
funktioniert weiterhin und `cli.py` nutzt es automatisch, falls
`AMADEUS_API_KEY`/`AMADEUS_API_SECRET` gesetzt sind - aber neu kommt man an
solche Zugangsdaten nur noch über ein Enterprise-Konto, nicht per
Selfservice-Anmeldung.

## Live-Suche mit echten Preisen (Cloudflare-Worker-Proxy)

Der **Suche**-Tab läuft komplett im Browser der Besucher:innen (`docs/app.js`)
- er kann deshalb nie den echten Travelpayouts-Token selbst halten, sonst
könnte ihn jeder über die Browser-Devtools auslesen. Ohne weiteres Setup
bleibt die freie A-nach-B-Suche deshalb auf Mock-Daten.

Um dort trotzdem echte Preise für beliebige Strecken zu bekommen, gibt es
`worker/` - einen minimalen, kostenlosen Cloudflare-Worker-Proxy, der den
Token serverseitig versteckt und Anfragen an `v1/prices/cheap` weiterreicht.

### Deploy ohne CLI/Terminal (empfohlen)

`.github/workflows/deploy-worker.yml` deployt den Worker automatisch bei
jedem Push - du musst nur zwei Werte aus dem Cloudflare-Dashboard kopieren,
genau wie bei den anderen Secrets oben:

1. Kostenloses Konto auf [dash.cloudflare.com](https://dash.cloudflare.com).
2. **API-Token erstellen:** Profil-Icon (oben rechts) -> *My Profile* ->
   Tab *API Tokens* -> *Create Token* -> Vorlage **"Edit Cloudflare
   Workers"** -> *Continue to summary* -> *Create Token* -> Wert kopieren
   (wird nur einmal angezeigt).
3. **Account-ID kopieren:** *Workers & Pages* im linken Menü -> die
   Account-ID steht rechts auf der Übersichtsseite.
4. Beide Werte als Repo-Secrets hinterlegen (Settings -> Secrets and
   variables -> Actions): `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
   `TRAVELPAYOUTS_TOKEN` hast du schon (wird automatisch wiederverwendet,
   um den Worker-internen Token zu setzen - nichts doppelt eintragen).
5. Push nach `main` (oder Actions-Tab -> *Deploy proxy worker* -> *Run
   workflow*) - die Action deployt den Worker und setzt sein
   `TRAVELPAYOUTS_TOKEN`-Secret automatisch.
6. Im Log dieses Workflow-Laufs steht die `*.workers.dev`-URL - die einmalig
   in `docs/app.js` in die Konstante `PROXY_URL` eintragen (Zeile mit
   `const PROXY_URL = '';`) und committen.

### Alternative: Deploy per CLI

```bash
cd worker/
npm install
npx wrangler login
npx wrangler secret put TRAVELPAYOUTS_TOKEN   # denselben Token wie oben einfügen
npx wrangler deploy
```
Ausgegebene URL wie oben in `PROXY_URL` eintragen.

---

Ohne gesetzte `PROXY_URL` - oder wenn der Proxy mal nicht erreichbar ist -
fällt die Suche automatisch auf Mock-Daten zurück, es gibt also keinen
kaputten Zustand dazwischen.

**Warum ein eigener Proxy und nicht direkt der Cronjob/die Watchlist?**
Die Watchlist (`ROUTES_YAML_CONTENT`) ist für Strecken, die du dauerhaft im
Hintergrund beobachten willst (mit Preishistorie, Fehlerpreis-Erkennung,
Telegram/E-Mail-Alerts). Der Proxy ist für spontanes Suchen "wonach mir
gerade ist" - beides nutzt denselben Travelpayouts-Token, aber für zwei
unterschiedliche Zwecke.

**Quota-Schutz:** Weil die Suche-Seite öffentlich ist, cached der Worker
Antworten für dieselbe Strecke+Datum+Währung serverseitig ca. 1 Stunde
(Cloudflare Cache API), damit nicht jeder Seitenbesuch einzeln aufs
Travelpayouts-Kontingent geht. Für zusätzlichen Schutz gegen Missbrauch
kann man im Cloudflare-Dashboard optional eine Rate-Limiting-Regel
hinzufügen (im kostenlosen Plan enthalten).

**Grenzen:** Die Flugdauer-Schätzung für Direktflüge (`docs/app.js`,
`estimateDirectFlightDurationHours`) ist derselbe Ansatz wie auf der
Python-Seite (`providers/geo.py`) - bei Umstiegen bleibt die Dauer bewusst
unbekannt, siehe "Was die Daten wirklich sind" oben.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # inkl. pytest

cp config/routes.example.yaml config/routes.yaml   # eigene Strecken eintragen
cp .env.example .env                                # optional: Telegram/E-Mail

python -m traveldeals.cli list-routes
python -m traveldeals.cli check       # schreibt docs/data/deals.json + Alerts
pytest                                # Tests
```

Dashboard lokal ansehen: `python -m http.server -d docs 8000` und
`http://localhost:8000` öffnen.

### Telegram- und E-Mail-Alerts einrichten

Siehe `.env.example` für die genauen Schritte (Telegram: `@BotFather`, dann
`getUpdates` für die Chat-ID; E-Mail: normale SMTP-Zugangsdaten, z.B.
Gmail-App-Passwort). Ohne Zugangsdaten läuft `check` trotzdem, nur die
Konsolen-Ausgabe ist dann aktiv.

### GitHub-Actions-Cronjob aktivieren

Wichtig: **GitHub führt geplante (`schedule`) Workflows nur für die Version
aus, die im Default-Branch liegt** (hier: `main`). Auf einem Feature-Branch
lässt sich der Job nur manuell über den "Run workflow"-Button im Actions-Tab
starten, bis der Branch gemerged ist.

Da dieses Repo öffentlich ist, wird `config/routes.yaml` bewusst **nicht**
eingecheckt (`.gitignore`), damit private Reisepläne nicht öffentlich
sichtbar sind. Für den automatischen Lauf:

1. Repo-Settings -> Secrets and variables -> Actions -> "New repository secret"
2. Name `ROUTES_YAML_CONTENT`, Wert = kompletter Inhalt deiner `routes.yaml`
3. Optional zusätzlich: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SMTP_HOST`,
   `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `SMTP_TO`

Der Workflow schreibt das Secret zur Laufzeit nach `config/routes.yaml`
(nie committet), führt `check` aus und committet nur die Ergebnis-Dateien
(`data/pricehistory.json`, `docs/data/deals.json`) zurück, damit das
Dashboard aktuell bleibt und die Preishistorie über die Zeit wächst.

## Roadmap: echte Datenquellen anbinden

Ziel ist, `providers/mock.py` Modus für Modus durch echte Adapter zu
ersetzen (Interface bleibt gleich, s.o.):

- **Flug:** ✅ erledigt - `providers/travelpayouts.py` (siehe "Travelpayouts
  einrichten" oben; Direktflug-Dauer wird über `providers/geo.py` geschätzt,
  Umstiege bleiben unbekannt statt geraten), `providers/amadeus.py` als
  Alternative für Enterprise-Zugänge. Möglicher nächster Schritt: echte
  Dauer auch für Verbindungen mit Umstieg bekommen - Travelpayouts hat dafür
  laut Doku einen GraphQL-Endpunkt mit `trip_duration`-Feld
  (`api.travelpayouts.com/graphql/v1/query`, `prices_one_way`-Query), dessen
  genaues Schema sich aber nicht zuverlässig verifizieren ließ (Doku-Seite
  blockiert automatisiertes Abrufen) - deshalb hier nicht spekulativ gegen
  ein ungetestetes Schema implementiert. Alternativ: Duffel im Test-Modus
  (kostenlos, aber Fake-Sandbox-Daten) oder ein Kiwi-Tequila-Partnerzugang
  (mittlerweile nur noch auf Anfrage, kein offenes Selfservice mehr).
- **Bahn:** kein offenes Preis-API von der DB; `db-vendo-client` (Community,
  inoffiziell) oder ein kommerzieller Distributor wie Trainline Partner API.
- **Bus:** FlixBus hat kein offenes Self-Serve-API, nur ein Partnerprogramm.
- **Hotel:** Booking.com Affiliate Partner Program oder Trivago Publisher
  Program - beide erfordern eine Bewerbung/Freischaltung.
- **Multi-Währungs-Preisvergleich (echt):** aktuell nur informative
  Umrechnung (`currency.py`). Eine echte Prüfung "günstiger über die
  US-Seite gebucht" bräuchte länderspezifische Preisabfragen (unterschiedliche
  Locale/IP) - das ist der nächste sinnvolle Ausbauschritt, sobald ein echter
  Flug-Provider angebunden ist.
- **Mehrbenutzer-Weboberfläche:** `config/routes.yaml` per Hand editieren ist
  die einfachste Lösung für v1. Für ein echtes Formular mit Login würde sich
  z.B. Supabase (Postgres + Auth, kostenloser Free-Tier) anbieten statt einer
  reinen YAML-Datei.
- **LLM-gestützte Kurzbegründung (optional, z.B. Gemini):** Ranking/Preise
  bleiben bewusst regelbasiert (deterministisch, testbar, kein API-Kosten-
  Risiko) - ein LLM würde hier nicht rechnen, sondern höchstens eine
  freitextliche Erklärung ("warum Option 3 die beste Wahl ist") oder fuzzy
  Wünsche wie "ruhige Lage" einordnen, die sich schlecht in feste Filter
  pressen lassen. Bisher nicht umgesetzt.
