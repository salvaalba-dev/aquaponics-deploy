#!/usr/bin/env python3
"""Departamento de la orden de reunion de una sala (o nada). Uso: get-dept.py <room>
Busca en la carpeta de ordenes dentro de 01_REUNIONES_GO (visible para la cuenta de servicio)."""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

import google.auth.transport.requests as tr
import google.oauth2.service_account as sa

SA = "/opt/whisper-transcribe/google-service-account.json"
SUBJ = "secretaria@aquaponicsunited.com"
PARENT = os.environ.get("ORDENES_PARENT", "1VnnY_IqQaaFJ9gL6imuuskd6G1_C85yN")  # 01_REUNIONES_GO
NAME = os.environ.get("ORDENES_NAME", "00_ORDENES_DE_REUNION")

creds = sa.Credentials.from_service_account_file(
    SA, scopes=["https://www.googleapis.com/auth/drive"], subject=SUBJ)
creds.refresh(tr.Request())


def api(params):
    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + creds.token})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


room = re.sub(r"_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$", "", sys.argv[1])
r = api({"q": "name='%s' and '%s' in parents and trashed=false" % (NAME, PARENT),
         "fields": "files(id)", "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
if not r.get("files"):
    sys.exit(0)
fid = r["files"][0]["id"]
r = api({"q": "name='%s.json' and '%s' in parents and trashed=false" % (room, fid),
         "fields": "files(id,name)", "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
if not r.get("files"):
    sys.exit(0)
with urllib.request.urlopen(urllib.request.Request(
        "https://www.googleapis.com/drive/v3/files/%s?alt=media&supportsAllDrives=true" % r["files"][0]["id"],
        headers={"Authorization": "Bearer " + creds.token})) as x:
    d = json.loads(x.read().decode())
dept = (d.get("department") or "").strip()
if dept:
    print(dept)
