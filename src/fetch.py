"""Pull everything the metrics need from HubSpot into one plain dict (the 'raw' dataset)."""
from datetime import timedelta

from . import config as C
from .bizhours import utc_now
from .hubspot import HubSpot, to_ms

CONTACT_PROPS = ["firstname", "lastname", "email", "phone", "mobilephone", "hubspot_owner_id",
                 "hubspot_owner_assigneddate", "mql_status", "mql_status_update_date",
                 "associatedcompanyid", "hs_lead_status", C.CHANNEL_PROPERTY, C.SOURCE_PROPERTY,
                 "company", C.DISQ_REASON_PROPERTY, C.NI_REASON_PROPERTY]
CALL_PROPS = ["hs_timestamp", "hs_createdate", "hubspot_owner_id", "hs_call_direction", "hs_call_status",
              "hs_call_disposition", "hs_call_duration", "hs_call_body", "hs_call_source",
              "hs_object_source_label", "hs_object_source_detail_1"]
EMAIL_PROPS = ["hs_timestamp", "hs_createdate", "hubspot_owner_id", "hs_email_direction",
               "hs_email_status", "hs_email_to_email"]
MEETING_PROPS = ["hs_timestamp", "hs_createdate", "hubspot_owner_id", "hs_meeting_outcome"]
DEAL_PROPS = ["dealname", "hubspot_owner_id", "hs_is_closed", "dealstage", "pipeline",
              "demo_status", C.DEMO_DATE_PROPERTY, "amount", "createdate", "hs_lastmodifieddate",
              C.DEAL_CHANNEL_PROPERTY, C.DEAL_ORIGINATION_PROPERTY, C.DEMO_DONE_DATE_PROPERTY, C.AMOUNT_PROPERTY, C.SQO_DATE_PROPERTY,
              C.DEAL_SPOC_PROPERTY]


def _flat(rec, keep=None):
    p = dict(rec.get("properties", {}))
    p["id"] = str(rec["id"])
    return p


def fetch_all(hs=None, log=print):
    hs = hs or HubSpot()
    now = utc_now()
    start = now - timedelta(days=C.LOOKBACK_DAYS)
    s_ms, e_ms = to_ms(start), to_ms(now + timedelta(days=1))
    bdr_ids = list(C.BDR_OWNERS)
    owner_f = {"propertyName": "hubspot_owner_id", "operator": "IN", "values": bdr_ids}

    log("contacts assigned in window ...")
    contacts = {r["id"]: _flat(r) for r in hs.search(
        "contacts", [owner_f], CONTACT_PROPS, "hubspot_owner_assigneddate", s_ms, e_ms)}
    log(f"  {len(contacts)}")
    log("contacts in Working / Meeting scheduled (any assignment date) ...")
    for r in hs.search_simple("contacts", [owner_f, {"propertyName": "mql_status", "operator": "IN",
                              "values": [C.MQL_WORKING, C.MQL_MEETING_SCHEDULED]}], CONTACT_PROPS):
        contacts.setdefault(str(r["id"]), _flat(r))
    log(f"  total contacts {len(contacts)}")

    def activities(obj, props):
        log(f"{obj} ...")
        rows = [_flat(r) for r in hs.search(obj, [owner_f], props, "hs_timestamp", s_ms, e_ms)]
        assoc = hs.associations(obj, "contacts", [r["id"] for r in rows])
        for r in rows:
            r["contact_ids"] = assoc.get(r["id"], [])
        log(f"  {len(rows)}")
        return rows

    calls = activities("calls", CALL_PROPS)
    for c in calls:  # keep only whether notes exist, not the note text
        c["has_notes"] = bool((c.pop("hs_call_body", None) or "").strip())
    emails = activities("emails", EMAIL_PROPS)
    meetings = activities("meetings", MEETING_PROPS)

    # MQL status history for closed contacts (check 4)
    closed_ids = [cid for cid, c in contacts.items() if c.get("mql_status") in C.MQL_CLOSED_CHECKED]
    log(f"mql_status history for {len(closed_ids)} closed contacts ...")
    for r in hs.batch_read("contacts", closed_ids, ["mql_status"], history=["mql_status"]):
        hist = r.get("propertiesWithHistory", {}).get("mql_status", [])
        contacts[str(r["id"])]["mql_history"] = [{"value": h.get("value"), "timestamp": h.get("timestamp")}
                                                 for h in hist]

    # Deals for Meeting scheduled contacts (check 2)
    ms_ids = [cid for cid, c in contacts.items() if c.get("mql_status") == C.MQL_MEETING_SCHEDULED]
    log(f"deals for {len(ms_ids)} meeting-scheduled contacts ...")
    contact_deals = hs.associations("contacts", "deals", ms_ids)
    company_ids = [contacts[c].get("associatedcompanyid") for c in ms_ids if contacts[c].get("associatedcompanyid")]
    company_deals = hs.associations("companies", "deals", company_ids)
    deal_ids = {d for v in contact_deals.values() for d in v} | {d for v in company_deals.values() for d in v}
    deals = {str(r["id"]): _flat(r) for r in hs.batch_read("deals", list(deal_ids), DEAL_PROPS)}

    # Deals with demo still Scheduled after the proposed date (check 3)
    log("deals with Demo Status = Scheduled ...")
    cutoff = now - timedelta(hours=C.DEMO_OVERDUE_HOURS)
    demo_deals = [_flat(r) for r in hs.search_simple("deals", [
        {"propertyName": "demo_status", "operator": "EQ", "value": C.DEMO_STATUS_SCHEDULED},
        {"propertyName": C.DEMO_DATE_PROPERTY, "operator": "LT", "value": str(to_ms(cutoff))},
    ], DEAL_PROPS)]

    # Deals tab: every deal with a proposed demo date in the window (plus the next 30 days)
    log("deals with a proposed demo date in the window ...")
    demo_window = {str(r["id"]): _flat(r) for r in hs.search(
        "deals", [], DEAL_PROPS, C.DEMO_DATE_PROPERTY, s_ms, to_ms(now + timedelta(days=30)))}
    log("deals with a demo done date in the window ...")
    for r in hs.search("deals", [], DEAL_PROPS, C.DEMO_DONE_DATE_PROPERTY, s_ms, to_ms(now + timedelta(days=1))):
        demo_window.setdefault(str(r["id"]), _flat(r))
    log("SQO deals with an SQO date in the window ...")
    for r in hs.search("deals", [{"propertyName": "demo_status", "operator": "IN", "values": sorted(C.SQO_STATUSES)}],
                       DEAL_PROPS, C.SQO_DATE_PROPERTY, s_ms, to_ms(now + timedelta(days=1))):
        demo_window.setdefault(str(r["id"]), _flat(r))
    demo_window = list(demo_window.values())
    log(f"  {len(demo_window)}")

    # Company names for contacts whose own "Company Name" field is empty
    need = {c.get("associatedcompanyid") for c in contacts.values()
            if not (c.get("company") or "").strip() and c.get("associatedcompanyid")}
    log(f"company names for {len(need)} companies ...")
    company_names = {str(r["id"]): (r.get("properties", {}).get("name") or "")
                     for r in hs.batch_read("companies", [x for x in need if x], ["name"])}

    return {
        "company_names": company_names,
        "reason_labels": {"disq": hs.property_labels("contacts", C.DISQ_REASON_PROPERTY),
                          "ni": hs.property_labels("contacts", C.NI_REASON_PROPERTY)},
        "demo_window_deals": demo_window, "deal_stages": hs.deal_stages(),
        "now": now.isoformat(), "start": start.isoformat(),
        "contacts": list(contacts.values()), "calls": calls, "emails": emails, "meetings": meetings,
        "contact_deals": contact_deals, "company_deals": company_deals, "deals": deals,
        "demo_deals": demo_deals, "dispositions": hs.call_dispositions(), "owners": hs.owners(),
    }
