import socket
import json
import sys

# ==============================================================================
# CLIENTE TCP DISTRIBUIDO - SISTEMA DE USUARIOS
# ==============================================================================
# Institución: IFTS N.° 29
# Materia: Programación sobre redes - 3.° D
# Alumno: Rodrigo Berger
# Proyecto: PFO 3 - Cliente de Sockets para el Sistema de Usuarios (PFO 2)
HOST = "localhost"
PORT = 5000
BUFFER_SIZE = 4096

class ClienteDistribuido:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.socket = None
        self.usuario_actual = None
        self.contrasena_actual = None

    def conectar(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            print(f"[ÉXITO] Conexión establecida con el servidor {self.host}:{self.port}.\n")
            return True
        except ConnectionRefusedError:
            print(f"[ERROR CONEXIÓN] No se pudo conectar a {self.host}:{self.port}.")
            print("[AYUDA] Asegúrate de haber iniciado primero 'servidor.py' en otra terminal.")
            return False
        except Exception as e:
            print(f"[ERROR INESPERADO] {e}")
            return False

    def enviar_peticion(self, tipo, parametros):
        try:
            payload = json.dumps({"tipo": tipo, "parametros": parametros})
            self.socket.sendall(payload.encode("utf-8"))

            respuesta_bytes = self.socket.recv(BUFFER_SIZE)
            if not respuesta_bytes:
                print("[AVISO] El servidor cerró la conexión.")
                return None
            return json.loads(respuesta_bytes.decode("utf-8"))
        except Exception as e:
            print(f"[ERROR COMUNICACIÓN] {e}")
            return None

    def registrar_usuario(self):
        print("\n" + "-" * 50)
        print(" [1] REGISTRO DE NUEVO USUARIO")
        print("-" * 50)
        usuario = input("Nombre de usuario: ").strip()
        contrasena = input("Contraseña: ").strip()

        if not usuario or not contrasena:
            print("[AVISO] Debe ingresar usuario y contraseña.")
            return

        resp = self.enviar_peticion("registro", {"usuario": usuario, "contrasena": contrasena})
        if resp:
            worker = resp.get("worker", "Desconocido")
            t_ms = resp.get("tiempo_ms", 0)
            if resp.get("status") == "success":
                u = resp.get("usuario", {})
                print(f"\n[ÉXITO 201] {resp.get('mensaje')}")
                print(f" -> ID: #{u.get('id')} | Usuario: {u.get('usuario')}")
                print(f" -> Atendido por: {worker} en {t_ms} ms (Hash con salt generado en el worker).")
            else:
                print(f"\n[ERROR {resp.get('codigo')}] {resp.get('mensaje')}")

    def iniciar_sesion(self):
        print("\n" + "-" * 50)
        print(" [2] INICIO DE SESIÓN")
        print("-" * 50)
        usuario = input("Nombre de usuario: ").strip()
        contrasena = input("Contraseña: ").strip()

        if not usuario or not contrasena:
            print("[AVISO] Debe ingresar usuario y contraseña.")
            return

        resp = self.enviar_peticion("login", {"usuario": usuario, "contrasena": contrasena})
        if resp:
            worker = resp.get("worker", "Desconocido")
            t_ms = resp.get("tiempo_ms", 0)
            if resp.get("status") == "success":
                self.usuario_actual = usuario
                self.contrasena_actual = contrasena
                print(f"\n[ÉXITO 200] {resp.get('mensaje')}")
                print(f" -> Sesión iniciada para: '{self.usuario_actual}'")
                print(f" -> Verificación de hash ejecutada por: {worker} en {t_ms} ms.")
            else:
                print(f"\n[ERROR {resp.get('codigo')}] {resp.get('mensaje')}")

    def listar_usuarios(self):
        print("\n" + "-" * 50)
        print(" [3] LISTADO DE USUARIOS (PROTEGIDO)")
        print("-" * 50)

        if not self.usuario_actual:
            print("[BLOQUEADO] Acceso no autorizado. Debe iniciar sesión primero (Opción 2).")
            return

        params = {
            "auth_usuario": self.usuario_actual,
            "auth_contrasena": self.contrasena_actual
        }
        resp = self.enviar_peticion("listar_usuarios", params)
        if resp:
            worker = resp.get("worker", "Desconocido")
            t_ms = resp.get("tiempo_ms", 0)
            if resp.get("status") == "success":
                usuarios = resp.get("usuarios", [])
                print(f"\n[ÉXITO 200] Total registrados: {resp.get('total_usuarios')} (Atendido por {worker} en {t_ms} ms)")
                print(f"{'ID':<6} {'USUARIO':<20} {'FECHA DE REGISTRO'}")
                print("-" * 50)
                for u in usuarios:
                    print(f"#{u['id']:<5} {u['usuario']:<20} {u['fecha_registro']}")
            else:
                print(f"\n[ERROR {resp.get('codigo')}] {resp.get('mensaje')}")

    def subir_archivo(self):
        print("\n" + "-" * 50)
        print(" [4] SUBIR ARCHIVO / AVATAR (ALMACENAMIENTO DISTRIBUIDO S3 + BD)")
        print("-" * 50)

        if not self.usuario_actual:
            print("[BLOQUEADO] Debe iniciar sesión primero para subir archivos.")
            return

        nombre = input("Nombre de archivo (ej: avatar.png, cv.pdf): ").strip()
        if not nombre:
            nombre = f"avatar_{self.usuario_actual}.png"
        contenido = input("Descripción o contenido del archivo: ").strip()
        if not contenido:
            contenido = f"Foto de perfil del usuario {self.usuario_actual}"

        params = {
            "auth_usuario": self.usuario_actual,
            "nombre": nombre,
            "contenido": contenido
        }
        resp = self.enviar_peticion("subir_archivo", params)
        if resp:
            worker = resp.get("worker", "Desconocido")
            t_ms = resp.get("tiempo_ms", 0)
            if resp.get("status") == "success":
                s3 = resp.get("s3", {})
                print(f"\n[ÉXITO 201] {resp.get('mensaje')}")
                print(f" -> Registro BD: #{s3.get('registro_id')} | URI S3: {s3.get('s3_uri')}")
                print(f" -> Tamaño: {s3.get('bytes')} bytes | Procesado por: {worker} en {t_ms} ms.")
            else:
                print(f"\n[ERROR] {resp.get('mensaje')}")

    def menu(self):
        while True:
            estado_sesion = f"Sesión activa: [{self.usuario_actual}]" if self.usuario_actual else "Sin sesión"
            print("\n" + "=" * 55)
            print(f"   PANEL DE USUARIOS DISTRIBUIDO - {estado_sesion}")
            print("=" * 55)
            print(" 1. Registrar nuevo usuario")
            print(" 2. Iniciar sesión (Login)")
            print(" 3. Listar usuarios (Requiere sesión iniciada)")
            print(" 4. Subir archivo / avatar (PostgreSQL + S3)")
            print(" 5. Salir (o escribe 'éxito')")
            print("=" * 55)

            op = input("Selecciona una opción (1-5) > ").strip().lower()
            if op in ["5", "éxito", "exito", "salir"]:
                print("\n[INFO] Desconectando del servidor...")
                try:
                    self.socket.sendall("éxito".encode("utf-8"))
                except Exception:
                    pass
                break
            elif op == "1":
                self.registrar_usuario()
            elif op == "2":
                self.iniciar_sesion()
            elif op == "3":
                self.listar_usuarios()
            elif op == "4":
                self.subir_archivo()
            else:
                print("[!] Opción inválida.")

        if self.socket:
            self.socket.close()
            print("[INFO] Socket cliente cerrado correctamente.")

def main():
    print("=" * 60)
    print("   CLIENTE TCP DISTRIBUIDO (PFO 3 - IFTS N° 29)")
    print("   Alumno: Rodrigo Berger")
    print("=" * 60)
    cliente = ClienteDistribuido()
    if cliente.conectar():
        cliente.menu()

if __name__ == "__main__":
    main()
