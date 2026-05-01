"""
Obsidian Notion Bridge - Step 3: Fix Images
=============================================
Re-reads original Obsidian .md files, swaps image references
with Google Drive URLs, and rewrites each Notion page via the API.

Features:
- Retry logic with exponential backoff for rate limiting
- Resume support — saves progress, re-run to continue
- Preserves child pages during content replacement

Prerequisites:
- Notion import already done (Step 1)
- gdrive_map.json created (Step 2)
- Notion integration connected to your pages
"""

import os
import re
import sys
import json
import time
import urllib.parse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── CONFIGURATION ──────────────────────────────────────────────
NOTION_API_KEY = "YOUR_NOTION_INTEGRATION_SECRET_HERE"
VAULT_PATH = r"C:\Obsidian\MAIN"
GDRIVE_MAP_FILE = r"C:\Obsidian\gdrive_map.json"
ATTACHMENTS_FOLDER = "Files and Links"
NOTION_ROOT_PAGE_ID = "YOUR_ROOT_PAGE_ID_HERE"
PROGRESS_FILE = r"C:\Obsidian\migration_progress.json"
# ───────────────────────────────────────────────────────────────

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def get_session():
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "PATCH", "DELETE", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION = get_session()


def notion_headers():
    return {
        "Authorization": "Bearer " + NOTION_API_KEY,
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def notion_request(method, url, **kwargs):
    for attempt in range(5):
        try:
            resp = SESSION.request(method, url, headers=notion_headers(), **kwargs)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                print(f"      Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            return resp
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            wait = 2 ** (attempt + 1)
            print(f"      Connection error, retrying in {wait}s...")
            time.sleep(wait)
    return None


def load_gdrive_map():
    with open(GDRIVE_MAP_FILE, "r") as f:
        return json.load(f)


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_progress(done):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(list(done), f)


# ── Markdown Conversion ───────────────────────────────────────

def convert_obsidian_md(content, gdrive_map):
    fixed = 0
    missing = []

    def replace_wiki(match):
        nonlocal fixed
        parts = match.group(1).split("|")
        filename = parts[0].strip()
        if filename in gdrive_map:
            fixed += 1
            return "![](" + gdrive_map[filename] + ")"
        missing.append(filename)
        return ""

    content = re.sub(r"!\[\[([^\]]+)\]\]", replace_wiki, content)

    def replace_md(match):
        nonlocal fixed
        path = urllib.parse.unquote(match.group(2))
        filename = os.path.basename(path)
        if filename in gdrive_map:
            fixed += 1
            return "![](" + gdrive_map[filename] + ")"
        missing.append(filename)
        return ""

    content = re.sub(
        r"!\[([^\]]*)\]\(([^)]+\.(?:png|jpg|jpeg|gif|svg|webp|bmp))\)",
        replace_md, content, flags=re.IGNORECASE,
    )

    def replace_link(match):
        parts = match.group(1).split("|")
        display = parts[1].strip() if len(parts) > 1 else parts[0].strip()
        return "**" + re.sub(r"\.md$", "", display) + "**"

    content = re.sub(r"(?<!!)\[\[([^\]]+)\]\]", replace_link, content)
    content = re.sub(r"%%.*?%%", "", content, flags=re.DOTALL)

    def replace_callout(match):
        ctype = match.group(1).strip().title()
        title = match.group(2).strip() if match.group(2) else ""
        return "> **" + ctype + ":** " + title if title else "> **" + ctype + "**"

    content = re.sub(r">\s*\[!(\w+)\]\s*(.*)", replace_callout, content)

    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].lstrip("\n")

    content = re.sub(r"\n{4,}", "\n\n\n", content)
    return content, fixed, missing


# ── Notion Page Discovery ─────────────────────────────────────

def get_child_pages(page_id):
    pages = []
    cursor = None
    while True:
        url = NOTION_API_URL + "/blocks/" + page_id + "/children"
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        resp = notion_request("GET", url, params=params)
        if not resp or resp.status_code != 200:
            break
        data = resp.json()
        for block in data.get("results", []):
            if block["type"] == "child_page":
                pages.append({"id": block["id"], "title": block["child_page"]["title"]})
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        time.sleep(0.4)
    return pages


def get_all_pages(page_id, depth=0):
    pages = []
    for child in get_child_pages(page_id):
        print("  " + "  " * depth + child["title"])
        pages.append(child)
        pages.extend(get_all_pages(child["id"], depth + 1))
        time.sleep(0.4)
    return pages


# ── File Index ────────────────────────────────────────────────

def build_file_index(vault_path, attachments_folder):
    index = {}
    for root, dirs, files in os.walk(vault_path):
        if attachments_folder in root:
            continue
        for f in files:
            if f.endswith(".md"):
                index[f[:-3].lower()] = os.path.join(root, f)
    return index


# ── Markdown to Notion Blocks ─────────────────────────────────

def rich_text(text):
    if len(text) > 2000:
        text = text[:2000]
    return [{"type": "text", "text": {"content": text}}]


def md_to_blocks(md):
    blocks = []
    lines = md.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        # Code block
        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip() or "plain text"
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            text = "\n".join(code)
            if len(text) > 2000:
                text = text[:2000]
            blocks.append({"object": "block", "type": "code",
                           "code": {"rich_text": rich_text(text), "language": lang}})
            continue

        # Image
        img = re.match(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$", line)
        if img and img.group(2).startswith("http"):
            blocks.append({"object": "block", "type": "image",
                           "image": {"type": "external", "external": {"url": img.group(2)}}})
            i += 1
            continue

        # Heading
        h = re.match(r"^(#{1,3})\s+(.+)$", line)
        if h:
            level = len(h.group(1))
            htype = "heading_" + str(level)
            blocks.append({"object": "block", "type": htype,
                           htype: {"rich_text": rich_text(h.group(2).strip())}})
            i += 1
            continue

        # Bullet
        if re.match(r"^[-*]\s+", line):
            text = re.sub(r"^[-*]\s+", "", line).strip()
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": rich_text(text)}})
            i += 1
            continue

        # Numbered
        n = re.match(r"^\d+\.\s+(.+)", line)
        if n:
            blocks.append({"object": "block", "type": "numbered_list_item",
                           "numbered_list_item": {"rich_text": rich_text(n.group(1).strip())}})
            i += 1
            continue

        # Quote
        if line.startswith(">"):
            blocks.append({"object": "block", "type": "quote",
                           "quote": {"rich_text": rich_text(line.lstrip(">").strip())}})
            i += 1
            continue

        # Divider
        if re.match(r"^---+\s*$", line):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # Table rows -> paragraphs
        if line.strip().startswith("|"):
            while i < len(lines) and lines[i].strip().startswith("|"):
                tl = lines[i].strip()
                i += 1
                if re.match(r"^\|[-\s|:]+\|$", tl):
                    continue
                text = tl.strip("|").strip()
                if text:
                    blocks.append({"object": "block", "type": "paragraph",
                                   "paragraph": {"rich_text": rich_text(text)}})
            continue

        # Paragraph
        text = line.strip()
        if text:
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": rich_text(text)}})
        i += 1

    return blocks


# ── Replace Page Content ──────────────────────────────────────

def replace_page(page_id, markdown):
    # Delete existing blocks (preserve child pages)
    while True:
        url = NOTION_API_URL + "/blocks/" + page_id + "/children"
        resp = notion_request("GET", url, params={"page_size": 100})
        if not resp or resp.status_code != 200:
            break
        data = resp.json()
        results = data.get("results", [])
        if not results:
            break

        deleted_any = False
        for block in results:
            if block["type"] in ("child_page", "child_database"):
                continue
            notion_request("DELETE", NOTION_API_URL + "/blocks/" + block["id"])
            deleted_any = True
            time.sleep(0.35)

        if not deleted_any or not data.get("has_more"):
            break

    time.sleep(0.5)

    # Append new blocks
    blocks = md_to_blocks(markdown)
    url = NOTION_API_URL + "/blocks/" + page_id + "/children"
    appended = 0

    for i in range(0, len(blocks), 100):
        batch = blocks[i:i + 100]
        resp = notion_request("PATCH", url, json={"children": batch})
        if resp and resp.status_code == 200:
            appended += len(batch)
        else:
            for block in batch:
                r = notion_request("PATCH", url, json={"children": [block]})
                if r and r.status_code == 200:
                    appended += 1
                time.sleep(0.35)
        time.sleep(0.5)

    return appended


# ── Main ──────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Obsidian Notion Bridge - Step 3: Fix Images")
    print("=" * 60)

    if "YOUR_" in NOTION_API_KEY or "YOUR_" in NOTION_ROOT_PAGE_ID:
        print("\n  Fill in NOTION_API_KEY and NOTION_ROOT_PAGE_ID!")
        sys.exit(1)

    print("\n  Loading Google Drive mapping...")
    gdrive_map = load_gdrive_map()
    print("  " + str(len(gdrive_map)) + " files mapped")

    print("\n  Indexing vault...")
    file_index = build_file_index(VAULT_PATH, ATTACHMENTS_FOLDER)
    print("  " + str(len(file_index)) + " markdown files")

    done = load_progress()
    if done:
        print("  Resuming — " + str(len(done)) + " pages already done")

    print("\n  Finding Notion pages...")
    pages = get_all_pages(NOTION_ROOT_PAGE_ID)
    print("\n  " + str(len(pages)) + " pages found")

    print("\n  Processing...\n")
    total_fixed = 0
    total_missing = 0
    updated = 0
    skipped = 0

    for i, page in enumerate(pages):
        title = page["title"]
        pid = page["id"]
        print("\n[" + str(i + 1) + "/" + str(len(pages)) + "] " + title)

        if pid in done:
            print("    Already done")
            skipped += 1
            continue

        if title.lower() not in file_index:
            print("    Skip: no .md file")
            skipped += 1
            done.add(pid)
            continue

        try:
            with open(file_index[title.lower()], "r", encoding="utf-8") as f:
                md = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_index[title.lower()], "r", encoding="latin-1") as f:
                    md = f.read()
            except Exception as e:
                print("    Skip: " + str(e))
                skipped += 1
                done.add(pid)
                continue

        converted, fixed, missing = convert_obsidian_md(md, gdrive_map)

        if fixed == 0:
            print("    Skip: no images")
            skipped += 1
            done.add(pid)
            save_progress(done)
            continue

        print("    Rewriting with " + str(fixed) + " images...")
        try:
            n = replace_page(pid, converted)
            total_fixed += fixed
            total_missing += len(missing)
            updated += 1
            if missing:
                print("    Warning: " + str(len(missing)) + " missing")
            print("    Done (" + str(n) + " blocks)")
            done.add(pid)
            save_progress(done)
        except Exception as e:
            print("    ERROR: " + str(e))
            save_progress(done)

        time.sleep(1)

    print("\n" + "=" * 60)
    print("  DONE!")
    print("=" * 60)
    print("  Pages:   " + str(len(pages)))
    print("  Updated: " + str(updated))
    print("  Skipped: " + str(skipped))
    print("  Images:  " + str(total_fixed))
    print("  Missing: " + str(total_missing))
    print("\n  Check Notion — images should be visible!")
    print("=" * 60)

    if updated + skipped == len(pages) and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)


if __name__ == "__main__":
    main()
