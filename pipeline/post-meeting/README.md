# Pipeline de actas y resúmenes — Aquaponics United (AU)

_Última actualización: 2026-10-10_

Este es el **detalle técnico** del pipeline. El documento general — en lenguaje
normal, para las personas y para el asistente — es
[`Readme_pipelines.md`](/opt/phantomorg/reglamentos/organizacion/au-pipelines-manual.md), en la raíz del repositorio.

Documenta la cadena completa que convierte una reunión grabada en **acta** y
**resumen** con la imagen de AU, y las decisiones tomadas. Vive en el VPS, junto
a los scripts (`/opt/post-meeting/README.md`).

## Qué produce

Por cada reunión grabada en `meet.aquaponicsunited.com`:

| Artefacto | Fichero | Qué es |
|---|---|---|
| Transcripción | `<sala>.txt` + `.transcripcion.pdf` | Diálogo etiquetado por interviniente, con marca de minuto |
| Resumen | `<sala>.resumen.md` + `.resumen.pdf` | Resumen automático (ejecutivo, acuerdos, acciones) |
| Acta | `<sala>.acta.md` + `.acta.pdf` | Borrador de acta con la plantilla de Secretaría |
| Coherencia | `<sala>.coherencia.md` | Informe de contraste para Secretaría (nombres y acuerdos del acta vs. marcas de tiempo de la grabación) |

Todo borrador: **Secretaría revisa, cierra y firma**.

## Dónde vive

- **VPS**: `root@72.62.179.111` (srv1684936.hstgr.cloud), clave
  `~/.ssh/id_hostinger`.
- `/opt/post-meeting/`: scripts de la ronda, `plantillas/AU_ActaReunion.md`,
  marca en `au-brand/` (`Logo_AU_horizontal.png`, `Anagrama_AU.png`,
  `Marca_agua_AU.png`, `html_to_pdf.js` — Chrome+node para el PDF).
- `/opt/whisper-transcribe/`: `process_recording.py`, `transcribe.py`,
  `summarize.py`, `.env` (modelo DeepSeek), `google-service-account.json` y el
  venv con whisper y google-auth.
- `/opt/diarize/`: diarización (sherpa-onnx) y modelos.
- `/var/recordings/`: grabaciones y artefactos. Log:
  `/var/log/post-meeting/post-meeting.log`. Registro:
  `/var/lib/post-meeting/records.log`.
- Timers: `post-meeting.timer` (cada hora, lun-vie 09:00-19:00 Europe/Madrid, `Persistent`)
  y, en el Mac, `phantomdocs-ingest.timer`.

## La cadena (`process_recording.py`)

1. **Comprueba el audio** de la grabación (ffprobe).
2. **Transcribe** con whisper (modelo turbo) + **diarización**
   (`--hablantes --nombres`): separa voces y, si alguien se presenta al
   principio («me llamo X», «soy X»), le pone el nombre; si no, `Interviniente n`.
1b. **`fusionar.py`**: une fragmentos seguidos del mismo interviniente — una
   intervención = un cambio de hablante.
2. **`summarize.py`** (DeepSeek, `deepseek-chat`): resumen con secciones.
2b. **`acta.py`**: genera el acta con la plantilla de Secretaría y los datos de
   la orden de reunión (título, fecha, solicitante, departamento).
2c. **`acta_a_pdf.py`**: PDF con portada AU.
3. **Sube a Drive** (bandeja del departamento solicitante): grabación,
   transcripción y resumen.
3b. **`fuentes.py`**: escribe en la nota de origen los enlaces de Drive y rehace
   **los tres PDFs**.
4. **Verifica** por id + tamaño + md5.
5. **Borra las copias locales** solo si `cotejo.py` dice BORRABLE (procesado +
   entregado + archivado en su **carpeta de destino** (`01_REUNIONES_GO` si es del
   proyecto ALMAPONIA; `02_Secretaria_PEPA/0211_Reuniones_AU` si no) con el mismo md5).
   `CLEANUP_AFTER_DELIVERY=0` a propósito: la regla de cotejo es más estricta.

## Cómo son los documentos

- **Plantilla del acta**: `AU_ActaReunion.md`, la oficial de Secretaría (Pepa).
- **Portada** (estilo de la convocatoria `AU_Convocatoria_Junta_*`): membrete con
  logo + datos legales a la derecha; «SECRETARÍA»; título en cian
  (`ACTA DE REUNIÓN` / `RESUMEN DE LA REUNIÓN`); subtítulo en oliva con el nombre
  de la reunión; línea cian; tabla de datos; marca de agua AU.
- **Hoja 1**: datos de la reunión estructurados (fecha en largo, modalidad,
  enlace, solicitante, departamento, referencia), **Asistentes**, **Orden del
  día** y la **nota de origen** con los enlaces a las fuentes.
- **Desde la hoja 2**: el contenido — en el acta, la conversación
  (`Desarrollo de la sesión`); en el resumen, sus secciones.
- **Pie**: `aquaponicsunited.com · <nombre del archivo> · Pág. X/Y`.

## Convenciones (decididas)

- **Acta nº / Referencia = el nombre del archivo** (`2026-09-30-16-00_...`):
  lleva fecha y hora del evento; nada se numera a mano.
- Fecha en formato humano: «miércoles, 30 de septiembre de 2026».
- Intervinientes **sin nombre**: fuera del listado de asistentes; **sí** en la
  conversación, con su etiqueta.
- Sin líneas en blanco de relleno.
- Enlaces de fuentes **visibles y clicables**, a las copias archivadas en la
  **carpeta de destino** de la reunión (`01_REUNIONES_GO` o
  `02_Secretaria_PEPA/0211_Reuniones_AU`).
- Archivo final: `05_Proyectos/01_GO_ALMAPONIA/01_COORDINACION/01_REUNIONES_GO`
  si la reunión es del proyecto ALMAPONIA; `02_Secretaria_PEPA/0211_Reuniones_AU`
  en cualquier otro caso.
- Resumen y acta cumplen **las mismas condiciones** de formato.

## Para el asistente (LLM): lanzarlo a mano

```bash
ssh -i ~/.ssh/id_hostinger root@72.62.179.111
V=/opt/whisper-transcribe/venv/bin/python3

# ronda completa de una grabación (sin borrar copias locales)
$V /opt/whisper-transcribe/process_recording.py \
   --recording /var/recordings/<sala>.mp4 --folder <id_bandeja> --keep

# solo transcribir/resumir (sin subir ni PDFs): añade --no-upload

# ¿se puede borrar la copia local? (solo lee)
$V /opt/post-meeting/cotejo.py <sala>

# rehacer acta y resumen con portada y fuentes
$V /opt/post-meeting/fuentes.py <sala>.acta.md <sala>.acta.pdf \
   --clase acta --url-grabacion <U> --url-transcripcion <U> --url-resumen <U>
$V /opt/post-meeting/fuentes.py <sala>.resumen.md <sala>.resumen.pdf \
   --clase resumen --datos-de <sala>.acta.md --url-grabacion <U> \
   --url-transcripcion <U> --url-resumen <U>
```

## Requisitos de cada reunión

- Que los participantes digan **nombre y cargo** en los primeros 10-20 s: así el
  acta atribuye las intervenciones y rellena la tabla de asistentes. Sin
  presentaciones no hay nombres.
- Aviso previo antes de grabar (política de custodia).

## Avisos conocidos

- El PDF del paso 2c sale **sin enlaces de fuentes** hasta el paso 3b (tras la
  subida); es normal.
- Buzones de Voluntariado y Formación en pausa: su correo cae en secretaría.
- El chequeo `/status` del bridge devuelve 401 (desactualizado, no es un fallo).
- Si el `md5Checksum` no se puede buscar en Drive, la verificación va por
  nombre + hash local.

## Historial

- **2026-09-30**: portada estilo convocatoria; datos estructurados en la hoja 1;
  nombre del archivo en el pie; conversación desde la hoja 2; acta nº = nombre
  del archivo; nota de origen con enlaces visibles; resumen con las mismas
  condiciones; pasos 2c y 3b automáticos.
