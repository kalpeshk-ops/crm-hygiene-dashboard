"""Dashboard configuration. Every rule from the metric spec lives here."""

PORTAL_ID = 20091681
TIMEZONE = "Asia/Kolkata"

# How far back to pull assignments and activities.
LOOKBACK_DAYS = 90

# BDRs ticked in the spec (HubSpot owner IDs). Region can be filled in later.
BDR_OWNERS = {
    "1576642308": {"name": "Ashwini Salunke", "region": ""},
    "79710714": {"name": "Btari Anya Safira", "region": ""},
    "258655244": {"name": "Lovely Rose Sanchez", "region": ""},
    "1900772008": {"name": "Mirna Kais", "region": ""},
    "81486491": {"name": "Shagun Singh", "region": ""},
    "1324590097": {"name": "Shazer Leah Esguerra", "region": ""},
    "91564712": {"name": "Shreiyas M", "region": ""},
    "87700994": {"name": "Simon Peter de Souza", "region": ""},
    "1683927953": {"name": "Sneha Majumdar", "region": ""},
}

# Business hours: Monday-Friday, 07:30-20:30 IST.
BH_START = (7, 30)
BH_END = (20, 30)
BH_WEEKDAYS = {0, 1, 2, 3, 4}
BH_PER_DAY = 13.0
HOLIDAYS = []  # "YYYY-MM-DD" strings, IST dates

# SLA (business hours)
FIRST_TOUCH_TARGET_BH = 1.0
FIRST_TOUCH_BREACH_BH = 13.0

# Qualifying touches
CALL_EXCLUDED_STATUSES = {"FAILED", "CANCELED"}
EMAIL_EXCLUDED_STATUSES = {"FAILED", "SCHEDULED", "SENDING"}
INTERNAL_EMAIL_DOMAINS = {"disprz.com"}
CONVERSATION_MIN_MS = 60_000
TALK_MIN_SEC = 30
# A call counts as CONNECTED when it has more than TALK_MIN_SEC seconds of talk time,
# OR it was logged manually (not by TeleCMI/Maqsam) and has call notes.
CONNECTED_MANUAL_WITH_NOTES = True
MEETING_OUTCOME_KEYWORDS = ["meeting"]

# Data quality flags
BACKDATE_HOURS = 24
DUPLICATE_CALL_MINUTES = 5
GROUP_EMAIL_MAX_CONTACTS = 5

# Coverage / persistence windows (business days)
ABANDONED_IDLE_BD = 10
PERSISTENCE_WINDOWS_BD = (10, 20)
AGING_BUCKETS_BD = [(0, 2, "0-2"), (3, 5, "3-5"), (6, 10, "6-10"), (11, 20, "11-20"), (21, None, "20+")]

# MQL Status (contact property mql_status) internal values
MQL_WORKING = "a6"
MQL_MEETING_SCHEDULED = "Meeting scheduled"
MQL_UNTOUCHED = "a7"
MQL_CLOSED_CHECKED = {"a4": "Disqualified", "a8": "Not Interested", "No Response": "No Response"}
MQL_CLOSED_ALL = {"a4", "a8", "No Response", "a10", "a1", "a2", "a3"}
MQL_LABELS = {
    "Meeting scheduled": "Meeting scheduled", "a6": "Working", "a5": "Qualified",
    "a1": "Existing Customer", "a2": "Existing Opportunity", "a3": "Partner",
    "a4": "Disqualified", "a7": "Untouched", "a8": "Not Interested", "a10": "DND",
    "a12": "Nurture", "Qualified": "Qualified", "Referral": "Referral", "No Response": "No Response",
}

# MQL status hygiene checks
WORKING_IDLE_BD = 2
MEETING_NO_DEAL_GRACE_BD = 1
DEMO_OVERDUE_HOURS = 48
DEMO_STATUS_SCHEDULED = "Scheduled"
DEMO_DATE_PROPERTY = "proposed_demo_date_"
ADEQUATE_MIN_TOUCHES = 5
ADEQUATE_MIN_DAYS = 3
ADEQUATE_MIN_CALLS = 1

# Contact segmentation filters (dashboard dropdowns)
CHANNEL_PROPERTY = "channel_"
SOURCE_PROPERTY = "disprz_original_source"
SOURCE_LABELS = {  # internal value -> label, where they differ
    "Organic": "Organic Search", "Paid": "Paid Search", "Direct": "Direct Traffic", "Email": "Email Marketing",
    "Disprz LeadGen": "BDR Cold Outreach", "webinars": "Webinars",
}
BLANK_LABEL = "(blank)"

# Deals tab: funnel metrics
DEAL_CHANNEL_PROPERTY = "channel_"
DEAL_ORIGINATION_PROPERTY = "deal_origination__"
ORIGINATION_LABELS = {
    "Organic": "Organic Search", "Paid": "Paid Search", "Direct": "Direct Traffic", "Sales": "Field Sales",
    "Disprz LeadGen": "BDR Cold Outreach", "Email": "Email marketing", "webinars": "Webinars",
}
DEMO_DONE_DATE_PROPERTY = "demo_done_date"
# A demo counts as DONE when Demo Done Date is set, or Demo Status is one of these:
DEMO_DONE_STATUSES = {"SQO < 6months", "SQO > 6months", "Completed - No fit", "Completed - Not interested",
                      "Not qualified", "Discovery"}
SQO_STATUSES = {"SQO < 6months", "SQO > 6months"}
# SQO date (drives the date filter for SQO counts and value). Falls back to Demo Done Date when blank.
SQO_DATE_PROPERTY = "last_stage_update_to_demo__"  # Last Stage Update to Demo - Disprz Sales Pipeline
AMOUNT_PROPERTY = "amount_in_home_currency"
CURRENCY = "USD"
DEAL_SPOC_PROPERTY = "bd_spoc"  # BD SPOC (stores a HubSpot owner ID)

# Reasons shown next to closed-out contacts
DISQ_REASON_PROPERTY = "new_disqualification_reason"   # Disqualification reason
NI_REASON_PROPERTY = "not_interested_reasons__c"       # Not interested Reasons
# Fallback labels if the HubSpot app can't read property definitions
DISQ_REASON_LABELS = {
    "a1": "Academia", "a2": "Competitor", "a3": "Not in ICP - cannot cater user requirements",
    "a4": "Not in ICP - userbase too low", "a5": "Spam - User unidentified", "a6": "ICP - No Requirement",
    "a7": "Not in ICP - Irrelevant Designation", "a8": "ICP - No Response",
}
