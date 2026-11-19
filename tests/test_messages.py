from marksapp.messages import MessageSettings, content_hash, message_settings, render_message
from tests.helpers import make_result

SPEC_BODY = ("*Advance Exam - 4 Marks*\n\nMaths - 41\nPhysics - 32\nChemistry - 17\n\n*Total Marks - 90*"
             "\n\n*Mains Exam - 4 Marks*\n\nMaths - 62\nPhysics - 17\nChemistry - 16\n\n*Total Marks - 95*")


def test_render_exact_spec_format(conn):
    assert render_message(make_result(), message_settings(conn)) == SPEC_BODY


def test_render_with_name(conn):
    ms = message_settings(conn)
    ms = MessageSettings(ms.exam_block, ms.separator, True, ms.name_line)
    body = render_message(make_result(), ms)
    assert body.startswith("*Pallapu Meghana Sri*\n\n*Advance Exam - 4 Marks*")
    assert body.endswith(SPEC_BODY)


def test_render_ab_na_negative(conn):
    body = render_message(make_result(exams=(("Advance Exam - 4", "AB", 16, -7, None),)), message_settings(conn))
    assert "Maths - AB" in body and "Chemistry - -7" in body and "*Total Marks - NA*" in body


def test_hash_changes_with_phone():
    assert content_hash("+919876543201", "b") != content_hash("+919876543202", "b")
    assert content_hash("+919876543201", "b") == content_hash("+919876543201", "b")
