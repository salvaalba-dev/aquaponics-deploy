# Plantilla — cómo se documenta un pipeline

Copia este esqueleto para cada pipeline nuevo, tanto en el documento general como
en la carpeta `pipelines/<nombre>/`. Cada tarea, siempre en dos partes: para las
personas y para el asistente.

---

## Pipeline N — <nombre corto>

**Estado:** en producción / en pruebas / en uso / por detallar.
**Detalle técnico:** `pipelines/<carpeta>/README.md`

### Para las personas

<Qué hace, en lenguaje normal: qué entra, qué sale, cuándo se dispara, quién lo
usa y para qué.>

**Dónde queda todo**

| Qué | Dónde |
|---|---|
| ... | ... |

### Tareas

#### 1. <nombre de la tarea>

**Para las personas:** <qué se hace, cuándo, dónde queda y qué hay que tener en
cuenta.>

**Para el asistente (LLM):**

```bash
<el comando exacto, probado>
```

### Qué hay que saber

<avisos, límites, lo que el sistema no puede hacer solo.>

---

**Al escribir:** lenguaje normal y frases cortas, nada de jerga; los comandos,
probados; ningún secreto (ni claves ni contraseñas); y si algo todavía no está
claro, se escribe «por detallar» en vez de inventarlo.
