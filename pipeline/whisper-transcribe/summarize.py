#!/usr/bin/env python3
"""Resume una transcripcion con DeepSeek API (modelo de Paco)."""
import argparse, json, os, sys, time, urllib.request

def load_env():
    env = {}
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript", help=".txt con la transcripcion")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    env = load_env()
    key = env.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("error: no DEEPSEEK_API_KEY", file=sys.stderr); sys.exit(1)
    model = env.get("DEEPSEEK_MODEL") or "deepseek-v4-flash"

    text = open(args.transcript, encoding="utf-8").read()
    if not text.strip():
        print("error: transcripcion vacia", file=sys.stderr); sys.exit(2)

    prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "prompt-resumen-v3.txt")
    contexto = text[:95000]
    if os.path.exists(prompt_path):
        prompt = open(prompt_path, encoding="utf-8").read() + contexto
    else:
        prompt = ("Eres el secretario de actas de Aquaponics United. Resume la siguiente "
                  "transcripcion en espanol.\n## Resumen ejecutivo\n## Decisiones\n"
                  "## Acuerdos\n## Acciones (tarea — responsable — plazo; "
                  "usa 'por identificar'/'sin plazo')\n## Riesgos\n## Temas pendientes\n\n"
                  "TRANSCRIPCION:\n" + contexto)

    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 4000,
    }).encode()

    base = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    req = urllib.request.Request(
        base + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
    summary = resp["choices"][0]["message"]["content"]
    usage = resp.get("usage", {})
    print(summary)
    print("\n--- stats: {} in / {} out / {:.1f}s".format(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), time.time() - t0), file=sys.stderr)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(summary + "\n")

if __name__ == "__main__":
    main()
