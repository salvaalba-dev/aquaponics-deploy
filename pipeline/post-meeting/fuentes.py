#!/usr/bin/env python3
"""Pone en la nota de origen del documento (acta o resumen) los enlaces a las
fuentes en Drive, y rehace el PDF con la portada AU.

Uso:
  fuentes.py <doc.md> <doc.pdf> [--clase acta|resumen] [--datos-de <acta.md>]
             [--url-grabacion U] [--url-transcripcion U] [--url-resumen U]

Reescribe la linea de la nota (empieza por "> **BORRADOR automático**"); si no
existe, la inserta al principio (es el caso del resumen).
"""
import argparse
import re
import subprocess
import sys

VENV_PY = "/opt/whisper-transcribe/venv/bin/python3"
ACTA_PDF = "/opt/post-meeting/acta_a_pdf.py"
COLA = " Pendiente de revisión, cierre y firma por Secretaría."
ORIGEN = {
    "acta": "generado desde la grabación y el resumen de la reunión.",
    "resumen": "generado desde la grabación y la transcripción de la reunión.",
    "transcripcion": "generado desde la grabación de la reunión.",
}
ETIQUETAS = (("grabacion", "grabación"), ("transcripcion", "transcripción"),
             ("resumen", "resumen"))


def nota(clase, urls):
    fuentes = ["%s: [%s](%s)" % (etiqueta, urls[clave], urls[clave])
               for clave, etiqueta in ETIQUETAS if urls.get(clave)]
    texto = ("> **BORRADOR automático** " + ORIGEN.get(clase, ORIGEN["acta"]))
    if fuentes:
        texto += " Fuentes — " + " · ".join(fuentes) + "."
    return texto + COLA


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("pdf")
    ap.add_argument("--clase", default="acta", choices=("acta", "resumen", "transcripcion"))
    ap.add_argument("--datos-de", default="")
    ap.add_argument("--url-grabacion", default="")
    ap.add_argument("--url-transcripcion", default="")
    ap.add_argument("--url-resumen", default="")
    args = ap.parse_args()

    urls = {"grabacion": args.url_grabacion,
            "transcripcion": args.url_transcripcion,
            "resumen": args.url_resumen}
    texto = nota(args.clase, urls)

    if args.clase == "transcripcion":
        # La transcripcion es un artefacto del pipeline (el .txt que se sube a
        # Drive): NO le insertamos la nota. La portada del PDF ya la toma de
        # <acta.md> (--datos-de), que lleva la nota y los enlaces a las fuentes.
        print("transcripcion: nota no aplicada al .txt (portada via --datos-de)")
    else:
        with open(args.md, encoding="utf-8") as f:
            original = f.read()
        salida, n = re.subn(r"(?m)^> \*\*BORRADOR automático\*\*.*$",
                            lambda _m: texto, original, count=1)
        if n == 0:
            salida = texto + "\n" + original
            print("nota insertada al principio de %s" % args.md)
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(salida)
        print("fuentes -> %s" % args.md)

    cmd = [VENV_PY, ACTA_PDF, args.md, args.pdf, "--clase", args.clase]
    if args.datos_de:
        cmd += ["--datos-de", args.datos_de]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print((r.stdout or "").strip() or (r.stderr or "").strip()[-300:])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
