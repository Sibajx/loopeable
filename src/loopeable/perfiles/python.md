## Contexto
Proyecto Python. Usa el gestor que ya use el repo (uv, poetry, pip). Tipado con anotaciones donde el repo las use,
pruebas con pytest, sin dependencias nuevas salvo que la tarea lo pida (y entonces fijadas en pyproject).

## Revisión
- Pruebas con pytest para el caso normal y los bordes; nada de pruebas que solo importan el módulo.
- Sin dependencias nuevas no justificadas; si las hay, están en pyproject.toml y el lock actualizado.
- Errores manejados con excepciones concretas, sin `except Exception: pass`.
- Docstrings y README al día con la API pública.
