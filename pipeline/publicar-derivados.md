# Publicar derivados en Drive (AU) — interfaces reales y nombres oficiales

Fecha: 2026-10-12. Solo lo **verificado** en el código vivo del VPS; se marcan los
huecos. Sin credenciales.

## 1. Subir a un ID de carpeta concreto

Herramienta: **`drive_upload.py`** (vivo `/opt/whisper-transcribe/drive_upload.py`).

```
drive_upload.py <local-path> --folder <name-or-id> [--subject <email>] [--chunk-mb 50]
```

- `--folder` acepta **nombre o id**. `resolve_folder()` usa el valor **como id** si,
  quitando `_` y `-`, es alfanumérico y `len >= 25` → subida directa a **ese id**
  (p. ej. `1VnnY_IqQaaFJ9gL6imuuskd6G1_C85yN`). Si no, busca por **nombre** y, si no
  existe, **crea la carpeta en la raíz** → para un destino fijo, pasar siempre el id.
- Subida **resumable por trozos** (50 MB), reintentos con backoff, reanuda desde el
  último byte confirmado, `supportsAllDrives=true` (unidades compartidas).
- **Devuelve el `id` de fichero de Drive** (`[drive] OK <nombre>: <id> (<size> bytes)`;
  la petición pide `fields=id,name,webViewLink,size`).

## 2. «Identificador de operación»

**No existe** una interfaz con id de operación/job en AU. Los identificadores reales son:

- **id de fichero de Drive** — lo devuelve la subida; es lo que se guarda para
  recuperar el resultado después.
- **md5** — la clave de idempotencia **real**: la organización **renombra al archivar**,
  así que verificar por nombre falla; y Drive **rechaza** `q=md5Checksum=…` (**HTTP 400**).
  El pipeline lista por `name contains <sala>` y coteja md5 en local (`find_by_md5`),
  y verifica con un GET por el id devuelto (`verify_by_id`: tamaño + md5).
- En PhantomDocs: `pd add --ref gdrive://<file_id> …` devuelve el nodo (urn) del store.
  **OJO**: el `--folder` de `pd add` es una carpeta **lógica** del store (p. ej.
  `reuniones`), **no** un id de carpeta de Drive.

→ Para «subir a un ID de carpeta»: `drive_upload.py --folder <id>`.
→ Para «recuperar el resultado»: por el **id de Drive** devuelto (y su md5).
→ Un «operation id» **no** existe: no inventarlo.

## 3. Nombres oficiales `AU-<fecha>-<seq>_<dept>_<título>_EVID`

- **El pipeline NO produce estos nombres.** Escribe los artefactos como
  `<sala>.txt` / `.resumen.md` / `.acta.md` / `.mp4` (el *stem* de la sala/jibri).
- La **organización renombra al archivar** a `AU-YYYYMMDD-NNN_…_EVID.ext`
  (evidencia: `post-meeting/patch-pipeline5.py`; archivado real 2026-09-30
  `AU-20260930-002/003/004_…_EVID.*`).
- Origen de cada valor:

| Campo | De dónde sale |
|---|---|
| **departamento** | campo `department` de la **orden de reunión**: Drive `01_COORDINACION/03_ORDENES_DE_REUNION/<room>.json`. Creador: `setup-ordenes*.py`. Lector: `get-dept*.py`. Fallback: `DEFAULT_DEPT=secretaria` |
| **título** | campo `title` de esa orden (y el *slug* de la sala) |
| **fecha** | nombre de sala (stem jibri `YYYY-MM-DD-HH-MM-SS`) y `created` de la orden |
| **secuencia (NNN)** | se **asigna al archivar** (observado: `001` captura, `002` grabación, `003` transcripción, `004` resumen) |

- Esquema de la orden (de `setup-ordenes.py`):
  `room, title, requester, department, bandeja, bandeja_id, ordered_by, created, note`.
- `org.yaml` **no** define el patrón: `documents.naming.domains` son dominios/tipos/
  categorías, y `communication.request_id_format` (`{org_id}-{yyyymmdd}-{seq4}`) es para
  **mensajes** de la org, **no** para nombres de fichero.
- Consecuencia: hoy el nombre canónico es una **convención operativa**, no una interfaz.
  Para usarlo como interfaz (p. ej. que el pipeline lo emita), hay que **declararlo**
  (patrón + de dónde sale la secuencia).

## 4. Ficheros de referencia (este repo)

- `whisper-transcribe/drive_upload.py` — subida a carpeta por id/nombre.
- `whisper-transcribe/process_recording.py` — subida + verificación por id + idempotencia md5.
- `post-meeting/setup-ordenes.py` — crea la orden de reunión (esquema anterior).
- `post-meeting/get-dept2.py` — lee el `department` de la orden para enrutar.
- `post-meeting/config` — `DEPT_INBOX_MAP`, `DESTINO_REUNIONES`, `DEFAULT_DEPT`.
