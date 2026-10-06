import re
from pathlib import Path

from services.enrich.fingerprint import (dom_structure_hash, extract_forms, favicon_hash, js_bundle_hashes,
                                         page_title)

KIT = (Path(__file__).parent / "fixtures/kit_a.html").read_text(encoding="utf-8")


def mutate(html: str) -> str:
    html = re.sub(r">([^<]+)<", lambda m: ">" + "Z" * len(m.group(1).strip()) + "<", html)  # every string
    html = re.sub(r"#[0-9a-fA-F]{3,6}", "#123456", html)                                    # every colour
    html = re.sub(r'src="[^"]*"', 'src="https://other.example/x.png"', html)                # every image URL
    html = re.sub(r'(class|id|style|alt|placeholder)="[^"]*"', r'\1="changed"', html)        # attributes
    return html.replace("\n", "\n    ")                                                     # whitespace


def test_hash_stable_under_trivial_variation():
    assert dom_structure_hash(KIT) == dom_structure_hash(mutate(KIT))


def test_hash_stable_when_brand_name_swapped():
    assert dom_structure_hash(KIT) == dom_structure_hash(KIT.replace("ICICI", "HDFC").replace("icici", "hdfc"))


def test_hash_stable_for_void_tag_spelling():
    assert dom_structure_hash("<div><br><img src=a></div>") == dom_structure_hash("<div><br/><img src='b' /></div>")


def test_hash_changes_when_structure_changes():
    changed = KIT.replace("<form", "<div><form", 1).replace("</form>", "</form></div>", 1)
    assert dom_structure_hash(KIT) != dom_structure_hash(changed)


def test_hash_ignores_script_and_style_contents():
    a = "<html><script>var a=1;</script><style>p{}</style><p>x</p></html>"
    b = "<html><script>eval(atob('Zm9v'))</script><style>div{color:red}</style><p>y</p></html>"
    assert dom_structure_hash(a) == dom_structure_hash(b)


def test_forms_detect_password_and_foreign_action():
    f = extract_forms(KIT, "https://icici-verify-kyc.top/login")
    assert any(x.has_password and x.action_url.startswith("https://185.243.115.22") and x.method == "post" for x in f)


def test_relative_action_resolved():
    f = extract_forms('<form action="/p.php"><input type="password"></form>', "https://a.top/x/")
    assert f[0].action_url == "https://a.top/p.php"


def test_missing_action_posts_to_page_itself():
    f = extract_forms('<form><input type="PASSWORD"></form>', "https://a.top/login")
    assert f[0].action_url == "https://a.top/login" and f[0].has_password


def test_malformed_html_does_not_crash():
    assert dom_structure_hash("<div><p>unclosed <b>tags") and dom_structure_hash("")
    assert extract_forms("<form action=", "https://a.top/") is not None


def test_title():
    assert page_title(KIT) == "ICICI Bank - Internet Banking Login"
    assert page_title("<p>no title</p>") is None


def test_favicon_hash_shodan_convention():
    import base64
    import mmh3
    data = b"\x00\x01\x02favicon-bytes"
    assert favicon_hash(data) == str(mmh3.hash(base64.encodebytes(data)))
    assert favicon_hash(b"a") != favicon_hash(b"b")


def test_js_bundle_hashes_sorted_and_deterministic():
    assert js_bundle_hashes([b"b", b"a"]) == js_bundle_hashes([b"a", b"b"]) and len(js_bundle_hashes([b"a"])[0]) == 64


def test_trivial_pages_get_no_kit_hash():
    """Review I7: a blank, parked or bare-form page has a structure thousands of unrelated sites share.
    Hashing it would merge them all into one 'kit', so below the complexity floor there is no kit hash."""
    from services.enrich.fingerprint import kit_hash
    trivial = ["", "<html><body></body></html>", "<html><head><title>x</title></head><body><h1>Parked</h1></body></html>",
               "<form method=post><input name=u><input type=password><button>Go</button></form>"]
    for html in trivial:
        assert kit_hash(html) is None, html
    assert kit_hash(KIT) == dom_structure_hash(KIT)
