#!/usr/bin/env python3
"""Ingesta automatica: bandeja -> PhantomDocs (por referencia) -> destino segun la regla 09/10/2026.
Corre como el custodio (pepa). Idempotente: marca cada fichero ya tratado."""
import json, os, pathlib, subprocess, sys, datetime, urllib.request, urllib.parse

PERSONA = os.environ.get("INGEST_PERSONA", "pepa")
HOME    = f"/home/pb-{PERSONA}"
DOCS    = f"{HOME}/.local/share/phantombot/personas/{PERSONA}/tools/documents.sh"
SA      = f"{HOME}/.local/share/phantombot/personas/{PERSONA}/.secure/google-service-account.json"
SUBJECT = os.environ.get("INGEST_SUBJECT", "secretaria@aquaponicsunited.com")
# Destino (regla 09/10/2026): las reuniones del proyecto ALMAPONIA (bandeja alma)
# van a 01_REUNIONES_GO; cualquier otra reunion de AU a 02_Secretaria_PEPA/0211_Reuniones_AU.
# OJO: estas dos constantes son SOLO REFERENCIA de la regla — hoy NO las usa el
# codigo (la ingesta indexa con FOLDER; el movimiento lo decide el triage).
DEST_GO           = "1VnnY_IqQaaFJ9gL6imuuskd6G1_C85yN"    # 01_REUNIONES_GO (no usada)
DEST_REUNIONES_AU = "1u0MWy4VtoNTwSzW5n4MsPFOkCYHgB0Mq"    # 02_Secretaria_PEPA/0211_Reuniones_AU (no usada)
# POR DETALLAR: el enrutado de los documentos que NO son de reunion (a la carpeta de
# su departamento) NO esta implementado. La tabla de destinos vive en Documents.md,
# seccion "Tus dominios y carpetas". Implementarlo exige mas codigo (leer la seccion,
# mapear departamento -> carpeta) y mueve ficheros en Drive: hoy lo decide el triage
# de la bandeja. NO inventar ese enrutado aqui.
FOLDER  = os.environ.get("INGEST_FOLDER", "reuniones")
STATE   = pathlib.Path("/var/lib/phantomdocs-ingest/seen")
LOG     = pathlib.Path("/var/log/phantomdocs-ingest.log")
DRY     = "--dry-run" in sys.argv
INBOXES = {
  "direccion":    "16NpHdnETcn0LagLjxWP0x8Lo6AO4MBtG",
  "secretaria":   "1aaOqIdZeLCNbRmz2P9sAS1k3Oy3QfGp-",
  "finanzas":     "1LU_zDsf26Y7h_gkFy5UCbFrO26euXFcC",
  "voluntariado": "1MIPoaQI8DX9A0hvOIq3h98v0L2Qt46Gr",
  "marketing":    "1mIPDvOsHi_B_DLI87tFcemSvRfSGzQtF",
  "formacion":    "1HAbm6H68j4aa2lUJusBXSss45D1TJx8E",
  "alma":         "17Owx101Wcqvi_yvKMHKP7jgg3bflrbrt",
}

def slugify(name):
    import unicodedata, re
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9.]+", "-", s).strip("-.").lower()
    return re.sub(r"-{2,}", "-", s) or "documento"

def log(m):
    line = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds") + " " + m
    print(line, flush=True)
    try: LOG.open("a").write(line + "\n")
    except Exception: pass

from google.oauth2 import service_account
import google.auth.transport.requests
creds = service_account.Credentials.from_service_account_file(
    SA, scopes=["https://www.googleapis.com/auth/drive"], subject=SUBJECT)
creds.refresh(google.auth.transport.requests.Request())

def api(path, params=None, method="GET"):
    url = "https://www.googleapis.com/drive/v3/" + path
    if params: url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method=method,
        headers={"Authorization": "Bearer " + creds.token})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

STATE.mkdir(parents=True, exist_ok=True)
total = 0
import re

def key_of(name):
    base = name.rsplit(".", 1)[0] if "." in name else name
    return re.sub(r"_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$", "", base).lower()

for area, fid in INBOXES.items():
    try:
        res = api("files", {"q": f"'{fid}' in parents and trashed=false",
                            "fields": "files(id,name,mimeType)",
                            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
    except Exception as e:
        log(f"ERROR listando {area}: {e}"); continue
    groups = {}
    for f in res.get("files", []):
        if f.get("mimeType") == "application/vnd.google-apps.folder": continue
        groups.setdefault(key_of(f["name"]), []).append(f)
    for key, items in sorted(groups.items()):
        names = [i["name"].lower() for i in items]
        transcribed = any(n.endswith(".txt") for n in names)
        summarized = any("resumen" in n for n in names)
        pend = [i for i in items if not (STATE / i["id"]).exists()]
        if not pend: continue
        if not (transcribed and summarized):
            log(f"ESPERA {area}: '{key}' sin completar (transcripcion={transcribed}, resumen={summarized}) -> NO se ingiere")
            continue
        for f in pend:
            file_id, name = f["id"], f["name"]
            total += 1
            if DRY:
                log(f"[dry] {area}: ingeriria {name} ({file_id})"); continue
            p = subprocess.run([DOCS, "add", "--ref", f"gdrive://{file_id}", "--slug", slugify(name),
                                "--folder", FOLDER, "--owners", PERSONA],
                               capture_output=True, text=True)
            if p.returncode != 0:
                log(f"ERROR ingesta {area}/{name}: {(p.stderr or p.stdout).strip()[:200]}"); continue
            (STATE / file_id).touch()
            log(f"OK {area}: {name} indexado en PhantomDocs (ficha). NO se mueve: el triage decide en la bandeja")
log(f"fin de ronda ({total} pendiente(s))")
