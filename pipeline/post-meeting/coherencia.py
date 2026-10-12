#!/usr/bin/env python3
"""Informe de coherencia: contrasta el acta y el resumen con la transcripcion
(marcas de tiempo). NO es un gate: si no hay clave o el modelo falla, escribe
"no verificable" y sale 0 (nunca tumba una entrega). No modifica el acta ni el .txt.
"""
import argparse
import json
import os
import sys
import urllib.request

ENV_PATH = "/opt/whisper-transcribe/.env"
PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt-coherencia.txt")


def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


def leer(p):
    try:
        return open(p, encoding="utf-8").read() if p and os.path.exists(p) else ""
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--acta", default="")
    ap.add_argument("--resumen", default="")
    ap.add_argument("--transcripcion", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--max-chars", type=int, default=95000)
    args = ap.parse_args()

    def emit(text):
        if not text.endswith("\n"):
            text += "\n"
        if args.out:
            open(args.out, "w", encoding="utf-8").write(text)
            print("coherencia -> %s" % args.out, file=sys.stderr)
        else:
            sys.stdout.write(text)

    texto = leer(args.transcripcion)
    if not texto.strip():
        emit("# Informe de coherencia\n\nno verificable (sin transcripcion)\n")
        return

    env = load_env()
    key = env.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        emit("# Informe de coherencia\n\nno verificable (sin clave DeepSeek)\n")
        return
    model = env.get("DEEPSEEK_MODEL") or "deepseek-v4-flash"

    base_prompt = leer(PROMPT_PATH) or (
        "Comprueba que lo que dicen el ACTA y el RESUMEN este realmente en la "
        "TRANSCRIPCION (cada intervencion trae su marca de tiempo). No corrijas el "
        "acta: solo informa. Dos secciones: '## Requiere revision de Secretaria' y "
        "'## Verificado'.\n\n")
    prompt = (base_prompt + "ACTA:\n" + leer(args.acta)[:40000] + "\n\nRESUMEN:\n"
              + leer(args.resumen)[:40000] + "\n\nTRANSCRIPCION:\n" + texto[:args.max_chars])

    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 4000,
    }).encode()
    base = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    req = urllib.request.Request(
        base + "/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.loads(r.read())
        emit("# Informe de coherencia\n\n" + resp["choices"][0]["message"]["content"])
    except Exception as e:
        emit("# Informe de coherencia\n\nno verificable (el modelo no respondio: %s)\n" % e)


if __name__ == "__main__":
    main()
