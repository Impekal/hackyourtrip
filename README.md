# HackYourTrip

Bot/Webapp, der Flug-, Bahn-, Bus- und Hotel-Angebote vergleicht, dich per
Telegram/E-Mail auf Preisverfall und mögliche Fehlerpreise hinweist und dir
auf einem Dashboard die besten aktuellen Optionen pro Strecke zeigt.

> **Stand v1:** Alle Preisdaten kommen aus **Mock-Providern** (siehe
> "Warum Mock-Daten?" unten) - die komplette Pipeline (Einstellungen, Ranking,
> Empfehlungen, Alerts, Dashboard, Cronjob) funktioniert bereits Ende-zu-Ende,
> nur eben noch mit erfundenen Preisen statt echten. Der nächste Schritt ist,
> Provider einzeln durch echte APIs zu ersetzen (Roadmap unten).

## Was der Bot kann

- **Modi:** Flug, Bahn, Bus, Hotel, Flug+Hotel, Bahn+Hotel, Bus+Hotel,
  "Bahn oder Bus – was günstiger/schneller ist" - pro Strecke frei kombinierbar.
- **Einstellungen pro Strecke** (`config/routes.yaml`): Start/Ziel, Datum +
  Flexibilität in Tagen davor/danach, Mindest-/Max-Aufenthalt (für Hotel),
  Budget, Währung, maximale Reisezeit, Priorität (`cheapest` / `fastest` /
  `best_value`), Gepäck (Handgepäck-only, Anzahl/Gewicht Koffer), Bahn-Extras
  (BahnCard 25/50/100, Deutschlandticket), ob Low-Cost-Airlines ok sind.
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

## Architektur

```
traveldeals/
  models.py         RoutePreference, Offer, TripOption, Enums
  config.py         lädt config/routes.yaml
  providers/
    base.py         Provider-Interface (search(route) -> list[Offer])
    mock.py         deterministische Fake-Angebote (v1, siehe unten)
    real.py         Stubs für Amadeus/DB/FlixBus/Booking - noch nicht implementiert
  engine.py         DealEngine: sammelt Angebote, baut Kombis, filtert
                     (Budget/Dauer/Low-Cost), rankt (cheapest/fastest/
                     best_value), hängt Empfehlungen an
  pricehistory.py   JSON-Preishistorie je Strecke+Modus -> Preisfall/Fehlerpreis
  currency.py       Wechselkurse (live via frankfurter.app, sonst Fallback-Tabelle)
  notifiers/        Telegram, E-Mail (SMTP), Konsole
  cli.py            `python -m traveldeals.cli check` - der komplette Lauf
docs/               statisches Dashboard (GitHub Pages), liest docs/data/deals.json
data/               Preishistorie (wird vom Cronjob committet)
.github/workflows/  Scheduled Job, der `check` laufen lässt
```

**Warum Mock-Daten?** Echte Preisvergleiche brauchen pro Modus eine reale
Datenquelle, und die sind fast alle kostenpflichtig oder erfordern ein
Partner-Konto (siehe Roadmap). Damit trotzdem sofort die komplette Logik -
Einstellungen, Ranking nach `cheapest`/`fastest`/`best_value`, alle
Empfehlungs-Regeln, Alert-Versand, Dashboard, Cronjob - steht und getestet
werden kann, generiert `providers/mock.py` deterministische, aber plausible
Angebote (inkl. gelegentlich einem künstlichen "Fehlerpreis" zur Demo). Jeder
Mock-Provider hat in `providers/real.py` ein Gegenstück, das nur noch die
echte API anbinden muss - die Schnittstelle (`Provider.search`) bleibt gleich.

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

Ziel ist, `providers/mock.py` Modus für Modus durch `providers/real.py` zu
ersetzen (Interface bleibt gleich, s.o.):

- **Flug:** [Amadeus Self-Service API](https://developers.amadeus.com)
  (kostenloses Test-Kontingent, danach nutzungsbasiert) oder Kiwi Tequila API.
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
