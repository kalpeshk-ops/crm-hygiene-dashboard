"""Generate a fake raw dataset (no real people) to test the build: python -m tools.make_sample sample.json"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone

from src import config as C
from src.bizhours import add_business_hours

random.seed(7)
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
START = NOW - timedelta(days=C.LOOKBACK_DAYS)
FIRST = ["Asha", "Ravi", "Meera", "Arjun", "Nisha", "Karan", "Priya", "Dev", "Isha", "Vikram", "Tara", "Omar", "Lina", "Noah", "Maya"]
LAST = ["Rao", "Iyer", "Shah", "Khan", "Menon", "Das", "Pillai", "Gupta", "Nair", "Bose", "Hamid", "Cruz", "Lim"]
iso = lambda d: d.isoformat().replace("+00:00", "Z")


def main(path):
    owners = list(C.BDR_OWNERS)
    speed = {o: random.choice([0.5, 1, 2, 4, 8]) for o in owners}
    contacts, calls, emails, meetings = [], [], [], []
    cid = 1000
    aid = 50000
    contact_deals, deals = {}, {}
    for o in owners:
        for _ in range(random.randint(60, 140)):
            cid += 1
            assigned = START + timedelta(minutes=random.randint(0, int((NOW - START).total_seconds() // 60)))
            mql = random.choices(["a6", "Meeting scheduled", "a4", "a8", "No Response", "a7", "a5", ""],
                                 [30, 8, 8, 5, 6, 15, 5, 10])[0]
            c = {"id": str(cid), "firstname": random.choice(FIRST), "lastname": random.choice(LAST),
                 "email": "" if random.random() < 0.04 else f"user{cid}@example.com",
                 "phone": "" if random.random() < 0.15 else "+910000000000", "mobilephone": "",
                 "hubspot_owner_id": o, "hubspot_owner_assigneddate": iso(assigned), "mql_status": mql,
                 "mql_status_update_date": iso(assigned + timedelta(days=random.uniform(0.5, 10))),
                 "associatedcompanyid": str(9000 + cid),
                 "company": random.choice(["Acme Learning", "Northwind Retail", "Globex Pharma", "Initech Bank", "Umbrella Logistics", "Stark Motors", ""]),
                 "new_disqualification_reason": random.choice(["a3", "a4", "a5", "a7", "ICP - No budget", ""]) if mql == "a4" else "",
                 "not_interested_reasons__c": random.choice(["No Requirement", "In-house system", "Other provider;On hold", ""]) if mql == "a8" else "",
                 "channel_": random.choices(["Outbound", "Marketing", "Sales", "Farming", "Partnership", ""], [40, 30, 10, 8, 4, 8])[0],
                 "disprz_original_source": random.choices(["Disprz LeadGen", "Events", "webinars", "Paid Social", "Organic", "3P LeadGen", "Partner", "Farming", ""], [35, 12, 10, 10, 8, 8, 5, 5, 7])[0]}
            n_touch = 0 if random.random() < 0.12 else random.choice([1, 1, 2, 2, 3, 4, 5, 6, 7, 8])
            t = add_business_hours(assigned, random.expovariate(1 / speed[o])).astimezone(timezone.utc)
            for _ in range(n_touch):
                if t > NOW:
                    break
                aid += 1
                if random.random() < 0.07:  # a little off-hours / weekend activity
                    t = t + timedelta(hours=random.choice([-4, 3, 48]))
                if random.random() < 0.6:
                    manual = random.random() < 0.2
                    connected = random.random() < 0.3
                    calls.append({"id": str(aid), "hs_timestamp": iso(t),
                                  "hs_createdate": iso(t + timedelta(hours=30 if random.random() < 0.03 else 0.01)),
                                  "hubspot_owner_id": o, "hs_call_direction": "" if manual else "OUTBOUND",
                                  "hs_call_status": "COMPLETED" if connected else random.choice(["NO_ANSWER", "NO_ANSWER", "BUSY", "FAILED"]),
                                  "hs_call_disposition": "Connected" if connected else ("" if random.random() < 0.1 else "No answer"),
                                  "hs_call_duration": "" if manual and random.random() < 0.6 else str(int(random.choice([random.uniform(3000, 30000), random.uniform(30000, 400000)])) if connected else 0),
                                  "has_notes": random.random() < 0.4,
                                  "hs_object_source_label": "CRM_UI" if manual else "INTEGRATION",
                                  "contact_ids": [c["id"]]})
                else:
                    emails.append({"id": str(aid), "hs_timestamp": iso(t), "hs_createdate": iso(t),
                                   "hubspot_owner_id": o, "hs_email_direction": "EMAIL",
                                   "hs_email_status": "BOUNCED" if random.random() < 0.04 else "SENT",
                                   "hs_email_to_email": f"user{cid}@example.com", "contact_ids": [c["id"]]})
                    if random.random() < 0.15:
                        aid += 1
                        emails.append({"id": str(aid), "hs_timestamp": iso(t + timedelta(hours=5)),
                                       "hubspot_owner_id": o, "hs_email_direction": "INCOMING_EMAIL",
                                       "contact_ids": [c["id"]]})
                t = add_business_hours(t, random.uniform(2, 40)).astimezone(timezone.utc)
            if mql == "Meeting scheduled" or random.random() < 0.05:
                aid += 1
                meetings.append({"id": str(aid), "hs_createdate": iso(min(t, NOW)), "hs_timestamp": iso(min(t, NOW)),
                                 "hubspot_owner_id": o, "contact_ids": [c["id"]]})
                if random.random() < 0.6:
                    did = str(700000 + cid)
                    contact_deals[c["id"]] = [did]
                    deals[did] = {"id": did, "hs_is_closed": "false"}
            if mql in C.MQL_CLOSED_CHECKED:
                c["mql_history"] = [{"value": mql, "timestamp": c["mql_status_update_date"]}]
            contacts.append(c)
    demo_deals = [{"id": str(800000 + i), "dealname": f"Sample Co {i} - New Business", "hubspot_owner_id": random.choice(owners),
                   "demo_status": "Scheduled", C.DEMO_DATE_PROPERTY: (NOW - timedelta(days=random.randint(3, 20))).date().isoformat()}
                  for i in range(12)]
    ae = {"900001": "Sample AE 1", "900002": "Sample AE 2", "900003": "Sample AE 3", "900004": "Sample AE 4"}
    statuses = ["SQO < 6months", "SQO > 6months", "Completed - No fit", "Completed - Not interested", "Not qualified", "No Show", "Discovery", "Closed Lost"]
    window = []
    for i in range(220):
        dd = (NOW - timedelta(days=random.randint(-21, C.LOOKBACK_DAYS))).date()
        owner = random.choice(list(ae) * 3 + owners)
        lag_days = (NOW.date() - dd).days
        chn, orig = random.choice([("Outbound", "Disprz LeadGen"), ("Outbound", "Disprz LeadGen"), ("Outbound", "GTM Engineering"),
                                   ("Marketing", "Organic"), ("Marketing", "Paid Social"), ("Marketing", "Events"), ("Marketing", "webinars"),
                                   ("Farming", "Farming"), ("Partnership", "Partner"), ("Sales", "Sales")])
        sqo_bias = {"Farming": 0.7, "Partnership": 0.55, "Sales": 0.6, "Marketing": 0.4, "Outbound": 0.3}[chn]
        if lag_days < 3:
            status = "Scheduled"
        elif random.random() < (0.22 if owner in ae else 0.35):
            status = random.choice(["Scheduled", "Scheduled", "No Show"])
        elif random.random() < sqo_bias:
            status = random.choice(["SQO < 6months", "SQO > 6months"])
        else:
            status = random.choice(["Completed - No fit", "Completed - Not interested", "Not qualified", "Discovery", "Closed Lost"])
        done = status in C.DEMO_DONE_STATUSES
        value = random.choice([5000, 10000, 15000, 25000, 40000, 67000]) if status in C.SQO_STATUSES else random.choice([0, 0, 5000])
        window.append({"id": str(810000 + i), "dealname": f"Sample Co {i} - New Business", "hubspot_owner_id": owner,
                       "demo_status": status, C.DEMO_DATE_PROPERTY: dd.isoformat(), C.DEAL_SPOC_PROPERTY: random.choice(owners + [""]), "dealstage": random.choice(["s1", "s2", "s3"]),
                       "pipeline": "default", "amount": str(value), C.AMOUNT_PROPERTY: str(value), "hs_is_closed": "false",
                       C.DEAL_CHANNEL_PROPERTY: chn, C.DEAL_ORIGINATION_PROPERTY: orig,
                       C.DEMO_DONE_DATE_PROPERTY: (dd + timedelta(days=random.choice([0, 0, 1]))).isoformat() if done else "",
                       C.SQO_DATE_PROPERTY: (dd + timedelta(days=random.randint(1, 12))).isoformat() if status in C.SQO_STATUSES and random.random() < 0.93 else ""})
    raw_stages = {"s1": {"stage": "Discovery", "pipeline": "Disprz Sales Pipeline"}, "s2": {"stage": "Demo", "pipeline": "Disprz Sales Pipeline"},
                  "s3": {"stage": "Proposal", "pipeline": "Disprz Sales Pipeline"}}
    raw = {"sample": True, "company_names": {}, "reason_labels": {"disq": {"a3": "Not in ICP - cannot cater user requirements", "a4": "Not in ICP - userbase too low", "a5": "Spam - User unidentified", "a7": "Not in ICP - Irrelevant Designation"}, "ni": {}}, "demo_window_deals": window, "deal_stages": raw_stages, "now": iso(NOW), "start": iso(START), "contacts": contacts, "calls": calls, "emails": emails,
           "meetings": meetings, "contact_deals": contact_deals, "company_deals": {}, "deals": deals,
           "demo_deals": demo_deals, "dispositions": {}, "owners": ae}
    with open(path, "w") as f:
        json.dump(raw, f)
    print(f"{len(contacts)} contacts, {len(calls)} calls, {len(emails)} emails")


if __name__ == "__main__":
    main(sys.argv[1])
