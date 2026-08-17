"""Tests fuer den lokalen Bahn-Preis-Server.

Der eigentliche curl-Aufruf wird gestubbt - getestet wird das, was uns
gehoert: dass die echte DB-Antwortstruktur (nachgebaut aus dem Live-Fund
Berlin->Muenchen, HTTP 201) korrekt auf die schlanke Form eingedampft wird,
und dass ein 403 als "blocked" durchkommt statt als kaputt.

Lauf:  python3 check_server.py
"""
import os
import pathlib
import sys
import tempfile
import time

import server


# Nachbau der echten Antwort (Feldnamen 1:1 aus dem Live-Test):
# angebotsPreis.betrag/waehrung, verbindungsDauerInSeconds, umstiegsAnzahl,
# verbindungsAbschnitte[].verkehrsmittel.name / abfahrtsOrt / ankunftsOrt.
REAL_SHAPE = {
    "verbindungen": [
        {
            "tripId": "abc",
            "umstiegsAnzahl": 0,
            "verbindungsDauerInSeconds": 14940,
            "angebotsPreis": {"betrag": 39.99, "waehrung": "EUR", "mwst": []},
            "angebotsPreisKlasse": "KLASSE_2",
            # Echte Form aus einer Live-Antwort: die Zeit steckt in einem
            # Objekt unter "sollzeit" - nicht als blanker String, und nicht
            # unter "zeit". Genau diese Annahme war einmal falsch geraten,
            # mit dem Ergebnis, dass jedes Angebot verworfen wurde.
            "verbindungsAbschnitte": [{
                "abfahrtsOrt": "Berlin Hbf",
                "ankunftsOrt": "München Hbf",
                "abfahrt": {"sollzeit": "2026-09-15T08:00:00"},
                "ankunft": {"sollzeit": "2026-09-15T12:09:00"},
                "verkehrsmittel": {"produktGattung": "ICE", "name": "ICE 1005",
                                    "richtung": "München Hbf"},
            }],
        },
        {
            # Eine Verbindung, zu der die DB keinen Preis nennt - muss als
            # price=None durchkommen, niemals als 0.
            "umstiegsAnzahl": 1,
            "verbindungsDauerInSeconds": 20400,
            "angebotsPreis": {},
            "verbindungsAbschnitte": [
                {"abfahrtsOrt": "Berlin Hbf", "ankunftsOrt": "Leipzig Hbf",
                 "abfahrt": {"sollzeit": "2026-09-15T09:00:00"},
                 "ankunft": {"sollzeit": "2026-09-15T10:15:00"},
                 "verkehrsmittel": {"produktGattung": "ICE", "name": "ICE 1701"}},
                {"abfahrtsOrt": "Leipzig Hbf", "ankunftsOrt": "München Hbf",
                 "abfahrt": {"sollzeit": "2026-09-15T10:30:00"},
                 "ankunft": {"sollzeit": "2026-09-15T14:40:00"},
                 "verkehrsmittel": {"produktGattung": "ICE", "name": "ICE 1005"}},
            ],
        },
    ],
}

results = []


def check(label, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok else f"\n      {detail}"))


# --- _trim_connection: echte Struktur -> schlanke Form ---------------------
first = server._trim_connection(REAL_SHAPE["verbindungen"][0])
check("Preis wird aus angebotsPreis.betrag gelesen", first["price"] == 39.99, str(first))
check("Waehrung kommt mit", first["currency"] == "EUR")
check("Dauer aus verbindungsDauerInSeconds", first["durationSeconds"] == 14940)
check("Klasse kommt mit", first["priceClass"] == "KLASSE_2")
check("umstiegsAnzahl 0 -> transfers 0", first["transfers"] == 0)
check("Abfahrtszeit aus dem ersten Abschnitt",
      first["depart"] == "2026-09-15T08:00:00", str(first["depart"]))
check("Ankunftszeit aus dem letzten Abschnitt",
      first["arrive"] == "2026-09-15T12:09:00", str(first["arrive"]))
check("Liniennummer aus verkehrsmittel.name",
      first["legs"][0]["line"] == "ICE 1005", str(first["legs"][0]))
check("Start-/Zielort im Abschnitt",
      first["legs"][0]["from"] == "Berlin Hbf" and first["legs"][0]["to"] == "München Hbf")

second = server._trim_connection(REAL_SHAPE["verbindungen"][1])
# Der wichtigste Test des ganzen Projekts, hier fuer die Bahn: kein Preis
# darf niemals als 0 erscheinen.
check("fehlender Preis -> None, niemals 0", second["price"] is None, str(second))
check("Umstieg wird gezaehlt", second["transfers"] == 1)
check("mehrere Abschnitte -> Abfahrt zuerst, Ankunft zuletzt",
      second["depart"] == "2026-09-15T09:00:00"
      and second["arrive"] == "2026-09-15T14:40:00", str(second))


# Der Fehler, der die Live-Preise unsichtbar machte: fehlt die Zeit, wirft
# die App das ganze Angebot weg - der Preis war da, aber unbrauchbar.
check("Abfahrtszeit ist gesetzt, nicht None", first["depart"] is not None, str(first))
check("Ankunftszeit ist gesetzt, nicht None", first["arrive"] is not None, str(first))

ez = server._trim_connection({
    "umstiegsAnzahl": 0,
    "verbindungsAbschnitte": [{
        "abfahrtsOrt": "A", "ankunftsOrt": "B",
        "abfahrt": {"sollzeit": "2026-09-15T08:00:00", "ezZeit": "2026-09-15T08:06:00"},
        "ankunft": {"sollzeit": "2026-09-15T09:00:00"},
        "verkehrsmittel": {"name": "RE 2"},
    }],
})
check("Sollzeit wird bevorzugt (bei Zukunftssuchen gibt es keine Echtzeit)",
      ez["depart"] == "2026-09-15T08:00:00", str(ez))

# --- Zeitfeld als blanker String (Robustheit) ------------------------------
obj_time = server._trim_connection({
    "umstiegsAnzahl": 0,
    "verbindungsAbschnitte": [{
        "abfahrtsOrt": "A", "ankunftsOrt": "B",
        "abfahrt": "2026-09-15T07:00:00",
        "ankunft": {"zeitpunkt": "2026-09-15T08:00:00"},
        "verkehrsmittel": {"name": "RE 1"},
    }],
})
check("blanker String und andere Objekt-Schluessel gehen ebenso",
      obj_time["depart"] == "2026-09-15T07:00:00"
      and obj_time["arrive"] == "2026-09-15T08:00:00", str(obj_time))


# --- get_fahrplan: Body-Bau + Nutzung des gestubbten curl ------------------
captured = {}


def fake_curl(method, url, body=None):
    captured["method"] = method
    captured["url"] = url
    captured["body"] = body
    return REAL_SHAPE


server._curl = fake_curl
server._cache.clear()
out = server.get_fahrplan("A=1@L=8011160@", "A=1@L=8000261@",
                          "2026-09-15T08:00:00", "2")
check("fahrplan liefert die eingedampften Verbindungen",
      len(out["connections"]) == 2 and out["connections"][0]["price"] == 39.99)
check("POST geht an den fahrplan-Endpunkt",
      captured["method"] == "POST" and captured["url"].endswith("/angebote/fahrplan"))
check("Halte-IDs landen im Body",
      captured["body"]["abfahrtsHalt"] == "A=1@L=8011160@"
      and captured["body"]["ankunftsHalt"] == "A=1@L=8000261@")
check("2. Klasse als Standard", captured["body"]["klasse"] == "KLASSE_2")
check("Regionalverkehr bleibt in den Produktgattungen",
      "REGIONAL" in captured["body"]["produktgattungen"])

server._cache.clear()
server.get_fahrplan("a", "b", "2026-09-15T08:00:00", "1")
check("erste Klasse wird durchgereicht", captured["body"]["klasse"] == "KLASSE_1")


# --- Datum deuten ----------------------------------------------------------
check("blankes Datum meint den ganzen Tag",
      server._parse_when("2026-09-15") == ("tag", "2026-09-15"))
check("voller Zeitstempel meint genau diesen Moment",
      server._parse_when("2026-09-15T14:30:00") == ("moment", "2026-09-15T14:30:00"))
check("Unfug-Datum -> None", server._parse_when("15.09.2026") is None)
check("leer -> None", server._parse_when("") is None)


# --- Ganztags-Suche: mehrere Anker statt einer 08:00-Seite -----------------
# Die echte Beschwerde: "nur 6 Angebote auf einen ganzen Tag und die
# teuersten" - weil eine einzige DB-Seite ab 08:00 geholt wurde. Jetzt muss
# ein blankes Datum den Tag an mehreren Ankerzeiten abklappern.
def _conn(depart, arrive, price, line="ICE 1", transfers=0):
    return {
        "umstiegsAnzahl": transfers,
        "verbindungsDauerInSeconds": 10000,
        "angebotsPreis": {"betrag": price, "waehrung": "EUR"} if price is not None else {},
        "verbindungsAbschnitte": [{
            "abfahrtsOrt": "Berlin Hbf", "ankunftsOrt": "München Hbf",
            "abfahrt": {"sollzeit": depart}, "ankunft": {"sollzeit": arrive},
            "verkehrsmittel": {"produktGattung": "ICE", "name": line},
        }],
    }


# Jede Ankerzeit bekommt ihre eigene Seite. Die 09:00-Seite wiederholt eine
# Verbindung der 05:00-Seite - einmal teurer (anderes Kontingent) - und die
# 21:00-Seite laeuft in den Folgetag ueber.
SEITEN = {
    "2026-09-15T00:00:00": [_conn("2026-09-15T04:30:00", "2026-09-15T08:30:00", 27.99)],
    "2026-09-15T05:00:00": [_conn("2026-09-15T06:00:00", "2026-09-15T10:00:00", 39.99, "ICE 501")],
    "2026-09-15T09:00:00": [
        _conn("2026-09-15T06:00:00", "2026-09-15T10:00:00", 59.99, "ICE 501"),
        _conn("2026-09-15T10:00:00", "2026-09-15T14:00:00", 49.99, "ICE 901"),
    ],
    "2026-09-15T13:00:00": [_conn("2026-09-15T14:00:00", "2026-09-15T18:00:00", None, "ICE 1301")],
    "2026-09-15T17:00:00": [
        # dieselbe Verbindung wie um 13:00, diesmal MIT Preis - der muss
        # die preislose Fassung ersetzen.
        _conn("2026-09-15T14:00:00", "2026-09-15T18:00:00", 44.99, "ICE 1301"),
    ],
    "2026-09-15T21:00:00": [
        _conn("2026-09-15T22:00:00", "2026-09-16T06:00:00", 29.99, "NJ 40421"),
        _conn("2026-09-16T05:00:00", "2026-09-16T09:00:00", 19.99, "ICE 501"),
    ],
}
anfragen = []


def fan_curl(method, url, body=None):
    anfragen.append(body["anfrageZeitpunkt"])
    return {"verbindungen": SEITEN.get(body["anfrageZeitpunkt"], [])}


server._curl = fan_curl
server._cache.clear()
tag = server.get_fahrplan_ganztag("a", "b", "2026-09-15", "2")
departs = [c["depart"] for c in tag["connections"]]
preise = {c["depart"]: c["price"] for c in tag["connections"]}

check("jede Ankerzeit wird abgefragt",
      anfragen == [f"2026-09-15T{a}" for a in server.DAY_ANCHORS], str(anfragen))
check("die Seiten werden zusammengelegt und nach Abfahrt sortiert",
      departs == sorted(departs) and len(departs) == 5, str(departs))
check("der fruehe Zug vor 05:00 ist dabei (00:00-Anker)",
      "2026-09-15T04:30:00" in departs, str(departs))
check("die Dublette zaehlt nur einmal", departs.count("2026-09-15T06:00:00") == 1)
check("bei Dubletten gewinnt der bessere Preis (Kontingente)",
      preise["2026-09-15T06:00:00"] == 39.99, str(preise))
check("ein spaeter gefundener Preis ersetzt die preislose Fassung",
      preise["2026-09-15T14:00:00"] == 44.99, str(preise))
check("Verbindungen des Folgetags fliegen raus",
      "2026-09-16T05:00:00" not in departs, str(departs))
check("der Nachtzug am Abend des Tages bleibt aber drin",
      "2026-09-15T22:00:00" in departs, str(departs))

# Der zweite Lauf muss komplett aus dem Cache kommen - sechs Anker duerfen
# nicht sechs neue DB-Anfragen je Wiederholung heissen.
anfragen.clear()
tag2 = server.get_fahrplan_ganztag("a", "b", "2026-09-15", "2")
check("Wiederholung kostet keine neue DB-Anfrage",
      anfragen == [] and len(tag2["connections"]) == 5, str(anfragen))

# Die Split-Ticket-Reststrecke fragt mit vollem Zeitstempel - dort zaehlt
# die Anschlusszeit, ein Faecher ueber den ganzen Tag waere falsch.
anfragen.clear()
server._cache.clear()
server.get_fahrplan("a", "b", "2026-09-15T14:30:00", "2")
check("voller Zeitstempel bleibt genau EINE Anfrage",
      anfragen == ["2026-09-15T14:30:00"], str(anfragen))


# --- ein 403 der DB wird als BahnError(403) gemeldet -----------------------
def curl_403(method, url, body=None):
    raise server.BahnError("gesperrt", 403)


server._curl = curl_403
server._cache.clear()
try:
    server.get_fahrplan("a", "b", "2026-09-15T08:00:00", "2")
    check("403 wird als Fehler durchgereicht", False, "keine Exception")
except server.BahnError as exc:
    check("403 bleibt als 403 erkennbar", exc.status == 403)


# --- Die App darf nicht auf einer alten Fassung stehenbleiben -------------
# Ohne Nachladen bliebe eine einmal heruntergeladene app.js ewig liegen: die
# App wuerde weiter funktionieren, nur eben in der Fassung von vor Wochen.
# Genau deshalb wird hier geprueft, wann nachgeladen wird - und wann nicht.
with tempfile.TemporaryDirectory() as tmp:
    server._app_dir = pathlib.Path(tmp)
    calls = []

    def fake_download(name, path):
        calls.append(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"neu")
        return b"neu"

    server._download_app_file = fake_download

    check("fehlende Datei wird geholt", server._app_file("app.js") == b"neu")
    check("dabei genau ein Download", calls == ["app.js"], str(calls))

    # Frisch heruntergeladen: kein zweiter Download.
    check("frische Datei kommt von der Platte", server._app_file("app.js") == b"neu")
    check("und loest keinen Download aus", calls == ["app.js"], str(calls))

    # Zeitstempel zurueckdrehen -> als veraltet behandeln.
    old = server._app_dir / "app.js"
    stale = time.time() - server.APP_MAX_AGE_S - 60
    os.utime(old, (stale, stale))
    check("veraltete Datei wird nachgeladen", server._app_file("app.js") == b"neu")
    check("dabei ein zweiter Download", calls == ["app.js", "app.js"], str(calls))

    # Ohne Netz: die vorhandene Fassung bleibt, statt die Seite zu killen.
    old.write_bytes(b"alt")
    os.utime(old, (stale, stale))
    server._download_app_file = lambda name, path: None
    check("ohne Netz wird die alte Fassung ausgeliefert",
          server._app_file("app.js") == b"alt")
    check("und der Zeitstempel wird zurueckgesetzt, damit nicht jeder "
          "Aufruf in den Timeout laeuft",
          time.time() - old.stat().st_mtime < 5)


# --- /info: die Adress-Auskunft fuer die Einrichtungs-Karte ---------------
# Die App baut daraus QR-Code und Einrichtungslink. Ohne --lan darf keine
# Heimnetz-Adresse versprochen werden - der Server hoert dann nur lokal.
import json as _json
import threading
import urllib.request

_info_srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
_info_thread = threading.Thread(target=_info_srv.serve_forever, daemon=True)
_info_thread.start()
_info_port = _info_srv.server_address[1]
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{_info_port}/info", timeout=5) as resp:
        info = _json.load(resp)
    check("/info weist sich als unser Dienst aus",
          info.get("service") == "hackyourtrip-bahn", str(info))
    check("/info ohne --lan: lanMode false, keine Adresse versprochen",
          info.get("lanMode") is False and info.get("lanUrl") is None, str(info))
    with urllib.request.urlopen(f"http://127.0.0.1:{_info_port}/health", timeout=5) as resp:
        health = _json.load(resp)
    check("/health bleibt unveraendert", health.get("ok") is True, str(health))
finally:
    _info_srv.shutdown()


# --- Ein belegter Port muss sich erklaeren ---------------------------------
# Mit `nohup ... &` gestartet sieht man im Terminal nur "exit 1"; ein
# Traceback verschwindet unsichtbar in der Logdatei. Genau dann braucht die
# Meldung Klartext - sonst steht man vor einem Server, der einfach nicht
# startet, ohne jeden Anhaltspunkt.
import io
import socket
from contextlib import redirect_stdout

belegt = socket.socket()
belegt.bind(("127.0.0.1", 0))
belegt.listen(1)
_port, _host = server.PORT, server.HOST
server.PORT, server.HOST = belegt.getsockname()[1], "127.0.0.1"
ausgabe = io.StringIO()
try:
    with redirect_stdout(ausgabe):
        server.main()
    code = None
except SystemExit as exc:
    code = exc.code
finally:
    server.PORT, server.HOST = _port, _host
    belegt.close()
text = ausgabe.getvalue()

check("belegter Port beendet den Start mit Fehlercode", code == 1, repr(code))
check("und sagt im Klartext, was los ist", "bereits belegt" in text, text)
check("nennt den wahrscheinlichsten Grund", "läuft schon" in text, text)
check("und wie man den alten beendet", "pkill -f bahn-server.py" in text, text)
check("kein Traceback", "Traceback" not in text, text)


print(f"\n{sum(results)}/{len(results)} checks bestanden")
sys.exit(0 if all(results) else 1)
