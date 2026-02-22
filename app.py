import os
import json
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from werkzeug.utils import secure_filename
from functools import wraps
import io

app = Flask(__name__)

# --- CONFIGURACIÓN DE SESIÓN ---
app.secret_key = 'bazar_guille_key_secret_2026'
app.config['SESSION_COOKIE_NAME'] = 'bazar_guille_session'
app.config['SESSION_PERMANENT'] = True
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Archivos de datos
PRODUCTOS_JSON = 'productos.json'
BANNERS_JSON = 'banners.json'
API_KEY_SINCRO = "Guille_Linux_Sincro_2026"

# --- CATEGORÍAS AMPLIADAS ---
CATEGORIAS_BAZAR = [
    "Cocina", "Baño", "Decoración", "Electrónica", 
    "Mates", "Textil", "Vajilla", "Limpieza", "Escolar", "Otros"
]

# --- PERSISTENCIA ---
def cargar_datos(archivo):
    if not os.path.exists(archivo): return []
    with open(archivo, 'r', encoding='utf-8') as f:
        try: return json.load(f)
        except: return []

def guardar_datos(archivo, datos):
    with open(archivo, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

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

# --- API DE SINCRONIZACIÓN ---
@app.route('/api/actualizar_stock', methods=['POST'])
def api_actualizar_stock():
    if request.headers.get('X-API-KEY') != API_KEY_SINCRO:
        return jsonify({"status": "error", "message": "No autorizado"}), 401
    datos = request.get_json()
    if datos:
        guardar_datos(PRODUCTOS_JSON, datos)
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 400

# --- RUTAS PÚBLICAS ---
@app.route('/')
def index():
    productos = cargar_datos(PRODUCTOS_JSON)
    banners = cargar_datos(BANNERS_JSON)
    cat = request.args.get('cat')
    q = request.args.get('q')
    
    prod_mostrar = productos
    if cat and cat != "Todos":
        prod_mostrar = [p for p in prod_mostrar if p.get('categoria') == cat]
    if q:
        q_l = q.lower()
        prod_mostrar = [p for p in prod_mostrar if q_l in p.get('nombre', '').lower() or str(p.get('id')) == q_l]
        
    return render_template('tienda.html', productos=prod_mostrar, banners=banners, 
                           carrito_total=len(session.get('carrito', [])), categorias=CATEGORIAS_BAZAR)

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
    productos = cargar_datos(PRODUCTOS_JSON)
    for p in productos:
        if 'imagenes_extras' not in p: p['imagenes_extras'] = []
    return render_template('admin.html', productos=productos, banners=cargar_datos(BANNERS_JSON), categorias=CATEGORIAS_BAZAR)

@app.route('/admin/producto/agregar', methods=['POST'])
@login_requerido
def agregar_producto():
    productos = cargar_datos(PRODUCTOS_JSON)
    fotos = request.files.getlist('imagenes_extras')
    nombres = []
    for img in fotos:
        if img.filename != '':
            fn = secure_filename(img.filename)
            img.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            nombres.append(fn)

    nuevo = {
        "id": max([p['id'] for p in productos], default=0) + 1,
        "nombre": request.form.get('nombre', '').upper(),
        "precio": float(request.form.get('precio') or 0),
        "categoria": request.form.get('categoria'),
        "stock": int(request.form.get('stock') or 0),
        "imagen": nombres[0] if nombres else "default.jpg",
        "imagenes_extras": nombres[1:] if len(nombres) > 1 else []
    }
    productos.append(nuevo)
    guardar_datos(PRODUCTOS_JSON, productos)
    return redirect(url_for('admin'))

@app.route('/admin/producto/editar', methods=['POST'])
@login_requerido
def editar_producto():
    p_id = request.form.get('id')
    productos = cargar_datos(PRODUCTOS_JSON)
    for p in productos:
        if str(p['id']) == str(p_id):
            p['nombre'] = request.form.get('nombre', '').upper()
            p['precio'] = float(request.form.get('precio') or 0)
            p['categoria'] = request.form.get('categoria')
            p['stock'] = int(request.form.get('stock') or 0)
            
            orden = request.form.getlist('orden_fotos[]')
            nuevas = request.files.getlist('fotos_extras')
            for f in nuevas:
                if f.filename != '':
                    fn = secure_filename(f.filename)
                    f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                    orden.append(fn)
            
            if orden:
                p['imagen'] = orden[0]
                p['imagenes_extras'] = orden[1:]
            break
    guardar_datos(PRODUCTOS_JSON, productos)
    return redirect(url_for('admin'))

@app.route('/admin/producto/eliminar/<int:id>')
@login_requerido
def eliminar_producto(id):
    productos = [p for p in cargar_datos(PRODUCTOS_JSON) if p['id'] != id]
    guardar_datos(PRODUCTOS_JSON, productos)
    return redirect(url_for('admin'))

# --- EXCEL ---
@app.route('/admin/importar_excel', methods=['POST'])
@login_requerido
def importar_excel():
    file = request.files.get('archivo_excel')
    if file and file.filename != '':
        df = pd.read_excel(file)
        productos = cargar_datos(PRODUCTOS_JSON)
        nuevo_id = max([p['id'] for p in productos], default=0) + 1
        for _, row in df.iterrows():
            productos.append({
                "id": nuevo_id, "nombre": str(row['Nombre']).upper(), "precio": float(row['Precio']),
                "categoria": str(row['Categoría']), "stock": int(row.get('Stock', 0)),
                "imagen": "default.jpg", "imagenes_extras": []
            })
            nuevo_id += 1
        guardar_datos(PRODUCTOS_JSON, productos)
    return redirect(url_for('admin'))

@app.route('/admin/descargar_plantilla')
@login_requerido
def descargar_plantilla():
    df = pd.DataFrame(columns=['Nombre', 'Precio', 'Categoría', 'Stock'])
    df.loc[0] = ['Ejemplo', 1500.0, 'Cocina', 10]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.ms-excel', as_attachment=True, download_name='plantilla.xlsx')

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
    todos = cargar_datos(PRODUCTOS_JSON)
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
    total_f = total + envio
    msj = f"Hola Bazar Guille! Pedido:\n" + "\n".join([f"- {i['nombre']} x{i['cantidad']}" for i in items])
    link_wa = f"https://wa.me/5491149899616?text={msj.replace(' ', '%20')}"
    return render_template('carrito.html', carrito=items, total=total, envio=envio, total_final=total_f, link_whatsapp=link_wa)

# --- BANNERS ---
@app.route('/admin/banner/agregar', methods=['POST'])
@login_requerido
def agregar_banner():
    banners = cargar_datos(BANNERS_JSON)
    f = request.files.get('imagen')
    if f:
        fn = secure_filename(f.filename)
        f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
        banners.append({
            "id": max([b['id'] for b in banners], default=0) + 1,
            "titulo": request.form.get('titulo'),
            "descripcion": request.form.get('descripcion'),
            "imagen": fn,
            "link": f"/?q={request.form.get('producto_id')}"
        })
        guardar_datos(BANNERS_JSON, banners)
    return redirect(url_for('admin'))

@app.route('/admin/banner/eliminar/<int:id>')
@login_requerido
def eliminar_banner(id):
    banners = [b for b in cargar_datos(BANNERS_JSON) if b['id'] != id]
    guardar_datos(BANNERS_JSON, banners)
    return redirect(url_for('admin'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)