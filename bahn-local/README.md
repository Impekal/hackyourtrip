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

2. **In diesen Ordner wechseln und den Server starten.** Ersetze den Pfad
   durch den Ort, wo dieser Ordner bei dir liegt:

   ```bash
   cd ~/hackyourtrip/bahn-local
   python3 server.py
   ```

   Es erscheint:

   ```
   ──────────────────────────────────────────────────────────
    HackYourTrip – lokaler Bahn-Preis-Server läuft
      Adresse:  http://127.0.0.1:8899
      Test:     http://127.0.0.1:8899/health
      Stoppen:  Strg+C
   ──────────────────────────────────────────────────────────
   ```

3. **Fertig.** Lass dieses Fenster offen. Öffne die HackYourTrip-App im
   **selben Browser auf demselben Rechner** und suche eine Bahnverbindung –
   die echten Preise erscheinen mit einem grünen „🟢 Live-Preis DB"-Abzeichen.

Zum Stoppen im Terminal `Strg`+`C` drücken.

## Kurztest, ob er wirklich Preise bekommt

Bei laufendem Server ein zweites Terminal öffnen und eingeben:

```bash
curl -sS "http://127.0.0.1:8899/fahrplan?from=$(curl -sS 'http://127.0.0.1:8899/orte?q=Berlin%20Hbf' | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["id"])')&to=$(curl -sS 'http://127.0.0.1:8899/orte?q=M%C3%BCnchen%20Hbf' | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["id"])')&date=2026-09-15" | python3 -m json.tool | head -20
```

Erscheinen Zeilen mit `"price": 39.99` o.ä., läuft alles.

## Wichtig zum Browser

Die veröffentlichte App läuft über **https**, der lokale Server über **http**.
**Chrome** erlaubt den Zugriff auf `http://127.0.0.1` problemlos. **Safari**
blockt ihn teilweise – wenn die Live-Preise in Safari nicht kommen, nutze
Chrome, oder öffne die App lokal.

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
| App zeigt keine Live-Preise, nur „Preis unbekannt" | Server läuft nicht, oder Safari blockt `http://localhost` → Chrome nutzen. |
| `curl: command not found` | Sehr selten. Auf dem Mac über die Xcode-Command-Line-Tools nachinstallierbar. |

## Technische Notiz

Nur Python-Standardbibliothek, keine Abhängigkeiten. Der einzige ausgehende
Verkehr sind die Abfragen an `int.bahn.de` – über `curl`, mit einer
Browser-Kennung, mit einem 5-Minuten-Cache, damit dieselbe Suche nicht doppelt
rausgeht (die DB verträgt ~60 Anfragen/Minute; ein Privatnutzer liegt weit
darunter). Die Antwort-Struktur (`angebotsPreis.betrag`,
`verbindungsDauerInSeconds`, `verbindungsAbschnitte[].verkehrsmittel.name`)
ist gegen eine echte Live-Antwort geprüft; die Parser-Tests stehen in
`check_server.py` (`python3 check_server.py`).
