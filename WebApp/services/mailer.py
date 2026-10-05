"""Envío de correo con Microsoft Graph (sendMail) y autenticación de aplicación OAuth 2.0.

Flujo "client credentials" de Microsoft Entra ID (el mismo que usan otras aplicaciones internas):
  1. Se pide un token a login.microsoftonline.com con el Client ID, el Tenant y el Client Secret,
     con el scope https://graph.microsoft.com/.default
  2. Se envía con POST https://graph.microsoft.com/v1.0/users/{remitente}/sendMail

Requisitos en Entra ID:
  - App registration con el permiso de aplicación  Microsoft Graph > Mail.Send  (consentimiento de admin).
  - No requiere SMTP AUTH en el buzón ni registrar el service principal en Exchange.
El Client Secret se guarda cifrado con DPAPI (credencial "Smtp"), nunca en config.json.
"""
import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from config import load_config
from services import credentials

log = logging.getLogger(__name__)

SCOPE = "https://graph.microsoft.com/.default"
GRAPH = "https://graph.microsoft.com/v1.0"
TIMEOUT_S = 30


class MailError(Exception):
    pass


def _detalle_http(exc):
    """Extrae el mensaje legible de una respuesta de error de Entra ID o de Graph."""
    try:
        cuerpo = json.loads(exc.read())
    except Exception:
        return str(exc.reason)
    if "error_description" in cuerpo:  # Entra ID
        return cuerpo["error_description"].split("\r\n")[0]
    error = cuerpo.get("error", {})
    if isinstance(error, dict):  # Graph
        return f"{error.get('code', '')}: {error.get('message', '')}".strip(": ")
    return str(error)


def _obtener_token(tenant, client_id, secret):
    url = f"https://login.microsoftonline.com/{urllib.parse.quote(tenant)}/oauth2/v2.0/token"
    cuerpo = urllib.parse.urlencode({
        "client_id": client_id, "client_secret": secret,
        "scope": SCOPE, "grant_type": "client_credentials",
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=cuerpo), timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as exc:
        raise MailError(f"Entra ID rechazó la solicitud de token ({exc.code}): {_detalle_http(exc)}")
    except Exception as exc:
        raise MailError(f"No se pudo contactar a login.microsoftonline.com: {exc}")


def _roles(token):
    """Permisos de aplicación incluidos en el token (claim 'roles' del JWT)."""
    try:
        carga = token.split(".")[1]
        carga += "=" * (-len(carga) % 4)
        return json.loads(base64.urlsafe_b64decode(carga)).get("roles", [])
    except Exception:
        return []


def _configuracion():
    cfg = load_config()
    faltantes = [k for k in ("UsuarioSmtp", "Auth_ClientID", "Auth_Tenant") if not cfg.get(k)]
    if faltantes:
        raise MailError("Falta configurar en Ajustes > Correo: " + ", ".join(faltantes))
    cred = credentials.cargar("Smtp")
    if not cred:
        raise MailError("No hay Client Secret guardado. Configúralo en Ajustes > Correo.")
    return cfg, cred[1]


def _token(cfg, secret):
    token = _obtener_token(cfg["Auth_Tenant"], cfg["Auth_ClientID"], secret)
    roles = _roles(token)
    if "Mail.Send" not in roles:
        actuales = ", ".join(roles) or "ninguno"
        raise MailError("La aplicación no tiene el permiso Microsoft Graph > Mail.Send (tipo Aplicación). "
                        f"Permisos actuales: {actuales}. Agrégalo en Entra ID y concede el consentimiento de administrador.")
    return token


def _send_mail(cfg, token, asunto, html, destinatarios, adjuntos=None):
    """adjuntos: lista de dicts {nombre, tipo, datos (bytes), cid}. Con 'cid' la imagen se ve dentro del
    cuerpo (<img src="cid:...">). sendMail admite hasta ~3 MB de adjuntos en una sola petición."""
    remitente = cfg["UsuarioSmtp"]
    mensaje = {
        "message": {
            "subject": asunto,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [{"emailAddress": {"address": d}} for d in destinatarios],
        },
        "saveToSentItems": True,  # copia en "Enviados" del buzón remitente para poder auditar
    }
    if adjuntos:
        mensaje["message"]["attachments"] = [{
            "@odata.type": "#microsoft.graph.fileAttachment", "name": a["nombre"], "contentType": a["tipo"],
            "contentBytes": base64.b64encode(a["datos"]).decode("ascii"),
            "isInline": bool(a.get("cid")), **({"contentId": a["cid"]} if a.get("cid") else {}),
        } for a in adjuntos]
    req = urllib.request.Request(
        f"{GRAPH}/users/{urllib.parse.quote(remitente, safe='@')}/sendMail",
        data=json.dumps(mensaje).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S):
            pass  # 202 Accepted
    except urllib.error.HTTPError as exc:
        raise MailError(f"Microsoft Graph rechazó el envío desde {remitente} ({exc.code}): {_detalle_http(exc)}")
    except Exception as exc:
        raise MailError(f"No se pudo contactar a graph.microsoft.com: {exc}")


def probar_conexion():
    """Obtiene el token, valida el permiso Mail.Send y envía un correo de prueba al propio buzón remitente."""
    cfg, secret = _configuracion()
    token = _token(cfg, secret)
    _send_mail(cfg, token, "Prueba de conexión - Sistema de Despliegues",
               "<p>Correo de prueba del Sistema de Despliegues. La configuración de Microsoft Graph es correcta.</p>",
               [cfg["UsuarioSmtp"]])
    return cfg["UsuarioSmtp"]


def enviar(asunto, html, destinatarios=None, adjuntos=None):
    cfg, secret = _configuracion()
    destinatarios = destinatarios or cfg.get("Destinatario") or []
    if not destinatarios:
        raise MailError("No hay destinatarios configurados.")
    _send_mail(cfg, _token(cfg, secret), asunto, html, destinatarios, adjuntos)
    log.info("Correo '%s' aceptado por Microsoft Graph para: %s", asunto, ", ".join(destinatarios))
    return destinatarios
