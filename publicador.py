import os
os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = r'C:\Program Files\Git\bin\git.exe'
import json
import shutil
from tkinter import *
from tkinter import filedialog, messagebox
from git import Repo

# --- CONFIGURACIÓN ---
# Cambiá esta ruta por la de tu carpeta del proyecto
RUTA_WEB = r"C:\Users\administracion\Desktop\pagina web\tienda_bazar"
PATH_JSON = os.path.join(RUTA_WEB, "productos.json")
PATH_UPLOADS = os.path.join(RUTA_WEB, "static", "uploads")

def seleccionar_imagen():
    archivo = filedialog.askopenfilename(filetypes=[("Imágenes", "*.jpg *.png *.jpeg *.webp")])
    entry_img.delete(0, END)
    entry_img.insert(0, archivo)

def publicar():
    nombre = entry_nombre.get()
    precio = entry_precio.get()
    categoria = var_cat.get()
    stock = entry_stock.get()
    img_origen = entry_img.get()

    if not (nombre and precio and img_origen):
        messagebox.showwarning("Faltan datos", "Por favor, completá nombre, precio e imagen.")
        return

    try:
        # 1. Mover imagen a la carpeta static/uploads
        nombre_archivo = os.path.basename(img_origen)
        img_destino = os.path.join(PATH_UPLOADS, nombre_archivo)
        shutil.copy(img_origen, img_destino)

        # 2. Actualizar JSON
        with open(PATH_JSON, 'r', encoding='utf-8') as f:
            productos = json.load(f)

        nuevo_id = max([p['id'] for p in productos]) + 1 if productos else 1
        nuevo_p = {
            "id": nuevo_id,
            "nombre": nombre,
            "precio": float(precio),
            "categoria": categoria,
            "stock": int(stock),
            "imagen": nombre_archivo
        }
        productos.append(nuevo_p)

        with open(PATH_JSON, 'w', encoding='utf-8') as f:
            json.dump(productos, f, indent=4)

        # 3. Git Push Automático
        repo = Repo(RUTA_WEB)
        repo.git.add(A=True)
        repo.git.commit('-m', f"Nuevo producto: {nombre} (Carga rápida)")
        origin = repo.remote(name='origin')
        origin.push()

        messagebox.showinfo("¡Éxito!", f"Producto '{nombre}' subido y publicado correctamente.")
        
        # Limpiar campos
        entry_nombre.delete(0, END)
        entry_precio.delete(0, END)
        entry_stock.delete(0, END)
        entry_img.delete(0, END)

    except Exception as e:
        messagebox.showerror("Error", f"Algo falló: {e}")

# --- INTERFAZ GRÁFICA ---
root = Tk()
root.title("Carga Rápida - Bazar Guille")
root.geometry("400x500")
root.config(padx=20, pady=20)

Label(root, text="Panel de Carga para la Tienda", font=("Arial", 14, "bold")).pack(pady=10)

Label(root, text="Nombre del Producto:").pack(anchor=W)
entry_nombre = Entry(root, width=50)
entry_nombre.pack(pady=5)

Label(root, text="Precio:").pack(anchor=W)
entry_precio = Entry(root, width=50)
entry_precio.pack(pady=5)

Label(root, text="Categoría:").pack(anchor=W)
var_cat = StringVar(value="Cocina")
OptionMenu(root, var_cat, "Cocina", "Baño", "Decoración", "Electrónica", "Limpieza").pack(fill=X, pady=5)

Label(root, text="Stock:").pack(anchor=W)
entry_stock = Entry(root, width=50)
entry_stock.insert(0, "1")
entry_stock.pack(pady=5)

Label(root, text="Imagen:").pack(anchor=W)
entry_img = Entry(root, width=50)
entry_img.pack(pady=5)
Button(root, text="Buscar Imagen 📂", command=seleccionar_imagen).pack(pady=5)

Button(root, text="🚀 PUBLICAR EN LA WEB", bg="#25d366", fg="white", font=("Arial", 12, "bold"), 
       height=2, command=publicar).pack(fill=X, pady=20)

root.mainloop()