"""Credenciales cifradas con DPAPI (perfil del usuario de Windows que ejecuta la aplicación).

Se usa Export-Clixml / Import-Clixml, el mismo formato del script original de PowerShell,
por lo que los archivos existentes siguen siendo válidos.
Los secretos viajan al subproceso por variables de entorno (nunca se interpolan en el script).
"""
import base64
import logging
import os
import subprocess

log = logging.getLogger(__name__)

CRED_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "SistemaDesplieguesProgress",
    "Credenciales",
)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

NOMBRES_VALIDOS = ("Datos", "Seguimiento", "Smtp")


def _ruta(nombre):
    if nombre not in NOMBRES_VALIDOS:
        raise ValueError(f"Credencial desconocida: {nombre}")
    return os.path.join(CRED_DIR, f"{nombre}.xml")


def _powershell(script, env_extra=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    try:
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, env=env, timeout=40, creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("PowerShell no respondió a tiempo (40 s).")
    except OSError as exc:
        raise RuntimeError(f"No se pudo ejecutar PowerShell (se requiere Windows): {exc}")


def existe(nombre):
    return os.path.isfile(_ruta(nombre))


def guardar(nombre, usuario, clave):
    ruta = _ruta(nombre)
    script = (
        "$ErrorActionPreference='Stop';"
        "New-Item -ItemType Directory -Force -Path $env:SD_DIR | Out-Null;"
        "$s = ConvertTo-SecureString $env:SD_PASS -AsPlainText -Force;"
        "$c = New-Object System.Management.Automation.PSCredential($env:SD_USER, $s);"
        "$c | Export-Clixml -Path $env:SD_FILE"
    )
    res = _powershell(script, {"SD_DIR": CRED_DIR, "SD_USER": usuario, "SD_PASS": clave, "SD_FILE": ruta})
    if res.returncode != 0:
        log.error("No se pudo guardar la credencial %s: %s", nombre, res.stderr.strip())
        raise RuntimeError("No se pudo cifrar y guardar la credencial: " + (res.stderr.strip() or "error desconocido"))


def cargar(nombre):
    """Devuelve (usuario, clave) o None si no existe / no se puede descifrar con el usuario actual."""
    if not existe(nombre):
        return None
    script = (
        "$ErrorActionPreference='Stop';"
        "$c = Import-Clixml -Path $env:SD_FILE;"
        "$u = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($c.UserName));"
        "$p = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($c.GetNetworkCredential().Password));"
        "[Console]::Out.Write($u + ':' + $p)"
    )
    try:
        res = _powershell(script, {"SD_FILE": _ruta(nombre)})
    except RuntimeError as exc:
        log.error("No se pudo leer la credencial %s: %s", nombre, exc)
        return None
    if res.returncode != 0 or ":" not in res.stdout:
        log.error("No se pudo descifrar la credencial %s (¿otro usuario de Windows?): %s", nombre, res.stderr.strip())
        return None
    u, p = res.stdout.strip().split(":", 1)
    return base64.b64decode(u).decode("utf-8"), base64.b64decode(p).decode("utf-8")


def usuario_de(nombre):
    cred = cargar(nombre)
    return cred[0] if cred else ""


BASES_BD = ("Datos", "Seguimiento")  # BdAgencias.db (-ld datos) y Seguimiento.db (-ld seguimiento)


def guardar_bd(base, usuario, clave):
    """Cada base de datos tiene su propio usuario y contraseña."""
    if base not in BASES_BD:
        raise ValueError(f"Base de datos desconocida: {base}")
    guardar(base, usuario, clave)


def bd_configurada():
    return all(existe(b) for b in BASES_BD)
