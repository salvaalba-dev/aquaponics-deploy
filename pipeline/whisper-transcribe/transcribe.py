#!/usr/bin/env python3
"""Transcribe audio/video with faster-whisper (local, no API). Optional: chain summary.

--hablantes : anade diarizacion (quien habla) EN LA MISMA PASADA, usando
              /opt/diarize (sherpa-onnx ONNX, CPU, sin torch ni token).
              El .txt sale ya como "[0012.3 -> 0015.7] Interviniente 1: ...".
--nombres   : intenta poner nombre a cada interviniente leyendo las
              presentaciones del principio ("me llamo X" / "soy X").
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

from faster_whisper import WhisperModel

DIARIZE_PYTHON = "/opt/diarize/venv/bin/python"
DIARIZE_PY = "/opt/diarize/diarize.py"
VENTANA_PRESENTACION = 900  # segundos: tramo donde se buscan las presentaciones


def diarizar(path):
    """Devuelve [{start,end,speaker}, ...] o [] si algo falla (no rompe la transcripcion)."""
    try:
        p = subprocess.run([DIARIZE_PYTHON, DIARIZE_PY, path, "--json"],
                           capture_output=True, text=True, timeout=7200)
    except Exception as e:
        print(f"[hablantes] no pude lanzar la diarizacion: {e}", file=sys.stderr)
        return []
    if p.returncode != 0:
        print(f"[hablantes] diarizacion fallida: {p.stderr.strip()[-300:]}", file=sys.stderr)
        return []
    try:
        return json.loads(p.stdout)
    except Exception as e:
        print(f"[hablantes] salida no JSON: {e}", file=sys.stderr)
        return []


def hablante_en(turnos, a, b):
    """Hablante con mas solape con el tramo [a,b]."""
    mejor, ov = None, 0.0
    for t in turnos:
        o = min(b, t["end"]) - max(a, t["start"])
        if o > ov:
            ov, mejor = o, t["speaker"]
    return mejor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--model", default="turbo")
    ap.add_argument("--language", default="es")
    ap.add_argument("--out", default="")
    ap.add_argument("--summarize", action="store_true", help="chain summarize.py after transcription")
    ap.add_argument("--hablantes", action="store_true", help="etiquetar por interviniente (diarizacion)")
    ap.add_argument("--nombres", action="store_true", help="deducir nombres de las presentaciones iniciales")
    args = ap.parse_args()

    t0 = time.time()
    print(f"[whisper] cargando modelo {args.model}...", flush=True)
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    print(f"[whisper] modelo listo en {time.time()-t0:.1f}s. Transcribiendo {args.input}...", flush=True)

    segments, info = model.transcribe(
        args.input,
        language=args.language,
        beam_size=1,
        vad_filter=True,
    )
    segs = []
    for seg in segments:
        texto = seg.text.strip()
        segs.append((float(seg.start), float(seg.end), texto))
        if not args.hablantes:  # con --hablantes se imprime al final, ya etiquetado
            print(f"[{seg.start:06.1f} -> {seg.end:06.1f}] {texto}", flush=True)
    dur = info.duration or 0

    turnos = diarizar(args.input) if (args.hablantes and segs) else []
    etiquetas = {}
    filas = []
    for (a, b, texto) in segs:
        spk = hablante_en(turnos, a, b) if turnos else None
        if spk is not None and spk not in etiquetas:
            etiquetas[spk] = f"Interviniente {len(etiquetas) + 1}"
        filas.append((a, b, spk, texto))

    if args.hablantes:
        if turnos:
            print(f"[hablantes] {len(etiquetas)} interviniente(s) detectado(s)", flush=True)
        else:
            print("[hablantes] sin diarizacion: la transcripcion va sin etiquetas", file=sys.stderr)

        if args.nombres:
            # Patron ampliado: "me llamo X" / "mi nombre es X" / "soy X", con X = nombre
            # o nombre + apellido. Los cargos ("soy el director") NO son nombres.
            rx_nombre = re.compile(
                r"(?i:(?:me llamo|mi nombre es|soy))\s+"
                r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de\s+(?:la\s+|los\s+|las\s+)?|del\s+)?[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})")
            cargos = {"director", "directora", "presidente", "presidenta", "secretario",
                      "secretaria", "coordinador", "coordinadora", "responsable", "jefe",
                      "jefa", "ingeniero", "ingeniera", "ceo", "cfo", "cto", "gerente",
                      "socio", "socia", "fundador", "fundadora"}
            # La diarizacion corta frases ("... Yo soy" | "Salvador Alba ..."), asi que
            # un nombre puede quedar a caballo entre dos segmentos del MISMO interviniente
            # (buscarlo por segmento da 0 coincidencias). Agregamos el texto de la ventana
            # por interviniente, en orden, antes de buscar la presentacion.
            acum = {}
            for (a, b, spk, texto) in filas:
                if spk is None or a > VENTANA_PRESENTACION:
                    continue
                acum[spk] = (acum.get(spk, "") + " " + texto).strip()
            asignados = 0
            for spk, blob in acum.items():
                if not etiquetas.get(spk, "").startswith("Interviniente"):
                    continue
                m = rx_nombre.search(blob)
                if not m:
                    continue
                nombre = m.group(1).strip()
                if any(t.lower() in cargos for t in nombre.split()):
                    continue
                etiquetas[spk] = nombre
                asignados += 1
                print(f"[nombres] Interviniente -> {nombre} (por su presentacion)", flush=True)
            if asignados == 0:
                print("[nombres] AVISO: 0 coincidencias; quedan 'Interviniente N' "
                      "(revisa VENTANA_PRESENTACION y el patron de presentacion)",
                      file=sys.stderr, flush=True)

    lines = []
    for (a, b, spk, texto) in filas:
        quien = ""
        if args.hablantes and spk is not None:
            quien = f"{etiquetas.get(spk, 'Interviniente ?')}: "
        line = f"[{a:06.1f} -> {b:06.1f}] {quien}{texto}"
        lines.append(line)
        if args.hablantes:
            print(line, flush=True)

    print(f"\n[whisper] OK: {len(lines)} segmentos, audio {dur:.0f}s, transcrito en {time.time()-t0:.1f}s", flush=True)

    if args.out:
        with open(args.out, "w") as f:
            f.write("\n".join(lines) + "\n")

    if args.summarize and lines:
        print(f"[whisper] lanzando resumen DeepSeek...", flush=True)
        here = os.path.dirname(os.path.abspath(__file__))
        summary_out = os.path.splitext(args.out)[0] + ".resumen.md" if args.out else ""
        cmd = [sys.executable, os.path.join(here, "summarize.py"), args.out]
        if summary_out:
            cmd += ["--out", summary_out]
        subprocess.run(cmd, check=False)
        if summary_out and os.path.exists(summary_out):
            print(f"[whisper] resumen guardado en {summary_out}")


if __name__ == "__main__":
    main()
