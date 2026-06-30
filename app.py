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
from sqlalchemy.orm import selectinload
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

CACHE_BANNERS = None

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
    activo = db.Column(db.Boolean, default=True, nullable=False)

    variantes = db.relationship('Variante', backref='articulo', lazy=True, cascade="all, delete-orphan")

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
            "imagenes_extras": img_ex,
            "activo": self.activo,
            "variantes": [v.to_dict() for v in self.variantes]
        }

class Variante(db.Model):
    __tablename__ = 'variantes'
    id = db.Column(db.Integer, primary_key=True)
    articulo_id = db.Column(db.Integer, db.ForeignKey('articulos.id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False) 
    stock = db.Column(db.Integer, default=0)
    imagen = db.Column(db.String(500), nullable=True) 

    def to_dict(self):
        return {"id": self.id, "nombre": self.nombre, "stock": self.stock, "imagen": self.imagen if self.imagen else ""}

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

def cargar_datos_banners():
    global CACHE_BANNERS
    if CACHE_BANNERS is not None: return CACHE_BANNERS
    if not os.path.exists(BANNERS_JSON): return []
    with open(BANNERS_JSON, 'r', encoding='utf-8') as f:
        try: 
            CACHE_BANNERS = json.load(f)
            return CACHE_BANNERS
        except: return []

def guardar_datos_banners(datos):
    global CACHE_BANNERS
    CACHE_BANNERS = datos
    with open(BANNERS_JSON, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)

# Inyección automática en caliente de columnas nuevas si faltaran
with app.app_context():
    db.create_all()
    try:
        db.session.execute(text("ALTER TABLE articulos ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE;"))
        db.session.execute(text("ALTER TABLE variantes ADD COLUMN IF NOT EXISTS imagen VARCHAR(500);"))
        db.session.commit()
    except:
        db.session.rollback()

def login_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logueado'): return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.template_filter('pesos')
def formato_pesos(valor):
    try: return f"${int(float(valor)):,}".replace(",", ".")
    except: return "$0"

# --- RUTAS PÚBLICAS ---
@app.route('/')
def index():
    cat = request.args.get('cat')
    q = request.args.get('q')
    
    query = Articulo.query.options(selectinload(Articulo.variantes)).filter(Articulo.activo == True)
    
    if cat and cat != "Todos":
        query = query.filter((Articulo.categoria == cat) | (Articulo.subcategoria == cat))
    if q:
        q_l = f"%{q.lower()}%"
        query = query.filter((Articulo.nombre.ilike(q_l)) | (db.cast(Articulo.id, db.String).ilike(q_l)))
        
    articulos_db = query.all()
    productos = [a.to_dict() for a in articulos_db]
    banners = cargar_datos_banners()
    categorias = [c.to_dict() for c in Categoria.query.order_by(Categoria.nombre.asc()).all()]
        
    return render_template('tienda.html', productos=productos, banners=banners, carrito_total=len(session.get('carrito', [])), categorias=categorias, categories=categorias)

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
    articulos_db = Articulo.query.options(selectinload(Articulo.variantes)).order_by(Articulo.id.desc()).all()
    productos = [a.to_dict() for a in articulos_db]
    categorias = [c.to_dict() for c in Categoria.query.order_by(Categoria.nombre.asc()).all()]
    return render_template('admin.html', productos=productos, banners=cargar_datos_banners(), categorias=categorias, categories=categorias)

@app.route('/admin/pedidos')
@login_requerido
def ver_pedidos_seccion():
    pedidos = Pedido.query.order_by(Pedido.id.desc()).all()
    return render_template('pedidos.html', pedidos=pedidos)

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
        imagenes_extras=",".join(urls_subidas[1:]) if len(urls_subidas) > 1 else "", activo=True
    )
    db.session.add(nuevo_articulo)
    db.session.commit()
    
    variantes_raw = request.form.get('variantes_input', '')
    if variantes_raw:
        for v_item in variantes_raw.split(','):
            if not v_item.strip(): continue
            parts = v_item.split(':')
            if len(parts) >= 2:
                v_nom = parts[0].strip().upper()
                v_stk = int(parts[1].strip() or 0)
                v_img = ":".join(parts[2:]).strip() if len(parts) >= 3 else None
                nueva_v = Variante(articulo_id=nuevo_id, nombre=v_nom, stock=v_stk, imagen=v_img)
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
        articulo.subcategoria = request.form.get('subcategoria') or ""
        articulo.stock = int(request.form.get('stock') or 0)
        
        nuevas_fotos = request.files.getlist('fotos_nuevas')
        urls_subidas = []
        for f in nuevas_fotos:
            if f and f.filename != '':
                try:
                    res = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBBB_API_KEY}, files={"image": (f.filename, f.read())})
                    if res.json().get("success"): urls_subidas.append(res.json()["data"]["url"])
                except: pass
        if urls_subidas:
            articulo.imagen = urls_subidas[0]
            if len(urls_subidas) > 1:
                articulo.imagenes_extras = ",".join(urls_subidas[1:])
        
        # Procesar edición avanzada de variantes (Soporta COLOR:STOCK:FOTO)
        variantes_raw = request.form.get('variantes_input', '')
        if variantes_raw:
            Variante.query.filter_by(articulo_id=articulo.id).delete()
            for v_item in variantes_raw.split(','):
                if not v_item.strip(): continue
                parts = v_item.split(':')
                if len(parts) >= 2:
                    v_nom = parts[0].strip().upper()
                    v_stk = int(parts[1].strip() or 0)
                    v_img = ":".join(parts[2:]).strip() if len(parts) >= 3 else None
                    nueva_v = Variante(articulo_id=articulo.id, nombre=v_nom, stock=v_stk, imagen=v_img)
                    db.session.add(nueva_v)
        
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/producto/toggle_pausa/<int:id>')
@login_requerido
def toggle_pausa(id):
    articulo = Articulo.query.get(id)
    if articulo:
        articulo.activo = not articulo.activo
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

@app.route('/agregar_al_carrito', methods=['POST'])
def agregar_al_carrito():
    carrito = session.get('carrito', [])
    item_key = f"{request.form.get('id')}:{request.form.get('variante', '')}" if request.form.get('variante') else str(request.form.get('id'))
    carrito.append(item_key)
    session['carrito'] = carrito; session.modified = True
    return redirect(url_for('index'))

@app.route('/carrito')
def mostrar_carrito():
    ids_raw = session.get('carrito', [])
    todos = [a.to_dict() for a in Articulo.query.options(selectinload(Articulo.variantes)).all()]
    items = []; total = 0
    for item_key in set(ids_raw):
        p_id = item_key.split(':')[0]
        v_nombre = item_key.split(':')[1] if ':' in item_key else ""
        p = next((prod for prod in todos if str(prod['id']) == p_id), None)
        if p:
            cant = ids_raw.count(item_key)
            total += p['precio'] * cant
            it = p.copy(); it['cantidad'] = cant; it['key'] = item_key; it['variante_elegida'] = v_nombre
            v_obj = next((v for v in p['variantes'] if v['nombre'] == v_nombre), None)
            if v_obj and v_obj['imagen']: it['imagen'] = v_obj['imagen']
            items.append(it)
    return render_template('carrito.html', carrito=items, total=total, envio=session.get('envio', 0), zona=session.get('zona', 'No seleccionada'), total_final=total+session.get('envio', 0))

@app.route('/finalizar_pedido', methods=['POST'])
def finalizar_pedido():
    ids_raw = session.get('carrito', [])
    if not ids_raw: return redirect(url_for('index'))
    todos = [a.to_dict() for a in Articulo.query.options(selectinload(Articulo.variantes)).all()]
    items = []; total = 0
    for item_key in set(ids_raw):
        p_id = item_key.split(':')[0]
        v_nombre = item_key.split(':')[1] if ':' in item_key else ""
        p = next((prod for prod in todos if str(prod['id']) == p_id), None)
        if p:
            cant = ids_raw.count(item_key)
            total += p['precio'] * cant
            it = p.copy(); it['cantidad'] = cant; it['variante_elegida'] = v_nombre
            v_obj = next((v for v in p['variantes'] if v['nombre'] == v_nombre), None)
            if v_obj and v_obj['imagen']: it['imagen'] = v_obj['imagen']
            items.append(it)
    
    nuevo_pedido = Pedido(total=total+session.get('envio',0), envio=session.get('envio',0), zona=session.get('zona','Retiro'), estado="PENDIENTE")
    db.session.add(nuevo_pedido); db.session.commit()
    for i in items:
        db.session.add(DetallePedido(pedido_id=nuevo_pedido.id, articulo_id=i['id'], nombre=i['nombre'], variante_nombre=i['variante_elegida'], precio=i['precio'], cantidad=i['cantidad'], imagen=i['imagen']))
    db.session.commit()
    
    msj = f"Hola Bazar Guille! Pedido #{nuevo_pedido.id}\n--------------------\n"
    for i in items: msj += f"- {i['nombre']}{' ['+i['variante_elegida']+']' if i['variante_elegida'] else ''} x{i['cantidad']}\n"
    msj += f"Total Final: {formato_pesos(total+session.get('envio',0))}"
    session['carrito'] = []
    return redirect(f"https://wa.me/5491149899616?text={requests.utils.quote(msj)}")

@app.route('/admin/banner/agregar', methods=['POST'])
@login_requerido
def agregar_banner():
    banners = cargar_datos_banners()
    f = request.files.get('imagen')
    if f and f.filename != '':
        try:
            res = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBBB_API_KEY}, files={"image": (f.filename, f.read())})
            if res.json().get("success"):
                banners.append({"id": max([b['id'] for b in banners], default=0) + 1, "titulo": request.form.get('titulo'), "descripcion": request.form.get('descripcion'), "imagen": res.json()["data"]["url"], "link": f"/?q={request.form.get('producto_id')}"})
                guardar_datos_banners(banners)
        except: pass
    return redirect(url_for('admin'))

@app.route('/admin/banner/eliminar/<int:id>')
@login_requerido
def eliminar_banner(id):
    banners = [b for b in cargar_datos_banners() if b['id'] != id]
    guardar_datos_banners(banners)
    return redirect(url_for('admin'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)