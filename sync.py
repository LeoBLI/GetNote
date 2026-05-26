#!/usr/bin/env python3
import os
import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path

VAULT_PATH = Path("/Users/leoclaw/LeoObisidian_Macmini/Sources/Get")
ATTACHMENTS_PATH = Path("/Users/leoclaw/LeoObisidian_Macmini/Sources/Get/get_attachment")
STATE_FILE = Path("state/last_sync.json")
LOG_FILE = Path("logs/sync.log")
SINCE_DATE = "2026-03-21"

API_KEY = os.environ.get("GETNOTE_API_KEY", "")
CLIENT_ID = os.environ.get("GETNOTE_CLIENT_ID", "")
BASE_URL = "https://openapi.biji.com/open/api/v1/resource/note"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def sanitize(s):
    if not s: return ""
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    return s.strip()

def safe_filename(s, max_len=80):
    s = sanitize(s)
    s = re.sub(r'[<>:"/\\|]', "_", s)
    s = re.sub(r"\s+", "_", s)
    return s[:max_len] if s else "untitled"

def normalize_tag(tag):
    tag = tag.lstrip('#')
    tag = re.sub(r'[<>:"/\\|?]', '', tag)
    tag = tag.replace(' ', '-')
    tag = re.sub(r'-+', '-', tag)
    return tag.strip('-')

def get_note_detail(note_id, retries=3):
    url = f"{BASE_URL}/detail?id={note_id}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("X-Client-ID", CLIENT_ID)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                if data.get("success"):
                    return data.get("data", {}).get("note", {})
                return None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                log(f"    HTTP 429, waiting 10s...")
                time.sleep(10)
                continue
            return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
    return None

def download_attachment(url, dest_path, retries=2):
    if dest_path.exists():
        return True
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                dest_path.write_bytes(resp.read())
            return True
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
    return False

def process_content(content, note_id, attachments_path):
    result = content

    def replace_img(match):
        url = match.group(2).replace('%2F', '/')
        url_path = re.search(r'([^/]+\.(?:jpg|jpeg|png|gif|webp))', url)
        if url_path:
            filename = re.sub(r'[?&#].*', '', url_path.group(1))
            filename = f"{note_id}_{filename}"
            local_path = attachments_path / filename
            if download_attachment(url, local_path):
                return f"![](.attachments/{filename})"
        return match.group(0)

    result = re.sub(r'!\[(.*?)\]\((https://get-notes[^\)]+)\)', replace_img, result)

    def replace_audio(match):
        url = match.group(0)
        url_path = re.search(r'([^/]+\.(?:mp3|m4a|wav|aac))', url)
        if url_path:
            filename = f"{note_id}_{url_path.group(1)}"
            local_path = attachments_path / filename
            if download_attachment(url, local_path):
                return f"[audio](.attachments/{filename})"
        return match.group(0)

    result = re.sub(r'https://get-notes[^\s]+\.(?:mp3|m4a|wav|aac)', replace_audio, result)
    return result

def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"]:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            pass
    return None

def fetch_notes(cursor=""):
    url = f"{BASE_URL}/list?page_size=100"
    if cursor:
        url += f"&cursor={cursor}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("X-Client-ID", CLIENT_ID)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")

def main():
    VAULT_PATH.mkdir(parents=True, exist_ok=True)
    ATTACHMENTS_PATH.mkdir(parents=True, exist_ok=True)

    log("=== Starting Get to Obsidian Sync ===")

    since_dt = datetime.strptime(SINCE_DATE, "%Y-%m-%d")
    since_ts = int(since_dt.timestamp())
    log(f"Filtering notes since {SINCE_DATE}")

    # Phase 1: Collect note_ids from list API
    cursor = ""
    page = 0
    will_sync_ids = []
    too_old = 0
    no_date = 0

    log("Phase 1: Collecting notes...")

    while True:
        page += 1
        try:
            response = fetch_notes(cursor)
        except Exception as e:
            log(f"List error: {e}")
            break

        if not response or response.strip() == "null":
            break

        try:
            data = json.loads(response)
        except:
            break

        if not data.get("success"):
            break

        notes = data.get("data", {}).get("notes", [])
        next_cursor = data.get("data", {}).get("next_cursor", "")

        for note in notes:
            note_id = str(note.get("note_id", ""))
            created_str = note.get("created_at") or note.get("created")
            created_at = parse_date(created_str) if created_str else None

            if not created_at:
                no_date += 1
                continue

            note_ts = int(created_at.timestamp())
            if note_ts >= since_ts:
                will_sync_ids.append(note_id)
            else:
                too_old += 1

        if page % 20 == 0:
            log(f"  Page {page}: will_sync={len(will_sync_ids)}, too_old={too_old}")

        if not next_cursor or next_cursor == "None" or next_cursor == "":
            break
        if page > 300:
            break

        cursor = next_cursor
        time.sleep(0.2)

    log(f"Phase 1 complete: {len(will_sync_ids)} notes to sync, {too_old} too old, {no_date} no date")

    # Phase 2: Process each note
    log("Phase 2: Processing notes...")

    total_written = 0
    total_skipped = 0
    total_errors = 0
    total_attachments = 0

    for i, note_id in enumerate(will_sync_ids):
        # Check if already synced (by note_id in filename)
        existing = list(VAULT_PATH.glob(f"*_{note_id}.md"))
        if existing:
            total_skipped += 1
            continue

        if i % 50 == 0:
            log(f"  Progress: {i}/{len(will_sync_ids)}, written={total_written}")

        detail = get_note_detail(note_id)
        if not detail:
            total_errors += 1
            continue

        created_str = detail.get("created_at") or detail.get("created")
        created_at = parse_date(created_str)
        if not created_at:
            total_errors += 1
            continue

        title = sanitize(detail.get("title", "") or "Untitled")
        content = detail.get("content", "") or ""

        api_tags = detail.get("tags", []) or []
        if api_tags and isinstance(api_tags[0], dict):
            tags = [t.get("name", "") or t.get("tag", "") for t in api_tags if t]
        else:
            tags = [str(t) for t in api_tags]

        content_tags = re.findall(r'(?<![#\w])#([^\s#]+)', content)
        all_tags = [str(t) for t in tags + content_tags if t]
        tags = list(set([normalize_tag(t) for t in all_tags]))[:20]

        content_clean = re.sub(r'(?<![#\w])#[^\s#]+', '', content).strip()
        processed_content = process_content(content_clean, note_id, ATTACHMENTS_PATH)

        local_imgs = re.findall(r'!\[\.\.attachments\/([^\)]+)\]', processed_content)
        total_attachments += len(local_imgs)

        date_str = created_at.strftime("%Y-%m-%d_%H-%M")
        safe_title = safe_filename(title) if title != "Untitled" else f"note_{note_id[-8:]}"
        filename = f"{date_str}_{safe_title}.md"
        full_path = VAULT_PATH / filename

        tags_yaml = ""
        if tags:
            tags_yaml = "\ntags:\n" + "\n".join([f"  - {t}" for t in tags])

        md = f"""---
source: get
created: {created_at.isoformat()}
updated: {created_at.isoformat()}
get_note_id: {note_id}{tags_yaml}
---

# {title}

{processed_content}"""

        try:
            full_path.write_text(md, encoding="utf-8")
            total_written += 1
        except Exception as e:
            log(f"  Error writing {filename}: {e}")
            total_errors += 1

        time.sleep(0.3)

    log("=== Done ===")
    log(f"Written: {total_written}, Skipped: {total_skipped}, Errors: {total_errors}, Attachments: {total_attachments}")

if __name__ == "__main__":
    main()