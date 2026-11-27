"""Estado de la corrida en SQLite (.loopeable/estado.db): seguro con loops en paralelo y reanudable."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS tareas (
  id TEXT PRIMARY KEY, titulo TEXT, cuerpo TEXT, prioridad INTEGER, estado TEXT,
  depende TEXT, profundidad INTEGER, padre TEXT, intentos INTEGER DEFAULT 0,
  costo REAL DEFAULT 0, nota TEXT DEFAULT '', rama TEXT DEFAULT '', origen TEXT, creado REAL,
  prueba TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS eventos (ts REAL, tarea TEXT, tipo TEXT, texto TEXT);
CREATE TABLE IF NOT EXISTS fuentes (ruta TEXT PRIMARY KEY, huella TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS meta (clave TEXT PRIMARY KEY, valor TEXT);
"""

# PROPUESTA → (aprobar) → PENDIENTE → EN_CURSO → HECHA | FALLÓ | ESTANCADA | DECISIÓN | NO_PUDE
TERMINALES = {"HECHA", "FALLÓ", "ESTANCADA", "NO_PUDE"}


class Estado:
    def __init__(self, carpeta: Path):
        carpeta.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(carpeta / "estado.db", isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(ESQUEMA)
        columnas = {r[1] for r in self.db.execute("PRAGMA table_info(tareas)")}
        if "prueba" not in columnas:              # estado.db de una versión anterior
            self.db.execute("ALTER TABLE tareas ADD COLUMN prueba TEXT DEFAULT ''")

    # ── tareas ──
    def nueva(self, titulo: str, cuerpo: str, prioridad: int = 2, depende: list[str] | None = None,
              profundidad: int = 0, padre: str = "", origen: str = "", estado: str = "PENDIENTE",
              prueba: str = "") -> str:
        """`prueba` es el comando propio de la tarea; solo lo llena el planificador, nunca el texto libre."""
        n = self.db.execute("SELECT COUNT(*) FROM tareas").fetchone()[0] + 1
        tid = f"T{n:02d}"
        self.db.execute("INSERT INTO tareas (id,titulo,cuerpo,prioridad,estado,depende,profundidad,padre,origen,creado,"
                        "prueba) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (tid, titulo, cuerpo, prioridad, estado, json.dumps(depende or []), profundidad, padre,
                         origen, time.time(), prueba))
        self.evento(tid, "creada", titulo)
        return tid

    def tarea(self, tid: str) -> dict:
        r = self.db.execute("SELECT * FROM tareas WHERE id=?", (tid,)).fetchone()
        if not r:
            raise KeyError(tid)
        d = dict(r)
        d["depende"] = json.loads(d["depende"])
        return d

    def todas(self) -> list[dict]:
        return [self.tarea(r[0]) for r in self.db.execute("SELECT id FROM tareas ORDER BY id")]

    def cambiar(self, tid: str, **campos):
        if "depende" in campos:
            campos["depende"] = json.dumps(campos["depende"])
        sets = ", ".join(f"{k}=?" for k in campos)
        self.db.execute(f"UPDATE tareas SET {sets} WHERE id=?", (*campos.values(), tid))
        if "estado" in campos:
            self.evento(tid, "estado", campos["estado"])

    def sumar_costo(self, tid: str, usd: float):
        self.db.execute("UPDATE tareas SET costo = costo + ? WHERE id=?", (usd, tid))

    def listas(self) -> list[dict]:
        """PENDIENTES cuyas dependencias ya están HECHAS, por prioridad."""
        hechas = {t["id"] for t in self.todas() if t["estado"] == "HECHA"}
        ts = [t for t in self.todas() if t["estado"] == "PENDIENTE" and all(d in hechas for d in t["depende"])]
        return sorted(ts, key=lambda t: (t["prioridad"], t["id"]))

    def bloqueadas_sin_salida(self) -> list[dict]:
        """PENDIENTES que dependen de algo que ya no se va a hacer."""
        muertas = {t["id"] for t in self.todas() if t["estado"] in TERMINALES - {"HECHA"} or t["estado"] == "DECISIÓN"}
        return [t for t in self.todas() if t["estado"] == "PENDIENTE" and any(d in muertas for d in t["depende"])]

    # ── eventos, fuentes, meta ──
    def evento(self, tarea: str, tipo: str, texto: str = ""):
        self.db.execute("INSERT INTO eventos VALUES (?,?,?,?)", (time.time(), tarea, tipo, texto[:4000]))

    def eventos(self, tarea: str | None = None, limite: int = 50) -> list[dict]:
        q = "SELECT * FROM eventos" + (" WHERE tarea=?" if tarea else "") + " ORDER BY ts DESC LIMIT ?"
        return [dict(r) for r in self.db.execute(q, ((tarea, limite) if tarea else (limite,)))]

    def fuente_vista(self, ruta: str, huella: str) -> bool:
        r = self.db.execute("SELECT huella FROM fuentes WHERE ruta=?", (ruta,)).fetchone()
        return bool(r and r[0] == huella)

    def marcar_fuente(self, ruta: str, huella: str):
        self.db.execute("INSERT OR REPLACE INTO fuentes VALUES (?,?,?)", (ruta, huella, time.time()))

    def meta(self, clave: str, defecto: str = "") -> str:
        r = self.db.execute("SELECT valor FROM meta WHERE clave=?", (clave,)).fetchone()
        return r[0] if r else defecto

    def poner_meta(self, clave: str, valor):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (clave, str(valor)))

    def gasto_total(self) -> float:
        return self.db.execute("SELECT COALESCE(SUM(costo),0) FROM tareas").fetchone()[0] + float(self.meta("costo_extra", "0"))

    def sumar_costo_extra(self, usd: float):
        self.poner_meta("costo_extra", float(self.meta("costo_extra", "0")) + usd)
