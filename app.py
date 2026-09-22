import os
import json
import re
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy 
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import io
import requests
from datetime import datetime
from sqlalchemy.orm import selectinload
from sqlalchemy import text
from PIL import Image
from fpdf import FPDF

app = Flask(__name__)

# --- CONFIGURACIÓN ---
app.secret_key = 'bazar_guille_key_secret_2026'
app.config['SESSION_COOKIE_NAME'] = 'bazar_guille_session'
app.config['SESSION_PERMANENT'] = True
app.config['UPLOAD_FOLDER'] = 'static/uploads'

MONTO_MINIMO_MAYORISTA = 50000.0

# 🔴 CONFIGURACIÓN DE POSTGRESQL EN RENDER
URL_RENDER = "postgresql://guille_admin:7nHE9WVezwoXS0RsDUiMrNkogSSX3FAW@dpg-d8sjeme7r5hc73fjftrg-a.oregon-postgres.render.com/bazarguille_db"
app.config['SQLALCHEMY_DATABASE_URI'] = URL_RENDER
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

BANNERS_JSON = 'banners.json'
API_KEY_SINCRO = "Guille_Linux_Sincro_2026"
IMGBBB_API_KEY = "65c21c6edd31fca5dd8d37e1ff870739"

CACHE_BANNERS = None

# --- LIMPIEZA DE TEXTO PARA PDF (EVITA ERRORES DE EMOJIS/UNICODE) ---
def limpiar_texto_pdf(texto):
    if not texto:
        return ""
    return str(texto).encode('latin-1', 'replace').decode('latin-1')

# --- COMPRESIÓN / OPTIMIZACIÓN DE IMÁGENES AL SUBIR ---
def optimizar_imagen(file, max_ancho=1000, calidad=80):
    try:
        img = Image.open(file)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if img.width > max_ancho:
            alto_proporcional = int((max_ancho / float(img.width)) * img.height)
            filtro = getattr(Image, 'Resampling', Image).LANCZOS
            img = img.resize((max_ancho, alto_proporcional), filtro)
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=calidad, optimize=True)
        buffer.seek(0)
        return buffer
    except Exception as e:
        file.seek(0)
        return file

# --- MODELOS DE LA BASE DE DATOS ---

class Cliente(db.Model):
    __tablename__ = 'clientes'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    telefono = db.Column(db.String(50), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    tipo_cliente = db.Column(db.String(20), default="MINORISTA") # "MINORISTA" o "MAYORISTA"
    activo = db.Column(db.Boolean, default=True)

class Articulo(db.Model):
    __tablename__ = 'articulos'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(100), nullable=True, default="")
    nombre = db.Column(db.String(250), nullable=False)
    precio = db.Column(db.Float, nullable=False)  # Minorista
    precio_mayorista = db.Column(db.Float, nullable=True, default=0.0)  # Mayorista
    categoria = db.Column(db.String(100), nullable=True)
    subcategoria = db.Column(db.String(100), nullable=True, default="")
    stock = db.Column(db.Integer, default=0) 
    imagen = db.Column(db.String(500), nullable=True)
    imagenes_extras = db.Column(db.Text, nullable=True, default="") 
    video_url = db.Column(db.String(500), nullable=True, default="")
    activo = db.Column(db.Boolean, default=True, nullable=False)

    variantes = db.relationship('Variante', backref='articulo', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        img_ex = self.imagenes_extras.split(',') if self.imagenes_extras else []
        return {
            "id": self.id,
            "codigo": self.codigo if self.codigo else "",
            "nombre": self.nombre,
            "precio": self.precio,
            "precio_mayorista": self.precio_mayorista if (self.precio_mayorista and self.precio_mayorista > 0) else self.precio,
            "categoria": self.categoria if self.categoria else "VARIOS",
            "subcategoria": self.subcategoria if self.subcategoria else "",
            "stock": self.stock,
            "imagen": self.imagen if self.imagen else "default.jpg",
            "imagenes_extras": img_ex,
            "video_url": self.video_url if self.video_url else "",
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
    cliente_id = db.Column(db.Integer, nullable=True)
    tipo_pedido = db.Column(db.String(20), default="MINORISTA")
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

# Inyección automática de columnas en PostgreSQL
with app.app_context():
    db.create_all()
    try:
        db.session.execute(text("ALTER TABLE articulos ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE;"))
        db.session.execute(text("ALTER TABLE articulos ADD COLUMN IF NOT EXISTS codigo VARCHAR(100) DEFAULT '';"))
        db.session.execute(text("ALTER TABLE articulos ADD COLUMN IF NOT EXISTS video_url VARCHAR(500) DEFAULT '';"))
        db.session.execute(text("ALTER TABLE articulos ADD COLUMN IF NOT EXISTS precio_mayorista FLOAT DEFAULT 0.0;"))
        db.session.execute(text("ALTER TABLE variantes ADD COLUMN IF NOT EXISTS imagen VARCHAR(500);"))
        db.session.execute(text("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS tipo_cliente VARCHAR(20) DEFAULT 'MINORISTA';"))
        db.session.execute(text("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS cliente_id INTEGER;"))
        db.session.execute(text("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS tipo_pedido VARCHAR(20) DEFAULT 'MINORISTA';"))
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

# --- RUTAS DE CLIENTES (LOGIN Y REGISTRO MAYORISTA) ---
@app.route('/cliente/registro', methods=['GET', 'POST'])
def registro_cliente():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        email = request.form.get('email', '').strip().lower()
        telefono = request.form.get('telefono', '').strip()
        password = request.form.get('password')
        tipo = request.form.get('tipo_cliente', 'MINORISTA')

        cliente_existente = Cliente.query.filter_by(email=email).first()
        if cliente_existente:
            return render_template('registro.html', error="El email ya se encuentra registrado.")

        nuevo_cliente = Cliente(
            nombre=nombre,
            email=email,
            telefono=telefono,
            password=generate_password_hash(password),
            tipo_cliente=tipo
        )
        db.session.add(nuevo_cliente)
        db.session.commit()

        session['cliente_id'] = nuevo_cliente.id
        session['cliente_nombre'] = nuevo_cliente.nombre
        session['cliente_tipo'] = nuevo_cliente.tipo_cliente
        return redirect(url_for('index'))

    return render_template('registro.html')

@app.route('/cliente/login', methods=['GET', 'POST'])
def login_cliente():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')

        cliente = Cliente.query.filter_by(email=email).first()
        if cliente and check_password_hash(cliente.password, password):
            session['cliente_id'] = cliente.id
            session['cliente_nombre'] = cliente.nombre
            session['cliente_tipo'] = cliente.tipo_cliente
            return redirect(url_for('index'))
        else:
            return render_template('login_cliente.html', error="Email o contraseña incorrectos.")

    return render_template('login_cliente.html')

@app.route('/cliente/logout')
def logout_cliente():
    session.pop('cliente_id', None)
    session.pop('cliente_nombre', None)
    session.pop('cliente_tipo', None)
    return redirect(url_for('index'))

# --- RUTAS PÚBLICAS Y TIENDA ---
@app.route('/')
def index():
    cat = request.args.get('cat')
    q = request.args.get('q')
    
    query = Articulo.query.options(selectinload(Articulo.variantes)).filter(Articulo.activo == True)
    
    if cat and cat != "Todos":
        query = query.filter((Articulo.categoria == cat) | (Articulo.subcategoria == cat))
    if q:
        q_l = f"%{q.lower()}%"
        query = query.filter((Articulo.nombre.ilike(q_l)) | (db.cast(Articulo.id, db.String).ilike(q_l)) | (Articulo.codigo.ilike(q_l)))
        
    articulos_db = query.all()
    productos = [a.to_dict() for a in articulos_db]
    banners = cargar_datos_banners()
    categorias = [c.to_dict() for c in Categoria.query.order_by(Categoria.nombre.asc()).all()]
        
    return render_template('tienda.html', productos=productos, banners=banners, carrito_total=len(session.get('carrito', [])), categorias=categorias, categories=categorias, monto_minimo=MONTO_MINIMO_MAYORISTA)

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
    
    total_unidades_stock = 0
    total_valor_mercaderia = 0.0

    for a in articulos_db:
        if a.variantes and len(a.variantes) > 0:
            stk_prod = sum(v.stock for v in a.variantes)
        else:
            stk_prod = a.stock or 0
            
        total_unidades_stock += stk_prod
        total_valor_mercaderia += (stk_prod * (a.precio or 0.0))

    productos = [a.to_dict() for a in articulos_db]
    categorias = [c.to_dict() for c in Categoria.query.order_by(Categoria.nombre.asc()).all()]
    
    return render_template(
        'admin.html', 
        productos=productos, 
        banners=cargar_datos_banners(), 
        categorias=categorias, 
        categories=categorias,
        total_unidades_stock=total_unidades_stock,
        total_valor_mercaderia=total_valor_mercaderia
    )

@app.route('/admin/pedidos')
@login_requerido
def ver_pedidos_seccion():
    pedidos = Pedido.query.order_by(Pedido.id.desc()).all()
    return render_template('pedidos.html', pedidos=pedidos)

# --- GESTIÓN DE ESTADO Y CANCELACIÓN DE PEDIDOS ---
@app.route('/admin/pedido/cancelar/<int:id>')
@login_requerido
def cancelar_pedido(id):
    pedido = Pedido.query.get(id)
    if pedido:
        pedido.estado = "CANCELADO"
        db.session.commit()
    
    from_param = request.args.get('from')
    if from_param == 'pedidos':
        return redirect(url_for('ver_pedidos_seccion'))
    return redirect(url_for('admin'))

@app.route('/admin/pedido/cambiar_estado/<int:id>/<string:nuevo_estado>')
@login_requerido
def cambiar_estado_pedido(id, nuevo_estado):
    pedido = Pedido.query.get(id)
    if pedido:
        pedido.estado = nuevo_estado.upper()
        db.session.commit()
    
    from_param = request.args.get('from')
    if from_param == 'pedidos':
        return redirect(url_for('ver_pedidos_seccion'))
    return redirect(url_for('admin'))

@app.route('/admin/pedido/eliminar/<int:id>')
@login_requerido
def eliminar_pedido(id):
    pedido = Pedido.query.get(id)
    if pedido:
        db.session.delete(pedido)
        db.session.commit()
    
    from_param = request.args.get('from')
    if from_param == 'pedidos':
        return redirect(url_for('ver_pedidos_seccion'))
    return redirect(url_for('admin'))

# --- EXPORTAR CATÁLOGO PDF MINORISTA (ULTRA EFICIENTE EN MEMORIA) ---
@app.route('/admin/articulos/exportar/pdf/minorista')
@login_requerido
def exportar_articulos_pdf_minorista():
    articulos = Articulo.query.options(selectinload(Articulo.variantes)).filter_by(activo=True).order_by(Articulo.categoria.asc(), Articulo.nombre.asc()).all()

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, limpiar_texto_pdf("CATÁLOGO DE PRODUCTOS - BAZAR GUILLE"), ln=1, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, limpiar_texto_pdf("Precios de Venta - Sujetos a cambio sin previo aviso"), ln=1, align="C")
    pdf.ln(5)
    
    cat_actual = ""

    for a in articulos:
        cat_nombre = a.categoria.upper() if a.categoria else "VARIOS"
        
        if cat_nombre != cat_actual:
            cat_actual = cat_nombre
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(0, 8, limpiar_texto_pdf(f"  CATEGORÍA: {cat_actual}"), ln=1, fill=True)
            pdf.ln(2)
        
        y_inicial = pdf.get_y()
        if y_inicial > 260:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(130, 6, limpiar_texto_pdf(a.nombre[:55]))
        
        precio_minorista = f"${int(a.precio):,}".replace(",", ".")
        pdf.cell(50, 6, f"Precio: {precio_minorista}", align="R", ln=1)

        if a.codigo:
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(130, 4, limpiar_texto_pdf(f"Cód: {a.codigo}"), ln=1)
            pdf.set_text_color(0, 0, 0)

        pdf.set_draw_color(230, 230, 230)
        pdf.line(15, pdf.get_y() + 1, 195, pdf.get_y() + 1)
        pdf.ln(2)

    pdf_bytes = pdf.output(dest='S')
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode('latin1')

    buffer_pdf = io.BytesIO(pdf_bytes)
    
    return send_file(
        buffer_pdf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"catalogo_minorista_bazar_guille_{datetime.now().strftime('%Y%m%d')}.pdf"
    )

# --- EXPORTAR CATÁLOGO PDF MAYORISTA (ULTRA EFICIENTE EN MEMORIA) ---
@app.route('/admin/articulos/exportar/pdf/mayorista')
@login_requerido
def exportar_articulos_pdf_mayorista():
    articulos = Articulo.query.options(selectinload(Articulo.variantes)).filter_by(activo=True).order_by(Articulo.categoria.asc(), Articulo.nombre.asc()).all()

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, limpiar_texto_pdf("CATÁLOGO MAYORISTA - BAZAR GUILLE"), ln=1, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, limpiar_texto_pdf("Precios Especiales por Mayor (Mínimo $50.000) - Sujetos a cambio sin previo aviso"), ln=1, align="C")
    pdf.ln(5)
    
    cat_actual = ""

    for a in articulos:
        cat_nombre = a.categoria.upper() if a.categoria else "VARIOS"
        
        if cat_nombre != cat_actual:
            cat_actual = cat_nombre
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(0, 8, limpiar_texto_pdf(f"  CATEGORÍA: {cat_actual}"), ln=1, fill=True)
            pdf.ln(2)
        
        y_inicial = pdf.get_y()
        if y_inicial > 260:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(130, 6, limpiar_texto_pdf(a.nombre[:55]))
        
        p_may = a.precio_mayorista if (a.precio_mayorista and a.precio_mayorista > 0) else a.precio
        precio_mayorista = f"${int(p_may):,}".replace(",", ".")
        pdf.cell(50, 6, f"Precio Mayor: {precio_mayorista}", align="R", ln=1)

        if a.codigo:
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(130, 4, limpiar_texto_pdf(f"Cód: {a.codigo}"), ln=1)
            pdf.set_text_color(0, 0, 0)

        pdf.set_draw_color(230, 230, 230)
        pdf.line(15, pdf.get_y() + 1, 195, pdf.get_y() + 1)
        pdf.ln(2)

    pdf_bytes = pdf.output(dest='S')
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode('latin1')

    buffer_pdf = io.BytesIO(pdf_bytes)
    
    return send_file(
        buffer_pdf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"catalogo_mayorista_bazar_guille_{datetime.now().strftime('%Y%m%d')}.pdf"
    )

# --- EXPORTAR EXCEL ---
@app.route('/admin/articulos/exportar/excel')
@login_requerido
def exportar_articulos_excel():
    articulos = Articulo.query.options(selectinload(Articulo.variantes)).order_by(Articulo.id.asc()).all()
    
    filas = []
    for a in articulos:
        p_may = a.precio_mayorista if (a.precio_mayorista and a.precio_mayorista > 0) else a.precio
        if a.variantes and len(a.variantes) > 0:
            for v in a.variantes:
                filas.append({
                    "ID_Producto": a.id,
                    "Codigo": a.codigo or '',
                    "Nombre": a.nombre,
                    "Categoria": a.categoria or 'VARIOS',
                    "Subcategoria": a.subcategoria or '',
                    "Variante": v.nombre,
                    "Stock": v.stock,
                    "Precio_Minorista": a.precio,
                    "Precio_Mayorista": p_may,
                    "Estado": "ACTIVO" if a.activo else "PAUSADO",
                    "Imagen": v.imagen if v.imagen else a.imagen
                })
        else:
            filas.append({
                "ID_Producto": a.id,
                "Codigo": a.codigo or '',
                "Nombre": a.nombre,
                "Categoria": a.categoria or 'VARIOS',
                "Subcategoria": a.subcategoria or '',
                "Variante": "ÚNICA",
                "Stock": a.stock,
                "Precio_Minorista": a.precio,
                "Precio_Mayorista": p_may,
                "Estado": "ACTIVO" if a.activo else "PAUSADO",
                "Imagen": a.imagen
            })
            
    df = pd.DataFrame(filas)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Catalogo_Bazar_Guille')
    output.seek(0)
    
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"catalogo_bazar_guille_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    )

# --- ABM PRODUCTOS ---
@app.route('/admin/producto/agregar', methods=['POST'])
@login_requerido
def agregar_producto():
    fotos = request.files.getlist('imagenes_extras')
    urls_subidas = []
    for img in fotos:
        if img and img.filename != '':
            try:
                img_opt = optimizar_imagen(img)
                res = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBBB_API_KEY}, files={"image": (img.filename, img_opt)})
                if res.json().get("success"): urls_subidas.append(res.json()["data"]["url"])
            except: pass
            
    max_id = db.session.query(db.func.max(Articulo.id)).scalar() or 0
    nuevo_id = max_id + 1
    
    nuevo_articulo = Articulo(
        id=nuevo_id, 
        codigo=request.form.get('codigo', '').strip().upper(),
        nombre=request.form.get('nombre', '').upper(), 
        precio=float(request.form.get('precio') or 0),
        precio_mayorista=float(request.form.get('precio_mayorista') or 0),
        categoria=request.form.get('categoria'), 
        subcategoria=request.form.get('subcategoria'),
        stock=int(request.form.get('stock') or 0), 
        imagen=urls_subidas[0] if urls_subidas else "default.jpg",
        imagenes_extras=",".join(urls_subidas[1:]) if len(urls_subidas) > 1 else "", 
        video_url=request.form.get('video_url', '').strip(),
        activo=True
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
        articulo.codigo = request.form.get('codigo', '').strip().upper()
        articulo.nombre = request.form.get('nombre', '').upper()
        articulo.precio = float(request.form.get('precio') or 0)
        articulo.precio_mayorista = float(request.form.get('precio_mayorista') or 0)
        articulo.categoria = request.form.get('categoria')
        articulo.subcategoria = request.form.get('subcategoria') or ""
        articulo.stock = int(request.form.get('stock') or 0)
        articulo.video_url = request.form.get('video_url', '').strip()
        
        nuevas_fotos = request.files.getlist('fotos_nuevas')
        urls_subidas = []
        for f in nuevas_fotos:
            if f and f.filename != '':
                try:
                    f_opt = optimizar_imagen(f)
                    res = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBBB_API_KEY}, files={"image": (f.filename, f_opt)})
                    if res.json().get("success"): urls_subidas.append(res.json()["data"]["url"])
                except: pass
        if urls_subidas:
            articulo.imagen = urls_subidas[0]
            if len(urls_subidas) > 1:
                articulo.imagenes_extras = ",".join(urls_subidas[1:])
        
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
    es_mayorista = session.get('cliente_tipo') == 'MAYORISTA'

    for item_key in set(ids_raw):
        p_id = item_key.split(':')[0]
        v_nombre = item_key.split(':')[1] if ':' in item_key else ""
        p = next((prod for prod in todos if str(prod['id']) == p_id), None)
        if p:
            cant = ids_raw.count(item_key)
            precio_unitario = p['precio_mayorista'] if (es_mayorista and p['precio_mayorista'] > 0) else p['precio']
            total += precio_unitario * cant
            it = p.copy()
            it['precio_aplicado'] = precio_unitario
            it['cantidad'] = cant
            it['key'] = item_key
            it['variante_elegida'] = v_nombre
            v_obj = next((v for v in p['variantes'] if v['nombre'] == v_nombre), None)
            if v_obj and v_obj['imagen']: it['imagen'] = v_obj['imagen']
            items.append(it)

    error_msg = request.args.get('error')
    return render_template('carrito.html', carrito=items, total=total, envio=session.get('envio', 0), zona=session.get('zona', 'No seleccionada'), total_final=total+session.get('envio', 0), es_mayorista=es_mayorista, monto_minimo=MONTO_MINIMO_MAYORISTA, error_msg=error_msg)

@app.route('/finalizar_pedido', methods=['POST'])
def finalizar_pedido():
    ids_raw = session.get('carrito', [])
    if not ids_raw: return redirect(url_for('index'))
    todos = [a.to_dict() for a in Articulo.query.options(selectinload(Articulo.variantes)).all()]
    items = []; total = 0
    es_mayorista = session.get('cliente_tipo') == 'MAYORISTA'

    for item_key in set(ids_raw):
        p_id = item_key.split(':')[0]
        v_nombre = item_key.split(':')[1] if ':' in item_key else ""
        p = next((prod for prod in todos if str(prod['id']) == p_id), None)
        if p:
            cant = ids_raw.count(item_key)
            precio_unitario = p['precio_mayorista'] if (es_mayorista and p['precio_mayorista'] > 0) else p['precio']
            total += precio_unitario * cant
            it = p.copy()
            it['precio_aplicado'] = precio_unitario
            it['cantidad'] = cant
            it['variante_elegida'] = v_nombre
            v_obj = next((v for v in p['variantes'] if v['nombre'] == v_nombre), None)
            if v_obj and v_obj['imagen']: it['imagen'] = v_obj['imagen']
            items.append(it)

    # Validación de Monto Mínimo Mayorista
    if es_mayorista and total < MONTO_MINIMO_MAYORISTA:
        return redirect(url_for('mostrar_carrito', error=f"El monto mínimo para compras mayoristas es de ${int(MONTO_MINIMO_MAYORISTA):,}".replace(",", ".")))

    nuevo_pedido = Pedido(
        total=total+session.get('envio',0), 
        envio=session.get('envio',0), 
        zona=session.get('zona','Retiro'), 
        estado="PENDIENTE",
        cliente_id=session.get('cliente_id'),
        tipo_pedido="MAYORISTA" if es_mayorista else "MINORISTA"
    )
    db.session.add(nuevo_pedido); db.session.commit()

    for i in items:
        db.session.add(DetallePedido(pedido_id=nuevo_pedido.id, articulo_id=i['id'], nombre=i['nombre'], variante_nombre=i['variante_elegida'], precio=i['precio_aplicado'], cantidad=i['cantidad'], imagen=i['imagen']))
    db.session.commit()
    
    msj = f"Hola Bazar Guille! Pedido {'MAYORISTA' if es_mayorista else 'MINORISTA'} #{nuevo_pedido.id}\n"
    if session.get('cliente_nombre'):
        msj += f"Cliente: {session.get('cliente_nombre')}\n"
    msj += "--------------------\n"
    for i in items: 
        msj += f"- {i['nombre']}{' ['+i['variante_elegida']+']' if i['variante_elegida'] else ''} x{i['cantidad']} ({formato_pesos(i['precio_aplicado'])})\n"
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
            f_opt = optimizar_imagen(f, max_ancho=1400)
            res = requests.post("https://api.imgbb.com/1/upload", data={"key": IMGBBB_API_KEY}, files={"image": (f.filename, f_opt)})
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