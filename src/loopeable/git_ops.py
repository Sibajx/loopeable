"""Git: rama de integración, un worktree por loop de tarea, commits y merges."""
from __future__ import annotations

import subprocess
from pathlib import Path


class ErrorGit(RuntimeError):
    pass


def git(cwd: Path, *args, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise ErrorGit(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()[:800]}")
    return r.stdout.strip()


def es_repo(raiz: Path) -> bool:
    return subprocess.run(["git", "-C", str(raiz), "rev-parse", "--git-dir"], capture_output=True).returncode == 0


# Lo que nunca debe entrar a un commit de loopeable aunque el proyecto no tenga .gitignore: el estado de
# loopeable y la basura que dejan las pruebas y los builds.
EXCLUIR = [".loopeable/", "__pycache__/", "*.pyc", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/",
           "node_modules/", ".venv/", "dist/", "build/", "*.egg-info/", ".pio/"]


def excluir_carpeta_estado(raiz: Path):
    """Agrega EXCLUIR al info/exclude del repo (lo comparten los worktrees), sin duplicar líneas."""
    excl = Path(git(raiz, "rev-parse", "--git-path", "info/exclude"))
    excl = excl if excl.is_absolute() else raiz / excl
    excl.parent.mkdir(parents=True, exist_ok=True)
    texto = excl.read_text() if excl.exists() else ""
    faltan = [p for p in EXCLUIR if p not in texto.splitlines()]
    if faltan:
        excl.write_text(texto + ("\n" if texto and not texto.endswith("\n") else "") + "\n".join(faltan) + "\n")


def cambios_sin_commit(raiz: Path) -> list[str]:
    """Líneas de `git status --porcelain`, sin contar .loopeable/ (es de loopeable, no del proyecto)."""
    return git(raiz, "status", "--porcelain", "--untracked-files=normal", "--", ".",
               ":(exclude).loopeable").splitlines()


def sucio(raiz: Path) -> bool:
    return bool(cambios_sin_commit(raiz))


def sacar_estado_de_git(raiz: Path) -> list[str]:
    """Si .loopeable/ quedó versionado (p. ej. un `git add -A` antes de la primera corrida), lo saca del índice
    con un commit en la rama actual. Devuelve los archivos que salieron. Nunca en main/master."""
    archivos = git(raiz, "ls-files", ".loopeable").splitlines()
    if not archivos:
        return []
    if git(raiz, "branch", "--show-current") in ("main", "master"):
        raise ErrorGit("no saco .loopeable de git en main/master: corre loopeable en su rama de integración")
    git(raiz, "rm", "-r", "-q", "--cached", ".loopeable")
    git(raiz, "-c", "user.name=loopeable", "-c", "user.email=loopeable@localhost",
        "commit", "-q", "--no-verify", "-m", "loopeable: saca .loopeable de git")
    return archivos


def preparar_rama(raiz: Path, rama: str):
    actual = git(raiz, "branch", "--show-current")
    if actual == rama:
        return
    existe = git(raiz, "rev-parse", "--verify", "-q", f"refs/heads/{rama}", check=False)
    git(raiz, "checkout", "-q", *([rama] if existe else ["-b", rama]))


def crear_worktree(raiz: Path, base: str, ruta: Path, rama: str) -> Path:
    if ruta.exists():
        quitar_worktree(raiz, ruta)
    git(raiz, "branch", "-f", rama, base)
    git(raiz, "worktree", "add", "-q", str(ruta), rama)
    return ruta


def quitar_worktree(raiz: Path, ruta: Path):
    git(raiz, "worktree", "remove", "--force", str(ruta), check=False)
    git(raiz, "worktree", "prune", check=False)


def diff(wt: Path, base: str) -> str:
    git(wt, "add", "-A")
    return git(wt, "diff", "--cached", base, "--stat", "--patch", "--no-color")


def tamano_diff(wt: Path, base: str) -> tuple[int, int]:
    """(líneas agregadas + quitadas, archivos) del cambio contra base. Los binarios cuentan como archivo."""
    git(wt, "add", "-A")
    lineas = archivos = 0
    for fila in git(wt, "diff", "--cached", "--numstat", base).splitlines():
        mas, menos, _ = fila.split("\t", 2)
        archivos += 1
        lineas += (int(mas) if mas.isdigit() else 0) + (int(menos) if menos.isdigit() else 0)
    return lineas, archivos


def hay_cambios(wt: Path) -> bool:
    git(wt, "add", "-A")
    return bool(git(wt, "diff", "--cached", "--name-only"))


def commit(wt: Path, mensaje: str):
    git(wt, "add", "-A")
    git(wt, "-c", "user.name=loopeable", "-c", "user.email=loopeable@localhost",
        "commit", "-q", "--no-verify", "-m", mensaje)


def descartar(wt: Path, base: str):
    git(wt, "reset", "-q", "--hard", base)
    git(wt, "clean", "-fdq")


def traer_base(wt: Path, base: str) -> list[str]:
    """Mezcla la rama de integración dentro del worktree. Devuelve los archivos en conflicto (vacío = limpio)."""
    r = subprocess.run(["git", "-C", str(wt), "-c", "user.name=loopeable", "-c", "user.email=loopeable@localhost",
                        "merge", "--no-edit", "-q", base], capture_output=True, text=True)
    if r.returncode == 0:
        return []
    return git(wt, "diff", "--name-only", "--diff-filter=U").splitlines() or ["(merge falló)"]


def integrar(raiz: Path, rama_tarea: str, mensaje: str):
    """La rama de la tarea ya contiene a la de integración, así que esto no puede chocar."""
    git(raiz, "-c", "user.name=loopeable", "-c", "user.email=loopeable@localhost",
        "merge", "--no-ff", "-q", "-m", mensaje, rama_tarea)
