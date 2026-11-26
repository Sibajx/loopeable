## Contexto
Repo de security-suite: una suite de seguridad para Claude Code (plugin) que audita apps y páginas hechas con IA.
Lo esencial vive en skills/security-suite/: SKILL.md (fases 0–6), SecurityChecks.md (20 chequeos + extras X, cada
uno con severidad fija y una tabla de reparto por agente), agentes/*.md (contrato común + un archivo por agente),
scripts/ (herramientas de pentest con códigos de salida documentados), owasp/, plantillas/ (incluidos repro/),
mejores-practicas.md y reglas-de-enfrentamiento.md (niveles 1–3). README.md (español) y README.en.md (inglés).
tests/ genera un fixture FastAPI con fallas plantadas y trampas; tests/esperado.md es la hoja de respuestas.
Todo se escribe en español salvo README.en.md. Los scripts: sin dependencias raras, nunca imprimen un secreto
completo (4 caracteres + …), y todo lo que toca una app en vivo respeta los niveles de reglas-de-enfrentamiento.md.

## Revisión
- Un chequeo nuevo o cambiado aparece en SecurityChecks.md (con severidad fija), en la tabla de reparto y en el
  archivo del agente que lo revisa; si cambia una fase, también en SKILL.md.
- Las tablas del README coinciden en español e inglés.
- Un script nuevo tiene cabecera de uso, códigos de salida documentados, su fila en la tabla del README y una prueba
  tests/probar-<script>.sh que no necesita red (CI la corre).
- Cualquier prueba en vivo declara su nivel mínimo y no hace DoS, extracción de datos ni shells.
- Si el chequeo se puede plantar en el fixture, hay una falla plantada nueva y su línea en tests/esperado.md.
