#!/usr/bin/env python3
"""Genera el ACTA (plantilla AU) desde una transcripcion etiquetada por interviniente.

Entrada : transcripcion .txt con lineas  [0000.0 -> 0005.1] Nombre: texto
Salida  : acta en Markdown siguiendo una plantilla AU dedicada (por defecto
          /opt/post-meeting/plantillas/AU_ActaReunion.md).

La seccion "Desarrollo de la sesion" se arma agrupando intervenciones consecutivas
del mismo hablante en parrafos legibles. Si se le pasa el resumen (.resumen.md),
toma de alli los acuerdos.

Uso:
  acta.py --transcripcion R.txt --plantilla AU_ActaReunion.md --out acta.md \
          [--meta meta.json] [--resumen R.resumen.md] [--minutos]
"""
import argparse
import json
import os
import sys
import re

RX_LINEA = re.compile(
    r"^\[(?P<a>\d+\.\d+)\s*->\s*(?P<b>\d+\.\d+)\]\s*(?:(?P<quien>[^:]{1,60}):\s*)?(?P<txt>.*)$")


def leer_intervenciones(path, hueco=6.0, tope=1500):
    """Agrupa segmentos consecutivos del mismo hablante en una intervencion-parrafo."""
    turnos = []
    for bruta in open(path, encoding="utf-8", errors="replace"):
        m = RX_LINEA.match(bruta.strip())
        if not m:
            continue
        a, b = float(m.group("a")), float(m.group("b"))
        quien = (m.group("quien") or "Interviniente ?").strip()
        txt = m.group("txt").strip()
        if not txt:
            continue
        if (turnos and turnos[-1]["quien"] == quien
                and (a - turnos[-1]["fin"]) <= hueco
                and len(turnos[-1]["texto"]) < tope):
            turnos[-1]["texto"] = (turnos[-1]["texto"] + " " + txt).strip()
            turnos[-1]["fin"] = b
        else:
            turnos.append({"quien": quien, "inicio": a, "fin": b, "texto": txt})
    return turnos


def desarrollo(turnos, minutos=True):
    """Una intervencion = un cambio de interlocutor. La marca es SOLO el minuto,
    entre parentesis justo despues del nombre: **Salvador (54):** ..."""
    partes = []
    for t in turnos:
        marca = ""
        if minutos:
            marca = " (%d)" % int(t["inicio"] // 60)
        partes.append("**%s%s:** %s" % (t["quien"], marca, t["texto"]))
    return "\n".join(partes)


def acuerdos_del_resumen(path):
    if not path or not os.path.exists(path):
        return None
    txt = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"(?ims)^#{1,4}[^\n]*\b(acuerdos|decisiones)\b[^\n]*\n(.*?)(?=^#{1,4}\s|\Z)", txt)
    if not m:
        return None
    items = re.findall(r"^\s*(?:[-*\u2022]|\d+[.)])\s+(.+)$", m.group(2), re.M)
    return [re.sub(r"\*\*", "", x).strip() for x in items] or None


def orden_desde_drive(room):
    """Lee la orden de reunion (<room>.json) del Drive de la organizacion."""
    try:
        import json as _json
        import urllib.parse
        import urllib.request

        import google.auth.transport.requests as _tr
        import google.oauth2.service_account as _sa
    except Exception as e:  # sin google-auth: reintentar con el interprete del venv
        venv = os.environ.get("ACTA_VENV_PY", "/opt/whisper-transcribe/venv/bin/python3")
        prefijo_venv = os.path.dirname(os.path.dirname(venv))
        if (not os.environ.get("ACTA_REEXEC") and os.path.exists(venv)
                and os.path.abspath(sys.prefix) != os.path.abspath(prefijo_venv)):
            os.environ["ACTA_REEXEC"] = "1"
            os.execv(venv, [venv, os.path.abspath(__file__)] + sys.argv[1:])
        print("aviso: sin google-auth (%s); usa %s" % (e, venv), file=sys.stderr)
        return {}
    sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS",
                             "/opt/whisper-transcribe/google-service-account.json")
    if not os.path.exists(sa_path):
        return {}
    creds = _sa.Credentials.from_service_account_file(
        sa_path, scopes=["https://www.googleapis.com/auth/drive"],
        subject="secretaria@aquaponicsunited.com")
    creds.refresh(_tr.Request())
    q = "name = '%s.json' and trashed=false" % room
    url = ("https://www.googleapis.com/drive/v3/files?q=" + urllib.parse.quote(q)
           + "&fields=files(id,name)&supportsAllDrives=true"
           + "&includeItemsFromAllDrives=true&corpora=allDrives")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + creds.token})
    fichas = _json.load(urllib.request.urlopen(req)).get("files", [])
    if not fichas:
        return {}
    url2 = ("https://www.googleapis.com/drive/v3/files/%s?alt=media&supportsAllDrives=true"
            % fichas[0]["id"])
    req2 = urllib.request.Request(url2, headers={"Authorization": "Bearer " + creds.token})
    return _json.load(urllib.request.urlopen(req2))


SIN_NOMBRE = re.compile(r"^interviniente\s*\d*\s*$", re.I)


def lista_asistentes(meta, hablantes):
    """Solo personas CON nombre. Los 'Interviniente n' no se listan aqui:
    van directamente en el desarrollo de la sesion (ahi si)."""
    gente = meta.get("asistentes") or hablantes or []
    lineas = []
    for g in gente:
        if isinstance(g, dict):
            nombre = (g.get("nombre") or "").strip()
            if not nombre or SIN_NOMBRE.match(nombre):
                continue
            linea = "- %s" % nombre
            if g.get("posicion"):
                linea += " — %s" % g["posicion"]
            if g.get("identificacion"):
                linea += " (%s)" % g["identificacion"]
            lineas.append(linea)
        else:
            nombre = str(g).strip()
            if not nombre or SIN_NOMBRE.match(nombre):
                continue
            lineas.append("- %s" % nombre)
    return "\n".join(lineas) if lineas else "Por identificar"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcripcion", required=True)
    ap.add_argument("--plantilla", default="/opt/post-meeting/plantillas/AU_ActaReunion.md")
    ap.add_argument("--meta", default="")
    ap.add_argument("--orden", default="", help="JSON de la orden de reunion (local)")
    ap.add_argument("--orden-drive", default="", dest="orden_drive",
                    help="nombre de la sala: lee <sala>.json del Drive")
    ap.add_argument("--resumen", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sin-minutos", action="store_true", dest="sin_minutos",
                    help="no poner la marca de minuto (por defecto SI se pone)")
    args = ap.parse_args()

    meta = {}
    if args.meta and os.path.exists(args.meta):
        meta = json.load(open(args.meta, encoding="utf-8"))
    if args.orden and os.path.exists(args.orden):
        orden_local = json.load(open(args.orden, encoding="utf-8"))
        meta.update({k: v for k, v in orden_local.items() if v})
        if orden_local.get("title"):
            meta.setdefault("tipo", orden_local["title"].upper())
        if orden_local.get("created"):
            meta.setdefault("fecha", orden_local["created"])
    if args.orden_drive:
        orden = orden_desde_drive(args.orden_drive)
        if orden:
            if orden.get("title"):
                meta.setdefault("tipo", orden["title"].upper())
            if orden.get("created"):
                meta.setdefault("fecha", orden["created"])
            if orden.get("requester"):
                meta.setdefault("solicitante", orden["requester"])
            if orden.get("department"):
                meta.setdefault("departamento", orden["department"])

    turnos = leer_intervenciones(args.transcripcion)
    hablantes = []
    for t in turnos:
        if t["quien"] not in hablantes:
            hablantes.append(t["quien"])

    plantilla = open(args.plantilla, encoding="utf-8").read()

    acuerdos = meta.get("acuerdos") or acuerdos_del_resumen(args.resumen)
    if acuerdos:
        bloque_ac = "\n".join("    %d.  %s" % (i, x) for i, x in enumerate(acuerdos, 1))
    else:
        bloque_ac = "    1.  [pendiente: completar y validar en Secretaría]"

    orden = meta.get("orden_del_dia") or ["[pendiente]"]
    bloque_orden = "\n".join("%d. %s" % (i, p) for i, p in enumerate(orden, 1))

    datos = []
    meta.setdefault("lugar", "Videoconferencia — meet.aquaponicsunited.com")
    for etq, clave in (("Fecha", "fecha"), ("Hora", "hora"), ("Lugar", "lugar"),
                       ("Carácter", "caracter"), ("Solicitante", "solicitante"),
                       ("Departamento", "departamento")):
        if meta.get(clave):
            datos.append("%s: %s" % (etq, meta[clave]))
    bloque_datos = "\n".join(datos) if datos else "[pendiente]"

    reemplazos = {
        "TIPO DE REUNIÓN / Nº ACTA": "%s — Acta nº %s" % (meta.get("tipo", "REUNIÓN"), meta.get("numero", "[nº]")),
        "NÚMERO": str(meta.get("numero", "[nº]")),
        "FECHA": meta.get("fecha", ""),
        "LISTA DE ASISTENTES": lista_asistentes(meta, hablantes),
        "ORDEN DEL DÍA APROBADO": bloque_orden,
        "DESARROLLO DE LA REUNIÓN — ACUERDOS, DEBATES, INTERVENCIONES": desarrollo(turnos, not args.sin_minutos),
        "FECHA Y HORA PRÓXIMA REUNIÓN": meta.get("proxima_reunion", "[pendiente]"),
    }
    for k, v in reemplazos.items():
        plantilla = plantilla.replace("[%s]" % k, v)

    plantilla = re.sub(r"(?ms)^\s+1\.\s+\[ACUERDO 1\].*?^\s+5\.\s+\[ACUERDO 5\]\s*$",
                       bloque_ac, plantilla)
    plantilla = re.sub(r"(?m)^Datos de la reunión\s*$",
                       "Datos de la reunión\n\n%s" % bloque_datos, plantilla, count=1)

    cabecera = ("> **BORRADOR automático** generado desde la grabación y el resumen de la reunión. "
                "Pendiente de revisión, cierre y firma por Secretaría.\n\n")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(cabecera + plantilla.rstrip() + "\n")
    print("acta escrita en %s (%d intervenciones, %d hablantes)"
          % (args.out, len(turnos), len(hablantes)))


if __name__ == "__main__":
    main()
