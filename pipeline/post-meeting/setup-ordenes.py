#!/usr/bin/env python3
"""Crea la carpeta de ordenes de reunion y deja registrada la orden de la reunion de hoy."""
import json
import urllib.parse
import urllib.request
import uuid

import google.auth.transport.requests as tr
import google.oauth2.service_account as sa

SA = "/opt/whisper-transcribe/google-service-account.json"
SUBJ = "secretaria@aquaponicsunited.com"
COORD = "1deRGoVKEIKib3_z8-H6ic3ncX6elfe2b"  # 01_COORDINACION
room = "2026-09-30-16-00_coordinacion_go_almaponia"
orden = {
    "room": room,
    "title": "Coordinacion GO ALMAPONIA",
    "requester": "alma",
    "department": "almaponia",
    "bandeja": "05_Proyectos/01_GO_ALMAPONIA/01_COORDINACION/00_INBOX",
    "bandeja_id": "17Owx101Wcqvi_yvKMHKP7jgg3bflrbrt",
    "ordered_by": "pepa",
    "created": "2026-09-30",
    "note": "Destino = bandeja del departamento solicitante (almaponia/alma). Norma 2026-09-30.",
}

creds = sa.Credentials.from_service_account_file(
    SA, scopes=["https://www.googleapis.com/auth/drive"], subject=SUBJ)
creds.refresh(tr.Request())


def api(path, params=None, body=None, method="GET"):
    url = "https://www.googleapis.com/drive/v3/" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": "Bearer " + creds.token,
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


# 1) carpeta de ordenes
r = api("files", {"q": "name='03_ORDENES_DE_REUNION' and '%s' in parents and trashed=false" % COORD,
                  "fields": "files(id,name)", "supportsAllDrives": "true",
                  "includeItemsFromAllDrives": "true"})
if r.get("files"):
    fid = r["files"][0]["id"]
    print("carpeta ya existia:", fid)
else:
    fid = api("files", {"supportsAllDrives": "true", "fields": "id,name"},
              body={"name": "03_ORDENES_DE_REUNION",
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [COORD]}, method="POST")["id"]
    print("carpeta creada:", fid)

# 2) orden de la reunion de hoy (si no existe ya)
r = api("files", {"q": "name='%s.json' and '%s' in parents and trashed=false" % (room, fid),
                  "fields": "files(id,name)", "supportsAllDrives": "true",
                  "includeItemsFromAllDrives": "true"})
if r.get("files"):
    print("orden ya existia:", r["files"][0]["id"])
else:
    content = json.dumps(orden, ensure_ascii=False, indent=2).encode()
    meta = json.dumps({"name": room + ".json", "parents": [fid], "mimeType": "application/json"})
    b = "b" + uuid.uuid4().hex
    body = b"".join([
        ("--" + b + "\r\n").encode(),
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        meta.encode(),
        ("\r\n--" + b + "\r\n").encode(),
        b"Content-Type: application/json\r\n\r\n",
        content,
        ("\r\n--" + b + "--\r\n").encode(),
    ])
    req = urllib.request.Request(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id,name",
        data=body, method="POST",
        headers={"Authorization": "Bearer " + creds.token,
                 "Content-Type": "multipart/related; boundary=" + b})
    with urllib.request.urlopen(req) as x:
        print("orden creada:", json.load(x)["id"])
