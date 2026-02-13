import os
import json
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from werkzeug.utils import secure_filename
from functools import wraps
import io

app = Flask(__name__)
app.secret_key = 'bazar_guille_key_secret'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Archivos de datos
PRODUCTOS_JSON = 'productos.json'
BANNERS_JSON = 'banners.json'
API_KEY_SINCRO = "Guille_Linux_Sincro_2026"  # Clave para tu programa de escritorio

# --- FUNCIONES DE PERSISTENCIA ---
def cargar_datos(archivo):
    if not os.path.exists(archivo):
        return []
    with open(archivo, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return []

def guardar_datos(archivo, datos):
    with open(archivo, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)

# Asegurar carpeta de fotos
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- SEGURIDAD ---
def login_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- FILTROS JINJA ---
def formato_pesos(valor):
    try:
        return f"${int(valor):,}".replace(",", ".")
    except:
        return "$0"

app.jinja_env.filters['pesos'] = formato_pesos

# --- API DE SINCRONIZACIÓN (Para tu Linux) ---
@app.route('/api/actualizar_stock', methods=['POST'])
def api_actualizar_stock():
    key = request.headers.get('X-API-KEY')
    if key != API_KEY_SINCRO:
        return jsonify({"status": "error", "message": "No autorizado"}), 401
    datos_nuevos = request.get_json()
    if datos_nuevos:
        guardar_datos(PRODUCTOS_JSON, datos_nuevos)
        return jsonify({"status": "success", "message": "Stock actualizado"}), 200
    return jsonify({"status": "error", "message": "Sin datos"}), 400

# --- RUTAS PÚBLICAS ---
@app.route('/')
def index():
    productos = cargar_datos(PRODUCTOS_JSON)
    banners = cargar_datos(BANNERS_JSON)
    cat = request.args.get('cat')
    q = request.args.get('q')
    
    productos_mostrar = productos
    if cat and cat != "Todos":
        productos_mostrar = [p for p in productos_mostrar if p.get('categoria') == cat]
    if q:
        q_lower = q.lower()
        productos_mostrar = [p for p in productos_mostrar if q_lower in p.get('nombre', '').lower() or str(p.get('id')) == q_lower]
        
    carrito = session.get('carrito', [])
    return render_template('tienda.html', productos=productos_mostrar, banners=banners, carrito_total=len(carrito))

# --- ADMINISTRACIÓN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('usuario') == 'admin' and request.form.get('password') == 'guille123':
            session['admin'] = True
            return redirect(url_for('admin'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/admin')
@login_requerido
def admin():
    productos = cargar_datos(PRODUCTOS_JSON)
    # Agregamos esto para "curar" los productos viejos al cargar la lista
    for p in productos:
        if 'imagenes_extras' not in p:
            p['imagenes_extras'] = []
            
    banners = cargar_datos(BANNERS_JSON)
    categorias = ["Cocina", "Baño", "Decoración", "Electrónica", "Otros"]
    return render_template('admin.html', productos=productos, banners=banners, categorias=categorias)

@app.route('/admin/producto/agregar', methods=['POST'])
@login_requerido
def agregar_producto():
    productos = cargar_datos(PRODUCTOS_JSON)
    imagenes_subidas = request.files.getlist('imagenes_extras')
    nombres_fotos = []
    for img in imagenes_subidas:
        if img.filename != '':
            filename = secure_filename(img.filename)
            img.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            nombres_fotos.append(filename)

    nuevo_id = max([p['id'] for p in productos], default=0) + 1
    nuevo_p = {
        "id": nuevo_id,
        "nombre": request.form.get('nombre'),
        "precio": float(request.form.get('precio')),
        "categoria": request.form.get('categoria'),
        "stock": int(request.form.get('stock') or 0),
        "imagen": nombres_fotos[0] if nombres_fotos else "default.jpg",
        "imagenes_extras": nombres_fotos[1:] if len(nombres_fotos) > 1 else []
    }
    productos.append(nuevo_p)
    guardar_datos(PRODUCTOS_JSON, productos)
    return redirect(url_for('admin'))

@app.route('/admin/producto/editar', methods=['POST'])
@login_requerido
def editar_producto():
    p_id = request.form.get('id')
    productos = cargar_datos(PRODUCTOS_JSON)
    
    for p in productos:
        if str(p['id']) == str(p_id):
            p['nombre'] = request.form.get('nombre')
            p['precio'] = float(request.form.get('precio'))
            p['categoria'] = request.form.get('categoria')
            p['stock'] = int(request.form.get('stock'))
            
            # --- ACÁ ESTÁ EL CAMBIO IMPORTANTE ---
            # 1. Obtenemos el nuevo orden que mandaste desde el admin (Drag & Drop)
            fotos_ordenadas = request.form.getlist('orden_fotos[]')
            
            # 2. Procesamos si subiste fotos nuevas desde el botón "Añadir más fotos"
            fotos_nuevas = request.files.getlist('fotos_extras')
            for foto in fotos_nuevas:
                if foto and foto.filename != '':
                    fname = secure_filename(foto.filename)
                    foto.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                    # Las agregamos al final de la lista actual
                    fotos_ordenadas.append(fname)
            
            # 3. Actualizamos el producto con el orden final
            if fotos_ordenadas:
                p['imagen'] = fotos_ordenadas[0]  # La primera es la principal
                p['imagenes_extras'] = fotos_ordenadas[1:]  # El resto a la galería
            # -------------------------------------
            break
            
    guardar_datos(PRODUCTOS_JSON, productos)
    return redirect(url_for('admin'))

@app.route('/admin/producto/eliminar/<int:id>')
@login_requerido
def eliminar_producto(id):
    productos = cargar_datos(PRODUCTOS_JSON)
    productos = [p for p in productos if p['id'] != id]
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
                "id": nuevo_id,
                "nombre": str(row['Nombre']),
                "precio": float(row['Precio']),
                "categoria": str(row['Categoría']),
                "stock": int(row.get('Stock', 0)),
                "imagen": "default.jpg",
                "imagenes_extras": []
            })
            nuevo_id += 1
        guardar_datos(PRODUCTOS_JSON, productos)
    return redirect(url_for('admin'))

@app.route('/admin/descargar_plantilla')
@login_requerido
def descargar_plantilla():
    df = pd.DataFrame(columns=['Nombre', 'Precio', 'Categoría', 'Stock'])
    df.loc[0] = ['Ejemplo Producto', 1500.50, 'Cocina', 10]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.ms-excel', as_attachment=True, download_name='plantilla_bazar.xlsx')

# --- CARRITO ---
@app.route('/agregar_al_carrito', methods=['POST'])
def agregar_al_carrito():
    p_id = request.form.get('id')
    carrito = session.get('carrito', [])
    carrito.append(str(p_id))
    session['carrito'] = carrito
    session.modified = True
    return redirect(url_for('index'))

@app.route('/carrito')
def mostrar_carrito():
    ids_en_carrito = session.get('carrito', [])
    todos = cargar_datos(PRODUCTOS_JSON)
    carrito_render = []
    total_productos = 0
    conteo = {p_id: ids_en_carrito.count(p_id) for p_id in set(ids_en_carrito)}
    
    for p_id, cantidad in conteo.items():
        p = next((prod for prod in todos if str(prod['id']) == p_id), None)
        if p:
            sub = p['precio'] * cantidad
            total_productos += sub
            item = p.copy()
            item['cantidad'] = cantidad
            carrito_render.append(item)
            
    envio = session.get('envio', 0)
    total_final = total_productos + envio
    
    # WhatsApp Link
    msj = "Hola Bazar Guille! Pedido:\n" + "\n".join([f"- {i['nombre']} x{i['cantidad']}" for i in carrito_render])
    msj += f"\nTotal: ${total_final}"
    link_wa = f"https://wa.me/5491149899616?text={msj.replace(' ', '%20')}"
    
    return render_template('carrito.html', carrito=carrito_render, total=total_productos, envio=envio, total_final=total_final, link_whatsapp=link_wa)

@app.route('/calcular_envio', methods=['POST'])
def calcular_envio():
    zona = request.form.get('zona')
    tarifas = {"CABA": 10000, "Zona Norte": 15000, "Zona Sur": 7000, "Zona Oeste": 10000, "Retiro en local": 0}
    session['envio'] = tarifas.get(zona, 0)
    session['zona_envio'] = zona
    return redirect(url_for('mostrar_carrito'))

@app.route('/disminuir/<int:id>')
def disminuir(id):
    carrito = session.get('carrito', [])
    if str(id) in carrito:
        carrito.remove(str(id))
        session['carrito'] = carrito
        session.modified = True
    return redirect(url_for('mostrar_carrito'))

@app.route('/aumentar/<int:id>')
def aumentar(id):
    carrito = session.get('carrito', [])
    carrito.append(str(id))
    session['carrito'] = carrito
    session.modified = True
    return redirect(url_for('mostrar_carrito'))

@app.route('/carrito/vaciar')
def vaciar_carrito():
    session.pop('carrito', None)
    return redirect(url_for('index'))

# --- BANNERS ---
@app.route('/admin/banner/agregar', methods=['POST'])
@login_requerido
def agregar_banner():
    banners = cargar_datos(BANNERS_JSON)
    archivo = request.files.get('imagen')
    if archivo and archivo.filename != '':
        fname = secure_filename(archivo.filename)
        archivo.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        banners.append({
            "id": max([b['id'] for b in banners], default=0) + 1,
            "titulo": request.form.get('titulo'),
            "descripcion": request.form.get('descripcion'),
            "imagen": fname,
            "link": f"/?q={request.form.get('producto_id')}" if request.form.get('producto_id') else ""
        })
        guardar_datos(BANNERS_JSON, banners)
    return redirect(url_for('admin'))

@app.route('/admin/banner/eliminar/<int:id>')
@login_requerido
def eliminar_banner(id):
    banners = cargar_datos(BANNERS_JSON)
    banners = [b for b in banners if b['id'] != id]
    guardar_datos(BANNERS_JSON, banners)
    return redirect(url_for('admin'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)