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
    if cat and cat != "Todos":
        productos_mostrar = [p for p in productos_mostrar if p.get('categoria') == cat]
    
    if q:
        productos_mostrar = [p for p in productos_mostrar if q.lower() in p.get('nombre', '').lower()]
        
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
    categorias = ["Cocina", "Baño", "Decoración", "Otros"]
    return render_template('admin.html', productos=productos, banners=banners, categorias=categorias)

@app.route('/admin/producto/agregar', methods=['POST'])
@login_requerido
def agregar_producto():
    productos = cargar_datos(PRODUCTOS_JSON)
    nombre = request.form.get('nombre')
    precio = request.form.get('precio')
    categoria = request.form.get('categoria')
    stock = request.form.get('stock')
    imagen = request.files.get('imagen')
    
    nombre_img = ""
    if imagen:
        nombre_img = secure_filename(imagen.filename)
        imagen.save(os.path.join(app.config['UPLOAD_FOLDER'], nombre_img))
    
    # Generar ID nuevo
    nuevo_id = max([p['id'] for p in productos], default=0) + 1
    
    nuevo_p = {
        "id": nuevo_id,
        "nombre": nombre,
        "precio": float(precio),
        "categoria": categoria,
        "stock": int(stock) if stock else 0,
        "imagen": nombre_img
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
@login_requerido
def agregar_banner():
    banners = cargar_datos(BANNERS_JSON)
    titulo = request.form.get('titulo')
    descripcion = request.form.get('descripcion')
    imagen = request.files.get('imagen')
    
    if imagen:
        nombre_img = secure_filename(imagen.filename)
        imagen.save(os.path.join(app.config['UPLOAD_FOLDER'], nombre_img))
        
        nuevo_id = max([b['id'] for b in banners], default=0) + 1
        nuevo_b = {
            "id": nuevo_id,
            "imagen": nombre_img,
            "titulo": titulo,
            "descripcion": descripcion
        }
        banners.append(nuevo_b)
        guardar_datos(BANNERS_JSON, banners)
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

if __name__ == '__main__':
    # Render asigna un puerto dinámico, lo capturamos con os.environ
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)