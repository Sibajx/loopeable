"""Verificación sin IA: lo primero y lo más barato. El revisor (que cuesta) solo entra si esto pasa."""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path


def detectar_pruebas(raiz: Path) -> list[str]:
    """Adivina el comando de pruebas del proyecto. La skill se lo muestra al usuario para que lo confirme."""
    c = []
    if (raiz / "pyproject.toml").exists() or (raiz / "pytest.ini").exists():
        if (raiz / "tests").is_dir() or (raiz / "test").is_dir():
            c.append("uv run pytest -q" if (raiz / "uv.lock").exists() else "python3 -m pytest -q")
    if (raiz / "package.json").exists():
        import json
        scripts = json.loads((raiz / "package.json").read_text() or "{}").get("scripts", {})
        gestor = "pnpm" if (raiz / "pnpm-lock.yaml").exists() else "npm"
        for s in ("lint", "typecheck", "test", "build"):
            if s in scripts:
                c.append(f"{gestor} run {s}")
    if (raiz / "platformio.ini").exists():
        c.append("pio run")
    if (raiz / "Cargo.toml").exists():
        c.append("cargo test -q")
    if (raiz / "go.mod").exists():
        c.append("go test ./...")
    if (raiz / "Makefile").exists() and re.search(r"^test:", (raiz / "Makefile").read_text(), re.M):
        c.append("make test")
    pruebas = sorted(p for p in (raiz / "tests").glob("probar-*.sh")) if (raiz / "tests").is_dir() else []
    c += [f"bash {p.relative_to(raiz)}" for p in pruebas]
    # Sintaxis de lo que haya, aunque no existan pruebas (barato y atrapa lo peor)
    c.append("for f in $(git ls-files -co --exclude-standard '*.sh'); do bash -n \"$f\" || exit 1; done")
    # compile() y no py_compile: py_compile escribe .pyc aunque esté PYTHONDONTWRITEBYTECODE
    c.append("f=$(git ls-files -co --exclude-standard '*.py'); [ -z \"$f\" ] || python3 -c "
             "'import sys\nfor f in sys.argv[1:]: compile(open(f, \"rb\").read(), f, \"exec\")' $f")
    return c


# Que verificar no ensucie el worktree: sin __pycache__/*.pyc ni .pytest_cache (si no, `git add -A` los commitea).
CREDENCIAL = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL|SSH_AUTH_SOCK", re.I)
ENTORNO_LIMPIO = {"PYTHONDONTWRITEBYTECODE": "1", "PYTEST_ADDOPTS": "-p no:cacheprovider"}


def verificar(wt: Path, comandos: list[str], timeout: int) -> tuple[bool, str]:
    errores = []
    # Las pruebas ejecutan código que escribió el agente, fuera del hook de frenos: sin credenciales a la vista.
    env = {k: v for k, v in os.environ.items() if not CREDENCIAL.search(k)} | ENTORNO_LIMPIO
    if os.environ.get("PYTEST_ADDOPTS"):
        env["PYTEST_ADDOPTS"] = os.environ["PYTEST_ADDOPTS"] + " " + ENTORNO_LIMPIO["PYTEST_ADDOPTS"]
    for cmd in comandos:
        try:
            r = subprocess.run(["bash", "-c", cmd], cwd=wt, capture_output=True, text=True, timeout=timeout,
                               env=env)
            if r.returncode != 0:
                errores.append(f"$ {cmd}  → salió {r.returncode}\n{(r.stdout + r.stderr)[-2500:]}")
        except subprocess.TimeoutExpired:
            errores.append(f"$ {cmd}  → se pasó de {timeout} s")
    return not errores, "\n\n".join(errores)


def huella(log: str) -> str:
    """Firma de un error ignorando números, rutas temporales y horas: el mismo error dos veces = atorado."""
    limpio = re.sub(r"0x[0-9a-f]+|\d+(\.\d+)?|/tmp/\S+|\.loopeable/worktrees/\S+", "#", log.lower())
    return hashlib.sha1(limpio.encode()).hexdigest()[:12]
