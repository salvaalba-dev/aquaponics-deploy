#!/usr/bin/env python3
"""Acta Markdown (acta.py) -> HTML con PORTADA estilo convocatoria AU -> PDF.

Portada (hoja 1): membrete de la convocatoria + DATOS DE LA REUNIÓN estructurados
(tabla campo/valor) + Asistentes + Orden del día.
Desde la hoja 2: la conversación (Desarrollo de la sesión) y lo que sigue
(Acuerdos, Próxima reunión, Cierre, Firmas).
En el pie de página: el nombre del archivo.

Uso:
  acta_a_pdf.py <acta.md> <salida.pdf> [--titulo "Acta de reunión"] [--html salida.html]
"""
import argparse
import datetime
import html
import os
import re
import subprocess
import sys

BRAND = "/opt/post-meeting/au-brand"
RENDER = os.path.join(BRAND, "html_to_pdf.js")

CIAN = "#00B1FD"
OLIVA = "#4C6620"
TXT = "#172238"
GRIS = "#6b7280"
LEGAL = ("Aquaponics United – AU | C/ Orfebres de Riviera, 22, 33, "
         "29649 Mijas Málaga | www.aquaponicsunited.com")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

CSS = """
@page { size: A4; }
* { box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 10.2pt;
       color: %(txt)s; margin: 0; }
.marca { position: fixed; top: 28%%; left: 50%%; transform: translateX(-50%%);
         width: 58%%; opacity: .055; z-index: 0; }

/* ---------- PORTADA (estilo convocatoria) ---------- */
.portada { position: relative; page-break-after: always; min-height: 244mm;
           padding: 4mm 0 0 0; }
.p-cab { display: flex; justify-content: space-between; align-items: flex-start; }
.p-cab img { height: 46px; }
.p-legal { text-align: right; font-size: 8.1pt; line-height: 1.35; color: #4a5568;
           text-transform: uppercase; }
.p-cuerpo { margin-top: 34mm; }
.p-eyebrow { font-size: 9.2pt; letter-spacing: .22em; text-transform: uppercase;
             color: %(gris)s; }
.p-tit { font-size: 25pt; font-weight: bold; text-transform: uppercase;
         color: %(cian)s; margin: 7px 0 0 0; line-height: 1.1; }
.p-sub { font-size: 14pt; font-weight: bold; color: %(oliva)s; margin-top: 10px; }
.p-linea { border-top: 1.5px solid %(cian)s; margin: 13px 0 4px 0; }
.p-tabla { border-collapse: collapse; width: 100%%; margin-top: 6px; }
.p-tabla th { text-align: left; width: 34mm; vertical-align: top;
              padding: 3.1mm 0 3.1mm 0; border-bottom: 1px solid #eef2f6;
              font-size: 8.5pt; letter-spacing: .06em; text-transform: uppercase;
              color: %(gris)s; font-weight: bold; }
.p-tabla td { vertical-align: top; padding: 3.1mm 0; font-size: 10.8pt;
              border-bottom: 1px solid #eef2f6; }
.p-sec { font-size: 11pt; font-weight: bold; color: %(oliva)s; margin: 9mm 0 2mm 0; }
.p-lista { margin: 0; font-size: 10.6pt; line-height: 1.55; }
.p-lista .n { color: %(gris)s; }
.nota { background: #fff8e1; border-left: 4px solid #e0a800;
        padding: 6px 10px; font-size: 8.8pt; margin-top: 8mm; }
.nota a { color: #00B1FD; text-decoration: none; }
.p-pie { position: absolute; bottom: 0; left: 0; right: 0; font-size: 8.2pt;
         color: %(gris)s; border-top: 1px solid #e2e8f0; padding-top: 5px; }

/* ---------- CUERPO (desde la hoja 2) ---------- */
.contenido { position: relative; z-index: 1; }
.cab { display: flex; align-items: center; gap: 12px;
       border-bottom: 2px solid %(cian)s; padding-bottom: 7px; margin-bottom: 15px; }
.cab img { height: 30px; }
.sec { font-size: 8.2pt; letter-spacing: .2em; text-transform: uppercase;
       color: %(cian)s; font-weight: bold; }
h1 { font-size: 15pt; margin: 8px 0 2px; color: %(cian)s; }
h2 { font-size: 11pt; margin: 16px 0 6px; color: %(oliva)s;
     border-bottom: 1px solid #dbe3ea; padding-bottom: 3px; }
p { margin: 5px 0; text-align: justify; }
.inter { margin: 6px 0; }
.inter strong { color: #00B1FD; }
.num { margin: 5px 0 5px 14px; }
.vin { margin: 3px 0 3px 14px; }
.pie { margin-top: 16px; font-size: 8.4pt; color: %(gris)s;
       border-top: 1px solid #e2e8f0; padding-top: 5px; }
.firmas { margin-top: 24px; font-size: 9.6pt; }
""" % {"txt": TXT, "gris": GRIS, "cian": CIAN, "oliva": OLIVA}


def inline(t):
    t = html.escape(t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", t)
    return t


def md_a_html(md):
    fuera = []
    for bruta in md.split("\n"):
        s = bruta.rstrip()
        if not s.strip():
            continue
        if s.startswith(">"):
            fuera.append('<div class="nota">%s</div>' % inline(s.lstrip("> ").strip()))
            continue
        if re.match(r"^\*\*[^*]+:\*\*", s):
            fuera.append('<p class="inter">%s</p>' % inline(s))
            continue
        if re.match(r"^\s*\d+[.)]\s+", s):
            fuera.append('<div class="num">%s</div>'
                         % inline(re.sub(r"^\s*(\d+)[.)]\s+", r"\1.  ", s)))
            continue
        if s.startswith("- "):
            fuera.append('<div class="vin">• %s</div>' % inline(s[2:]))
            continue
        if s.startswith("#"):
            n = len(s) - len(s.lstrip("#"))
            fuera.append("<h%d>%s</h%d>" % (n, inline(s.lstrip("# ").strip()), n))
            continue
        if "____" in s and "Fdo" in s:
            partes = [p.strip() for p in re.split(r"\s{3,}", s) if p.strip()]
            fuera.append('<div class="firmas">%s</div>'
                         % "".join("<div>%s</div>" % inline(p) for p in partes))
            continue
        fuera.append("<p>%s</p>" % inline(s))
    return "\n".join(fuera)


# ---------------------------------------------------------------- parseo del acta

def fecha_larga(txt):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", txt or "")
    if not m:
        return txt
    d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return "%s, %d de %s de %d" % (DIAS[d.weekday()], d.day, MESES[d.month - 1], d.year)


def seccion(md, titulo, hasta):
    """Devuelve las lineas utiles de una seccion, sin la cabecera ni lo siguiente."""
    lineas = [l.rstrip() for l in md.split("\n")]
    ini = None
    for i, l in enumerate(lineas):
        if l.strip().lower().startswith(titulo):
            ini = i + 1
            break
    if ini is None:
        return []
    fuera = []
    for l in lineas[ini:]:
        if not l.strip():
            continue
        if any(l.strip().lower().startswith(h) for h in hasta):
            break
        fuera.append(l.strip())
    return fuera


def parte_acta(md):
    """Titulo de la reunion, campos de datos, asistentes, orden del dia y avisos."""
    titulo_reunion = ""
    for l in md.split("\n"):
        if "Acta nº" in l and "—" in l:
            titulo_reunion = l.split("—")[0].strip()
            break
    titulo_reunion = titulo_reunion or seccion(md, "acta de reunión", ["datos de la reunión"])

    avisos = [l.strip().lstrip("> ").strip() for l in md.split("\n")
              if l.strip().startswith(">")]

    campos = {}
    for l in seccion(md, "datos de la reunión", ["asistentes", "orden del día",
                                                 "desarrollo de la sesión"]):
        if ":" in l:
            k, v = l.split(":", 1)
            campos[k.strip().lower()] = v.strip()
    m = re.search(r"Acta nº\s*([^|]*)", md)
    if m:
        campos["acta nº"] = m.group(1).strip()

    asistentes = seccion(md, "asistentes", ["orden del día", "desarrollo de la sesión"])
    orden = seccion(md, "orden del día", ["desarrollo de la sesión", "documentación"])

    cuerpo = ""
    lineas = md.split("\n")
    for i, l in enumerate(lineas):
        if l.strip().lower().startswith("desarrollo de la sesión"):
            cuerpo = "\n".join(lineas[i:])
            break
    cuerpo = cuerpo or md
    return titulo_reunion, campos, asistentes, orden, avisos, cuerpo


# ---------------------------------------------------------------- bloques HTML

def tabla_datos(campos, etiqueta_num="Acta nº"):
    filas = []
    fecha = campos.get("fecha", "")
    if fecha:
        filas.append(("Fecha", fecha_larga(fecha)))
    lugar = campos.get("lugar", "")
    if lugar:
        partes = [p.strip() for p in re.split(r"\s+—\s+", lugar)]
        filas.append(("Modalidad", partes[0]))
        if len(partes) > 1:
            filas.append(("Enlace", partes[1]))
    for clave, etiqueta in (("solicitante", "Solicitante"), ("departamento", "Departamento")):
        v = campos.get(clave, "")
        if v:
            filas.append((etiqueta, v[0].upper() + v[1:]))
    acta_n = campos.get("acta nº", "")
    if acta_n:
        n = re.sub(r"[\[\]]", "", acta_n).strip()
        filas.append((etiqueta_num, "Pendiente de Secretaría" if n in ("nº", "", "n")
                      else n))
    if not filas:
        return ""
    return ('<table class="p-tabla">%s</table>'
            % "".join("<tr><th>%s</th><td>%s</td></tr>" % (html.escape(k), inline(v))
                      for k, v in filas))


def bloques_lista(titulo, lineas, numerada=False, vacio="—"):
    if not lineas:
        return '<div class="p-sec">%s</div><div class="p-lista">%s</div>' % (titulo, vacio)
    items = []
    for i, l in enumerate(lineas, 1):
        texto = re.sub(r"^\s*\d+[.)]\s+", "", l)
        texto = re.sub(r"^-\s+", "", texto)
        marca = ("<span class=\"n\">%d.</span> " % i) if numerada else ""
        items.append("<div>%s%s</div>" % (marca, inline(texto)))
    return '<div class="p-sec">%s</div><div class="p-lista">%s</div>' % (titulo,
                                                                        "".join(items))


def portada(titulo_reunion, campos, asistentes, orden, avisos, titulo,
            etiqueta_num="Acta nº"):
    notas = "".join('<div class="nota">%s</div>' % inline(a) for a in avisos)
    return """
<div class="portada">
  <div class="p-cab">
    <img src="file://%s/Logo_AU_horizontal.png" alt="Aquaponics United">
    <div class="p-legal">Aquaponics United – AU<br>RNA: 624097<br>
      C/ Orfebres de Riviera, 22, 33<br>29649 Mijas M&aacute;laga<br>
      Espa&ntilde;a (Spain)</div>
  </div>
  <div class="p-cuerpo">
    <div class="p-eyebrow">Secretar&iacute;a</div>
    <div class="p-tit">%s</div>
    %s
    <div class="p-linea"></div>
    %s
    %s
    %s
    %s
  </div>
</div>""" % (BRAND,
             inline(titulo or "Acta de reunión"),
             ('<div class="p-sub">%s</div>' % inline(titulo_reunion))
             if titulo_reunion else "",
             tabla_datos(campos, etiqueta_num),
             bloques_lista("Asistentes", asistentes),
             bloques_lista("Orden del día", orden, numerada=True) if orden else "",
             notas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("pdf")
    ap.add_argument("--titulo", default="")
    ap.add_argument("--clase", default="acta", choices=("acta", "resumen", "transcripcion"))
    ap.add_argument("--datos-de", default="")
    ap.add_argument("--html", default="")
    args = ap.parse_args()

    md = open(args.md, encoding="utf-8").read()
    nombre_archivo = os.path.basename(args.pdf)
    fuente_datos = args.datos_de or args.md
    md_datos = open(fuente_datos, encoding="utf-8").read()
    titulo_reunion, campos, asistentes, orden, avisos_doc, cuerpo_acta = \
        parte_acta(md_datos)
    avisos = [l.strip().lstrip("> ").strip() for l in md.split("\n")
              if l.strip().startswith(">")] or avisos_doc
    if args.clase == "resumen":
        cuerpo = "\n".join(l for l in md.split("\n")
                            if not l.strip().startswith(">"))
        etiqueta_num = "Referencia"
    elif args.clase == "transcripcion":
        cuerpo = "\n".join(l for l in md.split("\n")
                            if not l.strip().startswith(">"))
        etiqueta_num = "Referencia"
    else:
        cuerpo = cuerpo_acta
        etiqueta_num = "Acta nº"
    titulo = args.titulo or ("Resumen de la reunión" if args.clase == "resumen"
                             else "Transcripción de la reunión"
                             if args.clase == "transcripcion"
                             else "Acta de reunión")
    # El numero/referencia es el nombre del archivo: lleva fecha y hora del evento
    campos["acta nº"] = re.sub(r"\.(acta|resumen|transcripcion)?\.?pdf$", "", nombre_archivo,
                               flags=re.I)
    cuerpo_html = md_a_html(cuerpo)
    html_path = args.html or (os.path.splitext(args.pdf)[0] + ".html")

    doc = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>%s</title><style>%s</style></head>
<body>
<img class="marca" src="file://%s/Marca_agua_AU.png" alt="">
%s
<div class="contenido">
  <div class="cab"><img src="file://%s/Logo_AU_horizontal.png" alt="AU">
    <div class="sec">Secretaría · Aquaponics United</div></div>
  %s
</div>
</body></html>""" % (html.escape(titulo or "AU"), CSS, BRAND,
                     portada(titulo_reunion, campos, asistentes, orden, avisos,
                             titulo, etiqueta_num),
                     BRAND, cuerpo_html)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(doc)

    r = subprocess.run(["node", RENDER, html_path, args.pdf, nombre_archivo],
                       capture_output=True, text=True)
    if r.stdout:
        print(r.stdout.strip())
    if r.returncode != 0:
        print("ERROR del render:", r.stderr.strip()[-500:], file=sys.stderr)
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()
