from flask import Flask, render_template, request, redirect, session
from werkzeug.utils import secure_filename
import json
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

app.secret_key = "42731440"
ADMIN_USER = "admin"
ADMIN_PASS = "1234"

ARCHIVO = os.path.join(BASE_DIR, "productos.json")
UPLOADS = os.path.join(BASE_DIR, "static", "uploads")

# crear carpeta uploads si no existe
os.makedirs(UPLOADS, exist_ok=True)

def cargar_productos():
    if not os.path.exists(ARCHIVO):
        return []
    with open(ARCHIVO, "r", encoding="utf-8") as f:
        return json.load(f)

def guardar_productos(productos):
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(productos, f, indent=4, ensure_ascii=False)

@app.context_processor
def carrito_contador():
    carrito = session.get("carrito", [])
    total_items = sum(item["cantidad"] for item in carrito)
    return dict(carrito_total=total_items)
CATEGORIAS = ["Cocina", "Baño", "Decoración", "Limpieza"]


@app.route("/")
def tienda():
    productos = cargar_productos()
    q = request.args.get("q")
    categoria = request.args.get("categoria")

    if q:
        q = q.lower()
        productos = [
            p for p in productos
            if q in p["nombre"].lower()
        ]

    if categoria:
        productos = [
            p for p in productos
            if p.get("categoria") == categoria
        ]

    return render_template(
        "tienda.html",
        productos=productos,
        categorias=CATEGORIAS,
        categoria_seleccionada=categoria
    )


@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/login")

    productos = cargar_productos()
    categorias = ["Cocina", "Baño", "Decoración", "Limpieza"]

    return render_template(
        "admin.html",
        productos=productos,
        categorias=categorias
    )

@app.route("/agregar", methods=["POST"])
def agregar():
    productos = cargar_productos()

    imagen = request.files.get("imagen")
    nombre_imagen = ""

    if imagen and imagen.filename != "":
        nombre_imagen = secure_filename(imagen.filename)
        imagen.save(os.path.join(UPLOADS, nombre_imagen))

    nuevo = {
    "id": productos[-1]["id"] + 1 if productos else 1,
    "nombre": request.form["nombre"],
    "precio": int(request.form["precio"]),
    "stock": int(request.form["stock"]),
    "categoria": request.form["categoria"],
    "imagen": nombre_imagen
}

    productos.append(nuevo)
    guardar_productos(productos)
    return redirect("/admin")

@app.route("/editar/<int:id>", methods=["POST"])
def editar(id):
    productos = cargar_productos()

    for p in productos:
        if p["id"] == id:
            p["nombre"] = request.form["nombre"]
            p["precio"] = int(request.form["precio"])
            p["stock"] = int(request.form["stock"])
            p["categoria"] = request.form["categoria"]
            p["codigo"] = request.form["codigo"]

            imagen = request.files.get("imagen")
            if imagen and imagen.filename != "":
                nombre = secure_filename(imagen.filename)
                imagen.save(os.path.join(UPLOADS, nombre))
                p["imagen"] = nombre

    guardar_productos(productos)
    return redirect("/admin")

@app.route("/eliminar/<int:id>")
def eliminar(id):
    productos = cargar_productos()
    productos = [p for p in productos if p["id"] != id]
    guardar_productos(productos)
    return redirect("/admin")

@app.route("/stock_mas/<int:id>")
def stock_mas(id):
    productos = cargar_productos()

    for p in productos:
        if p["id"] == id:
            p["stock"] += 1

    guardar_productos(productos)
    return redirect("/admin")


@app.route("/stock_menos/<int:id>")
def stock_menos(id):
    productos = cargar_productos()

    for p in productos:
        if p["id"] == id and p["stock"] > 0:
            p["stock"] -= 1

    guardar_productos(productos)
    return redirect("/admin")
#### ENTRAR AL USUARIO Y SALIR ############
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
            session["admin"] = True
            return redirect("/admin")
    else:
            return render_template("login.html", error="Datos incorrectos")

        

@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect("/login")
#########################################
#####AGREGAR AL CARRITO ,BORRAR ARTICULO O VACIAR CARRITO #####
@app.route("/agregar_carrito/<int:id>")
def agregar_carrito(id):
    carrito = session.get("carrito", [])

    productos = cargar_productos()
    producto = next((p for p in productos if p["id"] == id), None)

    if not producto:
        return redirect("/")

    for item in carrito:
        if item["id"] == id:
            item["cantidad"] += 1
            break
    else:
        carrito.append({
        "id": producto["id"],
        "codigo": producto["codigo"],
        "nombre": producto["nombre"],
        "precio": producto["precio"],
        "imagen": producto.get("imagen", ""),
        "cantidad": 1
        })

    session["carrito"] = carrito
    return redirect("/carrito")

@app.route("/carrito")
def carrito():
    carrito = session.get("carrito", [])
    total = sum(item["precio"] * item["cantidad"] for item in carrito)

    return render_template(
        "carrito.html",
        carrito=carrito,
        total=total
    )



@app.route("/carrito/eliminar/<int:id>")
def eliminar_del_carrito(id):
    carrito = session.get("carrito", [])

    carrito = [item for item in carrito if item["id"] != id]

    session["carrito"] = carrito
    return redirect("/carrito")


@app.route("/carrito/vaciar")
def vaciar_carrito():
    session["carrito"] = []
    return redirect("/")


    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)