# PENDIENTES — eliminar al finalizar

> ⚠️ **Este archivo es temporal.** Bórralo (y su mención en este encabezado) cuando todo esté resuelto, antes de la
> versión 1.0. Lo dejé al entregarte la v0.1 el 2026-11-26.

## Estado de la v0.1

- ✅ Orquestador completo: planear → loops en paralelo (worktrees) → verificar sin IA → puerta de seguridad →
  revisor con subagentes → corregir → commit → integrador → rama `loopeable/<fecha>`.
- ✅ Subtareas (loops que crean loops) con tope de profundidad y total; dependencias entre tareas.
- ✅ Vigía (otro enfoque si se repite el error, ESTANCADA a la tercera) y `LOOPEABLE-APRENDIZAJES.md`.
- ✅ Frenos en código: USD, horas, `parar`, rutas prohibidas / solo lectura, comandos peligrosos (hook PreToolUse).
- ✅ Estado SQLite reanudable, `TABLERO.md`, bitácora por sesión en `.loopeable/sesiones/`.
- ✅ CLI, skill `/loopeable` con entrevista, plugin, 4 perfiles, ejemplo para security-suite con tus 6 puntos.
- ✅ Docker + firewall, systemd para el server, avisos ntfy/Telegram, PR en borrador opcional.
- ✅ 12 pruebas con IA falsa (`uv run --extra dev pytest -q`) + CI.

## 1. Lo primero (no se pudo probar aquí)

- [ ] **Corrida real con Claude.** Donde lo construí no había credenciales: nunca corrió contra el SDK de verdad.
      Haz la "Primera prueba real" del README (tope de 1 USD) y revisa `.loopeable/sesiones/*.md`. Confirmar:
  - [ ] que `structured_output` llega lleno con `output_format` json_schema en cada rol (si llega `None`, el loop
        lo trata como error; ver `ia.py` y `orquestador.py`);
  - [ ] que `permission_mode="dontAsk"` + `allowed_tools` deja trabajar al implementador sin pedir permisos, y
        que los subagentes (herramienta `Task`) sí se lanzan;
  - [ ] que el hook de `frenos.py` realmente niega (prueba pidiéndole a un agente `git push` o leer `.env`);
  - [ ] que `max_budget_usd` corta la sesión y que `total_cost_usd` incluye lo gastado por los subagentes;
  - [ ] que los nombres de modelo de `[modelos]` en `config.py` son válidos para tu cuenta.
- [ ] **Construir la imagen de Docker** (aquí no había daemon): `docker compose -f docker/compose.yml build` y una
      corrida con `LOOPEABLE_FIREWALL=1`. Revisar `entrada.sh`: `usermod/groupmod` cuando el UID ya existe,
      `setpriv`, y que el firewall no bloquee algo que el SDK necesita (agregar dominios en
      `LOOPEABLE_DOMINIOS_EXTRA` o en `firewall.sh`).
- [ ] **Revisión independiente del código.** La empecé con un agente aparte y la corté para entregarte el repo.
      Córrela en tu terminal con este prompt:
      > Revisa src/loopeable/ sin modificarlo: carreras en la orquestación async (lock, sqlite, worktrees), que nada
      > toque `main` ni pierda trabajo, qué pasa con Freno a media corrida y al reanudar, huecos reales en
      > frenos.py, uso correcto de ClaudeAgentOptions (lee types.py del SDK instalado) y si docker/ funciona.
      > Archivo:línea, escenario concreto, severidad y arreglo mínimo.

## 1b. Corrida real 2026-11-26 (/tmp/prueba-loop: 3/3 tareas, 2.66 USD equivalentes del plan)

Funcionó de punta a punta con Claude real: plan, subtarea creada por un loop, rechazo del revisor y corrección,
tope de presupuesto, reanudar. Bugs que salieron (el prompt completo para arreglarlos está en el chat):
- [x] 1. El tope se pasa (1.14/1): mínimo de 0.05 por sesión y paralelo que recibe todo el restante. → `8609508`
- [x] 2. Error "maximum budget" del SDK cuenta como intento; debe ser Freno. → `37ace08`
- [x] 3. Al volver a PENDIENTE por Freno, `intentos` no se reinicia. → `c8e78de`
- [x] 4. No se registra el motivo de cada rechazo (revisor / seguridad / pruebas) en eventos ni en el tablero. → `1d71467`
- [x] 5. La verificación crea __pycache__/.pytest_cache y se commitean (el revisor lo rechazó). → `914643f`
- [x] 6. Las pruebas se detectan una sola vez al arrancar; en repo vacío no incluyen pytest. → `98cfdd1`
- [x] 7. Si .loopeable/ quedó versionado, mover la bandeja deja el árbol sucio y la siguiente corrida no arranca. → `98cf27d`
- [x] 8. Revisión proporcional: un .gitignore costó 1.25 USD en 3 intentos por revisar siempre con Opus + 3 subagentes. → `c161126`
- Decisiones tomadas al arreglarlos (rama `arreglos-corrida-real`), revisar:
  - [ ] `usd_minimo_sesion` se recorta a `usd` si el tope total es menor (si no, nada correría nunca).
  - [ ] "maximum budget" solo es Freno si el tope de la sesión venía del saldo de la corrida; si lo que cortó fue
        `usd_por_sesion` (sobra saldo), sigue contando como intento fallido (la tarea no cabe en una sesión).
  - [ ] Con el piso del mínimo, N loops en paralelo pueden pasarse del restante hasta (N−1)×`usd_minimo_sesion`
        (p. ej. quedan 0.50, 3 loops → 0.25 cada uno). Mejor: reservar saldo por sesión al arrancarla.
  - [ ] Tras un Freno por la parte del saldo de un loop, si todavía queda ≥ mínimo, la misma tarea se relanza
        enseguida con su parte nueva. Acotado por el tope, pero puede repetir trabajo.
  - [ ] El chequeo de sintaxis usa `compile()` en vez de `py_compile` (que escribe .pyc aunque esté
        PYTHONDONTWRITEBYTECODE). Ojo: tu shell exporta PYTHONDONTWRITEBYTECODE=1, por eso aquí no se veía el bug 5;
        las pruebas lo quitan con monkeypatch.
  - [ ] Si `[hecho] pruebas` tiene comandos explícitos, no se vuelven a detectar (el usuario manda).
  - [ ] La puerta de seguridad sigue usando el modelo `[modelos] revisor` sin importar el tamaño del diff.
  - [ ] Un archivo binario cuenta como archivo pero 0 líneas para el umbral de diff chico.
  - [ ] Repetir la corrida real (/tmp/prueba-loop desde cero, tope 1 USD) para confirmar los 8 arreglos con Claude.
- [x] Entrevista pregunta con qué se paga: `[cuenta] modo = "plan" | "api"` (key en archivo aparte, chmod 600).
- [x] Entrevista pregunta el tipo de plan (`[cuenta] plan`): Free se niega con modo plan; avisos y sugerencias por plan.
- [ ] Revisar de vez en cuando la tabla de planes de SKILL.md (qué incluye cada plan cambia; fuente: claude.com/pricing
      y support.claude.com, artículos de Claude Code por plan y de créditos mensuales de API).

## 2. Limitaciones conocidas de la v0.1

- [ ] Si se cumple un freno (USD/horas/parar) a media tarea, el trabajo sin commit de ese worktree se descarta y la
      tarea vuelve a PENDIENTE desde cero. Mejor: guardar un commit WIP en su rama y retomarlo.
- [ ] Si el integrador no resuelve un conflicto, la tarea queda FALLÓ. Mejor: reintentarla sobre la base nueva.
- [ ] Una fuente tipo `PENDIENTES.md` se vuelve a planear entera cuando cambia (el planificador ve las tareas
      existentes y no debería duplicarlas, pero gasta). Mejor: mandar solo el diff de la fuente.
- [ ] Con el árbol sucio no arranca; la skill hace commit de `loopeable.toml`, pero a mano hay que hacerlo.
- [ ] `entrega.pr` dentro de Docker no funciona: la imagen no trae `gh` ni credenciales de push. Pasar `GH_TOKEN`
      e instalar `gh`, o entregar el PR desde el host.
- [ ] El firewall resuelve las IP una sola vez al arrancar; corridas de muchas horas pueden perder dominios con IP
      rotativa. Re-resolver cada hora o usar un proxy con lista de dominios.
- [ ] `frenos.py` filtra comandos con regex: atrapa los errores honestos de un agente, no a uno que intente
      esconderse (p. ej. un script que arma `git push` en otro lenguaje). Docker es la caja real; documentarlo.
- [ ] Las lecciones se commitean en la rama de integración; si nunca se hace merge, no llegan a la siguiente rama.
      Considerar guardarlas también en `.loopeable/` o en el perfil.
- [ ] `config.PLANTILLA` (la de `loopeable iniciar`) no muestra `[rutas]` ni `[modelos]`.
- [ ] Solo Linux/macOS (bash, git worktrees). Windows: probar con WSL.

## 3. Lo que sigue (roadmap acordado)

- [ ] v0.2 — Replaneación a media corrida (tareas nuevas en la bandeja sin reiniciar), tablero web de solo lectura
      detrás de Cloudflare Access, métricas por tarea (costo, vueltas, motivo de rechazo, modelo).
- [ ] v0.3 — Fuentes: issues de GitHub con etiqueta `loopeable` y una base de Notion. Aprobar planes y contestar
      decisiones desde el celular (Telegram o comentario "ok" en el PR).
- [ ] v0.4 — Recetas listas: arreglar CI hasta que pase, subir cobertura, actualizar dependencias una por una,
      documentar módulos, traducir README, vaciar la bandeja de security-suite. Modo "cada X tiempo" (como /loop)
      y modo noche con tarea programada.
- [ ] v1.0 — Banco de pruebas con tareas de resultado conocido (como el fixture de 28 fallas de security-suite)
      para medir que nunca dé por HECHA una tarea que no pasó y para comparar modelos. Más perfiles. Estimado de
      costo del plan antes de aprobar. Puntos de control (tag por tarea). Varios repos en una corrida. Motor
      "interno" con Stop hook para loops cortos dentro de la sesión.

## 4. Integración con security-suite

- [ ] Copiar `ejemplos/security-suite/loopeable.toml` a la raíz de la suite, commit, copiar la bandeja a
      `.loopeable/bandeja/` y correr `loopeable planear`. Revisar el plan (deberían salir X10 webhooks y X11
      chatbot como prioridad 1) antes de `aprobar`.
- [ ] Decidir si la puerta de seguridad de loopeable usa la suite para revisar los cambios de cualquier proyecto
      (`[puertas] seguridad = "<ruta a la suite>"`). Probarla primero en un repo chico: es la sesión más cara.
- [ ] La carpeta `maidros/` que armé antes dentro de tu clon de security-suite quedó obsoleta (Maidros es otro
      proyecto): no la subas.
