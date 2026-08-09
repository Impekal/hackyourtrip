"""Tests fuer den lokalen Bahn-Preis-Server.

Der eigentliche curl-Aufruf wird gestubbt - getestet wird das, was uns
gehoert: dass die echte DB-Antwortstruktur (nachgebaut aus dem Live-Fund
Berlin->Muenchen, HTTP 201) korrekt auf die schlanke Form eingedampft wird,
und dass ein 403 als "blocked" durchkommt statt als kaputt.

Lauf:  python3 test_server.py
"""
import sys

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


# --- Datum weiten ----------------------------------------------------------
check("blankes Datum wird auf 08:00 gesetzt",
      server._widen_date("2026-09-15") == "2026-09-15T08:00:00")
check("voller Zeitstempel bleibt", server._widen_date("2026-09-15T14:30:00") == "2026-09-15T14:30:00")
check("Unfug-Datum -> None", server._widen_date("15.09.2026") is None)
check("leer -> None", server._widen_date("") is None)


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


print(f"\n{sum(results)}/{len(results)} checks bestanden")
sys.exit(0 if all(results) else 1)
