# Ataques del video que faltan o están a medias en la suite

Ya cubiertos (no duplicar): 1 IDOR (chequeo 6, matriz-permisos.py) · 2 registrarse como admin (7 y 6) · 3 /admin (4) ·
4 API key en el código (1) · 5 .env en git (3) · 6 editar el precio (X4, 7) · 8 cupón ×100 (X4, carrera.py) ·
11 XSS guardado (8) · 12 web shell como foto (13) · 13 SQLi (9, sqlmap).

## 1. Webhook de pago falso (ataque 7) — hueco real
Ningún chequeo verifica que el endpoint del webhook valide la firma del proveedor (Stripe-Signature, HMAC de
Mercado Pago o PayPal), que sea idempotente (un mismo evento no se procesa dos veces) y que confirme el pago con la API
del proveedor antes de entregar. En apps hechas con IA es común marcar el pedido como pagado con cualquier POST.
Propuesta: chequeo X10, CRÍTICA, una regla de semgrep y una prueba en vivo: mandar un webhook sin firma en el modo de
prueba del proveedor.

## 2. Inyección de instrucciones al chatbot (ataque 10) — hueco real
Hoy es solo una línea dentro de X4. Propuesta: chequeo X11 para funciones con LLM: ¿se filtra el system prompt?,
¿el chatbot tiene herramientas o acceso a datos de otros usuarios?, ¿el RAG mezcla datos entre clientes?, ¿su salida
se renderiza como HTML? Con un script chatbot-inyeccion.py de payloads inofensivos, dentro de las reglas de
enfrentamiento.

## 3. Ransomware (ataque 14) — a medias
El chequeo 20 pide respaldos probados pero no inmutables/externos: credenciales distintas a las de la app, versionado
u Object Lock en R2/S3, una copia que el servidor comprometido no pueda borrar. Agregarlo al 20 (o separarlo) con una
pregunta ❓, porque no se ve en el código.

## 4. Tres semanas sin logs (ataque 15) — a medias
X6 es MEDIA y no pide logs fuera del servidor ni retención. Subir a ALTA cuando no hay ningún log de autenticación;
exigir logs fuera del servidor, retención ≥ 90 días y alerta ante acciones de admin.

## 5. Fuerza bruta de códigos cortos (ataque 9) — a medias
El chequeo 11 cubre rate limit del login, no la fuerza bruta de OTP de 6 dígitos, códigos de recuperación y cupones
(el video muestra 384.211 de 1.000.000 intentos). Agregar límite de intentos por código y caducidad, y una prueba en
vivo: ráfaga pequeña contra la verificación de OTP.

## 6. Modo rápido "app hecha con IA" — opcional
Perfil exprés que corre solo estos 15 ataques, para apps de Lovable, Bolt o v0 con Supabase. Primero las reglas RLS del
chequeo 10 (lo que falló en el caso de las 18.000 cuentas). Diagnóstico corto.

Prioridad: 1 y 2 primero (huecos reales); 3, 4 y 5 son ajustes chicos; 6 es opcional.
