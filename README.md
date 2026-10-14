# BDR CRM Hygiene Dashboard

Hourly dashboard of how fast and how well Disprz BDRs work their assigned contacts, built from HubSpot and hosted on GitHub Pages.

GitHub Actions pulls contacts, calls, emails, meetings and deals from HubSpot, computes the metrics in Python, and publishes one static page (`dist/index.html`) to GitHub Pages. Contact data is never committed to this repo.

## What it measures

- **Clock:** starts at `hubspot_owner_assigneddate`, counted in business hours (Mon–Fri, 07:30–20:30 IST).
- **Touch:** an outbound call (from TeleCMI/Maqsam or logged manually) or a 1:1 email sent through the Sales Extension or a sequence, by the current contact owner, on or after assignment. Calls marked Failed/Canceled, emails sent only to @disprz.com addresses, and manual logs that duplicate a tool-logged call within 5 minutes are not touches.
- **First-touch target:** 1 business hour. **Breach:** 13 business hours (one business day).
- **Hygiene checks:** Working with no touch for 2 business days; Meeting scheduled with no open deal on the contact or its company (1-day grace); deal Demo Status still Scheduled 48 hours after `proposed_demo_date_`; Disqualified / Not Interested / No Response with fewer than 5 touches on 3 days including 1 call; plus SLA breaches, abandoned contacts, status lag, missing phone/email, and data-quality flags.

Every rule and threshold is in `src/config.py`.

## Files

| Path | What it does |
| --- | --- |
| `src/config.py` | BDR list, business hours, SLA and check thresholds, MQL Status values |
| `src/hubspot.py` | HubSpot API client (search with automatic splitting past the 10,000-result cap, batch read, associations) |
| `src/fetch.py` | Pulls the raw dataset |
| `src/bizhours.py` | Business-hours arithmetic in IST |
| `src/metrics.py` | Per-contact metrics and hygiene-check lists |
| `template.html` | The dashboard page; data is injected at build time |
| `build.py` | Runs fetch → metrics → `dist/index.html` |
| `tools/make_sample.py` | Fake dataset for testing the page without HubSpot |
| `.github/workflows/refresh.yml` | Hourly build and deploy |

## Setup (GitHub Pages)

1. **HubSpot private app.** Read-only scopes for contacts, companies, deals, owners and `sales-email-read`. Copy the token.
2. **Public GitHub repo** with these files (including `.github/workflows/refresh.yml`).
3. **Secret:** Settings → Secrets and variables → Actions → `HUBSPOT_TOKEN`.
4. **Pages:** Settings → Pages → Source: GitHub Actions.
5. **First run:** Actions → Refresh dashboard → Run workflow. The link appears on the run and in Settings → Pages.

The page is public to anyone with the link. No CRM data is committed to the repo; it exists only in the published page.

## Local testing

```bash
pip install -r requirements.txt
python -m tools.make_sample sample.json
python build.py --raw sample.json      # writes dist/index.html from fake data
HUBSPOT_TOKEN=... python build.py      # live run
```

## Using the page

- **Date range:** presets (today, last 7/30/90 days, this or last month) or a custom from–to. Contacts are filtered by the date they were assigned; calls and emails by the date they happened. Weekly charts show the weeks that overlap the range.
- **Disqualified without adequate touches (Contacts tab, near the top):** contacts set to Disqualified (or Not Interested / No Response, via the toggle) without 5 touches on 3 days including 1 call. Shows the share per BDR, the distribution of touches before the status change, what each contact was short of, and the list. Filtered by the date the status was set.
- **Contacts / Deals tabs:** the switch pinned to the bottom of the screen. The Deals tab shows **demo done but not updated**: deals whose Proposed Demo Date (`proposed_demo_date_`) is more than 48 hours in the past and whose Demo Status is still Scheduled, by deal owner, with how long each has gone un-updated and a list to fix. On this tab the date range applies to the proposed demo date and the filter is by deal owner.
- **Deals tab, demo funnel:** demos scheduled (Proposed Demo Date in range), demos done (Demo Done Date in range, or a Demo Status showing the demo happened), Demo → SQO conversion (SQO = Demo Status "SQO < 6months" or "SQO > 6months"), and SQO count and value (`amount_in_home_currency`, USD). SQOs are dated by Last Stage Update to Demo - Disprz Sales Pipeline (`last_stage_update_to_demo__`, falling back to Demo Done Date when blank), so the date filter picks them up by that date. Demo → SQO = SQOs dated in the range ÷ demos done in the range. Each is broken down by deal Channel_ (`channel_`) and Deal Origination (`deal_origination__`), which are also filters on this tab. Field names and status lists are in `src/config.py`.
- **Theme:** Light, Dark or System (follows your device), switched from the top-right of the header and remembered in your browser.

## Changing things

- **Add or remove a BDR:** edit `BDR_OWNERS` in `src/config.py` (owner ID → name, optional region).
- **Holidays:** add `YYYY-MM-DD` dates to `HOLIDAYS`.
- **Thresholds:** all in `src/config.py`. A call counts as **connected** when it has more than `TALK_MIN_SEC` (30) seconds of talk time, or was logged manually with call notes (`CONNECTED_MANUAL_WITH_NOTES`). Connect rate = connected calls ÷ total calls.
- **Channel filters:** the Channel_ (`channel_`) and Disprz Original Source (`disprz_original_source`) dropdowns are set by `CHANNEL_PROPERTY` and `SOURCE_PROPERTY` in `src/config.py`. Calls and emails take the channel of the contact they're logged against.
