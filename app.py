import os
import json
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy 
from werkzeug.utils import secure_filename
from functools import wraps
import io
import requests
from datetime import datetime

app = Flask(__name__)

# --- CONFIGURACIÓN ---
app.secret_key = 'bazar_guille_key_secret_2026'
app.config['SESSION_COOKIE_NAME'] = 'bazar_guille_session'
app.config['SESSION_PERMANENT'] = True
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# 🔴 CONFIGURACIÓN DE POSTGRESQL EN RENDER
URL_RENDER = "postgresql://guille_admin:7nHE9WVezwoXS0RsDUiMrNkogSSX3FAW@dpg-d8sjeme7r5hc73fjftrg-a.oregon-postgres.render.com/bazarguille_db"
app.config['SQLALCHEMY_DATABASE_URI'] = URL_RENDER
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

API_KEY_SINCRO = "Guille_Linux_Sincro_2026"
IMGBBB_API_KEY = "65c21c6edd31fca5dd8d37e1ff870739"

# --- FILTROS JINJA Y FUNCIONES AUXILIARES ---
@app.template_filter('pesos')
def formato_pesos(valor):
    try: return f"${int(float(valor)):,}".replace(",", ".")
    except: return "$0"

# --- MODELOS DE LA BASE DE DATOS (POSTGRESQL PERMANENTE) ---

class Articulo(db.Model):
    __tablename__ = 'articulos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(250), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    categoria = db.Column(db.String(100), nullable=True)
    subcategoria = db.Column(db.String(100), nullable=True, default="")
    stock = db.Column(db.Integer, default=0)
    imagen = db.Column(db.String(500), nullable=True)
    imagenes_extras = db.Column(db.Text, nullable=True, default="") 

    def to_dict(self):
        img_ex = self.imagenes_extras.split(',') if self.imagenes_extras else []
        return {
            "id": self.id,
            "nombre": self.nombre,
            "precio": self.precio,
            "categoria": self.categoria if self.categoria else "VARIOS",
            "subcategoria": self.subcategoria if self.subcategoria else "",
            "stock": self.stock,
            "imagen": self.imagen if self.imagen else "default.jpg",
            "imagenes_extras": img_ex
        }

class Banner(db.Model):
    __tablename__ = 'banners'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(250), nullable=True)
    descripcion = db.Column(db.String(500), nullable=True)
    imagen = db.Column(db.String(500), nullable=False)
    link = db.Column(db.String(250), nullable=True)

    def to_dict(self):
        return {"id": self.id, "titulo": self.titulo, "descripcion": self.descripcion, "imagen": self.imagen, "link": self.link}

class Categoria(db.Model):
    __tablename__ = 'categorias'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    subcategorias_text = db.Column(db.Text, default="") 

    def to_dict(self):
        subs = [s.strip() for s in self.subcategorias_text.split(',') if s.strip()] if self.subcategorias_text else []
        return {"nombre": self.nombre, "subcategorias": subs}

class Pedido(db.Model):
    __tablename__ = 'pedidos'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
    total = db.Column(db.Float, nullable=False)
    envio = db.Column(db.Float, default=0.0)
    zona = db.Column(db.String(100), default="Retiro en local")
    estado = db.Column(db.String(50), default="PENDIENTE") 
    detalles = db.relationship('DetallePedido', backref='pedido', lazy=True, cascade="all, delete-orphan")

class DetallePedido(db.Model):
    __tablename__ = 'detalles_pedido'
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id'), nullable=False)
    articulo_id = db.Column(db.Integer, nullable=False)
    nombre = db.Column(db.String(250), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    cantidad = db.Column(db.Integer, nullable=False) 
    imagen = db.Column(db.String(500), nullable=True)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- INICIALIZACIÓN Y MIGRACIÓN AUTOMÁTICA ---
with app.app_context():
    db.create_all()
    if Categoria.query.count() == 0:
        categorias_json = [
            {"nombre": "COCINA", "subcategorias": ["MATES", "TAZAS", "CUBIERTOS", "UTILITARIOS", "VASOS"]},
            {"nombre": "ELECTRONICA", "subcategorias": ["PARLANTES", "SMARTWACH", "PAVAS", "AURICULARES"]},
            {"nombre": "VUELTA AL COLE", "subcategorias": ["MOCHILAS"]},
            {"nombre": "EQUIPAJE", "subcategorias": ["MOCHILAS"]},
            {"nombre": "PORCELANA", "subcategorias": ["TAZAS", "SET DE VAJILLA"]},
            {"nombre": "VIDRIO", "subcategorias": ["TAZAS DOBLE FONDO", "VASOS", "BOTELLA/JARRAS/DISPENSER"]},
            {"nombre": "DECORACION", "subcategorias": ["PORTAVELAS", "CUADROS"]},
            {"nombre": "ILUMINACION", "subcategorias": ["LAMPARAS", "LINTERNAS"]},
            {"nombre": "BAÑO", "subcategorias": ["DISPENSER", "PORTAROLLOS", "SET DE BAÑO", "ACCESORIOS"]},
            {"nombre": "PETIT MUEBLES", "subcategorias": []}
        ]
        for cat_data in categorias_json:
            subs_str = ",".join(cat_data["subcategorias"])
            nueva_cat = Categoria(nombre=cat_data["nombre"], subcategorias_text=subs_str)
            db.session.add(nueva_cat)
        db.session.commit()

# --- SEGURIDAD ---
def login_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logueado'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- RUTAS PÚBLICAS ---
@app.route('/')
def index():
    articulos_db = Articulo.query.all()
    productos = [a.to_dict() for a in articulos_db]
    banners = [b.to_dict() for b in Banner.query.all()]
    categorias = [c.to_dict() for c in Categoria.query.all()]
    
    cat = request.args.get('cat')
    q = request.args.get('q')
    prod_mostrar = productos
    if cat and cat != "Todos":
        prod_mostrar = [p for p in prod_mostrar if p.get('categoria') == cat or p.get('subcategoria') == cat]
    if q:
        q_l = q.lower()
        prod_mostrar = [p for p in prod_mostrar if q_l in p.get('nombre', '').lower() or str(p.get('id')) == q_l]
        
    # 🔴 FIX: Se pasan tanto 'categorias' como 'categories' para evitar error 500 en tienda.html
    return render_template('tienda.html', productos=prod_mostrar, banners=banners, carrito_total=len(session.get('carrito', [])), categorias=categorias, categories=categorias)

# --- ADMINISTRACIÓN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('usuario') == 'admin' and request.form.get('password') == 'guille123':
            session.clear()
            session['admin_logueado'] = True
            session.permanent = True
            return redirect(url_for('admin'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin')
@login_requerido
def admin():
    productos = [a.to_dict() for a in Articulo.query.order_by(Articulo.id.desc()).all()]
    banners = [b.to_dict() for b in Banner.query.all()]
    categorias = [c.to_dict() for c in Categoria.query.all()]
    pedidos = Pedido.query.order_by(Pedido.id.desc()).all()
    return render_template('admin.html', productos=productos, banners=banners, categorias=categorias, pedidos=pedidos)

# --- PROCESAR PEDIDO Y ENVIAR WHATSAPP ---
@app.route('/finalizar_pedido', methods=['POST'])
def finalizar_pedido():
    ids = session.get('carrito', [])
    if not ids:
        return redirect(url_for('index'))
    
    articulos_db = Articulo.query.all()
    todos = [a.to_dict() for a in articulos_db]
    
    items = []
    total = 0
    for p_id in set(ids):
        p = next((prod for prod in todos if str(prod['id']) == p_id), None)
        if p:
            cant = ids.count(p_id)
            total += p['precio'] * cant
            it = p.copy()
            it['cantidad'] = cant
            items.append(it)
            
    envio = session.get('envio', 0)
    zona = session.get('zona', 'Retiro en local')
    total_final = total + envio

    # Guardar Pedido principal
    nuevo_pedido = Pedido(total=total_final, envio=envio, zona=zona, estado="PENDIENTE")
    db.session.add(nuevo_pedido)
    db.session.commit()

    # Guardar detalles del pedido
    for i in items:
        detalle = DetallePedido(
            pedido_id=nuevo_pedido.id,
            articulo_id=i['id'],
            nombre=i['nombre'],
            precio=i['precio'],
            cantidad=i['cantidad'],
            imagen=i['imagen']
        )
        db.session.add(detalle)
    db.session.commit()

    # Armamos el mensaje para WhatsApp
    msj = f"Hola Bazar Guille! Pedido #{nuevo_pedido.id}\n"
    msj += f"Metodo: {zona}\n--------------------\n"
    for i in items:
        msj += f"- {i['nombre']} x{i['cantidad']} ({formato_pesos(i['precio'] * i['cantidad'])})\n"
    if envio > 0:
        msj += f"Envio: {formato_pesos(envio)}\n"
    msj += f"--------------------\nTotal Final: {formato_pesos(total_final)}"
    
    # Vaciamos el carrito del cliente
    session['carrito'] = []
    session['envio'] = 0
    session['zona'] = 'No seleccionada'
    
    link_wa = f"https://wa.me/5491149899616?text={requests.utils.quote(msj)}"
    return redirect(link_wa)

# --- ACCIONES DE PEDIDOS (CAMBIO DE ESTADO Y STOCK) ---
@app.route('/admin/pedido/hecho/<int:id>')
@login_requerido
def pedido_hecho(id):
    pedido = Pedido.query.get(id)
    if pedido and pedido.estado == "PENDIENTE":
        for detalle in pedido.detalles:
            articulo = Articulo.query.get(detalle.articulo_id)
            if articulo:
                articulo.stock = max(0, articulo.stock - detalle.cantidad)
        pedido.estado = "HECHO"
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/pedido/cancelar/<int:id>')
@login_requerido
def pedido_cancelar(id):
    pedido = Pedido.query.get(id)
    if pedido and pedido.estado == "PENDIENTE":
        pedido.estado = "CANCELADO"
        db.session.commit()
    return redirect(url_for('admin'))

# --- CONFIGURACIÓN DE ABM ADICIONAL ---
@app.route('/admin/categorias/agregar', methods=['POST'])
@login_requerido
def agregar_categoria():
    nueva = request.form.get('nombre').strip().upper()
    if nueva:
        if not Categoria.query.filter_by(nombre=nueva).first():
            db.session.add(Categoria(nombre=nueva, subcategorias_text=""))
            db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/subcategorias/agregar', methods=['POST'])
@login_requerido
def agregar_subcategoria():
    padre = request.form.get('padre')
    nueva_sub = request.form.get('nombre_sub').strip().upper()
    cat = Categoria.query.filter_by(nombre=padre).first()
    if cat and nueva_sub:
        subs = [s.strip() for s in cat.subcategorias_text.split(',') if s.strip()] if cat.subcategorias_text else []
        if nueva_sub not in subs:
            subs.append(nueva_sub)
            cat.subcategorias_text = ",".join(subs)
            db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/categorias/eliminar/<nombre>')
@login_requerido
def eliminar_categoria(nombre):
    cat = Categoria.query.filter_by(nombre=nombre).first()
    if cat:
        db.session.delete(cat)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/subcategorias/eliminar/<padre>/<nombre_sub>')
@login_requerido
def eliminar_subcategoria(padre, nombre_sub):
    cat = Categoria.query.filter_by(nombre=padre).first()
    if cat:
        subs = [s.strip() for s in cat.subcategorias_text.split(',') if s.strip()] if cat.subcategorias_text else []
        if nombre_sub in subs:
            subs.remove(nombre_sub)
            cat.subcategorias_text = ",".join(subs)
            db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/producto/agregar', methods=['POST'])
@login_requerido
def agregar_producto():
    fotos = request.files.getlist('imagenes_extras')
    urls_subidas = []
    for img in fotos:
        if img and img.filename != '':
            img_bytes = img.read()
            payload = {"key": IMGBBB_API_KEY}
            files = {"image": (img.filename, img_bytes)}
            try:
                response = requests.post("https://api.imgbb.com/1/upload", data=payload, files=files)
                res_data = response.json()
                if res_data.get("success"): urls_subidas.append(res_data["data"]["url"])
            except Exception as e: print(f"Error al subir a ImgBB: {e}")
    max_id = db.session.query(db.func.max(Articulo.id)).scalar() or 0
    nuevo_id = max_id + 1
    img_extras_str = ",".join(urls_subidas[1:]) if len(urls_subidas) > 1 else ""
    imagen_portada = urls_subidas[0] if urls_subidas else "default.jpg"
    nuevo_articulo = Articulo(
        id=nuevo_id, nombre=request.form.get('nombre', '').upper(), precio=float(request.form.get('precio') or 0),
        categoria=request.form.get('categoria'), subcategoria=request.form.get('subcategoria'),
        stock=int(request.form.get('stock') or 0), imagen=imagen_portada, imagenes_extras=img_extras_str
    )
    db.session.add(nuevo_articulo)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/producto/editar', methods=['POST'])
@login_requerido
def editar_producto():
    p_id = int(request.form.get('id'))
    articulo = Articulo.query.get(p_id)
    if articulo:
        articulo.nombre = request.form.get('nombre', '').upper()
        articulo.precio = float(request.form.get('precio') or 0)
        articulo.categoria = request.form.get('categoria')
        articulo.subcategoria = request.form.get('subcategoria')
        articulo.stock = int(request.form.get('stock') or 0)
        orden = request.form.getlist('orden_fotos[]')
        nuevas = request.files.getlist('fotos_extras')
        for f in nuevas:
            if f.filename != '':
                img_bytes = f.read()
                payload = {"key": IMGBBB_API_KEY}
                files = {"image": (f.filename, img_bytes)}
                try:
                    response = requests.post("https://api.imgbb.com/1/upload", data=payload, files=files)
                    res_data = response.json()
                    if res_data.get("success"): orden.append(res_data["data"]["url"])
                except Exception as e: print(f"Error en edicion ImgBB: {e}")
        if orden:
            articulo.imagen = orden[0]
            articulo.imagenes_extras = ",".join(orden[1:]) if len(orden) > 1 else ""
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/producto/eliminar/<int:id>')
@login_requerido
def eliminar_producto(id):
    articulo = Articulo.query.get(id)
    if articulo:
        db.session.delete(articulo)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/importar_excel', methods=['POST'])
@login_requerido
def importar_excel():
    file = request.files.get('archivo_excel')
    if file and file.filename != '':
        df = pd.read_excel(file)
        max_id = db.session.query(db.func.max(Articulo.id)).scalar() or 0
        nuevo_id = max_id + 1
        for _, row in df.iterrows():
            cat_val = str(row['Categoría']).upper() if pd.notna(row['Categoría']) else 'VARIOS'
            sub_val = str(row.get('Subcategoría', '')).upper() if pd.notna(row.get('Subcategoría', '')) else ''
            nuevo_art = Articulo(
                id=nuevo_id, nombre=str(row['Nombre']).upper() if pd.notna(row['Nombre']) else 'SIN NOMBRE', precio=float(row['Precio'] or 0),
                categoria=cat_val, subcategoria=sub_val,
                stock=int(row.get('Stock', 0) if pd.notna(row.get('Stock')) else 0), imagen="default.jpg", imagenes_extras=""
            )
            db.session.add(nuevo_art)
            nuevo_id += 1
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/descargar_plantilla')
@login_requerido
def descargar_plantilla():
    df = pd.DataFrame(columns=['Nombre', 'Precio', 'Categoría', 'Subcategoría', 'Stock'])
    df.loc[0] = ['EJEMPLO PRODUCTO', 5000.0, 'COCINA', 'MATES', 10]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='plantilla_bazar.xlsx')

@app.route('/agregar_al_carrito', methods=['POST'])
def agregar_al_carrito():
    carrito = session.get('carrito', [])
    carrito.append(str(request.form.get('id')))
    session['carrito'] = carrito
    session.modified = True
    return redirect(url_for('index'))

@app.route('/aumentar/<id>')
def aumentar_carrito(id):
    carrito = session.get('carrito', [])
    carrito.append(str(id))
    session['carrito'] = carrito
    session.modified = True
    return redirect(url_for('mostrar_carrito'))

@app.route('/disminuir/<id>')
def disminuir_carrito(id):
    carrito = session.get('carrito', [])
    if str(id) in carrito:
        carrito.remove(str(id))
    session['carrito'] = carrito
    session.modified = True
    return redirect(url_for('mostrar_carrito'))

@app.route('/carrito/eliminar/<id>')
def eliminar_carrito(id):
    carrito = session.get('carrito', [])
    session['carrito'] = [x for x in carrito if x != str(id)]
    session.modified = True
    return redirect(url_for('mostrar_carrito'))

@app.route('/carrito/vaciar')
def vaciar_carrito():
    session['carrito'] = []
    return redirect(url_for('mostrar_carrito'))

@app.route('/calcular_envio', methods=['POST'])
def calcular_envio():
    zona = request.form.get('zona')
    session['zona'] = zona
    costos = {"CABA": 10000, "Zona Norte": 15000, "Zona Sur": 7000, "Zona Oeste": 10000, "Retiro en local": 0}
    session['envio'] = costos.get(zona, 0)
    return redirect(url_for('mostrar_carrito'))

@app.route('/carrito')
def mostrar_carrito():
    ids = session.get('carrito', [])
    todos = [a.to_dict() for a in Articulo.query.all()]
    items = []
    total = 0
    for p_id in set(ids):
        p = next((prod for prod in todos if str(prod['id']) == p_id), None)
        if p:
            cant = ids.count(p_id)
            total += p['precio'] * cant
            it = p.copy(); it['cantidad'] = cant
            items.append(it)
    envio = session.get('envio', 0)
    zona = session.get('zona', 'No seleccionada')
    return render_template('carrito.html', carrito=items, total=total, envio=envio, zona=zona, total_final=total+envio)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)