from flask import Flask, render_template, request, redirect, session, url_for
from datetime import timedelta
from werkzeug.utils import secure_filename
from functools import wraps
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = "1124023140aA@"  # Cambiá esto por algo más seguro luego
app.permanent_session_lifetime = timedelta(days=7)

# --- CONFIGURACIÓN DE CREDENCIALES ---
# Intentamos obtenerlas de las variables de entorno (para Render)
# Si no existen, usamos los valores por defecto (para tu PC local)
ADMIN_USER = os.environ.get("ADMIN_USER", "mariasotelo")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "241289maria@")

# Esto es muy útil para saber si Render las tomó bien:
if os.environ.get("ADMIN_USER"):
    print("Corriendo con variables de entorno de producción")

# Rutas de archivos
ARCHIVO = os.path.join(BASE_DIR, "productos.json")
ARCHIVO_BANNER = os.path.join(BASE_DIR, "banner.json")
UPLOADS = os.path.join(BASE_DIR, "static", "uploads")

os.makedirs(UPLOADS, exist_ok=True)

# --- DECORADOR DE SEGURIDAD ---
def login_requerido(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorador

# --- FUNCIONES DE PERSISTENCIA (JSON) ---
def cargar_productos():
    if not os.path.exists(ARCHIVO): return []
    with open(ARCHIVO, "r", encoding="utf-8") as f: return json.load(f)

def guardar_productos(productos):
    with open(ARCHIVO, "w", encoding="utf-8") as f: 
        json.dump(productos, f, indent=4, ensure_ascii=False)

def cargar_banner():
    if not os.path.exists(ARCHIVO_BANNER): return []
    with open(ARCHIVO_BANNER, "r", encoding="utf-8") as f: return json.load(f)

def guardar_banner(banner):
    with open(ARCHIVO_BANNER, "w", encoding="utf-8") as f: 
        json.dump(banner, f, indent=4, ensure_ascii=False)

# --- RUTAS PÚBLICAS (TIENDA) ---

@app.route("/")
def index():
    categoria = request.args.get("categoria")
    busqueda = request.args.get("q", "").lower()
    productos = cargar_productos()
    banner = cargar_banner()

    if categoria:
        productos = [p for p in productos if p.get("categoria") == categoria]
    if busqueda:
        productos = [p for p in productos if busqueda in p["nombre"].lower() or busqueda in p.get("codigo", "").lower()]

    # Cálculo del total de items en el carrito para el contador
    carrito = session.get("carrito", [])
    total_items = sum(item["cantidad"] for item in carrito)
    
    return render_template("tienda.html", productos=productos, carrito_total=total_items, banner=banner)

@app.route("/agregar_carrito/<int:id>")
def agregar_carrito(id):
    if "carrito" not in session:
        session["carrito"] = []
    
    carrito = session["carrito"]
    encontrado = False
    for item in carrito:
        if item["id"] == id:
            item["cantidad"] += 1
            encontrado = True
            break
    
    if not encontrado:
        carrito.append({"id": id, "cantidad": 1})
    
    session["carrito"] = carrito
    session.modified = True
    return redirect(url_for("index"))

@app.route("/carrito")
def ver_carrito():
    productos_db = cargar_productos()
    carrito_session = session.get("carrito", [])
    productos_carrito = []
    total = 0

    for item in carrito_session:
        producto = next((p for p in productos_db if p["id"] == item["id"]), None)
        if producto:
            subtotal = producto["precio"] * item["cantidad"]
            total += subtotal
            productos_carrito.append({
                "id": producto["id"],
                "nombre": producto["nombre"],
                "precio": producto["precio"],
                "cantidad": item["cantidad"],
                "imagen": producto.get("imagen"),
                "subtotal": subtotal
            })
    
    return render_template("carrito.html", productos=productos_carrito, total=total)

# --- RUTAS DE ADMINISTRACIÓN ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("usuario") == ADMIN_USER and request.form.get("password") == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin"))
        return render_template("login.html", error="Credenciales incorrectas")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("index"))

@app.route("/admin")
@login_requerido
def admin():
    productos = cargar_productos()
    banner = cargar_banner()
    categorias = ["Cocina", "Baño", "Decoración", "Limpieza"]
    return render_template("admin.html", productos=productos, categorias=categorias, banner=banner)

@app.route("/admin/banner/agregar", methods=["POST"])
@login_requerido
def agregar_banner():
    banner = cargar_banner()
    titulo = request.form.get("titulo")
    subtitulo = request.form.get("subtitulo")
    imagen = request.files.get("imagen")
    
    nombre_img = ""
    if imagen and imagen.filename != "":
        nombre_img = secure_filename(imagen.filename)
        imagen.save(os.path.join(UPLOADS, nombre_img))
    
    # Genera un ID aleatorio para el slide del banner
    import random
    nuevo_slide = {
        "id": random.randint(1000, 9999),
        "titulo": titulo,
        "subtitulo": subtitulo,
        "imagen": nombre_img
    }
    banner.append(nuevo_slide)
    guardar_banner(banner)
    return redirect(url_for("admin"))

@app.route("/admin/banner/eliminar/<int:id>")
@login_requerido
def eliminar_banner(id):
    banner = cargar_banner()
    banner = [b for b in banner if b["id"] != id]
    guardar_banner(banner)
    return redirect(url_for("admin"))

@app.route("/admin/producto/agregar", methods=["POST"])
@login_requerido
def agregar_producto():
    productos = cargar_productos()
    nombre = request.form.get("nombre")
    precio = float(request.form.get("precio"))
    categoria = request.form.get("categoria")
    stock = int(request.form.get("stock"))
    imagen = request.files.get("imagen")
    
    nombre_img = ""
    if imagen and imagen.filename != "":
        nombre_img = secure_filename(imagen.filename)
        imagen.save(os.path.join(UPLOADS, nombre_img))
    
    nuevo_p = {
        "id": int(os.urandom(2).hex(), 16),
        "nombre": nombre,
        "precio": precio,
        "categoria": categoria,
        "stock": stock,
        "imagen": nombre_img
    }
    
    productos.append(nuevo_p)
    guardar_productos(productos)
    return redirect(url_for("admin"))

@app.route("/admin/producto/eliminar/<int:id>")
@login_requerido
def eliminar_producto(id):
    productos = cargar_productos()
    productos = [p for p in productos if p["id"] != id]
    guardar_productos(productos)
    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(debug=True)