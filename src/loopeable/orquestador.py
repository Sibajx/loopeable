"""El loop que orquesta loops.

  planear ──► tareas ──► hasta N loops en paralelo, cada uno en su worktree:
                           implementador (+ subagentes) → verificar (sin IA) → puerta de seguridad →
                           revisor (+ subagentes en paralelo) → corregir … → commit → integrar
                           └─ subtareas descubiertas → nuevas tareas → nuevos loops
  vigía: estrategia nueva cuando un loop repite el mismo error; lección al terminar cada tarea.
Todos los límites los revisa este código, no el modelo.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import avisos, frenos, git_ops, ia, roles
from .config import avisos_plan, entorno_cuenta as config_entorno
from .estado import Estado
from .verificar import detectar_pruebas, huella, verificar

APRENDIZAJES = "LOOPEABLE-APRENDIZAJES.md"


class Freno(Exception):
    """Un límite global se cumplió: la tarea vuelve a PENDIENTE y la corrida termina limpio."""


class Orquestador:
    def __init__(self, raiz: Path, cfg: dict, log=print):
        self.raiz, self.cfg, self.log = Path(raiz).resolve(), cfg, log
        raiz = self.raiz
        self.dir = raiz / ".loopeable"
        self.est = Estado(self.dir)
        self.lock = asyncio.Lock()
        self.inicio = time.time()
        self.L, self.M = cfg["limites"], cfg["modelos"]
        self.pruebas = cfg["hecho"]["pruebas"] or detectar_pruebas(raiz)
        self.perfil_ctx, self.perfil_rev = roles.perfil(cfg["perfil"], raiz)
        self.rama = self.est.meta("rama") or cfg["entrega"]["rama"].format(fecha=time.strftime("%Y-%m-%d_%H%M"))
        self.n_sesion = 0
        self.env = config_entorno(cfg)
        for aviso in avisos_plan(cfg):
            self.log(f"⚠️  {aviso}")
        if cfg["cuenta"]["modo"] == "plan" and os.environ.get("ANTHROPIC_API_KEY"):
            self.log("⚠️  [cuenta] modo = \"plan\", pero ANTHROPIC_API_KEY está definida en tu terminal: el SDK la "
                     "usará y se cobrará a la API. Quítala (unset ANTHROPIC_API_KEY) si quieres usar tu plan.")

    # ───────────────────── utilidades ─────────────────────

    def restante(self) -> float:
        return self.L["usd"] - self.est.gasto_total()

    def minimo_sesion(self) -> float:
        """Saldo mínimo para arrancar una sesión (nunca más que el tope total, o nada correría)."""
        return min(self.L["usd_minimo_sesion"], self.L["usd"])

    def freno(self) -> str | None:
        if (self.dir / "PARAR").exists():
            return "pediste parar (.loopeable/PARAR)"
        if self.est.gasto_total() >= self.L["usd"] or self.restante() < self.minimo_sesion():
            return (f"presupuesto agotado ({self.est.gasto_total():.2f}/{self.L['usd']} USD; quedan "
                    f"{max(0.0, self.restante()):.2f}, menos que el mínimo por sesión de {self.minimo_sesion():.2f})")
        if time.time() - self.inicio >= self.L["horas"] * 3600:
            return f"límite de tiempo ({self.L['horas']} h)"
        return None

    def aprendizajes(self) -> str:
        p = self.raiz / APRENDIZAJES
        if not p.exists():
            return "(todavía ninguno)"
        lineas = [l for l in p.read_text().splitlines() if l.startswith("- ")]
        return "\n".join(lineas[-40:]) or "(todavía ninguno)"

    async def sesion(self, rol: str, prompt: str, cwd: Path, tid: str, herramientas: list[str], editar: bool,
                     esquema: dict | None, subagentes: list[str] | None = None, plugins: list[str] | None = None,
                     modelo: str | None = None, etiqueta: str = "") -> ia.Resultado:
        motivo = self.freno()
        if motivo:
            raise Freno(motivo)
        # El saldo se reparte entre los loops en curso: si cada sesión en paralelo recibiera todo el restante,
        # juntas se pasarían del tope. Piso en el mínimo (freno() ya garantizó que el restante lo cubre).
        activos = max(1, sum(t["estado"] == "EN_CURSO" for t in self.est.todas()))
        usd_max = min(self.L["usd_por_sesion"], max(self.minimo_sesion(), self.restante() / activos))
        s = ia.Sesion(
            rol=rol, prompt=prompt, cwd=cwd, modelo=modelo if modelo is not None else self.M.get(rol, ""),
            herramientas=herramientas, editar=editar, esquema=esquema,
            subagentes=roles.subagentes(subagentes, self.M.get("subagentes", ""), herramientas) if subagentes else None,
            plugins=plugins or [],
            hook_pre=frenos.hook(cwd, self.cfg["rutas"], lambda h, m: self.est.evento(tid, "negado", f"{h}: {m}")),
            usd_max=usd_max, turnos_max=self.L["turnos_por_sesion"],
            env=self.env)
        r = await ia.correr(s)
        if tid.startswith("T"):
            self.est.sumar_costo(tid, r.costo)
        else:
            self.est.sumar_costo_extra(r.costo)
        self.n_sesion += 1
        carpeta = self.dir / "sesiones"
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / f"{self.n_sesion:04d}-{tid}-{rol}.md").write_text(
            f"# {tid} · {rol} · {r.costo:.3f} USD · {r.turnos} turnos{' · ERROR ' + r.error if r.error else ''}\n\n"
            f"## Prompt\n{prompt}\n\n## Respuesta\n{r.texto}\n\n## Datos\n{r.datos}\n")
        self.est.evento(tid, rol, f"{r.costo:.3f} USD" + (f" · {etiqueta}" if etiqueta else "") +
                        (f" · error: {r.error}" if r.error else ""))
        # El SDK cortó la sesión por max_budget_usd. Si el tope venía del saldo de la corrida (no de usd_por_sesion),
        # es el presupuesto global el que se acabó: Freno, no un intento fallido.
        if "maximum budget" in r.error.lower() and usd_max < self.L["usd_por_sesion"]:
            raise Freno(f"la sesión de {rol} topó su parte del saldo ({usd_max:.2f} USD)")
        return r

    def _rechazo(self, tid: str, motivo: str):
        """Por qué se rechazó un intento: evento `rechazo` (ver / tablero) y nota de la tarea mientras siga en curso."""
        self.est.evento(tid, "rechazo", motivo)
        self.est.cambiar(tid, nota=motivo[:1000])

    def tablero(self):
        marca = {"HECHA": "✅", "PENDIENTE": "⏳", "EN_CURSO": "🔄", "PROPUESTA": "📝", "DECISIÓN": "❓",
                 "FALLÓ": "❌", "ESTANCADA": "🧱", "NO_PUDE": "⚠️"}
        ts = self.est.todas()
        L = [f"# Tablero de loopeable — {self.rama}", "",
             f"Actualizado: {time.strftime('%Y-%m-%d %H:%M:%S')} · gasto {self.est.gasto_total():.2f}/"
             f"{self.L['usd']} USD · {sum(t['estado'] == 'HECHA' for t in ts)}/{len(ts)} tareas hechas", "",
             "| | ID | Tarea | Prio | Intentos | USD | Nota |", "|---|---|---|---|---|---|---|"]
        for t in ts:
            nota = (t["nota"] or "").replace("|", "/").replace("\n", " ")[:120]
            L.append(f"| {marca.get(t['estado'], '·')} | {t['id']} | {t['titulo'][:70]} | {t['prioridad']} | "
                     f"{t['intentos']} | {t['costo']:.2f} | {nota} |")
        (self.dir / "TABLERO.md").write_text("\n".join(L) + "\n")

    # ───────────────────── preparar ─────────────────────

    def preparar(self):
        if not git_ops.es_repo(self.raiz):
            raise SystemExit(f"{self.raiz} no es un repo de git: loopeable necesita git para aislar y deshacer.")
        git_ops.excluir_carpeta_estado(self.raiz)
        if git_ops.sucio(self.raiz):
            raise SystemExit("Hay cambios sin commit. Haz commit (incluido loopeable.toml) antes de correr loopeable.")
        git_ops.preparar_rama(self.raiz, self.rama)
        self.est.poner_meta("rama", self.rama)
        try:
            fuera = git_ops.sacar_estado_de_git(self.raiz)
            if fuera:
                self.log(f"🧹 .loopeable/ estaba en git ({len(fuera)} archivos); lo saqué con un commit en {self.rama} "
                         "(main no se toca). Ya está en .git/info/exclude.")
        except git_ops.ErrorGit as e:
            self.log(f"⚠️  {e}")
        for t in self.est.todas():                     # una corrida anterior se cortó a la mitad
            if t["estado"] == "EN_CURSO":
                self.est.cambiar(t["id"], estado="PENDIENTE", intentos=0)
        git_ops.git(self.raiz, "worktree", "prune", check=False)
        (self.dir / "PARAR").unlink(missing_ok=True)

    # ───────────────────── loop externo: planear ─────────────────────

    def _fuentes(self) -> list[Path]:
        r = []
        for f in self.cfg["fuentes"]:
            if f == "bandeja":
                (self.dir / "bandeja").mkdir(parents=True, exist_ok=True)
                r += sorted((self.dir / "bandeja").glob("*.md"))
            elif (self.raiz / f).is_file():
                r.append(self.raiz / f)
        return r

    async def planear(self) -> list[str]:
        nuevas = []
        for p in self._fuentes():
            texto = p.read_text()
            h = hashlib.sha1(texto.encode()).hexdigest()
            if self.est.fuente_vista(str(p), h) or not texto.strip():
                continue
            self.log(f"📥 Planeando con {p.name}")
            existentes = "\n".join(f"- {t['id']} · {t['titulo']} ({t['estado']})" for t in self.est.todas())
            prompt = roles.plantilla(
                "planificador", raiz=self.raiz, objetivo=self.cfg["objetivo"], perfil_contexto=self.perfil_ctx,
                aprendizajes=self.aprendizajes(), tareas=existentes or "(ninguna)", fuente=p.name, info=texto,
                pruebas=" ; ".join(self.pruebas) or "(ninguna)")
            r = await self.sesion("planificador", prompt, self.raiz, "plan", roles.LECTURA + ["WebSearch", "WebFetch"],
                                  False, roles.ESQUEMA_PLAN, roles.PARA_PLANEAR)
            if r.error or not isinstance(r.datos, dict):
                self.log(f"   ⚠️  el planificador falló: {r.error or 'sin JSON'}; {p.name} se queda para la próxima")
                continue
            por_titulo = {}
            estado_inicial = "PROPUESTA" if self.cfg["puertas"]["aprobar_plan"] else "PENDIENTE"
            for t in r.datos.get("tareas", []):
                if len(self.est.todas()) >= self.L["tareas"]:
                    self.log(f"   tope de {self.L['tareas']} tareas: el resto del plan se descarta")
                    break
                prueba = (t.get("prueba") or "").strip()
                bloqueo = frenos.comando_bloqueado(prueba, self.raiz, self.cfg["rutas"]["prohibidas"]) if prueba else None
                if bloqueo:
                    self.log(f"   ⚠️  la prueba propia de «{t['titulo']}» se descarta: {bloqueo}")
                    self.est.evento("plan", "prueba-bloqueada", f"{t['titulo']}: {bloqueo}")
                    prueba = ""
                por_titulo[t["titulo"]] = self.est.nueva(
                    t["titulo"], roles.cuerpo_tarea(t), int(t.get("prioridad", 2)), origen=p.name,
                    estado="DECISIÓN" if t.get("decision") else estado_inicial, prueba=prueba)
                if t.get("decision"):
                    self.est.cambiar(por_titulo[t["titulo"]], nota=t["decision"])
            for t in r.datos.get("tareas", []):
                if t["titulo"] in por_titulo:
                    deps = [por_titulo.get(d, d) for d in t.get("depende_de", []) if por_titulo.get(d, d) != por_titulo[t["titulo"]]]
                    self.est.cambiar(por_titulo[t["titulo"]], depende=[d for d in deps if re.fullmatch(r"T\d+", d)])
            for d in r.datos.get("descartado", []):
                self.est.evento("plan", "descartado", d)
            self.est.marcar_fuente(str(p), h)
            if p.parent == self.dir / "bandeja":
                (p.parent / "procesadas").mkdir(exist_ok=True)
                p.rename(p.parent / "procesadas" / p.name)
            nuevas += por_titulo.values()
            for tid in por_titulo.values():
                t = self.est.tarea(tid)
                self.log(f"   + {tid} [{t['prioridad']}] {t['titulo']}" + ("  ❓" if t["estado"] == "DECISIÓN" else ""))
        self.tablero()
        return nuevas

    # ───────────────────── loop interno: una tarea ─────────────────────

    async def loop_tarea(self, tid: str) -> str:
        t = self.est.tarea(tid)
        wt = self.dir / "worktrees" / tid
        rama_t = f"{self.rama}--{tid}"
        async with self.lock:
            git_ops.crear_worktree(self.raiz, self.rama, wt, rama_t)
        base = git_ops.git(wt, "rev-parse", "HEAD")
        # La prueba propia viene de su columna (la llena solo el planificador) y pasa otra vez por los frenos:
        # se ejecuta con bash -c, fuera del hook.
        prueba = t.get("prueba") or ""
        prueba_propia = [prueba] if prueba and not frenos.comando_bloqueado(
            prueba, self.raiz, self.cfg["rutas"]["prohibidas"]) else []

        def comandos_ahora() -> list[str]:
            # Sin [hecho] pruebas, se detectan en el worktree cada vez: en un repo nuevo tests/ aparece a media tarea.
            return (self.cfg["hecho"]["pruebas"] or detectar_pruebas(wt)) + prueba_propia

        retro, huellas, historia, resultado = "", [], [], "FALLÓ"
        self.log(f"🔁 {tid} · {t['titulo']}")
        try:
            for intento in range(1, self.L["intentos"] + 1):
                self.est.cambiar(tid, intentos=intento)
                comandos = comandos_ahora()
                prompt = roles.plantilla(
                    "implementador", cwd=wt, perfil_contexto=self.perfil_ctx, aprendizajes=self.aprendizajes(),
                    tid=tid, titulo=t["titulo"], intento=intento, intentos=self.L["intentos"], cuerpo=t["cuerpo"],
                    criterios_globales="\n".join(f"- {c}" for c in self.cfg["hecho"]["criterios"]) or "- (ninguno)",
                    retro=f"\n## Por qué se rechazó el intento anterior\n{retro}\n" if retro else "",
                    pruebas=" ; ".join(comandos) or "(no hay; prueba a mano lo que hiciste)")
                r = await self.sesion("implementador", prompt, wt, tid, roles.TRABAJO, True,
                                      roles.ESQUEMA_IMPLEMENTAR, roles.PARA_IMPLEMENTAR)
                if r.error:
                    historia.append(f"intento {intento}: la sesión falló ({r.error[:200]})")
                    self._rechazo(tid, f"implementador: la sesión falló: {r.error[:500]}")
                    retro = f"La sesión anterior se cortó con un error: {r.error[:500]}. Continúa desde lo que hay."
                    continue
                d = r.datos if isinstance(r.datos, dict) else {}
                self._subtareas(t, d.get("subtareas") or [])
                estado = d.get("estado", "NO_PUDE")
                if estado in ("DECISIÓN", "NO_PUDE"):
                    self.est.cambiar(tid, nota=d.get("nota", "")[:1000])
                    resultado = estado
                    return estado
                if not git_ops.hay_cambios(wt):
                    historia.append(f"intento {intento}: dijo LISTO sin cambiar nada")
                    self._rechazo(tid, "implementador: dijo LISTO sin cambios en el repo")
                    retro = "Dijiste LISTO pero no hay ningún cambio en el repo. Implementa la tarea."
                    continue

                comandos = comandos_ahora()
                ok, log = await asyncio.to_thread(verificar, wt, comandos, self.cfg["hecho"]["timeout_pruebas"])
                if not ok:
                    h = huella(log)
                    historia.append(f"intento {intento}: pruebas fallaron (firma {h})")
                    self._rechazo(tid, "pruebas fallaron:\n" + "\n".join(log.strip().splitlines()[-15:]))
                    retro = f"Fallaron las pruebas:\n```\n{log[-4000:]}\n```"
                    if huellas.count(h) >= 2:
                        self.est.cambiar(tid, nota=f"mismo error 3 veces: {log[-300:]}")
                        resultado = "ESTANCADA"
                        return resultado
                    if h in huellas:                       # mismo error dos veces: el vigía propone otro camino
                        e = await self._vigia(t, historia, "estrategia")
                        if e:
                            retro += f"\n\nEl mismo error salió dos veces. Cambia de enfoque: {e}"
                    huellas.append(h)
                    continue

                cambio = git_ops.diff(wt, base)
                motivo = await self._puerta_seguridad(t, wt, base)
                if motivo:
                    historia.append(f"intento {intento}: la puerta de seguridad lo rechazó")
                    self._rechazo(tid, f"seguridad: {motivo}")
                    retro = motivo
                    continue

                # Revisión proporcional: un cambio chico no paga Opus + 3 subagentes.
                lineas, archivos = git_ops.tamano_diff(wt, base)
                chico = lineas <= self.L["diff_chico_lineas"] and archivos <= self.L["diff_chico_archivos"]
                rv = await self.sesion("revisor", roles.plantilla(
                    "revisor", perfil_contexto=self.perfil_ctx, perfil_revision=self.perfil_rev or "(nada extra)",
                    tid=tid, titulo=t["titulo"], cuerpo=t["cuerpo"],
                    criterios_globales="\n".join(f"- {c}" for c in self.cfg["hecho"]["criterios"]) or "- (ninguno)",
                    diff=cambio[:80000], como_revisar=roles.REVISAR_CHICO if chico else roles.REVISAR_COMPLETO),
                    wt, tid, roles.LECTURA, False, roles.ESQUEMA_REVISION, None if chico else roles.PARA_REVISAR,
                    modelo=self.M.get("implementador", "") if chico else None,
                    etiqueta=f"{'chico' if chico else 'completo'} ({lineas} líneas, {archivos} archivos)")
                dv = rv.datos if isinstance(rv.datos, dict) else {}
                if rv.error or not dv.get("aprobado"):
                    cambios = dv.get("cambios") or [rv.error or "el revisor no dio veredicto"]
                    historia.append(f"intento {intento}: el revisor pidió {len(cambios)} cambios")
                    self._rechazo(tid, "revisor pidió:\n" + "\n".join(f"- {c}" for c in cambios))
                    retro = "El revisor pidió:\n" + "\n".join(f"- {c}" for c in cambios)
                    continue

                git_ops.commit(wt, f"loopeable {tid}: {t['titulo']}")
                if not await self._integrar(t, wt, rama_t, comandos):
                    self.est.cambiar(tid, nota="conflicto de merge que el integrador no pudo resolver")
                    return resultado
                resultado = "HECHA"
                self.est.cambiar(tid, nota="")
                self.log(f"✅ {tid} integrada (intento {intento}, {self.est.tarea(tid)['costo']:.2f} USD)")
                return resultado
            self.est.cambiar(tid, nota="; ".join(historia)[-1000:])
            return resultado
        except Freno as f:
            self.log(f"⏸️  {tid} vuelve a pendiente: {f}")
            self.est.evento(tid, "freno", str(f))
            self.est.cambiar(tid, intentos=0)          # vuelve a la cola con todos sus intentos
            resultado = "PENDIENTE"
            return resultado
        finally:
            if resultado not in ("PENDIENTE",) and (historia or resultado != "HECHA"):
                try:
                    await self._leccion(t, historia, resultado)
                except Exception as e:             # una lección perdida no tumba la corrida
                    self.est.evento(tid, "leccion-fallo", str(e))
            async with self.lock:
                git_ops.quitar_worktree(self.raiz, wt)
                if resultado == "HECHA":
                    git_ops.git(self.raiz, "branch", "-D", rama_t, check=False)

    def _subtareas(self, padre: dict, subs: list[dict]):
        """Los loops crean loops: lo que un loop descubre se vuelve otra tarea (con tope de profundidad y total)."""
        for s in subs:
            if padre["profundidad"] + 1 > self.L["profundidad"] or len(self.est.todas()) >= self.L["tareas"]:
                self.est.evento(padre["id"], "subtarea-descartada", s.get("titulo", ""))
                continue
            if any(x["titulo"].strip().lower() == s["titulo"].strip().lower() for x in self.est.todas()):
                continue
            tid = self.est.nueva(s["titulo"], roles.cuerpo_tarea(s), min(3, padre["prioridad"] + 1),
                                 depende=[padre["id"]], profundidad=padre["profundidad"] + 1, padre=padre["id"],
                                 origen=f"descubierta en {padre['id']}")
            self.log(f"   ↳ {tid} creada por {padre['id']}: {s['titulo']}")

    async def _vigia(self, t: dict, historia: list[str], que: str) -> str:
        pedido = ("El loop repite el mismo error. Propón en 2-4 frases un enfoque distinto y concreto."
                  if que == "estrategia" else "")
        r = await self.sesion("vigia", roles.plantilla("vigia", pedido=pedido, tid=t["id"], titulo=t["titulo"],
                                                       cuerpo=t["cuerpo"], historia="\n".join(historia)),
                              self.raiz, t["id"], roles.LECTURA, False, roles.ESQUEMA_ESTRATEGIA)
        return (r.datos or {}).get("estrategia", "") if isinstance(r.datos, dict) else ""

    async def _leccion(self, t: dict, historia: list[str], resultado: str):
        pedido = (f"La tarea terminó como {resultado}. Escribe UNA lección corta y reutilizable para futuras tareas "
                  "en este repo (qué evitar o qué funciona), sin detalles de esta tarea en particular. Si no hay nada "
                  "útil que aprender, devuelve una cadena vacía.")
        r = await self.sesion("vigia", roles.plantilla("vigia", pedido=pedido, tid=t["id"], titulo=t["titulo"],
                                                       cuerpo=t["cuerpo"], historia="\n".join(historia) or "(a la primera)"),
                              self.raiz, t["id"], [], False, roles.ESQUEMA_APRENDIZAJE)
        leccion = ((r.datos or {}).get("leccion", "") if isinstance(r.datos, dict) else "").strip()
        if not leccion:
            return
        async with self.lock:
            p = self.raiz / APRENDIZAJES
            previo = p.read_text() if p.exists() else "# Lo que loopeable aprendió de este repo\n\n"
            if leccion.lower() in previo.lower():
                return
            p.write_text(previo + f"- {leccion}  _({t['id']}, {time.strftime('%Y-%m-%d')})_\n")
            git_ops.git(self.raiz, "add", APRENDIZAJES)
            git_ops.git(self.raiz, "-c", "user.name=loopeable", "-c", "user.email=loopeable@localhost",
                        "commit", "-q", "-m", f"loopeable: lección de {t['id']}")

    async def _puerta_seguridad(self, t: dict, wt: Path, base: str) -> str:
        ruta = self.cfg["puertas"]["seguridad"]
        if not ruta:
            return ""
        archivos = git_ops.git(wt, "diff", "--cached", "--name-only", base)
        r = await self.sesion("seguridad", roles.plantilla("seguridad", cwd=wt, tid=t["id"], titulo=t["titulo"],
                                                           archivos=archivos),
                              wt, t["id"], roles.LECTURA + ["Bash", "Skill"], False, roles.ESQUEMA_SEGURIDAD,
                              plugins=[str(Path(ruta).expanduser())], modelo=self.M.get("revisor", ""))
        d = r.datos if isinstance(r.datos, dict) else {}
        if r.error or d.get("veredicto") not in ("🔴", "🟠", "🟢"):
            return f"La puerta de seguridad no pudo revisar el cambio ({r.error or 'sin veredicto'}); vuelve a intentar."
        if d["veredicto"] in self.cfg["puertas"]["bloquear_en"]:
            hs = "\n".join(f"- {h.get('severidad', '')} · {h.get('donde', '')} · {h.get('titulo', '')}: {h.get('arreglo', '')}"
                           for h in d.get("hallazgos", []))
            return f"security-suite dio {d['veredicto']} sobre tu cambio. Arregla esto:\n{hs}"
        return ""

    async def _integrar(self, t: dict, wt: Path, rama_t: str, comandos: list[str]) -> bool:
        async with self.lock:
            conflictos = git_ops.traer_base(wt, self.rama)
            if conflictos:
                self.log(f"   ⚔️  {t['id']} choca con lo ya integrado ({', '.join(conflictos)}); llama al integrador")
                r = await self.sesion("integrador", roles.plantilla(
                    "integrador", tid=t["id"], titulo=t["titulo"], cwd=wt, conflictos="\n".join(conflictos),
                    cuerpo=t["cuerpo"], pruebas=" ; ".join(comandos)), wt, t["id"], roles.TRABAJO, True,
                    roles.ESQUEMA_IMPLEMENTAR)
                marcadores = subprocess.run(["git", "-C", str(wt), "grep", "-nE", "^(<<<<<<<|>>>>>>>)( |$)"],
                                            capture_output=True, text=True).stdout
                ok, _ = await asyncio.to_thread(verificar, wt, comandos, self.cfg["hecho"]["timeout_pruebas"])
                if r.error or (r.datos or {}).get("estado") != "LISTO" or marcadores or not ok:
                    git_ops.git(wt, "merge", "--abort", check=False)
                    return False
                git_ops.commit(wt, f"loopeable {t['id']}: integra la rama de integración")
            git_ops.integrar(self.raiz, rama_t, f"loopeable {t['id']}: {t['titulo']}")
            return True

    # ───────────────────── el loop que orquesta ─────────────────────

    async def correr(self) -> dict:
        self.preparar()
        self.log(f"🌿 Rama de integración: {self.rama}")
        self.log("💳 Cuenta: " + ("API key de " + self.cfg["cuenta"]["api_env"] + " (créditos de API)"
                                  if self.cfg["cuenta"]["modo"] == "api" else "tu plan de Claude (límites de uso)"))
        self.log(f"🧪 Pruebas: {' ; '.join(self.pruebas) or '(ninguna)'}")
        try:
            await self.planear()
        except Freno as f:
            self.log(f"⏹️  {f}")
        propuestas = [t for t in self.est.todas() if t["estado"] == "PROPUESTA"]
        if propuestas:
            texto = "\n".join(f"{t['id']} [{t['prioridad']}] {t['titulo']}" +
                              (f"\n     prueba propia (se ejecutará): {t['prueba']}" if t["prueba"] else "")
                              for t in propuestas)
            self.log(f"\n📝 Plan listo, esperando tu OK:\n{texto}\n\nApruébalo con: loopeable aprobar todas")
            avisos.avisar(self.cfg, "loopeable: plan listo para aprobar", texto)
            return self.resumen("esperando aprobación del plan")

        activas: dict[str, asyncio.Task] = {}
        motivo = None
        while True:
            motivo = self.freno()
            if not motivo:
                for t in self.est.listas():
                    if len(activas) >= self.L["paralelo"]:
                        break
                    if t["id"] not in activas:
                        self.est.cambiar(t["id"], estado="EN_CURSO")
                        activas[t["id"]] = asyncio.create_task(self.loop_tarea(t["id"]))
                self.tablero()
            if not activas:
                break
            listas, _ = await asyncio.wait(activas.values(), return_when=asyncio.FIRST_COMPLETED)
            for tid, tarea in list(activas.items()):
                if tarea not in listas:
                    continue
                del activas[tid]
                try:
                    estado = tarea.result()
                except Exception as e:
                    estado = "FALLÓ"
                    self.est.cambiar(tid, nota=f"{type(e).__name__}: {e}"[:1000])
                self.est.cambiar(tid, estado=estado)
                if estado in ("DECISIÓN", "ESTANCADA", "NO_PUDE", "FALLÓ"):
                    t = self.est.tarea(tid)
                    self.log(f"{'❓' if estado == 'DECISIÓN' else '❌'} {tid} {estado}: {t['nota'][:200]}")
                    avisos.avisar(self.cfg, f"loopeable: {tid} {estado}", f"{t['titulo']}\n{t['nota'][:500]}",
                                  urgente=estado == "DECISIÓN")
            self.tablero()
        self.tablero()
        if motivo:
            self.log(f"⏹️  {motivo}")
        suciedad = git_ops.git(self.raiz, "status", "--porcelain", "--untracked-files=normal").splitlines()
        if suciedad:
            self.log("⚠️  El árbol quedó con cambios sin commit (la próxima corrida no arrancará hasta que los "
                     "resuelvas):\n   " + "\n   ".join(suciedad[:20]))
        return self.resumen(motivo or "sin tareas pendientes")

    def resumen(self, motivo: str) -> dict:
        ts = self.est.todas()
        cuenta = {}
        for t in ts:
            cuenta[t["estado"]] = cuenta.get(t["estado"], 0) + 1
        res = {"motivo": motivo, "rama": self.rama, "gasto_usd": round(self.est.gasto_total(), 3), "tareas": cuenta,
               "bloqueadas": [t["id"] for t in self.est.bloqueadas_sin_salida()]}
        if motivo != "esperando aprobación del plan":
            texto = (f"{motivo}\n" + " · ".join(f"{k}: {v}" for k, v in cuenta.items()) +
                     f"\nGasto: {res['gasto_usd']} USD · rama {self.rama}")
            avisos.avisar(self.cfg, "loopeable terminó", texto)
            if self.cfg["entrega"]["pr"] and cuenta.get("HECHA"):
                res["pr"] = self.entregar_pr()
        return res

    def entregar_pr(self) -> str:
        """Push de la rama de integración (nunca main) y PR en borrador. Es lo único que sale de tu máquina."""
        if not shutil.which("gh"):
            return "no hay `gh`: sube la rama a mano"
        try:
            git_ops.git(self.raiz, "push", "-u", "origin", self.rama)
            cuerpo = (self.dir / "TABLERO.md").read_text()
            r = subprocess.run(["gh", "pr", "create", "--draft", "--head", self.rama, "--title",
                                f"loopeable: {self.cfg['objetivo'][:60]}", "--body", cuerpo],
                               cwd=self.raiz, capture_output=True, text=True)
            return (r.stdout or r.stderr).strip()
        except Exception as e:
            return f"no se pudo abrir el PR: {e}"
