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


def excluir_carpeta_estado(raiz: Path):
    """.loopeable/ nunca entra a git (estado, worktrees, bitácoras)."""
    excl = Path(git(raiz, "rev-parse", "--git-path", "info/exclude"))
    excl = excl if excl.is_absolute() else raiz / excl
    excl.parent.mkdir(parents=True, exist_ok=True)
    texto = excl.read_text() if excl.exists() else ""
    if ".loopeable/" not in texto.splitlines():
        excl.write_text(texto + ("\n" if texto and not texto.endswith("\n") else "") + ".loopeable/\n")


def sucio(raiz: Path) -> bool:
    return bool(git(raiz, "status", "--porcelain", "--untracked-files=normal"))


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
