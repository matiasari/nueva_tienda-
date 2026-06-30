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
from sqlalchemy import text

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

BANNERS_JSON = 'banners.json'
API_KEY_SINCRO = "Guille_Linux_Sincro_2026"
IMGBBB_API_KEY = "65c21c6edd31fca5dd8d37e1ff870739"

# --- MODELOS DE LA BASE DE DATOS ---

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
    
    variantes = db.relationship('Variante', backref='articulo', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        img_ex = self.imagenes_extras.split(',') if self.imagenes_extras else []
        try:
            vars_list = [v.to_dict() for v in self.variantes]
        except:
            vars_list = [] # Tolerancia por si el deploy tarda en migrar
        return {
            "id": self.id,
            "nombre": self.nombre,
            "precio": self.precio,
            "categoria": self.categoria if self.categoria else "VARIOS",
            "subcategoria": self.subcategoria if self.subcategoria else "",
            "stock": self.stock,
            "imagen": self.imagen if self.imagen else "default.jpg",
            "imagenes_extras": img_ex,
            "variantes": vars_list
        }

class Variante(db.Model):
    __tablename__ = 'variantes'
    id = db.Column(db.Integer, primary_key=True)
    articulo_id = db.Column(db.Integer, db.ForeignKey('articulos.id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False) 
    stock = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {"id": self.id, "nombre": self.nombre, "stock": self.stock}

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
    variante_nombre = db.Column(db.String(100), nullable=True, default="") 
    precio = db.Column(db.Float, nullable=False)
    cantidad = db.Column(db.Integer, nullable=False) 
    imagen = db.Column(db.String(500), nullable=True)

def cargar_datos(archivo):
    if not os.path.exists(archivo): return []
    with open(archivo, 'r', encoding='utf-8') as f:
        try: return json.load(f)
        except: return []

def guardar_datos(archivo, datos):
    with open(archivo, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)

# ✨ MIGRACIÓN DE TABLAS SEGURA Y TOLERANTE A ERRORES
with app.app_context():
    db.create_all()
    try:
        # Inyecta la columna variante_nombre usando SQL nativo si no existía previamente
        db.session.execute(text("ALTER TABLE detalles_pedido ADD COLUMN IF NOT EXISTS variante_nombre VARCHAR(100) DEFAULT '';"))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Aviso en migración: {e}")

def login_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logueado'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.template_filter('pesos')
def formato_pesos(valor):
    try: return f"${int(float(valor)):,}".replace(",", ".")
    except: return "$0"

# --- RUTAS PÚBLICAS ---
@app.route('/')
def index():
    articulos_db = Articulo.query.all()
    productos = [a.to_dict() for a in articulos_db]
    banners = cargar_datos(BANNERS_JSON)
    categorias = [c.to_dict() for c in Categoria.query.order_by(Categoria.nombre.asc()).all()]
    
    cat = request.args.get('cat')
    q = request.args.get('q')
    
    prod_mostrar = productos
    if cat and cat != "Todos":
        prod_mostrar = [p for p in prod_mostrar if p.get('categoria') == cat or p.get('subcategoria') == cat]
    if q:
        q_l = q.lower()
        prod_mostrar = [p for p in prod_mostrar if q_l in p.get('nombre', '').lower() or str(p.get('id')) == q_l]
        
    return render_template('tienda.html', productos=prod_mostrar, banners=banners, carrito_total=len(session.get('carrito', [])), categorias=categorias, categories=categorias)

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

# --- VISTAS ADMINISTRATIVAS ---
@app.route('/admin')
@login_requerido
def admin():
    productos = [a.to_dict() for a in Articulo.query.order_by(Articulo.id.desc()).all()]
    categorias = [c.to_dict() for c in Categoria.query.order_by(Categoria.nombre.asc()).all()]
    return render_template('admin.html', productos=productos, banners=cargar_datos(BANNERS_JSON), categorias=categorias, categories=categorias)

@app.route('/admin/pedidos')
@login_requerido
def ver_pedidos_seccion():
    pedidos = Pedido.query.order_by(Pedido.id.desc()).all()
    return render_template('pedidos.html', pedidos=pedidos)

# --- ACCIONES PEDIDOS Y DESCUENTO DE STOCK ---
@app.route('/admin/pedido/hecho/<int:id>')
@login_requerido
def pedido_hecho(id):
    pedido = Pedido.query.get(id)
    if pedido and pedido.estado == "PENDIENTE":
        for d in pedido.detalles:
            articulo = Articulo.query.get(d.articulo_id)
            if articulo:
                if getattr(d, 'variante_nombre', None):
                    var = Variante.query.filter_by(articulo_id=articulo.id, nombre=d.variante_nombre).first()
                    if var:
                        var.stock = max(0, var.stock - d.cantidad)
                else:
                    articulo.stock = max(0, articulo.stock - d.cantidad)
        pedido.estado = "HECHO"
        db.session.commit()
    if request.args.get('from') == 'pedidos':
        return redirect(url_for('ver_pedidos_seccion'))
    return redirect(url_for('admin'))

@app.route('/admin/pedido/cancelar/<int:id>')
@login_requerido
def pedido_cancelar(id):
    pedido = Pedido.query.get(id)
    if pedido and pedido.estado == "PENDIENTE":
        pedido.estado = "CANCELADO"
        db.session.commit()
    if request.args.get('from') == 'pedidos':
        return redirect(url_for('ver_pedidos_seccion'))
    return redirect(url_for('admin'))

# --- ABM CATEGORÍAS ---
@app.route('/admin/categorias/agregar', methods=['POST'])
@login_requerido
def agregar_categoria():
    nueva = request.form.get('nombre').strip().upper()
    if nueva:
        existente = Categoria.query.filter_by(nombre=nueva).first()
        if not existente:
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

# --- ABM PRODUCTOS ---
@app.route('/admin/producto/agregar', methods=['POST'])
@login_requerido
def agregar_producto():
    fotos = request.files.getlist('imagenes_extras')
    urls_subidas = []
    for img in fotos:
        if img and img.filename != '':
            try:
                res = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBBB_API_KEY}, files={"image": (img.filename, img.read())})
                if res.json().get("success"): urls_subidas.append(res.json()["data"]["url"])
            except: pass
            
    max_id = db.session.query(db.func.max(Articulo.id)).scalar() or 0
    nuevo_id = max_id + 1
    
    nuevo_articulo = Articulo(
        id=nuevo_id, nombre=request.form.get('nombre', '').upper(), precio=float(request.form.get('precio') or 0),
        categoria=request.form.get('categoria'), subcategoria=request.form.get('subcategoria'),
        stock=int(request.form.get('stock') or 0), imagen=urls_subidas[0] if urls_subidas else "default.jpg",
        imagenes_extras=",".join(urls_subidas[1:]) if len(urls_subidas) > 1 else ""
    )
    db.session.add(nuevo_articulo)
    db.session.commit()
    
    variantes_raw = request.form.get('variantes_input', '')
    if variantes_raw:
        for v_item in variantes_raw.split(','):
            if ':' in v_item:
                v_nom, v_stk = v_item.split(':')
                nueva_v = Variante(articulo_id=nuevo_id, nombre=v_nom.strip().upper(), stock=int(v_stk.strip() or 0))
                db.session.add(nueva_v)
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
                try:
                    res = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBBB_API_KEY}, files={"image": (f.filename, f.read())})
                    if res.json().get("success"): orden.append(res.json()["data"]["url"])
                except: pass
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

# --- CARRITO Y PROCESAMIENTO ---
@app.route('/finalizar_pedido', methods=['POST'])
def finalizar_pedido():
    ids_raw = session.get('carrito', [])
    if not ids_raw: return redirect(url_for('index'))
    
    todos = [a.to_dict() for a in Articulo.query.all()]
    items = []
    total = 0
    
    for item_key in set(ids_raw):
        p_id = item_key.split(':')[0]
        v_nombre = item_key.split(':')[1] if ':' in item_key else ""
        
        p = next((prod for prod in todos if str(prod['id']) == p_id), None)
        if p:
            cant = ids_raw.count(item_key)
            total += p['precio'] * cant
            it = p.copy()
            it['cantidad'] = cant
            it['variante_elegida'] = v_nombre
            items.append(it)
            
    envio = session.get('envio', 0)
    zona = session.get('zona', 'Retiro en local')
    total_final = total + envio

    nuevo_pedido = Pedido(total=total_final, envio=envio, zona=zona, estado="PENDIENTE")
    db.session.add(nuevo_pedido)
    db.session.commit()

    for i in items:
        detalle = DetallePedido(
            pedido_id=nuevo_pedido.id, 
            articulo_id=i['id'], 
            nombre=i['nombre'], 
            variante_nombre=i['variante_elegida'],
            precio=i['precio'], 
            cantidad=i['cantidad'], 
            imagen=i['imagen']
        )
        db.session.add(detalle)
    db.session.commit()

    msj = f"Hola Bazar Guille! Pedido #{nuevo_pedido.id}\nMetodo: {zona}\n--------------------\n"
    for i in items: 
        var_txt = f" [{i['variante_elegida']}]" if i['variante_elegida'] else ""
        msj += f"- {i['nombre']}{var_txt} x{i['cantidad']} ({formato_pesos(i['precio'] * i['cantidad'])})\n"
    if envio > 0: msj += f"Envio: {formato_pesos(envio)}\n"
    msj += f"--------------------\nTotal Final: {formato_pesos(total_final)}"
    
    session['carrito'] = []
    session['envio'] = 0
    session['zona'] = 'No seleccionada'
    return redirect(f"https://wa.me/5491149899616?text={requests.utils.quote(msj)}")

@app.route('/agregar_al_carrito', methods=['POST'])
def agregar_al_carrito():
    carrito = session.get('carrito', [])
    art_id = request.form.get('id')
    var_nom = request.form.get('variante', '')
    
    item_key = f"{art_id}:{var_nom}" if var_nom else str(art_id)
    carrito.append(item_key)
    session['carrito'] = carrito
    session.modified = True
    return redirect(url_for('index'))

@app.route('/aumentar/<key>')
def aumentar_carrito(key):
    carrito = session.get('carrito', [])
    carrito.append(str(key))
    session['carrito'] = carrito; session.modified = True
    return redirect(url_for('mostrar_carrito'))

@app.route('/disminuir/<key>')
def disminuir_carrito(key):
    carrito = session.get('carrito', [])
    if str(key) in carrito: carrito.remove(str(key))
    session['carrito'] = carrito; session.modified = True
    return redirect(url_for('mostrar_carrito'))

@app.route('/carrito/eliminar/<key>')
def eliminar_carrito(key):
    session['carrito'] = [x for x in session.get('carrito', []) if x != str(key)]; session.modified = True
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
    ids_raw = session.get('carrito', [])
    todos = [a.to_dict() for a in Articulo.query.all()]
    items = []
    total = 0
    for item_key in set(ids_raw):
        p_id = item_key.split(':')[0]
        v_nombre = item_key.split(':')[1] if ':' in item_key else ""
        
        p = next((prod for prod in todos if str(prod['id']) == p_id), None)
        if p:
            cant = ids_raw.count(item_key)
            total += p['precio'] * cant
            it = p.copy()
            it['cantidad'] = cant
            it['key'] = item_key
            it['variante_elegida'] = v_nombre
            items.append(it)
    envio = session.get('envio', 0)
    zona = session.get('zona', 'No seleccionada')
    return render_template('carrito.html', carrito=items, total=total, envio=envio, zona=zona, total_final=total+envio)

@app.route('/admin/banner/agregar', methods=['POST'])
@login_requerido
def agregar_banner():
    banners = cargar_datos(BANNERS_JSON)
    f = request.files.get('imagen')
    if f and f.filename != '':
        try:
            res = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBBB_API_KEY}, files={"image": (f.filename, f.read())})
            if res.json().get("success"):
                banners.append({"id": max([b['id'] for b in banners], default=0) + 1, "titulo": request.form.get('titulo'), "descripcion": request.form.get('descripcion'), "imagen": res.json()["data"]["url"], "link": f"/?q={request.form.get('producto_id')}"})
                guardar_datos(BANNERS_JSON, banners)
        except: pass
    return redirect(url_for('admin'))

@app.route('/admin/banner/eliminar/<int:id>')
@login_requerido
def eliminar_banner(id):
    banners = [b for b in cargar_datos(BANNERS_JSON) if b['id'] != id]
    guardar_datos(BANNERS_JSON, banners)
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
            nuevo_art = Articulo(id=nuevo_id, nombre=str(row['Nombre']).upper(), precio=float(row['Precio']), categoria=str(row['Categoría']).upper(), subcategoria=str(row.get('Subcategoría', '')).upper(), stock=int(row.get('Stock', 0)), imagen="default.jpg", imagenes_extras="")
            db.session.add(nuevo_art)
            nuevo_id += 1
        db.session.commit()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
