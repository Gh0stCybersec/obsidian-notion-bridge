"""
Obsidian Notion Bridge - Step 1: Convert Vault
================================================
Converts Obsidian wiki-link syntax to standard markdown and
packages into ZIP file(s) for Notion import.

Import the ZIP(s) via: Notion → Settings → Import → Text & Markdown
"""

import os
import re
import shutil
import zipfile
import urllib.parse
from pathlib import Path

# ── CONFIGURATION ──────────────────────────────────────────────
VAULT_PATH = r"C:\Obsidian\MAIN"
ATTACHMENTS_FOLDER = "Files and Links"
OUTPUT_DIR = r"C:\Obsidian\notion_export"
MAX_FILES_PER_ZIP = 1500
# ───────────────────────────────────────────────────────────────


def find_all_attachments(vault_path, attachments_folder):
    attachments = {}
    attach_dir = os.path.join(vault_path, attachments_folder)
    if os.path.isdir(attach_dir):
        for root, dirs, files in os.walk(attach_dir):
            for f in files:
                attachments[f.lower()] = os.path.join(root, f)
    for root, dirs, files in os.walk(vault_path):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".pdf"):
                key = f.lower()
                if key not in attachments:
                    attachments[key] = os.path.join(root, f)
    return attachments


def convert_obsidian_md(content, attachments_lookup):
    referenced_images = set()

    def replace_image(match):
        full = match.group(1)
        parts = full.split("|")
        filename = parts[0].strip()
        alt = parts[1].strip() if len(parts) > 1 else filename
        referenced_images.add(filename)
        return f"![{alt}](attachments/{urllib.parse.quote(filename)})"

    content = re.sub(r"!\[\[([^\]]+)\]\]", replace_image, content)

    def replace_link(match):
        full = match.group(1)
        parts = full.split("|")
        display = parts[1].strip() if len(parts) > 1 else parts[0].strip()
        return f"**{re.sub(r'.md$', '', display)}**"

    content = re.sub(r"(?<!!)\[\[([^\]]+)\]\]", replace_link, content)
    content = re.sub(r"%%.*?%%", "", content, flags=re.DOTALL)

    def replace_callout(match):
        ctype = match.group(1).strip().title()
        title = match.group(2).strip() if match.group(2) else ""
        return f"> **{ctype}:** {title}" if title else f"> **{ctype}**"

    content = re.sub(r">\s*\[!(\w+)\]\s*(.*)", replace_callout, content)

    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].lstrip("\n")

    return content, referenced_images


def main():
    vault = Path(VAULT_PATH)
    out = Path(OUTPUT_DIR)

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    print("=" * 50)
    print("  Obsidian Notion Bridge - Step 1: Convert Vault")
    print("=" * 50)

    print("\nScanning attachments...")
    attachments = find_all_attachments(VAULT_PATH, ATTACHMENTS_FOLDER)
    print(f"  {len(attachments)} attachment files found")

    md_files = list(vault.rglob("*.md"))
    print(f"  {len(md_files)} markdown files found")

    all_refs = set()
    notes = []

    print("\nConverting...")
    for md_file in md_files:
        try:
            md_file.relative_to(vault / ATTACHMENTS_FOLDER)
            continue
        except ValueError:
            pass

        try:
            content = md_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = md_file.read_text(encoding="latin-1")
            except Exception:
                continue

        converted, refs = convert_obsidian_md(content, attachments)
        all_refs.update(refs)
        notes.append((str(md_file.relative_to(vault)), converted))

    print(f"  {len(notes)} notes converted")
    print(f"  {len(all_refs)} images referenced")

    resolved = {}
    missing = []
    for img in all_refs:
        if img.lower() in attachments:
            resolved[f"attachments/{img}"] = attachments[img.lower()]
        else:
            missing.append(img)

    if missing:
        print(f"\n  Warning: {len(missing)} images not found")

    total = len(notes) + len(resolved)
    num_zips = max(1, (total // MAX_FILES_PER_ZIP) + (1 if total % MAX_FILES_PER_ZIP else 0))

    print(f"\n  Creating {num_zips} ZIP file(s)...")

    if num_zips == 1:
        zp = out / "obsidian_to_notion.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel, content in notes:
                zf.writestr(rel, content)
            for zip_path, actual in resolved.items():
                zf.write(actual, zip_path)
        print(f"  Created: {zp} ({zp.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        per = len(notes) // num_zips + 1
        for i in range(num_zips):
            batch = notes[i * per: min((i + 1) * per, len(notes))]
            if not batch:
                continue
            batch_imgs = {k: v for k, v in resolved.items()
                         if any(os.path.basename(k) in c for _, c in batch)}
            zp = out / f"obsidian_to_notion_part{i + 1}.zip"
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
                for rel, content in batch:
                    zf.writestr(rel, content)
                for k, v in batch_imgs.items():
                    zf.write(v, k)
            print(f"  Created: {zp} ({zp.stat().st_size / 1024 / 1024:.1f} MB)")

    print("\n" + "=" * 50)
    print("  Done! Import the ZIP(s) into Notion:")
    print("  Settings -> Import -> Text & Markdown")
    print("=" * 50)


if __name__ == "__main__":
    main()
