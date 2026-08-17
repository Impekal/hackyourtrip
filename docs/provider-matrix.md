# Provider Contract Matrix

Pro Datenquelle die acht Fragen, die vor einer kommerziellen Nutzung
beantwortet sein müssen. Diese Datei ist die Entscheidungsgrundlage für
`SOURCE_POLICY` in `docs/app.js` – ändert sich hier eine Einstufung,
ändert sie sich dort mit.

**Lesehinweis, damit nichts verwechselt wird:**

- **Gemessen** = von uns technisch geprüft (Live-Abfragen, siehe
  `HANDOFF.md`). Verlässlich.
- **Ungeprüft** = wir haben die Nutzungsbedingungen/Lizenz **nicht**
  gelesen. Eine funktionierende API ist **kein** Beleg dafür, dass ihre
  Nutzung erlaubt ist. Diese Felder darf nur füllen, wer die Bedingungen
  tatsächlich gelesen oder beim Anbieter nachgefragt hat.

Einstufung in drei Stufen:

| Stufe | Bedeutung | Im Store-Modus |
|---|---|---|
| `erlaubt` | offizieller Zugang, Nutzung gedeckt | läuft |
| `ungeklaert` | Bedingungen nicht geprüft | läuft **nicht** |
| `nurPrivat` | inoffiziell/nicht lizenzierbar | läuft **nicht** |

---

## Flug

### Travelpayouts (Aviasales-Daten)

| Frage | Antwort | Quelle |
|---|---|---|
| Zugang | offizielles Partnerprogramm, Token | gemessen: funktioniert |
| Preis anzeigen? | **ungeprüft** – Programmbedingungen lesen | – |
| Preis cachen? Wie lange? | **ungeprüft** | – |
| Verbindung speichern? | **ungeprüft** | – |
| Request-Limit | **ungeprüft** | – |
| Weitergabe an Dritte? | **ungeprüft** | – |
| Attribution nötig? | **ungeprüft** (vermutlich ja) | – |
| Affiliate-Provision? | ja, das ist der Geschäftszweck | – |

**Einstufung: `erlaubt`** – der einzige Flugpreis-Zugang, der für ein
kommerzielles Produkt gedacht ist. Die offenen Felder sind trotzdem vor
Veröffentlichung zu klären.

### Ryanair (`services-api.ryanair.com/farfnd/v4`)

| Frage | Antwort |
|---|---|
| Zugang | interner Endpunkt, **kein** öffentliches Programm gefunden |
| Alles Weitere | **ungeprüft**, vermutlich nicht gestattet |

**Einstufung: `nurPrivat`** – funktioniert (gemessen), ist aber kein
lizenzierter Zugang. Für private Nutzung in Ordnung, nicht für ein
verkauftes Produkt.

### Skiplagged

| Frage | Antwort |
|---|---|
| Zugang | fremde Website als Datenquelle |
| Alles Weitere | **nicht lizenzierbar**; Anbieter geht gegen fremde Nutzung vor |

**Einstufung: `nurPrivat`**.

---

## Bahn

### Deutsche Bahn (`int.bahn.de` über den lokalen Server)

| Frage | Antwort |
|---|---|
| Zugang | **inoffizieller** interner Endpunkt; Abfragen von Server-IPs werden gesperrt (gemessen: 403) |
| Preis anzeigen? | **nein**, nicht auf dieser Grundlage |

**Einstufung: `nurPrivat`** – ausdrücklich durch die Strategie
ausgeschlossen (kein Scraping, keine inoffiziellen Schnittstellen).
Bleibt als privates Werkzeug bestehen.

**Offene Aufgabe:** Beim DB API Marketplace klären, welche offizielle
API mit welcher Lizenz *aktuellen Preis anzeigen + externe
Vergleichsanwendung + Weiterleitung zur DB-Buchung* erlaubt.

### Transitous / MOTIS (`api.transitous.org`)

| Frage | Antwort |
|---|---|
| Zugang | offenes Community-Projekt, kein Schlüssel nötig (gemessen) |
| Preis | liefert **keine** Preise (gemessen: `fares: 0`) |
| Request-Limit | **ungeprüft** – Fair-Use-Regeln des Projekts lesen |
| Attribution nötig? | **ungeprüft** – offene Fahrplandaten verlangen meist Namensnennung |
| Kommerzielle Nutzung? | **ungeprüft** |

**Einstufung: `ungeklaert`** – technisch der naheliegende Bahn-Ersatz
für die Store-Fassung, aber erst nach Prüfung von Nutzungsbedingungen
und Attribution. Bis dahin zeigt der Store-Modus keine Bahnverbindungen.

---

## Bus

### FlixBus (`global.api.flixbus.com`)

| Frage | Antwort |
|---|---|
| Zugang | interner Endpunkt, **kein** öffentliches Programm gefunden |
| Alles Weitere | **ungeprüft**, vermutlich nicht gestattet |

**Einstufung: `nurPrivat`**. Für die Store-Fassung wäre ein
Affiliate-Programm des Anbieters der richtige Weg.

---

## Hotel

### LiteAPI (`api.liteapi.travel`)

| Frage | Antwort |
|---|---|
| Zugang | offizieller Anbieter; wir nutzen bisher den **Sandbox**-Schlüssel |
| Preis anzeigen? | im Sandbox-Rahmen ja (gemessen: echte Raten); kommerziell → Produktionszugang nötig |
| Preis cachen? | **ungeprüft** |
| Request-Limit | **ungeprüft** |
| Attribution nötig? | **ungeprüft** |
| Provision? | Anbieter arbeitet mit Provisionsmodell – **Konditionen ungeprüft** |

**Einstufung: `erlaubt`** (als Anbieterbeziehung), **aber** der
Produktionszugang fehlt. Bis dahin liefert die Store-Fassung keine
Hotelpreise.

---

## Sonstige

### Deal-Feeds (fly4free, travelfree, Urlaubspiraten)

| Frage | Antwort |
|---|---|
| Inhalt | fremde **redaktionelle** Beiträge |
| Nutzung | Anriss + Link ist üblich; Volltext-Übernahme nicht |
| Alles Weitere | **ungeprüft** |

**Einstufung: `ungeklaert`**.

### Beispieldaten (eigene Erfindung)

Keine Fremddaten, aber in einem verkauften Produkt trotzdem
inakzeptabel: erfundene Preise, die wie Angebote aussehen.

**Einstufung: `nurPrivat`** – im Store-Modus nicht einmal zuschaltbar.

### KI (Groq / Mistral / Gemini)

Eigene Schlüssel, keine Reisedaten Dritter. Für die Store-Fassung ist
BYOK vorgesehen (Nutzer bringt seinen eigenen Schlüssel mit).

**Einstufung: `erlaubt`**.

---

## Was daraus folgt

Im Store-Modus laufen heute: **Flug (Travelpayouts)** und **Hotel
(LiteAPI, sobald Produktionszugang da)**. Bahn und Bus fehlen, bis
Transitous geprüft bzw. offizielle Zugänge vorhanden sind. Das ist kein
Mangel der Umsetzung, sondern der ehrliche Stand der Rechtelage – und
genau der Grund, warum diese Matrix existiert.
