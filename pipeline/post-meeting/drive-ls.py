#!/usr/bin/env python3
"""Lista una carpeta de Drive por id (solo lectura). Uso: drive-ls.py <folder_id>"""
import json
import sys
import urllib.parse
import urllib.request

import google.auth.transport.requests as tr
import google.oauth2.service_account as sa

SA_PATH = "/opt/whisper-transcribe/google-service-account.json"
SUBJECT = "secretaria@aquaponicsunited.com"

creds = sa.Credentials.from_service_account_file(
    SA_PATH, scopes=["https://www.googleapis.com/auth/drive"], subject=SUBJECT)
creds.refresh(tr.Request())


def api(params):
    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + creds.token})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


fid = sys.argv[1]
r = api({"q": "'%s' in parents and trashed=false" % fid,
         "fields": "files(id,name,mimeType,size,md5Checksum,createdTime)",
         "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
         "orderBy": "name"})
for f in r.get("files", []):
    is_dir = f["mimeType"] == "application/vnd.google-apps.folder"
    sz = int(f.get("size", 0) or 0)
    print("%s %9s  %-10s  %s  %s" % ("DIR " if is_dir else "FILE", ("%.1fMB" % (sz / 1e6)) if not is_dir else "-",
                                     (f.get("md5Checksum") or "-")[:10], f["name"], f["id"]))
print("total: %d" % len(r.get("files", [])))
