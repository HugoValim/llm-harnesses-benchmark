from __future__ import annotations

from chat.ws_fragments import token_append


def test_token_fragment_escapes_html() -> None:
    frag = token_append("b1", "<script>x</script>")
    assert "<script>" not in frag
    assert "&lt;script&gt;" in frag
