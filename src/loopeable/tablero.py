"""`loopeable tablero`: una página local que muestra el avance en vivo (se actualiza sola cada 3 s).

Solo escucha en 127.0.0.1 y solo lee .loopeable/estado.db: no puede cambiar nada de la corrida.
Para verla desde el celular, ponla detrás de un túnel con Cloudflare Access (ver despliegue/SERVER.md).
"""
from __future__ import annotations

import json
import time
import tomllib
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .estado import Estado

PAGINA = r"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>loopeable</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--borde:#262b36;--txt:#e6e8ee;--sub:#8b93a7;--ok:#3fb950;--run:#58a6ff;
--warn:#d29922;--bad:#f85149;--q:#bc8cff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.45 system-ui,sans-serif}
header{padding:18px 22px;border-bottom:1px solid var(--borde);display:flex;gap:14px;align-items:baseline;flex-wrap:wrap}
h1{font-size:18px;margin:0}.sub{color:var(--sub);font-size:13px}
main{padding:18px 22px;display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}
.card{background:var(--card);border:1px solid var(--borde);border-radius:10px;padding:14px 16px}
.big{font-size:26px;font-weight:600;margin-top:2px}.barra{height:8px;background:#222733;border-radius:6px;overflow:hidden;margin-top:10px}
.barra>div{height:100%;transition:width .5s}.ancho{grid-column:1/-1}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--borde);vertical-align:top}
th{color:var(--sub);font-weight:500;font-size:12px}td.n{text-align:right;font-variant-numeric:tabular-nums}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;border:1px solid currentColor;white-space:nowrap}
.HECHA{color:var(--ok)}.EN_CURSO{color:var(--run)}.PENDIENTE,.PROPUESTA{color:var(--sub)}.DECISIÓN{color:var(--q)}
.FALLÓ,.ESTANCADA,.NO_PUDE{color:var(--bad)}.nota{color:var(--sub);font-size:12px;max-width:520px}
.ev{font-family:ui-monospace,monospace;font-size:12px;color:var(--sub);max-height:260px;overflow:auto}
.ev div{padding:2px 0;border-bottom:1px dashed #1f2430}.vivo{width:8px;height:8px;border-radius:50%;background:var(--ok);display:inline-block;margin-right:6px}
.alerta{border-color:var(--q)}
</style></head><body>
<header><h1>🔁 loopeable</h1><span class="sub" id="rama"></span><span class="sub" id="act"></span></header>
<main>
  <div class="card"><div class="sub">Tareas hechas</div><div class="big" id="hechas">–</div><div class="barra"><div id="bh" style="background:var(--ok);width:0"></div></div></div>
  <div class="card"><div class="sub">Gasto</div><div class="big" id="gasto">–</div><div class="barra"><div id="bg" style="background:var(--warn);width:0"></div></div></div>
  <div class="card"><div class="sub">Loops corriendo ahora</div><div class="big" id="corriendo">–</div></div>
  <div class="card" id="cdec"><div class="sub">Esperan tu decisión</div><div class="big" id="dec">–</div></div>
  <div class="card ancho"><table><thead><tr><th>ID</th><th>Tarea</th><th>Estado</th><th>Prio</th><th class="n">Intentos</th><th class="n">USD</th><th>Nota</th></tr></thead><tbody id="filas"></tbody></table></div>
  <div class="card ancho"><div class="sub" style="margin-bottom:6px">Últimos eventos</div><div class="ev" id="ev"></div></div>
</main>
<script>
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const hora=t=>new Date(t*1000).toLocaleTimeString();
async function tick(){
  try{
    const d=await (await fetch("estado.json",{cache:"no-store"})).json();
    const ts=d.tareas, n=ts.length, h=ts.filter(t=>t.estado==="HECHA").length;
    document.getElementById("rama").textContent=d.rama?("rama "+d.rama):"sin corrida todavía";
    document.getElementById("act").innerHTML='<span class="vivo"></span>actualizado '+new Date().toLocaleTimeString();
    document.getElementById("hechas").textContent=h+" / "+n;
    document.getElementById("bh").style.width=(n?100*h/n:0)+"%";
    document.getElementById("gasto").textContent="$"+d.gasto_usd.toFixed(2)+(d.tope_usd?" / $"+d.tope_usd:"");
    document.getElementById("bg").style.width=(d.tope_usd?Math.min(100,100*d.gasto_usd/d.tope_usd):0)+"%";
    document.getElementById("corriendo").textContent=ts.filter(t=>t.estado==="EN_CURSO").length;
    const dec=ts.filter(t=>t.estado==="DECISIÓN").length;
    document.getElementById("dec").textContent=dec;document.getElementById("cdec").classList.toggle("alerta",dec>0);
    document.getElementById("filas").innerHTML=ts.map(t=>`<tr><td>${esc(t.id)}</td><td>${esc(t.titulo)}${t.padre?` <span class="sub">↳ ${esc(t.padre)}</span>`:""}</td>
      <td><span class="chip ${esc(t.estado)}">${esc(t.estado)}</span></td><td>${t.prioridad}</td><td class="n">${t.intentos}</td>
      <td class="n">${t.costo.toFixed(2)}</td><td class="nota">${esc(t.nota).slice(0,220)}</td></tr>`).join("")||'<tr><td colspan="7" class="sub">Sin tareas todavía.</td></tr>';
    document.getElementById("ev").innerHTML=d.eventos.map(e=>`<div>${hora(e.ts)} · ${esc(e.tarea)} · ${esc(e.tipo)} ${esc(e.texto).slice(0,160)}</div>`).join("");
  }catch(e){document.getElementById("act").textContent="sin conexión con loopeable tablero"}
}
tick();setInterval(tick,3000);
</script></body></html>"""


def datos(raiz: Path) -> dict:
    est = Estado(raiz / ".loopeable")
    tope = None
    cfg = raiz / "loopeable.toml"
    if cfg.exists():
        try:
            tope = tomllib.loads(cfg.read_text()).get("limites", {}).get("usd", 20)
        except tomllib.TOMLDecodeError:
            pass
    ts = est.todas()
    for t in ts:
        t.pop("cuerpo", None)
    return {"rama": est.meta("rama"), "gasto_usd": est.gasto_total(), "tope_usd": tope, "tareas": ts,
            "eventos": est.eventos(limite=40), "ahora": time.time()}


def servir(raiz: Path, puerto: int = 8787, abrir: bool = True):
    class Manejador(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/estado.json"):
                cuerpo, tipo = json.dumps(datos(raiz), ensure_ascii=False).encode(), "application/json"
            elif self.path in ("/", "/index.html"):
                cuerpo, tipo = PAGINA.encode(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    url = f"http://127.0.0.1:{puerto}/"
    print(f"Tablero en {url}  (Ctrl+C para cerrarlo; la corrida sigue aunque lo cierres)")
    if abrir:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
