#!/usr/bin/env python3
"""
Contact Enrichment & ICP Scoring Pipeline

Ingests a contact list CSV, enriches with social data,
and scores each contact against a video-first operator ICP.

ICP Target: Video-first operators where archive pain is highly probable.
"""

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass, field, asdict
from typing import Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Contact:
    contact_id: str = ""
    name: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    company: str = ""
    company_url: str = ""
    city: str = ""
    industry: str = ""
    revenue: str = ""
    headcount: str = ""
    bio: str = ""
    context: str = ""
    help_goal: str = ""

    # Social discovery
    instagram_url: str = ""
    instagram_followers: str = ""
    instagram_cadence: str = ""

    youtube_url: str = ""
    youtube_subscribers: str = ""
    youtube_cadence: str = ""

    tiktok_url: str = ""
    tiktok_followers: str = ""
    tiktok_cadence: str = ""

    # Longevity
    years_publishing: str = ""

    # Scoring
    icp_fit_score: int = 0
    icp_tier: str = ""

    # Metadata
    notes: str = ""


# ---------------------------------------------------------------------------
# Step 1: Load & Normalize
# ---------------------------------------------------------------------------

def load_contacts(csv_path: str) -> list[Contact]:
    """Load semicolon-delimited CSV and normalize fields."""
    contacts = []
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter=";")
        fields = reader.fieldnames or []

        for row in reader:
            name_raw = (row.get("Name", "") or "").strip()
            email = (row.get("Email", "") or "").strip().lower()

            if not email:
                continue  # skip rows without email

            # Normalize name
            first = (row.get("First name", "") or "").strip()
            last = (row.get("Last name", "") or "").strip()
            name = normalize_name(name_raw, first, last)

            # Company
            company = (row.get("Company", "") or "").strip()
            company_url = (row.get("Company URL", "") or "").strip()

            # Generate deterministic contact_id from email
            contact_id = hashlib.md5(email.encode()).hexdigest()[:12]

            # Bio field (Twitter bio question)
            bio_key = [k for k in fields if "Twitter bio" in k or "Describe who" in k]
            bio = (row.get(bio_key[0], "") or "").strip() if bio_key else ""

            # Help goal
            help_key = [k for k in fields if "most important" in k]
            help_goal = (row.get(help_key[0], "") or "").strip() if help_key else ""

            # Context
            ctx_key = [k for k in fields if "final context" in k.lower()]
            context = (row.get(ctx_key[0], "") or "").strip() if ctx_key else ""

            # Industry
            ind_key = [k for k in fields if "industry" in k.lower()]
            industry = (row.get(ind_key[0], "") or "").strip() if ind_key else ""

            # Revenue
            rev_key = [k for k in fields if "revenue the last" in k.lower()]
            revenue = (row.get(rev_key[0], "") or "").strip() if rev_key else ""

            # Headcount
            headcount = (row.get("Headcount", "") or "").strip()

            # City
            city = (row.get("City", "") or "").strip()

            c = Contact(
                contact_id=contact_id,
                name=name,
                first_name=first or name.split()[0] if name else "",
                last_name=last or (name.split()[-1] if len(name.split()) > 1 else ""),
                email=email,
                company=company,
                company_url=company_url,
                city=city,
                industry=industry,
                revenue=revenue,
                headcount=headcount,
                bio=bio,
                context=context,
                help_goal=help_goal,
            )
            contacts.append(c)

    print(f"[Step 1] Loaded {len(contacts)} contacts with valid emails")
    return contacts


def normalize_name(name_raw: str, first: str, last: str) -> str:
    """Clean up name field."""
    # Remove common prefixes like "Hi Dan, I'm ..."
    name = name_raw
    patterns_to_strip = [
        r"^Hi\s+\w+,?\s*I'?m\s+",
        r"^I'?m\s+",
        r"^Hey,?\s*I'?m\s+",
        r"^Hello,?\s*I'?m\s+",
        r"^My name is\s+",
        r"\s*-\s*Team\s+\w+$",
        r"\s*\(.*?\)\s*$",
    ]
    for pat in patterns_to_strip:
        name = re.sub(pat, "", name, flags=re.IGNORECASE).strip()

    # If first/last provided and name is ambiguous, prefer first+last
    if first and last:
        return f"{first} {last}"
    if first and not last and len(name.split()) <= 1:
        return first

    return name.strip() if name.strip() else name_raw.strip()


# ---------------------------------------------------------------------------
# Step 2: Social Account Discovery (from existing data)
# ---------------------------------------------------------------------------

def extract_social_from_existing_data(contacts: list[Contact]) -> None:
    """Extract social URLs from Company URL and bio text."""
    ig_count = 0
    yt_count = 0
    tt_count = 0

    for c in contacts:
        url = c.company_url.lower()

        # Instagram
        if "instagram.com" in url:
            c.instagram_url = clean_instagram_url(c.company_url)
            ig_count += 1

        # YouTube
        if "youtube.com" in url or "youtu.be" in url:
            c.youtube_url = clean_youtube_url(c.company_url)
            yt_count += 1

        # TikTok
        if "tiktok.com" in url:
            c.tiktok_url = c.company_url.strip()
            tt_count += 1

        # Also scan bio text for social handles/URLs
        all_text = f"{c.bio} {c.context}"
        ig_match = re.search(r'instagram\.com/[\w.]+', all_text, re.IGNORECASE)
        if ig_match and not c.instagram_url:
            c.instagram_url = "https://www." + ig_match.group(0)
            ig_count += 1

        yt_match = re.search(r'youtube\.com/[@\w]+', all_text, re.IGNORECASE)
        if yt_match and not c.youtube_url:
            c.youtube_url = "https://www." + yt_match.group(0)
            yt_count += 1

        tt_match = re.search(r'tiktok\.com/@[\w.]+', all_text, re.IGNORECASE)
        if tt_match and not c.tiktok_url:
            c.tiktok_url = "https://www." + tt_match.group(0)
            tt_count += 1

    print(f"[Step 2] Extracted from existing data: IG={ig_count}, YT={yt_count}, TT={tt_count}")


def clean_instagram_url(url: str) -> str:
    """Normalize Instagram URL."""
    # Remove tracking params
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")
    return f"https://www.instagram.com{path}"


def clean_youtube_url(url: str) -> str:
    """Normalize YouTube URL."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")
    if not path or path == "/":
        return url.split("?")[0].rstrip("/")
    return f"https://www.youtube.com{path}"


# ---------------------------------------------------------------------------
# Step 3 & 4: Signal Detection & Analysis
# ---------------------------------------------------------------------------

VIDEO_FIRST_STRONG = [
    "youtube", "youtuber", "vlog", "vlogger", "filmmaker", "videographer",
    "video production", "video editor", "video editing", "content creator",
    "content creation", "film production", "cinematograph", "video agency",
    "media production", "video marketing", "video content", "tiktok",
    "video ads", "video tutorial", "film colorist", "podcast production",
    "animated video", "video design",
]

VIDEO_FIRST_MODERATE = [
    "podcast", "podcaster", "film", "media company", "media agency",
    "creative agency", "production company", "streaming", "shorts",
    "reels", "video", "camera", "drone",
]

OPS_SIGNALS = [
    "editor", "editors", "team", "crew", "production team", "video team",
    "staff", "hire", "hiring", "contractor", "freelance", "outsource",
    "multiple formats", "post-production", "post production",
    "behind the scenes", "bts", "workflow", "sop", "process",
]

ARCHIVE_SIGNALS = [
    "years of content", "archive", "library", "catalog", "back catalog",
    "repurpos", "evergreen", "old content", "content library",
    "footage", "b-roll", "raw footage", "hard drive", "storage",
    "terabyte", "tb of", "asset management",
]


def detect_signals(c: Contact) -> dict:
    """Analyze a contact's text fields for video-first and ops signals."""
    all_text = f"{c.bio} {c.context} {c.help_goal} {c.company_url} {c.industry}".lower()

    # Video-first strength
    strong_hits = [kw for kw in VIDEO_FIRST_STRONG if kw in all_text]
    moderate_hits = [kw for kw in VIDEO_FIRST_MODERATE if kw in all_text]

    # Ops signals
    ops_hits = [kw for kw in OPS_SIGNALS if kw in all_text]

    # Archive signals
    archive_hits = [kw for kw in ARCHIVE_SIGNALS if kw in all_text]

    # Check if company URL is a social platform (strong signal)
    url_is_social = any(
        p in c.company_url.lower()
        for p in ["youtube.com", "instagram.com", "tiktok.com"]
    )

    return {
        "strong_video": strong_hits,
        "moderate_video": moderate_hits,
        "ops_signals": ops_hits,
        "archive_signals": archive_hits,
        "url_is_social": url_is_social,
        "is_video_business": is_video_business(c),
    }


def is_video_business(c: Contact) -> bool:
    """Determine if the contact's primary business is video/content."""
    bio_lower = c.bio.lower()
    all_text = f"{bio_lower} {c.company_url.lower()} {c.company.lower()} {c.email.lower()}"
    video_biz_patterns = [
        r"video\s+(production|agency|company|studio|editor|editing|marketing|content|tutorial)",
        r"(film|cinema|media)\s+(production|company|studio|agency)",
        r"youtuber", r"vlogger", r"content\s+creator",
        r"podcast\s+(production|agency|studio|launch)",
        r"videograph", r"cinematograph",
        r"animated?\s+video", r"video\s+ad",
        r"create[sd]?\s+video", r"make[sd]?\s+video",
        r"video\s+for\s+", r"through\s+video",
        r"help.*video", r"vlogs?\s+on\s+youtube",
        r"on\s+youtube\s+(every|weekly|daily)",
    ]
    # Also check company URL/email domain for video-related terms
    domain_patterns = [
        r"video", r"film", r"media", r"studio", r"creative",
        r"production", r"vlog",
    ]
    is_biz = any(re.search(p, bio_lower) for p in video_biz_patterns)
    if not is_biz:
        # Check domain for video business indicators
        domain = urllib.parse.urlparse(c.company_url).netloc.lower()
        email_domain = c.email.split("@")[-1].lower()
        combined = f"{domain} {email_domain}"
        is_biz = any(p in combined for p in domain_patterns)
    return is_biz


# ---------------------------------------------------------------------------
# Step 5: Web Search Enrichment (for high-signal contacts)
# ---------------------------------------------------------------------------

def web_search_enrich(contacts: list[Contact], max_searches: int = 80) -> None:
    """
    Use web search for contacts with strong video signals
    to find additional social accounts and approximate metrics.
    """
    # Prioritize contacts most likely to be video-first
    candidates = []
    for c in contacts:
        signals = detect_signals(c)
        priority = 0
        if signals["url_is_social"]:
            priority += 3
        if signals["is_video_business"]:
            priority += 3
        priority += len(signals["strong_video"]) * 2
        priority += len(signals["moderate_video"])
        if priority >= 3:
            candidates.append((priority, c, signals))

    candidates.sort(key=lambda x: -x[0])
    candidates = candidates[:max_searches]

    print(f"[Step 5] Enriching top {len(candidates)} contacts via web search...")

    for i, (priority, c, signals) in enumerate(candidates):
        if i > 0 and i % 10 == 0:
            print(f"  ... processed {i}/{len(candidates)}")

        search_queries = build_search_queries(c)
        for query in search_queries:
            try:
                result = do_web_search(query)
                if result:
                    parse_search_results(c, result, query)
            except Exception as e:
                c.notes += f"Search error: {str(e)[:50]}; "

        # Small delay between contacts to be respectful
        time.sleep(0.3)

    print(f"[Step 5] Web enrichment complete")


def build_search_queries(c: Contact) -> list[str]:
    """Build targeted search queries for a contact."""
    queries = []
    name_parts = c.name.strip()

    # If we don't have YouTube, search for it
    if not c.youtube_url and name_parts:
        company_hint = ""
        if c.company:
            company_hint = f" {c.company}"
        elif c.company_url and "instagram.com" not in c.company_url.lower():
            # Extract domain as company hint
            parsed = urllib.parse.urlparse(c.company_url)
            domain = parsed.netloc.replace("www.", "")
            if domain:
                company_hint = f" {domain}"
        queries.append(f"{name_parts}{company_hint} YouTube channel")

    # If we don't have Instagram, search for it
    if not c.instagram_url and name_parts:
        queries.append(f"{name_parts} Instagram")

    # If we don't have TikTok, search for it
    if not c.tiktok_url and name_parts:
        queries.append(f"{name_parts} TikTok")

    return queries[:2]  # Limit to 2 queries per contact


def do_web_search(query: str) -> Optional[str]:
    """Execute a web search using subprocess call to web search utility."""
    # We'll use curl to a search API or similar
    # For now, we'll use a basic approach
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        result = subprocess.run(
            ["curl", "-sL", "-A",
             "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
             "--max-time", "10", url],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return None


def parse_search_results(c: Contact, html: str, query: str) -> None:
    """Parse search results HTML to find social URLs."""
    # Extract YouTube URLs
    if "youtube" in query.lower() and not c.youtube_url:
        yt_matches = re.findall(
            r'https?://(?:www\.)?youtube\.com/(?:@|channel/|c/|user/)[\w-]+',
            html
        )
        if yt_matches:
            # Take first non-generic result
            for url in yt_matches:
                if not any(skip in url.lower() for skip in
                          ["/results", "/watch", "/feed", "/playlist"]):
                    c.youtube_url = url
                    c.notes += "YT found via search; "
                    break

    # Extract Instagram URLs
    if "instagram" in query.lower() and not c.instagram_url:
        ig_matches = re.findall(
            r'https?://(?:www\.)?instagram\.com/[\w.]+',
            html
        )
        if ig_matches:
            for url in ig_matches:
                if not any(skip in url.lower() for skip in
                          ["/explore", "/accounts", "/p/", "/reel/"]):
                    c.instagram_url = url
                    c.notes += "IG found via search; "
                    break

    # Extract TikTok URLs
    if "tiktok" in query.lower() and not c.tiktok_url:
        tt_matches = re.findall(
            r'https?://(?:www\.)?tiktok\.com/@[\w.]+',
            html
        )
        if tt_matches:
            c.tiktok_url = tt_matches[0]
            c.notes += "TT found via search; "

    # Look for subscriber/follower counts in snippets
    if c.youtube_url and not c.youtube_subscribers:
        sub_match = re.search(
            r'([\d,.]+[KkMm]?)\s*(?:subscriber|sub)',
            html, re.IGNORECASE
        )
        if sub_match:
            c.youtube_subscribers = sub_match.group(1)
            c.notes += "YT subs from search snippet; "

    if c.instagram_url and not c.instagram_followers:
        fol_match = re.search(
            r'([\d,.]+[KkMm]?)\s*(?:follower)',
            html, re.IGNORECASE
        )
        if fol_match:
            c.instagram_followers = fol_match.group(1)
            c.notes += "IG followers from search snippet; "


# ---------------------------------------------------------------------------
# Step 5b: Apply Manual Enrichment Data
# ---------------------------------------------------------------------------

def apply_manual_enrichment(contacts: list[Contact], enrichment_path: str) -> None:
    """Apply manually researched enrichment data from JSON file."""
    if not os.path.exists(enrichment_path):
        print(f"[Step 5b] No manual enrichment file at {enrichment_path}")
        return

    with open(enrichment_path, "r") as f:
        enrichment = json.load(f)

    applied = 0
    for c in contacts:
        if c.email in enrichment:
            data = enrichment[c.email]
            if data.get("youtube_url") and not c.youtube_url:
                c.youtube_url = data["youtube_url"]
            if data.get("youtube_subscribers"):
                c.youtube_subscribers = data["youtube_subscribers"]
            if data.get("instagram_url") and not c.instagram_url:
                c.instagram_url = data["instagram_url"]
            if data.get("instagram_followers"):
                c.instagram_followers = data["instagram_followers"]
            if data.get("tiktok_url") and not c.tiktok_url:
                c.tiktok_url = data["tiktok_url"]
            if data.get("tiktok_followers"):
                c.tiktok_followers = data["tiktok_followers"]
            if data.get("years_publishing"):
                c.years_publishing = data["years_publishing"]
            if data.get("notes"):
                c.notes = data["notes"]
            applied += 1

    print(f"[Step 5b] Applied manual enrichment to {applied} contacts")


# ---------------------------------------------------------------------------
# Step 6 & 7: ICP Scoring & Classification
# ---------------------------------------------------------------------------

def score_contact(c: Contact) -> None:
    """
    Score a contact against the video-first operator ICP.

    score = audience_score (0-2)
          + cadence_score (0-3)
          + ops_signal_score (0-3)
          + archive_likelihood_score (0-2)

    Penalty: -1 if identity ambiguous
    """
    signals = detect_signals(c)
    notes_parts = []

    # --- Audience Score (0-2) ---
    audience_score = 0
    follower_count = estimate_follower_count(c)

    if follower_count >= 100_000:
        audience_score = 2
        notes_parts.append(f"Audience: {follower_count:,}+ (high)")
    elif follower_count >= 10_000:
        audience_score = 1
        notes_parts.append(f"Audience: {follower_count:,}+ (moderate)")
    elif c.youtube_url or c.instagram_url or c.tiktok_url:
        # Has social presence but unknown size
        if signals["is_video_business"] or len(signals["strong_video"]) >= 2:
            audience_score = 1
            notes_parts.append("Audience: social presence found, size unverified")
        else:
            notes_parts.append("Audience: social present but unverified")
    else:
        notes_parts.append("Audience: no social accounts found")

    # --- Cadence Score (0-3) ---
    cadence_score = 0

    # Infer cadence from signals
    has_yt = bool(c.youtube_url)
    has_ig = bool(c.instagram_url)
    has_tt = bool(c.tiktok_url)
    platform_count = sum([has_yt, has_ig, has_tt])

    # High subscriber count is direct evidence of consistent publishing
    if follower_count >= 500_000:
        cadence_score = 3
        notes_parts.append("Cadence: 500K+ subs proves sustained publishing")
    elif follower_count >= 100_000:
        cadence_score = max(cadence_score, 2)
        notes_parts.append("Cadence: 100K+ subs implies regular publishing")

    if signals["is_video_business"]:
        # Video businesses produce content by definition
        cadence_score = 2
        notes_parts.append("Cadence: video business (assumed regular)")
    elif signals["url_is_social"]:
        # Primary URL is social = active publisher
        cadence_score = 2
        notes_parts.append("Cadence: primary URL is social platform")

    if len(signals["strong_video"]) >= 3:
        cadence_score = max(cadence_score, 3)
        notes_parts.append("Cadence: multiple strong video signals")
    elif len(signals["strong_video"]) >= 1:
        cadence_score = max(cadence_score, 2)
    elif platform_count >= 2:
        cadence_score = max(cadence_score, 1)
        notes_parts.append("Cadence: multi-platform presence")

    # Specific bio keywords that indicate high cadence
    bio_lower = c.bio.lower()
    if any(kw in bio_lower for kw in ["daily", "every day", "weekly", "new video",
                                       "every weekday", "live on youtube"]):
        cadence_score = max(cadence_score, 3)
        notes_parts.append("Cadence: explicit frequency mentioned in bio")
    elif any(kw in bio_lower for kw in ["tutorials", "tutorial", "how-to",
                                         "teaching", "lessons", "course"]):
        if c.youtube_url or "youtube" in bio_lower:
            cadence_score = max(cadence_score, 2)
            notes_parts.append("Cadence: tutorial/education content publisher")

    if c.youtube_cadence:
        notes_parts.append(f"YT cadence: {c.youtube_cadence}")
    if c.instagram_cadence:
        notes_parts.append(f"IG cadence: {c.instagram_cadence}")

    # --- Ops Signal Score (0-3) ---
    ops_score = 0

    if signals["ops_signals"]:
        ops_score = min(len(signals["ops_signals"]), 3)
        notes_parts.append(f"Ops signals: {', '.join(signals['ops_signals'][:5])}")

    # High subs implies operational sophistication (editor, thumbnails, SEO, etc.)
    if follower_count >= 500_000:
        ops_score = max(ops_score, 2)
        notes_parts.append("Ops: 500K+ subs implies production team/workflow")
    elif follower_count >= 100_000:
        ops_score = max(ops_score, 1)
        notes_parts.append("Ops: 100K+ subs implies structured workflow")

    # Multi-platform presence implies ops capacity
    if platform_count >= 2:
        ops_score = max(ops_score, 1)
        notes_parts.append("Ops: multi-platform content distribution")

    # Headcount as ops signal
    headcount_lower = c.headcount.lower()
    if any(h in headcount_lower for h in ["11-25", "25-50", "50+"]):
        ops_score = max(ops_score, 2)
        notes_parts.append(f"Team size: {c.headcount}")
    elif any(h in headcount_lower for h in ["1-10"]):
        ops_score = max(ops_score, 1)

    # Revenue as proxy for ops sophistication
    if c.revenue in ["10m+", "6-10m"]:
        ops_score = max(ops_score, 2)
    elif c.revenue in ["3-6m", "1-3m"]:
        ops_score = max(ops_score, 1)

    # --- Archive Likelihood Score (0-2) ---
    archive_score = 0

    if signals["archive_signals"]:
        archive_score = 2
        notes_parts.append(f"Archive signals: {', '.join(signals['archive_signals'][:3])}")

    # Infer from business type
    if signals["is_video_business"]:
        archive_score = max(archive_score, 2)
        notes_parts.append("Archive: video business (high archive likelihood)")
    elif len(signals["strong_video"]) >= 2:
        archive_score = max(archive_score, 1)
        notes_parts.append("Archive: content creator (moderate likelihood)")

    # YouTube presence is a strong archive signal
    if c.youtube_url:
        archive_score = max(archive_score, 1)
        if not any("Archive" in n for n in notes_parts):
            notes_parts.append("Archive: YouTube channel = content archive")

    # High subscriber count = years of accumulated content = archive pain
    if follower_count >= 100_000:
        archive_score = max(archive_score, 2)
        if not any("archive pain" in n.lower() for n in notes_parts):
            notes_parts.append("Archive: high subs = large content archive, high archive pain likelihood")

    # --- Identity Penalty ---
    penalty = 0
    if is_identity_ambiguous(c):
        penalty = -1
        notes_parts.append("PENALTY: identity ambiguous")

    # --- Final Score ---
    raw_score = audience_score + cadence_score + ops_score + archive_score + penalty
    c.icp_fit_score = max(0, min(10, raw_score))

    # --- Classification ---
    if c.icp_fit_score >= 9:
        c.icp_tier = "Priority"
    elif c.icp_fit_score >= 7:
        c.icp_tier = "Qualified"
    elif c.icp_fit_score >= 4:
        c.icp_tier = "Nurture"
    else:
        c.icp_tier = "Drop"

    # Append scoring notes
    score_detail = (
        f"Score breakdown: audience={audience_score} cadence={cadence_score} "
        f"ops={ops_score} archive={archive_score} penalty={penalty}"
    )
    notes_parts.insert(0, score_detail)
    c.notes = "; ".join(notes_parts) if not c.notes else c.notes + " | " + "; ".join(notes_parts)


def estimate_follower_count(c: Contact) -> int:
    """Try to parse a numeric follower count from available data."""
    for field in [c.youtube_subscribers, c.instagram_followers, c.tiktok_followers]:
        if not field:
            continue
        count = parse_count(field)
        if count > 0:
            return count

    # Check bio for follower mentions
    count_match = re.search(
        r'([\d,.]+)\s*(?:k|K)\+?\s*(?:subscriber|follower|sub)',
        c.bio
    )
    if count_match:
        return parse_count(count_match.group(1) + "K")

    count_match2 = re.search(
        r'([\d,.]+)\s*(?:m|M)\+?\s*(?:subscriber|follower)',
        c.bio
    )
    if count_match2:
        return parse_count(count_match2.group(1) + "M")

    # Direct number mentions like "244,000 men on YouTube"
    # Must be specifically about social/YouTube, not general subscriptions
    count_match3 = re.search(
        r'([\d,]+)\s*(?:youtube\s*subscriber|youtube\s*sub|men on youtube|follower)',
        c.bio, re.IGNORECASE
    )
    if count_match3:
        return parse_count(count_match3.group(1))

    return 0


def parse_count(s: str) -> int:
    """Parse a count string like '244K', '1.2M', '10,000' to int."""
    if not s:
        return 0
    s = s.strip().replace(",", "")
    multiplier = 1
    if s.upper().endswith("K"):
        multiplier = 1000
        s = s[:-1]
    elif s.upper().endswith("M"):
        multiplier = 1_000_000
        s = s[:-1]
    try:
        return int(float(s) * multiplier)
    except ValueError:
        return 0


def is_identity_ambiguous(c: Contact) -> bool:
    """Check if contact identity is uncertain."""
    name_lower = c.name.lower()

    # Single word names with no company
    if len(c.name.split()) <= 1 and not c.company and not c.company_url:
        return True

    # Name matches a common greeting/placeholder
    if name_lower in ["test", "admin", "user", "n/a", "none", ""]:
        return True

    # Email domain mismatch with company (possible fan/impersonator)
    if c.company_url and c.email:
        email_domain = c.email.split("@")[-1].lower()
        url_domain = urllib.parse.urlparse(c.company_url).netloc.replace("www.", "").lower()
        # Generic email providers are fine
        generic = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                   "icloud.com", "me.com", "aol.com", "protonmail.com",
                   "live.com", "msn.com", "mail.com"]
        if email_domain not in generic and url_domain and email_domain != url_domain:
            # Different but could be legit (company vs personal domain)
            pass

    return False


# ---------------------------------------------------------------------------
# Step 8: Output
# ---------------------------------------------------------------------------

OUTPUT_COLUMNS = [
    "contact_id",
    "name",
    "email",
    "company",
    "icp_fit_score",
    "icp_tier",
    "instagram_url",
    "instagram_followers",
    "instagram_cadence",
    "youtube_url",
    "youtube_subscribers",
    "youtube_cadence",
    "tiktok_url",
    "tiktok_followers",
    "tiktok_cadence",
    "years_publishing",
    "notes",
]


def write_output(contacts: list[Contact], output_path: str) -> None:
    """Write enriched contacts to CSV."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for c in contacts:
            row = {col: getattr(c, col, "") for col in OUTPUT_COLUMNS}
            writer.writerow(row)

    print(f"[Step 8] Wrote {len(contacts)} contacts to {output_path}")


def print_summary(contacts: list[Contact]) -> None:
    """Print scoring summary statistics."""
    tiers = {"Priority": 0, "Qualified": 0, "Nurture": 0, "Drop": 0}
    for c in contacts:
        tiers[c.icp_tier] = tiers.get(c.icp_tier, 0) + 1

    print("\n" + "=" * 60)
    print("ICP SCORING SUMMARY")
    print("=" * 60)
    print(f"Total contacts scored: {len(contacts)}")
    print(f"  Priority (9-10): {tiers.get('Priority', 0)}")
    print(f"  Qualified (7-8): {tiers.get('Qualified', 0)}")
    print(f"  Nurture (4-6):   {tiers.get('Nurture', 0)}")
    print(f"  Drop (0-3):      {tiers.get('Drop', 0)}")
    print()

    # List Priority contacts
    priority = [c for c in contacts if c.icp_tier == "Priority"]
    if priority:
        print("PRIORITY CONTACTS:")
        for c in priority:
            print(f"  [{c.icp_fit_score}] {c.name} <{c.email}>")
            if c.youtube_url:
                print(f"       YT: {c.youtube_url}")
            if c.instagram_url:
                print(f"       IG: {c.instagram_url}")
            print()

    # List Qualified contacts
    qualified = [c for c in contacts if c.icp_tier == "Qualified"]
    if qualified:
        print(f"QUALIFIED CONTACTS ({len(qualified)}):")
        for c in qualified[:30]:
            platforms = []
            if c.youtube_url:
                platforms.append("YT")
            if c.instagram_url:
                platforms.append("IG")
            if c.tiktok_url:
                platforms.append("TT")
            plat_str = ",".join(platforms) if platforms else "none found"
            print(f"  [{c.icp_fit_score}] {c.name} <{c.email}> [{plat_str}]")
        if len(qualified) > 30:
            print(f"  ... and {len(qualified) - 30} more")
        print()

    # Validate: check that 7+ scores are legitimately video-first
    high_scores = [c for c in contacts if c.icp_fit_score >= 7]
    if high_scores:
        video_first_count = sum(
            1 for c in high_scores
            if detect_signals(c)["is_video_business"]
            or detect_signals(c)["strong_video"]
            or c.youtube_url
        )
        pct = (video_first_count / len(high_scores)) * 100 if high_scores else 0
        print(f"VALIDATION: {video_first_count}/{len(high_scores)} "
              f"({pct:.0f}%) of 7+ scores have verified video-first signals")
        if pct < 90:
            print("  WARNING: Below 90% target. Review scoring thresholds.")
        else:
            print("  PASS: Meets 90% video-first threshold.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(input_csv: str, output_csv: str, skip_web_search: bool = False):
    """Execute the full enrichment pipeline."""
    print("=" * 60)
    print("CONTACT ENRICHMENT & ICP SCORING PIPELINE")
    print("=" * 60)

    # Step 1: Load & Normalize
    contacts = load_contacts(input_csv)

    # Step 2: Social Account Discovery (from existing data)
    extract_social_from_existing_data(contacts)

    # Step 3-5: Web Search Enrichment (for high-signal contacts)
    if not skip_web_search:
        web_search_enrich(contacts, max_searches=80)
    else:
        print("[Step 5] Web search skipped (--no-web-search flag)")

    # Step 5b: Apply manual enrichment
    enrichment_path = os.path.join(os.path.dirname(output_csv), "manual_enrichment.json")
    apply_manual_enrichment(contacts, enrichment_path)

    # Step 6-7: Score & Classify
    print("[Step 6-7] Scoring contacts...")
    for c in contacts:
        score_contact(c)

    # Step 8: Output
    write_output(contacts, output_csv)

    # Summary
    print_summary(contacts)

    return contacts


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Contact Enrichment Pipeline")
    parser.add_argument("--input", default="/tmp/contacts_raw.csv",
                        help="Input CSV path")
    parser.add_argument("--output", default="/home/user/mythos/enriched_contacts_scored.csv",
                        help="Output CSV path")
    parser.add_argument("--no-web-search", action="store_true",
                        help="Skip web search enrichment")
    args = parser.parse_args()

    run_pipeline(args.input, args.output, skip_web_search=args.no_web_search)
