#!/usr/bin/env python3
"""Fusiona segmentos consecutivos del mismo interlocutor en una sola intervencion.

Entrada: transcripcion etiquetada tipo "[0000.1 -> 0001.7] Interviniente 1: texto"
Salida : las mismas lineas, pero juntando los trozos seguidos del mismo hablante.

Uso: fusionar.py <entrada.txt> [salida.txt]
"""
import re
import sys

PAT = re.compile(r"^\[(\d+\.\d+)\s*->\s*(\d+\.\d+)\]\s*([^:]+?)\s*:\s*(.*)$")


def fusionar(texto, hueco=1.0):
    trozos = []
    for linea in texto.split("\n"):
        s = linea.strip()
        if not s:
            continue
        m = PAT.match(s)
        if not m:
            trozos.append({"quien": None, "ini": None, "fin": None, "texto": s})
            continue
        ini, fin, quien, cuerpo = m.groups()
        ini, fin = float(ini), float(fin)
        ultimo = trozos[-1] if trozos else None
        if (ultimo and ultimo["quien"] == quien and ultimo["fin"] is not None
                and ini - ultimo["fin"] <= hueco):
            ultimo["texto"] = (ultimo["texto"] + " " + cuerpo.strip()).strip()
            ultimo["fin"] = fin
        else:
            trozos.append({"quien": quien, "ini": ini, "fin": fin, "texto": cuerpo.strip()})
    lineas = []
    for t in trozos:
        if t["quien"] is None:
            lineas.append(t["texto"])
        else:
            lineas.append("[%.1f -> %.1f] %s: %s" % (t["ini"], t["fin"], t["quien"], t["texto"]))
    return "\n".join(lineas) + "\n", trozos


if __name__ == "__main__":
    entrada = sys.argv[1]
    salida = sys.argv[2] if len(sys.argv) > 2 else entrada
    txt = open(entrada, encoding="utf-8").read()
    out, trozos = fusionar(txt)
    open(salida, "w", encoding="utf-8").write(out)
    antes = len([l for l in txt.split("\n") if l.strip()])
    print("fusionado: %d lineas -> %d intervenciones (%s)" % (antes, len(trozos), salida))
    voces = {}
    for t in trozos:
        if t["quien"]:
            voces[t["quien"]] = voces.get(t["quien"], 0) + 1
    print("reparto:", ", ".join("%s=%d" % (k, v) for k, v in sorted(voces.items())))
