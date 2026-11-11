"""Turn the raw HubSpot dataset into per-contact rows and hygiene-check lists for the page."""
import re
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, time

from . import config as C
from .bizhours import TZ, business_hours_between, ist_date
from .hubspot import parse_ts

EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+\.)+[\w-]+")


def _week(dt):
    d = ist_date(dt)
    return (d - timedelta(days=d.weekday())).isoformat()


def _name(c):
    n = f"{c.get('firstname') or ''} {c.get('lastname') or ''}".strip()
    return n or c.get("email") or f"Contact {c['id']}"


def _url(obj, rid):
    return f"https://app.hubspot.com/contacts/{C.PORTAL_ID}/record/{obj}/{rid}"


def _r(x, n=1):
    return None if x is None else round(x, n)


def _all_internal(to_field):
    addrs = [m.group(0).lower() for m in EMAIL_RE.finditer(to_field or "")]
    return bool(addrs) and all(a.split("@")[1] in C.INTERNAL_EMAIL_DOMAINS for a in addrs)


def _segs(c):
    chn = (c.get(C.CHANNEL_PROPERTY) or "").strip() or C.BLANK_LABEL
    src = (c.get(C.SOURCE_PROPERTY) or "").strip()
    src = C.SOURCE_LABELS.get(src, src) or C.BLANK_LABEL
    return chn, src


def compute(raw):
    reg_labels = (raw.get("region_labels") or {}).get("contact", {})
    deal_reg_labels = (raw.get("region_labels") or {}).get("deal", {})
    company_names = raw.get("company_names", {})
    reason_labels = raw.get("reason_labels", {})

    def company_of(c):
        return (c.get("company") or "").strip() or company_names.get(str(c.get("associatedcompanyid") or ""), "")

    def reason_of(c, status_value):
        if status_value == "a4":
            v = c.get(C.DISQ_REASON_PROPERTY) or ""
            return (reason_labels.get("disq") or C.DISQ_REASON_LABELS).get(v, v)
        if status_value == "a8":
            v = c.get(C.NI_REASON_PROPERTY) or ""
            return ", ".join(reason_labels.get("ni", {}).get(x, x) for x in v.split(";") if x)
        return ""

    now = parse_ts(raw["now"])
    start = parse_ts(raw["start"])
    bdr = C.BDR_OWNERS
    dispo = raw.get("dispositions", {})
    owners = raw.get("owners", {})

    def owner_name(oid):
        return bdr.get(str(oid), {}).get("name") or owners.get(str(oid)) or f"Owner {oid}"

    contacts = {c["id"]: c for c in raw["contacts"] if str(c.get("hubspot_owner_id")) in bdr}
    for c in contacts.values():
        c["_assigned"] = parse_ts(c.get("hubspot_owner_assigneddate"))
        c["_touches"], c["_incoming"], c["_meetings"], c["_dispos"] = [], [], [], []
        c["_chn"], c["_src"] = _segs(c)
        rv = (c.get(C.REGION_PROPERTY) or "").strip()
        c["_reg"] = reg_labels.get(rv, rv) or C.BLANK_LABEL

    def act_reg(row):
        for cid in row.get("contact_ids", []):
            if cid in contacts:
                return contacts[cid]["_reg"]
        return C.BLANK_LABEL

    def act_segs(row):
        """Channel/source of the first associated contact we know about."""
        for cid in row.get("contact_ids", []):
            if cid in contacts:
                return [contacts[cid]["_chn"], contacts[cid]["_src"]]
        return [C.BLANK_LABEL, C.BLANK_LABEL]

    # ---------------- calls ----------------
    call_rows, dq = [], defaultdict(lambda: defaultdict(int))
    pre_assignment = []
    per_contact_calls = defaultdict(list)
    for call in raw["calls"]:
        owner = str(call.get("hubspot_owner_id") or "")
        if owner not in bdr or (call.get("hs_call_direction") or "").upper() == "INBOUND":
            continue
        ts = parse_ts(call.get("hs_timestamp"))
        if ts is None:
            continue
        created = parse_ts(call.get("hs_createdate")) or ts
        status = (call.get("hs_call_status") or "").upper()
        label = dispo.get(call.get("hs_call_disposition") or "", call.get("hs_call_disposition") or "")
        manual = (call.get("hs_object_source_label") or "") != "INTEGRATION"
        dur = int(float(call.get("hs_call_duration") or 0))
        has_notes = bool(call.get("has_notes", False))
        by_talk = dur > C.TALK_MIN_SEC * 1000
        by_notes = C.CONNECTED_MANUAL_WITH_NOTES and manual and has_notes and not by_talk
        connected = by_talk or by_notes  # >30s talk time, or a manual log with notes
        call["_ts"], call["_manual"], call["_label"], call["_dup"] = ts, manual, label, False
        call["_backdated"] = (created - ts).total_seconds() / 3600 > C.BACKDATE_HOURS
        call["_valid"] = status not in C.CALL_EXCLUDED_STATUSES
        for cid in call.get("contact_ids", []):
            per_contact_calls[(cid, owner)].append(call)
        call_rows.append(call)
        call["_row"] = [owner, _week(ts), ts.astimezone(TZ).hour, int(connected),
                        int(connected and dur >= C.CONVERSATION_MIN_MS), int(bool(label)),
                        int(call.get("has_notes", False)), int(manual), int(call["_backdated"]), 0,
                        int(call["_valid"]), ts.astimezone(TZ).weekday()] + act_segs(call) + [
                        round(dur / 1000), (call.get("contact_ids") or [""])[0], ist_date(ts).isoformat(),
                        int(call.get("hs_call_duration") not in (None, "")), 1 if by_talk else 2 if by_notes else 0, act_reg(call)]

    # duplicate = manual log within N minutes of a tool-logged call to the same contact by the same owner
    win = timedelta(minutes=C.DUPLICATE_CALL_MINUTES)
    for (cid, owner), cl in per_contact_calls.items():
        tool = [x["_ts"] for x in cl if not x["_manual"]]
        for x in cl:
            if x["_manual"] and any(abs(x["_ts"] - t) <= win for t in tool):
                x["_dup"] = True
                x["_row"][9] = 1

    for call in call_rows:
        if not call["_valid"] or call["_dup"]:
            continue
        for cid in call.get("contact_ids", []):
            c = contacts.get(cid)
            if not c or str(c.get("hubspot_owner_id")) != str(call["hubspot_owner_id"]) or not c["_assigned"]:
                continue
            if call["_ts"] < c["_assigned"]:
                pre_assignment.append((c, call["_ts"], "Call"))
                continue
            c["_touches"].append({"ts": call["_ts"], "ch": "call", "label": call["_label"],
                                  "dur": int(float(call.get("hs_call_duration") or 0))})

    # ---------------- emails ----------------
    email_rows = []
    for em in raw["emails"]:
        owner = str(em.get("hubspot_owner_id") or "")
        ts = parse_ts(em.get("hs_timestamp"))
        if ts is None:
            continue
        direction = (em.get("hs_email_direction") or "").upper()
        if direction == "INCOMING_EMAIL":
            for cid in em.get("contact_ids", []):
                if cid in contacts:
                    contacts[cid]["_incoming"].append(ts)
            continue
        if direction != "EMAIL" or owner not in bdr:
            continue
        status = (em.get("hs_email_status") or "").upper()
        internal = _all_internal(em.get("hs_email_to_email"))
        group = len(em.get("contact_ids", [])) > C.GROUP_EMAIL_MAX_CONTACTS
        lt = ts.astimezone(TZ)
        email_rows.append([owner, _week(ts), int(status == "BOUNCED"), int(group), int(internal), lt.hour, lt.weekday()] + act_segs(em) + [lt.date().isoformat(), act_reg(em)])
        if status in C.EMAIL_EXCLUDED_STATUSES or internal:
            continue
        for cid in em.get("contact_ids", []):
            c = contacts.get(cid)
            if not c or str(c.get("hubspot_owner_id")) != owner or not c["_assigned"]:
                continue
            if ts < c["_assigned"]:
                pre_assignment.append((c, ts, "Email"))
                continue
            c["_touches"].append({"ts": ts, "ch": "email", "bounced": status == "BOUNCED"})

    # ---------------- meetings ----------------
    for m in raw["meetings"]:
        booked = parse_ts(m.get("hs_createdate")) or parse_ts(m.get("hs_timestamp"))
        for cid in m.get("contact_ids", []):
            c = contacts.get(cid)
            if c and c["_assigned"] and booked and booked >= c["_assigned"]:
                c["_meetings"].append(booked)

    # ---------------- per-contact rows ----------------
    rows = []
    for c in contacts.values():
        a = c["_assigned"]
        if not a or a < start:
            continue
        t = sorted(c["_touches"], key=lambda x: x["ts"])
        first = t[0] if t else None
        last = t[-1]["ts"] if t else None
        ft_bh = business_hours_between(a, first["ts"]) if first else None
        days = {ist_date(x["ts"]) for x in t}
        calls = [x for x in t if x["ch"] == "call"]
        mails = [x for x in t if x["ch"] == "email"]
        gaps = [business_hours_between(t[i - 1]["ts"], t[i]["ts"]) for i in range(1, len(t))]
        bh_since = [business_hours_between(a, x["ts"]) for x in t]
        first_mail = mails[0]["ts"] if mails else None
        meet = min(c["_meetings"]) if c["_meetings"] else None
        mql = c.get("mql_status") or ""
        missing = [m for m, ok in (("email", c.get("email")), ("phone", c.get("phone") or c.get("mobilephone"))) if not ok]
        idle_bd = business_hours_between(last, now) / C.BH_PER_DAY if last else None
        rows.append({
            "id": c["id"], "name": _name(c), "url": _url("0-1", c["id"]),
            "owner": str(c["hubspot_owner_id"]), "assigned": a.isoformat(), "week": _week(a),
            "chn": c["_chn"], "src": c["_src"], "reg": c["_reg"], "aday": ist_date(a).isoformat(), "company": company_of(c),
            "mql": C.MQL_LABELS.get(mql, mql or "(blank)"),
            "ft": first["ts"].isoformat() if first else None, "ft_ch": first["ch"] if first else None,
            "ft_bh": _r(ft_bh, 2), "ft_raw_h": _r((first["ts"] - a).total_seconds() / 3600, 1) if first else None,
            "age_bh": _r(business_hours_between(a, now), 1),
            "t": len(t), "t10": sum(1 for h in bh_since if h <= C.PERSISTENCE_WINDOWS_BD[0] * C.BH_PER_DAY),
            "t20": sum(1 for h in bh_since if h <= C.PERSISTENCE_WINDOWS_BD[1] * C.BH_PER_DAY),
            "days": len(days), "calls": len(calls), "emails": len(mails),
            "gap_bh": _r(statistics.median(gaps), 1) if gaps else None,
            "last": last.isoformat() if last else None, "idle_bd": _r(idle_bd, 1),
            "replied": bool(first_mail and any(x > first_mail for x in c["_incoming"])),
            "bounced": any(x.get("bounced") for x in mails),
            "meeting": bool(meet), "ttm_bd": _r(business_hours_between(a, meet) / C.BH_PER_DAY, 1) if meet else None,
            "t_before_meet": sum(1 for x in t if meet and x["ts"] < meet) if meet else None,
            "unworkable": ", ".join("no " + m for m in missing),
            "status_lag": bool(t) and mql == C.MQL_UNTOUCHED,
            "abandoned": 1 <= len(t) <= 2 and idle_bd is not None and idle_bd >= C.ABANDONED_IDLE_BD
                         and mql not in C.MQL_CLOSED_ALL,
        })
        c["_row"] = rows[-1]

    # ---------------- MQL status hygiene checks ----------------
    checks = {"working_idle": [], "meeting_no_deal": [], "demo_overdue": [], "closed_low_touch": [],
              "outcome_mismatch": [], "pre_assignment": []}
    closed_all = []  # every Disqualified / Not Interested / No Response contact, adequate or not

    for c in contacts.values():
        mql = c.get("mql_status") or ""
        a = c["_assigned"]
        t = sorted(c["_touches"], key=lambda x: x["ts"])
        last = t[-1]["ts"] if t else None
        status_at = parse_ts(c.get("mql_status_update_date"))
        base = {"id": c["id"], "name": _name(c), "url": _url("0-1", c["id"]), "owner": str(c["hubspot_owner_id"]),
                "chn": c["_chn"], "src": c["_src"], "reg": c["_reg"], "aday": ist_date(a).isoformat() if a else None,
                "company": company_of(c)}

        if mql == C.MQL_WORKING:
            clock = max([x for x in (last, status_at, a) if x] or [now])
            idle = business_hours_between(clock, now) / C.BH_PER_DAY
            if idle >= C.WORKING_IDLE_BD:
                checks["working_idle"].append({**base, "last": last.isoformat() if last else None,
                                               "status_at": status_at.isoformat() if status_at else None,
                                               "idle_bd": _r(idle)})

        if mql == C.MQL_MEETING_SCHEDULED:
            since = status_at or a
            if since and business_hours_between(since, now) >= C.MEETING_NO_DEAL_GRACE_BD * C.BH_PER_DAY:
                dids = set(raw["contact_deals"].get(c["id"], []))
                comp = c.get("associatedcompanyid")
                if comp:
                    dids |= set(raw["company_deals"].get(str(comp), []))
                open_deals = [d for d in dids if str(raw["deals"].get(d, {}).get("hs_is_closed", "")).lower() != "true"]
                if not open_deals:
                    checks["meeting_no_deal"].append({**base, "status_at": since.isoformat(),
                                                      "deals_total": len(dids),
                                                      "age_bd": _r(business_hours_between(since, now) / C.BH_PER_DAY)})

        if mql in C.MQL_CLOSED_CHECKED and a and a >= start:
            hist = c.get("mql_history") or []
            changed = next((parse_ts(h["timestamp"]) for h in hist if h.get("value") == mql), None) or status_at
            if changed and changed >= a:
                before = [x for x in t if x["ts"] <= changed]
                n_days = len({ist_date(x["ts"]) for x in before})
                n_calls = sum(1 for x in before if x["ch"] == "call")
                adequate = not (len(before) < C.ADEQUATE_MIN_TOUCHES or n_days < C.ADEQUATE_MIN_DAYS or n_calls < C.ADEQUATE_MIN_CALLS)
                closed_all.append({**base, "status": C.MQL_CLOSED_CHECKED[mql], "changed": changed.isoformat(),
                                   "day": ist_date(changed).isoformat(), "touches": len(before), "days": n_days,
                                   "calls": n_calls, "emails": len(before) - n_calls, "adequate": adequate,
                                   "reason": reason_of(c, mql),
                                   "bd": _r(business_hours_between(a, changed) / C.BH_PER_DAY)})
                if not adequate:
                    checks["closed_low_touch"].append({**base, "status": C.MQL_CLOSED_CHECKED[mql],
                                                       "changed": changed.isoformat(), "touches": len(before),
                                                       "days": n_days, "calls": n_calls})

        for x in t:
            if x["ch"] == "call" and any(k in (x.get("label") or "").lower() for k in C.MEETING_OUTCOME_KEYWORDS) \
                    and not c["_meetings"]:
                checks["outcome_mismatch"].append({**base, "call": x["ts"].isoformat(), "outcome": x["label"]})
                break

    for c, ts, ch in pre_assignment:
        checks["pre_assignment"].append({"id": c["id"], "name": _name(c), "url": _url("0-1", c["id"]),
                                         "chn": c["_chn"], "src": c["_src"], "reg": c["_reg"], "aday": ist_date(c["_assigned"]).isoformat(),
                                         "company": company_of(c),
                                         "owner": str(c["hubspot_owner_id"]), "activity": ts.isoformat(),
                                         "channel": ch, "assigned": c["_assigned"].isoformat()})

    for d in raw["demo_deals"]:
        dd = parse_ts(d.get(C.DEMO_DATE_PROPERTY))
        if not dd:
            continue
        demo_day_end = datetime.combine(dd.date() + timedelta(days=1), time(0, 0), TZ)
        over_h = (now - demo_day_end).total_seconds() / 3600
        if over_h >= C.DEMO_OVERDUE_HOURS:
            oid = str(d.get("hubspot_owner_id") or "")
            checks["demo_overdue"].append({"id": d["id"], "name": d.get("dealname") or f"Deal {d['id']}",
                                           "url": _url("0-3", d["id"]), "owner": oid,
                                           "owner_name": owner_name(oid), "demo_date": dd.date().isoformat(),
                                           "overdue_h": round(over_h)})

    # ---------------- deals tab ----------------
    stages = raw.get("deal_stages", {})
    deal_rows = []
    for d in raw.get("demo_window_deals", []):
        dd = parse_ts(d.get(C.DEMO_DATE_PROPERTY))
        done_ts = parse_ts(d.get(C.DEMO_DONE_DATE_PROPERTY))
        sqo_ts = parse_ts(d.get(C.SQO_DATE_PROPERTY))
        if not dd and not done_ts and not sqo_ts:
            continue
        demo_day = dd.date() if dd else None  # HubSpot date properties are midnight UTC of the chosen day
        status = d.get("demo_status") or ""
        if demo_day:
            due = datetime.combine(demo_day + timedelta(days=1), time(0, 0), TZ) + timedelta(hours=C.DEMO_OVERDUE_HOURS)
            past = now >= due
        else:
            due, past = None, False
        done = bool(done_ts) or status in C.DEMO_DONE_STATUSES
        done_day = (done_ts.date() if done_ts else demo_day) if done else None
        orig = (d.get(C.DEAL_ORIGINATION_PROPERTY) or "").strip()
        try:
            value = float(d.get(C.AMOUNT_PROPERTY)) if d.get(C.AMOUNT_PROPERTY) not in (None, "") else None
        except ValueError:
            value = None
        oid = str(d.get("hubspot_owner_id") or "")
        st = stages.get(d.get("dealstage") or "", {})
        try:
            amount = float(d.get("amount")) if d.get("amount") not in (None, "") else None
        except ValueError:
            amount = None
        deal_rows.append({
            "id": d["id"], "name": d.get("dealname") or f"Deal {d['id']}", "url": _url("0-3", d["id"]),
            "owner": oid, "owner_name": owner_name(oid) if oid else "(no owner)",
            "demo_date": demo_day.isoformat() if demo_day else None, "status": status or C.BLANK_LABEL,
            "chn": (d.get(C.DEAL_CHANNEL_PROPERTY) or "").strip() or C.BLANK_LABEL,
            "reg": deal_reg_labels.get((d.get(C.DEAL_REGION_PROPERTY) or "").strip(), (d.get(C.DEAL_REGION_PROPERTY) or "").strip()) or C.BLANK_LABEL,
            "spoc": owner_name(str(d.get(C.DEAL_SPOC_PROPERTY))) if d.get(C.DEAL_SPOC_PROPERTY) else C.BLANK_LABEL,
            "orig": C.ORIGINATION_LABELS.get(orig, orig) or C.BLANK_LABEL,
            "done": done, "done_date": done_day.isoformat() if done_day else None,
            "sqo": status in C.SQO_STATUSES, "value": value,
            "sqo_date": ((sqo_ts.date() if sqo_ts else done_day).isoformat() if (sqo_ts or done_day) else None)
                        if status in C.SQO_STATUSES else None,
            "sqo_date_fallback": status in C.SQO_STATUSES and not sqo_ts,
            "stage": st.get("stage") or d.get("dealstage") or "", "pipeline": st.get("pipeline") or d.get("pipeline") or "",
            "closed": str(d.get("hs_is_closed", "")).lower() == "true", "amount": amount,
            "past": past, "overdue": past and status == C.DEMO_STATUS_SCHEDULED,
            "overdue_h": round((now - due).total_seconds() / 3600 + C.DEMO_OVERDUE_HOURS) if past else None,
        })

    return {
        "closed": closed_all,
        "deals": deal_rows, "demo_overdue_hours": C.DEMO_OVERDUE_HOURS, "currency": C.CURRENCY,
        "generated_at": now.isoformat(), "window_start": start.isoformat(), "sample": bool(raw.get("sample")),
        "config": {"target_bh": C.FIRST_TOUCH_TARGET_BH, "breach_bh": C.FIRST_TOUCH_BREACH_BH,
                   "bh_per_day": C.BH_PER_DAY, "aging": C.AGING_BUCKETS_BD,
                   "lookback_days": C.LOOKBACK_DAYS, "talk_min_s": C.TALK_MIN_SEC, "conn_manual_notes": C.CONNECTED_MANUAL_WITH_NOTES, "adequate": [C.ADEQUATE_MIN_TOUCHES, C.ADEQUATE_MIN_DAYS,
                                                                  C.ADEQUATE_MIN_CALLS]},
        "bdrs": [{"id": k, **v, **({"name": f"Sample BDR {i + 1}"} if raw.get("sample") else {})}
                 for i, (k, v) in enumerate(bdr.items())],
        "contacts": rows,
        "calls": [x["_row"] for x in call_rows],
        "call_cols": ["owner", "week", "hour", "connected", "convo", "outcome", "notes", "manual",
                      "backdated", "dup", "valid", "dow", "chn", "src",
                      "dur_s", "contact", "day", "has_dur", "conn_via", "reg"],
        "emails": email_rows, "email_cols": ["owner", "week", "bounced", "group", "internal", "hour", "dow", "chn", "src", "day", "reg"],
        "checks": checks,
    }
