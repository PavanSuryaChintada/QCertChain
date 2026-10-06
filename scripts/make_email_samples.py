"""Generate the labelled synthetic .eml sample set (services/email/samples/).

Every sample is synthetic: senders on reserved .example names (RFC 2606), documentation IPs (RFC 5737),
and an `X-QCertChain-Sample: synthetic` header. Brand legit domains appear only where a real brand would
legitimately send (the "legit" class) or where the scenario is exact-domain spoofing that DMARC catches.
labels.json holds GROUND TRUTH (phishing | legit) and the scenario — not the verdict our gate is expected
to give — so recall/precision are measured honestly.
"""
import json

from services.config import ROOT

OUT = ROOT / "services/email/samples"
HDR = "X-QCertChain-Sample: synthetic\n"


def eml(headers: str, body: str, html: str | None = None) -> str:
    h = HDR + headers.strip() + "\n"
    if html is None:
        return h + "Content-Type: text/plain; charset=utf-8\n\n" + body + "\n"
    return (h + 'MIME-Version: 1.0\nContent-Type: multipart/alternative; boundary="b1"\n\n'
            "--b1\nContent-Type: text/plain; charset=utf-8\n\n" + body + "\n"
            "--b1\nContent-Type: text/html; charset=utf-8\n\n" + html + "\n--b1--\n")


S = {}
S["p01_display_spoof_dmarc_fail.eml"] = ("phishing", "cold-start: SBI display name on a lookalike domain, DMARC fail, Reply-To mismatch", eml("""
From: "State Bank of India" <alerts@sbi-kyc-update.example>
Reply-To: help@sbi-support-desk.example
Return-Path: <bounce@bulk-mailer.example>
Message-ID: <a1@bulk-mailer.example>
Subject: KYC pending: account will be blocked
Date: Mon, 05 Oct 2026 03:00:00 +0000
Authentication-Results: mx.recipient.example; spf=fail smtp.mailfrom=bulk-mailer.example; dkim=none; dmarc=fail header.from=sbi-kyc-update.example
Received: from bulk-mailer.example (unknown [203.0.113.9]) by mx.recipient.example; Mon, 05 Oct 2026 03:00:02 +0000
""", "Dear customer, update your KYC: https://sbi-kyc-verify-17.example/login", '<a href="https://sbi-kyc-verify-17.example/login">Update KYC</a>'))

S["p02_exact_domain_spoof.eml"] = ("phishing", "cold-start: From is the real sbi.co.in, DMARC fail (exact-domain spoof)", eml("""
From: SBI Alerts <alerts@sbi.co.in>
Return-Path: <x@spoofer.example>
Message-ID: <b2@spoofer.example>
Subject: Your YONO access is suspended
Date: Mon, 05 Oct 2026 04:00:00 +0000
Authentication-Results: mx.recipient.example; spf=fail smtp.mailfrom=spoofer.example; dkim=fail; dmarc=fail header.from=sbi.co.in
Received: from spoofer.example ([198.51.100.40]) by mx.recipient.example; Mon, 05 Oct 2026 04:00:01 +0000
""", "Restore access: https://yonosbi-restore-22.example/"))

S["p03_campaign_link.eml"] = ("phishing", "warm: ICICI display spoof + link to a domain the CT pipeline already confirmed", eml("""
From: "ICICI Bank" <service@icici-netbanking-secure.example>
Reply-To: support@icici-helpdesk.example
Message-ID: <c3@icici-netbanking-secure.example>
Subject: Unusual login detected
Date: Mon, 05 Oct 2026 05:00:00 +0000
Authentication-Results: mx.recipient.example; spf=pass smtp.mailfrom=icici-netbanking-secure.example; dkim=pass; dmarc=pass header.from=icici-netbanking-secure.example
Received: from mail.icici-netbanking-secure.example ([203.0.113.10]) by mx.recipient.example; Mon, 05 Oct 2026 05:00:01 +0000
""", "Verify now: https://icicibank-verify-kyc-4412.example/login"))

S["p04_income_tax_refund.eml"] = ("phishing", "cold-start: Income Tax refund display spoof, all auth passes for the attacker's own domain", eml("""
From: "Income Tax Department" <refunds@incometax-refund-status.example>
Message-ID: <d4@incometax-refund-status.example>
Subject: Refund of Rs 18,450 approved
Date: Tue, 06 Oct 2026 02:00:00 +0000
Authentication-Results: mx.recipient.example; spf=pass; dkim=pass; dmarc=pass header.from=incometax-refund-status.example
Received: from mta.incometax-refund-status.example ([198.51.100.77]) by mx.recipient.example; Tue, 06 Oct 2026 02:00:01 +0000
""", "Claim your refund: https://incometax-refund-claim.example/efiling"))

S["p05_paytm_no_display_brand.eml"] = ("phishing", "cold-start: no brand display name; lookalike sender, Reply-To mismatch, SPF softfail", eml("""
From: notice@paytm-kyc-verify.example
Reply-To: kyc@paytm-verification-desk.example
Message-ID: <e5@paytm-kyc-verify.example>
Subject: Complete KYC within 24h
Date: Tue, 06 Oct 2026 02:30:00 +0000
Authentication-Results: mx.recipient.example; spf=softfail; dkim=none; dmarc=none
Received: from paytm-kyc-verify.example ([203.0.113.55]) by mx.recipient.example; Tue, 06 Oct 2026 02:30:01 +0000
""", "https://paytm-kyc-update-9.example/verify"))

S["p06_hdfc_exact_spoof_plus_lookalike_link.eml"] = ("phishing", "warm: hdfcbank.com spoofed (DMARC fail) + link to a confirmed campaign domain", eml("""
From: "HDFC Bank" <alerts@hdfcbank.com>
Message-ID: <f6@mailer.example>
Subject: NetBanking password expiry
Date: Tue, 06 Oct 2026 03:00:00 +0000
Authentication-Results: mx.recipient.example; spf=fail; dkim=none; dmarc=fail header.from=hdfcbank.com
Received: from mailer.example ([198.51.100.12]) by mx.recipient.example; Tue, 06 Oct 2026 03:00:01 +0000
""", "Reset: https://hdfc-netbanking-secure-301.example/reset"))

S["p07_body_only_paste.eml"] = ("phishing", "analyst pasted only the body: no headers at all", "Your SBI account is blocked. Verify at https://sbi-kyc-verify-17.example/login now.\n")

S["p08_folded_headers.eml"] = ("phishing", "cold-start: p01 with folded Authentication-Results and Received headers", eml("""
From: "State Bank of India"
 <alerts@sbi-kyc-update.example>
Reply-To: help@sbi-support-desk.example
Message-ID: <a8@bulk-mailer.example>
Subject: KYC pending
Date: Mon, 05 Oct 2026 03:10:00 +0000
Authentication-Results: mx.recipient.example;
 spf=fail smtp.mailfrom=bulk-mailer.example;
 dkim=none;
 dmarc=fail header.from=sbi-kyc-update.example
Received: from bulk-mailer.example (unknown [203.0.113.9])
 by mx.recipient.example; Mon, 05 Oct 2026 03:10:02 +0000
""", "https://sbi-kyc-verify-17.example/login"))

S["l01_sbi_newsletter.eml"] = ("legit", "SBI newsletter from sbi.co.in, all auth pass", eml("""
From: SBI <newsletter@sbi.co.in>
Message-ID: <n1@sbi.co.in>
Subject: Festive offers on home loans
Date: Mon, 05 Oct 2026 06:00:00 +0000
Authentication-Results: mx.recipient.example; spf=pass smtp.mailfrom=sbi.co.in; dkim=pass header.d=sbi.co.in; dmarc=pass header.from=sbi.co.in
Received: from mail.sbi.co.in ([192.0.2.20]) by mx.recipient.example; Mon, 05 Oct 2026 06:00:01 +0000
""", "Read more at https://sbi.co.in/web/personal-banking/loans"))

S["l02_amazon_order.eml"] = ("legit", "Amazon order confirmation from amazon.in, auth pass", eml("""
From: "Amazon.in" <order-update@amazon.in>
Message-ID: <n2@amazon.in>
Subject: Your order has shipped
Date: Mon, 05 Oct 2026 07:00:00 +0000
Authentication-Results: mx.recipient.example; spf=pass; dkim=pass header.d=amazon.in; dmarc=pass header.from=amazon.in
Received: from a1-2.smtp-out.amazonses.com ([192.0.2.21]) by mx.recipient.example; Mon, 05 Oct 2026 07:00:01 +0000
""", "Track: https://www.amazon.in/gp/your-account/order-history"))

S["l03_internal_no_auth_headers.eml"] = ("legit", "internal mail from a company relay that adds no Authentication-Results", eml("""
From: Priya <priya@company.example>
Message-ID: <n3@company.example>
Subject: Lunch?
Date: Mon, 05 Oct 2026 08:00:00 +0000
Received: from relay.company.example ([192.0.2.30]) by mx.company.example; Mon, 05 Oct 2026 08:00:01 +0000
""", "Shall we meet at 1?"))

S["l04_non_utf8_newsletter.eml"] = ("legit", "legit HDFC mail with latin-1 bytes in the body", None)

S["l05_brand_via_esp.eml"] = ("legit", "HDFC via a third-party ESP: Return-Path on the ESP, DMARC pass by DKIM alignment", eml("""
From: "HDFC Bank" <offers@hdfcbank.com>
Return-Path: <bounces+123@em.esp-provider.example>
Message-ID: <n5@esp-provider.example>
Subject: Credit card offers
Date: Mon, 05 Oct 2026 09:00:00 +0000
Authentication-Results: mx.recipient.example; spf=pass smtp.mailfrom=em.esp-provider.example; dkim=pass header.d=hdfcbank.com; dmarc=pass header.from=hdfcbank.com
Received: from em.esp-provider.example ([192.0.2.40]) by mx.recipient.example; Mon, 05 Oct 2026 09:00:01 +0000
""", "https://www.hdfcbank.com/personal/pay/cards"))

L04 = (HDR + "From: HDFC Bank <alerts@hdfcbank.com>\nMessage-ID: <n4@hdfcbank.com>\nSubject: Statement\n"
       "Authentication-Results: mx.recipient.example; spf=pass; dkim=pass; dmarc=pass header.from=hdfcbank.com\n"
       "Content-Type: text/plain; charset=latin-1\n\n").encode() + "Your statement is ready éè at https://www.hdfcbank.com/\n".encode("latin-1")

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    labels = {}
    for name, (truth, scenario, body) in S.items():
        data = L04 if body is None else body.encode("utf-8")
        (OUT / name).write_bytes(data)
        labels[name] = {"truth": truth, "scenario": scenario}
    (OUT / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8")
    # domains the CT pipeline would already have confirmed in the "warm" condition
    (OUT / "warm_confirmed.json").write_text(json.dumps(
        ["sbi-kyc-verify-17.example", "icicibank-verify-kyc-4412.example", "hdfc-netbanking-secure-301.example",
         "yonosbi-restore-22.example", "incometax-refund-claim.example", "paytm-kyc-update-9.example"], indent=1),
        encoding="utf-8")
    print(f"wrote {len(S)} samples")
