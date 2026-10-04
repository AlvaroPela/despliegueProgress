"""Envío de correo por SMTP de Office 365 con autenticación moderna (OAuth 2.0 / XOAUTH2).

Flujo "client credentials" de Microsoft Entra ID:
  1. Se pide un token a login.microsoftonline.com con el Client ID, el Tenant y el Client Secret.
  2. Se autentica en smtp.office365.com:587 (STARTTLS) con el mecanismo XOAUTH2.

Requisitos en Entra ID / Exchange Online:
  - App registration con el permiso de aplicación  Office 365 Exchange Online > SMTP.Send  (consentimiento de admin).
  - Registrar el service principal en Exchange (New-ServicePrincipal) y darle permiso sobre el buzón remitente
    (Add-MailboxPermission ... -AccessRights FullAccess).
  - SMTP AUTH habilitado en el buzón remitente.
El Client Secret se guarda cifrado con DPAPI (credencial "Smtp"), nunca en config.json.
"""
import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import load_config
from services import credentials

log = logging.getLogger(__name__)

SCOPE = "https://outlook.office365.com/.default"


class MailError(Exception):
    pass


def _obtener_token(tenant, client_id, secret):
    url = f"https://login.microsoftonline.com/{urllib.parse.quote(tenant)}/oauth2/v2.0/token"
    cuerpo = urllib.parse.urlencode({
        "client_id": client_id, "client_secret": secret,
        "scope": SCOPE, "grant_type": "client_credentials",
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=cuerpo), timeout=30) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as exc:
        try:
            detalle = json.loads(exc.read()).get("error_description", "").split("\r\n")[0]
        except Exception:
            detalle = exc.reason
        raise MailError(f"Entra ID rechazó la solicitud de token ({exc.code}): {detalle}")
    except Exception as exc:
        raise MailError(f"No se pudo contactar a login.microsoftonline.com: {exc}")


def _configuracion():
    cfg = load_config()
    faltantes = [k for k in ("UsuarioSmtp", "ServidorSmtp", "Auth_ClientID", "Auth_Tenant") if not cfg.get(k)]
    if faltantes:
        raise MailError("Falta configurar en Ajustes > Correo: " + ", ".join(faltantes))
    cred = credentials.cargar("Smtp")
    if not cred:
        raise MailError("No hay Client Secret guardado. Configúralo en Ajustes > Correo.")
    return cfg, cred[1]


def _conectar(cfg, secret):
    token = _obtener_token(cfg["Auth_Tenant"], cfg["Auth_ClientID"], secret)
    auth = f"user={cfg['UsuarioSmtp']}\x01auth=Bearer {token}\x01\x01"
    try:
        smtp = smtplib.SMTP(cfg["ServidorSmtp"], int(cfg["PuertoSmtp"]), timeout=30)
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.auth("XOAUTH2", lambda challenge=None: auth)
        return smtp
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError(f"Office 365 rechazó la autenticación XOAUTH2: {exc.smtp_error.decode(errors='ignore')}")
    except Exception as exc:
        raise MailError(f"Fallo en la conexión SMTP: {exc}")


def probar_conexion():
    """Obtiene el token y autentica en SMTP sin enviar nada."""
    cfg, secret = _configuracion()
    smtp = _conectar(cfg, secret)
    smtp.quit()


def enviar(asunto, html, destinatarios=None):
    cfg, secret = _configuracion()
    destinatarios = destinatarios or cfg.get("Destinatario") or []
    if not destinatarios:
        raise MailError("No hay destinatarios configurados.")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = cfg["UsuarioSmtp"]
    msg["To"] = ", ".join(destinatarios)
    msg.attach(MIMEText(html, "html", "utf-8"))
    smtp = _conectar(cfg, secret)
    try:
        smtp.sendmail(cfg["UsuarioSmtp"], destinatarios, msg.as_string())
    except Exception as exc:
        raise MailError(f"No se pudo enviar el mensaje: {exc}")
    finally:
        try:
            smtp.quit()
        except Exception:
            pass
