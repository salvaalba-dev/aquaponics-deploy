# Pipeline AU — copia saneada (2026-10-12)

Instantánea **sin credenciales** del pipeline de post-proceso de reuniones de
Aquaponics United (AU), tal como está **desplegado en el VPS**
(`root@72.62.179.111`, `srv1684936.hstgr.cloud`).

Fuera de la copia: `.env` (clave DeepSeek), `google-service-account.json`,
`.secret` (token de los enlaces de entrega) y los `.bak-*`. Los correos
personales quedan como `<redacted-personal-email>`.

Cada carpeta replica su ruta viva bajo `/opt/`:

| En el repo | Ruta viva (VPS) | Qué es |
|---|---|---|
| `post-meeting/` | `/opt/post-meeting/` | Ronda automática, actas, marca y plantillas |
| `whisper-transcribe/` | `/opt/whisper-transcribe/` | Transcripción (Whisper local) y resumen (DeepSeek) |
| `recordings-serve/` | `/opt/recordings-serve/` | Enlaces temporales de entrega (`:8091`) |

## 1. La cadena (procesamiento de grabaciones)

La ronda la dispara `post-meeting.timer` → `post-meeting.sh` (idempotente, con
`flock`). Detecta un MP4 nuevo y «estable» en `/var/recordings` y ejecuta:

1. **Comprobación de audio** (ffprobe).
2. **Transcripción** — `process_recording.py` llama a `transcribe.py` (Whisper
   *turbo* local, sin coste) con diarización `--hablantes --nombres`.
3. **Fusión** — `fusionar.py` une fragmentos seguidos del mismo interviniente.
4. **Resumen** — `summarize.py` sobre el `.txt` (API DeepSeek, prompt
   `prompt-resumen-v3.txt`).
5. **Acta** — `acta.py` con la plantilla de Secretaría + `acta_a_pdf.py` / `fuentes.py`
   para el PDF con marca AU.
6. **Coherencia** — `coherencia.py` (contraste para Secretaría).
7. **Entrega** — subida a la **bandeja del departamento** (`DEPT_INBOX_MAP`),
   enlace temporal (`mint-url.py`, 7 días) y aviso por correo.
8. **Custodia** — la ingesta (`phantomdocs-ingest`) indexa por referencia en
   PhantomDocs y archiva en el destino: `01_REUNIONES_GO` (ALMAPONIA) o
   `02_Secretaria_PEPA/0211_Reuniones_AU` (resto).

Salida por reunión: `<sala>.txt`/`.transcripcion.pdf`, `.resumen.md`/`.resumen.pdf`,
`.acta.md`/`.acta.pdf`, `.coherencia.md`. Todo **borrador**: Secretaría revisa,
cierra y firma.

## 2. Interfaces (línea de comandos)

```
# Orquestador de una grabación (ruta o nombre base)
process_recording.py <recording> [--folder] [--subject] [--keep] [--no-upload] [--chunk-mb]

# Transcripción
transcribe.py <input> [--model] [--language] [--out] [--summarize] [--hablantes] [--nombres]

# Resumen
summarize.py <transcript.txt> [--out]

# Acta (borrador) desde transcripción + plantilla
acta.py --transcripcion <txt> --out <md> [--plantilla <AU_ActaReunion.md>]
        [--meta] [--orden <json>] [--orden-drive] [--resumen <md>] [--sin-minutos]

# PDF con marca AU (3 clases)
acta_a_pdf.py <md> <pdf> [--titulo] [--clase {acta,resumen,transcripcion}] [--datos-de] [--html]

# Bloque de fuentes / enlaces en el PDF
fuentes.py <md> <pdf> [--clase {acta,resumen,transcripcion}] [--datos-de]
           [--url-grabacion] [--url-transcripcion] [--url-resumen]

# Informe de coherencia (nombres/acuerdos vs marcas de tiempo)
coherencia.py --transcripcion <txt> [--acta <md>] [--resumen <md>] [--out] [--max-chars]

# HTML -> PDF vía Chrome headless (marca al pie)
node au-brand/html_to_pdf.js <input.html> <output.pdf> [title]

# Enlaces temporales de entrega
recordings-serve/serve.py        # sirve /var/recordings/entregas en :8091
recordings-serve/mint-url.py     # acuña un enlace con token caducable
```

Otros: `cotejo.py` (contraste/archivado), `drive-ls.py` / `drive-find.py`
(consulta Drive de solo lectura), `referencia/verificar-drive.py`.

## 3. Branding AU

- **Assets**: `post-meeting/au-brand/` — `Logo_AU_horizontal.png`,
  `Anagrama_AU.png`, `Marca_agua_AU.png`, `html_to_pdf.js` (Chrome headless).
- **Paleta** (en `post-meeting/acta_a_pdf.py`): `CIAN = #00B1FD`,
  `OLIVA = #4C6620`, texto `TXT = #333333`.
- **Plantilla de acta**: `post-meeting/plantillas/AU_ActaReunion.md`
  (bloques: Datos de la reunión · Asistentes · Orden del día · Desarrollo de la
  sesión · Acuerdos adoptados · Próxima reunión · firmas · pie
  `Aquaponics United – AU | www.aquaponicsunited.com`).
- Nota: la web de AU usa otra paleta (navy `#18265c` / aqua `#05a5cf` / green
  `#6e9e62`); son superficies distintas.

## 4. Configuración — `post-meeting/config`

Claves (valores saneados en el fichero de este repo):

| Clave | Significado |
|---|---|
| `ENABLED` | 1 = ronda activa |
| `DEFAULT_DEPT` | Depto. por defecto si la grabación no dice cuál la pidió (`secretaria`) |
| `DEPT_MAP` | Depto. → correo de aviso |
| `DEPT_INBOX_MAP` | Depto. → **bandeja única** (Drive) `area:id_carpeta\|nombre` |
| `DESTINO_REUNIONES` | Carpeta final del proceso (`01_REUNIONES_GO`) |
| `DRIVE_FOLDER` | Nombre del destino (lo archiva PhantomDocs) |
| `CLEANUP_AFTER_DELIVERY` | 0 = conservar copias locales del servidor |
| `MIN_AGE_SECONDS`, `STABLE_SECONDS` | Umbrales de «fichero terminado» |
| `MAIL_FROM`, `ALERT_TO` | Remitente de avisos / destino de fallos |

Rutas por defecto (en `post-meeting.sh`): `REC_DIR=/var/recordings`,
`ENT_DIR=/var/recordings/entregas`, `STATE_DIR=/var/lib/post-meeting`,
`LOG_FILE=/var/log/post-meeting/post-meeting.log`, `WORK_PY=<venv>/bin/python`.

## 5. Temporizadores

- `post-meeting.timer` — cada hora, lun-vie 09:00-19:00 (Europe/Madrid),
  `Persistent`.
- `phantomdocs-ingest.timer` — cada 15 min, `User=pb-pepa` (**VPS**; el
  `Readme_pipelines.md` dice «en el Mac» — deriva doc/realidad conocida).

## 6. Persona por defecto de Phantombot

Ver [`phantombot-persona-por-defecto.md`](phantombot-persona-por-defecto.md) y
la muestra `phantombot/config.sanitized.toml`.

## 7. Qué se ha saneado

`.env`, `google-service-account.json`, `.secret`, `*.bak-*`, `__pycache__/`,
`venv/`, y parches de un solo uso (`patch-*.py`). Correos personales →
`<redacted-personal-email>`. Los IDs de carpeta de Drive se conservan (ya
aparecen en el `org.yaml` saneado). Ninguna credencial viaja en este árbol.
