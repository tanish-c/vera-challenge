from __future__ import annotations

import os
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from composer import compose

app = FastAPI()

START_TIME = time.time()

TEAM_NAME = os.getenv("TEAM_NAME", "")
TEAM_MEMBERS = [m.strip() for m in os.getenv("TEAM_MEMBERS", "").split(",") if m.strip()] or ["Tanish Chhabra"]
MODEL_NAME = os.getenv("MODEL_NAME", "template-composer")
APPROACH = os.getenv("APPROACH", "deterministic context-aware templates")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "imtanish09@gmail.com")
VERSION = os.getenv("BOT_VERSION", "0.1.0")
SUBMITTED_AT = os.getenv("SUBMITTED_AT", datetime.utcnow().isoformat() + "Z")

contexts: dict[str, dict[str, dict[str, Any]]] = {
    "category": {},
    "merchant": {},
    "customer": {},
    "trigger": {},
}

conversations: dict[str, dict[str, Any]] = {}
suppression_keys: set[str] = set()
auto_reply_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))


class ContextBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict
    delivered_at: str | None = None


class TickBody(BaseModel):
    now: str
    available_triggers: list[str] = []


class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str
    message: str
    received_at: str
    turn_number: int


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _safe_slug(value: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in value)


def _is_hostile(msg: str) -> bool:
    lower = msg.lower()
    return any(p in lower for p in [
        "stop messaging", "stop", "spam", "not interested", "unsubscribe",
        "dont message", "do not message", "leave me alone", "no interest",
    ])


def _is_auto_reply(msg: str) -> bool:
    lower = msg.lower()
    patterns = [
        "thank you for contacting", "we will respond", "we'll respond",
        "our team will respond", "auto-reply", "automated response",
        "currently unavailable", "out of office", "away from the phone",
    ]
    return any(p in lower for p in patterns)


def _is_commitment(msg: str) -> bool:
    lower = msg.lower()
    return any(p in lower for p in [
        "yes", "ok", "okay", "lets do it", "let's do it", "go ahead",
        "do it", "proceed", "send it", "sounds good", "sure",
        "please do", "do this", "do that",
    ])


def _is_curveball(msg: str) -> bool:
    lower = msg.lower()
    return any(p in lower for p in ["gst", "tax", "filing", "accounting"])


def _build_action(trigger_id: str) -> dict[str, Any] | None:
    trg_entry = contexts["trigger"].get(trigger_id)
    if not trg_entry:
        return None
    trigger = trg_entry["payload"]
    merchant_id = trigger.get("merchant_id")
    if not merchant_id:
        return None
    merchant_entry = contexts["merchant"].get(merchant_id)
    if not merchant_entry:
        return None
    merchant = merchant_entry["payload"]
    category_slug = merchant.get("category_slug")
    category_entry = contexts["category"].get(category_slug)
    if not category_entry:
        return None
    category = category_entry["payload"]

    customer = None
    if trigger.get("scope") == "customer":
        customer_id = trigger.get("customer_id")
        if not customer_id:
            return None
        customer_entry = contexts["customer"].get(customer_id)
        if not customer_entry:
            return None
        customer = customer_entry["payload"]

    msg = compose(category, merchant, trigger, customer)
    if not msg:
        return None

    suppression_key = msg.get("suppression_key") or trigger.get("suppression_key")
    if suppression_key in suppression_keys:
        return None

    conversation_id = f"conv_{merchant_id}_{trigger_id}"
    template_name = f"vera_{_safe_slug(trigger.get('kind', 'generic'))}_v1"

    action = {
        "conversation_id": conversation_id,
        "merchant_id": merchant_id,
        "customer_id": trigger.get("customer_id"),
        "send_as": msg["send_as"],
        "trigger_id": trigger_id,
        "template_name": template_name,
        "template_params": [merchant.get("identity", {}).get("name", ""), msg["body"], msg["cta"]],
        "body": msg["body"],
        "cta": msg["cta"],
        "suppression_key": suppression_key,
        "rationale": msg["rationale"],
    }

    suppression_keys.add(suppression_key)
    conversations[conversation_id] = {
        "trigger_id": trigger_id,
        "merchant_id": merchant_id,
        "customer_id": trigger.get("customer_id"),
        "last_body": msg["body"],
        "messages": [{"from": msg["send_as"], "msg": msg["body"]}],
    }
    return action


@app.get("/v1/healthz")
def healthz():
    uptime = int(time.time() - START_TIME)
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "contexts_loaded": {k: len(v) for k, v in contexts.items()},
    }


@app.get("/v1/metadata")
def metadata():
    return {
        "team_name": TEAM_NAME,
        "team_members": TEAM_MEMBERS,
        "model": MODEL_NAME,
        "approach": APPROACH,
        "contact_email": CONTACT_EMAIL,
        "version": VERSION,
        "submitted_at": SUBMITTED_AT,
    }


@app.post("/v1/context")
def push_context(body: ContextBody):
    if body.scope not in contexts:
        return JSONResponse(status_code=400, content={
            "accepted": False, "reason": "invalid_scope", "details": body.scope
        })

    scope_store = contexts[body.scope]
    existing = scope_store.get(body.context_id)
    if existing:
        if body.version < existing["version"]:
            return JSONResponse(status_code=409, content={
                "accepted": False,
                "reason": "stale_version",
                "current_version": existing["version"],
            })
        if body.version == existing["version"]:
            return {
                "accepted": True,
                "ack_id": f"ack_{body.context_id}_v{body.version}",
                "stored_at": _now_iso(),
            }

    scope_store[body.context_id] = {"version": body.version, "payload": body.payload}
    return {
        "accepted": True,
        "ack_id": f"ack_{body.context_id}_v{body.version}",
        "stored_at": _now_iso(),
    }


@app.post("/v1/tick")
def tick(body: TickBody):
    actions = []
    for trigger_id in body.available_triggers:
        if len(actions) >= 20:
            break
        action = _build_action(trigger_id)
        if action:
            actions.append(action)
    return {"actions": actions}


@app.post("/v1/reply")
def reply(body: ReplyBody):
    convo = conversations.setdefault(body.conversation_id, {
        "messages": [],
        "merchant_id": body.merchant_id,
        "customer_id": body.customer_id,
    })
    convo["messages"].append({"from": body.from_role, "msg": body.message})

    msg = body.message.strip()
    if not msg:
        return {"action": "end", "rationale": "Empty reply."}

    if _is_hostile(msg):
        return {"action": "end", "rationale": "Merchant opted out or hostile."}

    merchant_id = body.merchant_id or "unknown"
    if _is_auto_reply(msg):
        auto_reply_counts[merchant_id][msg] += 1
        count = auto_reply_counts[merchant_id][msg]
        if count == 1:
            response = {
                "action": "send",
                "body": "Got it - looks like an auto-reply. If the owner is available, reply YES and I will share the exact update; otherwise I will check back later.",
                "cta": "binary_yes_no",
                "rationale": "Auto-reply detected; one low-friction check to reach the owner.",
            }
            _finalize_reply(convo, response)
            return response
        return {"action": "end", "rationale": "Repeated auto-reply; exiting to avoid spam."}

    if _is_commitment(msg):
        response = {
            "action": "send",
            "body": "Done. Drafting the next step now and will share it here shortly.",
            "cta": "open_ended",
            "rationale": "Merchant signaled commitment; switching to action mode.",
        }
        _finalize_reply(convo, response)
        return response

    if _is_curveball(msg):
        response = {
            "action": "send",
            "body": "I cannot help with that directly. Coming back to the current item - want me to draft the message for you?",
            "cta": "open_ended",
            "rationale": "Out-of-scope request; redirecting to the active trigger.",
        }
        _finalize_reply(convo, response)
        return response

    response = {
        "action": "send",
        "body": "Got it. Tell me which offer or outcome you want to highlight and I will draft the message.",
        "cta": "open_ended",
        "rationale": "Acknowledged reply and requested the smallest missing input.",
    }
    _finalize_reply(convo, response)
    return response


def _finalize_reply(convo: dict, response: dict) -> None:
    if response.get("action") != "send":
        return
    body = response.get("body", "")
    last_body = convo.get("last_body")
    if body and body == last_body:
        response["body"] = body + " Let me know if you want a different angle."
    convo["last_body"] = response.get("body")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("bot:app", host="0.0.0.0", port=port, reload=False)
