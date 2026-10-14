"""Minimal HubSpot REST client: search (with 10k-cap splitting), batch read, associations."""
import os
import re
import time
from datetime import datetime, timezone

import requests

BASE = "https://api.hubapi.com"
SEARCH_CAP = 10_000


class HubSpot:
    def __init__(self, token=None):
        self.token = token or os.environ["HUBSPOT_TOKEN"]
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        self._last_search = 0.0

    def _req(self, method, path, **kw):
        for attempt in range(6):
            r = self.s.request(method, BASE + path, timeout=60, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("Retry-After", 2 ** attempt))
                time.sleep(min(wait, 30))
                continue
            if r.status_code >= 400:
                raise requests.HTTPError(f"{r.status_code} from HubSpot on {method} {path}: {r.text[:800]}", response=r)
            return r.json() if r.content else {}
        raise requests.HTTPError(f"{r.status_code} from HubSpot on {method} {path} after retries: {r.text[:800]}", response=r)

    # ---- search -------------------------------------------------------
    def _search_page(self, obj, body):
        gap = time.time() - self._last_search
        if gap < 0.25:  # search endpoints allow ~5 requests/second
            time.sleep(0.25 - gap)
        self._last_search = time.time()
        return self._req("POST", f"/crm/v3/objects/{obj}/search", json=body)

    def search(self, obj, filters, properties, date_prop, start_ms, end_ms):
        """All records matching filters with date_prop in [start_ms, end_ms).

        The search API stops at 10,000 results per query, so windows that
        exceed the cap are split in half until each fits.
        """
        windows = [(start_ms, end_ms)]
        out = {}
        while windows:
            a, b = windows.pop()
            fs = list(filters) + [
                {"propertyName": date_prop, "operator": "GTE", "value": str(a)},
                {"propertyName": date_prop, "operator": "LT", "value": str(b)},
            ]
            body = {"filterGroups": [{"filters": fs}], "properties": properties, "limit": 200,
                    "sorts": [{"propertyName": date_prop, "direction": "ASCENDING"}]}
            first = self._search_page(obj, body)
            if first.get("total", 0) >= SEARCH_CAP and b - a > 60_000:
                mid = (a + b) // 2
                windows += [(a, mid), (mid, b)]
                continue
            page = first
            while True:
                for r in page.get("results", []):
                    out[r["id"]] = r
                after = page.get("paging", {}).get("next", {}).get("after")
                if not after:
                    break
                body["after"] = after
                page = self._search_page(obj, body)
        return list(out.values())

    def search_simple(self, obj, filters, properties):
        body = {"filterGroups": [{"filters": filters}], "properties": properties, "limit": 200}
        out = []
        page = self._search_page(obj, body)
        while True:
            out += page.get("results", [])
            after = page.get("paging", {}).get("next", {}).get("after")
            if not after or len(out) >= SEARCH_CAP:
                break
            body["after"] = after
            page = self._search_page(obj, body)
        return out

    # ---- batch read ----------------------------------------------------
    def batch_read(self, obj, ids, properties, history=None):
        out = []
        ids = list(dict.fromkeys(ids))
        size = 50 if history else 100  # HubSpot caps batch reads with property history at 50 records
        for i in range(0, len(ids), size):
            body = {"inputs": [{"id": x} for x in ids[i:i + size]], "properties": properties}
            if history:
                body["propertiesWithHistory"] = history
            out += self._req("POST", f"/crm/v3/objects/{obj}/batch/read", json=body).get("results", [])
        return out

    # ---- associations --------------------------------------------------
    def associations(self, from_obj, to_obj, ids):
        """{from_id: [to_id, ...]}"""
        res = {}
        ids = list(dict.fromkeys(ids))
        for i in range(0, len(ids), 500):
            body = {"inputs": [{"id": x} for x in ids[i:i + 500]]}
            data = self._req("POST", f"/crm/v4/associations/{from_obj}/{to_obj}/batch/read", json=body)
            for r in data.get("results", []):
                res[str(r["from"]["id"])] = [str(t["toObjectId"]) for t in r.get("to", [])]
        return res

    # ---- misc ----------------------------------------------------------
    def owners(self):
        out, after = {}, None
        while True:
            params = {"limit": 500, "archived": "false"}
            if after:
                params["after"] = after
            data = self._req("GET", "/crm/v3/owners", params=params)
            for o in data.get("results", []):
                name = f"{o.get('firstName') or ''} {o.get('lastName') or ''}".strip() or o.get("email", "")
                out[str(o["id"])] = name
            after = data.get("paging", {}).get("next", {}).get("after")
            if not after:
                return out

    def deal_stages(self):
        """{stage_id: {"stage": label, "pipeline": pipeline label}}"""
        try:
            out = {}
            for pl in self._req("GET", "/crm/v3/pipelines/deals").get("results", []):
                for st in pl.get("stages", []):
                    out[st["id"]] = {"stage": st["label"], "pipeline": pl["label"]}
            return out
        except Exception:
            return {}

    def property_labels(self, obj, name):
        """{internal value: label} for an enumeration property; {} if unavailable."""
        try:
            data = self._req("GET", f"/crm/v3/properties/{obj}/{name}")
            return {o["value"]: o["label"] for o in data.get("options", [])}
        except Exception:
            return {}

    def call_dispositions(self):
        """{disposition_id: label}. Empty dict if the endpoint is unavailable."""
        try:
            data = self._req("GET", "/calling/v1/dispositions")
            return {d["id"]: d["label"] for d in data}
        except Exception:
            return {}


def to_ms(dt):
    return int(dt.timestamp() * 1000)


def parse_ts(v):
    """HubSpot datetime/date string or epoch-ms string -> aware UTC datetime.

    Works on Python 3.9+, whose fromisoformat() only accepts 3 or 6 fractional digits.
    """
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or str(v).isdigit():
        return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc)
    s = str(v).strip().replace("Z", "+00:00")
    if len(s) == 10:
        s += "T00:00:00+00:00"
    m = re.match(r"^(.*T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(.*)$", s)
    if m:
        frac = (m.group(2) or "")[:6].ljust(6, "0") if m.group(2) else ""
        s = m.group(1) + ("." + frac if frac else "") + (m.group(3) or "")
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
