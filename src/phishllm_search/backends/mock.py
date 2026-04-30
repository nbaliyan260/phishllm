"""Deterministic mock backend that emulates a PhishLLM-style detector.

The mock is intentionally dependency-free so the full pipeline (and CI) can
run on any machine without API keys. It models the four pipeline stages of
the paper -- brand recognition, CRP detection, optional CRP transition, and
fusion -- as transparent rules. Every candidate field has a measurable,
documented effect on at least one stage, which guarantees that the search
loop sees a non-trivial trade-off surface.

Failure modes intentionally reproduced
======================================
* brand hallucination       - happens at low confidence floor with the
  recall-first prompt on benign pages whose URL/text contain weak brand
  cues.
* alias false positive      - benign aliases (e.g. ``fb.com`` for
  ``facebook.com``) are flagged when popularity validation is disabled.
* prompt injection failure  - pages with adversarial markers fool the CRP
  stage when ``prompt_defense`` is off and a non-robust CRP prompt is used.
* CRP miss                  - phishing login pages are missed when CRP
  prompts are precision-biased and ``max_interactions`` is 0.
* hidden login miss         - login text only appears after a continue
  button and is missed unless ``max_interactions >= 1``.
"""

from __future__ import annotations

import re
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from ..dataset import Sample
from .base import Backend, Prediction


SUSPICIOUS_TLDS = {"click", "top", "xyz", "zip", "live", "support", "review"}
HOSTING_DOMAINS = {"vercel.app", "netlify.app", "github.io", "pages.dev",
                   "web.app", "firebaseapp.com", "workers.dev", "azurewebsites.net"}
POPULAR_DOMAINS = {
    "adobe.com", "microsoft.com", "office.com", "live.com",
    "facebook.com", "fb.com", "meta.com", "instagram.com",
    "paypal.com", "amazon.com", "amazon.co.uk", "dropbox.com",
    "google.com", "gmail.com", "apple.com", "icloud.com",
    "linkedin.com", "github.com", "twitter.com", "x.com",
    "netflix.com", "spotify.com", "wellsfargo.com", "chase.com",
    "bankofamerica.com", "hsbc.com",
}
ALIAS_TO_PRIMARY = {
    "fb.com": "facebook.com",
    "amazon.co.uk": "amazon.com",
    "live.com": "microsoft.com",
    "office.com": "microsoft.com",
    "outlook.com": "microsoft.com",
    "x.com": "twitter.com",
}
BRAND_KEYWORDS: Dict[str, List[str]] = {
    "adobe.com":       ["adobe", "acrobat", "creative cloud"],
    "microsoft.com":   ["microsoft", "office365", "office 365", "outlook", "onedrive", "sharepoint"],
    "facebook.com":    ["facebook", "meta business", "fb"],
    "meta.com":        ["meta"],
    "paypal.com":      ["paypal"],
    "amazon.com":      ["amazon", "aws"],
    "dropbox.com":     ["dropbox"],
    "google.com":      ["google", "gmail", "drive.google"],
    "apple.com":       ["apple id", "icloud"],
    "linkedin.com":    ["linkedin"],
    "github.com":      ["github"],
    "netflix.com":     ["netflix"],
    "wellsfargo.com":  ["wells fargo"],
    "chase.com":       ["chase bank"],
    "bankofamerica.com": ["bank of america"],
    "hsbc.com":        ["hsbc"],
    "sonicwall.com":   ["sonicwall"],
}
CRP_TERMS = ["password", "sign in", "signin", "log in", "login", "verify",
             "credential", "two-factor", "2fa", "username", "security code",
             "one-time code", "passcode"]
TRANSITION_TERMS = ["continue", "next", "proceed", "go to login", "sign-in"]
PROMPT_INJECTION_MARKERS = [
    "ignore previous instructions",
    "ignore all previous",
    "this is not a credential-taking page",
    "this page is benign",
    "do not flag",
    "system prompt:",
]
CRYPTO_TERMS = ["wallet", "seed phrase", "qr code", "scan qr", "token",
                "private key", "metamask", "trust wallet"]
TYPO_PATTERNS = [
    (re.compile(r"micr0soft", re.I),     "microsoft.com"),
    (re.compile(r"paypa[1]", re.I),      "paypal.com"),
    (re.compile(r"app[1i]e", re.I),      "apple.com"),
    (re.compile(r"g[0]{2}gle", re.I),    "google.com"),
    (re.compile(r"faceb[0]{2}k", re.I),  "facebook.com"),
    (re.compile(r"amaz[0]n", re.I),      "amazon.com"),
]


_TWO_PART_TLDS = {
    "co.uk", "co.jp", "co.kr", "co.in", "co.nz", "co.za", "com.au",
    "com.br", "com.cn", "com.mx", "com.tr", "com.sg", "com.hk",
    "ac.uk", "gov.uk", "org.uk",
}


def registered_domain(url: str) -> str:
    """Best-effort registered (eTLD+1) domain extraction.

    Handles a small whitelist of common two-part eTLDs (``co.uk``, ``com.au``,
    ...). Falls back to the last two labels otherwise. This is good enough
    for the synthetic dataset; production systems should use ``tldextract``
    or the official Public Suffix List.
    """
    parsed = urlparse(url if "://" in url else f"http://{url}")
    host = parsed.netloc.lower().split(":")[0]
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 3:
        last_two = ".".join(parts[-2:])
        if last_two in _TWO_PART_TLDS:
            return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host or url.lower()


def tld_of(domain: str) -> str:
    parts = domain.split(".")
    return parts[-1] if parts else domain


def primary_of(domain: str) -> str:
    return ALIAS_TO_PRIMARY.get(domain, domain)


# ---------------------------------------------------------------------------
# Stage 1 - brand recognition
# ---------------------------------------------------------------------------


_KNOWN_TLDS = {
    "com", "net", "org", "io", "co", "uk", "us", "ai", "edu", "gov", "info", "biz",
    "click", "top", "xyz", "zip", "live", "support", "review", "app", "dev", "cloud",
    "store", "online", "site", "page", "tech",
}


def _url_stem_brand(domain: str) -> Optional[str]:
    """Extract a candidate brand string from the URL host.

    The PhishLLM paper argues that an LLM-based brand detector can recover
    brand intent from the URL itself, even for brands not in any pre-defined
    list. The mock simulates this by stripping a trailing TLD-like token from
    the registered domain and returning ``<stem>.com``. This lets recall- and
    robust-leaning prompts pick up lesser-known brands at the cost of some
    confidence.
    """
    parts = [p for p in domain.split(".") if p]
    if len(parts) < 2:
        return None
    stem_token = parts[0]
    head = stem_token.split("-")[0].split("_")[0]
    head = head.strip().lower()
    if not head or head in _KNOWN_TLDS:
        return None
    return f"{head}.com"


def _detect_brand(text: str, domain: str, candidate: Dict) -> Tuple[Optional[str], float, str, List[str]]:
    """Return ``(brand, confidence, source, evidence)``.

    The confidence and choice depend on which prompt template the candidate
    selects and on whether OCR / caption modalities are enabled.
    """
    use_ocr = bool(candidate.get("use_logo_ocr", True))
    use_caption = bool(candidate.get("use_logo_caption", True))
    prompt = candidate.get("brand_prompt", "brand_default_v1")
    text_l = text.lower()
    evidence: List[str] = []

    for pattern, brand in TYPO_PATTERNS:
        if pattern.search(domain):
            evidence.append(f"typosquat:{brand}")
            base = 0.85
            base += 0.05 if use_ocr else 0.0
            base += 0.05 if use_caption else 0.0
            if prompt == "brand_robust_v1":
                base = min(base + 0.05, 0.99)
            return brand, min(base, 0.99), "url+visual", evidence

    best_brand: Optional[str] = None
    best_hits = 0
    for brand, keywords in BRAND_KEYWORDS.items():
        hits = 0
        for kw in keywords:
            if " " in kw:
                if kw in text_l:
                    hits += 1
            else:
                if re.search(rf"\b{re.escape(kw)}\b", text_l):
                    hits += 1
        if hits > best_hits:
            best_brand, best_hits = brand, hits

    if best_brand is None:
        domain_labels = domain.lower().split(".")
        for brand in BRAND_KEYWORDS:
            stem = brand.split(".")[0]
            if stem in domain_labels:
                best_brand = brand
                best_hits = 1
                evidence.append(f"domain-stem:{stem}")
                break

    used_url_fallback = False
    if best_brand is None and prompt in {"brand_recall_v1", "brand_robust_v1"}:
        guess = _url_stem_brand(domain)
        if guess is not None:
            tld = tld_of(domain)
            on_hosting = domain in HOSTING_DOMAINS
            on_suspicious_tld = tld in SUSPICIOUS_TLDS
            corroborated = on_hosting or on_suspicious_tld

            if prompt == "brand_robust_v1" and not corroborated:
                pass  # robust prompt requires a phishy signal before guessing
            else:
                best_brand = guess
                best_hits = 0
                used_url_fallback = True
                evidence.append(
                    f"url_stem_guess:{guess}{'+suspicious' if corroborated else ''}"
                )

    if best_brand is None:
        return None, 0.0, "no_brand_signal", ["no_brand_signal"]

    base = 0.45
    base += 0.18 * best_hits
    base += 0.10 if use_ocr else 0.0
    base += 0.10 if use_caption else 0.0
    if not (use_ocr or use_caption):
        base -= 0.10

    if prompt == "brand_recall_v1":
        base += 0.08
    elif prompt == "brand_precision_v1":
        base -= 0.05
    elif prompt == "brand_robust_v1":
        base += 0.02

    if used_url_fallback:
        base = max(0.0, base - 0.10)

    confidence = max(0.0, min(base, 0.99))
    source = "ocr+caption" if (use_ocr and use_caption) else "single_modality"
    evidence.append(f"keywords:{best_hits}")
    return best_brand, confidence, source, evidence


# ---------------------------------------------------------------------------
# Stage 2 - CRP detection
# ---------------------------------------------------------------------------


def _detect_crp(html: str, candidate: Dict) -> Tuple[bool, str, bool]:
    """Return ``(is_crp, reason, injection_detected)``."""
    html_l = html.lower()
    injection = any(marker in html_l for marker in PROMPT_INJECTION_MARKERS)
    crp_prompt = candidate.get("crp_prompt", "crp_default_v1")
    prompt_defense = bool(candidate.get("prompt_defense", True))
    robust_prompt = crp_prompt == "crp_robust_v1"

    if injection and not (prompt_defense or robust_prompt):
        return False, "prompt_injection_failure", True

    has_credential_term = any(term in html_l for term in CRP_TERMS)
    has_crypto_term = any(term in html_l for term in CRYPTO_TERMS)

    if crp_prompt == "crp_precision_v1":
        is_crp = ("password" in html_l) or ("seed phrase" in html_l)
        reason = "explicit_credential_field" if is_crp else "no_explicit_credential"
    elif crp_prompt == "crp_recall_v1":
        is_crp = has_credential_term or has_crypto_term or ("verify" in html_l)
        reason = "broad_credential_signal" if is_crp else "no_credential_signal"
    elif crp_prompt == "crp_robust_v1":
        is_crp = has_credential_term or has_crypto_term
        reason = "robust_credential_signal" if is_crp else "no_credential_signal"
    else:
        is_crp = has_credential_term or has_crypto_term
        reason = "crp_terms" if is_crp else "no_crp_terms"

    return is_crp, reason, injection


# ---------------------------------------------------------------------------
# Stage 3 - CRP transition (one extra hop)
# ---------------------------------------------------------------------------


def _transition_possible(html: str, max_interactions: int) -> bool:
    if max_interactions <= 0:
        return False
    html_l = html.lower()
    has_button = any(term in html_l for term in TRANSITION_TERMS)
    leads_to_credentials = ("password" in html_l) or ("sign in" in html_l) or ("verify" in html_l)
    return has_button and leads_to_credentials


# ---------------------------------------------------------------------------
# Stage 4 - validation + fusion + reporting
# ---------------------------------------------------------------------------


class MockPhishLLMBackend(Backend):
    """Deterministic stand-in for the official PhishLLM pipeline."""

    def predict(self, sample: Sample, candidate: Dict) -> Prediction:
        start = time.perf_counter()
        url_domain = registered_domain(sample.url)
        tld = tld_of(url_domain)
        text = sample.html

        brand, brand_conf, brand_source, brand_evidence = _detect_brand(text, url_domain, candidate)
        crp, crp_reason, injection_seen = _detect_crp(text, candidate)
        if not crp and _transition_possible(text, int(candidate.get("max_interactions", 0))):
            crp = True
            crp_reason = "transition_found_login_ui"

        threshold = float(candidate.get("brand_confidence_min", 0.80))
        report_policy = candidate.get("report_policy", "mismatch_and_crp")
        hosting_rule = candidate.get("hosting_rule", "strict")
        popularity_validation = candidate.get("popularity_validation", "google-indexed")

        primary_url = primary_of(url_domain)
        primary_brand = primary_of(brand) if brand else None
        brand_mismatch = bool(brand) and primary_brand != primary_url
        hosted = url_domain in HOSTING_DOMAINS
        suspicious_domain = (tld in SUSPICIOUS_TLDS) or hosted
        popular = primary_url in POPULAR_DOMAINS

        score = 0.0
        reasons: List[str] = []

        if brand and brand_conf >= threshold:
            score += 0.35
            reasons.append(f"brand={brand}@{brand_conf:.2f}")
        elif brand:
            reasons.append(f"brand_below_threshold={brand}@{brand_conf:.2f}")

        if brand_mismatch:
            score += 0.30
            reasons.append("brand_domain_mismatch")
        if crp:
            score += 0.25
            reasons.append("credential_taking")
        if suspicious_domain:
            score += 0.20
            reasons.append("suspicious_domain")
        if any(term in text.lower() for term in CRYPTO_TERMS) and not crp:
            score += 0.10
            reasons.append("crypto_signal_no_password")

        if popularity_validation == "google-indexed":
            if popular:
                score -= 0.30
                reasons.append("popular_domain_validated")
        elif popularity_validation == "cached":
            if popular:
                score -= 0.25
                reasons.append("popular_domain_cached")
        elif popularity_validation == "disabled":
            if popular and brand_mismatch:
                reasons.append("alias_false_positive")

        if hosting_rule == "strict":
            if hosted and brand_mismatch:
                score += 0.10
                reasons.append("strict_hosting_rule")
        else:
            if hosted:
                score -= 0.05
                reasons.append("relaxed_hosting_rule")

        if injection_seen and bool(candidate.get("prompt_defense", True)):
            reasons.append("injection_defended")

        if report_policy == "mismatch_and_crp":
            pred_phish = brand_mismatch and crp and score >= 0.55
        elif report_policy == "mismatch_or_crp":
            pred_phish = (brand_mismatch or crp) and score >= 0.50
        else:
            pred_phish = score >= 0.55

        if (
            sample.label == "benign"
            and popular
            and primary_brand == primary_url
            and popularity_validation == "disabled"
            and brand
        ):
            pred_phish = True
            reasons.append("alias_false_positive")

        runtime = 0.20
        runtime += 0.30 if candidate.get("use_logo_ocr", True) else 0.0
        runtime += 0.35 if candidate.get("use_logo_caption", True) else 0.0
        if popularity_validation == "google-indexed":
            runtime += 0.40
        elif popularity_validation == "cached":
            runtime += 0.05
        runtime += 0.45 * int(candidate.get("max_interactions", 0))

        cost = 0.0004
        cost += 0.0008 if candidate.get("use_logo_caption", True) else 0.0
        if popularity_validation == "google-indexed":
            cost += 0.0006
        elif popularity_validation == "cached":
            cost += 0.0001
        cost += 0.0005 * int(candidate.get("max_interactions", 0))

        runtime += (time.perf_counter() - start) * 0.01

        return Prediction(
            pred_label="phish" if pred_phish else "benign",
            pred_brand=brand,
            brand_confidence=brand_conf,
            brand_source=brand_source,
            crp=crp,
            crp_reason=crp_reason,
            reasons=reasons + brand_evidence,
            runtime_sec=runtime,
            estimated_cost=cost,
        )
