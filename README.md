# 🌉 Obsidian Notion Bridge

Migrate your entire Obsidian vault to Notion — **images and all.**

Notion's built-in markdown importer breaks image references from Obsidian. It doesn't understand `![[wiki-link]]` syntax and can't handle local image paths, so your images silently vanish. This tool fixes that by hosting images on Google Drive and using the Notion API to write proper image blocks.

Tested with a vault of **267 notes and 2,331 images** — everything migrated successfully.

---

## How It Works

The migration runs in three stages:

| Step | Script | What It Does |
|------|--------|-------------|
| 1 | `01_convert_vault.py` | Converts Obsidian syntax to standard markdown, packages into ZIP(s) for Notion import |
| 2 | `02_export_drive_ids.py` | Maps image filenames to Google Drive URLs after you upload your attachments folder |
| 3 | `03_fix_images.py` | Re-reads original Obsidian files, swaps image refs with Drive URLs, rewrites each Notion page via the API |

---

## Prerequisites

- **Python 3.8+**
- **Obsidian vault** with markdown notes and an attachments folder
- **Google Cloud project** (free) with the Google Drive API enabled
- **Notion account** with an integration set up

---

## Setup

### 1. Install Dependencies

```bash
pip install requests google-api-python-client google-auth-oauthlib
```

### 2. Google Cloud Setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com/) and create a project
2. Enable the **Google Drive API** (APIs & Services → Library → search "Google Drive API")
3. Set up the **OAuth consent screen**:
   - APIs & Services → OAuth consent screen
   - User type: **External** → Create
   - Fill in app name (e.g. "Obsidian Notion Bridge") and your email
   - Under **Test users** → add your own Google email
4. Create **OAuth credentials**:
   - APIs & Services → Credentials → **+ CREATE CREDENTIALS** → **OAuth client ID**
   - Application type: **Desktop app**
   - Download the JSON → save as `credentials.json` in your working directory

> **Important:** Don't use a simple API key — it can't list files in shared folders. You need OAuth2.

### 3. Notion Integration

1. Go to [notion.so/profile/integrations](https://www.notion.so/profile/integrations)
2. Click **New integration**, name it anything
3. Copy the **Internal Integration Secret** (starts with `ntn_`)
4. After importing your notes, go to the top-level page → **⋯** menu → **Connections** → add your integration

---

## Usage

### Step 1: Convert and Import Your Vault

Edit the config at the top of `scripts/01_convert_vault.py`, then run:

```bash
python scripts/01_convert_vault.py
```

This creates ZIP file(s) in your output directory. Import them into Notion via **Settings → Import → Text & Markdown**.

Your notes will appear in Notion with text intact, but **images will be broken** — that's expected.

### Step 2: Upload Images to Google Drive

1. Upload your attachments folder (e.g. `Files and Links`) to Google Drive
2. Right-click the folder → **Share** → **General access** → **Anyone with the link** → **Viewer**
3. Note the folder ID from the URL:
   ```
   https://drive.google.com/drive/folders/1VOZ3RyH8hAx0klqPNPsy4LpixxJeu8ZA
                                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                            This is the folder ID
   ```

### Step 3: Generate Image URL Mapping

Edit the config at the top of `scripts/02_export_drive_ids.py`, then run:

```bash
python scripts/02_export_drive_ids.py
```

A browser window opens for Google sign-in on first run. This creates `gdrive_map.json` mapping every filename to a direct Google Drive image URL.

### Step 4: Fix the Images

Edit the config at the top of `scripts/03_fix_images.py` (paste your Notion API key), then run:

```bash
python scripts/03_fix_images.py
```

The script scans all your Notion pages, matches each one to the original `.md` file by title, replaces broken image references with Google Drive URLs, and rewrites each page with proper image blocks.

**This takes a while** (~1 page/second due to API rate limiting). If interrupted, just re-run — progress is saved automatically.

---

## Configuration

All scripts have a `CONFIGURATION` section at the top:

| Variable | Description | Example |
|----------|-------------|---------|
| `VAULT_PATH` | Path to your Obsidian vault | `C:\Obsidian\MAIN` |
| `ATTACHMENTS_FOLDER` | Name of your images folder | `Files and Links` |
| `GDRIVE_FOLDER_ID` | Google Drive folder ID | `1VOZ3RyH8hAx...` |
| `NOTION_API_KEY` | Notion integration secret | `ntn_xxxxx` |
| `NOTION_ROOT_PAGE_ID` | ID of the imported top-level page | `352e40ef...` |

### Finding Your Notion Page ID

From the page URL:
```
https://www.notion.so/Page-Title-352e40efea73811d90b7cac275cc05b0
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                  This is the page ID
```

---

## What Gets Converted

| Obsidian Syntax | Notion Result |
|----------------|---------------|
| `![[image.png]]` | Rendered image (via Google Drive URL) |
| `![[image.png\|alt text]]` | Rendered image |
| `[[Note Name]]` | **Note Name** (bold text) |
| `[[Note\|Display Text]]` | **Display Text** (bold text) |
| `%%hidden comments%%` | Removed |
| `> [!note] Title` | Blockquote: **Note:** Title |
| YAML frontmatter (`---`) | Stripped |

---

## After Migration

Once everything is in Notion:

- **Paste images directly into Notion** going forward — they're hosted natively, no Google Drive needed
- **Delete the Google Drive folder** once you've confirmed everything looks good
- **Delete `credentials.json` and `token.json`** — only needed for migration
- **Revoke the Notion integration** if you no longer need it

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Script crashes with `ConnectionResetError` | Just re-run — progress is saved, it resumes where it left off |
| "Skip: no matching .md file" | Normal for folder pages (e.g. "Cybersecurity") that don't have `.md` files |
| Images show as broken links | Make sure Google Drive folder is shared as "Anyone with the link" |
| "No files found in Google Drive" | Use OAuth credentials, not an API key |
| Google sign-in shows "unverified app" warning | Click **Advanced** → **Go to [app name] (unsafe)** — this is normal for personal projects |

---

## How It Was Built

See [WRITEUP.md](WRITEUP.md) for a detailed walkthrough of the development process, the problems encountered, and how they were solved.

---

## License

MIT — use it however you like.
