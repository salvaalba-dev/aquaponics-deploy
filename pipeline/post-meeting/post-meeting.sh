#!/usr/bin/env bash
# Post-proceso automático de grabaciones de reuniones (Aquaponics United).
# Detecta un MP4 nuevo y estable en /var/recordings y ejecuta:
#   verificación de audio -> transcripción (Whisper local) -> resumen (DeepSeek)
#   -> subida de los 3 documentos a la BANDEJA UNICA del departamento (Drive)
#   -> aviso por correo -> registro. Idempotente; nunca borra antes de entregar.
# Politica (decision 24/08/2026, Salvador): bandeja unica -> PhantomDocs (integridad
# + sensibilidad) -> destino segun la regla 09/10/2026 (reunion del GO -> 01_REUNIONES_GO;
# Final archival is a separate deployment-owned step; reference ingestion does not move files.
set -uo pipefail
CONF=/opt/post-meeting/config
# shellcheck disable=SC1090
[ -r "$CONF" ] && . "$CONF"

REC_DIR=${REC_DIR:-/var/recordings}
ENT_DIR=${ENT_DIR:-/var/recordings/entregas}
STATE_DIR=${STATE_DIR:-/var/lib/post-meeting}
LOG_FILE=${LOG_FILE:-/var/log/post-meeting/post-meeting.log}
WORK_PY=${WORK_PY:-/opt/whisper-transcribe/venv/bin/python}
PROC=${PROC:-/opt/whisper-transcribe/process_recording.py}
MINT=${MINT:-/opt/recordings-serve/mint-url.py}
LOCK=${LOCK:-/run/post-meeting.lock}
ROUTE=${ROUTE:-/opt/post-meeting/resolve-route.py}
COTEJO=${COTEJO:-/opt/post-meeting/cotejo.py}

log(){ printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG_FILE"; }

[ "${ENABLED:-0}" = "1" ] || { log "deshabilitado (ENABLED != 1)"; exit 0; }

mkdir -p "$ENT_DIR" "$STATE_DIR" "$(dirname "$LOG_FILE")"
exec 9>"$LOCK" || exit 1
flock -n 9 || { log "otra ejecución en curso; salgo"; exit 0; }

dept_email(){ # $1 = clave de departamento o dirección completa
  local d="$1" e
  case "$d" in *@*) printf '%s' "$d"; return 0;; esac
  e=$(printf '%s\n' "${DEPT_MAP:-}" | awk -F: -v k="$d" 'tolower($1)==tolower(k){print $2}' | head -1)
  [ -n "$e" ] && { printf '%s' "$e"; return 0; }
  return 1 # Missing destinations must not fall back to another department.
}

dept_inbox(){ # $1 = clave de departamento -> "id_carpeta|nombre" de la bandeja en Drive
  local d="$1" e
  e=$(printf '%s\n' "${DEPT_INBOX_MAP:-}" | awk -F: -v k="$d" 'tolower($1)==tolower(k){print $2; exit}')
  [ -n "$e" ] && { printf '%s' "$e"; return 0; }
  return 1 # The selected department must have its own declared inbox.
}

audio_report(){ # $1 = fichero ; imprime el informe de audio
  local f="$1" a dur vol
  a=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,channels,sample_rate -of default=nw=1 "$f" 2>/dev/null | tr '\n' ' ')
  dur=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$f" 2>/dev/null)
  if [ -z "$a" ]; then
    printf 'AUDIO: SIN PISTA DE AUDIO (no se podrá transcribir nada)'; return 1
  fi
  vol=$(ffmpeg -v error -t 60 -i "$f" -af volumedetect -f null - 2>&1 | grep -oE 'mean_volume: [-0-9.]+ dB' | head -1)
  printf 'AUDIO: pista OK [%s] duración=%ss %s' "$a" "${dur%%.*}" "$vol"
  return 0
}

shopt -s nullglob
for f in "$REC_DIR"/*.mp4; do
  base=$(basename "$f"); stem="${base%.mp4}"
  case "$base" in *.part|*_partial*) continue;; esac
  [ -f "$STATE_DIR/$stem.done" ] && continue
  # no pisar la transcripcion que Jibri ya lanza en finalize.sh
  if pgrep -f "transcribe\.py .*${stem}" >/dev/null 2>&1; then
    log "transcripcion en curso (finalize de Jibri): $base"; continue
  fi

  now=$(date +%s); mt=$(stat -c %Y "$f"); age=$(( now - mt ))
  [ "$age" -lt "${MIN_AGE_SECONDS:-60}" ] && { log "esperando: $base (edad ${age}s)"; continue; }
  s1=$(stat -c %s "$f"); sleep "${STABLE_SECONDS:-20}"; s2=$(stat -c %s "$f")
  [ "$s1" != "$s2" ] && { log "aún escribiéndose: $base"; continue; }

  # Resolve only explicit context; a missing/failed order must not route to
  # Secretariat. Processing custody and document access remain unchanged.
  if ! dept=$("$WORK_PY" "$ROUTE" "$f" --lookup-python "$WORK_PY" \
      --lookup-script /opt/post-meeting/get-dept.py 2>>"$LOG_FILE"); then
    log "HOLD stage=routing meeting=$stem reason=explicit-context-required"
    continue
  fi
  to=$(dept_email "$dept")
  entry=$(dept_inbox "$dept"); inbox="${entry%%|*}"; inbox_name="${entry#*|}"
  [ "$inbox_name" = "$entry" ] && inbox_name="$dept"

  log "=== $stem | dept=$dept | bandeja=$inbox_name ($inbox) | aviso=$to ==="
  if [ -z "$inbox" ] || [ -z "$to" ]; then
    log "ERROR: el departamento '$dept' no tiene bandeja declarada; no proceso $stem"
    continue
  fi
  audio_line=$(audio_report "$f"); audio_rc=$?
  log "$audio_line"
  [ "$audio_rc" -ne 0 ] && log "AVISO: la grabación $stem no tiene audio"

  extra=""
  [ "${TEST_NO_UPLOAD:-0}" = "1" ] && extra="--no-upload"
  if ! "$WORK_PY" "$PROC" "$f" --keep --folder "$inbox" $extra >>"$LOG_FILE" 2>&1; then
    log "ERROR: falló el post-proceso de $stem"
    printf 'To: %s\nFrom: %s\nSubject: [Grabaciones] fallo al procesar %s\nContent-Type: text/plain; charset=utf-8\n\nFalló el post-proceso de %s.\n%s\nRevisar %s\n' \
      "${ALERT_TO:-root@localhost}" "${MAIL_FROM:-grabaciones@aquaponicsunited.com}" "$stem" "$stem" "$audio_line" "$LOG_FILE" \
      | /usr/sbin/sendmail -t -oi 2>>"$LOG_FILE"
    continue
  fi

  room="$stem"
  case "$stem" in
    *_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-[0-9][0-9]-[0-9][0-9]-[0-9][0-9]) room="${stem%_*}" ;;
  esac
  txt="$REC_DIR/$room.txt"; res="$REC_DIR/$room.resumen.md"
  segs=$(grep -cE '^\[[0-9]' "$txt" 2>/dev/null || echo 0)
  [ "$segs" -eq 0 ] && log "AVISO: $stem transcrito con 0 segmentos (posible silencio)"

  url=$(python3 "$MINT" "$base" --expires 168 2>>"$LOG_FILE" | tail -1)

  dest="$ENT_DIR/$(date +%Y-%m-%d)_${stem}"; mkdir -p "$dest"
  [ -f "$txt" ] && cp -a "$txt" "$dest/"
  [ -f "$res" ] && cp -a "$res" "$dest/"
  [ -f "$REC_DIR/$room.coherencia.md" ] && cp -a "$REC_DIR/$room.coherencia.md" "$dest/"
  for _p in acta resumen transcripcion; do
    [ -f "$REC_DIR/$room.$_p.pdf" ] && cp -a "$REC_DIR/$room.$_p.pdf" "$dest/"
  done
  printf '%s\n' "$url" > "$dest/grabacion.url"
  cat > "$dest/meta.json" <<JSON
{"room":"$stem","department":"$dept","bandeja":"$inbox_name","bandeja_id":"$inbox","aviso":"$to","processed":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","segments":$segs,"audio":"$audio_line","recording_url":"$url"}
JSON

  # Prepare evidence before rendering; submit the exact frozen MIME bytes.
  message=$(mktemp "$dest/.mail-XXXXXX") || continue
  if "$WORK_PY" "$COTEJO" --prepare-delivery "$dest/meta.json" --recording "$f" >>"$LOG_FILE" 2>&1; then
  {
    printf 'To: %s\n' "$to"
    printf 'From: %s\n' "${MAIL_FROM:-grabaciones@aquaponicsunited.com}"
    printf 'Reply-To: secretaria@aquaponicsunited.com\n'
    printf 'Subject: [Grabación] %s\n' "$stem"
    printf 'MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary="AU-BOUNDARY"\n\n'
    printf -- '--AU-BOUNDARY\nContent-Type: text/plain; charset=utf-8\n\n'
    printf 'Reunión grabada: %s\nFecha de procesado: %s\n\n%s\nSegmentos de transcripción: %s\n\n' "$stem" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$audio_line" "$segs"
    printf 'Grabación (enlace temporal, 7 días): %s\nAdjuntos: transcripción, resumen y acta borrador (PDF con portada AU).\n\n— Sistema de grabaciones de Aquaponics United\n\n' "$url"
    for a in "$txt" "$res" "$REC_DIR/$room.acta.pdf" "$REC_DIR/$room.resumen.pdf" "$REC_DIR/$room.transcripcion.pdf"; do
      [ -f "$a" ] || continue
      case "$a" in
        *.pdf) _ct="application/pdf" ;;
        *)     _ct="text/plain; charset=utf-8" ;;
      esac
      printf -- '--AU-BOUNDARY\nContent-Type: %s; name="%s"\nContent-Disposition: attachment; filename="%s"\nContent-Transfer-Encoding: base64\n\n' "$_ct" "$(basename "$a")" "$(basename "$a")"
      base64 -w 76 "$a"; echo
    done
    printf -- '--AU-BOUNDARY--\n'
  } >"$message"
    if [ "${TEST_NO_UPLOAD:-0}" != "1" ] && "$WORK_PY" "$COTEJO" --send-delivery "$dest/meta.json" --recording "$f" --message "$message" >>"$LOG_FILE" 2>&1; then
      log "STATE delivery=sendmail-accepted meeting=$stem archive=not-confirmed"
    else
      log "HOLD stage=cleanup meeting=$stem reason=delivery-not-confirmed"
    fi
  else
    log "HOLD stage=cleanup meeting=$stem reason=delivery-evidence-unavailable"
  fi
  rm -f "$message"

  # M7: informe de coherencia APARTE, a Secretaría (no al departamento).
  _coh="$REC_DIR/$room.coherencia.md"
  if [ -f "$_coh" ]; then
    _coh_to="${COHERENCIA_TO:-secretaria@aquaponicsunited.com}"
    {
      printf 'To: %s\n' "$_coh_to"
      printf 'From: %s\n' "${MAIL_FROM:-grabaciones@aquaponicsunited.com}"
      printf 'Reply-To: secretaria@aquaponicsunited.com\n'
      printf 'Subject: [Coherencia] %s\n' "$stem"
      printf 'MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary="AU-COH"\n\n'
      printf -- '--AU-COH\nContent-Type: text/plain; charset=utf-8\n\n'
      printf 'Informe de coherencia de la reunión %s.\n\nEs el material para la revisión de Secretaría: contrasta el acta borrador con las marcas de tiempo de la grabación. No se envía al departamento y no es un gate (si dice "no verificable", también se envía: es información para la revisión).\n\n— Sistema de grabaciones de Aquaponics United\n\n' "$stem"
      printf -- '--AU-COH\nContent-Type: text/markdown; charset=utf-8; name="%s"\nContent-Disposition: attachment; filename="%s"\nContent-Transfer-Encoding: base64\n\n' "$(basename "$_coh")" "$(basename "$_coh")"
      base64 -w 76 "$_coh"; echo
      printf -- '--AU-COH--\n'
    } | /usr/sbin/sendmail -t -oi 2>>"$LOG_FILE" \
      && log "informe de coherencia enviado a $_coh_to" \
      || log "ERROR: no se pudo enviar el informe de coherencia a $_coh_to"
  fi


  # Legacy done means processing/delivery attempted, not registered/archived.
  log "STATE stage=processing-finished delivery=see-receipt registration=not-confirmed archive=not-confirmed meeting=$stem"
  : > "$STATE_DIR/$stem.done"
  printf '%s %s %s %s segments=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$stem" "$dept" "$to" "$segs" >> "$STATE_DIR/records.log"

  # Delivery alone never authorizes deletion, including legacy configurations.
  if [ "${CLEANUP_AFTER_DELIVERY:-0}" = "1" ]; then
    log "CLEANUP_AFTER_DELIVERY ignored: final per-file archival verification required"
  fi
done

# Run under the existing round lock; each artifact needs its own archive proof.
# A missing route map or legacy delivery metadata keeps local files intact.
if ! CLEANUP_ARCHIVE_MAP="${CLEANUP_ARCHIVE_MAP:-}" "$WORK_PY" "$COTEJO" --borrar >>"$LOG_FILE" 2>&1; then
  log "HOLD stage=cleanup reason=verification-incomplete"
fi
log "fin de ronda"
