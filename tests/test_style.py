from marksapp.settings import get_setting
from marksapp.ui.style import bubble, status_label, whatsapp_link_html


def test_bubble_bold_and_escape():
    html = bubble("*Advance Exam - 4 Marks*\n\nMaths - 41 <b>x</b> & y")
    assert html.startswith('<div class="wa-bubble">')
    assert "<b>Advance Exam - 4 Marks</b>" in html and "<br>" in html
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in html


def test_bubble_star_inside_text_not_bold_across_lines():
    html = bubble("a * b\nc * d")
    assert "<b>" not in html


def test_status_labels():
    assert status_label("ready") == "🟢 Ready"
    assert status_label("review") == "🟡 Needs review"
    assert status_label("blocked") == "🔴 Blocked"
    assert status_label("approved") == "✅ Approved"
    assert status_label("accepted") == status_label("sent") == "📤 Sent"
    assert status_label("unknown") == "⚠️ Unknown — check"


def test_link_targets():
    d = whatsapp_link_html("whatsapp://send?phone=91&text=a%26b", "desktop")
    assert 'target="_self"' in d and 'class="wa-btn"' in d
    assert 'href="whatsapp://send?phone=91&amp;text=a%26b"' in d
    assert 'target="marks_whatsapp"' in whatsapp_link_html("https://web.whatsapp.com/send?x", "web")
    assert 'target="_blank"' in whatsapp_link_html("https://wa.me/91?text=x", "wa.me")


def test_default_link_kind_is_desktop(conn):
    assert get_setting(conn, "link_kind") == "desktop"
