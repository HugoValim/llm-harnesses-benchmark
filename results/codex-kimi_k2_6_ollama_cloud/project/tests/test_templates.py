from django.template.loader import render_to_string


def test_base_contains_htmx_ws_extension() -> None:
    html = render_to_string("chat/base.html")
    assert "htmx.org" in html
    assert "htmx-ext-ws" in html


def test_index_contains_ws_attributes() -> None:
    html = render_to_string("chat/index.html")
    assert 'ws-connect="/ws/chat/"' in html
    assert 'ws-send=""' in html
    assert 'hx-ext="ws"' in html
