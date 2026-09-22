import os
import requests
from sqlalchemy import create_engine, text

# 1. Conexión a la base de datos PostgreSQL de Render
URL_DATABASE = "postgresql://guille_admin:7nHE9WVezwoXS0RsDUiMrNkogSSX3FAW@dpg-d8sjeme7r5hc73fjftrg-a.oregon-postgres.render.com/bazarguille_db"
engine = create_engine(URL_DATABASE)

# 2. Carpeta de destino
CARPETA_DESTINO = "fotos_descargadas"
os.makedirs(CARPETA_DESTINO, exist_ok=True)

# Encabezados para imitar un navegador y evitar bloqueos de ImgBB
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def descargar_imagen(url, nombre_archivo):
    if not url or not str(url).startswith('http'):
        return
    
    ruta_completa = os.path.join(CARPETA_DESTINO, nombre_archivo)
    
    # Si ya la descargaste anteriormente, no la vuelve a bajar
    if os.path.exists(ruta_completa):
        print(f"⏩ Ya existe: {nombre_archivo}")
        return

    try:
        # Aumentamos timeout a 30 segundos
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            with open(ruta_completa, 'wb') as f:
                f.write(response.content)
            print(f"✅ Descargada: {nombre_archivo}")
        else:
            print(f"⚠️ Error HTTP {response.status_code} en: {url}")
    except Exception as e:
        print(f"❌ No se pudo descargar {nombre_archivo}: {e}")

# 3. Consulta y descarga continua
print("🚀 Iniciando descarga masiva de imágenes...")

try:
    with engine.connect() as conn:
        query = text("SELECT id, nombre, imagen, imagenes_extras FROM articulos ORDER BY id ASC")
        resultado = conn.execute(query)
        
        for row in resultado:
            try:
                prod_id = row.id
                # Sanitizar nombre para evitar errores de caracteres inválidos en Windows
                prod_nombre = "".join([c if c.isalnum() else "_" for c in str(row.nombre)])[:40]
                
                # Foto principal
                if row.imagen:
                    ext = str(row.imagen).split('.')[-1].split('?')[0].lower()
                    if len(ext) > 4 or not ext: ext = "jpg"
                    nombre_foto = f"{prod_id}_{prod_nombre}_principal.{ext}"
                    descargar_imagen(row.imagen, nombre_foto)
                    
                # Fotos extras
                if row.imagenes_extras:
                    extras = [u.strip() for u in str(row.imagenes_extras).split(',') if u.strip()]
                    for idx, url_extra in enumerate(extras, start=1):
                        ext = url_extra.split('.')[-1].split('?')[0].lower()
                        if len(ext) > 4 or not ext: ext = "jpg"
                        nombre_foto_extra = f"{prod_id}_{prod_nombre}_extra_{idx}.{ext}"
                        descargar_imagen(url_extra, nombre_foto_extra)
            except Exception as row_err:
                print(f"⚠️ Error procesando artículo ID {row.id}: {row_err}")
                continue

    print("\n🎉 ¡Proceso finalizado! Revisa la carpeta 'fotos_descargadas'.")

except Exception as db_err:
    print(f"\n❌ Error de conexión a la base de datos: {db_err}")