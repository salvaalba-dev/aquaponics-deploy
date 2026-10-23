#!/usr/bin/env python3
"""VPS-side post-meeting pipeline: transcribe -> summarize -> upload to Drive -> verified retention.

Moves the heavy lifting off the MacBookPro: the server already owns the MP4
(recorded by Jibri) and already runs Whisper + DeepSeek summary. This script
adds the final steps of the custody flow (see Meetings.md «Custodia»):

  1. locate the recording MP4 in /var/recordings
  2. transcribe with faster-whisper if the .txt is missing
  3. summarize with DeepSeek if the .resumen.md is missing
  4. upload MP4 + .txt + .resumen.md to Drive folder 0211_Reuniones_AU
     (resumable chunked upload, no full-file buffering)
  5. verify the upload (name + size on Drive)
  6. retain server copies until the separate final-archive check succeeds

Designed to run as a detached background job (nohup / systemd-run), so it
never blocks a bot turn. Logs to /var/recordings/process-<name>.log.

Usage:
  process-recording.py <mp4-path-or-base-name> [--keep] [--folder 0211_Reuniones_AU]
                       [--subject secretaria@aquaponicsunited.com] [--no-upload]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request as ur
import urllib.error as ue
import urllib.parse as up

import google.oauth2.service_account as sa
import google.auth.transport.requests as tr

RECORDINGS_DIR = "/var/recordings"
WHISPER_DIR = "/opt/whisper-transcribe"
VENV_PY = os.path.join(WHISPER_DIR, "venv", "bin", "python")
SA_PATH = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    os.path.join(WHISPER_DIR, "google-service-account.json"),
)
SCOPE_DRIVE = ["https://www.googleapis.com/auth/drive"]
DEFAULT_FOLDER = "0211_Reuniones_AU"
DEFAULT_SUBJECT = "secretaria@aquaponicsunited.com"



def md5_of(path, chunk=8 * 1024 * 1024):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def find_existing(creds, room, md5):
    """Busca la sala en toda la unidad y devuelve el fichero con ese md5, o None.

    No se puede buscar por md5Checksum (Drive devuelve 400), así que se busca por
    el nombre de la sala y se coteja el hash en local. Resiste el renombrado del
    archivo: los ficheros archivados conservan el nombre de la sala.
    """
    q = up.quote("name contains '%s' and trashed = false" % room)
    url = ("https://www.googleapis.com/drive/v3/files?q=" + q +
           "&corpora=allDrives&includeItemsFromAllDrives=true&supportsAllDrives=true"
           "&fields=files(id,name,size,md5Checksum,parents)")
    req = ur.Request(url, headers={"Authorization": "Bearer " + creds.token})
    with ur.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())
    for f in resp.get("files", []):
        if (f.get("md5Checksum") or "") == md5:
            return f
    return None


def verify_by_id(creds, fid, size, md5):
    url = ("https://www.googleapis.com/drive/v3/files/" + fid +
           "?supportsAllDrives=true&fields=id,name,size,md5Checksum")
    req = ur.Request(url, headers={"Authorization": "Bearer " + creds.token})
    with ur.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def log(msg):
    print(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + msg, flush=True)


def find_mp4(name):
    """Accept full path or base name; return the mp4 path or None."""
    if os.path.isfile(name):
        return name
    base = os.path.basename(name)
    if base.endswith(".mp4"):
        base = base[:-4]
    for root, _dirs, files in os.walk(RECORDINGS_DIR):
        for f in files:
            if f == base + ".mp4" or f.startswith(base + "_") and f.endswith(".mp4"):
                return os.path.join(root, f)
    # fallback: any file containing the base
    for root, _dirs, files in os.walk(RECORDINGS_DIR):
        for f in files:
            if base in f and f.endswith(".mp4"):
                return os.path.join(root, f)
    return None


def run(cmd, timeout=None):
    log("RUN: " + " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def transcribe(mp4_path, txt_path):
    log("transcription missing -> running whisper")
    r = run([VENV_PY, os.path.join(WHISPER_DIR, "transcribe.py"),
             mp4_path, "--out", txt_path, "--hablantes", "--nombres", "--summarize"],
            timeout=4 * 3600)
    if r.stdout:
        log("whisper stdout tail: " + r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")
    if r.stderr:
        log("whisper stderr tail: " + r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")
    return os.path.exists(txt_path) and os.path.getsize(txt_path) > 0


def summarize(txt_path, resumen_path):
    log("summary missing -> running DeepSeek summarize")
    r = run([VENV_PY, os.path.join(WHISPER_DIR, "summarize.py"),
             txt_path, "--out", resumen_path], timeout=600)
    return os.path.exists(resumen_path) and os.path.getsize(resumen_path) > 0


def get_creds(subject):
    creds = sa.Credentials.from_service_account_file(
        SA_PATH, scopes=SCOPE_DRIVE, subject=subject)
    creds.refresh(tr.Request())
    return creds


def resolve_folder(creds, folder):
    if folder and folder.replace("_", "").replace("-", "").isalnum() and len(folder) >= 25:
        return folder
    q = up.quote("name = '" + folder.replace("'", "\\'") + "' and trashed = false")
    url = ("https://www.googleapis.com/drive/v3/files?q=" + q +
           "&corpora=allDrives&supportsAllDrives=true&includeItemsFromAllDrives=true&fields=files(id,name,mimeType)")
    req = ur.Request(url, headers={"Authorization": "Bearer " + creds.token})
    with ur.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())
    for f in resp.get("files", []):
        if f.get("mimeType") == "application/vnd.google-apps.folder":
            return f["id"]
    md = {"name": folder, "mimeType": "application/vnd.google-apps.folder"}
    req = ur.Request("https://www.googleapis.com/drive/v3/files?supportsAllDrives=true&fields=id,name",
                     data=json.dumps(md).encode(),
                     headers={"Authorization": "Bearer " + creds.token,
                              "Content-Type": "application/json"},
                     method="POST")
    with ur.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["id"]


def upload_file(creds, path, folder_id, chunk=50 * 1024 * 1024, max_retries=5):
    """Resumable chunked upload; returns drive file id."""
    size = os.path.getsize(path)
    name = os.path.basename(path)
    if name.endswith(".mp4"):
        mime = "video/mp4"
    elif name.endswith((".txt", ".md")):
        mime = "text/plain"
    else:
        mime = "application/octet-stream"
    log("uploading %s (%.1f MB)…" % (name, size / 1048576.0))

    meta = {"name": name, "mimeType": mime, "parents": [folder_id]}
    init_url = ("https://www.googleapis.com/upload/drive/v3/files"
                "?uploadType=resumable&supportsAllDrives=true&fields=id,name,size,webViewLink")
    req = ur.Request(init_url, data=json.dumps(meta).encode(),
                     headers={"Authorization": "Bearer " + creds.token,
                              "Content-Type": "application/json; charset=UTF-8",
                              "X-Upload-Content-Type": mime,
                              "X-Upload-Content-Length": str(size)},
                     method="POST")
    with ur.urlopen(req, timeout=60) as r:
        session_url = r.headers.get("Location")
    if not session_url:
        raise RuntimeError("no resumable session URL for " + name)

    offset = 0
    with open(path, "rb") as f:
        while offset < size:
            f.seek(offset)
            data = f.read(chunk)
            if not data:
                break
            end = offset + len(data) - 1
            hdrs = {"Content-Length": str(len(data)),
                    "Content-Range": "bytes %d-%d/%d" % (offset, end, size)}
            attempt = 0
            while True:
                try:
                    req = ur.Request(session_url, data=data, headers=hdrs, method="PUT")
                    resp = ur.urlopen(req, timeout=900)
                    if resp.status in (200, 201):
                        result = json.loads(resp.read())
                        log("upload OK %s -> id %s" % (name, result.get("id")))
                        return result.get("id")
                    rng = resp.headers.get("Range", "")
                    if rng:
                        offset = int(rng.split("-")[1]) + 1
                    break
                except ue.HTTPError as e:
                    if e.code == 308:
                        rng = e.headers.get("Range", "")
                        if rng:
                            offset = int(rng.split("-")[1]) + 1
                        break
                    if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                        delay = 2 ** attempt
                        log("HTTP %d chunk@%d: retry in %ds" % (e.code, offset, delay))
                        time.sleep(delay)
                        attempt += 1
                        try:
                            q = ur.Request(session_url, method="PUT")
                            qr = ur.urlopen(q, timeout=60)
                            qr.read()
                            rng = qr.headers.get("Range")
                            if rng:
                                offset = int(rng.split("-")[1]) + 1
                        except ue.HTTPError as qe:
                            if qe.code == 308 and qe.headers.get("Range"):
                                offset = int(qe.headers["Range"].split("-")[1]) + 1
                        continue
                    raise
                except ue.URLError as e:
                    if attempt < max_retries:
                        delay = 2 ** attempt
                        log("conn err @%d: retry in %ds" % (offset, delay))
                        time.sleep(delay)
                        attempt += 1
                        continue
                    raise
            f.seek(offset)
    raise RuntimeError("upload ended without completion: %d/%d" % (offset, size))


def drive_verify(creds, folder_id, name, size):
    """Check a file exists in folder with matching size; return (id, size) or None."""
    q = up.quote("name = '%s' and '%s' in parents and trashed = false"
                 % (name.replace("'", "\\'"), folder_id))
    url = ("https://www.googleapis.com/drive/v3/files?q=" + q +
           "&corpora=allDrives&supportsAllDrives=true&includeItemsFromAllDrives=true&fields=files(id,name,size)")
    req = ur.Request(url, headers={"Authorization": "Bearer " + creds.token})
    with ur.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())
    for f in resp.get("files", []):
        fsize = f.get("size")
        if fsize is not None and int(fsize) == size:
            return f["id"], int(fsize)
    if resp.get("files"):
        f = resp["files"][0]
        return f["id"], int(f.get("size") or 0)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("recording", help="mp4 path or base name")
    ap.add_argument("--folder", default=DEFAULT_FOLDER)
    ap.add_argument("--subject", default=DEFAULT_SUBJECT)
    ap.add_argument("--keep", action="store_true", help="do not delete server copies")
    ap.add_argument("--no-upload", action="store_true", help="transcribe/summarize only")
    ap.add_argument("--chunk-mb", type=int, default=50)
    args = ap.parse_args()

    log("=== process-recording: %s ===" % args.recording)
    mp4 = find_mp4(args.recording)
    if not mp4:
        log("ERROR: mp4 not found for '%s'" % args.recording)
        sys.exit(1)
    log("mp4: %s (%d bytes)" % (mp4, os.path.getsize(mp4)))

    base = os.path.splitext(os.path.basename(mp4))[0]
    # strip the trailing "_<date>-<time>" jibri suffix if present: NAME_YYYY-MM-DD-HH-MM-SS.mp4
    # e.g. 11-08-2026-09-00_almaponia_coordinacion_2026-08-11-07-16-49.mp4 -> base room name
    room = base
    parts = base.rsplit("_", 1)
    if len(parts) == 2 and len(parts[1]) == 19 and parts[1][4] == "-" and parts[1][7] == "-":
        room = parts[0]
    txt = os.path.join(RECORDINGS_DIR, room + ".txt")
    resumen = os.path.join(RECORDINGS_DIR, room + ".resumen.md")
    log("room: %s" % room)

    # 1. Transcribe if missing
    if not os.path.exists(txt) or os.path.getsize(txt) == 0:
        if not transcribe(mp4, txt):
            log("ERROR: transcription failed")
            sys.exit(2)
    else:
        log("transcription exists: %s (%d bytes)" % (txt, os.path.getsize(txt)))

    # 1b. Fusionar trozos seguidos del mismo interlocutor (lectura legible)
    if os.path.exists(txt) and os.path.getsize(txt) > 0:
        try:
            with open(txt, encoding="utf-8") as fh:
                if "Interviniente" in fh.read():
                    import shutil as _sh
                    _sh.copy2(txt, txt + ".crudo")
                    run([VENV_PY, "/opt/post-meeting/fusionar.py", txt, txt], timeout=600)
                    log("fusionado: %s (%d bytes)" % (txt, os.path.getsize(txt)))
        except Exception as e:
            log("aviso fusion: %s" % e)

    # 2. Summarize if missing
    if not os.path.exists(resumen) or os.path.getsize(resumen) == 0:
        if not summarize(txt, resumen):
            log("ERROR: summary failed")
            sys.exit(3)
    else:
        log("summary exists: %s (%d bytes)" % (resumen, os.path.getsize(resumen)))

    # 2b. Acta automatica (plantilla AU) desde la transcripcion etiquetada
    acta_path = os.path.join(RECORDINGS_DIR, room + ".acta.md")
    if os.path.exists(txt) and os.path.getsize(txt) > 0 and not os.path.exists(acta_path):
        cmd_acta = [VENV_PY, "/opt/post-meeting/acta.py", "--transcripcion", txt,
                    "--orden-drive", room,
                    "--plantilla", "/opt/post-meeting/plantillas/AU_ActaReunion.md",
                    "--out", acta_path]
        if os.path.exists(resumen):
            cmd_acta += ["--resumen", resumen]
        run(cmd_acta, timeout=900)
        log("acta: %s (%s)" % (acta_path, os.path.exists(acta_path)))

    # 2c. Acta a PDF con portada AU (el nombre del archivo va en el pie)
    acta_pdf = os.path.join(RECORDINGS_DIR, room + ".acta.pdf")
    if os.path.exists(acta_path) and os.path.getsize(acta_path) > 0:
        run([VENV_PY, "/opt/post-meeting/acta_a_pdf.py", acta_path, acta_pdf,
             "--titulo", "Acta de reunión"], timeout=900)
        log("acta pdf: %s (%s)" % (acta_pdf, os.path.exists(acta_pdf)))

    if args.no_upload:
        log("--no-upload: done (transcribe/summarize only)")
        sys.exit(0)

    # 3. Upload to Drive
    creds = get_creds(args.subject)
    folder_id = resolve_folder(creds, args.folder)
    log("folder %s -> %s" % (args.folder, folder_id))

    results = {}
    sizes = {}
    hashes = {}
    for path in (mp4, txt, resumen):
        name = os.path.basename(path)
        fsize = os.path.getsize(path)
        md5 = md5_of(path)
        sizes[name] = fsize
        hashes[name] = md5
        seen = find_existing(creds, room, md5)
        if seen:
            log("already in Drive (md5 %s), skipping upload: %s -> id %s"
                % (md5[:10], name, seen["id"]))
            results[name] = seen["id"]
            continue
        fid = upload_file(creds, path, folder_id, chunk=args.chunk_mb * 1024 * 1024)
        results[name] = fid

    # 3b. Enlazar las fuentes (URLs de Drive) en acta y resumen, y rehacer sus PDFs
    ids = [results.get(os.path.basename(p)) for p in (mp4, txt, resumen)]
    if all(ids):
        enlaces = []
        for flag, uid in zip(("--url-grabacion", "--url-transcripcion",
                              "--url-resumen"), ids):
            enlaces += [flag, "https://drive.google.com/file/d/%s/view" % uid]
        docs = [
            (acta_path, acta_pdf, "acta", []),
            (os.path.join(RECORDINGS_DIR, room + ".resumen.md"),
             os.path.join(RECORDINGS_DIR, room + ".resumen.pdf"), "resumen",
             ["--datos-de", acta_path]),
            (os.path.join(RECORDINGS_DIR, room + ".txt"),
             os.path.join(RECORDINGS_DIR, room + ".transcripcion.pdf"), "transcripcion",
             ["--datos-de", acta_path]),
        ]
        for md_doc, pdf_doc, clase, extra in docs:
            if os.path.exists(md_doc) and os.path.getsize(md_doc) > 0:
                run([VENV_PY, "/opt/post-meeting/fuentes.py", md_doc, pdf_doc,
                     "--clase", clase] + extra + enlaces, timeout=900)
                log("fuentes + pdf (%s): %s" % (clase, pdf_doc))

    # 3c. Informe de coherencia acta/resumen vs marcas de tiempo (NO es un gate:
    # nunca tumba la entrega; se deja junto a los artefactos y viaja a entregas/).
    coherencia = os.path.join(RECORDINGS_DIR, room + ".coherencia.md")
    if os.path.exists(acta_path) and os.path.exists(resumen) and os.path.exists(txt):
        try:
            run([VENV_PY, "/opt/post-meeting/coherencia.py", "--acta", acta_path,
                 "--resumen", resumen, "--transcripcion", txt, "--out", coherencia],
                timeout=900)
            log("coherencia: %s (%s)" % (coherencia, os.path.exists(coherencia)))
        except Exception as e:
            log("aviso coherencia (no fatal): %s" % e)

    # 3d. Segundo pase: subir los 3 PDF FINALES (con enlaces de Drive) a la bandeja.
    #     Van tras 3b porque embeben las URLs que solo existen tras el paso 3.
    pdf_docs = [acta_pdf,
                os.path.join(RECORDINGS_DIR, room + ".resumen.pdf"),
                os.path.join(RECORDINGS_DIR, room + ".transcripcion.pdf")]
    pdfs_ok = True
    for path in pdf_docs:
        name = os.path.basename(path)
        if not (os.path.exists(path) and os.path.getsize(path) > 0):
            pdfs_ok = False
            log("ERROR: falta el PDF final %s" % path)
            continue
        fsize = os.path.getsize(path); md5 = md5_of(path)
        seen = find_existing(creds, room, md5)
        if seen:
            log("already in Drive (md5 %s), skipping upload: %s -> id %s"
                % (md5[:10], name, seen["id"]))
            fid = seen["id"]
        else:
            fid = upload_file(creds, path, folder_id, chunk=args.chunk_mb * 1024 * 1024)
        try:
            f = verify_by_id(creds, fid, fsize, md5)
        except Exception as e:
            f = None
            log("verify error %s: %s" % (name, e))
        if bool(f and int(f.get("size") or 0) == fsize
                and (f.get("md5Checksum") or "") == md5):
            log("verify OK %s (%s bytes, md5 %s, en Drive como '%s')"
                % (name, fsize, md5[:10], f.get("name")))
        else:
            pdfs_ok = False
            log("verify FAILED %s (drive=%s)" % (name, f))
    if not pdfs_ok:
        log("ERROR: el 2º pase de PDF falló la verificación, keeping server copies")
        sys.exit(4)

    # 4. Verify
    log("verifying uploads…")
    all_ok = True
    for path in (mp4, txt, resumen):
        name = os.path.basename(path)
        try:
            f = verify_by_id(creds, results[name], sizes[name], hashes[name])
        except Exception as e:
            f = None
            log("verify error %s: %s" % (name, e))
        ok = bool(f and int(f.get("size") or 0) == sizes[name]
                  and (f.get("md5Checksum") or "") == hashes[name])
        if ok:
            log("verify OK %s (%s bytes, md5 %s, en Drive como '%s')"
                % (name, f["size"], hashes[name][:10], f.get("name")))
        else:
            all_ok = False
            log("verify FAILED %s (drive=%s)" % (name, f))
    if not all_ok:
        log("ERROR: verification failed, keeping server copies")
        sys.exit(4)

    # Uploading to an intake folder is not proof of final archival. Retain all
    # local files, even without --keep; only the verified cleanup owns deletion.
    log("server copies retained pending final per-artifact archival verification")

    log("=== DONE %s ===" % room)


if __name__ == "__main__":
    main()
