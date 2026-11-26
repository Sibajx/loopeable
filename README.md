# 🔁 loopeable

[English](README.en.md) · **Español**

**Deja a Claude Code trabajando.** Un loop que orquesta loops: le das un objetivo e información, y loopeable la
convierte en tareas, corre un loop por tarea (varios en paralelo, cada uno con sus agentes y subagentes), verifica,
revisa, integra y sigue hasta terminar o topar un límite. Te avisa al celular cuando necesita algo.

```
/loopeable  →  entrevista  →  loopeable.toml
                                  │
ORQUESTADOR (código, no modelo: límites, frenos, git, estado)
  │
  ├─ planificador ── subagentes: explorador ×N, investigador
  │      └─ tareas con criterios, prioridad y dependencias  → 📝 esperan tu OK
  │
  ├─ loop T01 (worktree propio) ─┐
  ├─ loop T02 (worktree propio) ─┼─ en paralelo
  └─ loop T03 …                  ┘
        implementador ── subagentes: explorador, investigador, probador
          → verificar (tus pruebas, sin IA)
          → puerta de seguridad (security-suite, opcional)
          → revisor ── subagentes en paralelo: correctitud · seguridad · consistencia (solo si el cambio es grande)
          → ¿rechazado? vuelve con la retroalimentación concreta
          → commit → integrador (resuelve choques con otros loops) → rama de integración
        ↳ descubre algo que falta → subtarea → otro loop
  vigía: si un loop repite el mismo error propone otro camino; al terminar guarda una lección
```

## Por qué así

- **El control vive en código.** Presupuesto, tiempo, intentos, profundidad, rutas prohibidas y comandos peligrosos
  los revisa loopeable (con un hook `PreToolUse` del Agent SDK), no el modelo. Un agente no se puede "saltar" un
  límite aunque lo intente.
- **"Hecho" lo deciden tus pruebas,** no el modelo diciendo que terminó. El revisor (que cuesta) solo entra si las
  pruebas ya pasaron, y no es la misma sesión que escribió el código.
- **Nada se pierde ni se ensucia.** Cada loop trabaja en su propio `git worktree`; lo que pasa se integra con un
  commit por tarea en la rama `loopeable/<fecha>`; lo que falla se descarta. `main` no se toca.
- **Aprende.** `LOOPEABLE-APRENDIZAJES.md` guarda una lección por tarea difícil; el planificador y los
  implementadores la leen en la siguiente corrida.
- **Reanudable.** Estado en SQLite (`.loopeable/estado.db`). Si se corta la luz, vuelves a correrlo y sigue.

## Instalación

```bash
uv tool install git+https://github.com/Sibajx/loopeable        # el comando `loopeable`
```
Como plugin de Claude Code (para la entrevista con `/loopeable`):
```
/plugin marketplace add Sibajx/loopeable
/plugin install loopeable@loopeable
```
Necesita git, Python ≥ 3.11 y Claude Code con sesión iniciada (usa tu plan), o una API key en un archivo aparte
(`[cuenta] modo = "api"`). En Docker o en un server sin sesión: `CLAUDE_CODE_OAUTH_TOKEN` (de `claude setup-token`,
tu plan) o `ANTHROPIC_API_KEY`. Cada quien corre loopeable con su propia cuenta: no lo uses para mandar
solicitudes de otras personas con tus credenciales.

## Uso

En Claude Code, dentro del proyecto: **`/loopeable`** (o "deja a Claude trabajando en esto…"). Te pregunta carpeta,
objetivo, de dónde sale el trabajo, qué es "hecho", hasta dónde, qué no tocar, puertas y avisos; escribe
`loopeable.toml`, te muestra el plan y lo lanza.

A mano:
```bash
loopeable iniciar                 # plantilla de loopeable.toml
echo "- agregar X…" > .loopeable/bandeja/ideas.md
git add loopeable.toml && git commit -m "loopeable"
loopeable planear                 # tareas propuestas en .loopeable/TABLERO.md
loopeable aprobar todas
loopeable correr                  # horas: en segundo plano, tmux, Docker o server
loopeable estado                  # tablero en texto
loopeable tablero                 # página con el avance en vivo: http://127.0.0.1:8787
loopeable ver T03                 # detalle y eventos
loopeable responder T03 "Mercado Pago"   # contesta una ❓ decisión
loopeable reintentar T05
loopeable parar                   # alto limpio
```
¿Llegó más información? Otro `.md` a `.loopeable/bandeja/` y `loopeable correr`: solo procesa lo nuevo.

## Configuración (`loopeable.toml`)

| Sección | Qué controla | Por defecto |
|---|---|---|
| `objetivo`, `perfil`, `fuentes` | qué se busca, cómo es "bien hecho" en este repo, de dónde salen tareas | `generico`, `["bandeja"]` |
| `[hecho]` | `pruebas` (comandos que deben salir 0; vacío = se detectan), `criterios` globales | detectadas |
| `[limites]` | `usd`, `usd_por_sesion`, `usd_minimo_sesion` (con menos saldo no arranca ninguna sesión; el restante se reparte entre los loops en curso), `horas`, `intentos`, `tareas`, `profundidad`, `paralelo`, `diff_chico_lineas` y `diff_chico_archivos` (un cambio hasta ese tamaño lo revisa el modelo del implementador sin subagentes) | 20 · 4 · 0.25 · 6 · 3 · 40 · 2 · 4 · 40 · 3 |
| `[modelos]` | modelo por rol: planificador, implementador, revisor, integrador, vigía, subagentes | Opus para planear y revisar, Sonnet para implementar, Haiku para el vigía |
| `[rutas]` | `prohibidas` (ni leer ni escribir: secretos), `solo_lectura` (CI, .git; también vale para Bash), `permitidas` | secretos · CI · .git · `.claude/`, `.mcp.json`, `CLAUDE.md` y `loopeable.toml` siempre |
| `[puertas]` | `aprobar_plan`, `seguridad` (ruta a security-suite), `bloquear_en` | sí · apagada · 🔴 |
| `[entrega]` | `rama`, `pr` (push de la rama + PR en borrador con `gh`) | `loopeable/{fecha}` · no |
| `[cuenta]` | `modo`: `plan` (tu suscripción; los "$" son equivalente de API) o `api` (la key de `api_env`, p. ej. los créditos de API de Max/Ultra/Team); `plan`: free/pro/max/ultra/team/enterprise, para sugerir límites y avisar (Free no incluye Claude Code: solo `api`) | `plan` |
| `[avisos]` | `ntfy`, `telegram_token_env`, `telegram_chat` | apagados |

Perfiles incluidos: `generico`, `python`, `security-suite`, `firmware-esp32`. Uno propio es un `.md` con secciones
`## Contexto` y `## Revisión`.

## Frenos

| Freno | Qué pasa |
|---|---|
| Tope de USD / horas | Ninguna sesión nueva arranca; las tareas en curso vuelven a pendiente; resumen y aviso. |
| `loopeable parar` | Igual, a mano. |
| Mismo error 2 veces | El vigía propone otro enfoque. 3 veces → 🧱 ESTANCADA. |
| Ruta prohibida / solo lectura | La herramienta se niega con el motivo; el agente sigue o pide DECISIÓN. |
| `git push/commit/reset`, `sudo`, despliegues, publicar paquetes, leer `.env`, `curl \| sh` | Negados siempre a los agentes. |
| Algo que solo tú decides | ❓ DECISIÓN: la tarea espera, las demás siguen, te llega un aviso. |

**Corre los agentes dentro de Docker** si el proyecto tiene algo valioso cerca: los agentes tienen Bash.
`docker/` trae una imagen que solo ve el proyecto montado, corre sin privilegios y, con el firewall, solo sale a
Anthropic, GitHub, PyPI y npm:
```bash
PROYECTO=$PWD docker compose -f ~/loopeable/docker/compose.yml run --rm loopeable correr
```
Para dejarlo 24/7 en un server con systemd y avisos al celular: [`despliegue/SERVER.md`](despliegue/SERVER.md).

## Ejemplo: hacer crecer security-suite

[`ejemplos/security-suite/`](ejemplos/security-suite) trae el `loopeable.toml` (con las pruebas del CI de la suite y
`owasp/` como solo lectura) y una bandeja con 6 mejoras: webhooks de pago falsos, inyección al chatbot, respaldos
inmutables, logs, fuerza bruta de códigos cortos y un modo rápido para apps hechas con IA.

## Primera prueba real (5 minutos, centavos)

```bash
mkdir /tmp/prueba-loop && cd /tmp/prueba-loop && git init -q
printf 'objetivo = "Una calculadora mínima en Python con pruebas"\nperfil = "python"\n[limites]\nusd = 1\n[puertas]\naprobar_plan = false\n' > loopeable.toml
git add -A && git commit -qm inicio            # primero el commit: .loopeable/ no debe entrar a git
mkdir -p .loopeable/bandeja && echo "- calc.py con suma y resta, y tests/test_calc.py con pytest" > .loopeable/bandeja/ideas.md
loopeable correr && git log --oneline --all
```
Si `.loopeable/` ya había quedado versionado, loopeable lo saca de git con un commit en su rama (nunca en `main`).

## Pruebas

`uv run --extra dev pytest` corre el orquestador completo con una IA falsa (`tests/ia_falsa.py`): loops en
paralelo, choque de merge resuelto por el integrador, subtareas creadas por un loop, dependencias, tarea estancada,
decisión, revisor que rechaza, tope de presupuesto y frenos. No gasta nada.

## Lo que sigue

v0.2 replaneación a media corrida y tablero web · v0.3 issues de GitHub y Notion como fuentes, aprobar desde el
celular · v0.4 recetas (arreglar CI, subir cobertura, actualizar dependencias…) y banco de pruebas para comparar
modelos.

> ⚠️ loopeable automatiza, no garantiza. Revisa la rama antes de hacer merge, sobre todo si el proyecto tiene pocas
> pruebas: una tarea HECHA pasó tus pruebas y una revisión, no más.

Licencia MIT.
