import socket
import threading
import queue
import json
import sqlite3
import time
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# ==============================================================================
# CONFIGURACIÓN DEL SERVIDOR DISTRIBUIDO
# ==============================================================================
# Institución: IFTS N.° 29
# Materia: Programación sobre redes - 3.° D
# Alumno: Rodrigo Berger
# Proyecto: PFO 3 - Rediseño del Sistema de Usuarios (PFO 2) como Sistema Distribuido
HOST = "localhost"
PORT = 5000
NUM_WORKERS = 3
BUFFER_SIZE = 4096
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "usuarios_distribuido.db")

# Cola sincronizada de tareas para los workers
cola_tareas = queue.Queue()

# ==============================================================================
# 1. BASE DE DATOS DISTRIBUIDA (SQLITE / POSTGRESQL SIMULADO)
# ==============================================================================
def get_db():
    """Cada hilo abre y cierra su propia conexión para garantizar concurrencia segura."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_db():
    """Crea las tablas de usuarios y de archivos/objetos S3."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            contrasena_hash TEXT NOT NULL,
            fecha_registro TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS archivos_s3 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            nombre_archivo TEXT NOT NULL,
            s3_uri TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            fecha_subida TEXT NOT NULL
        )
    """)
    conn.commit()

    # Usuarios de prueba iniciales (iguales a los del PFO 2)
    cursor.execute("SELECT COUNT(*) as total FROM usuarios")
    if cursor.fetchone()["total"] == 0:
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for u in ["Rodrigo", "Berger"]:
            cursor.execute(
                "INSERT INTO usuarios (usuario, contrasena_hash, fecha_registro) VALUES (?, ?, ?)",
                (u, generate_password_hash("1234"), fecha)
            )
        conn.commit()
        print("[DB] Usuarios de prueba creados: 'Rodrigo' y 'Berger' (clave: '1234')")

    conn.close()
    print(f"[DB] Base de datos '{DB_NAME}' inicializada con éxito.")

# ==============================================================================
# 2. LÓGICA DE PROCESAMIENTO DISTRIBUIDO (TAREAS DEL PFO 2)
# ==============================================================================
def procesar_registro(parametros):
    usuario = parametros.get("usuario", "").strip()
    contrasena = parametros.get("contrasena", "").strip()

    if not usuario or not contrasena:
        return {"status": "error", "codigo": 400, "mensaje": "Debe enviar 'usuario' y 'contrasena'."}

    # El worker ejecuta el cómputo pesado del hash criptográfico con salt (PBKDF2/scrypt)
    hash_clave = generate_password_hash(contrasena)
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO usuarios (usuario, contrasena_hash, fecha_registro) VALUES (?, ?, ?)",
            (usuario, hash_clave, fecha)
        )
        conn.commit()
        nuevo_id = cursor.lastrowid
        conn.close()
        return {
            "status": "success",
            "codigo": 201,
            "mensaje": f"Usuario '{usuario}' registrado con hash en el clúster.",
            "usuario": {"id": nuevo_id, "usuario": usuario, "fecha_registro": fecha}
        }
    except sqlite3.IntegrityError:
        conn.close()
        return {"status": "error", "codigo": 409, "mensaje": f"El usuario '{usuario}' ya existe."}
    except Exception as e:
        conn.close()
        return {"status": "error", "codigo": 500, "mensaje": f"Error interno: {str(e)}"}

def procesar_login(parametros):
    usuario = parametros.get("usuario", "").strip()
    contrasena = parametros.get("contrasena", "").strip()

    if not usuario or not contrasena:
        return {"status": "error", "codigo": 400, "mensaje": "Debe enviar 'usuario' y 'contrasena'."}

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,))
    user = cursor.fetchone()
    conn.close()

    # El worker verifica el hash de forma concurrente
    if not user or not check_password_hash(user["contrasena_hash"], contrasena):
        return {"status": "error", "codigo": 401, "mensaje": "Credenciales inválidas."}

    return {
        "status": "success",
        "codigo": 200,
        "mensaje": f"Login exitoso. ¡Bienvenido/a {usuario}!",
        "usuario": {"id": user["id"], "usuario": user["usuario"]}
    }

def procesar_listar_usuarios(parametros):
    # Verificación de credenciales (endpoint protegido como en PFO 2)
    auth_user = parametros.get("auth_usuario", "").strip()
    auth_pass = parametros.get("auth_contrasena", "").strip()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE usuario = ?", (auth_user,))
    user = cursor.fetchone()

    if not user or not check_password_hash(user["contrasena_hash"], auth_pass):
        conn.close()
        return {"status": "error", "codigo": 401, "mensaje": "Acceso no autorizado. Debe iniciar sesión primero."}

    cursor.execute("SELECT id, usuario, fecha_registro FROM usuarios ORDER BY id ASC")
    filas = cursor.fetchall()
    conn.close()

    lista = [{"id": f["id"], "usuario": f["usuario"], "fecha_registro": f["fecha_registro"]} for f in filas]
    return {
        "status": "success",
        "codigo": 200,
        "solicitado_por": auth_user,
        "total_usuarios": len(lista),
        "usuarios": lista
    }

def procesar_subir_archivo(parametros):
    """Guarda metadatos en la base de datos y simula almacenamiento en Amazon S3."""
    usuario = parametros.get("auth_usuario", "anonimo")
    nombre_archivo = parametros.get("nombre", "avatar.png")
    contenido = parametros.get("contenido", "Datos binarios")

    s3_uri = f"s3://bucket-usuarios-pfo3/{usuario}/{nombre_archivo}"
    bytes_archivo = len(contenido.encode("utf-8"))
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    time.sleep(0.3)  # Simula latencia de almacenamiento de objetos

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO archivos_s3 (usuario, nombre_archivo, s3_uri, bytes, fecha_subida) VALUES (?, ?, ?, ?, ?)",
        (usuario, nombre_archivo, s3_uri, bytes_archivo, fecha)
    )
    conn.commit()
    nuevo_id = cursor.lastrowid
    conn.close()

    return {
        "status": "success",
        "codigo": 201,
        "mensaje": f"Archivo '{nombre_archivo}' subido a S3 y registrado en la BD.",
        "s3": {"registro_id": nuevo_id, "s3_uri": s3_uri, "bytes": bytes_archivo, "fecha": fecha}
    }

# ==============================================================================
# 3. POOL DE WORKERS CONCURRENTE
# ==============================================================================
def worker_loop(id_worker):
    """Bucle de ejecución de cada hilo trabajador del clúster."""
    print(f"[WORKER {id_worker}] Iniciado y listo para recibir tareas.")
    while True:
        try:
            tipo, parametros, evento_fin, contenedor = cola_tareas.get()
            print(f"[WORKER {id_worker}] Procesando tarea '{tipo}'...")
            t0 = time.time()

            if tipo == "registro":
                resp = procesar_registro(parametros)
            elif tipo == "login":
                resp = procesar_login(parametros)
            elif tipo == "listar_usuarios":
                resp = procesar_listar_usuarios(parametros)
            elif tipo == "subir_archivo":
                resp = procesar_subir_archivo(parametros)
            else:
                resp = {"status": "error", "mensaje": f"Tarea '{tipo}' no soportada."}

            duracion_ms = round((time.time() - t0) * 1000, 2)
            resp["worker"] = f"Worker-{id_worker}"
            resp["tiempo_ms"] = duracion_ms
            contenedor.update(resp)

            print(f"[WORKER {id_worker}] Tarea '{tipo}' completada ({duracion_ms} ms).")
            cola_tareas.task_done()
            evento_fin.set()

        except Exception as e:
            print(f"[ERROR WORKER {id_worker}] Error: {e}")

# ==============================================================================
# 4. GESTIÓN DE CONEXIONES POR SOCKET
# ==============================================================================
def atender_cliente(conn, addr):
    ip, puerto = addr
    print(f"[NUEVA CONEXIÓN] Cliente conectado desde {ip}:{puerto}")

    try:
        while True:
            datos = conn.recv(BUFFER_SIZE)
            if not datos:
                break

            mensaje = datos.decode("utf-8").strip()
            if mensaje.lower() in ["éxito", "exito", "salir"]:
                print(f"[DESCONEXIÓN] Cliente {ip}:{puerto} cerró sesión.")
                break

            try:
                peticion = json.loads(mensaje)
                tipo = peticion.get("tipo", "")
                parametros = peticion.get("parametros", {})

                evento_fin = threading.Event()
                resultado = {}

                # Encolar en el Worker Pool
                cola_tareas.put((tipo, parametros, evento_fin, resultado))
                evento_fin.wait(timeout=10.0)

                conn.sendall(json.dumps(resultado).encode("utf-8"))

            except json.JSONDecodeError:
                conn.sendall(json.dumps({"status": "error", "mensaje": "JSON inválido"}).encode("utf-8"))

    except ConnectionResetError:
        print(f"[AVISO] Cliente {ip}:{puerto} desconectado abruptamente.")
    except Exception as e:
        print(f"[ERROR COMUNICACIÓN] {ip}:{puerto}: {e}")
    finally:
        conn.close()
        print(f"[SOCKET CERRADO] Finalizada conexión con {ip}:{puerto}")

# ==============================================================================
# 5. INICIAR SERVIDOR
# ==============================================================================
def iniciar_servidor():
    print("=" * 65)
    print("   SERVIDOR DISTRIBUIDO DE USUARIOS Y AUTENTICACIÓN (PFO 3)")
    print("   Rediseño del PFO 2 con Sockets TCP y Worker Pool")
    print("   IFTS N.° 29 | Prog. sobre redes - 3.° D | Rodrigo Berger")
    print("=" * 65)

    inicializar_db()

    print(f"[SISTEMA] Iniciando Worker Pool con {NUM_WORKERS} hilos...")
    for i in range(1, NUM_WORKERS + 1):
        t = threading.Thread(target=worker_loop, args=(i,), daemon=True)
        t.start()

    try:
        servidor_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        servidor_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor_socket.bind((HOST, PORT))
        servidor_socket.listen(5)
        print(f"[SERVIDOR] Escuchando conexiones TCP en {HOST}:{PORT}...")
    except OSError as e:
        print(f"[ERROR RED] Puerto {PORT} ocupado: {e}")
        return

    try:
        while True:
            conn, addr = servidor_socket.accept()
            threading.Thread(target=atender_cliente, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[SERVIDOR] Deteniendo servidor (Ctrl+C)...")
    finally:
        servidor_socket.close()
        print("[SERVIDOR] Socket principal cerrado correctamente.")

if __name__ == "__main__":
    iniciar_servidor()
