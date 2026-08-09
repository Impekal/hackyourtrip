"""LiteAPI-Hotelprovider - geprueft gegen die gemessene Antwortform.

Die Fixture stammt aus Probe 17 (Melia Berlin, 1 Nacht, 2 Erwachsene):
Feldnamen und Betraege 1:1 wie live gemessen. Eine ausgedachte Fixture
haette hier nichts bewiesen - genau daran ist beim Bahn-Server der Parser
gescheitert, der gegen erfundene Feldnamen gruen war.

Im Mittelpunkt steht der Fehler, der Geld kostet: LiteAPI nennt drei
Betraege je Zimmer, und die City Tax steckt ausdruecklich NICHT im
genannten Preis.
"""
from __future__ import annotations

from datetime import date, timedelta

from traveldeals.models import HotelPref, Mode, RoutePreference
from traveldeals.engine import _meets_hotel_constraints, hotel_comfort_score
from traveldeals.providers.liteapi import (LiteApiHotelProvider, _cheapest_offer,
                                            _meal_plan, _split_destination)

RATE_ENTRY = {
    "hotelId": "lp394f5",
    "roomTypes": [
        {
            "offerId": "x" * 900,
            "offerRetailRate": {"amount": 260.45, "currency": "EUR"},
            "suggestedSellingPrice": {"amount": 333.13, "currency": "EUR",
                                       "source": "booking.com"},
            "offerInitialPrice": {"amount": 260.45, "currency": "EUR"},
            "rates": [{
                "name": "Deluxe Room City View",
                "boardType": "RO",
                "boardName": "Room Only",
                "retailRate": {
                    "total": [{"amount": 260.45, "currency": "EUR"}],
                    "suggestedSellingPrice": [{"amount": 333.13, "currency": "EUR",
                                                "source": "booking.com"}],
                    "taxesAndFees": [
                        {"included": False, "description": "City Tax",
                         "amount": 19.56, "currency": "EUR"},
                        {"included": True, "description": "VAT",
                         "amount": 17.04, "currency": "EUR"},
                    ],
                },
                "cancellationPolicies": {"refundableTag": "NRFN"},
            }],
        },
        {
            # Auf dem Papier billiger (250), mit 40 EUR nicht enthaltener
            # Gebuehr in Wahrheit teurer (290) als das Zimmer oben (280,01).
            "offerRetailRate": {"amount": 250.00, "currency": "EUR"},
            "rates": [{
                "name": "Falle",
                "retailRate": {"taxesAndFees": [
                    {"included": False, "description": "Resort Fee",
                     "amount": 40.00, "currency": "EUR"}]},
                "cancellationPolicies": {"refundableTag": "RFN"},
            }],
        },
    ],
}

HOTEL_RECORD = {
    "id": "lp394f5", "name": "Meliá Berlin", "city": "Berlin", "country": "de",
    "address": "Friedrichstr. 103", "zip": "10117", "stars": 4, "rating": 8,
    "reviewCount": 5000, "latitude": 52.52, "longitude": 13.38,
    "facilityIds": [47, 107, 2],
}


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _Session:
    """Minimaler Ersatz fuer requests - haelt fest, was rausgegangen waere."""

    def __init__(self, listing, rates):
        self.listing = listing
        self.rates = rates
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, params, headers))
        return _Resp(self.listing)

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json, headers))
        return _Resp(self.rates)


def _route(**kw):
    start = date.today() + timedelta(days=30)
    defaults = dict(
        id="test", origin="", destination="Berlin, DE",
        modes=[Mode.HOTEL], depart_date_from=start, depart_date_until=start,
        currency="EUR", min_nights=1,
    )
    defaults.update(kw)
    return RoutePreference(**defaults)


# --- Der entscheidende Betrag ---------------------------------------------

def test_gesamtpreis_enthaelt_die_nicht_enthaltene_city_tax():
    best = _cheapest_offer(RATE_ENTRY)
    assert best["total"] == 280.01, "260,45 waere der Lockpreis, nicht der Preis"
    assert best["price"] == 260.45
    assert best["extra_tax"] == 19.56


def test_guenstigstes_zimmer_wird_nach_gesamtpreis_gewaehlt():
    # Das "Falle"-Zimmer nennt 250 und kostet 290 - wer den genannten Betrag
    # vergleicht, empfiehlt hier das teurere.
    assert _cheapest_offer(RATE_ENTRY)["room_name"] == "Deluxe Room City View"


def test_vergleichspreis_kommt_mit_quelle():
    best = _cheapest_offer(RATE_ENTRY)
    assert best["compare_at"] == 333.13
    assert best["compare_source"] == "booking.com"


def test_vergleichspreis_unter_unserem_preis_wird_verworfen():
    entry = {"hotelId": "h", "roomTypes": [{
        "offerRetailRate": {"amount": 100.0, "currency": "EUR"},
        "suggestedSellingPrice": {"amount": 90.0, "source": "booking.com"},
        "rates": [{"name": "R", "retailRate": {"taxesAndFees": []}}],
    }]}
    assert _cheapest_offer(entry)["compare_at"] is None


def test_zimmer_ohne_lesbaren_preis_faellt_raus():
    assert _cheapest_offer({"hotelId": "h", "roomTypes": [{"rates": [{}]}]}) is None


# --- Unbekannt ist nicht nein ---------------------------------------------

def test_nicht_erstattbar_ist_false_alles_andere_bleibt_offen():
    assert _cheapest_offer(RATE_ENTRY)["free_cancellation"] is False
    entry = {"hotelId": "h", "roomTypes": [{
        "offerRetailRate": {"amount": 100.0, "currency": "EUR"},
        "rates": [{"name": "R", "cancellationPolicies": {}}],
    }]}
    # Kein Hinweis auf Stornierbarkeit -> None, niemals True.
    assert _cheapest_offer(entry)["free_cancellation"] is None


def test_unbekannte_ausstattung_schliesst_ein_hotel_nicht_aus():
    offers = _search(_route())
    hotel = offers[0]
    assert hotel.parking is None, "die Quelle sagt nichts ueber Parkplaetze"
    # Frueher htte `not None` hier ausgeschlossen - und die Liste geleert.
    assert _meets_hotel_constraints(hotel, HotelPref(require_parking=True))


def test_ein_ausdrueckliches_nein_schliesst_weiterhin_aus():
    hotel = _search(_route())[0]
    assert hotel.free_cancellation is False
    assert not _meets_hotel_constraints(hotel, HotelPref(require_free_cancellation=True))


def test_bekannte_verpflegung_filtert_weiterhin():
    hotel = _search(_route())[0]
    assert hotel.meal_plan == "none"  # "Room Only"
    assert not _meets_hotel_constraints(hotel, HotelPref(min_meal_plan="breakfast"))


def test_unbekannte_verpflegung_filtert_nicht():
    hotel = _search(_route(), board_name=None)[0]
    assert hotel.meal_plan is None
    assert _meets_hotel_constraints(hotel, HotelPref(min_meal_plan="breakfast"))


def test_komfortwert_bestraft_schweigen_nicht():
    hotel = _search(_route())[0]
    wert = hotel_comfort_score(hotel)
    assert 0.0 < wert < 1.0
    # Ohne die Sonderbehandlung waere amenity_norm 0 und meal_plan_norm ein
    # Absturz - ein echtes Hotel landete hinter jedem erfundenen.
    assert wert > 0.3


# --- Anfrage und Umsetzung ------------------------------------------------

def _search(route, board_name="Room Only"):
    entry = {**RATE_ENTRY}
    if board_name is None:
        rooms = [dict(RATE_ENTRY["roomTypes"][0])]
        rooms[0]["rates"] = [{**RATE_ENTRY["roomTypes"][0]["rates"][0]}]
        rooms[0]["rates"][0].pop("boardName")
        entry = {**RATE_ENTRY, "roomTypes": rooms}
    session = _Session({"data": [HOTEL_RECORD]}, {"data": [entry]})
    provider = LiteApiHotelProvider(api_key="sand_test", session=session)
    return provider.search(route)


def test_angebot_traegt_gesamtpreis_und_hoteldaten():
    offer = _search(_route())[0]
    assert offer.price == 280.01
    assert offer.booking_site == "Meliá Berlin"
    assert offer.stars == 4 and offer.rating == 8
    assert offer.provider == "liteapi"
    assert "booking.com" in offer.url


def test_ohne_schluessel_bleibt_der_provider_still():
    provider = LiteApiHotelProvider(api_key="")
    assert not provider.configured
    assert provider.search(_route()) == []


def test_ohne_laenderkuerzel_wird_nicht_geraten():
    # "Frankfurt" gibt es auch in Kentucky - lieber nichts liefern als das
    # falsche Land.
    assert _split_destination("Berlin") == ("Berlin", "")
    assert _split_destination("Berlin, DE") == ("Berlin", "DE")
    assert _search(_route(destination="Berlin")) == []


def test_verpflegung_aus_klartext():
    assert _meal_plan("Room Only") == "none"
    assert _meal_plan("Breakfast included") == "breakfast"
    assert _meal_plan("All Inclusive") == "all_inclusive"
    # Unbekannte Formulierung -> None, nicht "none": das waere die Aussage
    # "keine Verpflegung", und die steht da nicht.
    assert _meal_plan("Zimmer mit Meerblick") is None
    assert _meal_plan(None) is None
