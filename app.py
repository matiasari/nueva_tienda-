import os
import json
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.secret_key = 'bazar_guille_key_secret'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Archivos de datos
PRODUCTOS_JSON = 'productos.json'
BANNERS_JSON = 'banners.json'

# --- FUNCIONES DE PERSISTENCIA ---
def cargar_datos(archivo):
    if not os.path.exists(archivo):
        # Si no existe, devuelve una lista vacía
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

# --- RUTAS PÚBLICAS ---

@app.route('/')
def index():
    productos = cargar_datos(PRODUCTOS_JSON)
    banners = cargar_datos(BANNERS_JSON)
    
    cat = request.args.get('cat')
    q = request.args.get('q')
    
    # Filtrado
    productos_mostrar = productos
    
    # 1. Filtrar por categoría
    if cat and cat != "Todos":
        productos_mostrar = [p for p in productos_mostrar if p.get('categoria') == cat]
    
    # 2. Filtrar por búsqueda (Nombre o ID exacto)
    if q:
        q_lower = q.lower()
        productos_mostrar = [
            p for p in productos_mostrar 
            if q_lower in p.get('nombre', '').lower() or str(p.get('id')) == q_lower
        ]
        
    # --- LIMPIEZA DE CARRITO (FANTASMAS) ---
    carrito = session.get('carrito', [])
    ids_existentes = [str(p['id']) for p in productos]
    
    # Solo dejamos en el carrito los IDs que realmente están en el JSON
    carrito_limpio = [p_id for p_id in carrito if str(p_id) in ids_existentes]
    
    if len(carrito) != len(carrito_limpio):
        session['carrito'] = carrito_limpio
        session.modified = True

    return render_template('tienda.html', 
                           productos=productos_mostrar, 
                           banners=banners, 
                           carrito_total=len(carrito_limpio))
    
    
    
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

# --- PANEL DE ADMINISTRACIÓN ---

@app.route('/admin')
@login_requerido
def admin():
    productos = cargar_datos(PRODUCTOS_JSON)
    banners = cargar_datos(BANNERS_JSON)
    # Agregamos la nueva categoría aquí:
    categorias = ["Cocina", "Baño", "Decoración", "Electrónica", "Otros"]
    return render_template('admin.html', productos=productos, banners=banners, categorias=categorias)



@app.route('/admin/producto/agregar', methods=['POST'])
@login_requerido
def agregar_producto():
    productos = cargar_datos(PRODUCTOS_JSON)
    nombre = request.form.get('nombre')
    precio = request.form.get('precio')
    categoria = request.form.get('categoria')
    stock = request.form.get('stock')
    
    # Manejo de múltiples imágenes
    imagenes_subidas = request.files.getlist('imagenes_extras')
    nombres_fotos = []

    for img in imagenes_subidas:
        if img.filename != '':
            filename = secure_filename(img.filename)
            img.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            nombres_fotos.append(filename)

    # La primera foto será la principal, el resto van a la lista 'imagenes_extras'
    foto_principal = nombres_fotos[0] if nombres_fotos else ""
    fotos_adicionales = nombres_fotos[1:] if len(nombres_fotos) > 1 else []

    nuevo_id = max([p['id'] for p in productos], default=0) + 1
    
    nuevo_p = {
        "id": nuevo_id,
        "nombre": nombre,
        "precio": float(precio),
        "categoria": categoria,
        "stock": int(stock) if stock else 0,
        "imagen": foto_principal,
        "imagenes_extras": fotos_adicionales  # Nueva clave en tu JSON
    }
    
    productos.append(nuevo_p)
    guardar_datos(PRODUCTOS_JSON, productos)
    return redirect(url_for('admin'))


@app.route('/admin/producto/eliminar/<int:id>')
@login_requerido
def eliminar_producto(id):
    productos = cargar_datos(PRODUCTOS_JSON)
    productos = [p for p in productos if p['id'] != id]
    guardar_datos(PRODUCTOS_JSON, productos)
    return redirect(url_for('admin'))

@app.route('/admin/producto/editar', methods=['POST'])
def editar_producto():
    p_id = request.form.get('id')
    nombre = request.form.get('nombre')
    precio = float(request.form.get('precio'))
    categoria = request.form.get('categoria')
    stock = int(request.form.get('stock'))
    
    productos = cargar_datos(PRODUCTOS_JSON)
    for p in productos:
        if str(p['id']) == str(p_id):
            p['nombre'] = nombre
            p['precio'] = precio
            p['categoria'] = categoria
            p['stock'] = stock
            # Si se sube una imagen nueva, la cambiamos. Si no, queda la anterior.
            if 'imagen' in request.files and request.files['imagen'].filename != '':
                archivo = request.files['imagen']
                filename = archivo.filename
                archivo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                p['imagen'] = filename
            break
            
    with open(PRODUCTOS_JSON, 'w', encoding='utf-8') as f:
        json.dump(productos, f, indent=4)
        
    return redirect(url_for('admin'))

# --- SISTEMA DE CARRITO ---

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
    todos_los_productos = cargar_datos(PRODUCTOS_JSON)
    
    conteo = {}
    for p_id in ids_en_carrito:
        conteo[str(p_id)] = conteo.get(str(p_id), 0) + 1
    
    carrito_render = []
    total_productos = 0
    for p_id, cantidad in conteo.items():
        p = next((prod for prod in todos_los_productos if str(prod['id']) == p_id), None)
        if p:
            subtotal = p['precio'] * cantidad
            total_productos += subtotal
            item = p.copy()
            item['cantidad'] = cantidad
            carrito_render.append(item)
    
    # --- LÓGICA DE ENVÍO ---
    costo_envio = session.get('envio', 0)
    zona_envio = session.get('zona_envio', 'No seleccionada')
    total_final = total_productos + costo_envio
    
    # Preparar mensaje de WhatsApp
    mensaje = "Hola Bazar Guille! Mi pedido:\n"
    for item in carrito_render:
        mensaje += f"- {item['nombre']} x{item['cantidad']} (${item['precio']})\n"
    
    if costo_envio > 0:
        mensaje += f"\nEnvío ({zona_envio}): ${costo_envio}"
    
    mensaje += f"\n*Total Final: ${total_final}*"
    
    mensaje_limpio = mensaje.replace(' ', '%20').replace('\n', '%0A')
    link_wa = f"https://wa.me/5491149899616?text={mensaje_limpio}"

    return render_template('carrito.html', 
                           carrito=carrito_render, 
                           total=total_productos, 
                           envio=costo_envio,
                           zona=zona_envio,
                           total_final=total_final,
                           link_whatsapp=link_wa)
    

@app.route('/aumentar/<int:id>')
def aumentar(id):
    carrito = session.get('carrito', [])
    carrito.append(str(id))
    session['carrito'] = carrito
    session.modified = True
    return redirect(url_for('mostrar_carrito'))

@app.route('/disminuir/<int:id>')
def disminuir(id):
    carrito = session.get('carrito', [])
    if str(id) in carrito:
        carrito.remove(str(id))
        session['carrito'] = carrito
        session.modified = True
    return redirect(url_for('mostrar_carrito'))

@app.route('/carrito/eliminar/<int:id>')
def eliminar_del_carrito(id):
    carrito = session.get('carrito', [])
    nuevo_carrito = [p_id for p_id in carrito if str(p_id) != str(id)]
    session['carrito'] = nuevo_carrito
    session.modified = True
    return redirect(url_for('mostrar_carrito'))

@app.route('/carrito/vaciar')
def vaciar_carrito():
    session.pop('carrito', None)
    return redirect(url_for('index'))

@app.route('/admin/banner/agregar', methods=['POST'])
def agregar_banner():
    banners = cargar_datos(BANNERS_JSON)
    titulo = request.form.get('titulo')
    descripcion = request.form.get('descripcion')
    
    prod_id = request.form.get('producto_id')
# Si hay ID, armamos el link. Si no, lo dejamos vacío o directo a productos
    enlace = f"/?q={prod_id}" if prod_id else ""

    if 'imagen' in request.files:
        archivo = request.files['imagen']
        if archivo.filename != '':
            filename = archivo.filename
            archivo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            nuevo_id = 1 if not banners else max([b['id'] for b in banners]) + 1
            nuevo_b = {
                "id": nuevo_id,
                "titulo": titulo,
                "descripcion": descripcion,
                "imagen": filename,
                "link": enlace  # Acá ya se guarda como /?q=9
            }
            
            banners.append(nuevo_b)
            with open(BANNERS_JSON, 'w', encoding='utf-8') as f:
                json.dump(banners, f, indent=4)
                
    return redirect(url_for('admin'))
    
@app.route('/admin/banner/eliminar/<int:id>')
@login_requerido
def eliminar_banner(id):
    banners = cargar_datos(BANNERS_JSON)
    banners = [b for b in banners if b['id'] != id]
    guardar_datos(BANNERS_JSON, banners)
    return redirect(url_for('admin'))


@app.route('/calcular_envio', methods=['POST'])
def calcular_envio():
    zona = request.form.get('zona')
    
    # Definí acá tus costos por zona
    tarifas = {
        "CABA": 10000,
        "Zona Norte": 15000,
        "Zona Sur": 7000,
        "Zona Oeste": 10000,
        "Retiro en local": 0
    }
    
    costo = tarifas.get(zona, 0)
    
    # Guardamos en la sesión
    session['envio'] = costo
    session['zona_envio'] = zona
    session.modified = True
    
    return redirect(url_for('mostrar_carrito'))


def formato_pesos(valor):
    try:
        return f"${int(valor):,}".replace(",", ".")
    except:
        return "$0"

app.jinja_env.filters['pesos'] = formato_pesos

import pandas as pd

@app.route('/admin/importar_excel', methods=['POST'])
@login_requerido
def importar_excel():
    if 'archivo_excel' not in request.files:
        return redirect(url_for('admin'))
    
    file = request.files['archivo_excel']
    if file.filename == '':
        return redirect(url_for('admin'))

    if file:
        # Leemos el Excel
        df = pd.read_excel(file)
        productos = cargar_datos(PRODUCTOS_JSON)
        
        # Obtenemos el último ID para no repetir
        nuevo_id = max([p['id'] for p in productos], default=0) + 1

        for index, row in df.iterrows():
            nuevo_p = {
                "id": nuevo_id,
                "nombre": str(row['Nombre']),
                "precio": float(row['Precio']),
                "categoria": str(row['Categoría']),
                "stock": int(row['Stock']) if 'Stock' in row else 0,
                "imagen": "default.jpg", # Foto temporal
                "imagenes_extras": []
            }
            productos.append(nuevo_p)
            nuevo_id += 1

        guardar_datos(PRODUCTOS_JSON, productos)
        return redirect(url_for('admin'))
    
from flask import send_file
import io

@app.route('/admin/descargar_plantilla')
@login_requerido
def descargar_plantilla():
    # Creamos un DataFrame de ejemplo con las columnas exactas
    df = pd.DataFrame(columns=['Nombre', 'Precio', 'Categoría', 'Stock'])
    
    # Agregamos una fila de ejemplo (opcional, para que veas cómo se llena)
    df.loc[0] = ['Ejemplo Producto', 1500.50, 'Cocina', 10]
    
    # Guardamos el Excel en memoria para no crear archivos basura en el servidor
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Productos')
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='plantilla_bazar_guille.xlsx'
    )    
    
    

if __name__ == '__main__':
    # Render asigna un puerto dinámico, lo capturamos con os.environ
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)