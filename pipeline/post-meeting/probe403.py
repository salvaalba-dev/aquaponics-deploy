#!/usr/bin/env python3
"""Sonda: distinguir 403 por permisos vs por limite de peticiones."""
import json
import time
import urllib.parse
import urllib.request
import urllib.error

import google.auth.transport.requests as tr
import google.oauth2.service_account as sa

SA = "/opt/whisper-transcribe/google-service-account.json"
SUBJ = "secretaria@aquaponicsunited.com"
GO = "1VnnY_IqQaaFJ9gL6imuuskd6G1_C85yN"      # 01_REUNIONES_GO
COORD = "1deRGoVKEIKib3_z8-H6ic3ncX6elfe2b"   # 01_COORDINACION

creds = sa.Credentials.from_service_account_file(
    SA, scopes=["https://www.googleapis.com/auth/drive"], subject=SUBJ)
creds.refresh(tr.Request())


def call(params, path="files"):
    url = "https://www.googleapis.com/drive/v3/" + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + creds.token})
    try:
        with urllib.request.urlopen(req) as r:
            return "OK", json.load(r)
    except urllib.error.HTTPError as e:
        return "HTTP %s" % e.code, e.read().decode()[:500]


def show(label, st, body):
    print("%-42s %s" % (label, st))
    if st != "OK":
        print("      ", body.replace("\n", " ")[:300])


LIST = {"fields": "files(id,name)", "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
st, b = call(dict(LIST, q="'%s' in parents and trashed=false" % GO)); show("listar 01_REUNIONES_GO", st, b)
time.sleep(8)
st, b = call(dict(LIST, q="'%s' in parents and trashed=false" % COORD)); show("listar 01_COORDINACION", st, b)
time.sleep(8)
st, b = call(dict(LIST, q="name='00_ORDENES_DE_REUNION' and '%s' in parents and trashed=false" % GO))
show("buscar por nombre en 01_REUNIONES_GO", st, b)
time.sleep(8)
st, b = call(dict(LIST, q="name='03_ORDENES_DE_REUNION' and '%s' in parents and trashed=false" % COORD))
show("buscar por nombre en 01_COORDINACION", st, b)
