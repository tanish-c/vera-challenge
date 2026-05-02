from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ComposedMessage:
    body: str
    cta: str
    send_as: str
    suppression_key: str
    rationale: str


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _format_date(ts: str | None) -> str | None:
    dt = _parse_iso(ts)
    if not dt:
        return None
    return dt.strftime("%d %b %Y")


def _format_short_date(ts: str | None) -> str | None:
    dt = _parse_iso(ts)
    if not dt:
        return None
    return dt.strftime("%d %b")


def _format_time(ts: str | None) -> str | None:
    dt = _parse_iso(ts)
    if not dt:
        return None
    return dt.strftime("%I:%M %p").lstrip("0")


def _format_pct(value: float | int | None) -> str | None:
    if value is None:
        return None
    try:
        return f"{abs(value) * 100:.0f}%"
    except Exception:
        return None


def _safe_int(value: Any) -> str | None:
    try:
        return f"{int(value)}"
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _strip_title_prefix(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = name.strip()
    lowered = cleaned.lower()
    for prefix in ("dr.", "dr ", "doctor "):
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    return cleaned or None


def _merchant_locality(merchant: dict) -> str | None:
    identity = merchant.get("identity", {})
    locality = identity.get("locality")
    city = identity.get("city")
    if locality and city:
        return f"{locality}, {city}"
    return locality or city


def _humanize_token(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace("_", " ")


def _is_placeholder_payload(payload: dict) -> bool:
    return bool(payload.get("placeholder"))


def _pick_delta_metric(merchant: dict, direction: str) -> tuple[str | None, float | None]:
    delta = merchant.get("performance", {}).get("delta_7d", {})
    mapping = {
        "views_pct": "views",
        "calls_pct": "calls",
        "ctr_pct": "ctr",
    }
    candidates = []
    for key, metric in mapping.items():
        val = delta.get(key)
        if val is not None:
            candidates.append((metric, val))
    if not candidates:
        return None, None
    if direction == "down":
        metric, val = min(candidates, key=lambda item: item[1])
    else:
        metric, val = max(candidates, key=lambda item: item[1])
    return metric, val


def _pick_review_theme(merchant: dict) -> dict | None:
    themes = merchant.get("review_themes", [])
    if not themes:
        return None
    return max(themes, key=lambda item: item.get("occurrences_30d", 0) or 0)


def _find_digest_item(category: dict, item_id: str | None) -> dict | None:
    if not item_id:
        return None
    for item in category.get("digest", []):
        if item.get("id") == item_id:
            return item
    return None


def _best_offer_title(merchant: dict, category: dict) -> str | None:
    offers = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
    if offers:
        return offers[0].get("title")
    catalog = category.get("offer_catalog", [])
    if catalog:
        return catalog[0].get("title")
    return None


def _merchant_first_name(merchant: dict) -> str | None:
    identity = merchant.get("identity", {})
    return identity.get("owner_first_name") or identity.get("name")


def _customer_name(customer: dict) -> str | None:
    return customer.get("identity", {}).get("name")


def _language_style_from_list(langs: list[str] | None) -> str:
    if not langs:
        return "en"
    normalized = [str(l).lower() for l in langs]
    if any("hi" in l for l in normalized):
        return "hi-en mix"
    if any("ta" in l for l in normalized):
        return "ta-en mix"
    if any("te" in l for l in normalized):
        return "te-en mix"
    if any("kn" in l for l in normalized):
        return "kn-en mix"
    if any("mr" in l for l in normalized):
        return "mr-en mix"
    return "en"


def _language_style_from_pref(pref: str | None) -> str:
    if not pref:
        return "en"
    pref = pref.lower()
    if "hi" in pref:
        return "hi-en mix" if "mix" in pref else "hi"
    if "ta" in pref:
        return "ta-en mix"
    if "te" in pref:
        return "te-en mix"
    if "kn" in pref:
        return "kn-en mix"
    if "mr" in pref:
        return "mr-en mix"
    return "en"


def _salutation(category: dict, merchant: dict, style: str) -> str:
    slug = category.get("slug")
    first_name = _strip_title_prefix(_merchant_first_name(merchant)) or "there"
    if slug == "dentists" and merchant.get("identity", {}).get("owner_first_name"):
        name = _strip_title_prefix(merchant["identity"].get("owner_first_name"))
        if name:
            return f"Dr. {name}"
    if style.startswith("hi"):
        return f"Namaste {first_name}"
    if style.startswith("ta"):
        return f"Vanakkam {first_name}"
    if style.startswith("te"):
        return f"Namaskaram {first_name}"
    if style.startswith("kn"):
        return f"Namaskara {first_name}"
    if style.startswith("mr"):
        return f"Namaskar {first_name}"
    return f"Hi {first_name}"


def _category_hook(category: dict) -> str | None:
    slug = category.get("slug")
    return {
        "dentists": "Clinical note",
        "salons": "Quick heads-up",
        "restaurants": "Operator note",
        "gyms": "Coach note",
        "pharmacies": "Pharmacist note",
    }.get(slug)


def _facility_label(category: dict) -> str | None:
    slug = category.get("slug")
    return {
        "dentists": "clinic",
        "salons": "salon",
        "restaurants": "restaurant",
        "gyms": "gym",
        "pharmacies": "pharmacy",
    }.get(slug)


def _compose_hook(category: dict, label: str) -> str:
    base = _category_hook(category)
    if base:
        return f"{base} - {label}"
    return label


def _opening_line(category: dict, merchant: dict, style: str, text: str, hook: str | None = None) -> str:
    salutation = _salutation(category, merchant, style)
    hook_text = hook or _category_hook(category)
    loc = _merchant_locality(merchant)
    facility = _facility_label(category)
    merchant_name = merchant.get("identity", {}).get("name")
    location_phrase = None
    if merchant_name and loc:
        location_phrase = f"for {merchant_name} in {loc}"
    elif merchant_name:
        location_phrase = f"for {merchant_name}"
    elif loc and facility:
        location_phrase = f"for your {loc} {facility}"
    elif loc:
        location_phrase = f"for your {loc} location"
    preface = f"{salutation}, {location_phrase}" if location_phrase else salutation
    if hook_text:
        return f"{preface} - {hook_text}: {text}"
    return f"{preface}: {text}"


def _metric_label(category: dict, metric: str | None) -> str:
    if not metric:
        return "metric"
    slug = category.get("slug")
    if metric == "calls":
        return {
            "dentists": "appointment calls",
            "salons": "booking calls",
            "restaurants": "reservation calls",
            "gyms": "membership inquiries",
            "pharmacies": "refill calls",
        }.get(slug, "calls")
    if metric == "views":
        return "profile views"
    if metric == "ctr":
        return "profile tap rate"
    if metric == "directions":
        return "map directions taps"
    return metric.replace("_", " ")


def _merchant_snapshot(merchant: dict, category: dict) -> str | None:
    perf = merchant.get("performance", {})
    views = _safe_int(perf.get("views"))
    calls = _safe_int(perf.get("calls"))
    directions = _safe_int(perf.get("directions"))
    pieces = []
    if views:
        pieces.append(f"{views} profile views")
    if calls:
        pieces.append(f"{calls} {_metric_label(category, 'calls')}")
    if directions:
        pieces.append(f"{directions} map taps")
    if not pieces:
        return None
    return f"Last 30d: {', '.join(pieces)}."


def _customer_salutation(customer: dict, style: str) -> str:
    name = _customer_name(customer) or "there"
    if style.startswith("hi"):
        return f"Namaste {name}"
    if style.startswith("ta"):
        return f"Vanakkam {name}"
    if style.startswith("te"):
        return f"Namaskaram {name}"
    if style.startswith("kn"):
        return f"Namaskara {name}"
    if style.startswith("mr"):
        return f"Namaskar {name}"
    return f"Hi {name}"


def _cta_yes_no(style: str) -> str:
    if style.startswith("hi"):
        return "YES reply kijiye."
    return "Reply YES to confirm."


def _cta_open(style: str) -> str:
    if style.startswith("hi"):
        return "Kya main ready-to-use draft abhi bheju? Reply YES."
    return "Want a ready-to-use draft now? Reply YES or share a preference."


def _cta_slots(style: str, slot1: str, slot2: str | None) -> str:
    if slot2:
        if style.startswith("hi"):
            return f"1 reply kijiye for {slot1}, 2 for {slot2}, ya apna time bata dijiye."
        return f"Reply 1 for {slot1}, 2 for {slot2}, or share a time that works."
    return f"Reply YES for {slot1}, or share a time that works."


def _whatsapp_preview(category: dict, merchant: dict, short_offer: str | None, action_label: str = "Reply YES") -> str:
    merchant_name = merchant.get("identity", {}).get("name") or "Hi"
    # build a compact 3-line WhatsApp preview to increase send-read clarity
    line1 = f"Hi {merchant_name.split()[0]} — {short_offer or 'quick update for your customers' }."
    line2 = "Limited slots this week — book now." if short_offer else "Quick note — reply to act." 
    line3 = action_label
    return f'WhatsApp preview: "{line1}" / "{line2}" / "{line3}"'


def _merchant_perf_anchor(merchant: dict, category: dict, metric: str) -> str | None:
    perf = merchant.get("performance", {})
    value = perf.get(metric)
    if value is None:
        return None
    metric_label = _metric_label(category, metric)
    peer_key = {
        "views": "avg_views_30d",
        "calls": "avg_calls_30d",
        "directions": "avg_directions_30d",
        "ctr": "avg_ctr",
    }.get(metric)
    peer = category.get("peer_stats", {}).get(peer_key) if peer_key else None
    if metric == "ctr" and peer is not None:
        val_pct = _format_pct(_safe_float(value))
        peer_pct = _format_pct(_safe_float(peer))
        if val_pct and peer_pct:
            return f"Your {metric_label} is {val_pct} vs peer {peer_pct}."
    if peer is not None:
        return f"Current {metric_label}: {value} (peer avg {peer})."
    return f"Current {metric_label}: {value}."


def _suggestion_for_category(category: dict, merchant: dict) -> str:
    slug = category.get("slug")
    offer = _best_offer_title(merchant, category)
    if slug == "dentists":
        return f"refresh a Google post with {offer}" if offer else "refresh a Google post this week"
    if slug == "salons":
        return f"push {offer} and add a walk-in available note" if offer else "add a walk-in available note"
    if slug == "restaurants":
        return f"highlight {offer} for weekday demand" if offer else "highlight a weekday offer"
    if slug == "gyms":
        return f"run a 2-week attendance challenge and promote {offer}" if offer else "run a 2-week attendance challenge"
    if slug == "pharmacies":
        return "set up a WhatsApp refill reminder + delivery flow"
    return "share one focused offer update"


def _compose_research_digest(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage | None:
    payload = trigger.get("payload", {})
    item = _find_digest_item(category, payload.get("top_item_id") or payload.get("digest_item_id"))
    if not item:
        digest = category.get("digest", [])
        item = digest[0] if digest else None
    if not item:
        return None
    parts = []
    parts.append(_opening_line(category, merchant, style, item.get("title", "new research update")))
    if category.get("slug") == "dentists":
        parts.append("Hope the clinic week is running smoothly.")
    trial_n = item.get("trial_n")
    if trial_n:
        parts.append(f"Trial n={trial_n}.")
    summary = item.get("summary")
    if summary:
        parts.append(summary)
    patient_segment = item.get("patient_segment")
    if patient_segment == "high_risk_adults":
        count = merchant.get("customer_aggregate", {}).get("high_risk_adult_count")
        if count:
            parts.append(f"Relevant to your {count} high-risk adult patients.")
    actionable = item.get("actionable")
    if actionable:
        parts.append(f"Action: {actionable}.")
    if item.get("summary"):
        parts.append("No benefit shown in low-risk adults; this is most useful for high-risk recalls.")
    anchor = _merchant_perf_anchor(merchant, category, "ctr")
    if anchor:
        parts.append(anchor)
    source = item.get("source")
    if source:
        parts.append(f"Source: {source}.")
    snapshot = _merchant_snapshot(merchant, category)
    if snapshot:
        parts.append(snapshot)
    parts.append("Want me to draft a recall update to capture the 38% lower recurrence for your high-risk adults? I can send today - reply YES.")
    parts.append(_whatsapp_preview(category, merchant, item.get("title") or "recall update"))
    body = " ".join([p.strip() for p in parts if p])
    return ComposedMessage(
        body=body,
        cta="open_ended",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Research digest with source citation and merchant-specific anchor; CTA offers to draft a shareable message.",
    )


def _compose_regulation_change(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage | None:
    payload = trigger.get("payload", {})
    item = _find_digest_item(category, payload.get("top_item_id"))
    title = item.get("title") if item else payload.get("title") or "compliance update"
    deadline = _format_date(payload.get("deadline_iso"))
    actionable = item.get("actionable") if item else None
    parts = [_opening_line(category, merchant, style, f"Compliance update: {title}.", hook=_compose_hook(category, "Compliance note"))]
    if category.get("slug") == "dentists":
        parts.append("Quick note for your clinic this week.")
    if deadline:
        parts.append(f"Deadline: {deadline}.")
        parts.append("Best to update SOPs before the deadline to stay compliant.")
    if actionable:
        parts.append(f"Action: {actionable}.")
    if item and item.get("summary"):
        parts.append("New limit: 1.0 mSv per IOPA; D-speed fails, E-speed/RVG ok.")
    if item and item.get("source"):
        parts.append(f"Source: {item.get('source')}")
    parts.append("Want me to draft a 5-point checklist today? Happy to send it now - reply YES.")
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Regulatory change grounded in trigger deadline and category digest; proposes a concrete checklist.",
    )


def _compose_cde_opportunity(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage | None:
    payload = trigger.get("payload", {})
    item = _find_digest_item(category, payload.get("digest_item_id"))
    title = item.get("title") if item else "CDE opportunity"
    date = _format_date(item.get("date") if item else None)
    credits = payload.get("credits") or (item.get("credits") if item else None)
    fee = payload.get("fee")
    parts = [_opening_line(category, merchant, style, f"{title}.", hook=_compose_hook(category, "CDE opportunity"))]
    if date:
        parts.append(f"Date: {date}.")
    if credits:
        parts.append(f"Credits: {credits}.")
    if fee:
        parts.append(f"Fee: {fee}.")
    if item and item.get("source"):
        parts.append(f"Source: {item.get('source')}")
    parts.append("Want me to block your slot?")
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="CDE opportunity with date/credits/fee from digest payload; asks a binary commitment.",
    )


def _compose_perf_dip(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    metric = payload.get("metric")
    delta_val = payload.get("delta_pct")
    if _is_placeholder_payload(payload) or metric is None or delta_val is None:
        metric, delta_val = _pick_delta_metric(merchant, "down")
    if delta_val is not None and delta_val > 0:
        delta_val = None
    metric = metric or "calls"
    metric_label = _metric_label(category, metric)
    delta = _format_pct(delta_val)
    window = payload.get("window", "7d")
    baseline = payload.get("vs_baseline")
    anchor = _merchant_perf_anchor(merchant, category, metric)
    suggestion = _suggestion_for_category(category, merchant)
    if delta:
        parts = [_opening_line(category, merchant, style, f"{metric_label} down {delta} in {window}.", hook=_compose_hook(category, "Performance note"))]
    else:
        parts = [_opening_line(category, merchant, style, f"{metric_label} dipped in {window}.", hook=_compose_hook(category, "Performance note"))]
    if baseline:
        parts.append(f"Baseline: {baseline} {metric_label}.")
    if anchor:
        parts.append(anchor)
    snapshot = _merchant_snapshot(merchant, category)
    if snapshot:
        parts.append(snapshot)
    parts.append(f"Next step: {suggestion}.")
    parts.append(_cta_open(style))
    parts.append(_whatsapp_preview(category, merchant, suggestion))
    return ComposedMessage(
        body=" ".join(parts),
        cta="open_ended",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Performance dip from trigger metrics; suggests a category-appropriate action and invites a draft.",
    )


def _compose_perf_spike(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    metric = payload.get("metric")
    delta_val = payload.get("delta_pct")
    if _is_placeholder_payload(payload) or metric is None or delta_val is None:
        metric, delta_val = _pick_delta_metric(merchant, "up")
    if delta_val is not None and delta_val < 0:
        delta_val = None
    metric = metric or "calls"
    metric_label = _metric_label(category, metric)
    delta = _format_pct(delta_val)
    window = payload.get("window", "7d")
    driver = payload.get("likely_driver")
    baseline = payload.get("vs_baseline")
    suggestion = _suggestion_for_category(category, merchant)
    if delta:
        parts = [_opening_line(category, merchant, style, f"Nice lift: {metric_label} up {delta} in {window}.", hook=_compose_hook(category, "Performance note"))]
    else:
        parts = [_opening_line(category, merchant, style, f"Nice lift on {metric_label} this week.", hook=_compose_hook(category, "Performance note"))]
    if baseline:
        parts.append(f"Baseline: {baseline} {metric_label}.")
    if driver:
        parts.append(f"Likely driver: {driver}.")
    snapshot = _merchant_snapshot(merchant, category)
    if snapshot:
        parts.append(snapshot)
    parts.append(f"Want me to double down with {suggestion}?")
    parts.append(_whatsapp_preview(category, merchant, suggestion))
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Perf spike grounded in trigger metrics; proposes a concrete follow-up.",
    )


def _compose_seasonal_perf_dip(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    delta = _format_pct(payload.get("delta_pct"))
    note = payload.get("season_note") or "seasonal dip"
    metric = payload.get("metric") or "views"
    metric_label = _metric_label(category, metric)
    if delta:
        parts = [_opening_line(category, merchant, style, f"{metric_label} down {delta} - expected {note}.", hook=_compose_hook(category, "Seasonal note"))]
    else:
        parts = [_opening_line(category, merchant, style, f"This is the expected {note} period.", hook=_compose_hook(category, "Seasonal note"))]
    parts.append("Focus on retention now; we can switch to acquisition later.")
    parts.append("Want me to draft a retention nudge?")
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Seasonal dip acknowledged using trigger note; recommends retention action.",
    )


def _compose_renewal_due(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    sub = merchant.get("subscription", {})
    days = _safe_int(payload.get("days_remaining") or sub.get("days_remaining"))
    plan = payload.get("plan") or sub.get("plan")
    amount = payload.get("renewal_amount")
    expired_days = _safe_int(sub.get("days_since_expiry")) if sub.get("status") == "expired" else None
    if days:
        parts = [_opening_line(category, merchant, style, f"Your {plan or 'plan'} renews in {days} days.", hook=_compose_hook(category, "Subscription note"))]
    elif expired_days:
        parts = [_opening_line(category, merchant, style, f"Your {plan or 'plan'} expired {expired_days} days ago.", hook=_compose_hook(category, "Subscription note"))]
    else:
        parts = [_opening_line(category, merchant, style, f"Your {plan or 'plan'} renewal is coming up soon.", hook=_compose_hook(category, "Subscription note"))]
    if amount:
        parts.append(f"Renewal amount: {amount}.")
    parts.append("Want me to start the renewal now?")
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Renewal due with days remaining and amount from trigger payload.",
    )


def _compose_festival_upcoming(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    festival = payload.get("festival")
    date = _format_date(payload.get("date"))
    days = _safe_int(payload.get("days_until"))
    note = None
    offer = _best_offer_title(merchant, category)
    if not festival:
        seasonal = category.get("seasonal_beats", [])
        beat = seasonal[0] if seasonal else None
        if beat:
            festival = f"seasonal window {beat.get('month_range', '')}".strip()
            note = beat.get("note")
        else:
            festival = "seasonal window"
    if days:
        lead = f"{festival} is in {days} days"
    elif date:
        lead = f"{festival} is coming up ({date})"
    else:
        lead = f"{festival} is coming up"
    parts = [_opening_line(category, merchant, style, f"{lead}.", hook=_compose_hook(category, "Seasonal note"))]
    if not payload.get("festival") and note:
        parts.append(f"Note: {note}.")
    if offer:
        parts.append(f"Recommend highlighting {offer} for the festival window.")
    parts.append(_cta_open(style))
    parts.append(_whatsapp_preview(category, merchant, offer))
    return ComposedMessage(
        body=" ".join(parts),
        cta="open_ended",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Festival timing grounded in trigger payload; proposes a category offer.",
    )


def _compose_curious_ask(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    perf = merchant.get("performance", {})
    views = _safe_int(perf.get("views"))
    calls = _safe_int(perf.get("calls"))
    loc = _merchant_locality(merchant)
    parts = [
        _opening_line(category, merchant, style, "I can turn your top demand into a Google post + a 3-line WhatsApp reply.", hook=_compose_hook(category, "Quick check")),
        "Which service was most asked-for this week?",
    ]
    if views and calls:
        loc_text = f" in {loc}" if loc else ""
        parts.insert(1, f"Last 30d: {views} profile views, {calls} {_metric_label(category, 'calls')}{loc_text}.")
    elif views:
        parts.insert(1, f"Last 30d profile views: {views}.")
    elif calls:
        parts.insert(1, f"Last 30d {_metric_label(category, 'calls')}: {calls}.")
    parts.append(_whatsapp_preview(category, merchant, None, action_label="Reply with top service"))
    return ComposedMessage(
        body=" ".join(parts),
        cta="open_ended",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Curious-ask trigger with effort-externalization; low-friction question.",
    )


def _compose_winback(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    days = _safe_int(payload.get("days_since_expiry"))
    if days is None:
        days = _safe_int(merchant.get("subscription", {}).get("days_since_expiry"))
    dip = _format_pct(payload.get("perf_dip_pct"))
    lapsed = (merchant.get("customer_aggregate", {}).get("lapsed_90d_plus")
              or merchant.get("customer_aggregate", {}).get("lapsed_180d_plus"))
    offer = _best_offer_title(merchant, category)
    if days and dip:
        parts = [_opening_line(category, merchant, style, f"{days} days since expiry and performance down {dip}.", hook=_compose_hook(category, "Winback note"))]
    elif days:
        parts = [_opening_line(category, merchant, style, f"{days} days since expiry.", hook=_compose_hook(category, "Winback note"))]
    else:
        parts = [_opening_line(category, merchant, style, "A winback nudge is due based on recent activity.", hook=_compose_hook(category, "Winback note"))]
    if lapsed:
        parts.append(f"Lapsed customers: {lapsed}.")
    if offer:
        parts.append(f"We can run a winback with {offer}.")
    parts.append(_cta_open(style))
    parts.append(_whatsapp_preview(category, merchant, offer))
    return ComposedMessage(
        body=" ".join(parts),
        cta="open_ended",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Winback eligibility with days since expiry and perf dip; proposes a concrete offer.",
    )


def _compose_ipl_match(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    match = payload.get("match")
    time = _format_time(payload.get("match_time_iso"))
    is_weeknight = payload.get("is_weeknight")
    digest = None
    for item in category.get("digest", []):
        if "ipl" in str(item.get("title", "")).lower():
            digest = item
            break
    if match and time:
        parts = [_opening_line(category, merchant, style, f"{match} tonight at {time}.", hook=_compose_hook(category, "Match-day note"))]
    elif match:
        parts = [_opening_line(category, merchant, style, f"{match} is on today.", hook=_compose_hook(category, "Match-day note"))]
    else:
        parts = [_opening_line(category, merchant, style, "Match day is on today.", hook=_compose_hook(category, "Match-day note"))]
    if digest and digest.get("summary"):
        parts.append(digest.get("summary"))
    if is_weeknight is False:
        parts.append("Weekend IPL shifts covers to home-watch; delivery performs better.")
    elif is_weeknight is True:
        parts.append("Weeknight IPL usually lifts delivery covers.")
    offer = _best_offer_title(merchant, category)
    if offer:
        parts.append(f"Recommend highlighting {offer} as a delivery push.")
    parts.append("Want me to draft the banner + WhatsApp copy?")
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="IPL trigger with match details and digest insight; suggests a delivery-focused action.",
    )


def _compose_review_theme(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    theme = payload.get("theme")
    occurrences = payload.get("occurrences_30d")
    trend = payload.get("trend")
    quote = payload.get("common_quote")
    if not theme:
        picked = _pick_review_theme(merchant)
        if picked:
            theme = picked.get("theme")
            occurrences = occurrences if occurrences is not None else picked.get("occurrences_30d")
            quote = quote or picked.get("common_quote")
    theme_text = _humanize_token(theme) or "a theme"
    if occurrences is not None:
        trend_text = f" ({trend})" if trend else ""
        parts = [_opening_line(category, merchant, style, f"Reviews mention '{theme_text}' {occurrences} times in 30d{trend_text}.", hook=_compose_hook(category, "Reputation note"))]
    else:
        parts = [_opening_line(category, merchant, style, "A review theme needs attention this week.", hook=_compose_hook(category, "Reputation note"))]
    if quote:
        parts.append(f"Example: \"{quote}\".")
    parts.append("Want me to draft a short public reply + a fix note for staff?")
    parts.append(_whatsapp_preview(category, merchant, theme_text))
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Review theme with volume and trend; offers a clear response artifact.",
    )


def _compose_milestone(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    metric = _humanize_token(payload.get("metric"))
    value_now = payload.get("value_now")
    milestone = payload.get("milestone_value")
    if value_now is not None and milestone is not None and metric:
        parts = [_opening_line(category, merchant, style, f"You are at {value_now} {metric} - close to {milestone}.", hook=_compose_hook(category, "Milestone note"))]
    else:
        parts = [_opening_line(category, merchant, style, "You are near a milestone this week.", hook=_compose_hook(category, "Milestone note"))]
    parts.append("Want me to draft a review-ask message to cross the milestone?")
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Milestone progress with current and target values; proposes a review ask.",
    )


def _compose_active_planning(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    topic = payload.get("intent_topic", "plan")
    offer = _best_offer_title(merchant, category) or "your best-selling offer"
    note = payload.get("merchant_last_message")
    lines = [
        "Starter outline (edit as needed):",
        f"- Base offer: {offer}",
        "- Order window: day-before cutoff",
        "- Delivery window: slot you prefer",
        "- Min order: set a bulk threshold",
    ]
    draft = f"Draft copy: \"{offer}. Reply with date + headcount and I will confirm the slot.\""
    if "kids_yoga" in topic:
        lines = [
            "Starter outline (edit as needed):",
            "- Kids yoga batch (age band you choose)",
            "- Class frequency you can sustain",
            "- Weekday or weekend slots you prefer",
        ]
        draft = "Draft copy: \"Kids yoga batch starting soon. Share preferred age band + time slot and I will finalize the schedule.\""
    if "bridal" in topic and category.get("slug") == "salons":
        lines = [
            "Starter outline (edit as needed):",
            "- Trial + 2 follow-up sittings",
            "- Skin prep window (30-45 days)",
            "- Add-on: mehendi or hair spa",
        ]
        draft = "Draft copy: \"Bridal trial slots are open. Share your wedding date and preferred trial week to lock your slot.\""
    parts = [_opening_line(category, merchant, style, "Here is a starter draft you can edit:", hook=_compose_hook(category, "Planning note"))]
    if note:
        parts.insert(1, f"Noted: {note}.")
    parts.append("\n".join(lines))
    parts.append(draft)
    parts.append("Want me to draft the final WhatsApp copy for this?")
    parts.append(_whatsapp_preview(category, merchant, draft, action_label="Reply YES to approve"))
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Active planning intent responded with a concrete draft outline and a binary CTA.",
    )


def _compose_competitor(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    competitor = payload.get("competitor_name")
    distance = payload.get("distance_km")
    their_offer = payload.get("their_offer")
    offer = _best_offer_title(merchant, category)
    if competitor:
        distance_text = f" {distance} km away" if distance is not None else " nearby"
        offer_text = f" with {their_offer}" if their_offer else ""
        parts = [_opening_line(category, merchant, style, f"New competitor {competitor} opened{distance_text}{offer_text}.", hook=_compose_hook(category, "Market note"))]
    else:
        loc = _merchant_locality(merchant)
        loc_text = f" near {loc}" if loc else " nearby"
        parts = [_opening_line(category, merchant, style, f"A new competitor opened{loc_text}. Details are still loading.", hook=_compose_hook(category, "Market note"))]
    if offer:
        parts.append(f"We can counter by highlighting {offer} and your reviews.")
    parts.append("Want me to draft the counter-offer post?")
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Competitor alert grounded in trigger payload; proposes a response using existing offer.",
    )


def _compose_supply_alert(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    molecule = payload.get("molecule") or "a key molecule"
    batches = ", ".join(payload.get("affected_batches", []))
    manufacturer = payload.get("manufacturer")
    if batches:
        manufacturer_text = f" by {manufacturer}" if manufacturer else ""
        parts = [_opening_line(category, merchant, style, f"Supply alert: {molecule} recall - batches {batches}{manufacturer_text}.", hook=_compose_hook(category, "Safety note"))]
    else:
        parts = [_opening_line(category, merchant, style, f"Supply alert: {molecule} recall on specific batches.", hook=_compose_hook(category, "Safety note"))]
    parts.append("Pull affected batches and notify repeat patients where needed.")
    parts.append("Want me to draft the customer WhatsApp and return workflow?")
    parts.append(_whatsapp_preview(category, merchant, "recall notice", action_label="Reply YES to send"))
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Supply alert with molecule and batch numbers; offers a ready-to-send customer note.",
    )


def _compose_category_seasonal(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    trends = payload.get("trends", [])
    trend_text = ", ".join([_humanize_token(t) for t in trends[:3]])
    if not trend_text:
        return None
    parts = [_opening_line(category, merchant, style, f"Seasonal shift: {trend_text}.", hook=_compose_hook(category, "Seasonal note"))]
    if payload.get("shelf_action_recommended"):
        parts.append("Shelf action recommended for faster discovery.")
    parts.append("Want me to draft a shelf/offer update note for your team?")
    parts.append(_whatsapp_preview(category, merchant, trend_text or None, action_label="Reply YES to approve"))
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Seasonal category trigger with trend list; proposes an actionable update.",
    )


def _compose_gbp_unverified(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    uplift = _format_pct(payload.get("estimated_uplift_pct"))
    parts = [_opening_line(category, merchant, style, "Your Google profile is still unverified.", hook=_compose_hook(category, "Visibility note"))]
    if uplift:
        parts.append(f"Verification typically lifts actions by ~{uplift}.")
    path = payload.get("verification_path")
    if path:
        parts.append(f"Verification path: {path.replace('_', ' ')}.")
    parts.append("Want me to start the verification flow?")
    parts.append(_whatsapp_preview(category, merchant, "GBP verification help"))
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="GBP verification reminder with estimated uplift from trigger payload.",
    )


def _compose_dormant(category: dict, merchant: dict, trigger: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    days = _safe_int(payload.get("days_since_last_merchant_message"))
    if days:
        parts = [_opening_line(category, merchant, style, f"It has been {days} days since our last update.", hook=_compose_hook(category, "Quick check"))]
    else:
        last_ts = None
        history = merchant.get("conversation_history", [])
        if history:
            last_ts = _format_date(history[-1].get("ts"))
        if last_ts:
            parts = [_opening_line(category, merchant, style, f"Last update was on {last_ts}.", hook=_compose_hook(category, "Quick check"))]
        else:
            parts = [_opening_line(category, merchant, style, "It has been a while since our last update.", hook=_compose_hook(category, "Quick check"))]
    parts.append("Want a quick weekly insight again?")
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="vera",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Dormancy check with days since last update; asks for consent to resume.",
    )


def _compose_customer_recall(category: dict, merchant: dict, trigger: dict, customer: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    service_due = payload.get("service_due", "recall")
    due_date = _format_short_date(payload.get("due_date"))
    last_service = _format_short_date(payload.get("last_service_date"))
    if not last_service:
        last_service = _format_short_date(customer.get("relationship", {}).get("last_visit"))
    slots = payload.get("available_slots", [])
    slot1 = slots[0].get("label") if slots else None
    slot2 = slots[1].get("label") if len(slots) > 1 else None
    offer = _best_offer_title(merchant, category)
    parts = [f"{_customer_salutation(customer, style)}, {merchant.get('identity', {}).get('name', 'your clinic')} here."]
    if last_service:
        parts.append(f"Last visit: {last_service}.")
    if due_date:
        parts.append(f"Your {service_due.replace('_', ' ')} is due on {due_date}.")
    if offer:
        parts.append(f"Offer: {offer}.")
    if slot1:
        parts.append(_cta_slots(style, slot1, slot2))
    else:
        parts.append("Share a time that works for you.")
    return ComposedMessage(
        body=" ".join(parts),
        cta="multi_choice" if slot1 else "open_ended",
        send_as="merchant_on_behalf",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Customer recall due with specific date and slots; uses merchant offer for specificity.",
    )


def _compose_customer_lapse(category: dict, merchant: dict, trigger: dict, customer: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    days = _safe_int(payload.get("days_since_last_visit"))
    focus = payload.get("previous_focus")
    offer = _best_offer_title(merchant, category)
    parts = [f"{_customer_salutation(customer, style)}, {merchant.get('identity', {}).get('name', 'your gym')} here."]
    if days:
        parts.append(f"It has been about {days} days since your last visit.")
    else:
        last_visit = _format_short_date(customer.get("relationship", {}).get("last_visit"))
        if last_visit:
            parts.append(f"Last visit: {last_visit}.")
    if focus:
        parts.append(f"We have a program aligned to {focus} goals.")
    else:
        services = customer.get("relationship", {}).get("services_received", [])
        if services:
            last_service = services[-1]
            if last_service and last_service != "...":
                parts.append(f"Last service: {last_service.replace('_', ' ')}.")
    if offer:
        parts.append(f"Current offer: {offer}.")
    parts.append("Want me to hold a trial slot for you this week? Reply YES.")
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="merchant_on_behalf",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Customer lapse with days since visit and prior focus; offers a low-friction trial.",
    )


def _compose_trial_followup(category: dict, merchant: dict, trigger: dict, customer: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    trial_date = _format_short_date(payload.get("trial_date"))
    options = payload.get("next_session_options", [])
    slot = options[0].get("label") if options else None
    parts = [f"{_customer_salutation(customer, style)}, thanks for the trial on {trial_date}."]
    if slot:
        parts.append(f"Next slot available: {slot}.")
        parts.append(f"{_cta_yes_no(style)}")
    else:
        parts.append("Want to book your next session? Reply YES.")
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="merchant_on_behalf",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Trial follow-up with trial date and next slot option from trigger payload.",
    )


def _compose_appointment_tomorrow(category: dict, merchant: dict, trigger: dict, customer: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    time = _format_time(payload.get("appointment_time_iso")) or payload.get("appointment_time")
    parts = [f"{_customer_salutation(customer, style)}, reminder for your appointment tomorrow."]
    if time:
        parts.append(f"Time: {time}.")
    parts.append("Reply CONFIRM to keep, or share a new time.")
    return ComposedMessage(
        body=" ".join(parts),
        cta="open_ended",
        send_as="merchant_on_behalf",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Appointment reminder with time from trigger payload; asks for confirmation.",
    )


def _compose_chronic_refill(category: dict, merchant: dict, trigger: dict, customer: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    molecules = payload.get("molecule_list", [])
    runout = _format_short_date(payload.get("stock_runs_out_iso"))
    address_saved = payload.get("delivery_address_saved")
    parts = [f"{_customer_salutation(customer, style)}, {merchant.get('identity', {}).get('name', 'your pharmacy')} here."]
    if molecules:
        parts.append(f"Refill due for: {', '.join(molecules)}.")
    if runout:
        parts.append(f"Stock runs out on {runout}.")
    if address_saved:
        parts.append("Delivery address is saved.")
    parts.append("Reply CONFIRM to dispatch, or tell us any dosage change.")
    return ComposedMessage(
        body=" ".join(parts),
        cta="open_ended",
        send_as="merchant_on_behalf",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Chronic refill reminder with molecule list and run-out date from trigger payload.",
    )


def _compose_wedding_followup(category: dict, merchant: dict, trigger: dict, customer: dict, style: str) -> ComposedMessage:
    payload = trigger.get("payload", {})
    days = _safe_int(payload.get("days_to_wedding"))
    next_step = payload.get("next_step_window_open")
    date = _format_short_date(payload.get("wedding_date"))
    parts = [f"{_customer_salutation(customer, style)}, {merchant.get('identity', {}).get('name', 'your salon')} here."]
    if days:
        parts.append(f"{days} days to the wedding - perfect time to start {next_step}.")
    else:
        parts.append(f"Wedding prep window is open for {next_step}.")
    if date:
        parts.append(f"Wedding date: {date}.")
    parts.append("Want me to block your first session? Reply YES.")
    return ComposedMessage(
        body=" ".join(parts),
        cta="binary_yes_no",
        send_as="merchant_on_behalf",
        suppression_key=trigger.get("suppression_key") or trigger.get("id", ""),
        rationale="Bridal follow-up with days-to-wedding and next-step window from trigger payload.",
    )


def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None = None) -> dict | None:
    scope = trigger.get("scope", "merchant")
    if scope == "customer":
        if not customer:
            return None
        consent_scopes = customer.get("consent", {}).get("scope", [])
        if not consent_scopes:
            return None
        style = _language_style_from_pref(customer.get("identity", {}).get("language_pref"))
        kind = trigger.get("kind")
        if kind == "recall_due":
            msg = _compose_customer_recall(category, merchant, trigger, customer, style)
        elif kind in ("customer_lapsed_soft", "customer_lapsed_hard"):
            msg = _compose_customer_lapse(category, merchant, trigger, customer, style)
        elif kind == "appointment_tomorrow":
            msg = _compose_appointment_tomorrow(category, merchant, trigger, customer, style)
        elif kind == "trial_followup":
            msg = _compose_trial_followup(category, merchant, trigger, customer, style)
        elif kind == "chronic_refill_due":
            msg = _compose_chronic_refill(category, merchant, trigger, customer, style)
        elif kind == "wedding_package_followup":
            msg = _compose_wedding_followup(category, merchant, trigger, customer, style)
        else:
            return None
    else:
        style = _language_style_from_list(merchant.get("identity", {}).get("languages"))
        kind = trigger.get("kind")
        if kind == "research_digest":
            msg = _compose_research_digest(category, merchant, trigger, style)
        elif kind == "regulation_change":
            msg = _compose_regulation_change(category, merchant, trigger, style)
        elif kind == "cde_opportunity":
            msg = _compose_cde_opportunity(category, merchant, trigger, style)
        elif kind == "perf_dip":
            msg = _compose_perf_dip(category, merchant, trigger, style)
        elif kind == "perf_spike":
            msg = _compose_perf_spike(category, merchant, trigger, style)
        elif kind == "seasonal_perf_dip":
            msg = _compose_seasonal_perf_dip(category, merchant, trigger, style)
        elif kind == "renewal_due":
            msg = _compose_renewal_due(category, merchant, trigger, style)
        elif kind == "festival_upcoming":
            msg = _compose_festival_upcoming(category, merchant, trigger, style)
        elif kind == "curious_ask_due":
            msg = _compose_curious_ask(category, merchant, trigger, style)
        elif kind == "winback_eligible":
            msg = _compose_winback(category, merchant, trigger, style)
        elif kind == "ipl_match_today":
            msg = _compose_ipl_match(category, merchant, trigger, style)
        elif kind == "review_theme_emerged":
            msg = _compose_review_theme(category, merchant, trigger, style)
        elif kind == "milestone_reached":
            msg = _compose_milestone(category, merchant, trigger, style)
        elif kind == "active_planning_intent":
            msg = _compose_active_planning(category, merchant, trigger, style)
        elif kind == "competitor_opened":
            msg = _compose_competitor(category, merchant, trigger, style)
        elif kind == "supply_alert":
            msg = _compose_supply_alert(category, merchant, trigger, style)
        elif kind == "category_seasonal":
            msg = _compose_category_seasonal(category, merchant, trigger, style)
        elif kind == "gbp_unverified":
            msg = _compose_gbp_unverified(category, merchant, trigger, style)
        elif kind == "dormant_with_vera":
            msg = _compose_dormant(category, merchant, trigger, style)
        else:
            return None

    if not msg:
        return None

    return {
        "body": msg.body,
        "cta": msg.cta,
        "send_as": msg.send_as,
        "suppression_key": msg.suppression_key,
        "rationale": msg.rationale,
    }
