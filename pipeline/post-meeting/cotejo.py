#!/usr/bin/env python3
"""Cotejo PREVIO al borrado. SOLO LECTURA: no borra nada.

Una copia local de /var/recordings se puede borrar SOLO si se cumplen las tres cosas:
  1) esta PROCESADA  -> existen transcripcion + resumen + meta.json en entregas/
  2) esta ENTREGADA  -> meta.json declara el aviso a la bandeja del departamento
  3) esta ARCHIVADA  -> el mismo contenido (md5) ya esta en su carpeta de destino (Drive)
Si falta cualquiera de las tres: NO BORRAR.
"""
import hashlib
import json
import pathlib
import sys
import urllib.parse
import urllib.request

import google.auth.transport.requests as tr
import google.oauth2.service_account as sa

SA_PATH = "/opt/whisper-transcribe/google-service-account.json"
SUBJECT = "secretaria@aquaponicsunited.com"
REC = pathlib.Path("/var/recordings")
ENT = REC / "entregas"
# Destinos validos (regla 09/10/2026): 01_REUNIONES_GO (reuniones del proyecto
# ALMAPONIA) y 02_Secretaria_PEPA/0211_Reuniones_AU (resto de reuniones de AU).
# Fallo al leer un destino = esos ficheros NO se dan por archivados (fail-closed).
DESTS = [
    "1VnnY_IqQaaFJ9gL6imuuskd6G1_C85yN",  # 01_REUNIONES_GO
    "1u0MWy4VtoNTwSzW5n4MsPFOkCYHgB0Mq",  # 02_Secretaria_PEPA/0211_Reuniones_AU
]

creds = sa.Credentials.from_service_account_file(
    SA_PATH, scopes=["https://www.googleapis.com/auth/drive"], subject=SUBJECT)
creds.refresh(tr.Request())

BORRAR = "--borrar" in sys.argv


def api(params):
    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + creds.token})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


dest = {}
for d in DESTS:
    try:
        r = api({"q": "'%s' in parents and trashed=false" % d,
                 "fields": "files(id,name,md5Checksum,size)",
                 "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
        n0 = len(dest)
        for f in r.get("files", []):
            if f.get("md5Checksum"):
                dest[f["md5Checksum"]] = f["name"]
        print("%s: %d fichero(s), %d con hash comprobable" % (d, len(r.get("files", [])), len(dest) - n0))
    except Exception as e:
        print("AVISO: no pude leer el destino %s (%s) -> esos ficheros no seran borrables" % (d, e))

vids = sorted(REC.glob("*.mp4"))
print()
print("Copias locales en %s: %d   |   entregas registradas: %d" % (REC, len(vids), len([p for p in ENT.glob('*') if p.is_dir()])))
borrados = 0
print("-" * 74)
for v in vids:
    stem = v.stem
    recs = [p for p in ENT.glob("*" + stem + "*") if p.is_dir()]
    rec = recs[0] if recs else None
    txt = bool(rec and list(rec.glob("*.txt")))
    resu = bool(rec and list(rec.glob("*resumen*")))
    meta = (rec / "meta.json") if rec else None
    meta_ok = bool(meta and meta.exists())
    proc = bool(rec and txt and resu and meta_ok)
    ent = False
    if meta_ok:
        try:
            d = json.loads(meta.read_text())
            ent = bool(d.get("aviso") or d.get("bandeja_id"))
        except Exception:
            ent = False
    m = md5(v)
    arch = m in dest
    falta = [n for n, ok in (("procesado", proc), ("entregado", ent), ("archivado", arch)) if not ok]
    print(v.name)
    print("   %.1f MB   md5 %s" % (v.stat().st_size / 1e6, m))
    print("   procesado=%s  entregado=%s  archivado=%s   (transcripcion=%s, resumen=%s, meta=%s)"
          % ("SI" if proc else "NO", "SI" if ent else "NO", "SI" if arch else "NO",
             "si" if txt else "no", "si" if resu else "no", "si" if meta_ok else "no"))
    if not falta:
        print("   => BORRABLE (procesado + entregado + archivado con el mismo hash)")
        if BORRAR:
            room = stem
            parts = room.rsplit("_", 1)
            if (len(parts) == 2 and len(parts[1]) == 19
                    and parts[1][4] == "-" and parts[1][7] == "-"):
                room = parts[0]
            victims = [v, REC / (room + ".txt"), REC / (room + ".resumen.md"),
                       REC / (room + ".acta.pdf"), REC / (room + ".resumen.pdf"),
                       REC / (room + ".transcripcion.pdf"), REC / (room + ".coherencia.md"),
                       REC / (room + ".meta.json"), pathlib.Path(str(v) + ".dept")]
            for x in victims:
                try:
                    if x.exists():
                        x.unlink()
                        borrados += 1
                        print("   borrado local: %s" % x.name)
                except Exception as e:
                    print("   AVISO: no pude borrar %s (%s)" % (x, e))
    else:
        print("   => NO BORRAR  (falta: %s)" % ", ".join(falta))
print("-" * 74)
if BORRAR:
    print("Modo borrado: %d fichero(s) local(es) eliminado(s); entregas/ y Drive intactos." % borrados)
else:
    print("Solo lectura: este cotejo NO ha borrado nada.")
