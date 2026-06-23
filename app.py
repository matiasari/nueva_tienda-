import os
import json
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy 
from werkzeug.utils import secure_filename
from functools import wraps
import io
import requests

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

# 🔴 NUEVO: Tabla permanente para Banners en PostgreSQL
class Banner(db.Model):
    __tablename__ = 'banners'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(250), nullable=True)
    descripcion = db.Column(db.String(500), nullable=True)
    imagen = db.Column(db.String(500), nullable=False)
    link = db.Column(db.String(250), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "titulo": self.titulo,
            "descripcion": self.descripcion,
            "imagen": self.imagen,
            "link": self.link
        }

# 🔴 NUEVO: Tabla permanente para Categorías en PostgreSQL
class Categoria(db.Model):
    __tablename__ = 'categorias'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    subcategorias_text = db.Column(db.Text, default="") # Guardado como texto separado por comas

    def to_dict(self):
        subs = [s.strip() for s in self.subcategorias_text.split(',') if s.strip()] if self.subcategorias_text else []
        return {
            "nombre": self.nombre,
            "subcategorias": subs
        }

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# 🔴 NUEVO: Asegura que las tablas se creen en Render de forma permanente
with app.app_context():
    db.create_all()

# --- SEGURIDAD ---
def login_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logueado'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- FILTROS JINJA ---
@app.template_filter('pesos')
def formato_pesos(valor):
    try: return f"${int(float(valor)):,}".replace(",", ".")
    except: return "$0"

# --- RUTAS PÚBLICAS ---
@app.route('/')
def index():
    articulos_db = Articulo.query.all()
    productos = [a.to_dict() for a in articulos_db]
    
    # 🔴 CAMBIADO: Traemos desde PostgreSQL
    banners_db = Banner.query.all()
    banners = [b.to_dict() for b in banners_db]
    
    categorias_db = Categoria.query.all()
    categorias = [c.to_dict() for c in categorias_db]
    
    cat = request.args.get('cat')
    q = request.args.get('q')

    prod_mostrar = productos
    if cat and cat != "Todos":
        prod_mostrar = [p for p in prod_mostrar if p.get('categoria') == cat or p.get('subcategoria') == cat]
    
    if q:
        q_l = q.lower()
        prod_mostrar = [p for p in prod_mostrar if q_l in p.get('nombre', '').lower() or str(p.get('id')) == q_l]
        
    return render_template('tienda.html', productos=prod_mostrar, banners=banners, 
                           carrito_total=len(session.get('carrito', [])), categorias=categorias)

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
    articulos_db = Articulo.query.order_by(Articulo.id.desc()).all()
    productos = [a.to_dict() for a in articulos_db]
    
    # 🔴 CAMBIADO: Traemos desde PostgreSQL permanente
    banners_db = Banner.query.all()
    banners = [b.to_dict() for b in banners_db]
    
    categorias_db = Categoria.query.all()
    categorias = [c.to_dict() for c in categorias_db]
    
    return render_template('admin.html', productos=productos, banners=banners, categorias=categorias)

# --- GESTIÓN DE CATEGORÍAS (MODIFICADO A BD PERMANENTE) ---
@app.route('/admin/categorias/agregar', methods=['POST'])
@login_requerido
def agregar_categoria():
    nueva = request.form.get('nombre').strip().upper()
    if nueva:
        existe = Categoria.query.filter_by(nombre=nueva).first()
        if not existe:
            cat = Categoria(nombre=nueva, subcategorias_text="")
            db.session.add(cat)
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

# --- PRODUCTOS (ABM CON CONEXIÓN EN NUBE IMGBB) ---
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
                if res_data.get("success"):
                    urls_subidas.append(res_data["data"]["url"])
            except Exception as e:
                print(f"Error al subir a ImgBB: {e}")

    max_id = db.session.query(db.func.max(Articulo.id)).scalar() or 0
    nuevo_id = max_id + 1
    
    img_extras_str = ",".join(urls_subidas[1:]) if len(urls_subidas) > 1 else ""
    imagen_portada = urls_subidas[0] if urls_subidas else "default.jpg"

    nuevo_articulo = Articulo(
        id=nuevo_id,
        nombre=request.form.get('nombre', '').upper(),
        precio=float(request.form.get('precio') or 0),
        categoria=request.form.get('categoria'),
        subcategoria=request.form.get('subcategoria'),
        stock=int(request.form.get('stock') or 0),
        imagen=imagen_portada,
        imagenes_extras=img_extras_str
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
                    if res_data.get("success"):
                        orden.append(res_data["data"]["url"])
                except Exception as e:
                    print(f"Error en edicion ImgBB: {e}")
        
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

# --- EXCEL ---
@app.route('/admin/importar_excel', methods=['POST'])
@login_requerido
def importar_excel():
    file = request.files.get('archivo_excel')
    if file and file.filename != '':
        df = pd.read_excel(file)
        
        max_id = db.session.query(db.func.max(Articulo.id)).scalar() or 0
        nuevo_id = max_id + 1
        
        for _, row in df.iterrows():
            nuevo_art = Articulo(
                id=nuevo_id,
                nombre=str(row['Nombre']).upper(),
                precio=float(row['Precio']),
                categoria=str(row['Categoría']).upper(),
                subcategoria=str(row.get('Subcategoría', '')).upper(),
                stock=int(row.get('Stock', 0)),
                imagen="default.jpg",
                imagenes_extras=""
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
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                     as_attachment=True, download_name='plantilla_bazar.xlsx')

# --- CARRITO ---
@app.route('/agregar_al_carrito', methods=['POST'])
def agregar_al_carrito():
    carrito = session.get('carrito', [])
    carrito.append(str(request.form.get('id')))
    session['carrito'] = carrito
    session.modified = True
    return redirect(url_for('index'))

@app.route('/carrito')
def mostrar_carrito():
    ids = session.get('carrito', [])
    articulos_db = Articulo.query.all()
    todos = [a.to_dict() for a in articulos_db]
    
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
    msj = f"Hola Bazar Guille! Pedido:\n" + "\n".join([f"- {i['nombre']} x{i['cantidad']}" for i in items])
    link_wa = f"https://wa.me/5491149899616?text={msj.replace(' ', '%20')}"
    return render_template('carrito.html', carrito=items, total=total, envio=envio, total_final=total+envio, link_whatsapp=link_wa)

# --- BANNERS (ABM MODIFICADO PARA POSTGRESQL + IMGBB PERMANENTE) ---
@app.route('/admin/banner/agregar', methods=['POST'])
@login_requerido
def agregar_banner():
    f = request.files.get('imagen')
    if f and f.filename != '':
        img_bytes = f.read()
        payload = {"key": IMGBBB_API_KEY}
        files = {"image": (f.filename, img_bytes)}
        try:
            response = requests.post("https://api.imgbb.com/1/upload", data=payload, files=files)
            res_data = response.json()
            if res_data.get("success"):
                url_banner = res_data["data"]["url"]
                
                # 🔴 CAMBIADO: Guardamos directo en PostgreSQL
                nuevo_banner = Banner(
                    titulo=request.form.get('titulo'),
                    descripcion=request.form.get('descripcion'),
                    imagen=url_banner,
                    link=f"/?q={request.form.get('producto_id')}"
                )
                db.session.add(nuevo_banner)
                db.session.commit()
        except Exception as e:
            print(f"Error al subir banner a ImgBB: {e}")
    return redirect(url_for('admin'))

@app.route('/admin/banner/eliminar/<int:id>')
@login_requerido
def eliminar_banner(id):
    # 🔴 CAMBIADO: Eliminamos de PostgreSQL
    banner = Banner.query.get(id)
    if banner:
        db.session.delete(banner)
        db.session.commit()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)