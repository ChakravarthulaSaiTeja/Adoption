from marksapp.values import AB, NA, Mark, decode_mark, parse_mark


def test_integers_and_negatives():
    assert parse_mark(41) == Mark("num", 41.0)
    assert parse_mark("-7") == Mark("num", -7.0)
    assert parse_mark("−7") == Mark("num", -7.0)  # unicode minus
    assert parse_mark(" 60 ") == Mark("num", 60.0)
    assert parse_mark(0) == Mark("num", 0.0)


def test_display():
    assert parse_mark(41).display() == "41"
    assert parse_mark(-7.0).display() == "-7"
    assert parse_mark("41.5").display() == "41.5"
    assert AB.display() == "AB" and NA.display() == "NA"


def test_absent_words():
    for raw in ["AB", "ab ", "Absent", "A"]:
        assert parse_mark(raw) == AB


def test_missing_is_never_zero():
    for raw in [None, "", "  ", float("nan"), "--", "x12", True]:
        assert parse_mark(raw) == NA


def test_encode_roundtrip():
    for m in [Mark("num", 41.0), Mark("num", -7.0), Mark("num", 41.5), AB, NA]:
        assert decode_mark(m.encode()) == m
