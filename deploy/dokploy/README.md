# Sellbird en Dokploy (sellbird.dropia.uy)

Issue: drop-ia/sellbird#1.

## Cómo está armado

- Una aplicación de Dokploy que se construye con `Dockerfile.dokploy` (sin docker-compose). Expone el puerto 8080.
- El panel de Sellbird solo atiende en `127.0.0.1:5555` y rechaza cualquier otro dominio. Caddy (`deploy/dokploy/Caddyfile`) recibe `sellbird.dropia.uy` en el 8080 y se lo pasa al panel como si fuera local.
- Caddy responde 403 a todo lo que no llegue por Cloudflare (por IP de origen) o no traiga la identidad de Cloudflare Access (`Cf-Access-Jwt-Assertion`). Solo traduce el `Origin` público (`SELLBIRD_PUBLIC_ORIGIN`, por defecto `https://sellbird.dropia.uy`); cualquier otro llega tal cual y el panel lo rechaza.
- El panel sigue pidiendo su propio link de desbloqueo: está en el log del contenedor.

## Volúmenes

| Ruta | Qué guarda |
|---|---|
| `/data` | `SELLBIRD_HOME`: `sellbird.yaml`, `sellbird.local.yaml`, `.env`, `prompts/`, `skills/`, `data/` (base, token del panel) |
| `/home/sellbird/.claude` | La sesión de Claude |

La primera vez, `/data` se llena con los archivos por defecto. Nunca se pisan después.

## Primer arranque

1. En Cloudflare, `sellbird.dropia.uy` va **con proxy** (nube naranja) y tiene una aplicación de Cloudflare Access que deja entrar solo a los correos autorizados.
2. Desplegar en Dokploy con dominio `sellbird.dropia.uy`, puerto 8080, HTTPS.
3. En la terminal del contenedor: `claude` e iniciar sesión con la cuenta de Claude.
4. En la terminal: `python -m sellbird setup` (el asistente de configuración), o completar `/data/.env` y `/data/sellbird.yaml` desde el panel.
5. Abrir el link de desbloqueo del log cambiando `http://127.0.0.1:5555` por `https://sellbird.dropia.uy`.

## Correo

`santiago@dropia.com.uy` por SMTP + IMAP (Zoho Mail): `channels.email.provider: smtp` en `sellbird.yaml` y `SMTP_*` / `IMAP_*` en `/data/.env`. El dominio necesita MX, SPF, DKIM y DMARC de Zoho, y la casilla conviene calentarla antes de mandar en volumen (`docs/deliverability.md`).

## Al actualizar desde upstream

`git fetch upstream && git merge upstream/main`. Si upstream cambia su `Dockerfile` (dependencias, Playwright, Claude), llevar el mismo cambio a `Dockerfile.dokploy`.
