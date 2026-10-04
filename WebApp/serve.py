"""Servidor de producción (Waitress). Lo inicia iniciar.bat."""
from waitress import serve

from app import app

if __name__ == "__main__":
    print("Sistema de Despliegues disponible en http://0.0.0.0:5000")
    serve(app, host="0.0.0.0", port=5000, threads=8)
