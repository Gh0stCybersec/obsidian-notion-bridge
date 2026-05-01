"""
Obsidian Notion Bridge - Step 2: Export Google Drive IDs
=========================================================
Lists all files in your Google Drive attachments folder and
creates a JSON mapping of filename -> direct image URL.

Prerequisites:
- Google Cloud project with Drive API enabled
- OAuth credentials saved as credentials.json

Output: gdrive_map.json
"""

import json
import os
import sys

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ── CONFIGURATION ──────────────────────────────────────────────
GDRIVE_FOLDER_ID = "YOUR_GOOGLE_DRIVE_FOLDER_ID_HERE"
GOOGLE_CREDENTIALS_FILE = r"C:\Obsidian\credentials.json"
TOKEN_FILE = r"C:\Obsidian\token.json"
OUTPUT_FILE = r"C:\Obsidian\gdrive_map.json"
# ───────────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        else:
            if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
                print(f"  Credentials not found: {GOOGLE_CREDENTIALS_FILE}")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print("  Auth token saved")
    return build("drive", "v3", credentials=creds)


def main():
    print("=" * 50)
    print("  Obsidian Notion Bridge - Step 2: Drive IDs")
    print("=" * 50)

    if "YOUR_" in GDRIVE_FOLDER_ID:
        print("\n  Fill in GDRIVE_FOLDER_ID at the top of this script!")
        sys.exit(1)

    print("\n  Authenticating...")
    service = get_drive_service()

    print("  Listing files...")
    files = {}
    page_token = None
    total = 0

    while True:
        results = service.files().list(
            q=f"'{GDRIVE_FOLDER_ID}' in parents and trashed = false",
            fields="nextPageToken, files(id, name)",
            pageSize=1000,
            pageToken=page_token,
        ).execute()

        for f in results.get("files", []):
            files[f["name"]] = f"https://lh3.googleusercontent.com/d/{f['id']}"
            total += 1

        page_token = results.get("nextPageToken")
        if not page_token:
            break
        print(f"  ... {total} files")

    print(f"  Found {total} files")

    with open(OUTPUT_FILE, "w") as out:
        json.dump(files, out, indent=2)

    print(f"  Saved to {OUTPUT_FILE}")
    print("\n  Next: Run 03_fix_images.py")


if __name__ == "__main__":
    main()
