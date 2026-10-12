#!/usr/bin/env python3
"""Diagnostico de autenticacion Drive."""
import json
import urllib.parse

import google.auth.transport.requests as tr
import google.oauth2.service_account as sa

SA = "/opt/whisper-transcribe/google-service-account.json"
SUBJ = "secretaria@aquaponicsunited.com"

creds = sa.Credentials.from_service_account_file(
    SA, scopes=["https://www.googleapis.com/auth/drive"], subject=SUBJ)
creds.refresh(tr.Request())
print("creds.valid:", creds.valid, "| token len:", len(creds.token or ""), "| subject:", creds._subject)

sess = tr.AuthorizedSession(creds)
q = "'1VnnY_IqQaaFJ9gL6imuuskd6G1_C85yN' in parents and trashed=false"
url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(
    {"q": q, "fields": "files(id,name)", "supportsAllDrives": "true",
     "includeItemsFromAllDrives": "true"})
with sess.get(url) as r:
    d = r.json()
    print("AuthorizedSession ->", r.status, "|", len(d.get("files", [])), "ficheros en 01_REUNIONES_GO")
    for f in d.get("files", []):
        print("   -", f["name"])
