"""Las plantillas de los agentes con Bash avisan que git lo maneja loopeable."""

import pytest

from loopeable import roles

FRASE = "loopeable hace las ramas, los commits y los merges"


@pytest.mark.parametrize("nombre", ["implementador", "integrador", "seguridad"])
def test_plantilla_avisa_que_git_lo_maneja_loopeable(nombre: str) -> None:
    texto = " ".join(roles.plantilla(nombre).split())
    assert FRASE in texto
    assert "No uses git" in texto
