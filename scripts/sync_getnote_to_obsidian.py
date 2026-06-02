#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
得到大脑 -> Obsidian Raw Layer 增量同步脚本

唯一合法执行入口（相对于 project root）：
    scripts/sync_getnote_to_obsidian.py

治理规则见：PROJECT_CONVENTIONS.md

标题生成流程：
    无标题笔记 → 调用 DeepSeek API 自动生成语义标题 → 创建文件
    文件只创建一次，创建时标题已是最终值，符合 create once, never mutate 原则。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# ── 配置常量 ──────────────────────────────────────────────────────────────────

SYNC_START_DATE = dt.date(2026, 3, 21)

API_BASE = "https://openapi.biji.com/open/api/v1"
API_KEY = os.environ.get("GETNOTE_API_KEY", "")
CLIENT_ID = os.environ.get("GETNOTE_CLIENT_ID", "")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

OBSIDIAN_OUTPUT_DIR = Path("/Users/leoclaw/LeoObisidian_Macmini/00 Sources/GetNote")

PROJECT_ROOT = Path(__file__).parent.parent
SYNC_STATE_FILE = PROJECT_ROOT / "sync_state.json"

ILLEGAL_FILENAME_CHARS = r'\/:*?"<>|'
ILLEGAL_TAG_CHARS_RE = re.compile(r'[\/\\:\*\?"<>\|]')

RETRY_WAIT_SECONDS = 60
MAX_RETRIES = 5

# ── 日志 ──────────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    print(msg, flush=True)

def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)

# ── 得到大脑 API ──────────────────────────────────────────────────────────────

def api_headers() -> dict[str, str]:
    if not API_KEY or not CLIENT_ID:
        fail("环境变量 GETNOTE_API_KEY 或 GETNOTE_CLIENT_ID 未设置")
    return {
        "Authorization": API_KEY,
        "X-Client-ID": CLIENT_ID,
        "Accept": "application/json",
    }


def api_get_with_retry(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    url = f"{API_BASE}{path}?{qs}"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=api_headers(), method="GET")
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body)
            if not data.get("success"):
                fail(f"API 错误: {data}")
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if attempt < MAX_RETRIES:
                    log(f"  429 限流，等待 {RETRY_WAIT_SECONDS}s 后重试（第 {attempt}/{MAX_RETRIES} 次）...")
                    time.sleep(RETRY_WAIT_SECONDS)
                else:
                    fail(f"429 限流，已重试 {MAX_RETRIES} 次，放弃。")
            else:
                raise

# ── DeepSeek 标题生成 ─────────────────────────────────────────────────────────

def strip_noise(content: str) -> str:
    lines = []
    for line in content.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.fullmatch(r"(#\S+\s*)+", s):
            continue
        if re.fullmatch(r"!\[[^\]]*\]\([^)]+\)", s):
            continue
        if s in {"TODO", "todo", "- [ ]", "[ ]"}:
            continue
        s = re.sub(r"^(#\S+\s+)+", "", s).strip()
        if s:
            lines.append(s)
    return "\n".join(lines).strip()


def generate_title_with_deepseek(content: str) -> str | None:
    if not DEEPSEEK_API_KEY:
        return None

    meaningful = strip_noise(content)
    if not meaningful:
        return None

    prompt = (
        "你是一个笔记归档助手。请为以下笔记生成一个简洁的中文标题。\n"
        "要求：\n"
        "- 基于全文语义理解，不要机械截取第一句\n"
        "- 不要使用 hashtag 作为标题\n"
        "- 只返回标题本身，不加引号、不加解释、不加标点\n"
        "- 控制在 20 字以内\n\n"
        f"笔记内容：\n{meaningful[:1000]}"
    )

    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 60,
        "temperature": 0.3,
    }).encode("utf-8")

    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        title = result["choices"][0]["message"]["content"].strip()
        title = title.strip("「」『』""\"'` \n")
        return title if title else None
    except Exception as e:
        log(f"  DeepSeek 标题生成失败: {e}")
        return None

# ── 同步状态 ──────────────────────────────────────────────────────────────────

def load_sync_state() -> dict:
    if SYNC_STATE_FILE.exists():
        return json.loads(SYNC_STATE_FILE.read_text(encoding="utf-8"))
    return {"latest_synced_id": "0"}


def save_sync_state(state: dict) -> None:
    SYNC_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

# ── 日期过滤 ──────────────────────────────────────────────────────────────────

def parse_datetime(value: str) -> dt.datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None


def is_after_start_date(created_at: str) -> bool:
    parsed = parse_datetime(created_at)
    if parsed is None:
        return False
    return parsed.date() >= SYNC_START_DATE

# ── 标题 & 文件名 ─────────────────────────────────────────────────────────────

def sanitize_title(title: str) -> str:
    title = title.strip()
    title = re.sub(r"\s+", " ", title)
    title = "".join(ch for ch in title if ch not in ILLEGAL_FILENAME_CHARS)
    title = title.strip(". ")
    return title[:80] if title else "Untitled"


def resolve_title(note: dict) -> str:
    raw_title = (note.get("title") or "").strip()
    if raw_title:
        return sanitize_title(raw_title)

    content = note.get("content") or ""
    generated = generate_title_with_deepseek(content)
    if generated:
        return sanitize_title(generated)

    # 兜底：用 note id，极少触发（DeepSeek 不可用时）
    return f"GetNote_{note['id']}"


def build_filename(created_at: str, title: str) -> str:
    parsed = parse_datetime(created_at)
    stamp = parsed.strftime("%Y-%m-%d %H-%M") if parsed else "0000-00-00 00-00"
    name = f"{stamp} {title}.md"
    name = "".join(ch for ch in name if ch not in ILLEGAL_FILENAME_CHARS)
    return re.sub(r"\s+", " ", name).strip()

# ── 标签 ──────────────────────────────────────────────────────────────────────

def normalize_tag(tag: str) -> str:
    tag = tag.strip().lstrip("#")
    tag = tag.replace(" ", "_")
    tag = ILLEGAL_TAG_CHARS_RE.sub("", tag)
    return tag.strip("_")


def collect_tags(note: dict) -> list[str]:
    tags: list[str] = []
    for t in note.get("tags") or []:
        name = t.get("name") if isinstance(t, dict) else str(t)
        normalized = normalize_tag(str(name or ""))
        if normalized and normalized not in tags:
            tags.append(normalized)
    content = note.get("content") or ""
    for match in re.finditer(r"(?<!\w)\\?#([^\s#，。！？；；、,\.\!\?\)\]\}]+)", content):
        normalized = normalize_tag(match.group(1))
        if normalized and normalized not in tags:
            tags.append(normalized)
    return tags

# ── 文件写入 ──────────────────────────────────────────────────────────────────

def render_frontmatter(note: dict, tags: list[str]) -> str:
    created = (note.get("created_at") or "")[:19]
    note_id = note["id"]
    if tags:
        tags_yaml = "\n".join(f"  - {t}" for t in tags)
        tags_block = f"tags:\n{tags_yaml}"
    else:
        tags_block = "tags:"
    return (
        "---\n"
        "source: get\n"
        f"created: {created}\n"
        f"get_note_id: {note_id}\n"
        "noteType: RawGet\n"
        f"{tags_block}\n"
        "---\n"
    )


def note_already_synced(note_id: str) -> bool:
    if not OBSIDIAN_OUTPUT_DIR.exists():
        return False
    needle = f"get_note_id: {note_id}"
    for path in OBSIDIAN_OUTPUT_DIR.glob("*.md"):
        try:
            if needle in path.read_text(encoding="utf-8", errors="ignore")[:1024]:
                return True
        except OSError:
            continue
    return False


def write_note(note: dict) -> str:
    note_id = str(note["id"])

    if note_already_synced(note_id):
        return f"SKIP  already synced  id={note_id}"

    title = resolve_title(note)
    filename = build_filename(note.get("created_at", ""), title)
    target = OBSIDIAN_OUTPUT_DIR / filename

    if target.exists():
        return f"SKIP  filename exists  id={note_id}  file={filename}"

    tags = collect_tags(note)
    content = (note.get("content") or "").rstrip()
    markdown = render_frontmatter(note, tags) + "\n" + content + "\n"

    OBSIDIAN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as f:
        f.write(markdown)

    return f"CREATED  id={note_id}  file={filename}"

# ── 主流程 ────────────────────────────────────────────────────────────────────

def main() -> None:
    log(f"同步目标目录: {OBSIDIAN_OUTPUT_DIR}")
    log(f"起始日期过滤: {SYNC_START_DATE}")

    state = load_sync_state()
    latest_synced_id = state.get("latest_synced_id", "0")
    log(f"上次最新已同步 id: {latest_synced_id}")

    cursor = "0"
    newest_id_this_run = None
    reached_stop = False
    created = skipped = failed = 0

    while True:
        log(f"  拉取列表 since_id={cursor} ...")
        data = api_get_with_retry("/resource/note/list", {"since_id": cursor})

        notes = data["data"]["notes"]
        has_more = data["data"].get("has_more", False)
        next_cursor = str(data["data"].get("next_cursor", cursor))

        for note_summary in notes:
            note_id = str(note_summary["id"])
            created_at = note_summary.get("created_at", "")

            if newest_id_this_run is None:
                newest_id_this_run = note_id

            if note_id == latest_synced_id:
                reached_stop = True
                break

            if not is_after_start_date(created_at):
                continue

            try:
                result = write_note(note_summary)
                log(f"  {result}")
                if result.startswith("CREATED"):
                    created += 1
                else:
                    skipped += 1
            except Exception as e:
                log(f"  FAILED  id={note_id}  err={e}")
                failed += 1

        if reached_stop or not has_more:
            break

        if next_cursor and next_cursor != cursor:
            cursor = next_cursor
        else:
            break

    # 更新 latest_synced_id
    if newest_id_this_run and newest_id_this_run != latest_synced_id:
        state["latest_synced_id"] = newest_id_this_run
        save_sync_state(state)

    log(f"\n同步完成。created={created}  skipped={skipped}  failed={failed}")

    if failed > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
