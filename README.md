# Aquaponics United — configuración de despliegue

Aquí vive la **configuración de despliegue** de Aquaponics United: lo que se aplica a las
máquinas y lo que se comprueba en ellas. El código de las herramientas va en los proyectos
(`phantomyard/phantomtools` y nuestro fork); aquí solo va la configuración de AU.

## Contenido

| Fichero | Qué es |
| --- | --- |
| `phantommeet/aquaponics-united.yaml` | Manifiesto de PhantomMeet de AU: organización, personas y roles, departamentos, almacenamiento y las **sondas de infraestructura** (`infra.checks[]`) que se ejecutan con `pm check-infra`. |

## Dónde está desplegado

- **VPS** `72.62.179.111` (srv1684936.hstgr.cloud) → `/opt/phantommeet/examples/aquaponics-united.yaml`
  - Comprobar: `cd /opt/phantommeet && ./.venv/bin/pm check-infra -m examples/aquaponics-united.yaml --host vps`
  - El informe se guarda además en `~/.local/state/phantommeet/check-infra.log`.

Hoy la copia del VPS es la que manda. **Se cambia en un sitio y se copia al otro**, y se comprueba
con el `sha256` de abajo.

## Reglas

- **Nada de secretos aquí.** Este fichero no lleva ninguno: solo nombres de variables (`key: X`) y
  textos de plantilla (`%PASSWORD_LINE%`). Si alguna vez hiciera falta un valor, se usa `env:` o
  `vault:` del proyecto — nunca el valor escrito.
- Los `*.bak` de las copias a mano se retiran: la historia la guarda este repo.

## Estado versionado

- `phantommeet/aquaponics-united.yaml` — versión `0.2.0`, 8874 bytes,
  `sha256 dfde1fb7671a485a66fb524f771683d9b506af4d70c64afd775bd46a6fb7fe64`
  (tal y como está en el VPS el 2026-10-09).
