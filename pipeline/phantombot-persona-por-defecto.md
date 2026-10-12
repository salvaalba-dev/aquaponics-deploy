# Phantombot — dónde se selecciona la persona por defecto (AU, VPS)

Objetivo: saber **qué fichero** hace que una instancia Phantombot sirva a una
persona concreta. No hay secretos aquí.

## 1. La clave: `state.json` → `default_persona`

El archivo que **selecciona la persona predeterminada** es el `state.json` del
*home* de Phantombot:

```
<home>/.local/share/phantombot/state.json
{
  "harness_bins": {},
  "default_persona": "<id>"
}
```

En el VPS hay **un home por persona** (`/home/pb-<id>/`), así que hay un
`state.json` por persona:

| Home | `default_persona` |
|---|---|
| `/home/pb-alicia/.local/share/phantombot/state.json` | `alicia` |
| `/home/pb-carla/...` | `carla` |
| `/home/pb-elena/...` | `elena` |
| `/home/pb-iris/...` | `iris` |
| `/home/pb-paco/...` | `paco` |
| `/home/pb-pepa/...` | `pepa` |
| `/home/pb-rakocy/...` | `rakocy` |
| `/home/pb-roberto/...` | `roberto` |

(Nota histórica: `state.json` **manda** sobre el `.toml`; en el corte de paco
del 23-sep el `default_persona` del store compartido se repuntó a `alma` sin
tocar el TOML.)

Home heredado (bots por dominio, otro principal): `/home/aquaponi/.../state.json`
→ `"default_persona": "lisa"`.

## 2. La configuración de la instancia: `config.toml`

```
<home>/.config/phantombot/config.toml          # config del home (600)
<home>/.local/share/phantombot/personas/<id>/config.toml   # config por persona
```

Bloques relevantes (muestra saneada en `config.sanitized.toml`):

- `[channels.telegram]` → `token` (por persona), `allowed_user_ids`, `poll_timeout_s`.
- `[harnesses] chain` + `[harnesses.pi.routing]` → `provider` / `primary_model`.
- `[embeddings]` / `[embeddings.gemini]` → proveedor y modelo de embeddings.
- `[jev]` + `[jev.judge]` → modelo de decisión (openrouter, `key_env`).
- `[autostart_modes] <id> = "login"` → arranque de esa persona.

## 3. Cómo arranca

Servicio de **sistema** por persona:

```
/etc/systemd/system/phantombot-pb-<id>.service
  User=pb-<id> / Group=pb-<id> / HOME=/home/pb-<id>
  ExecStart=… phantombot run
  PrivateTmp=yes / NoNewPrivileges=yes
/etc/systemd/system/phantombot-pb-<id>.service.d/   # log + relays
```

Timers: `phantombot-tick@<id>.timer`, `phantombot-heartbeat@<id>.timer`.

Regla (23-sep): `phantombot` original = unidad **de usuario**; `phantombot-pb-<id>`
= unidad **de sistema**. No mezclar.

## 4. Alcance de la persona: `scopes.json`

```
<home>/.local/share/phantombot/scopes.json
{ "format_version": 1, "org": "aquaponics-united", "rule": "chain",
  "scopes": { "alma": ["alma"], "pepa": ["alma","elena","pepa"], ... } }
```

Define qué personas puede «ver» cada una (p. ej. `paco: ["*"]`).
