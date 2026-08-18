# HackYourTrip – Weg zur kommerzialisierbaren Fassung

Diese Datei hält die strategische Entscheidung fest und listet die
Aufgaben, die daraus folgen. Sie ergänzt `HANDOFF.md` (technischer
Projektstand), ersetzt sie nicht.

**Sicherungspunkt vor dem Umbau:** Branch
`backup-vor-kommerz-2026-08-17` (Stand Build 2026-08-09-21, alle Tests
grün). Von dort ist der heutige Zustand jederzeit wiederherstellbar.

## Die Entscheidung in einem Satz

HackYourTrip verkauft nichts. Es aggregiert **offiziell zugängliche**
Reiseinformationen, vergleicht sie mit einer **eigenen Ranking-Engine**,
nennt die beste Option und schickt den Nutzer zum Anbieter – dort wird
gebucht, und darüber wird ggf. über Affiliate verdient.

Daraus folgen vier Leitplanken, an denen sich jede weitere Entscheidung
messen lassen muss:

1. **Keine Buchung, keine Zahlung, keine Ticketverwaltung** in der App.
2. **Nur erlaubte Datenquellen**: offizielle APIs, Affiliate-APIs,
   lizenzierte Aggregatoren. Kein Scraping, keine inoffiziellen
   Endpunkte in der ausgelieferten Fassung.
3. **Der eigene Mehrwert ist die Entscheidungslogik**, nicht der
   Datenbesitz. Fremde Daten sind Input.
4. **Kein Datenlager**: Speichern/Cachen nur, soweit die jeweilige
   Lizenz es erlaubt.

## Der unangenehme Befund zuerst

Die heutige Fassung ist als **private Nutzung** gebaut. Für einen
Store-Release ist ein Teil der Preisquellen nicht verwendbar – und
ausgerechnet die stärksten:

| Quelle | Was sie liefert | Technische Einordnung (gemessen) | Für Store |
|---|---|---|---|
| **Travelpayouts** | Flugpreise | offizielles Partnerprogramm, dokumentierte API, Token | ✅ tragfähige Basis |
| **LiteAPI** | Hotelpreise | offizieller Anbieter, aber wir nutzen den **Sandbox**-Key | ⚠️ Produktionszugang nötig |
| **Transitous/MOTIS** | Bahnverbindungen **ohne Preis** | offenes Community-Projekt, offene Daten | ⚠️ Nutzungsbedingungen + Attribution prüfen |
| **bahn.de / int.bahn.de** | echte DB-Preise | **inoffizieller** interner Endpunkt, umgeht Bot-Schutz | ❌ nicht auslieferbar |
| **Ryanair `services-api`** | echte Flugpreise | interner Endpunkt ohne öffentliches Programm | ❌ bis Lizenz geklärt |
| **Skiplagged** | Flugpreise anderer Airlines | fremde Website als Quelle | ❌ nicht auslieferbar |
| **FlixBus `global.api`** | Buspreise | interner Endpunkt ohne öffentliches Programm | ❌ bis Lizenz geklärt |
| **Deal-Feeds** (fly4free u.a.) | Fehlerpreis-Meldungen | fremde redaktionelle Inhalte | ⚠️ nur Anriss + Link, nie Volltext |

**Konsequenz, klar ausgesprochen:** Der lokale Bahn-Preis-Server – die
Live-DB-Preise, an denen wir zuletzt gearbeitet haben – kann in einer
kommerziellen Fassung **nicht mitgeliefert werden**. Er bleibt ein
privates Werkzeug. Die Store-Fassung zeigt Bahnverbindungen ohne Preis
plus „Bei DB buchen"-Link, bis geklärt ist, welche offizielle DB-API mit
welcher Lizenz die Kombination *aktuellen Preis anzeigen + externe
Vergleichsanwendung + Weiterleitung zur DB-Buchung* erlaubt.

**Zweiter Befund:** Unsere Buchungslinks tragen heute **keinen
Affiliate-Marker**. Selbst wenn morgen jemand über HackYourTrip bucht,
verdienen wir nichts. Das ist der schnellste konkrete Schritt.

## Zwei Fassungen statt eines Kompromisses

Der Kern des Umbaus: Jede Quelle bekommt eine Einstufung
(`erlaubt` / `nur privat` / `ungeklärt`), und ein Schalter entscheidet,
welche Fassung läuft:

- **Privat-Modus** (wie heute, für dich zuhause): alle Quellen, inkl.
  lokalem Bahn-Server. Maximale Ersparnis.
- **Store-Modus** (das, was veröffentlicht wird): ausschließlich als
  `erlaubt` eingestufte Quellen. Kein Beispieldaten-Fallback.

So geht die heutige Funktionalität nicht verloren, und die
auslieferbare Fassung ist trotzdem sauber.

## Provider Contract Matrix

Pro Quelle sind acht Fragen zu beantworten (Punkt 3 der Strategie).
Die Matrix liegt in `docs/provider-matrix.md` (wird in Aufgabe 1
angelegt). Wichtig für die Ehrlichkeit dieser Datei: Die technische
Einordnung oben ist **gemessen**; die lizenzrechtlichen Antworten sind
**noch nicht geprüft** und dürfen nicht aus der Existenz einer API
abgeleitet werden.

## Aufgabenliste

### Phase 0 – Fundament (bestimmt alles andere)

1. ~~**Provider Contract Matrix anlegen**~~ ✅ erledigt →
   `docs/provider-matrix.md`. Technische Einordnung eingetragen
   (gemessen), Lizenzfragen ausdrücklich als **ungeprüft** markiert.
2. ~~**Quellen-Einstufung im Code + Store-Modus-Schalter**~~ ✅ erledigt
   (Build 2026-08-09-22). `SOURCE_POLICY` + `sourceAllowed()` in
   `docs/app.js`; Umschalten mit `?modus=store` bzw. `?modus=privat`,
   die Wahl bleibt im Browser gemerkt. Privat-Modus unverändert.

   **Beim Testen zwei echte Fehler gefunden und behoben:** (a) Transitous
   wurde im Store-Modus über die *Adress-Vervollständigung* weiter
   abgefragt – eine Sperre an der Angebotssuche allein genügt nicht,
   jede Nutzung derselben Quelle zählt; (b) `?modus=store` wurde nicht
   gemerkt, weil die Auswertung nur zufällig lief – jetzt einmal beim
   Start. Gemessen wird an den tatsächlich rausgehenden HTTP-Anfragen,
   nicht an der Absicht im Code (Test `ui_storemode.py`, 19/19).
3. **Affiliate-Marker in allen Buchungslinks** – Travelpayouts-Marker
   sauber durchreichen, Klick-Tracking prüfen. *(baubar, sobald du die
   Partner-ID hast)*
4. ~~**Werbekennzeichnung**~~ ✅ erledigt (Build 2026-08-09-23).
   Provisionsfähige Links tragen ein erklärtes `*` **direkt am Link**
   (dort wird geklickt) plus `rel="sponsored"`; die Ergebnisliste
   erklärt es, die Fußzeile dauerhaft. Bewusst über eine Liste der
   Ziele, an denen wir verdienen können (`AFFILIATE_HOSTS`), nicht über
   eine Faustregel: die Anbieterliste „Echte Preise direkt prüfen"
   bringt nichts ein und wird deshalb **nicht** gekennzeichnet – der
   Test prüft beide Richtungen (`ui_werbung.py`, 23/23). Der Text sagt
   ehrlich „ggf. eine Provision", denn bis Aufgabe 3 greift, bringt
   kein Link etwas ein.

### Phase 1 – MVP-Kette: 1 Flug + 1 Bahn + 1 Hotel

5. **Flug: Travelpayouts als einzige Store-Quelle** – Ryanair/Skiplagged
   nur noch im Privat-Modus.
6. **Bahn: Store-Fassung ohne Preis** – Transitous-Verbindungen +
   Weiterleitung, ehrliche Kennzeichnung „Preis beim Anbieter".
7. **DB-Lizenzfrage klären** – welche offizielle DB-API erlaubt
   Preisanzeige für externe Vergleichsanwendungen? *(deine Aufgabe:
   Anfrage an DB API Marketplace; ich formuliere sie dir)*
8. **Hotel: LiteAPI-Produktionszugang** – Sandbox reicht kommerziell
   nicht. *(deine Aufgabe: Zahlungsmittel hinterlegen)*

### Phase 2 – Der eigene Mehrwert, sichtbar gemacht

9. **HackYourTrip-Score** – aus der bestehenden Ranking-Logik einen
   benannten, erklärten Score machen: Preis, Reisezeit, Umstiege,
   Abfahrtszeit, Komfort, Präferenzen, Gepäck. Mit sichtbarer
   Begründung je Angebot („warum Platz 1?").
10. **CO₂ und Zuverlässigkeit** als Score-Faktoren ergänzen – beides
    fehlt bisher; nur aus belegbaren Quellen, nie geschätzt.

### Phase 3 – Betrieb bei 1.000 Nutzern

11. **Rate-Limiting + Request-Deduplizierung** im Worker, pro Provider
    getrennte Limits.
12. **Caching-Regeln pro Provider** – Dauer aus der Matrix, nicht
    geraten; automatische Löschung, kein Datenlager.
13. **Monitoring + Fallbacks** – Kontingentverbrauch sichtbar, Ausfall
    einer Quelle darf die Suche nicht töten.

### Phase 4 – Store-Reife

14. **Beispieldaten im Store-Modus hart aus** – keine erfundenen Preise
    in einer verkauften App, auch nicht abschaltbar.
15. **BYOK-KI** – Nutzer kann eigenen KI-Schlüssel hinterlegen; der
    bleibt auf dem Gerät, nie auf unserem Server.
16. **Rechtstexte** – Impressum, Datenschutzerklärung, Nutzungs-
    bedingungen, Affiliate-Offenlegung.
17. **App-Verpackung für die Stores** – PWA in eine Store-Hülle,
    Entwicklerkonten, Prüfprozess.
18. **Nebengewerbe Impekal** – deckt HackYourTrip, MySportPilot und
    ANITEW gemeinsam ab. *(kein Code – deine Aufgabe, wenn Einnahmen
    tatsächlich fließen)*

## Reihenfolge-Empfehlung

Zuerst 1 → 2 → 4 (Fundament, rein bei uns, sofort baubar), dann 3
(sobald Partner-ID da), dann 5/6 (MVP-Kette steht), parallel dazu 7/8
als deine Anfragen nach außen. Phase 2 ist der Teil, der HackYourTrip
von einer Linkliste unterscheidet – der lohnt sich, sobald die Kette
steht. Phase 3 vor dem ersten echten Nutzeransturm, Phase 4 unmittelbar
vor Veröffentlichung.
