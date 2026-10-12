# PhantomDocs — insumos para el arreglo de la ingesta (AU)

Copias **saneadas** (sin credenciales ni secretos) para que ChatGPT/Codex pueda leerlas:

- `au-org.sanitized.yaml` — modelo de organización AU **vivo** (`/opt/phantomdocs/org.yaml`, VPS). 516 líneas.
- `au-ingest-bandejas.py` — script de ingesta local (`/opt/phantomdocs/bin/ingest-bandejas.py`, VPS). 102 líneas.

**Saneado:** ids de Telegram de personas, correos personales, `chat_id` del grupo,
relay `ws://` y `bridge_npub` → `<redacted>`. Los `npub` de los actores se
conservan (son claves públicas, no secretos).

**Origen:** copiado del VPS el 2026-10-12. Repo privado (configuración de despliegue de AU).
