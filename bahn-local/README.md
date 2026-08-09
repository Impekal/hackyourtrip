# Echte Bahn-Live-Preise – der lokale Preis-Server

Die Deutsche Bahn hat keine offene Preis-API und sperrt automatische Abfragen
von Server-IPs (Cloudflare, GitHub, jeder VPS bekommt `403 OPS_BLOCKED`). Von
**deiner eigenen Internetleitung zuhause** aus geht es aber – und nur über
`curl`, weil die DB sogar den Netzwerk-Fingerabdruck des Programms prüft
(Node und Python werden erkannt und geblockt, `curl` sieht aus wie ein
Browser).

Dieser kleine Server nutzt genau das aus: Er läuft auf **deinem** Rechner,
fragt die DB über `curl` und reicht die echten Preise an die HackYourTrip-App
weiter. Solange er läuft, siehst du in der App echte Sparpreise. Läuft er
nicht (Handy unterwegs, Rechner aus), zeigt die App automatisch weiter den
Fahrplan und den Deutschland-Ticket-Preis – nie einen erfundenen Preis.

## Was du brauchst

- Einen Mac, Linux-Rechner oder Windows mit **Python 3** (auf dem Mac schon
  dabei). Test: im Terminal `python3 --version` eingeben – kommt eine
  Versionsnummer, passt es.
- **`curl`** – auf Mac und Linux immer vorinstalliert.
- Nichts weiter. Kein Docker, keine Installation, keine Anmeldung.

## Starten (3 Schritte)

1. **Terminal öffnen.** Auf dem Mac: `Cmd`+`Leertaste`, „Terminal" tippen,
   Enter.

2. **Server holen und starten.** `server.py` ist eine einzelne Datei ohne
   Abhängigkeiten – das ganze Projekt braucht man dafür nicht:

   ```bash
   cd ~
   curl -sS -o bahn-server.py https://raw.githubusercontent.com/kalivolut/hackyourtrip/main/bahn-local/server.py
   python3 bahn-server.py
   ```

   Es erscheint:

   ```
   ──────────────────────────────────────────────────────────
    HackYourTrip – lokaler Bahn-Preis-Server läuft

      ▶  App öffnen:  http://127.0.0.1:8899/
   ──────────────────────────────────────────────────────────
   ```

3. **Dieses Fenster offen lassen** (kein `Strg`+`C`!) und im Browser
   **http://127.0.0.1:8899/** öffnen. Bahnverbindung suchen – die echten
   Preise erscheinen mit einem grünen „🟢 Live-Preis DB"-Abzeichen.

Zum Stoppen im Terminal `Strg`+`C` drücken.

**Server aktualisieren:** die App selbst frischt sich von allein auf – nur
`bahn-server.py` nicht, denn die Datei liegt bei dir. Wenn ich am Server
etwas ändere: `Strg`+`C`, dann dieselben drei Zeilen von oben noch einmal.
Der `curl`-Befehl überschreibt die alte Datei.

## Kurztest, ob er wirklich Preise bekommt

Bei laufendem Server ein zweites Terminal öffnen und eingeben:

```bash
curl -sS "http://127.0.0.1:8899/fahrplan?from=$(curl -sS 'http://127.0.0.1:8899/orte?q=Berlin%20Hbf' | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["id"])')&to=$(curl -sS 'http://127.0.0.1:8899/orte?q=M%C3%BCnchen%20Hbf' | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["id"])')&date=2026-09-15" | python3 -m json.tool | head -20
```

Erscheinen Zeilen mit `"price": 39.99` o.ä., läuft alles.

## Der Spar-Trick: Fahrkarte teilen

Mit gesetztem Haken „Deutschlandticket vorhanden" sucht die App zusätzlich
nach Verbindungen, bei denen der **erste Teil aufs D-Ticket geht**:

> 💡 **Spar-Trick – 25,00 € günstiger, +0.5h**
> 🎫 bis Bremen Hbf mit D-Ticket · spart 25,00 EUR

Statt Hamburg → Hannover für 30 € im ICE: mit dem D-Ticket bis Bremen (kostet
nichts extra), ab dort nur den Rest zahlen. Solche Vorschläge sind farblich
hervorgehoben und stehen mit ihrem **echten Gesamtpreis** in der Sortierung –
sie konkurrieren also fair mit den normalen Verbindungen.

Vorgeschlagen wird nur, was sich lohnt und machbar ist: mindestens 3 € Ersparnis,
höchstens 3 Stunden Mehrfahrzeit, mindestens 8 Minuten zum Umsteigen, und der
erste Teil muss nachweislich reiner Nahverkehr in Deutschland sein. Ist eine
Bedingung nicht erfüllt, erscheint kein Vorschlag – lieber keiner als ein
falscher.

## Auf dem Handy nutzen (gleiches WLAN)

`127.0.0.1` ist auf dem Handy **das Handy selbst** – dort läuft kein Server.
Damit das Handy den Rechner erreicht, muss der Server im Heimnetz hören:

```bash
python3 bahn-server.py --lan
```

Er zeigt dann zwei Adressen an:

```
   ▶  Auf diesem Rechner:  http://127.0.0.1:8899/
   ▶  Auf Handy/Tablet:    http://192.168.1.42:8899/
```

Die zweite Adresse auf dem Handy im Browser öffnen (Handy und Rechner im
selben WLAN). Die App merkt selbst, dass der Server dort steht.

**Was `--lan` bedeutet:** Ohne die Angabe hört der Server nur auf dem eigenen
Rechner – das ist der sichere Standard. Mit `--lan` kann ihn jedes Gerät im
selben Netz benutzen. Im Heim-WLAN ist das unbedenklich (er kann nur
Fahrpläne und Preise abfragen), im Café- oder Hotel-WLAN würde ich es
lassen.

## Wofür brauche ich den Server überhaupt noch?

Nur für **Bahnpreise**. Alles andere läuft über den Cloudflare-Worker und
funktioniert überall, auch wenn der Laptop aus ist:

| | Braucht den lokalen Server? |
|---|---|
| Bahnpreise (DB-Sparpreise) | **ja** – nur eine Wohn-IP kommt an der DB vorbei |
| Flüge, Bus, **Hotels**, Deals, KI-Empfehlung | nein |
| Fahrpläne (Bahn/Bus ohne Preis) | nein |

Heißt praktisch: Für „mal eben Flüge und Hotels vergleichen" reicht die
github.io-Seite auf dem Handy. Der Laptop muss nur an, wenn du **Bahnpreise**
sehen willst.

## Kann ich das Terminal-Fenster schließen?

**So wie gestartet: nein.** Der Server läuft im Vordergrund dieses Fensters –
schließt du es, ist er weg. Das Fenster darf aber in den Hintergrund, und du
kannst am Rechner normal weiterarbeiten.

**Wenn er ohne offenes Fenster laufen soll**, einmal so starten statt wie
oben:

```bash
nohup python3 ~/bahn-server.py --lan > ~/bahn-server.log 2>&1 &
sleep 2 && cat ~/bahn-server.log
```

Dann kannst du das Terminal schließen; der Server läuft weiter.

Was die Teile bedeuten: `nohup` = „nicht beenden, wenn das Fenster zugeht",
`&` = „im Hintergrund", der Rest schreibt die Ausgabe in eine Datei, damit
sie bei Problemen nachlesbar bleibt (`~/bahn-server.log`).

Die zweite Zeile wartet zwei Sekunden und zeigt dann die Startmeldung. Das
Warten gehört dazu: Liest man die Datei sofort, ist Python gerade erst am
Hochfahren und sie ist noch leer – das sieht aus wie ein Fehlstart, obwohl
alles läuft.

Stoppen geht dann nicht mehr mit `Strg`+`C`, sondern mit:

```bash
pkill -f bahn-server.py
```

**Zwei Dinge bleiben trotzdem:**

- **Der Laptop darf nicht schlafen.** Im Ruhezustand antwortet der Server
  nicht – für das Handy sieht das aus, als wäre er aus. Am Mac hilft
  `caffeinate -s` in einem zweiten Terminal, oder in den Systemeinstellungen
  den Ruhezustand bei Netzbetrieb abschalten.
- **Nach einem Neustart des Rechners ist er weg** und muss neu gestartet
  werden.

## Einmal einrichten, nie wieder anfassen (macOS)

Das Angenehmste: Der Server startet bei jeder Anmeldung von selbst, läuft im
Hintergrund und startet sich sogar neu, falls er abstürzt. Kein Terminal,
kein Befehl, nichts zu merken. macOS hat dafür `launchd`; man hinterlegt
einmal eine kleine Datei.

**Einmalig einrichten** – dieser Block darf am Stück eingefügt werden:

```bash
curl -sS -o ~/bahn-server.py https://raw.githubusercontent.com/kalivolut/hackyourtrip/main/bahn-local/server.py

mkdir -p ~/Library/LaunchAgents
cat > ~/Library/LaunchAgents/de.hackyourtrip.bahnserver.plist <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>de.hackyourtrip.bahnserver</string>
  <key>ProgramArguments</key>
  <array>
    <string>$(which python3)</string>
    <string>$HOME/bahn-server.py</string>
    <string>--lan</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$HOME/bahn-server.log</string>
  <key>StandardErrorPath</key><string>$HOME/bahn-server.log</string>
</dict>
</plist>
PLIST

pkill -f bahn-server.py 2>/dev/null
launchctl unload ~/Library/LaunchAgents/de.hackyourtrip.bahnserver.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/de.hackyourtrip.bahnserver.plist
sleep 2 && cat ~/bahn-server.log
```

Am Ende muss der Startkasten mit den beiden Adressen erscheinen. Danach:
**Terminal schließen, fertig.** Ab jetzt läuft er immer mit.

**Was die Datei bewirkt:** `RunAtLoad` = bei der Anmeldung starten,
`KeepAlive` = neu starten, falls er abstürzt, `ThrottleInterval` = zwischen
zwei Startversuchen 30 Sekunden warten (sonst würde ein dauerhafter Fehler
in einer Endlosschleife enden). Die Ausgabe landet weiter in
`~/bahn-server.log`.

**Läuft er gerade?**

```bash
curl -sS http://127.0.0.1:8899/health
```

**Server aktualisieren**, wenn ich etwas daran geändert habe:

```bash
curl -sS -o ~/bahn-server.py https://raw.githubusercontent.com/kalivolut/hackyourtrip/main/bahn-local/server.py
launchctl kickstart -k gui/$(id -u)/de.hackyourtrip.bahnserver
```

**Wieder abschalten:**

```bash
launchctl unload ~/Library/LaunchAgents/de.hackyourtrip.bahnserver.plist
rm ~/Library/LaunchAgents/de.hackyourtrip.bahnserver.plist
```

**Zwei Ehrlichkeiten dazu:** Der Agent startet bei der **Anmeldung** – nach
einem Neustart also, sobald du angemeldet bist. Und im **Ruhezustand**
antwortet er nicht; das ist keine Einstellungssache, sondern schläft der
ganze Rechner. Wer das Handy auch bei zugeklapptem Deckel bedienen will,
kommt um ein Dauergerät (Raspberry Pi, NAS) nicht herum.

## Später: rund um die Uhr (für Preisalarme)

Dieser Server liefert Preise, solange dein Rechner an ist. Für nächtliche
Preisalarme müsste er dauerhaft laufen – z.B. auf einem Raspberry Pi im
Heimnetz. Derselbe `server.py` läuft dort unverändert; in der App dann unter
`localStorage` den Schlüssel `bahnLocalUrl` auf die Adresse des Pi setzen
(z.B. `http://raspberrypi.local:8899`). Sag Bescheid, wenn du so weit bist –
das ist ein kleiner Zusatzschritt, kein Umbau.

## Fehlersuche

| Symptom | Ursache / Lösung |
|---|---|
| `403` / „gesperrt" in der Antwort | Du bist nicht auf einer Wohn-IP (VPN aus? nicht über einen Server?). Die DB lässt nur normale Heimanschlüsse durch. |
| App zeigt keine Live-Preise, nur „Preis unbekannt" | Fast immer: die App wurde über die **github.io**-Adresse geöffnet statt über `http://127.0.0.1:8899/`. Siehe unten. Zur Diagnose in der Browser-Konsole `await bahnLocalStatus()` eingeben. |
| `curl: command not found` | Sehr selten. Auf dem Mac über die Xcode-Command-Line-Tools nachinstallierbar. |
| Start endet sofort mit `exit 1` | Meist läuft der Server schon (anderes Fenster oder im Hintergrund) – Port 8899 ist dann belegt. Prüfen mit `cat ~/bahn-server.log`; dort steht der Grund im Klartext. Alten beenden: `pkill -f bahn-server.py`. |

## Technische Notiz

Nur Python-Standardbibliothek, keine Abhängigkeiten. Der einzige ausgehende
Verkehr sind die Abfragen an `int.bahn.de` – über `curl`, mit einer
Browser-Kennung, mit einem 5-Minuten-Cache, damit dieselbe Suche nicht doppelt
rausgeht (die DB verträgt ~60 Anfragen/Minute; ein Privatnutzer liegt weit
darunter). Die Antwort-Struktur (`angebotsPreis.betrag`,
`verbindungsDauerInSeconds`, `verbindungsAbschnitte[].verkehrsmittel.name`)
ist gegen eine echte Live-Antwort geprüft; die Parser-Tests stehen in
`check_server.py` (`python3 check_server.py`).

---

## Wichtig: die App **über den Server** öffnen

Nach dem Start steht im Terminal:

```
▶  App öffnen:  http://127.0.0.1:8899/
```

**Diese Adresse benutzen – nicht die github.io-Seite.**

Warum: Ruft man die App von ihrer öffentlichen `https`-Adresse auf, verbietet
Chrome ihr den Zugriff auf `http://127.0.0.1` („Mixed Content" bzw. „Private
Network Access"). Die Live-Preise bleiben dann ohne erkennbaren Grund aus –
und in der Oberfläche sieht das genauso aus, als liefe der Server gar nicht.

Kommt die Seite dagegen von diesem Server, sind Seite und Preisabfrage
dieselbe Herkunft: kein Mixed Content, kein CORS, keine Sonderregel. Die
beiden App-Dateien holt der Server von GitHub und legt sie daneben in `app/`
ab. Sie werden automatisch aufgefrischt (spätestens alle 15 Minuten), damit
nicht wochenlang eine alte Fassung stehenbleibt – ist gerade kein Internet
da, bleibt einfach die vorhandene Fassung in Betrieb.

Die github.io-Seite bleibt für alles andere nutzbar (Flug, Bus, Hotel,
Fahrplan) – nur die Bahn-Live-Preise brauchen den Aufruf über `127.0.0.1`.
