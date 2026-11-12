import os
import json
import uuid
import urllib.request
import urllib.error
from datetime import datetime

SUPABASE_URL = "https://jttyndtcfrdxdquoloin.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp0dHluZHRjZnJkeGRxdW9sb2luIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE5ODM3MTMsImV4cCI6MjEwNzU1OTcxM30."
    "wbOV_d9Y3tGs608fBsMFzUAz3b9mh5OCCRpxhylwSZc"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "cms_data.json")


def _get_headers():
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def _load_local_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "literacy_tips": [],
        "guide_principles": [],
        "guide_contents": [],
        "app_info": []
    }


def _save_local_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CMS Local Save Error] {e}")


def _call_supabase(endpoint, method="GET", payload=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = _get_headers()
    data = json.dumps(payload).encode("utf-8") if payload is not None else None

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            res_body = res.read().decode("utf-8")
            if res_body:
                return json.loads(res_body)
            return []
    except Exception as e:
        # Fallback graceful jika jaringan atau RLS Supabase memblokir
        print(f"[Supabase API Error on {method} {endpoint}] {e}")
        return None


# ---------------------------------------------------------------------------
# 1. TIPS LITERASI (literacy_tips)
# ---------------------------------------------------------------------------

def get_literacy_tips():
    # Coba fetch dari Supabase, jika gagal gunakan lokal
    remote = _call_supabase("literacy_tips?select=*&order=order_index.asc")
    local = _load_local_data()

    if remote and len(remote) > 0:
        local["literacy_tips"] = remote
        _save_local_data(local)
        return sorted(remote, key=lambda x: x.get("order_index", 0))

    return sorted(local.get("literacy_tips", []), key=lambda x: x.get("order_index", 0))


def save_tip(tip_data, tip_id=None):
    local = _load_local_data()
    tips = local.get("literacy_tips", [])

    if tip_id:
        # UPDATE
        for t in tips:
            if t.get("id") == tip_id:
                t.update(tip_data)
                break
        _save_local_data(local)
        _call_supabase(f"literacy_tips?id=eq.{tip_id}", method="PATCH", payload=tip_data)
    else:
        # INSERT
        new_id = str(uuid.uuid4())
        tip_data["id"] = new_id
        tip_data["created_at"] = datetime.utcnow().isoformat()
        tips.append(tip_data)
        _save_local_data(local)
        _call_supabase("literacy_tips", method="POST", payload=tip_data)

    return True


def delete_tip(tip_id):
    local = _load_local_data()
    tips = local.get("literacy_tips", [])
    local["literacy_tips"] = [t for t in tips if t.get("id") != tip_id]
    _save_local_data(local)
    _call_supabase(f"literacy_tips?id=eq.{tip_id}", method="DELETE")
    return True


def toggle_tip_status(tip_id):
    local = _load_local_data()
    tips = local.get("literacy_tips", [])
    new_status = True
    for t in tips:
        if t.get("id") == tip_id:
            t["is_active"] = not t.get("is_active", True)
            new_status = t["is_active"]
            break
    _save_local_data(local)
    _call_supabase(f"literacy_tips?id=eq.{tip_id}", method="PATCH", payload={"is_active": new_status})
    return new_status


# ---------------------------------------------------------------------------
# 2. PANDUAN LITERASI (guide_principles & guide_contents)
# ---------------------------------------------------------------------------

def get_guide_data():
    local = _load_local_data()

    # Remote fetch principles
    remote_principles = _call_supabase("guide_principles?select=*&order=order_index.asc")
    if remote_principles and len(remote_principles) > 0:
        local["guide_principles"] = remote_principles

    # Remote fetch contents
    remote_contents = _call_supabase("guide_contents?select=*&limit=1")
    if remote_contents and len(remote_contents) > 0:
        local["guide_contents"] = remote_contents

    _save_local_data(local)

    principles = sorted(local.get("guide_principles", []), key=lambda x: x.get("order_index", 0))
    contents = local.get("guide_contents", [{}])
    content = contents[0] if len(contents) > 0 else {}

    return {
        "principles": principles,
        "content": content
    }


def save_guide_content(quote_text, checklist_title, checklist_subtitle, checklist_items):
    local = _load_local_data()
    contents = local.get("guide_contents", [])

    payload = {
        "quote_text": quote_text,
        "checklist_title": checklist_title,
        "checklist_subtitle": checklist_subtitle,
        "checklist_items": checklist_items
    }

    if contents and len(contents) > 0:
        content_id = contents[0].get("id")
        contents[0].update(payload)
        _save_local_data(local)
        if content_id:
            _call_supabase(f"guide_contents?id=eq.{content_id}", method="PATCH", payload=payload)
    else:
        new_id = str(uuid.uuid4())
        payload["id"] = new_id
        payload["created_at"] = datetime.utcnow().isoformat()
        local["guide_contents"] = [payload]
        _save_local_data(local)
        _call_supabase("guide_contents", method="POST", payload=payload)

    return True


def save_guide_principle(principle_data, principle_id=None):
    local = _load_local_data()
    principles = local.get("guide_principles", [])

    if principle_id:
        for p in principles:
            if p.get("id") == principle_id:
                p.update(principle_data)
                break
        _save_local_data(local)
        _call_supabase(f"guide_principles?id=eq.{principle_id}", method="PATCH", payload=principle_data)
    else:
        new_id = str(uuid.uuid4())
        principle_data["id"] = new_id
        principle_data["created_at"] = datetime.utcnow().isoformat()
        principles.append(principle_data)
        _save_local_data(local)
        _call_supabase("guide_principles", method="POST", payload=principle_data)

    return True


def delete_guide_principle(principle_id):
    local = _load_local_data()
    principles = local.get("guide_principles", [])
    local["guide_principles"] = [p for p in principles if p.get("id") != principle_id]
    _save_local_data(local)
    _call_supabase(f"guide_principles?id=eq.{principle_id}", method="DELETE")
    return True


# ---------------------------------------------------------------------------
# 3. TENTANG HOAXCHECK (app_info)
# ---------------------------------------------------------------------------

def get_app_info():
    local = _load_local_data()
    remote = _call_supabase("app_info?select=*&limit=1")
    if remote and len(remote) > 0:
        local["app_info"] = remote
        _save_local_data(local)
        return remote[0]

    items = local.get("app_info", [])
    return items[0] if len(items) > 0 else {}


def save_app_info(info_data):
    local = _load_local_data()
    items = local.get("app_info", [])

    info_data["updated_at"] = datetime.utcnow().isoformat()

    if items and len(items) > 0:
        app_id = items[0].get("id")
        items[0].update(info_data)
        _save_local_data(local)
        if app_id:
            _call_supabase(f"app_info?id=eq.{app_id}", method="PATCH", payload=info_data)
    else:
        new_id = str(uuid.uuid4())
        info_data["id"] = new_id
        local["app_info"] = [info_data]
        _save_local_data(local)
        _call_supabase("app_info", method="POST", payload=info_data)

    return True
