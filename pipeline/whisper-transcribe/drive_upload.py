#!/usr/bin/env python3
"""Resumable chunked upload to Google Drive (service account, domain delegation).

Handles arbitrarily large files: 50 MB chunks, retries with backoff, resume
from the last acknowledged byte on transient failures. No full-file buffering.

Usage:
  drive_upload.py <local-path> --folder <name-or-id> [--subject <email>] [--chunk-mb 50]
"""
import argparse
import json
import os
import sys
import time
import urllib.request as ur
import urllib.error as ue
import urllib.parse as up

import google.oauth2.service_account as sa
import google.auth.transport.requests as tr

SA_PATH = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "/opt/whisper-transcribe/google-service-account.json",
)
SCOPE_DRIVE = ["https://www.googleapis.com/auth/drive"]
CHUNK = 50 * 1024 * 1024
MAX_RETRIES = 5


def get_creds(subject):
    creds = sa.Credentials.from_service_account_file(
        SA_PATH, scopes=SCOPE_DRIVE, subject=subject)
    creds.refresh(tr.Request())
    return creds


def resolve_folder(creds, folder):
    """Return folder id for name or id."""
    if folder and folder.replace("_", "").replace("-", "").isalnum() and len(folder) >= 25:
        return folder
    q = up.quote("name = '" + folder.replace("'", "\\'") + "' and trashed = false")
    url = ("https://www.googleapis.com/drive/v3/files"
           "?q=" + q + "&fields=files(id,name,mimeType)")
    req = ur.Request(url, headers={"Authorization": "Bearer " + creds.token})
    with ur.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())
    for f in resp.get("files", []):
        if f.get("mimeType") == "application/vnd.google-apps.folder":
            return f["id"]
    # create at root
    md = {"name": folder, "mimeType": "application/vnd.google-apps.folder"}
    req = ur.Request("https://www.googleapis.com/drive/v3/files?fields=id,name",
                     data=json.dumps(md).encode(),
                     headers={"Authorization": "Bearer " + creds.token,
                              "Content-Type": "application/json"},
                     method="POST")
    with ur.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["id"]


def resumable_upload(creds, path, name, folder_id, mime):
    size = os.path.getsize(path)
    print("[drive] %s (%.1f MB) -> folder %s" % (name, size / 1048576.0, folder_id), flush=True)

    # 1. Initiate resumable session
    meta = {"name": name, "mimeType": mime}
    if folder_id:
        meta["parents"] = [folder_id]
    init_url = ("https://www.googleapis.com/upload/drive/v3/files"
                "?uploadType=resumable&supportsAllDrives=true&fields=id,name,webViewLink,size")
    req = ur.Request(init_url, data=json.dumps(meta).encode(),
                     headers={"Authorization": "Bearer " + creds.token,
                              "Content-Type": "application/json; charset=UTF-8",
                              "X-Upload-Content-Type": mime,
                              "X-Upload-Content-Length": str(size)},
                     method="POST")
    with ur.urlopen(req, timeout=60) as r:
        session_url = r.headers.get("Location")
    if not session_url:
        raise RuntimeError("no resumable session URL")

    # 2. Upload chunks with resume-on-retry
    offset = 0
    with open(path, "rb") as f:
        while offset < size:
            f.seek(offset)
            data = f.read(CHUNK)
            if not data:
                break
            end = offset + len(data) - 1
            hdrs = {
                "Content-Length": str(len(data)),
                "Content-Range": "bytes %d-%d/%d" % (offset, end, size),
            }
            attempt = 0
            while True:
                try:
                    req = ur.Request(session_url, data=data, headers=hdrs, method="PUT")
                    resp = ur.urlopen(req, timeout=600)
                    if resp.status in (200, 201):
                        result = json.loads(resp.read())
                        print("[drive] OK %s: %s (%s bytes)" % (name, result.get("id"), result.get("size", size)), flush=True)
                        return result
                    # 308 resume incomplete
                    rng = resp.headers.get("Range", "")
                    if rng:
                        offset = int(rng.split("-")[1]) + 1
                    break
                except ue.HTTPError as e:
                    if e.code == 308:
                        rng = e.headers.get("Range", "")
                        if rng:
                            offset = int(rng.split("-")[1]) + 1
                        break
                    if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                        delay = 2 ** attempt
                        print("[drive] HTTP %d chunk@%d: retry in %ds" % (e.code, offset, delay), flush=True)
                        time.sleep(delay)
                        attempt += 1
                        # re-query progress
                        try:
                            q = ur.Request(session_url, method="PUT")
                            qr = ur.urlopen(q, timeout=60)
                            qr.read()
                            rng = qr.headers.get("Range")
                            if rng:
                                offset = int(rng.split("-")[1]) + 1
                        except ue.HTTPError as qe:
                            if qe.code == 308 and qe.headers.get("Range"):
                                offset = int(qe.headers["Range"].split("-")[1]) + 1
                        continue
                    raise
                except ue.URLError as e:
                    if attempt < MAX_RETRIES:
                        delay = 2 ** attempt
                        print("[drive] conn err @%d: retry in %ds" % (offset, delay), flush=True)
                        time.sleep(delay)
                        attempt += 1
                        continue
                    raise
            f.seek(offset)
    raise RuntimeError("upload ended without completion: %d/%d" % (offset, size))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--folder", required=True)
    ap.add_argument("--subject", default="secretaria@aquaponicsunited.com")
    ap.add_argument("--chunk-mb", type=int, default=50)
    args = ap.parse_args()
    global CHUNK
    CHUNK = args.chunk_mb * 1024 * 1024

    creds = get_creds(args.subject)
    folder_id = resolve_folder(creds, args.folder)
    name = os.path.basename(args.path)
    if name.endswith(".mp4"):
        mime = "video/mp4"
    elif name.endswith((".txt", ".md")):
        mime = "text/plain"
    else:
        mime = "application/octet-stream"
    resumable_upload(creds, args.path, name, folder_id, mime)


if __name__ == "__main__":
    main()
