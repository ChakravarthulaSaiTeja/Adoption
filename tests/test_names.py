from marksapp.names import clean_name, name_key, similarity, title_name


def test_clean():
    assert clean_name("  Pallapu.  Meghana-Sri ") == "PALLAPU MEGHANA SRI"
    assert clean_name("GORANTLA SAI\nKARTHIK") == "GORANTLA SAI KARTHIK"
    assert clean_name("K.Ravi") == "K RAVI"
    assert clean_name(None) == ""


def test_key_ignores_order_and_dots():
    assert name_key("PALLAPU MEGHANA SRI") == name_key("Meghana Sri Pallapu")
    assert name_key("K. Ravi Teja") == name_key("RAVI TEJA K")


def test_spelling_variant_scores_high():
    assert similarity("GORANTLA SAI KARTHIK", "Gorantla Sai Kartik") >= 85


def test_initial_vs_full_word_is_candidate_but_capped():
    s = similarity("V NIHARIKA DEVI", "Niharika Devi Vanga")
    assert 85 <= s <= 90


def test_siblings_are_not_candidates():
    assert similarity("NAKKA RAVI TEJA", "Nakka Ravi Kiran") < 70


def test_missing_surname_is_candidate_not_exact():
    assert 70 <= similarity("PALLAPU MEGHANA SRI", "Pallapu Meghana") < 100


def test_identical_after_cleaning_is_100():
    assert similarity("PALLAPU MEGHANA SRI", "Meghana Sri Pallapu") == 100


def test_empty_is_zero():
    assert similarity("", "Syed Afreen") == 0


def test_title_name():
    assert title_name("PALLAPU MEGHANA SRI") == "Pallapu Meghana Sri"
