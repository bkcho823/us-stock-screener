"""
Supabase Cloud Database Client (REST API via PostgREST)
Uses standard `requests` + `SUPABASE_URL` and `SUPABASE_KEY` (from environment variables or Streamlit secrets).
Automatically normalizes SUPABASE_URL even if the user pasted a dashboard URL or '/rest/v1' suffix.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional
import requests


def _normalize_supabase_url(raw_url: str) -> str:
    """
    Ensures any Supabase URL format is converted to the clean base URL:
    `https://<project_ref>.supabase.co`
    Handles cases where the user pasted:
    - `https://<ref>.supabase.co/rest/v1/...`
    - `https://supabase.com/dashboard/project/<ref>...`
    - `<ref>.supabase.co`
    - `<ref>` (just the 20-char project ID)
    """
    u = (raw_url or "").strip().strip('"').strip("'")
    if not u:
        return ""

    # Case 1: User pasted dashboard URL: https://supabase.com/dashboard/project/<ref>...
    m_dash = re.search(r"supabase\.com/dashboard/project/([a-z0-9]+)", u, re.IGNORECASE)
    if m_dash:
        return f"https://{m_dash.group(1)}.supabase.co"

    # Case 2: Standard <ref>.supabase.co anywhere in the string
    m_host = re.search(r"([a-z0-9\-]+)\.supabase\.co", u, re.IGNORECASE)
    if m_host:
        return f"https://{m_host.group(1)}.supabase.co"

    # Case 3: Just a bare 20-character project reference ID
    if re.fullmatch(r"[a-z0-9]{15,30}", u):
        return f"https://{u}.supabase.co"

    # Fallback: keep only scheme + netloc
    if not u.startswith("http"):
        u = "https://" + u
    parsed = urlparse(u)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return u.rstrip("/")


def get_supabase_credentials() -> tuple[str, str]:
    """
    Retrieves SUPABASE_URL and SUPABASE_KEY from:
    1. Environment variables (used by GitHub Actions or local .env)
    2. Streamlit secrets (st.secrets, used by Streamlit Community Cloud)
    """
    raw_url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip().strip('"').strip("'")

    if not raw_url or not key:
        try:
            import streamlit as st
            if "SUPABASE_URL" in st.secrets and not raw_url:
                raw_url = str(st.secrets["SUPABASE_URL"]).strip()
            if "SUPABASE_KEY" in st.secrets and not key:
                key = str(st.secrets["SUPABASE_KEY"]).strip().strip('"').strip("'")
        except Exception:
            pass

    return _normalize_supabase_url(raw_url), key


def is_supabase_configured() -> bool:
    url, key = get_supabase_credentials()
    return bool(url and key)


def _headers(key: str, prefer: str = "") -> Dict[str, str]:
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def sb_upsert_kv(item_key: str, payload: Any) -> bool:
    """Upserts a JSON object into `screener_kv_store` (used for EOD snapshot & S&P 500 benchmark)."""
    url, key = get_supabase_credentials()
    if not url or not key:
        print(f"[Supabase] Skipping upsert for '{item_key}': SUPABASE_URL or SUPABASE_KEY is empty.")
        return False
    endpoint = f"{url}/rest/v1/screener_kv_store?on_conflict=key"
    body = {"key": item_key, "payload": payload}
    resp = requests.post(
        endpoint,
        headers=_headers(key, prefer="resolution=merge-duplicates,return=minimal"),
        json=body,
        timeout=45,
    )
    if not resp.ok:
        raise RuntimeError(
            f"Supabase upsert '{item_key}' to '{endpoint}' failed ({resp.status_code}): {resp.text}"
        )
    print(f"[Supabase] Successfully saved '{item_key}' to screener_kv_store ({url}).")
    return True


def sb_get_kv(item_key: str) -> Optional[Any]:
    """Fetches a JSON payload by key from `screener_kv_store`."""
    url, key = get_supabase_credentials()
    if not url or not key:
        return None
    endpoint = f"{url}/rest/v1/screener_kv_store?key=eq.{item_key}&select=payload"
    resp = requests.get(endpoint, headers=_headers(key), timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    if rows and isinstance(rows, list):
        return rows[0].get("payload")
    return None


def sb_list_presets() -> Dict[str, Dict[str, Any]]:
    """Loads all custom user presets from `screener_presets` table."""
    url, key = get_supabase_credentials()
    if not url or not key:
        return {}
    endpoint = f"{url}/rest/v1/screener_presets?select=name,description,layer0,layer1,saved_at_utc"
    resp = requests.get(endpoint, headers=_headers(key), timeout=15)
    resp.raise_for_status()
    out: Dict[str, Dict[str, Any]] = {}
    for row in resp.json():
        out[row["name"]] = {
            "description": row.get("description", ""),
            "layer0": row.get("layer0", {}),
            "layer1": row.get("layer1", {}),
            "saved_at_utc": row.get("saved_at_utc", ""),
        }
    return out


def sb_upsert_preset(name: str, description: str, layer0: Dict[str, Any], layer1: Dict[str, Any], saved_at_utc: str) -> bool:
    """Saves or updates a custom preset in `screener_presets`."""
    url, key = get_supabase_credentials()
    if not url or not key:
        return False
    endpoint = f"{url}/rest/v1/screener_presets?on_conflict=name"
    body = {
        "name": name,
        "description": description,
        "layer0": layer0,
        "layer1": layer1,
        "saved_at_utc": saved_at_utc,
    }
    resp = requests.post(
        endpoint,
        headers=_headers(key, prefer="resolution=merge-duplicates,return=minimal"),
        json=body,
        timeout=15,
    )
    resp.raise_for_status()
    return True


def sb_delete_preset(name: str) -> bool:
    """Deletes a custom preset from `screener_presets`."""
    url, key = get_supabase_credentials()
    if not url or not key:
        return False
    endpoint = f"{url}/rest/v1/screener_presets?name=eq.{requests.utils.quote(name)}"
    resp = requests.delete(endpoint, headers=_headers(key), timeout=15)
    resp.raise_for_status()
    return True


def sb_insert_run_log(entry: Dict[str, Any]) -> bool:
    """Inserts a screening run log into `screener_run_history`."""
    url, key = get_supabase_credentials()
    if not url or not key:
        return False
    endpoint = f"{url}/rest/v1/screener_run_history?on_conflict=run_id"
    resp = requests.post(
        endpoint,
        headers=_headers(key, prefer="resolution=merge-duplicates,return=minimal"),
        json={"run_id": entry["run_id"], "timestamp_utc": entry["timestamp_utc"], "payload": entry},
        timeout=15,
    )
    resp.raise_for_status()
    return True


def sb_list_run_logs(limit: int = 200) -> List[Dict[str, Any]]:
    """Fetches the most recent screening run logs from `screener_run_history`."""
    url, key = get_supabase_credentials()
    if not url or not key:
        return []
    endpoint = f"{url}/rest/v1/screener_run_history?select=payload&order=timestamp_utc.desc&limit={limit}"
    resp = requests.get(endpoint, headers=_headers(key), timeout=15)
    resp.raise_for_status()
    return [r["payload"] for r in resp.json() if "payload" in r]
