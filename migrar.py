import json
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# URL Externa de la base de datos de Render que me pasaste
URL_RENDER = "postgresql://guille_admin:7nHE9WVezwoXS0RsDUiMrNkogSSX3FAW@dpg-d8sjeme7r5hc73fjftrg-a.oregon-postgres.render.com/bazarguille_db"

app.config['SQLALCHEMY_DATABASE_URI'] = URL_RENDER
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Estructura adaptada idéntica a los datos de tu JSON
class Articulo(db.Model):
    __tablename__ = 'articulos'
    id = db.Column(db.Integer, primary_key=True) # Mantiene el ID original del JSON
    nombre = db.Column(db.String(250), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    categoria = db.Column(db.String(100), nullable=True)
    subcategoria = db.Column(db.String(100), nullable=True, default="")
    stock = db.Column(db.Integer, default=0)
    imagen = db.Column(db.String(500), nullable=True)
    # Las listas de imágenes extras las guardamos como texto plano separado por comas para compatibilidad directa
    imagenes_extras = db.Column(db.Text, nullable=True, default="")

with app.app_context():
    print("🔄 Conectando a Render y preparando las tablas...")
    db.create_all() 
    
    # PONÉ ACÁ EL NOMBRE REAL DE TU ARCHIVO JSON (ej: 'productos.json' o 'articulos.json')
    archivo_json = 'productos.json' 
    
    if os.path.exists(archivo_json):
        with open(archivo_json, 'r', encoding='utf-8') as f:
            productos = json.load(f)
        
        print(f"📦 Se encontraron {len(productos)} registros en el archivo JSON. Iniciando migración...")
        
        ids_cargados = set()
        contador = 0
        
        for p in productos:
            prod_id = p.get('id')
            
            # Como en tu JSON hay IDs repetidos (ej: el 32, 39, 44 figuran dos veces), omitimos duplicados para que no falle la base de datos
            if prod_id in ids_cargados:
                continue
                
            # Procesar el campo de imágenes extras (si viene como lista, unirla por comas)
            img_extras = p.get('imagenes_extras', '')
            if isinstance(img_extras, list):
                img_extras = ",".join(img_extras)
            
            nuevo_art = Articulo(
                id=prod_id,
                nombre=p.get('nombre', 'Sin nombre'),
                precio=float(p.get('precio', 0.0)),
                categoria=p.get('categoria'),
                subcategoria=p.get('subcategoria', ''),
                stock=int(p.get('stock', 0)),
                imagen=p.get('imagen', ''),
                imagenes_extras=img_extras
            )
            
            db.session.add(nuevo_art)
            ids_cargados.add(prod_id)
            contador += 1
        
        db.session.commit()
        print(f"🚀 ¡Éxito total! Se subieron {contador} productos únicos a tu base de datos en Render.")
    else:
        print(f"❌ Error: No se encontró el archivo '{archivo_json}' en esta carpeta. Verificá el nombre.")