## Contexto
Firmware para ESP32 con PlatformIO (o ESP-IDF si el repo lo usa). La verificación base es que compile
(`pio run`) para todos los entornos de platformio.ini. Cuida la memoria (stack de tareas de FreeRTOS, heap, PSRAM),
no bloquees el loop principal, y nada de credenciales Wi-Fi o tokens en el código: van en un archivo excluido de git
o en NVS.

## Revisión
- Compila sin warnings nuevos en todos los entornos.
- Sin delays largos en tareas críticas ni en callbacks; sin asignaciones dinámicas en ISR.
- Credenciales fuera del código; logs sin datos sensibles.
- Si hay pruebas unitarias (`pio test` en native), cubren la lógica nueva.
