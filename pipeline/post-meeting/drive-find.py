#!/usr/bin/env python3
"""Busca en Drive por nombre y descarga. Reusa el service account del pipeline.

Uso:
  SA_PATH=/ruta/clave.json drive-find.py buscar "<texto>"
  SA_PATH=/ruta/clave.json drive-find.py bajar <file_id> <destino>
"""
import json
import os
import sys
import urllib.parse
import urllib.request

import google.auth.transport.requests as tr
import google.oauth2.service_account as sa

SA_PATH = os.environ["SA_PATH"]
SUBJECT = os.environ.get("SUBJECT", "secretaria@aquaponicsunited.com")
SCOPE = ["https://www.googleapis.com/auth/drive"]


def token():
    creds = sa.Credentials.from_service_account_file(SA_PATH, scopes=SCOPE, subject=SUBJECT)
    creds.refresh(tr.Request())
    return creds.token


def buscar(patron):
    tok = token()
    q = "name contains '%s' and trashed=false" % patron.replace("'", "")
    url = ("https://www.googleapis.com/drive/v3/files?q=" + urllib.parse.quote(q)
           + "&fields=files(id,name,size,md5Checksum)"
           + "&supportsAllDrives=true&includeItemsFromAllDrives=true&corpora=allDrives&pageSize=100")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    data = json.load(urllib.request.urlopen(req))
    for f in data.get("files", []):
        print("%s\t%s\t%s\t%s" % (f.get("id"), f.get("size", "?"), f.get("md5Checksum", "?"), f.get("name")))


def bajar(file_id, destino):
    tok = token()
    url = ("https://www.googleapis.com/drive/v3/files/" + file_id
           + "?alt=media&supportsAllDrives=true")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(req) as r, open(destino, "wb") as out:
        while True:
            trozo = r.read(4 * 1024 * 1024)
            if not trozo:
                break
            out.write(trozo)
    print("descargado en %s (%d bytes)" % (destino, os.path.getsize(destino)))


if __name__ == "__main__":
    modo = sys.argv[1]
    if modo == "buscar":
        buscar(sys.argv[2])
    elif modo == "bajar":
        bajar(sys.argv[2], sys.argv[3])
    else:
        sys.exit("modo desconocido")
