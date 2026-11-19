import os
import json
import uuid
import urllib.request
import urllib.error
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "cms_data.json")
CONFIG_FILE = os.path.join(BASE_DIR, "supabase_config.json")

DEFAULT_URL = "https://jttyndtcfrdxdquoloin.supabase.co"
DEFAULT_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp0dHluZHRjZnJkeGRxdW9sb2luIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE5ODM3MTMsImV4cCI6MjEwNzU1OTcxM30."
    "wbOV_d9Y3tGs608fBsMFzUAz3b9mh5OCCRpxhylwSZc"
)


def get_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "supabase_url": DEFAULT_URL,
        "supabase_anon_key": DEFAULT_ANON_KEY,
        "supabase_service_role_key": ""
    }


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[Config Save Error] {e}")


def _get_active_key():
    cfg = get_config()
    service_key = (cfg.get("supabase_service_role_key") or "").strip()
    if service_key:
        return service_key, True
    return (cfg.get("supabase_anon_key") or DEFAULT_ANON_KEY).strip(), False


def _get_headers():
    key, is_service = _get_active_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
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
    cfg = get_config()
    url = f"{cfg.get('supabase_url', DEFAULT_URL)}/rest/v1/{endpoint}"
    headers = _get_headers()
    data = json.dumps(payload).encode("utf-8") if payload is not None else None

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            res_body = res.read().decode("utf-8")
            if res_body:
                return json.loads(res_body), None
            return [], None
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_msg)
            msg = err_json.get("message") or err_msg
        except Exception:
            msg = err_msg
        print(f"[Supabase API Error on {method} {endpoint}] HTTP {e.code}: {msg}")
        return None, f"HTTP {e.code}: {msg}"
    except Exception as e:
        print(f"[Supabase API Error on {method} {endpoint}] {e}")
        return None, str(e)


def check_supabase_sync_status():
    """Memeriksa apakah Supabase dapat menerima write/insert atau terblokir RLS."""
    cfg = get_config()
    _, is_service = _get_active_key()
    if is_service:
        return {"status": "connected", "type": "service_role", "message": "Service Role aktif (Bypass RLS - Akses Penuh)"}

    # Coba test ping read
    res, err = _call_supabase("literacy_tips?select=id&limit=1")
    if err:
        return {"status": "error", "type": "anon", "message": f"Koneksi gagal: {err}"}

    # Coba test write dengan POST payload kosong (non-destructive):
    # Jika RLS memblokir anon, Supabase mengembalikan HTTP 401 "violates row-level security policy".
    # Jika RLS mengizinkan atau dinonaktifkan, Supabase mengembalikan HTTP 400 (schema validation / not-null).
    test_res, test_err = _call_supabase("literacy_tips", method="POST", payload={})
    if test_err and ("violates row-level security" in test_err or "401" in test_err):
        return {
            "status": "rls_blocked",
            "type": "anon",
            "message": "Row Level Security (RLS) Supabase membatasi write untuk Anon Key."
        }

    return {"status": "connected", "type": "anon", "message": "Supabase terhubung (Write diizinkan)"}


# ---------------------------------------------------------------------------
# 1. TIPS LITERASI (literacy_tips)
# ---------------------------------------------------------------------------

def get_literacy_tips():
    local = _load_local_data()
    local_tips = local.get("literacy_tips", [])
    remote, err = _call_supabase("literacy_tips?select=*&order=order_index.asc")

    if remote is not None and isinstance(remote, list):
        remote_ids = {t.get("id") for t in remote}
        # Pertahankan data lokal yang mungkin belum sempat tersinkron ke Supabase karena RLS
        merged = list(remote)
        for lt in local_tips:
            if lt.get("id") and lt.get("id") not in remote_ids:
                lt["sync_pending"] = True
                merged.append(lt)

        local["literacy_tips"] = merged
        _save_local_data(local)
        return sorted(merged, key=lambda x: x.get("order_index", 0))

    return sorted(local_tips, key=lambda x: x.get("order_index", 0))


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
        res, err = _call_supabase(f"literacy_tips?id=eq.{tip_id}", method="PATCH", payload=tip_data)
        return res is not None, err
    else:
        # INSERT
        new_id = str(uuid.uuid4())
        tip_data["id"] = new_id
        tip_data["created_at"] = datetime.utcnow().isoformat()
        tips.append(tip_data)
        _save_local_data(local)
        res, err = _call_supabase("literacy_tips", method="POST", payload=tip_data)
        return res is not None, err


def delete_tip(tip_id):
    local = _load_local_data()
    tips = local.get("literacy_tips", [])
    local["literacy_tips"] = [t for t in tips if t.get("id") != tip_id]
    _save_local_data(local)
    res, err = _call_supabase(f"literacy_tips?id=eq.{tip_id}", method="DELETE")
    return res is not None, err


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
    res, err = _call_supabase(f"literacy_tips?id=eq.{tip_id}", method="PATCH", payload={"is_active": new_status})
    return new_status, err


# ---------------------------------------------------------------------------
# 2. PANDUAN LITERASI (guide_principles & guide_contents)
# ---------------------------------------------------------------------------

def get_guide_data():
    local = _load_local_data()
    local_principles = local.get("guide_principles", [])
    remote_principles, _ = _call_supabase("guide_principles?select=*&order=order_index.asc")
    remote_contents, _ = _call_supabase("guide_contents?select=*&limit=1")

    if remote_principles is not None and isinstance(remote_principles, list):
        remote_ids = {p.get("id") for p in remote_principles}
        merged = list(remote_principles)
        for lp in local_principles:
            if lp.get("id") and lp.get("id") not in remote_ids:
                lp["sync_pending"] = True
                merged.append(lp)
        local["guide_principles"] = merged

    if remote_contents is not None and isinstance(remote_contents, list) and len(remote_contents) > 0:
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
            res, err = _call_supabase(f"guide_contents?id=eq.{content_id}", method="PATCH", payload=payload)
            return res is not None, err
    else:
        new_id = str(uuid.uuid4())
        payload["id"] = new_id
        payload["created_at"] = datetime.utcnow().isoformat()
        local["guide_contents"] = [payload]
        _save_local_data(local)
        res, err = _call_supabase("guide_contents", method="POST", payload=payload)
        return res is not None, err

    return True, None


def save_guide_principle(principle_data, principle_id=None):
    local = _load_local_data()
    principles = local.get("guide_principles", [])

    if principle_id:
        for p in principles:
            if p.get("id") == principle_id:
                p.update(principle_data)
                break
        _save_local_data(local)
        res, err = _call_supabase(f"guide_principles?id=eq.{principle_id}", method="PATCH", payload=principle_data)
        return res is not None, err
    else:
        new_id = str(uuid.uuid4())
        principle_data["id"] = new_id
        principle_data["created_at"] = datetime.utcnow().isoformat()
        principles.append(principle_data)
        _save_local_data(local)
        res, err = _call_supabase("guide_principles", method="POST", payload=principle_data)
        return res is not None, err


def delete_guide_principle(principle_id):
    local = _load_local_data()
    principles = local.get("guide_principles", [])
    local["guide_principles"] = [p for p in principles if p.get("id") != principle_id]
    _save_local_data(local)
    res, err = _call_supabase(f"guide_principles?id=eq.{principle_id}", method="DELETE")
    return res is not None, err


# ---------------------------------------------------------------------------
# 3. TENTANG HOAXCHECK (app_info)
# ---------------------------------------------------------------------------

def get_app_info():
    local = _load_local_data()
    remote, _ = _call_supabase("app_info?select=*&limit=1")
    if remote is not None and isinstance(remote, list) and len(remote) > 0:
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
            res, err = _call_supabase(f"app_info?id=eq.{app_id}", method="PATCH", payload=info_data)
            return res is not None, err
    else:
        new_id = str(uuid.uuid4())
        info_data["id"] = new_id
        local["app_info"] = [info_data]
        _save_local_data(local)
        res, err = _call_supabase("app_info", method="POST", payload=info_data)
        return res is not None, err

    return True, None


def sync_all_to_supabase():
    """Mencoba menyinkronkan seluruh item lokal ke Supabase."""
    local = _load_local_data()
    synced_count = 0
    errors = []

    # 1. Sync Literacy Tips
    remote_tips, _ = _call_supabase("literacy_tips?select=id")
    remote_tip_ids = {t["id"] for t in remote_tips} if remote_tips and isinstance(remote_tips, list) else set()
    for tip in local.get("literacy_tips", []):
        t_id = tip.get("id")
        clean_tip = {k: v for k, v in tip.items() if k != "sync_pending"}
        if t_id in remote_tip_ids:
            res, err = _call_supabase(f"literacy_tips?id=eq.{t_id}", method="PATCH", payload=clean_tip)
        else:
            res, err = _call_supabase("literacy_tips", method="POST", payload=clean_tip)
        if err:
            errors.append(f"Tips '{tip.get('title', '')}': {err}")
        else:
            tip["sync_pending"] = False
            synced_count += 1

    # 2. Sync Guide Principles
    remote_p, _ = _call_supabase("guide_principles?select=id")
    remote_p_ids = {p["id"] for p in remote_p} if remote_p and isinstance(remote_p, list) else set()
    for p in local.get("guide_principles", []):
        p_id = p.get("id")
        clean_p = {k: v for k, v in p.items() if k != "sync_pending"}
        if p_id in remote_p_ids:
            res, err = _call_supabase(f"guide_principles?id=eq.{p_id}", method="PATCH", payload=clean_p)
        else:
            res, err = _call_supabase("guide_principles", method="POST", payload=clean_p)
        if err:
            errors.append(f"Prinsip '{p.get('title', '')}': {err}")
        else:
            p["sync_pending"] = False
            synced_count += 1

    # 3. Sync Guide Content
    for c in local.get("guide_contents", []):
        c_id = c.get("id")
        if c_id:
            res, err = _call_supabase(f"guide_contents?id=eq.{c_id}", method="PATCH", payload=c)
            if not err:
                synced_count += 1

    # 4. Sync App Info
    for a in local.get("app_info", []):
        a_id = a.get("id")
        if a_id:
            res, err = _call_supabase(f"app_info?id=eq.{a_id}", method="PATCH", payload=a)
            if not err:
                synced_count += 1

    _save_local_data(local)
    return {
        "success": len(errors) == 0,
        "synced_count": synced_count,
        "errors": errors
    }
