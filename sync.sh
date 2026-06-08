#!/bin/bash
set -e

# Configuration
VAULT_PATH="/Users/leoclaw/LeoObisidian_Macmini/Sources/Get"
STATE_FILE="state/last_sync.json"
LOG_FILE="logs/sync.log"
SINCE_DATE="2026-03-21"

# API Config
API_KEY="$GETNOTE_API_KEY"
CLIENT_ID="$GETNOTE_CLIENT_ID"
BASE_URL="https://openapi.biji.com/open/api/v1/resource/note"

# Ensure directories exist
mkdir -p "$(dirname "$VAULT_PATH")"
mkdir -p "$(dirname "$STATE_FILE")"
mkdir -p "$(dirname "$LOG_FILE")"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Load last sync state
load_state() {
    if [ -f "$STATE_FILE" ]; then
        LAST_SYNC_TIME=$(cat "$STATE_FILE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('last_sync_time',''))" 2>/dev/null || echo "")
        LAST_NOTE_ID=$(cat "$STATE_FILE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('last_note_id',''))" 2>/dev/null || echo "")
    else
        LAST_SYNC_TIME=""
        LAST_NOTE_ID=""
    fi
}

# Save sync state
save_state() {
    echo "{\"last_sync_time\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"last_note_id\":\"$1\",\"notes_synced\":$2}" > "$STATE_FILE"
}

# Fetch notes with pagination
fetch_notes() {
    local cursor="$1"
    local url="${BASE_URL}/list?page_size=100"
    if [ -n "$cursor" ]; then
        url="${url}&cursor=${cursor}"
    fi

    curl -s -X GET "$url" \
        -H "Authorization: Bearer $API_KEY" \
        -H "X-Client-ID: $CLIENT_ID"
}

# Process notes via Python
process_notes_python() {
    python3 << 'PYEOF'
import json, sys, re, os
from datetime import datetime
import time

data = json.load(sys.stdin)
notes = data.get('data', {}).get('notes', [])
next_cursor = data.get('data', {}).get('next_cursor', '')

vault_path = os.environ.get('VAULT_PATH', '.')
since_date = os.environ.get('SINCE_DATE', '2026-03-21')

since_ts = None
try:
    since_dt = datetime.strptime(since_date, '%Y-%m-%d')
    since_ts = int(since_dt.timestamp())
except:
    since_ts = 0

def sanitize(s):
    if not s: return ''
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)
    return s.strip()

def safe_filename(s, max_len=80):
    s = sanitize(s)
    s = re.sub(r'[<>:"/\\|]', '_', s)
    s = re.sub(r'\s+', '_', s)
    return s[:max_len] if s else 'untitled'

now_ts = int(time.time())
written_count = 0

for note in notes:
    note_id = str(note.get('note_id', ''))
    title = sanitize(note.get('title', '')) or 'Untitled'
    content = note.get('content', '')
    created_str = note.get('created', '') or ''
    updated_str = note.get('updated', '') or ''

    # Parse created time if available, otherwise use current time
    created_ts = now_ts
    if created_str:
        try:
            dt = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
            created_ts = int(dt.timestamp())
        except:
            pass

    # Filter by date - skip if before SINCE_DATE
    if since_ts and created_ts < since_ts:
        print(f'SKIP_OLD:{note_id}:{title[:30]}')
        continue

    # Generate filename with current timestamp (since API doesn't provide created)
    date_str = datetime.fromtimestamp(created_ts).strftime('%Y-%m-%d_%H-%M')
    safe_title = safe_filename(title)
    filename = f'{date_str}_{safe_title}.md'
    full_path = os.path.join(vault_path, filename)

    # Write markdown file
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write('---\n')
        f.write(f'source: get\n')
        f.write(f'created: {created_str or "unknown"}\n')
        f.write(f'updated: {updated_str or "unknown"}\n')
        f.write(f'get_note_id: {note_id}\n')
        f.write('---\n\n')
        f.write(f'# {title}\n\n')
        f.write(content)

    print(f'WRITE:{note_id}:{os.path.basename(full_path)}')
    written_count += 1

print(f'NEXT_CURSOR:{next_cursor}')
print(f'WRITTEN_COUNT:{written_count}')
PYEOF
}

# Main sync loop
main() {
    log "=== Starting Get to Obsidian Sync ==="
    load_state

    log "Last sync: $LAST_SYNC_TIME, Last note: $LAST_NOTE_ID"
    log "Filtering notes since: $SINCE_DATE"

    export VAULT_PATH
    export SINCE_DATE

    total_fetched=0
    total_written=0
    total_skipped=0
    cursor=""

    while true; do
        log "Fetching notes (page_size=100)..."
        response=$(fetch_notes "$cursor")

        if [ -z "$response" ] || [ "$(echo "$response" | head -c 10)" = "null" ]; then
            log "Empty response, rate limited. Waiting 10s..."
            sleep 10
            continue
        fi

        if echo "$response" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('success') else 1)" 2>/dev/null; then
            export VAULT_PATH
            export SINCE_DATE
            result=$(echo "$response" | process_notes_python)

            writes=$(echo "$result" | grep '^WRITE:' | wc -l | tr -d ' ')
            skips=$(echo "$result" | grep '^SKIP_OLD:' | wc -l | tr -d ' ')
            cursor=$(echo "$result" | grep '^NEXT_CURSOR:' | head -1 | cut -d: -f2)
            page_written=$(echo "$result" | grep '^WRITTEN_COUNT:' | head -1 | cut -d: -f2)

            total_fetched=$((total_fetched + writes + skips))
            total_written=$((total_written + writes))
            total_skipped=$((total_skipped + skips))

            log "Page results: Written=$writes, Skipped_old=$skips"

            if [ -z "$cursor" ] || [ "$cursor" = "None" ] || [ "$cursor" = "" ]; then
                log "No next_cursor, sync complete."
                break
            fi

            # Safety limit
            if [ $total_fetched -gt 1000 ]; then
                log "Safety limit (1000 notes) reached"
                break
            fi

            # Small delay to avoid rate limit
            sleep 0.5
        else
            error_code=$(echo "$response" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('error',{}).get('code','?'))" 2>/dev/null)
            log "API error code: $error_code"
            if echo "$response" | grep -q "qps_bucket_exceeded"; then
                log "Rate limited, waiting 5s..."
                sleep 5
                continue
            fi
            break
        fi
    done

    log "=== Sync Complete ==="
    log "Total fetched: $total_fetched"
    log "Total written: $total_written"
    log "Total skipped (old): $total_skipped"

    # Save state
    save_state "last_note_$total_written" "$total_written"

    echo ""
    echo "=== DONE ==="
    echo "Written: $total_written notes to $VAULT_PATH"
    echo "Log: $LOG_FILE"
}

main "$@"