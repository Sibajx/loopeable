Usa la skill security-suite en modo `auditoria` (solo código, sin ninguna petición a apps en vivo) sobre la
carpeta {{cwd}}. Corres sin usuario presente: no hagas preguntas, no instales herramientas (si falta alguna, sigue y
anótalo) y no modifiques el proyecto.

Revisa SOLO lo que cambió en esta tarea ({{tid}} · {{titulo}}) y lo que ese cambio toca. Archivos:
{{archivos}}

No uses git (ni status, diff, log…): loopeable hace las ramas, los commits y los merges, y el hook lo niega. Los
archivos a revisar ya vienen arriba; léelos directamente.

Responde con el JSON del esquema: `veredicto` (🔴 si hay alguna CRÍTICA, 🟠 si hay ALTAS, 🟢 si no) y los
hallazgos de ese cambio con severidad, archivo:línea y el arreglo concreto.
