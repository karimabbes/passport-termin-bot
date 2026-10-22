from datetime import date

from checker import find_slots, format_slot, within_window


def test_old_availability_api_shape():
    payload = {"availabilityEntries": [
        {"slot": {"startDate": "2026-10-23T09:00:00Z", "serviceId": "x"}, "bookable": True, "openSpots": 1},
        {"slot": {"startDate": "2026-10-23T09:30:00Z", "serviceId": "x"}, "bookable": False, "openSpots": 0},
    ]}
    assert find_slots(payload) == ["2026-10-23T09:00:00Z"]


def test_time_slots_api_shape():
    payload = {"timeSlots": [
        {"localStartDate": "2026-10-24T10:00:00", "bookable": True, "remainingCapacity": 2},
        {"localStartDate": "2026-10-24T10:30:00", "bookable": True, "remainingCapacity": 0},
    ]}
    assert find_slots(payload) == ["2026-10-24T10:00:00"]


def test_ignores_non_availability_dates():
    assert find_slots({"service": {"createdDate": "2026-01-01T00:00:00Z", "startDate": "2026-01-01T00:00:00Z"}}) == []


def test_within_window():
    slots = ["2026-10-21T09:00:00", "2026-10-25T09:00:00", "2026-12-01T09:00:00"]
    assert within_window(slots, 14, today=date(2026, 10, 22)) == ["2026-10-25T09:00:00"]


def test_until_date_is_inclusive():
    slots = ["2026-11-26T15:00:00", "2026-11-27T09:00:00"]
    assert within_window(slots, 14, until=date(2026, 11, 26), today=date(2026, 10, 22)) == ["2026-11-26T15:00:00"]


def test_format_slot_converts_utc_to_german_time():
    assert format_slot("2026-11-03T08:00:00Z") == "Tue 03 Nov 2026, 09:00"
    assert format_slot("2026-11-03T08:00:00") == "Tue 03 Nov 2026, 08:00"
