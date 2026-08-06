# HackYourTrip

Bot/Webapp, der Flug-, Bahn-, Bus- und Hotel-Angebote vergleicht, dich per
Telegram/E-Mail auf Preisverfall und mögliche Fehlerpreise hinweist und dir
auf einem Dashboard die besten aktuellen Optionen pro Strecke zeigt.

> ## ⚠️ Wichtig: Was ist echt, was ist Beispiel?
>
> | Modus | Datenquelle |
> |---|---|
> | **Flug** | **echte Preise** aus drei Quellen: **Ryanair** (live buchbar, ohne Zugangsdaten), **Skiplagged** (Lufthansa, Air France, KLM, Swiss, Turkish … – die Airlines, die Ryanair nicht fliegt) und **Travelpayouts** (mit Token) |
> | **Bus** | **echte, buchbare Preise** – **FlixBus** liefert Live-Fahrpreise inkl. freier Plätze und Umstiegen |
> | **Bahn** | **echte Verbindungen, aber ohne Preis** (Transitous/MOTIS): richtige Linie (ICE 1007), Abfahrtszeit, Gleis, Umstiege – nur **kein Preis**, weil die Quelle keinen führt. Dort steht "Preis unbekannt" statt einer erfundenen Zahl. |
> | **Hotel** | **erfundene Beispieldaten** - keine buchbaren Angebote |
>
> **Belegt, nicht vermutet** (Stand 06.08.2026, gegen die Live-Endpunkte
> geprüft): Für Bahn/Bus/Hotel-*Preise* gibt es keine kostenlose Quelle ohne
> Anmeldung.
>
> | Quelle | Ergebnis |
> |---|---|
> | `v6.db.transport.rest` (DB-Wrapper) | **HTTP 503** – Dienst nicht verfügbar |
> | `v5.db.transport.rest` | HTTP 503 |
> | `flixbus.transport.rest` | Domain existiert nicht |
> | **`api.transitous.org`** (MOTIS) | **funktioniert** – echte Verbindungen/Zeiten, aber `fares: 0`, also **keine Preise**. **Ist jetzt eingebaut** (siehe unten). |
> | `v6.vbb` / `v6.bvg.transport.rest` | 200, aber nur Berliner Nahverkehr |
> | OpenTripMap (Hotels) | 401 – Schlüssel erforderlich |
>
> Zweite Runde (06.08.2026), diesmal für **Flugpreise**:
>
> | Quelle | Ergebnis |
> |---|---|
> | **`services-api.ryanair.com/farfnd/v4`** | **funktioniert ohne Schlüssel** – echte, buchbare Preise inkl. Flugnummer. **Ist eingebaut.** |
> | Ryanair `availability` | 409 „Availability declined" – braucht Buchungs-Session |
> | Ryanair `cheapestPerDay` | 200, aber leere Antwort |
> | `bahn.de` Sparpreise (inoffiziell) | 403 `OPS_BLOCKED` |
> | Lufthansa Open API | 596 Service Not Found |
> | SNCF / Navitia | 401 – Token nötig |
> | Wizz Air, easyJet | kein öffentlicher Endpunkt, nur kostenpflichtige Scraper-Dienste |
>
> Dritte Runde (06.08.2026), **weltweit**, ~25 Endpunkte live angefragt:
>
> | Quelle | Ergebnis |
> |---|---|
> | **FlixBus `global.api.flixbus.com`** | **funktioniert ohne Schlüssel** – Live-Preise, freie Plätze, Umstiege. **Ist eingebaut.** |
> | Kiwi `api.skypicker.com` (früher keylos) | 404, abgeschaltet |
> | Kiwi Tequila | 403, `apikey` erforderlich |
> | Hotellook / Travelpayouts-Hotels | alle Varianten 404 |
> | easyJet, Southwest | 403 Access Denied |
> | Norwegian, Volotea | 403 Bot-Wall („Are you human?") |
> | Wizz Air, Vueling, AirAsia, Transavia | 404, Endpunkte existieren nicht mehr |
> | IndiGo, Amtrak | Timeout |
> | DB (`int.bahn.de`, `www.bahn.de`, vendo) | 403 `OPS_BLOCKED` auf **allen** Hosts |
> | SBB, SNCF/Navitia | 403 / 401 |
> | Trenitalia Stationssuche | 200 – Preise wären ein eigener Ausbauschritt |
>
> Vierte und fünfte Runde (06.08.2026): Wiederverkäufer und Aggregatoren –
> hat jemand Zugriff, wo der Betreiber selbst blockt?
>
> | Quelle | Ergebnis |
> |---|---|
> | **Skiplagged** | **funktioniert ohne Schlüssel** – 252 Verbindungen für HAM→LYS mit Lufthansa/AF/KLM/Swiss. **Ist eingebaut.** |
> | **Deal-Feeds** (Urlaubspiraten, Travelfree, Fly4free) | **funktionieren** – echte RSS-Feeds mit Aktionen und Fehlerpreisen. **Sind eingebaut.** |
> | Trainline Stationssuche | 200 – die Suche selbst aber hinter DataDome-Captcha (403) |
> | thetrainline, Omio, Busbud, Wanderu, Checkmybus | 403 Captcha bzw. 404 |
> | Rome2Rio | Domain existiert nicht mehr |
> | Kiwi skypicker | 404, abgeschaltet |
> | Hostelworld, Booking, Hotelbeds | 404 / 401 |
>
> Sechste Runde (06.08.2026) – deine Idee: Wiederverkäufer verkaufen sich
> gegenseitig die Tickets, vielleicht ist DB über SNCF & Co. erreichbar.
>
> | Quelle | Ergebnis |
> |---|---|
> | SNCF Connect | 401 UNAUTHORIZED |
> | B-Europe (SNCB, verkauft DB+TGV) | 404 |
> | Rail Europe | Domain existiert nicht mehr |
> | Trenitalia, Italo | 400 / SOAP-Fault |
> | Renfe | Dynatrace-Bot-Schutz |
> | NS (NL) | Subscription-Key nötig |
> | Eurostar, ÖBB-Ticketshop, Interrail | 403 / 404 |
> | **SBB via `transport.opendata.ch`** | **200 – aber Fahrplan ohne Preise** |
> | Agoda, Trivago, Expedia, Hotels.com | 404 / 429 |
> | Kayak | 200, aber nur ein Hotelmarken-Verzeichnis ohne Preise |
>
> Die Idee war richtig gedacht, führt aber nicht zum Ziel: **jeder** europäische
> Bahn-Wiederverkäufer verlangt entweder Auth oder sitzt hinter Bot-Schutz.
>
> **Fazit nach sechs Runden:** Vier kostenlose, anmeldungsfreie Quellen mit
> echten Preisen – **Ryanair**, **Skiplagged**, **FlixBus** und (mit
> kostenlosem Token) **Travelpayouts** –, dazu drei Deal-Feeds. Für **Bahn**
> und **Hotel** gibt es keine: die Bahn blockt ihre eigene App-API
> serverseitig, und auch die Wiederverkäufer, die DB-Preise hätten, sitzen
> hinter einem Captcha.
>
> **Zur Währung bei Skiplagged:** die API nennt keine und ignoriert einen
> `currency`-Parameter. Statt zu raten wurde es belegt – die Seite zeigt „$",
> und BER→BCN kostete dort 62,00 an einem Tag, an dem Ryanair 53,36 EUR
> nannte (Verhältnis 0,86 = der damalige EUR/USD-Kurs). Preise werden
> deshalb **umgerechnet**, nicht umetikettiert.
>
> **Die Einschränkung, die dazugehört:** Ryanair kennt nur Ryanair-Strecken.
> Hamburg–Lyon fliegt Ryanair nicht, also hilft es dort nicht. Deshalb werden
> beide Quellen **gemischt**, nicht gegeneinander ausgetauscht.
>
> **Was daraus geworden ist:** Bahn und Bus laufen nicht mehr auf erfundenen
> Preisen, sondern auf echten Fahrplandaten von Transitous - ohne Schlüssel,
> ohne Anmeldung, gespeist aus den offiziellen Verkehrsverbund-Feeds. Eine
> Zeile zeigt also die tatsächliche Verbindung und ausdrücklich **keinen**
> Preis. Das ist bewusst so: ein echter ICE ohne Preisangabe ist mehr wert
> als eine plausible Zahl, die niemand buchen kann.
>
> Für **Hotels** existiert weiterhin keine frei nutzbare Quelle; dieser Modus
> läuft auf generierten Zufallspreisen, mit denen die Vergleichs- und
> Ranking-Logik getestet wird. **Solche Angebote lassen sich nirgends
> buchen** - sie sind in der Oberfläche mit Warnbanner, durchgestrichenem
> Preis und "Nicht buchbar"-Abzeichen gekennzeichnet. Unter den Ergebnissen
> stehen in jedem Fall Direktlinks zu den echten Anbietern (DB, SNCF Connect
> für TGV, Trainline, FlixBus, BlaBlaCar Bus, Omio, Lastminute …), um den
> Preis dort zu prüfen.
>
> Bis Version vom 06.08.2026 trugen diese Beispielangebote echte
> Anbieternamen wie "DB Navigator" - das war irreführend und ist behoben.

> **Stand 06.08.2026:** Für **Flug** und **Bus** liefert die App echte,
> buchbare Preise, ganz ohne Zugangsdaten - Ryanair und Skiplagged für Flüge,
> FlixBus für Busse. Ein kostenloser `TRAVELPAYOUTS_TOKEN` erweitert die
> Flugsuche zusätzlich (siehe "Travelpayouts einrichten"); Amadeus wird für
> Enterprise-Zugänge weiter unterstützt, die kostenlose Self-Service-Stufe
> wurde im Juli 2026 abgeschaltet. **Bahn** kommt über Transitous aus echten
> Fahrplandaten - dafür ohne Preis. Nur **Hotel** hat keine freie Quelle.
>
> **Beispieldaten sind standardmäßig aus.** Findet keine echte Quelle etwas,
> bleibt die Liste leer und nennt den Grund - statt drei erfundene Preise
> anzuzeigen, die wie eine Antwort aussehen.

## Was der Bot kann

- **10 Such-Modi** (im Suche-Tab als eigene Reiter, weil z.B. bei "nur Hotel"
  eine Anreise irrelevant ist - jeder Modus zeigt nur die Felder, die für ihn
  Sinn ergeben): Flug, Bahn, Bus, Hotel, Bahn/Bus, Flug/Bahn, Flug/Bus (jeweils
  "was ist besser"), Flug+Hotel, Bahn+Hotel, Bus+Hotel.
- **Einstellungen pro Strecke** (`config/routes.yaml`): Start/Ziel, Datum +
  Flexibilität in Tagen davor/danach, Mindest-/Max-Aufenthalt (für Hotel),
  Budget, Währung, maximale Reisezeit, Priorität (`cheapest` / `fastest` /
  `best_value`), Gepäck (aufgegebene Koffer: kg pro Stück + Anzahl;
  Handgepäck separat: kg-Limit pro Stück + Anzahl), Bahn-Extras (BahnCard
  25/50/100, Deutschlandticket), ob Low-Cost-Airlines ok sind.
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
- **Umkreis Start / Umkreis Ziel** (`nearby_origin_km`,
  `nearby_destination_km`): Hamburg→Lyon hat kaum Preise, Bremen→Genf schon.
  Auf Wunsch werden Nachbar-**Flughäfen und -Bahnhöfe** bis
  20/50/100/150/250 km mitgesucht, und jedes Angebot von dort trägt sichtbar
  „ab BRE · +103 km Anfahrt". Ob ein Umweg das wert ist, entscheidet niemand
  außer dir - genau deshalb wird er angezeigt statt eingerechnet.
  **Getrennt je Seite**, weil der Umweg an den beiden Enden selten gleich
  viel wert ist: zum Startflughafen fährt man im eigenen Auto, am Ziel steht
  man mit Gepäck und ohne Auto da. 150 km Anfahrt zu Hause und 20 km am Ziel
  ist eine völlig normale Kombination - ein einzelner Regler konnte sie nicht
  ausdrücken. Ein altes `nearby_km` in einer bestehenden `routes.yaml` gilt
  weiterhin für beide Seiten.
  Für Bahnhöfe gibt es **keine** Koordinatentabelle im Code: jeder Kandidat
  wird über Transitous aufgelöst, das die echte Haltestelle mit echten
  Koordinaten liefert. Eine aus Flughafenpositionen gebastelte Tabelle würde
  den angezeigten Umweg um zig Kilometer danebenlegen.
- **Hin/Zurück frei kombinieren** (Modus `mixed_return`): Hinweg und Rückweg
  werden unabhängig gewählt, quer über Flug, Bahn und Bus - „hin fliegen,
  zurück Bus". Kein Portal bietet das, weil jedes nur einen Modus verkauft.
- **Deals und Fehlerpreise**: unter den Ergebnissen erscheinen passende
  Beiträge aus den RSS-Feeds von Urlaubspiraten, Travelfree und Fly4free -
  das, was keine Preis-API beantworten kann. Bewusst als Links, nicht als
  Angebote mit Preis: „Mallorca ab 39 EUR" ist eine Anzeige, keine buchbare
  Verbindung für deine Daten.
- **Von/Nach-Autocomplete:** Stadt eintippen, passenden Flughafen/Bahnhof
  auswählen - wie auf gängigen Reiseplattformen. Flug/Hotel nutzen die
  echte, öffentliche Travelpayouts-Places-API (`autocomplete.travelpayouts.com`,
  kein Token nötig), Bahn/Bus den Transitous-Geocoder - also genau die
  Haltestellen-Datenbank, mit der anschließend auch geroutet wird, damit ein
  ausgewählter Vorschlag garantiert auflösbar ist. Nur Hotels/POIs werden
  dabei aussortiert (der Top-Treffer für "München Hbf" war eine Sauna
  nebenan). Fällt Transitous aus, greift eine kuratierte statische Liste
  großer DACH-/europäischer Bahnhöfe.
- **Hin- und Rückreise:** bei Flug/Bahn/Bus (und deren "was ist besser"-Kombis)
  lässt sich zwischen Nur-Hinfahrt und Hin+Rück wählen (`round_trip` +
  `return_date` in `RoutePreference`). Bei echten Travelpayouts-Daten liefert
  die API dafür einen kombinierten Gesamtpreis für beide Strecken (kein
  client-seitiges Aufsummieren nötig); die Mock-Provider bilden das mit einer
  synthetisierten Rückreise nach demselben Prinzip nach. Reine Hotel-Modi
  brauchen das nicht (Checkin+Nächte bilden die Aufenthaltsdauer schon ab).
- **Drei Ergebnis-Tabs bei Hin+Rück:** „Nur Hinfahrt", „Nur Rückfahrt"
  und „Hin + Zurück" - jeder mit eigener Liste und eigener Sortierung, als
  echte Reiterleiste über den Ergebnissen (`role="tablist"`, Pfeiltasten/Pos1/
  Ende, Roving-Tabindex, Ergebnisliste als zugehöriges `tabpanel`). Die
  Kombi-Liste enthält beides nebeneinander: echte Hin-/Rückflug-Tickets (ein
  Preis, ein Ticket) und aus zwei Einzelfahrten zusammengesetzte Reisen.
  Genau daran hängt der Spareffekt - zwei getrennt gebuchte Einzelfahrten
  sind regelmäßig günstiger als das Rückflugticket derselben Airline, aber
  nur sichtbar, wenn man die drei Zahlen direkt vergleichen kann. Eine
  einzige gemischte Liste hat das nie gezeigt.
  Beim Zusammensetzen wird jede Hinfahrt mit der günstigsten Rückfahrt *pro
  Verkehrsmittel* gepaart (jede gegen jede wären Tausende fast identischer
  Zeilen ohne zusätzliche Erkenntnis), und eine Rückfahrt, die vor der
  Hinfahrt startet, fällt raus.
- **Sortierung frei wählbar** - und zwar *an den Ergebnissen*, nicht im
  Suchformular: bestes Verhältnis, Preis aufsteigend, Preis absteigend,
  Dauer, oder Präzision (`exact_date` - Angebote am exakt gewünschten Datum
  zuerst, dann die aus dem Flex-Fenster, Preis als Tie-Breaker). Umsortieren
  und der Wechsel zwischen den drei Abschnitten laufen komplett auf den schon
  geladenen Angeboten: keine einzige neue Anbieter-Abfrage, kein Warten. Als
  Suchfeld hatte jede Umsortierung eine komplette neue Runde bei allen
  Quellen gekostet.
  Preislose Fahrplan-Verbindungen sortieren in allen Preis-Reihenfolgen hinter
  jedes bepreiste Angebot (ihre 0 ist ein Platzhalter, kein Preis) - außer
  bei „Dauer", denn die Dauer, die sie mitbringen, ist echt.
- **Maximale Reisezeit gilt pro Strecke,** nicht für die Summe: 5h hin und 5h
  zurück ist keine „10h-Reise", die ein 8h-Limit ausblenden dürfte.
- **Deals-Filter:** entweder alle Angebote oder nur die, die wirklich nach
  einem Deal aussehen (`deals_only`). Als Deal gilt: von der Preishistorie
  als Preisverfall/Fehlerpreis markiert - oder, solange keine Historie
  existiert, mindestens 15% unter dem Median derselben Suche (je
  Verkehrsmittel verglichen). Bewusst so gebaut, dass der Filter auch leer
  bleiben darf, statt normale Preise zu Deals zu erklären.
- **Möglichst viele Flüge scannen:** die Flugsuche fragt pro *Monat* ab
  statt pro Tag und filtert clientseitig auf das Flex-Fenster. Grund: gegen
  die Live-API gemessen liefert eine Abfrage für ein konkretes Datum genau
  1 Angebot, eine Monatsabfrage 27-44. Zusätzlich werden zwei Indizes
  gemischt (`aviasales/v3/prices_for_dates` + `v2/prices/latest`), die teils
  unterschiedliche Verbindungen kennen. **Ehrliche Einordnung:** das ist der
  volle Umfang der kostenlosen Travelpayouts-Stufe - ein Cache zuletzt
  gefundener Preise, keine Live-GDS-Suche. Skyscanner/Momondo/Opodo fragen
  Airline-Systeme direkt live ab; das ist mit kostenlosen Zugängen nicht
  erreichbar. Wer mehr Ergebnisse will, erhöht die Flex-Tage - das erweitert
  das Fenster, ohne zusätzliche API-Anfragen zu kosten.
- **KI-Empfehlung, optional:** Button unter der Suche schickt die gefundenen
  Angebote plus die eigenen Kriterien an ein Sprachmodell und bekommt eine
  begründete Empfehlung zurück. Läuft über denselben Cloudflare-Worker wie
  die Preisabfrage (ein API-Key kann genauso wenig im Browser-JS liegen wie
  ein Reise-API-Token). Unterstützt **Gemini, Groq oder Mistral** - einer
  genügt, Setup siehe unten; ohne Key blendet die Oberfläche einen Hinweis
  ein statt zu scheitern. **Wichtig:** die KI bewertet nur die bereits
  gefundenen Angebote - sie kann selbst keine Flüge suchen und darf laut
  Prompt auch keine erfinden. Mehr Ergebnisse kommen von der Monatsabfrage
  oben, nicht von der KI.
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
gelegentlich einem künstlichen "Fehlerpreis" zur Demo).

Für **Bahn und Bus** ist das inzwischen nur noch der Notnagel: normalerweise
antwortet `providers/transitous.py` mit echten Verbindungen, und die
Mock-Generatoren springen nur ein, wenn Transitous die Haltestellen nicht
auflösen kann oder nicht erreichbar ist. Übrig bleibt **Hotel** als einziger
Modus, der grundsätzlich auf erfundenen Preisen läuft.

**Beispieldaten sind seit 06.08.2026 standardmäßig aus.** Im Suche-Tab steht
dafür „Datenquelle → Nur echte Daten" (Voreinstellung). Findet keine echte
Quelle etwas, bleibt die Liste leer und nennt den Grund plus die Anbieter zum
Selbstprüfen – statt drei erfundene Preise anzuzeigen, die wie eine Antwort
aussehen. Wer die Sortier- und Filterlogik testen will, schaltet auf „Auch
Beispieldaten".

**Die Regel dahinter:** Ein erfundener Preis darf nie wie ein buchbarer
aussehen. Kennt eine Quelle die Verbindung, aber nicht den Preis, wird
`Offer.price_known = False` gesetzt - dann steht in der Oberfläche "Preis
unbekannt", die Zeile zählt nirgends als Deal, taucht in keiner
Preishistorie auf und rutscht auch bei "Preis aufsteigend" nicht nach oben,
als wäre sie kostenlos.

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

### KI-Empfehlung aktivieren - optional

Der Worker kann zusätzlich eine KI-Empfehlung liefern (`POST /ai`).
**Drei Anbieter werden unterstützt** - es reicht *einer*, und zwar der, für
den du am einfachsten einen Key bekommst:

| Anbieter | Key holen | Repo-Secret | Braucht Cloud-Projekt/Abrechnung? |
|---|---|---|---|
| Google Gemini | [aistudio.google.com](https://aistudio.google.com/apikey) | `GEMINI_API_KEY` | Cloud-Projekt ja, Abrechnung nein |
| Groq | [console.groq.com/keys](https://console.groq.com/keys) | `GROQ_API_KEY` | nein |
| Mistral | [console.mistral.ai/api-keys](https://console.mistral.ai/api-keys) | `MISTRAL_API_KEY` | nein |

Google sperrt die Key-Erstellung für manche Konten komplett (Alter, Region,
oder Workspace-Richtlinie - erkennbar an "Sie sind derzeit nicht berechtigt,
API Key zu erstellen"). Deshalb sind Groq und Mistral als vollwertige
Alternativen eingebaut; beide vergeben Keys ohne Cloud-Projekt und ohne
Zahlungsdaten.

1. Bei einem der drei Anbieter einen Key erstellen.
2. Als Repo-Secret unter dem passenden Namen aus der Tabelle hinterlegen
   (Settings -> Secrets and variables -> Actions).
3. Worker neu deployen (Actions-Tab -> *Deploy proxy worker* -> *Run
   workflow*) - der Key wird automatisch als Worker-Secret gesetzt.

Sind mehrere gesetzt, gewinnt Gemini vor Groq vor Mistral. Ohne jeden Key
funktioniert alles andere normal weiter; der Button zeigt dann nur einen
Hinweis. Der Key liegt ausschließlich im Worker, nie im Browser-JS.

**Modellname überschreiben:** Anbieter mustern Modellnamen gelegentlich aus.
Falls die Antwort dann "model not found" o.ä. lautet, muss dafür kein Code
geändert werden - eine Repo-*Variable* (nicht Secret) namens `AI_MODEL`
setzen und neu deployen. Standard ist `gemini-2.0-flash`,
`llama-3.3-70b-versatile` bzw. `mistral-small-latest`.

**Kann ich einen Key aus einem anderen Google-Projekt nehmen?** Ja - der
Worker schickt den Key nur weiter, das Projekt dahinter ist ihm egal. Zwei
Bedingungen: in dem Projekt muss die *Generative Language API* aktiviert
sein, und falls für den Key API-Einschränkungen gesetzt sind, muss sie dort
erlaubt sein. Ein Key für einen *anderen* Google-Dienst (Maps, YouTube, …)
funktioniert nicht.

Was die KI macht und was nicht: sie bekommt die *bereits gefundenen*
Angebote plus die eingestellten Kriterien und begründet eine Auswahl. Sie
sucht selbst keine Flüge und darf laut Prompt keine erfinden - mehr
Ergebnisse kommen von der Monatsabfrage der Preis-APIs, nicht von Gemini.

### Alternative: Deploy per CLI

```bash
cd worker/
npm install
npx wrangler login
npx wrangler secret put TRAVELPAYOUTS_TOKEN   # denselben Token wie oben einfügen
npx wrangler secret put GROQ_API_KEY          # optional, nur für die KI-Empfehlung
                                              # (oder GEMINI_API_KEY / MISTRAL_API_KEY)
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
- **Bahn:** ✅ Fahrpläne erledigt - `providers/transitous.py` liefert echte
  Verbindungen über `api.transitous.org` (MOTIS, kostenlos, ohne Schlüssel
  und ohne Anmeldung, gespeist aus offiziellen GTFS-Feeds). **Preise fehlen
  dort und werden bewusst nicht erfunden** (`Offer.price_known = False`).
  Offen bleibt also nur der Preis: die DB hat kein offenes Preis-API;
  denkbar wären `db-vendo-client` (Community, inoffiziell - die öffentlichen
  Wrapper antworteten zuletzt mit 503) oder ein kommerzieller Distributor
  wie die Trainline Partner API.
- **Bus:** ✅ Fahrpläne erledigt - derselbe Transitous-Provider mit
  `COACH`/`BUS`-Modi. Preise ebenfalls offen: FlixBus hat kein offenes
  Self-Serve-API, nur ein Partnerprogramm.
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
