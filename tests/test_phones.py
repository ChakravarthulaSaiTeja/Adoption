from marksapp.phones import normalise_phone, pretty_phone


def test_accepted_forms():
    for raw in ["9876543210", "+91 98765-43210", "(+91) 98765 43210",
                "919876543210", "09876543210", 9876543210, 9876543210.0, "9.87654321E9"]:
        r = normalise_phone(raw)
        assert r.ok and r.e164 == "+919876543210", raw
        assert r.problem is None


def test_rejected_forms():
    assert normalise_phone("5876543210").problem == "Must start with 6, 7, 8 or 9"
    assert normalise_phone("98765").problem == "Must be 10 digits"
    assert normalise_phone(None).problem == "Missing"
    assert normalise_phone("").problem == "Missing"
    assert normalise_phone(float("nan")).problem == "Missing"
    assert normalise_phone("+1 415 555 0100").problem == "Not an Indian mobile number"
    assert not normalise_phone("5876543210").ok


def test_two_numbers_in_one_cell_is_flagged():
    for raw in ["9876543210 / 9123456789", "9876543210, 9123456789", "9876543210 or 9123456789"]:
        r = normalise_phone(raw)
        assert not r.ok and r.problem == "More than one number", raw


def test_raw_kept_and_pretty():
    assert normalise_phone(" 98765 43210 ").raw == "98765 43210"
    assert pretty_phone("+919876543210") == "+91 98765 43210"
