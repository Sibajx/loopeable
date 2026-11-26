# loopeable en un server (24/7)

Un loop de horas no debería vivir en tu laptop: si se duerme, se detiene. En un server Linux con Docker queda
corriendo aunque cierres todo, y te avisa al celular.

## Una vez

```bash
sudo mkdir -p /srv/loopeable/proyectos && sudo chown -R $USER /srv/loopeable
git clone https://github.com/Sibajx/loopeable /srv/loopeable/loopeable
docker compose -f /srv/loopeable/loopeable/docker/compose.yml build

# Credenciales: en tu máquina corre `claude setup-token` y copia el token
sudo install -m 600 /dev/null /srv/loopeable/secretos.env
echo 'CLAUDE_CODE_OAUTH_TOKEN=...' | sudo tee -a /srv/loopeable/secretos.env >/dev/null

sudo cp /srv/loopeable/loopeable/despliegue/loopeable@.service /etc/systemd/system/
sudo systemctl daemon-reload
```

## Por proyecto

```bash
git clone https://github.com/Sibajx/Security-Suite /srv/loopeable/proyectos/security-suite
cd /srv/loopeable/proyectos/security-suite
cp /srv/loopeable/loopeable/ejemplos/security-suite/loopeable.toml .
git add loopeable.toml && git commit -m "loopeable: configuración"
mkdir -p .loopeable/bandeja && cp /srv/loopeable/loopeable/ejemplos/security-suite/bandeja/*.md .loopeable/bandeja/

# 1) planear y revisar el plan
PROYECTO=$PWD docker compose -f /srv/loopeable/loopeable/docker/compose.yml run --rm loopeable planear
PROYECTO=$PWD docker compose -f /srv/loopeable/loopeable/docker/compose.yml run --rm loopeable aprobar todas
# 2) dejarlo trabajando
sudo systemctl start loopeable@security-suite
journalctl -u loopeable@security-suite -f
```

## Verlo desde el celular

- **Avisos:** pon `ntfy = "https://ntfy.sh/<tema-largo-y-secreto>"` en `[avisos]` y suscríbete a ese tema en la app
  ntfy. Te llega el plan listo, cada ❓ decisión, cada tarea que se atora y el resumen final. El firewall abre el
  dominio de ntfy (o Telegram) solo si `[avisos]` lo usa. El token de Telegram va en un archivo aparte
  (`LOOPEABLE_AVISOS_ENV=/srv/loopeable/avisos.env`, chmod 600, con `TELEGRAM_TOKEN=...`), no en `secretos.env`:
  así los agentes no lo ven.
- **Tablero:** `.loopeable/TABLERO.md` se actualiza en cada cambio. Para verlo por web, sírvelo detrás de Cloudflare
  Access (por ejemplo con un túnel `cloudflared` a un servidor estático de solo lectura sobre `.loopeable/`).
  Nunca lo publiques sin Access: incluye nombres de archivos y notas de tu código.
- **Contestar una decisión:** `loopeable responder T03 "Mercado Pago"` (por SSH) y vuelve a arrancar el servicio.
