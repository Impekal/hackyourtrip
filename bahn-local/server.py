#!/usr/bin/env python3
"""HackYourTrip – lokaler Bahn-Preis-Server.

Warum das existiert
-------------------
Die Deutsche Bahn gibt keine offizielle Preis-API heraus und sperrt jede
automatisierte Abfrage von Server-/Rechenzentrums-IPs (gemessen: Cloudflare,
GitHub-Runner und ein Ionos-VPS bekommen alle `403 OPS_BLOCKED`). Von einer
**Wohn-IP** aus geht es dagegen – der bahn.de-Endpunkt `int.bahn.de` antwortet
dort mit echten Sparpreisen.

Es gibt aber einen zweiten Filter: die DB erkennt auch den TLS-/HTTP-
Fingerabdruck des Clients. Gemessen auf ein und derselben Maschine, derselben
IP, demselben Endpunkt:

    curl                  -> HTTP 201, echte Preise  ("betrag": 39.99)
    Node (db-vendo-client)-> HTTP 403 Forbidden

`curl` sieht für die DB aus wie ein Browser, Nodes (und Pythons) eigener
TLS-Stack nicht. Deshalb macht dieser Server die Abfrage **nicht** selbst,
sondern ruft das System-`curl` als Unterprozess auf – exakt der Fingerabdruck,
der nachweislich durchkommt.

Was er ist
----------
Ein winziger, nur-lokaler HTTP-Server (nur Python-Standardbibliothek, kein
`pip install`). Er läuft auf deinem eigenen Rechner, hört ausschließlich auf
127.0.0.1 und stellt der HackYourTrip-Weboberfläche drei Endpunkte bereit:

    GET /health                      -> {"ok": true}
    GET /orte?q=Berlin Hbf           -> Stationsliste (id, name, extId)
    GET /fahrplan?from=<id>&to=<id>&date=YYYY-MM-DD[THH:MM:SS]&class=2
                                     -> Verbindungen mit echtem Preis

Und – der entscheidende Teil – er liefert die App gleich selbst aus:

    GET /                            -> die HackYourTrip-Oberfläche

Das ist kein Komfort, sondern notwendig. Ruft man die App von ihrer
öffentlichen https-Adresse auf, verbietet Chrome ihr den Zugriff auf
`http://127.0.0.1` ("Mixed Content" bzw. "Private Network Access") – die
Live-Preise bleiben dann ohne erkennbaren Grund aus, und in der Oberfläche
sieht das genauso aus, als liefe dieser Server gar nicht. Kommt die Seite
dagegen von *hier*, sind Seite und Preisabfrage dieselbe Herkunft: kein
Mixed Content, kein CORS, keine Sonderregel. Die beiden App-Dateien werden
beim ersten Aufruf von GitHub geholt und daneben zwischengespeichert.

Starten:  python3 server.py
Danach:   http://127.0.0.1:8899/ im Browser öffnen
Stoppen:  Strg+C

Nichts davon verlässt deinen Rechner ausser den Abfragen an bahn.de selbst –
die App im Browser holt die Preise von hier, und die DB sieht deine normale
Wohn-IP wie bei einem Besuch auf bahn.de.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

# Standard: nur der eigene Rechner. Mit `--lan` hört der Server auf allen
# Schnittstellen, damit Handy und Tablet im selben WLAN ihn erreichen -
# bewusst nicht der Standard, denn dann kann jedes Gerät im Netz ihn
# benutzen. Im Heim-WLAN ist das unbedenklich, im Café-WLAN nicht.
LAN_MODE = "--lan" in sys.argv
HOST = "0.0.0.0" if LAN_MODE else "127.0.0.1"
PORT = 8899

# Der Endpunkt, den bahn.de selbst benutzt (dbweb-Profil von db-vendo-client).
BAHN_BASE = "https://int.bahn.de/web/api"

# Die Browser-Kennung, die im Live-Test durchkam. Ein reiner Skript-UA
# ("python", "curl/8.x") wird eher gesperrt.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0.0.0 Safari/537.36")

# Die DB verträgt grob 60 Anfragen/Minute. Ein Privatnutzer liegt weit
# darunter, aber ein kleiner Cache verhindert, dass dieselbe Suche (z.B. beim
# Umsortieren in der App) doppelt rausgeht.
CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, object]] = {}

# Alle Produktgattungen: der günstige Preis ist oft genau die langsame
# Regionalverbindung, die nicht ausgeblendet werden darf.
PRODUKTGATTUNGEN = ["ICE", "EC_IC", "IR", "REGIONAL", "SBAHN", "BUS",
                    "SCHIFF", "UBAHN", "TRAM", "ANRUFPFLICHTIG"]

# Genau die Gattungen, die das Deutschland-Ticket abdeckt. Fuer die Frage
# "komme ich da auch ohne Fernverkehr hin?" - der Kern des Spar-Tricks,
# eine Fahrkarte aufzuteilen.
D_TICKET_PRODUKTGATTUNGEN = ["REGIONAL", "SBAHN", "BUS", "UBAHN", "TRAM"]

CURL_TIMEOUT_SECONDS = 30


class BahnError(Exception):
    """Upstream hat nicht mit brauchbarem JSON geantwortet."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _curl(method: str, url: str, body: dict | None = None) -> object:
    """Eine Anfrage über das System-curl – der Fingerabdruck, der durchkommt.

    Rückgabe ist das geparste JSON. Ein 403 der DB wird als BahnError(403)
    weitergereicht, damit die App "geblockt" von "kaputt" unterscheiden kann.
    """
    cmd = [
        "curl", "-sS", "--compressed", "--max-time", str(CURL_TIMEOUT_SECONDS),
        "-X", method, url,
        "-H", "Accept: application/json",
        "-H", "Accept-Language: de",
        "-H", f"User-Agent: {USER_AGENT}",
        # Statuscode getrennt vom Body, damit ein 403 erkennbar ist, auch
        # wenn der Body leer oder komprimierter Müll ist.
        "-w", "\n%{http_code}",
    ]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=CURL_TIMEOUT_SECONDS + 5)
    except FileNotFoundError:
        raise BahnError("curl ist nicht installiert.", 500)
    except subprocess.TimeoutExpired:
        raise BahnError("Zeitüberschreitung bei der Bahn-Anfrage.", 504)

    if proc.returncode != 0:
        raise BahnError(f"curl-Fehler: {proc.stderr.strip()[:200]}", 502)

    raw = proc.stdout
    newline = raw.rfind("\n")
    status_text = raw[newline + 1:].strip() if newline != -1 else ""
    payload_text = raw[:newline] if newline != -1 else raw
    try:
        status = int(status_text)
    except ValueError:
        status = 0

    if status == 403:
        raise BahnError("Die DB hat diese Abfrage gesperrt (403).", 403)
    if status and status >= 400 and status not in (200, 201):
        raise BahnError(f"Bahn antwortete mit HTTP {status}.", 502)

    try:
        return json.loads(payload_text)
    except json.JSONDecodeError:
        raise BahnError("Antwort der Bahn war kein JSON.", 502)


def _first(d: dict, *keys):
    """Erster vorhandener, nicht-leerer Wert unter mehreren möglichen Keys.

    Die DB benennt Zeit-/Ortsfelder je nach Abschnitt uneinheitlich; so bleibt
    der Parser robust, statt an einem einzelnen Key zu zerbrechen.
    """
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def _leg_time(leg: dict, *keys):
    """Eine Zeitangabe aus einem Abschnitt lesen.

    Gemessen an einer echten Antwort sieht das so aus:

        "abfahrt": {"sollzeit": "2026-09-15T08:36:00"}

    Der Zeitpunkt steckt also in einem Objekt, und der Schlüssel heißt
    `sollzeit` – nicht `zeit`. `ezZeit` ist die Echtzeit-Prognose, wo
    vorhanden; bei einer Suche Wochen im Voraus gibt es sie nicht, deshalb
    ist die Sollzeit der verlässliche Anker. Die übrigen Namen bleiben als
    Auffangnetz stehen, falls die DB eine Variante liefert.
    """
    value = _first(leg, *keys)
    if isinstance(value, dict):
        return _first(value, "sollzeit", "ezZeit", "zeit", "zeitpunkt",
                      "abfahrtsZeitpunkt", "ankunftsZeitpunkt")
    return value


def _trim_connection(conn: dict) -> dict:
    """Eine DB-Verbindung auf das reduzieren, was die App braucht.

    Der Preis kommt ehrlich als `null` durch, wenn die DB keinen nennt
    (z.B. reine Auskunft ohne Angebot) – nie als 0, das wäre eine Lüge.
    """
    preis = conn.get("angebotsPreis") or {}
    betrag = preis.get("betrag")
    legs_raw = conn.get("verbindungsAbschnitte") or []

    legs = []
    for leg in legs_raw:
        vm = leg.get("verkehrsmittel") or {}
        # Zwischenhalte mitgeben: sie sind die Kandidaten fuers Aufteilen
        # der Fahrkarte ("mit D-Ticket bis Bremen, ab da erst zahlen").
        # Ohne sie muesste die App raten, wo eine Verbindung teilbar waere.
        halts = []
        for halt in (leg.get("halte") or []):
            name = halt.get("name")
            if name:
                halts.append({"name": name, "id": halt.get("id"),
                              "extId": halt.get("extId")})
        legs.append({
            "line": _first(vm, "name", "displayName", "kategorie") or "",
            "product": vm.get("produktGattung") or "",
            "from": _first(leg, "abfahrtsOrt", "abfahrtsOrtName") or "",
            "to": _first(leg, "ankunftsOrt", "ankunftsOrtName") or "",
            "depart": _leg_time(leg, "abfahrt", "abfahrtsZeitpunkt"),
            "arrive": _leg_time(leg, "ankunft", "ankunftsZeitpunkt"),
            "halts": halts,
        })

    depart = legs[0]["depart"] if legs else None
    arrive = legs[-1]["arrive"] if legs else None
    # Nur echte Zug-/Bus-Abschnitte zählen als Umstieg; die DB liefert
    # umstiegsAnzahl direkt, das ist verlässlicher als legs zu zählen.
    transfers = conn.get("umstiegsAnzahl")
    if transfers is None:
        transfers = max(len(legs) - 1, 0)

    return {
        "price": betrag,
        "currency": preis.get("waehrung") or "EUR",
        "priceClass": conn.get("angebotsPreisKlasse"),
        "durationSeconds": conn.get("verbindungsDauerInSeconds"),
        "transfers": transfers,
        "depart": depart,
        "arrive": arrive,
        "legs": legs,
    }


def get_orte(query: str) -> object:
    key = f"orte:{query.lower()}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]
    url = (f"{BAHN_BASE}/reiseloesung/orte?suchbegriff={quote(query)}"
           "&typ=ALL&limit=8")
    data = _curl("GET", url)
    # Auf das Nötige eindampfen: id (für /fahrplan), Name, EVA-Nummer.
    slim = [{"id": o.get("id"), "name": o.get("name"),
             "extId": o.get("extId"), "products": o.get("products")}
            for o in (data or []) if isinstance(o, dict) and o.get("id")]
    _cache[key] = (time.time(), slim)
    return slim


def get_fahrplan(from_id: str, to_id: str, when: str, klasse: str,
                  products: str = "") -> object:
    key = f"fahrplan:{from_id}|{to_id}|{when}|{klasse}|{products}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]

    # `products=regional` sucht gezielt Nahverkehr. Ohne das liefert die DB
    # bevorzugt schnelle Fernverbindungen - fuer die Frage "geht das auch mit
    # dem Deutschland-Ticket?" also genau das Falsche.
    regional_only = products == "regional"
    body = {
        "abfahrtsHalt": from_id,
        "ankunftsHalt": to_id,
        "anfrageZeitpunkt": when,
        "ankunftSuche": "ABFAHRT",
        "klasse": "KLASSE_1" if klasse == "1" else "KLASSE_2",
        "produktgattungen": D_TICKET_PRODUKTGATTUNGEN if regional_only else PRODUKTGATTUNGEN,
        "reisende": [{"typ": "ERWACHSENER",
                      "ermaessigungen": [{"art": "KEINE_ERMAESSIGUNG",
                                           "klasse": "KLASSENLOS"}],
                      "alter": [], "anzahl": 1}],
        # Bei der Nahverkehrssuche waere "schnell" kontraproduktiv:
        # gesucht ist die guenstige Verbindung, nicht die schnellste.
        "schnelleVerbindungen": not regional_only,
        "sitzplatzOnly": False,
        "bikeCarriage": False,
        "reservierungsKontingenteVorhanden": False,
    }
    data = _curl("POST", f"{BAHN_BASE}/angebote/fahrplan", body)
    conns = (data or {}).get("verbindungen") or []
    trimmed = [_trim_connection(c) for c in conns]

    # Ein Angebot ohne Abfahrtszeit wird von der App verworfen - der Preis
    # ist dann da, aber unbrauchbar, und in der Oberfläche sieht es aus wie
    # "keine Live-Preise". Genau das ist einmal passiert, weil der
    # Zeit-Schlüssel geraten statt gelesen war. Deshalb wird es hier laut:
    # lieber eine Warnung im Terminal als stilles Verschwinden.
    if conns and not any(c["depart"] for c in trimmed):
        sample = (conns[0].get("verbindungsAbschnitte") or [{}])[0]
        print("  ⚠️  Keine Abfahrtszeit lesbar - die App wird diese Angebote "
              "verwerfen. Abschnitt-Felder:", sorted(sample.keys())[:12],
              file=sys.stderr)

    result = {"connections": trimmed}
    _cache[key] = (time.time(), result)
    return result


# --- Die App selbst ausliefern ---------------------------------------------
# Damit Seite und Preisabfrage dieselbe Herkunft haben (siehe Modul-Doku).
# Die Dateien liegen neben diesem Skript und werden von GitHub geholt.
#
# Sie werden bewusst nachgeladen, nicht nur einmalig: die App wird
# weiterentwickelt, und eine einmal heruntergeladene app.js bliebe sonst
# ewig stehen. Der Nutzer saehe eine alte Fassung, ohne dass irgendetwas
# kaputt aussieht - der aergerlichste Fehlerfall ueberhaupt. Ohne Internet
# wird die vorhandene Fassung weiterbenutzt; ein Update ist nichts, wofuer
# die App ausfallen darf.
APP_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}
APP_SOURCE = "https://raw.githubusercontent.com/kalivolut/hackyourtrip/main/docs/"
APP_MAX_AGE_S = 900
_app_dir = Path(__file__).resolve().parent / "app"


def _download_app_file(name: str, path: Path) -> bytes | None:
    try:
        _app_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["curl", "-sS", "-f", "--max-time", "30", APP_SOURCE + name],
            capture_output=True, timeout=40)
        if proc.returncode != 0 or not proc.stdout:
            return None
        changed = not path.exists() or path.read_bytes() != proc.stdout
        path.write_bytes(proc.stdout)
        if changed:
            print(f"  App-Datei aktualisiert: {name} ({len(proc.stdout)} Bytes)")
        return proc.stdout
    except Exception:
        return None


def _app_file(name: str) -> bytes | None:
    """Datei aus dem lokalen App-Ordner, regelmaessig frisch von GitHub."""
    path = _app_dir / name
    if path.exists():
        try:
            fresh = (time.time() - path.stat().st_mtime) < APP_MAX_AGE_S
        except OSError:
            fresh = False
        if fresh:
            return path.read_bytes()
        # Abgelaufen: neu holen, aber die alte Fassung nicht wegwerfen,
        # falls gerade kein Netz da ist.
        data = _download_app_file(name, path)
        if data is None:
            # Ohne Netz laeuft curl in jeden Timeout - das darf nicht bei
            # jedem Seitenaufruf passieren. Der Zeitstempel bedeutet hier
            # "zuletzt nachgesehen", nicht "zuletzt geaendert".
            try:
                path.touch()
            except OSError:
                pass
            return path.read_bytes()
        return data
    return _download_app_file(name, path)


def _widen_date(raw: str) -> str | None:
    """Blankes Datum -> voller Zeitstempel; volles durchlassen; sonst None."""
    if not raw:
        return None
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return f"{raw}T08:00:00"
    if len(raw) == 19 and raw[10] == "T":
        return raw
    return None


class Handler(BaseHTTPRequestHandler):
    # Ausgabe ruhig halten – eine Zeile pro Anfrage reicht.
    def log_message(self, fmt, *args):
        sys.stderr.write("  " + (fmt % args) + "\n")

    def _send(self, status: int, payload: object):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # Nur-lokaler Dienst mit öffentlichen Fahrplandaten – jede Origin darf
        # lesen, damit die veröffentlichte App (https) hierher darf.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # Chromes "Private Network Access": eine oeffentliche https-Seite darf
        # nur dann auf 127.0.0.1 zugreifen, wenn der lokale Dienst es
        # ausdruecklich erlaubt. Ohne diesen Header blockt Chrome die Abfrage,
        # und in der App saehe es aus, als liefe der Server gar nicht.
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802 (Framework-Signatur)
        self._send(204, {})

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/")
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        # Die App zuerst: sie kommt von hier, damit sie die Preisabfrage
        # unten ohne Browser-Sonderregeln erreichen darf.
        app_entry = APP_FILES.get(parsed.path) or APP_FILES.get(route or "/")
        if app_entry:
            name, content_type = app_entry
            data = _app_file(name)
            if data is None:
                return self._send(503, {
                    "error": f"App-Datei {name} liess sich nicht laden. "
                             "Internetverbindung pruefen."})
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            # Nicht zwischenspeichern: sonst haengt nach einem Update die
            # alte Fassung im Browser fest, was die Fehlersuche verdirbt.
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)

        try:
            if route == "/health":
                return self._send(200, {"ok": True, "service": "hackyourtrip-bahn"})
            if route == "/orte":
                q = (params.get("q") or "").strip()
                if not q:
                    return self._send(400, {"error": "q fehlt"})
                return self._send(200, get_orte(q))
            if route == "/fahrplan":
                from_id = params.get("from")
                to_id = params.get("to")
                when = _widen_date(params.get("date", ""))
                if not (from_id and to_id and when):
                    return self._send(400, {
                        "error": "from, to und date (YYYY-MM-DD) noetig."})
                return self._send(200, get_fahrplan(
                    from_id, to_id, when, params.get("class", "2"),
                    params.get("products", "")))
            return self._send(404, {"error": "Unbekannter Endpunkt."})
        except BahnError as exc:
            self._send(exc.status, {"error": str(exc),
                                    "blocked": exc.status == 403})
        except Exception as exc:  # defensiv: nie den Server umbringen
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})


def _lan_address() -> str | None:
    """Die eigene Adresse im Heimnetz – die, die das Handy braucht.

    Ohne echten Verbindungsaufbau: ein UDP-Socket „verbinden" wählt nur die
    passende Netzwerkkarte aus, es wird kein Paket verschickt.
    """
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))  # reservierte Testadresse, nie erreichbar
        ip = s.getsockname()[0]
        s.close()
        return ip if not ip.startswith("127.") else None
    except Exception:
        return None


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("─" * 60)
    print(" HackYourTrip – lokaler Bahn-Preis-Server läuft")
    print("")
    print(f"   ▶  Auf diesem Rechner:  http://127.0.0.1:{PORT}/")
    if LAN_MODE:
        lan = _lan_address()
        if lan:
            print(f"   ▶  Auf Handy/Tablet:    http://{lan}:{PORT}/")
            print("      (Gerät muss im selben WLAN sein)")
        else:
            print("   ⚠️  Keine Heimnetz-Adresse gefunden – ist WLAN aktiv?")
    else:
        print("")
        print("   Für Handy/Tablet im selben WLAN neu starten mit:")
        print("      python3 bahn-server.py --lan")
    print("")
    print("      Diese Adressen benutzen – nicht die github.io-Seite,")
    print("      sonst blockt der Browser die Live-Preise.")
    print("")
    print(f"   Test:     http://127.0.0.1:{PORT}/health")
    print("   Stoppen:  Strg+C")
    print("─" * 58)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nGestoppt.")
        server.shutdown()


if __name__ == "__main__":
    main()
