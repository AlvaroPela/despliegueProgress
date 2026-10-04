"""Motor de despliegue (portado del script original DespliegueAutomatico.ps1).

Etapas:
  1. Estructura de carpetas del caso y copia de fuentes (incluida la red N:)
  2. Compilación con OpenEdge (prowin.exe), leyendo compilacion.log de compilar.p
  3. Backup previo desde el primer servidor destino y copia de los .r a todos los destinos
  4. Notificación por correo (OAuth 2.0)
"""
import html
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from config import COMPILAR_P_PATH, LOG_DIR, load_config, load_servidores
from services import credentials, history, mailer, versions
from services.system import extraer_ip, ping

log = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PASOS = {
    1: "Preparando estructura y fuentes",
    2: "Compilando en OpenEdge",
    3: "Backup y despliegue en servidores",
    4: "Notificación por correo",
}
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Septiembre", "Octubre", "Noviembre", "Diciembre"]
CASO_RE = re.compile(r"^[\w\-]{1,40}$")
EXT_FUENTES = (".p", ".w")
MAX_HILOS_COPIA = 8

_run_lock = threading.Lock()
_caso_activo = {"caso": None}


class DeployError(Exception):
    def __init__(self, estado, mensaje):
        super().__init__(mensaje)
        self.estado = estado


class DeployBusy(Exception):
    pass


# ----------------------------------------------------------------------------
# Contexto de una ejecución (log + progreso)
# ----------------------------------------------------------------------------
class Run:
    def __init__(self, reg_id, caso, usuario, destino, ips, actualizar, ruta_mb, log_file):
        self.id = reg_id
        self.caso = caso
        self.usuario = usuario
        self.destino = destino
        self.ips = ips
        self.actualizar = actualizar == "S"
        self.ruta_mb = ruta_mb
        self.log_file = log_file
        self.log_path = os.path.join(LOG_DIR, log_file)
        self.progress_path = os.path.join(LOG_DIR, f"progreso_{reg_id}.json")
        self.inicio = time.time()
        self.cfg = load_config()
        self.tipo = ""
        self.ramas = []
        self.targets = []
        self.advertencias = []
        self.fuentes = []
        self.incluidos = []
        self.versiones = {}
        self.exitosos = []
        self.backups = []
        self.resultados_copia = []
        self.dir_caso = ""
        self.dir_backup = ""
        self.paso = 0
        self.nombre_paso = "Iniciando"

    def log(self, mensaje, nivel="INFO"):
        linea = f"[{datetime.now():%H:%M:%S}] [{nivel}] {mensaje}\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(linea)

    def advertir(self, mensaje):
        self.advertencias.append(mensaje)
        self.log(mensaje, "WARN")

    def progreso(self, paso, detalle, estado="running"):
        self.paso = paso
        self.nombre_paso = PASOS.get(paso, "Finalizado")
        data = {
            "step": paso, "step_name": self.nombre_paso, "details": detalle, "status": estado,
            "elapsed": int(time.time() - self.inicio), "advertencias": len(self.advertencias),
            "id": self.id,
        }
        tmp = self.progress_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self.progress_path)

    def duracion(self):
        s = int(time.time() - self.inicio)
        return f"{s // 60:02d}:{s % 60:02d}"


# ----------------------------------------------------------------------------
# Resolución de destinos
# ----------------------------------------------------------------------------
def _ruta_oficina(entrada):
    return entrada if entrada.startswith("\\\\") else rf"\\{entrada}\Escala"


def resolver_destinos(destino, ips_texto, servidores):
    """Devuelve (tipo, ramas, targets, advertencias). Lanza ValueError si no hay nada válido."""
    dg = list(servidores["DG"])
    oficinas = [_ruta_oficina(o) for o in servidores["Oficinas"]]
    advertencias = []

    if destino == "1":
        tipo, ramas, targets = "DG", ["DG"], dg
    elif destino == "2":
        tipo, ramas, targets = "Oficinas", ["Oficinas"], oficinas
    elif destino == "3":
        tipo, ramas, targets = "Todos", ["DG", "Oficinas"], dg + oficinas
    elif destino == "4":
        tipo, ramas, targets = "Marcha Blanca", [], []
        for crudo in (ips_texto or "").split(","):
            ip = extraer_ip(crudo.strip())
            if not ip:
                continue
            encontrado = next((t for t in dg if extraer_ip(t) == ip), None)
            rama = "DG"
            if not encontrado:
                encontrado = next((t for t in oficinas if extraer_ip(t) == ip), None)
                rama = "Oficinas"
            if encontrado:
                targets.append(encontrado)
                if rama not in ramas:
                    ramas.append(rama)
            else:
                advertencias.append(f"La IP {ip} no existe en servidores.json y fue omitida.")
        if not targets:
            raise ValueError("Ninguna de las IPs ingresadas está registrada en servidores.json.")
    else:
        raise ValueError("Destino de despliegue no válido.")

    unicos, vistos = [], set()
    for t in targets:
        if t.lower() not in vistos:
            vistos.add(t.lower())
            unicos.append(t)
    if not unicos:
        raise ValueError("No hay servidores configurados para el destino elegido (revisa Ajustes > Servidores).")
    return tipo, ramas, unicos, advertencias


# ----------------------------------------------------------------------------
# Entrada pública
# ----------------------------------------------------------------------------
def despliegue_en_curso():
    return _caso_activo["caso"] if _run_lock.locked() else None


def _limpiar_directorio(ruta):
    os.makedirs(ruta, exist_ok=True)
    for nombre in os.listdir(ruta):
        p = os.path.join(ruta, nombre)
        try:
            shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.unlink(p)
        except OSError as exc:
            log.warning("No se pudo borrar %s: %s", p, exc)


def _guardar_archivos(archivos, carpeta, extensiones):
    guardados = []
    for f in archivos:
        nombre = os.path.basename((f.filename or "").replace("\\", "/"))
        if not nombre:
            continue
        if not nombre.lower().endswith(extensiones):
            raise ValueError(f"Extensión no permitida: {nombre}")
        f.save(os.path.join(carpeta, nombre))
        guardados.append(nombre)
    return guardados


def iniciar(usuario, caso, destino, ips, actualizar, ruta_mb, archivos_prin, archivos_inc):
    """Valida, prepara los archivos y lanza el despliegue en un hilo. Devuelve el id del registro."""
    caso = (caso or "").strip()
    if not CASO_RE.match(caso):
        raise ValueError("El número de caso solo admite letras, números, guion y guion bajo.")
    cfg = load_config()
    tipo, ramas, targets, adv = resolver_destinos(destino, ips, load_servidores())
    if not any((f.filename or "").strip() for f in archivos_prin):
        raise ValueError("Debes subir al menos un programa (.p / .w).")

    if not _run_lock.acquire(blocking=False):
        raise DeployBusy(f"Ya hay un despliegue en curso (caso {_caso_activo['caso']}). Espera a que termine.")
    try:
        _caso_activo["caso"] = caso
        os.makedirs(LOG_DIR, exist_ok=True)
        origen = cfg["RutaOrigen"]
        incluidos_dir = os.path.join(origen, "Incluido")
        _limpiar_directorio(origen)
        os.makedirs(incluidos_dir, exist_ok=True)
        _guardar_archivos(archivos_prin, origen, EXT_FUENTES)
        _guardar_archivos(archivos_inc, incluidos_dir, (".i",))

        reg_id = history.crear(caso, usuario, tipo)
        log_file = f"log_{caso}_{datetime.now():%Y%m%d%H%M%S}.txt"
        history.actualizar(reg_id, Log_File=log_file)
        run = Run(reg_id, caso, usuario, destino, ips, actualizar, ruta_mb, log_file)
        run.tipo, run.ramas, run.targets = tipo, ramas, targets
        run.advertencias.extend(adv)
        run.progreso(1, "En cola...")
        threading.Thread(target=_ejecutar, args=(run,), name=f"deploy-{reg_id}", daemon=True).start()
        return reg_id
    except Exception:
        _caso_activo["caso"] = None
        _run_lock.release()
        raise


def _registrar(run, **campos):
    """Actualiza el historial sin interrumpir el hilo si el Excel está bloqueado."""
    try:
        history.actualizar(run.id, **campos)
    except Exception as exc:
        log.exception("No se pudo actualizar el historial del despliegue %s", run.id)
        run.log(f"No se pudo actualizar historial.xlsx: {exc}", "WARN")


def _ejecutar(run):
    try:
        run.log(f"=== DESPLIEGUE caso {run.caso} | usuario {run.usuario} | destino {run.tipo} ===")
        for adv in run.advertencias:
            run.log(adv, "WARN")
        _etapa1(run)
        _etapa2(run)
        _etapa3(run)
        estado = "Exitoso" if not run.advertencias else "Exitoso con advertencias"
        _etapa4(run, estado)
        run.log("PROCESO DE DESPLIEGUE FINALIZADO")
        detalle = " | ".join(run.advertencias)[:600]
        _registrar(run, Estado=estado, Detalle=detalle, Duracion=run.duracion())
        run.progreso(5, "Despliegue completado" + (" con advertencias" if run.advertencias else ""),
                     "warning" if run.advertencias else "success")
    except DeployError as exc:
        run.log(str(exc), "ERROR")
        _notificar_fallo(run, exc.estado, str(exc))
        _registrar(run, Estado=exc.estado, Detalle=str(exc)[:600], Duracion=run.duracion())
        run.progreso(run.paso or 1, str(exc), "error")
    except Exception as exc:  # error inesperado: nunca dejar el registro "En Proceso"
        run.log("Error inesperado:\n" + traceback.format_exc(), "ERROR")
        log.exception("Fallo inesperado en despliegue %s", run.id)
        _notificar_fallo(run, "Error", str(exc))
        _registrar(run, Estado="Error", Detalle=f"Error inesperado: {exc}"[:600], Duracion=run.duracion())
        run.progreso(run.paso or 1, f"Error inesperado: {exc}", "error")
    finally:
        _caso_activo["caso"] = None
        _run_lock.release()


# ----------------------------------------------------------------------------
# Etapa 1: estructura y fuentes
# ----------------------------------------------------------------------------
def _copiar(run, origen, destino, critico=False):
    try:
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.copy2(origen, destino)
        return True
    except OSError as exc:
        if critico:
            raise DeployError("Error", f"No se pudo copiar {os.path.basename(origen)}: {exc}")
        run.advertir(f"No se pudo copiar a {destino}: {exc}")
        return False


def _etapa1(run):
    cfg = run.cfg
    run.progreso(1, "Creando carpetas del caso...")
    origen = cfg["RutaOrigen"]
    inc_origen = os.path.join(origen, "Incluido")
    run.fuentes = sorted(f for f in os.listdir(origen)
                         if os.path.isfile(os.path.join(origen, f)) and f.lower().endswith(EXT_FUENTES))
    if not run.fuentes:
        raise DeployError("Error", f"No se encontraron programas (.p / .w) en {origen}.")
    run.incluidos = sorted(f for f in os.listdir(inc_origen) if f.lower().endswith(".i")) \
        if os.path.isdir(inc_origen) else []
    run.versiones = {f: versions.desde_archivo(os.path.join(origen, f)) for f in run.fuentes}
    run.log("Programas: " + ", ".join(f"{n} (v{v})" for n, v in run.versiones.items()))

    ahora = datetime.now()
    run.dir_caso = os.path.join(cfg["RutaBaseY"], str(ahora.year), MESES[ahora.month - 1], run.caso)
    run.dir_backup = os.path.join(run.dir_caso, "Backup")
    try:
        os.makedirs(run.dir_backup, exist_ok=True)
        for rama in run.ramas:
            comp = os.path.join(run.dir_caso, rama, "compilados")
            os.makedirs(comp, exist_ok=True)
            for f in os.listdir(comp):
                try:
                    os.unlink(os.path.join(comp, f))
                except OSError:
                    pass
    except OSError as exc:
        raise DeployError("Error", f"No se pudo crear la estructura en {run.dir_caso}: {exc}")

    rutinas = {n.lower() for n in cfg["RutinasEspeciales"]}
    es_mb = run.destino == "4"
    actualizar_red = (not es_mb) or run.actualizar
    base_n, rutinas_n = cfg["RutaBaseN"], cfg["RutaRutinasN"]

    for i, nombre in enumerate(run.fuentes, 1):
        run.progreso(1, f"[{i}/{len(run.fuentes)}] Copiando {nombre}...")
        src = os.path.join(origen, nombre)
        for rama in run.ramas:
            _copiar(run, src, os.path.join(run.dir_caso, rama, nombre), critico=True)
        if nombre.lower() in rutinas:
            run.log(f"{nombre} es una RUTINA ESPECIAL -> {rutinas_n}")
            if actualizar_red:
                _copiar(run, src, os.path.join(rutinas_n, nombre))
        elif run.destino == "1":
            _copiar(run, src, os.path.join(base_n, "FuentesDG", nombre))
        elif run.destino in ("2", "3"):
            _copiar(run, src, os.path.join(base_n, "FuentesOficinas", nombre))
        elif es_mb and run.actualizar and run.ruta_mb:
            _copiar(run, src, os.path.join(run.ruta_mb, nombre))

    if run.incluidos:
        dir_inc = os.path.join(run.dir_caso, "Incluido")
        for nombre in run.incluidos:
            src = os.path.join(inc_origen, nombre)
            _copiar(run, src, os.path.join(dir_inc, nombre), critico=True)
            if not es_mb:
                _copiar(run, src, os.path.join(base_n, "Incluido", nombre))
            elif run.actualizar and run.ruta_mb:
                _copiar(run, src, os.path.join(run.ruta_mb, "Incluido", nombre))
    run.log("Etapa 1 completada")


# ----------------------------------------------------------------------------
# Etapa 2: compilación
# ----------------------------------------------------------------------------
def _enmascarar(cmd):
    salida, ocultar = [], False
    for parte in cmd:
        salida.append("********" if ocultar else parte)
        ocultar = parte == "-P"
    return " ".join(salida)


def _leer_desde(ruta, offset):
    try:
        with open(ruta, "rb") as f:
            f.seek(offset)
            return f.read().decode("cp1252", errors="replace").strip()
    except OSError:
        return ""


def _etapa2(run):
    cfg = run.cfg
    run.progreso(2, "Leyendo credenciales de base de datos...")
    datos = credentials.cargar("Datos")
    if not datos:
        raise DeployError("Error de Credenciales",
                          "No se pudieron leer las credenciales de BD (¿no configuradas o guardadas por otro usuario de Windows?). "
                          "Configúralas en Perfil > Base de datos con el usuario que ejecuta el servicio.")
    seguimiento = credentials.cargar("Seguimiento") or datos
    if not os.path.exists(cfg["ProgressExe"]):
        raise DeployError("Error", f"No se encontró {cfg['ProgressExe']}.")
    if not os.path.exists(COMPILAR_P_PATH):
        raise DeployError("Error", f"No se encontró compilar.p en {COMPILAR_P_PATH}.")
    os.makedirs(r"C:\tempo", exist_ok=True)

    rama_ref = run.ramas[0]
    carpeta = os.path.join(run.dir_caso, rama_ref, "compilados")
    log_compilacion = os.path.join(carpeta, "compilacion.log")
    fallidos = []

    for i, nombre in enumerate(run.fuentes, 1):
        run.progreso(2, f"[{i}/{len(run.fuentes)}] Compilando {nombre}...")
        origen = os.path.join(cfg["RutaOrigen"], nombre)
        cmd = [
            cfg["ProgressExe"], "-b", "-cpinternal", "undefined", "-cpstream", "undefined",
            "-p", COMPILAR_P_PATH, "-param", f"{origen};{carpeta}",
            "-basekey", "INI", "-ini", cfg["ProgressIni"],
            "-db", "BdAgencias.db", "-ld", "datos", "-H", cfg["DbHost"], "-S", str(cfg["DbPuertoDatos"]),
            "-U", datos[0], "-P", datos[1],
            "-db", "Seguimiento.db", "-ld", "seguimiento", "-H", cfg["DbHost"], "-S", str(cfg["DbPuertoSeguimiento"]),
            "-U", seguimiento[0], "-P", seguimiento[1],
            "-N", "tcp", "-Mm", "2048", "-T", r"c:\tempo", "-Wa", "-wpp",
        ]
        run.log(f"Compilando {nombre}")
        run.log("CMD: " + _enmascarar(cmd), "DEBUG")
        offset = os.path.getsize(log_compilacion) if os.path.exists(log_compilacion) else 0
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                                 timeout=int(cfg["TimeoutCompilacion"]), creationflags=_NO_WINDOW)
            codigo, salida = res.returncode, (res.stdout + res.stderr).strip()
        except subprocess.TimeoutExpired:
            run.log(f"{nombre}: tiempo de espera agotado ({cfg['TimeoutCompilacion']} s)", "ERROR")
            fallidos.append(nombre)
            continue
        except OSError as exc:
            raise DeployError("Error", f"No se pudo ejecutar prowin.exe: {exc}")

        detalle_progress = _leer_desde(log_compilacion, offset)
        if detalle_progress:
            run.log(detalle_progress)
        if salida:
            run.log("Salida de prowin: " + salida, "DEBUG")
        r_generado = os.path.join(carpeta, os.path.splitext(nombre)[0] + ".r")
        if os.path.isfile(r_generado) and "[ERROR]" not in detalle_progress:
            run.exitosos.append(os.path.basename(r_generado))
            run.log(f"{nombre} compilado correctamente")
        else:
            fallidos.append(nombre)
            if not detalle_progress:
                run.log(f"{nombre}: no se generó compilacion.log (código {codigo}). Posible fallo de conexión a la BD, "
                        "credenciales inválidas o ruta INI inaccesible.", "ERROR")

    if fallidos:
        raise DeployError("Fallo Compilación", "Fallaron: " + ", ".join(fallidos) + ". Revisa el log técnico.")

    for rama in run.ramas[1:]:  # misma compilación para las demás ramas
        for r in run.exitosos:
            _copiar(run, os.path.join(carpeta, r), os.path.join(run.dir_caso, rama, "compilados", r))
    run.log("Etapa 2 completada")


# ----------------------------------------------------------------------------
# Etapa 3: backup y despliegue
# ----------------------------------------------------------------------------
def _copiar_a_target(run, target, archivos, progreso):
    ip = extraer_ip(target) or target
    resultado = {"target": target, "ip": ip, "estado": "ok", "copiados": 0, "errores": []}
    if not ping(ip):
        resultado["estado"] = "sin_ping"
    else:
        for f in archivos:
            try:
                shutil.copy2(f, target)
                resultado["copiados"] += 1
            except OSError as exc:
                resultado["errores"].append(f"{os.path.basename(f)}: {exc}")
        if resultado["errores"]:
            resultado["estado"] = "error" if not resultado["copiados"] else "parcial"
    progreso(resultado)
    return resultado


def _etapa3(run):
    cfg = run.cfg
    run.progreso(3, "Reuniendo compilados...")
    destino_comp = cfg["RutaCompilados"]
    os.makedirs(destino_comp, exist_ok=True)
    for f in os.listdir(destino_comp):
        p = os.path.join(destino_comp, f)
        if os.path.isfile(p):
            try:
                os.unlink(p)
            except OSError:
                pass
    for rama in run.ramas:
        carpeta = os.path.join(run.dir_caso, rama, "compilados")
        for r in run.exitosos:
            ruta = os.path.join(carpeta, r)
            if os.path.isfile(ruta):
                shutil.copy2(ruta, destino_comp)
    archivos = sorted(os.path.join(destino_comp, f) for f in os.listdir(destino_comp) if f.lower().endswith(".r"))
    if not archivos:
        raise DeployError("Fallo Compilación", "No se generaron archivos .r válidos. No hay nada para desplegar.")

    # --- Backup previo (protegido con ping) ---
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    base = run.targets[0]
    ip_base = extraer_ip(base) or base
    run.progreso(3, f"Backup previo desde {ip_base}...")
    if ping(ip_base):
        dir_backup_local = os.path.join(cfg["RutaBackup"], f"{stamp}_{run.tipo.replace(' ', '')}")
        for f in archivos:
            nombre = os.path.basename(f)
            remoto = os.path.join(base, nombre)
            try:
                if os.path.isfile(remoto):
                    nombre_bk = f"{os.path.splitext(nombre)[0]}_{stamp}.r"
                    os.makedirs(dir_backup_local, exist_ok=True)
                    shutil.copy2(remoto, os.path.join(run.dir_backup, nombre_bk))
                    shutil.copy2(remoto, os.path.join(dir_backup_local, nombre_bk))
                    run.backups.append(nombre_bk)
                    run.log(f"Backup de {nombre} guardado en {run.dir_backup} y {dir_backup_local}")
                else:
                    run.log(f"{nombre} no existe aún en {base}: no hay versión previa que respaldar")
            except OSError as exc:
                run.advertir(f"No se pudo respaldar {remoto}: {exc}")
    else:
        run.advertir(f"El servidor {ip_base} no responde al ping: se omitió el backup previo.")

    # --- Copia a los destinos ---
    total = len(run.targets)
    hechos = {"n": 0}
    lock = threading.Lock()

    def avance(res):
        with lock:
            hechos["n"] += 1
            run.log(f"[{hechos['n']}/{total}] {res['target']}: {res['estado']} "
                    f"({res['copiados']} archivo(s)) " + "; ".join(res["errores"]))
            run.progreso(3, f"Copiando a servidores ({hechos['n']}/{total})...")

    run.progreso(3, f"Copiando a servidores (0/{total})...")
    with ThreadPoolExecutor(max_workers=MAX_HILOS_COPIA) as pool:
        run.resultados_copia = list(pool.map(lambda t: _copiar_a_target(run, t, archivos, avance), run.targets))

    ok = [r for r in run.resultados_copia if r["estado"] == "ok"]
    sin_ping = [r for r in run.resultados_copia if r["estado"] == "sin_ping"]
    con_error = [r for r in run.resultados_copia if r["estado"] in ("error", "parcial")]
    if sin_ping:
        run.advertir("Sin ping: " + ", ".join(r["ip"] for r in sin_ping))
    if con_error:
        run.advertir("Errores de copia en: " + ", ".join(r["ip"] for r in con_error))
    if not ok and not any(r["copiados"] for r in run.resultados_copia):
        raise DeployError("Fallo Despliegue", "No se pudo copiar a ningún servidor destino.")
    run.log(f"Etapa 3 completada: {len(ok)}/{total} servidores sin novedad")


# ----------------------------------------------------------------------------
# Etapa 4: correo
# ----------------------------------------------------------------------------
def _fila(etiqueta, valor):
    return (f"<tr><td style='padding:6px 12px;color:#667;border-bottom:1px solid #eee'>{html.escape(etiqueta)}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #eee'><b>{valor}</b></td></tr>")


def _html_reporte(run, estado, mensaje=""):
    color = "#2e7d32" if estado.startswith("Exitoso") else "#c62828"
    ok = sum(1 for r in run.resultados_copia if r["estado"] == "ok")
    filas = [
        _fila("Caso", html.escape(run.caso)),
        _fila("Solicitado por", html.escape(run.usuario)),
        _fila("Fecha", f"{datetime.now():%Y-%m-%d %H:%M:%S}"),
        _fila("Destino", html.escape(run.tipo)),
        _fila("Duración", run.duracion()),
        _fila("Servidores OK", f"{ok} / {len(run.targets)}"),
        _fila("Backup previo", html.escape(run.dir_backup) if run.backups else "Sin versión previa / omitido"),
        _fila("Verificación en Escala", "Pendiente de confirmación manual"),
    ]
    progs = "".join(f"<li>{html.escape(n)} &mdash; v{html.escape(v)}</li>" for n, v in run.versiones.items())
    adv = "".join(f"<li>{html.escape(a)}</li>" for a in run.advertencias)
    return (
        "<div style='font-family:Segoe UI,Arial,sans-serif;max-width:640px'>"
        f"<div style='background:{color};color:#fff;padding:16px 20px;border-radius:8px 8px 0 0'>"
        f"<h2 style='margin:0'>Despliegue {html.escape(estado)}</h2></div>"
        f"<table style='width:100%;border-collapse:collapse;border:1px solid #eee'>{''.join(filas)}</table>"
        f"<h4>Programas y versiones</h4><ul>{progs}</ul>"
        + (f"<h4>Error</h4><p style='color:#c62828'>{html.escape(mensaje)}</p>" if mensaje else "")
        + (f"<h4>Advertencias</h4><ul>{adv}</ul>" if adv else "")
        + "<p style='color:#999;font-size:12px'>Mensaje automático del Sistema de Despliegues.</p></div>"
    )


def _etapa4(run, estado):
    run.progreso(4, "Enviando notificación por correo...")
    try:
        mailer.enviar(f"[{estado}] Despliegue caso {run.caso} - {run.tipo}", _html_reporte(run, estado))
        run.log("Correo enviado")
    except mailer.MailError as exc:
        run.advertir(f"Correo no enviado: {exc}")
    except Exception as exc:
        log.exception("Error enviando correo")
        run.advertir(f"Correo no enviado: {exc}")


def _notificar_fallo(run, estado, mensaje):
    try:
        mailer.enviar(f"[{estado}] Despliegue caso {run.caso} - {run.tipo}", _html_reporte(run, estado, mensaje))
        run.log("Correo de fallo enviado")
    except Exception as exc:
        run.log(f"Correo de fallo no enviado: {exc}", "WARN")
