import os
import json
import concurrent.futures
from typing import Dict, Any, List, Optional, Tuple
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "supabase_config.json")

DEFAULT_URL = "https://jttyndtcfrdxdquoloin.supabase.co"
DEFAULT_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp0dHluZHRjZnJkeGRxdW9sb2luIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE5ODM3MTMsImV4cCI6MjEwNzU1OTcxM30."
    "wbOV_d9Y3tGs608fBsMFzUAz3b9mh5OCCRpxhylwSZc"
)


class SupabaseService:
    def __init__(self):
        self.url = ""
        self.anon_key = ""
        self.service_role_key = ""
        # Reuse HTTP session for keep-alive connections (avoids TLS handshake overhead)
        self.session = requests.Session()
        self.load_config()

    def load_config(self):
        # 1. Start from default
        self.url = os.environ.get("SUPABASE_URL", DEFAULT_URL).rstrip("/")
        self.anon_key = os.environ.get("SUPABASE_ANON_KEY", DEFAULT_ANON_KEY)
        self.service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

        # 2. Check local json override
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if cfg.get("url"):
                        self.url = cfg["url"].rstrip("/")
                    if cfg.get("anon_key"):
                        self.anon_key = cfg["anon_key"]
                    if cfg.get("service_role_key"):
                        self.service_role_key = cfg["service_role_key"]
            except Exception as e:
                print(f"[SupabaseService] Gagal membaca {CONFIG_FILE}: {e}")

    def save_config(self, url: str, anon_key: str, service_role_key: str = "") -> bool:
        self.url = url.rstrip("/")
        self.anon_key = anon_key.strip()
        self.service_role_key = service_role_key.strip()

        data = {
            "url": self.url,
            "anon_key": self.anon_key,
            "service_role_key": self.service_role_key
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"[SupabaseService] Gagal menyimpan config: {e}")
            return False

    @property
    def active_key(self) -> str:
        # Prefer service_role_key if available (bypasses RLS for full admin capabilities)
        if self.service_role_key and len(self.service_role_key) > 20:
            return self.service_role_key
        return self.anon_key

    @property
    def is_using_service_role(self) -> bool:
        return bool(self.service_role_key and len(self.service_role_key) > 20)

    def _headers(self, return_rep: bool = True) -> Dict[str, str]:
        key = self.active_key
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        if return_rep:
            headers["Prefer"] = "return=representation"
        return headers

    def test_connection(self) -> Dict[str, Any]:
        results = {
            "connected": False,
            "url": self.url,
            "using_service_role": self.is_using_service_role,
            "tables": {}
        }
        if not self.url or not self.active_key:
            results["error"] = "Supabase URL atau API Key belum diisi."
            return results

        tables_to_check = [
            "literacy_tips",
            "guide_principles",
            "guide_contents",
            "app_info",
            "problem_reports",
            "notifications"
        ]

        def _check_single_table(tbl: str):
            try:
                resp = self.session.get(
                    f"{self.url}/rest/v1/{tbl}?select=*&limit=1",
                    headers=self._headers(),
                    timeout=4
                )
                if resp.status_code in (200, 206):
                    return tbl, {"status": "ok", "accessible": True}
                return tbl, {
                    "status": f"HTTP {resp.status_code}",
                    "accessible": False,
                    "error": resp.text
                }
            except Exception as e:
                return tbl, {"status": "error", "accessible": False, "error": str(e)}

        # Run checks in parallel with ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            future_results = executor.map(_check_single_table, tables_to_check)
            for tbl, res in future_results:
                results["tables"][tbl] = res
                if res["accessible"]:
                    results["connected"] = True

        return results

    # --------------------------------------------------------------------------
    # GENERIC REST CALLS (USING KEEP-ALIVE SESSION)
    # --------------------------------------------------------------------------
    def select(self, table: str, params: Optional[Dict[str, str]] = None) -> Tuple[bool, Any, Optional[str]]:
        try:
            url = f"{self.url}/rest/v1/{table}"
            resp = self.session.get(url, headers=self._headers(), params=params, timeout=8)
            if resp.status_code in (200, 206):
                return True, resp.json(), None
            return False, None, f"HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, None, str(e)

    def insert(self, table: str, payload: Any) -> Tuple[bool, Any, Optional[str]]:
        try:
            url = f"{self.url}/rest/v1/{table}"
            resp = self.session.post(url, headers=self._headers(return_rep=True), json=payload, timeout=8)
            if resp.status_code in (200, 201):
                data = resp.json()
                return True, data, None
            return False, None, f"HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, None, str(e)

    def update(self, table: str, query_params: Dict[str, str], payload: Dict[str, Any]) -> Tuple[bool, Any, Optional[str]]:
        try:
            url = f"{self.url}/rest/v1/{table}"
            resp = self.session.patch(url, headers=self._headers(return_rep=True), params=query_params, json=payload, timeout=8)
            if resp.status_code in (200, 204):
                data = resp.json() if resp.text else []
                return True, data, None
            return False, None, f"HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, None, str(e)

    def delete(self, table: str, query_params: Dict[str, str]) -> Tuple[bool, Any, Optional[str]]:
        try:
            url = f"{self.url}/rest/v1/{table}"
            resp = self.session.delete(url, headers=self._headers(return_rep=True), params=query_params, timeout=8)
            if resp.status_code in (200, 204):
                data = resp.json() if resp.text else []
                return True, data, None
            return False, None, f"HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, None, str(e)

    # --------------------------------------------------------------------------
    # 1. TIPS LITERASI BERANDA (literacy_tips)
    # --------------------------------------------------------------------------
    def get_tips(self) -> List[Dict[str, Any]]:
        ok, data, _ = self.select("literacy_tips", {"select": "*", "order": "order_index.asc,created_at.desc"})
        return data if ok and isinstance(data, list) else []

    def create_tip(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        ok, res, err = self.insert("literacy_tips", data)
        if ok:
            return True, "Tips literasi berhasil ditambahkan."
        return False, err or "Gagal menambahkan tips literasi."

    def update_tip(self, tip_id: str, data: Dict[str, Any]) -> Tuple[bool, str]:
        ok, res, err = self.update("literacy_tips", {"id": f"eq.{tip_id}"}, data)
        if ok:
            return True, "Tips literasi berhasil diperbarui."
        return False, err or "Gagal memperbarui tips literasi."

    def delete_tip(self, tip_id: str) -> Tuple[bool, str]:
        ok, res, err = self.delete("literacy_tips", {"id": f"eq.{tip_id}"})
        if ok:
            return True, "Tips literasi berhasil dihapus."
        return False, err or "Gagal menghapus tips literasi."

    def toggle_tip_status(self, tip_id: str, is_active: bool) -> Tuple[bool, str]:
        ok, res, err = self.update("literacy_tips", {"id": f"eq.{tip_id}"}, {"is_active": is_active})
        if ok:
            status_str = "diaktifkan" if is_active else "dinonaktifkan"
            return True, f"Tips berhasil {status_str}."
        return False, err or "Gagal mengubah status tips."

    # --------------------------------------------------------------------------
    # 2. PANDUAN LITERASI & CHECKLIST (guide_principles & guide_contents)
    # --------------------------------------------------------------------------
    def get_principles(self) -> List[Dict[str, Any]]:
        ok, data, _ = self.select("guide_principles", {"select": "*", "order": "order_index.asc,created_at.asc"})
        return data if ok and isinstance(data, list) else []

    def create_principle(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        ok, res, err = self.insert("guide_principles", data)
        if ok:
            return True, "Langkah prinsip panduan berhasil ditambahkan."
        return False, err or "Gagal menambahkan prinsip panduan."

    def update_principle(self, principle_id: str, data: Dict[str, Any]) -> Tuple[bool, str]:
        ok, res, err = self.update("guide_principles", {"id": f"eq.{principle_id}"}, data)
        if ok:
            return True, "Langkah prinsip panduan berhasil diperbarui."
        return False, err or "Gagal memperbarui prinsip panduan."

    def delete_principle(self, principle_id: str) -> Tuple[bool, str]:
        ok, res, err = self.delete("guide_principles", {"id": f"eq.{principle_id}"})
        if ok:
            return True, "Langkah prinsip panduan berhasil dihapus."
        return False, err or "Gagal menghapus prinsip panduan."

    def get_guide_content(self) -> Optional[Dict[str, Any]]:
        ok, data, _ = self.select("guide_contents", {"select": "*", "limit": "1", "order": "created_at.desc"})
        if ok and isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

    def save_guide_content(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        current = self.get_guide_content()
        if current and current.get("id"):
            ok, res, err = self.update("guide_contents", {"id": f"eq.{current['id']}"}, data)
            if ok:
                return True, "Konten kutipan & checklist berhasil diperbarui."
            return False, err or "Gagal memperbarui konten panduan."
        else:
            ok, res, err = self.insert("guide_contents", data)
            if ok:
                return True, "Konten kutipan & checklist berhasil disimpan."
            return False, err or "Gagal menyimpan konten panduan."

    # --------------------------------------------------------------------------
    # 3. INFORMASI APLIKASI & CARA KERJA (app_info)
    # --------------------------------------------------------------------------
    def get_app_info(self) -> Optional[Dict[str, Any]]:
        ok, data, _ = self.select("app_info", {"select": "*", "limit": "1", "order": "updated_at.desc"})
        if ok and isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

    def save_app_info(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        current = self.get_app_info()
        data["updated_at"] = "now()"
        if current and current.get("id"):
            ok, res, err = self.update("app_info", {"id": f"eq.{current['id']}"}, data)
            if ok:
                return True, "Informasi aplikasi berhasil diperbarui."
            return False, err or "Gagal memperbarui info aplikasi."
        else:
            ok, res, err = self.insert("app_info", data)
            if ok:
                return True, "Informasi aplikasi berhasil disimpan."
            return False, err or "Gagal menyimpan info aplikasi."

    # --------------------------------------------------------------------------
    # 4. LAPORAN MASALAH / BUG (problem_reports)
    # --------------------------------------------------------------------------
    def get_problem_reports(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"select": "*", "order": "created_at.desc"}
        if status and status != "Semua":
            params["status"] = f"eq.{status}"
        ok, data, _ = self.select("problem_reports", params)
        return data if ok and isinstance(data, list) else []

    def update_report_status(self, report_id: str, new_status: str) -> Tuple[bool, str]:
        ok, res, err = self.update("problem_reports", {"id": f"eq.{report_id}"}, {"status": new_status})
        if ok:
            return True, f"Status laporan berhasil diperbarui menjadi '{new_status}'."
        return False, err or "Gagal memperbarui status laporan."

    def delete_report(self, report_id: str) -> Tuple[bool, str]:
        ok, res, err = self.delete("problem_reports", {"id": f"eq.{report_id}"})
        if ok:
            return True, "Laporan masalah berhasil dihapus."
        return False, err or "Gagal menghapus laporan masalah."

    # --------------------------------------------------------------------------
    # 5. BROADCAST NOTIFIKASI SISTEM (notifications)
    # --------------------------------------------------------------------------
    def get_notifications(self, filter_type: str = "all") -> List[Dict[str, Any]]:
        params = {"select": "*", "order": "created_at.desc"}
        if filter_type == "broadcast":
            params["user_id"] = "is.null"
        elif filter_type == "personal":
            params["user_id"] = "not.is.null"
        ok, data, _ = self.select("notifications", params)
        return data if ok and isinstance(data, list) else []

    def create_broadcast_notification(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        payload = {
            "user_id": None,  # NULL indicates Broadcast to all users
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "time_label": data.get("time_label", "Baru saja"),
            "tag_label": data.get("tag_label", "Info"),
            "is_unread": data.get("is_unread", True)
        }
        ok, res, err = self.insert("notifications", payload)
        if ok:
            return True, "Siaran notifikasi global berhasil dikirim ke seluruh pengguna."
        return False, err or "Gagal mengirim siaran notifikasi."

    def update_notification(self, notif_id: str, data: Dict[str, Any]) -> Tuple[bool, str]:
        ok, res, err = self.update("notifications", {"id": f"eq.{notif_id}"}, data)
        if ok:
            return True, "Notifikasi berhasil diperbarui."
        return False, err or "Gagal memperbarui notifikasi."

    def delete_notification(self, notif_id: str) -> Tuple[bool, str]:
        ok, res, err = self.delete("notifications", {"id": f"eq.{notif_id}"})
        if ok:
            return True, "Notifikasi berhasil dihapus."
        return False, err or "Gagal menghapus notifikasi."


supabase_service = SupabaseService()
