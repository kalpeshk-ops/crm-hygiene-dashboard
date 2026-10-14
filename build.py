"""Build the dashboard: fetch from HubSpot, compute metrics, write dist/index.html.

Usage:
    python build.py                    # live run (needs HUBSPOT_TOKEN)
    python build.py --raw sample.json  # build from a saved raw dataset (testing)
    python build.py --save-raw raw.json  # live run, also keep the raw pull locally
"""
import argparse
import warnings

# macOS system Python is built with LibreSSL; urllib3 warns about it but HubSpot calls work fine.
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
import json
import pathlib

from src.metrics import compute

ROOT = pathlib.Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw")
    ap.add_argument("--save-raw")
    ap.add_argument("--out", default="dist")
    args = ap.parse_args()

    if args.raw:
        raw = json.loads(pathlib.Path(args.raw).read_text())
    else:
        from src.fetch import fetch_all
        raw = fetch_all()
        if args.save_raw:
            pathlib.Path(args.save_raw).write_text(json.dumps(raw))

    data = compute(raw)
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = (ROOT / "template.html").read_text().replace("/*__DATA__*/null", payload)
    out = ROOT / args.out
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html)
    print(f"wrote {out / 'index.html'}: {len(data['contacts'])} contacts, {len(data['calls'])} calls, "
          f"{len(data['emails'])} emails")


if __name__ == "__main__":
    main()
