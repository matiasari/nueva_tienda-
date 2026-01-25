from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import timedelta
from werkzeug.utils import secure_filename
from functools import wraps
import json
import os
import urllib.parse

# =====================
# CONFIGURACIÓN GENERAL
# =====================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.secret_key = "1124023140aA@"

ADMIN_USER = "mariasotelo"
ADMIN_PASS = "241289maria@"

ARCHIVO = os.path.join(BASE_DIR, "productos.json")
UPLOADS = os.path.join(BASE_DIR, "static", "uploads")

os.makedirs(UPLOADS, exist_ok=True)

CATEGORIAS = ["Cocina", "Baño", "Decoración", "Limpieza"]

# =====================
# FUNCIONES AUXILIARES
# =====================

def cargar_productos():
    if not os.path.exists(ARCHIVO):
        return []
    with open(ARCHIVO, "r", encoding="utf-8") as f:
        return json.load(f)

def guardar_productos(productos):
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(productos, f, indent=4, ensure_ascii=False)

def zona_por_cp(cp):
    try:
        cp = int(cp)
        if 1000 <= cp <= 1499: return "CABA"
        elif 1500 <= cp <= 1999: return "AMBA"
        elif 2000 <= cp <= 2999: return "CENTRO"
        else: return "INTERIOR"
    except:
        return "INTERIOR"

def costo_envio_por_peso(peso):
    if peso <= 1: return 15500
    elif peso <= 5: return 18300
    elif peso <= 10: return 24500
    elif peso <= 15: return 30300
    elif peso <= 20: return 35700
    elif peso <= 25: return 42900
    else: return 42900 + int((peso - 25) * 2000)

# =====================
# DECORADORES
# =====================

def login_requerido(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorador

@app.context_processor
def carrito_contador():
    carrito = session.get("carrito", [])
    total_items = sum(item.get("cantidad", 0) for item in carrito)
    return dict(carrito_total=total_items)

# =====================
# RUTAS PÚBLICAS
# =====================

@app.route("/")
def tienda():
    productos = cargar_productos()
    q = request.args.get("q")
    categoria = request.args.get("categoria")

    if q:
        q = q.lower()
        productos = [p for p in productos if q in p["nombre"].lower()]

    if categoria:
        productos = [p for p in productos if p.get("categoria") == categoria]

    return render_template(
        "tienda.html",
        productos=productos,
        categorias=CATEGORIAS,
        categoria_seleccionada=categoria
    )

# =====================
# LOGIN / LOGOUT
# =====================

@app.route("/login", methods=["GET", "POST"])
def login():
    app.permanent_session_lifetime = timedelta(minutes=30)
    if request.method == "POST":
        user = request.form.get("usuario")
        password = request.form.get("password")
        if user == ADMIN_USER and password == ADMIN_PASS:
            session.clear()
            session["admin"] = True
            session.permanent = True
            return redirect(url_for("admin"))
        return render_template("login.html", error="Usuario o contraseña incorrectos")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("login"))

# =====================
# PANEL ADMIN
# =====================

@app.route("/admin")
@login_requerido
def admin():
    productos = cargar_productos()
    return render_template("admin.html", productos=productos, categorias=CATEGORIAS)

@app.route("/agregar", methods=["POST"])
@login_requerido
def agregar():
    productos = cargar_productos()
    imagen = request.files.get("imagen")
    nombre_imagen = ""
    if imagen and imagen.filename:
        nombre_imagen = secure_filename(imagen.filename)
        imagen.save(os.path.join(UPLOADS, nombre_imagen))

    nuevo = {
        "id": productos[-1]["id"] + 1 if productos else 1,
        "nombre": request.form["nombre"],
        "precio": int(request.form["precio"]),
        "stock": int(request.form["stock"]),
        "codigo": request.form["codigo"],
        "categoria": request.form["categoria"],
        "peso": float(request.form["peso"]),
        "imagen": nombre_imagen
    }
    productos.append(nuevo)
    guardar_productos(productos)
    return redirect(url_for("admin"))

@app.route("/editar/<int:id>", methods=["POST"])
@login_requerido
def editar(id):
    productos = cargar_productos()
    for p in productos:
        if p["id"] == id:
            p.update({
                "nombre": request.form["nombre"],
                "precio": int(request.form["precio"]),
                "stock": int(request.form["stock"]),
                "codigo": request.form["codigo"],
                "categoria": request.form["categoria"],
                "peso": float(request.form["peso"])
            })
            imagen = request.files.get("imagen")
            if imagen and imagen.filename:
                nombre = secure_filename(imagen.filename)
                imagen.save(os.path.join(UPLOADS, nombre))
                p["imagen"] = nombre
    guardar_productos(productos)
    return redirect(url_for("admin"))

@app.route("/eliminar/<int:id>")
@login_requerido
def eliminar(id):
    productos = [p for p in cargar_productos() if p["id"] != id]
    guardar_productos(productos)
    return redirect(url_for("admin"))

# =====================
# CARRITO
# =====================

@app.route("/agregar_carrito/<int:id>")
def agregar_carrito(id):
    carrito = session.get("carrito", [])
    productos = cargar_productos()
    producto = next((p for p in productos if p["id"] == id), None)

    if not producto:
        return redirect(url_for("tienda"))

    # Validación de stock al agregar
    for item in carrito:
        if item["id"] == id:
            if item["cantidad"] < int(producto.get("stock", 0)):
                item["cantidad"] += 1
            else:
                flash("Stock máximo alcanzado para este producto", "warning")
            break
    else:
        if int(producto.get("stock", 0)) > 0:
            carrito.append({
                "id": producto["id"],
                "codigo": producto["codigo"],
                "nombre": producto["nombre"],
                "precio": producto["precio"],
                "peso": producto.get("peso", 0),
                "imagen": producto.get("imagen", ""),
                "cantidad": 1
            })
        else:
            flash("Producto sin stock disponible", "danger")

    session["carrito"] = carrito
    return redirect(url_for("carrito"))

@app.route('/carrito')
def carrito():
    carrito = session.get("carrito", [])
    total = sum(float(i.get("precio", 0)) * int(i.get("cantidad", 1)) for i in carrito)
    peso_total = sum(float(i.get("peso", 0)) * int(i.get("cantidad", 1)) for i in carrito)
    envio = session.get("envio", 0)

    mensaje = "*Pedido Bazar Guille*\n\n"
    for i in carrito:
        mensaje += f"• {i['nombre']} x{i['cantidad']} - ${i['precio'] * i['cantidad']}\n"
    
    if envio > 0:
        mensaje += f"\nSubtotal: ${total}\nEnvío: ${envio}\n*TOTAL: ${total + envio}*"
    else:
        mensaje += f"\n*TOTAL: ${total}*\n(Envío a convenir)"

    link_whatsapp = f"https://wa.me/5491149899616?text={urllib.parse.quote(mensaje)}"

    return render_template('carrito.html', carrito=carrito, total=total, peso_total=peso_total, link_whatsapp=link_whatsapp)

@app.route('/aumentar/<int:producto_id>')
def aumentar(producto_id):
    carrito = session.get("carrito", [])
    productos_db = cargar_productos() 
    p_db = next((p for p in productos_db if p["id"] == producto_id), None)
    
    for item in carrito:
        if item["id"] == producto_id:
            if p_db and item["cantidad"] < int(p_db.get("stock", 0)):
                item["cantidad"] += 1
            else:
                flash(f"No hay más stock disponible", "warning")
            break
            
    session["carrito"] = carrito
    session.modified = True
    return redirect(url_for('carrito'))

@app.route('/disminuir/<int:producto_id>')
def disminuir(producto_id):
    carrito = session.get("carrito", [])
    for item in carrito:
        if item["id"] == producto_id:
            if item["cantidad"] > 1:
                item["cantidad"] -= 1
            else:
                return redirect(url_for('eliminar_del_carrito', id=producto_id))
            break
    session["carrito"] = carrito
    session.modified = True
    return redirect(url_for('carrito'))

@app.route("/carrito/eliminar/<int:id>")
def eliminar_del_carrito(id):
    session["carrito"] = [i for i in session.get("carrito", []) if i["id"] != id]
    return redirect(url_for("carrito"))

@app.route("/carrito/vaciar")
def vaciar_carrito():
    session["carrito"] = []
    session.pop("envio", None)
    return redirect(url_for("tienda"))

# =====================
# ENVÍO
# =====================

@app.route("/calcular_envio", methods=["POST"])
def calcular_envio():
    cp = request.form.get("cp")
    if not cp: return redirect(url_for("carrito"))
    
    zona = zona_por_cp(cp)
    carrito = session.get("carrito", [])
    peso_total = sum(float(i.get("peso", 0)) * int(i.get("cantidad", 1)) for i in carrito)
    
    envio = costo_envio_por_peso(peso_total)
    session["envio"] = envio
    session["zona_envio"] = zona
    return redirect(url_for("carrito"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)