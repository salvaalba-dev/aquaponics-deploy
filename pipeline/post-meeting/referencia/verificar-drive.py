#!/usr/bin/env python3
"""Comprueba contra el Drive de AU dónde está cada bandeja de departamento.

Solo lee: para cada bandeja imprime su nombre, su direccion y la cadena de
carpetas a la que pertenece. Si algo no cuadra con referencia/drive.md, manda
lo que diga el Drive.

Uso (en el VPS, con la credencial que vive alli):
    /opt/whisper-transcribe/venv/bin/python3 verificar-drive.py
"""
import json
import urllib.parse
import urllib.request

import google.auth.transport.requests as tr
import google.oauth2.service_account as sa

SA = "/opt/whisper-transcribe/google-service-account.json"
SUBJ = "secretaria@aquaponicsunited.com"

# Lo que dice drive.md (cotejo 2026-10-01)
BANDEJAS = {
    "Direccion": "16NpHdnETcn0LagLjxWP0x8Lo6AO4MBtG",
    "Secretaria": "1aaOqIdZeLCNbRmz2P9sAS1k3Oy3QfGp-",
    "CFO": "1LU_zDsf26Y7h_gkFy5UCbFrO26euXFcC",
    "Voluntariado": "1MIPoaQI8DX9A0hvOIq3h98v0L2Qt46Gr",
    "Proyectos": "18Vzr9D0lfDbBDyf2HIXFiFFLLsmcf6av",  # sin subcarpeta inbox
    "Marketing": "1mIPDvOsHi_B_DLI87tFcemSvRfSGzQtF",
    "Formacion": "1HAbm6H68j4aa2lUJusBXSss45D1TJx8E",
}
COORDINACION = "1deRGoVKEIKib3_z8-H6ic3ncX6elfe2b"


def creds():
    c = sa.Credentials.from_service_account_file(
        SA, scopes=["https://www.googleapis.com/auth/drive"], subject=SUBJ)
    c.refresh(tr.Request())
    return c


def get(c, fid, fields="name,id,parents"):
    url = "https://www.googleapis.com/drive/v3/files/%s?%s&supportsAllDrives=true" % (
        fid, urllib.parse.urlencode({"fields": fields}))
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + c.token})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def hijos(c, fid):
    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode({
        "q": "'%s' in parents and trashed=false" % fid,
        "fields": "files(id,name,mimeType)", "orderBy": "name", "pageSize": "100",
        "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + c.token})
    with urllib.request.urlopen(req) as r:
        return json.load(r).get("files", [])


def main():
    c = creds()
    for label, bid in BANDEJAS.items():
        try:
            f = get(c, bid)
        except Exception as e:
            print("%-13s NO ENCONTRADA o sin acceso (%s)" % (label, str(e)[:60]))
            continue
        print("%-13s bandeja='%s'  %s" % (label, f["name"], bid))
        cur, cadena = f, []
        for _ in range(4):
            ps = cur.get("parents")
            if not ps:
                break
            p = get(c, ps[0])
            cadena.append("%s (%s)" % (p["name"], p["id"]))
            cur = p
        print("              cadena: " + " > ".join(cadena or ["(sin padre)"]))
    print()
    print("Dentro de 01_COORDINACION (%s):" % COORDINACION)
    for f in hijos(c, COORDINACION):
        print("  %-24s %s" % (f["name"], f["id"]))


if __name__ == "__main__":
    main()
