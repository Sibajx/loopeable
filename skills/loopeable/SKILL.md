---
name: loopeable
description: Use when the user wants to leave Claude Code working autonomously on a project — "deja trabajando a Claude", "haz un loop que…", "loopeable", "automatiza esto hasta que quede", "implementa todo lo de esta lista", "orquesta agentes/subagentes", "vacía la bandeja", or wants to configure, launch, monitor, approve, answer or stop a loopeable run. Not for a single quick edit, and not for a simple recurring check on an interval (that is the built-in /loop).
---

# loopeable — dejar a Claude Code trabajando

Configuras y lanzas `loopeable`, un orquestador que convierte información en tareas y corre un loop por tarea
(implementar → verificar → puerta de seguridad → revisar → corregir → integrar), varios en paralelo, cada uno en su
propio git worktree, con agentes y subagentes, hasta cumplir el objetivo o topar un límite. Los límites y frenos los
aplica el código de loopeable, no el modelo.

Respondes en el idioma del usuario (por defecto español).

## 0. ¿Está instalado?

`command -v loopeable || uv tool install git+https://github.com/Sibajx/loopeable` (pregunta antes de instalar).

## 1. Entrevista (una sola ronda, solo lo que no sepas)

Si ya hay `loopeable.toml` en el proyecto, léelo y pregunta solo qué cambia. Si no, junta en **una** pregunta
agrupada (con opciones y un valor recomendado en cada una):

1. **Carpeta o repo.** Por defecto, el directorio actual. Debe ser un repo de git (si no, ofrece `git init`).
2. **Objetivo**: una o dos frases de qué debe lograrse.
3. **Trabajo**: de dónde salen las tareas — lo que el usuario escribe ahora (lo guardas como
   `.loopeable/bandeja/<fecha>-<tema>.md`), un archivo del repo (p. ej. `PENDIENTES.md`) o ambos. Lo que vaya
   llegando después se agrega a la bandeja y se vuelve a correr.
4. **Qué es "hecho"**: corre `loopeable -C <carpeta> pruebas` y muestra los comandos detectados; el usuario confirma
   o corrige. Criterios extra que apliquen a todas las tareas.
5. **Hasta dónde**: tope de USD, horas, intentos por tarea, total de tareas, profundidad de subtareas (loops que crean
   loops) y loops en paralelo. Sugiere: 20 USD, 6 h, 3 intentos, 40 tareas, profundidad 2, paralelo 4. Los
   subagentes dentro de cada sesión no tienen tope propio: los limita el tope de USD.
6. **Qué no se toca**: rutas prohibidas además de las de siempre (.env, llaves, .git, workflows de CI) y, si quiere,
   solo-estas-rutas.
7. **Puertas humanas**: ¿aprobar el plan antes de implementar? (recomendado: sí). ¿Revisar cada cambio con
   security-suite? (pide la ruta a su clon). ¿PR en borrador al final?
8. **Dónde corre**: aquí en segundo plano, en Docker (recomendado si el proyecto tiene secretos cerca: los agentes
   tienen Bash) o en un server 24/7 (ver `despliegue/SERVER.md` del repo de loopeable).
9. **Avisos**: tema de ntfy y/o bot de Telegram para el celular.
10. **Cuenta: ¿qué plan tiene y con qué se paga?** Primero el plan (`[cuenta] plan`), porque cambia lo que conviene:

    | Plan | ¿Puede usar su plan? | Créditos mensuales de API incluidos | Sugerencia con `modo = "plan"` |
    |---|---|---|---|
    | Free | No: Free no incluye Claude Code | No | Solo `modo = "api"` con key de platform.claude.com |
    | Pro | Sí, con límites chicos | No | `paralelo = 1`, Sonnet para planificar y revisar, corridas cortas |
    | Max | Sí (5× o 20× Pro) | Sí (Max 5x/20x) | `paralelo = 2`, Opus solo para planear |
    | Ultra | Sí, el más holgado | Sí | `paralelo = 4`, Opus para planear y revisar |
    | Team | Sí, según el asiento (estándar o premium) | Sí, compartidos en el equipo | `paralelo = 2`, Sonnet; confirmar con el admin |
    | Enterprise | Sí, si su asiento incluye Claude Code | No | `paralelo = 2`; puede facturarse a precios de API: preguntar al admin |

    Si no sabe su plan: claude.ai → Configuración → Facturación. Luego el modo de pago (recomendado: plan, salvo Free):
    - **Plan** (`modo = "plan"`, por defecto): usa la sesión de Claude Code de esta máquina. No hay cobros
      aparte, pero consume los mismos límites de uso que su Claude Code interactivo; una corrida larga o con mucho
      paralelo puede dejarlo sin uso esa semana. Los "$" del tablero son un equivalente a precios de API.
      Si elige plan, sugiere `paralelo = 2` y Sonnet en `[modelos]` planificador y revisor para que rinda.
    - **API** (`modo = "api"`): usa la API key guardada en un archivo aparte (`api_env`, por defecto
      `~/.config/loopeable/api.env`, chmod 600). Sirve para los créditos mensuales de API que incluyen Max/Ultra
      (se activan en claude.ai → Configuración → Facturación → "Vincular organización", y la key se crea en
      platform.claude.com). No cuentan contra su plan, no se acumulan de un mes a otro y, si se acaban, la API deja
      de responder hasta el siguiente ciclo (sin cobros sorpresa). Aquí el tope `usd` es dinero real.
    Nunca escribas la key en loopeable.toml ni la pongas en su `~/.zshrc`/`~/.bashrc`: si `ANTHROPIC_API_KEY`
    queda global, su Claude Code interactivo también la usaría. Si elige API y el archivo no existe, dale los
    comandos para crearlo (`install -m 600 /dev/null <ruta>` y que él pegue la key; tú no la pidas en el chat).
11. **Perfil**: propón uno según el repo — `security-suite`, `python`, `firmware-esp32` o `generico` — o una ruta a un
    `.md` propio con secciones `## Contexto` y `## Revisión`.

Escribe `loopeable.toml` (formato: `loopeable iniciar` crea una plantilla comentada) y la bandeja. Muestra el archivo,
y con OK del usuario haz commit de `loopeable.toml` (loopeable exige el árbol limpio para poder deshacer).

## 2. Plan

`loopeable -C <carpeta> planear` → muestra `.loopeable/TABLERO.md`. Resume en el chat: cuántas tareas, las de
prioridad 1, las ❓ que esperan decisión y lo que el planificador descartó (`loopeable ver plan`).
Con el OK del usuario: `loopeable aprobar todas` (o solo los IDs que elija).

## 3. Lanzar

Una corrida dura horas: **no** la corras en primer plano en esta sesión.
- Aquí: lánzala en segundo plano (`loopeable -C <carpeta> correr > .loopeable/corrida.log 2>&1`) y dile al usuario
  que puede cerrar la sesión pero no apagar la máquina.
- Docker: `PROYECTO=<carpeta> docker compose -f <loopeable>/docker/compose.yml run --rm loopeable correr`.
- Server: `sudo systemctl start loopeable@<proyecto>`.

## 4. Seguimiento (cuando el usuario pregunte)

- `loopeable estado` — tablero; `loopeable ver T03` — detalle y eventos de una tarea.
- ❓ DECISIÓN: muéstrale la pregunta, y con su respuesta `loopeable responder T03 "<respuesta>"` y vuelve a correr.
- ❌ FALLÓ / 🧱 ESTANCADA: lee `.loopeable/sesiones/*-T03-*.md`, explica por qué en dos líneas y ofrece
  `loopeable reintentar T03` (quizá tras ajustar la tarea o el perfil).
- Parar: `loopeable parar` (termina las sesiones en curso y se detiene limpio).
- Al terminar: la rama de integración (`loopeable/<fecha>`) tiene un commit por tarea; `main` no se tocó. Muestra
  `git log --oneline main..<rama>` y `LOOPEABLE-APRENDIZAJES.md`. El merge a main lo decide el usuario.

## Señales de alarma

| Pensamiento | Realidad |
|---|---|
| "Lo corro en primer plano para ver" | Se corta a los minutos y deja worktrees colgando. Segundo plano o Docker. |
| "Le subo el tope para que termine" | Pregunta. El tope es la única protección contra un loop caro. |
| "Quito la ruta prohibida para que avance" | Si una tarea necesita tocar .env o CI, es una DECISIÓN del usuario. |
| "Hago merge a main, ya pasó todo" | Nunca: loopeable entrega una rama; el merge es del usuario. |
| "La tarea dice HECHA, entonces funciona" | HECHA = pasó pruebas y revisión. Si el repo tiene pocas pruebas, dilo. |
