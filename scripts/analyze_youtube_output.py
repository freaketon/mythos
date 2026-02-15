from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path


def _tokenize(text: str) -> set[str]:
    parts = re.split(r"[^a-z0-9]+", (text or "").lower())
    return {p for p in parts if len(p) >= 3}


def _domain_from_email(email: str) -> str:
    email = (email or "").strip()
    if "@" not in email:
        return ""
    return email.split("@", 1)[-1].lower()


def _local_from_email(email: str) -> str:
    email = (email or "").strip()
    if "@" not in email:
        return ""
    return email.split("@", 1)[0].lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hydrated", required=True, type=Path)
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    with args.hydrated.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)

    url_key = "Youtube URL"
    name_key = "Name"
    email_key = "Email"
    company_key = "Company"
    company_url_key = "Company URL"

    urls = [row.get(url_key, "").strip() for row in rows if row.get(url_key, "").strip()]
    ctr = Counter(urls)
    dupes = [(u, c) for u, c in ctr.most_common() if c > 1]

    print(f"rows={len(rows)} youtube_nonempty={len(urls)} youtube_unique={len(ctr)} dupes={len(dupes)}")
    if dupes:
        print("\nTop duplicates:")
        for url, c in dupes[: args.top]:
            print(f"{c} {url}")
            shown = 0
            for row in rows:
                if row.get(url_key, "").strip() != url:
                    continue
                name = row.get(name_key, "").strip()
                email = row.get(email_key, "").strip()
                company = row.get(company_key, "").strip()
                company_url = row.get(company_url_key, "").strip()
                print(f"  - {name} | {company} | {email} | {company_url}")
                shown += 1
                if shown >= 6:
                    break

    suspicious: list[tuple[str, str, str]] = []
    for row in rows:
        url = row.get(url_key, "").strip()
        if not url:
            continue
        name = row.get(name_key, "").strip()
        email = row.get(email_key, "").strip()
        company = row.get(company_key, "").strip()
        company_url = row.get(company_url_key, "").strip()

        email_local = _local_from_email(email)
        email_domain = _domain_from_email(email)
        lead_tokens = _tokenize(" ".join([name, company, email_local, email_domain, company_url]))
        yt_tokens = _tokenize(url + " " + (row.get("Youtube handle", "") or ""))
        overlap = lead_tokens & yt_tokens
        # Very cheap mismatch heuristic: no overlap at all between lead identifiers and the chosen channel URL/handle.
        if lead_tokens and yt_tokens and not overlap:
            suspicious.append((name, email, url))

    print(f"\nsuspicious_zero_overlap={len(suspicious)}")
    for name, email, url in suspicious[: args.top]:
        print(f"- {name} | {email} -> {url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
