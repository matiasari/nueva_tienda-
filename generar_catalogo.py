import os
import time
import hashlib
import base64
import mimetypes
from datetime import datetime
from html import escape
from playwright.sync_api import sync_playwright

URL_TIENDA = "http://127.0.0.1:5000"

CARPETA_IMAGENES = os.path.join(
    os.path.expanduser("~"),
    "Downloads",
    "bazar_guille_imagenes_catalogo"
)


def hash_url(url, indice=None):
    clave = url if indice is None else f"{url}|{indice}"
    return hashlib.md5(clave.encode("utf-8")).hexdigest()


def buscar_imagen_existente(url, indice):
    if not url:
        return None

    hashes = [hash_url(url), hash_url(url, indice)]
    extensiones = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"]

    for h in hashes:
        for ext in extensiones:
            ruta = os.path.join(CARPETA_IMAGENES, h + ext)
            if os.path.isfile(ruta) and os.path.getsize(ruta) > 0:
                return ruta

    if os.path.isdir(CARPETA_IMAGENES):
        for archivo in os.listdir(CARPETA_IMAGENES):
            base = os.path.splitext(archivo)[0]
            if base in hashes:
                ruta = os.path.join(CARPETA_IMAGENES, archivo)
                if os.path.isfile(ruta) and os.path.getsize(ruta) > 0:
                    return ruta

    return None


def extension_imagen(response, url):
    tipo = (response.headers.get("content-type") or "").split(";")[0].lower()
    mapa = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/avif": ".avif",
    }

    if tipo in mapa:
        return mapa[tipo]

    ext = os.path.splitext(url.split("?")[0])[1].lower()
    return ext if ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"] else ".jpg"


def obtener_o_descargar_imagen(request, url, indice):
    existente = buscar_imagen_existente(url, indice)

    if existente:
        return existente, False, None

    try:
        response = request.get(
            url,
            timeout=30000,
            fail_on_status_code=False
        )

        if not response.ok:
            return None, True, f"HTTP {response.status}"

        content_type = (response.headers.get("content-type") or "").lower()
        if "image" not in content_type:
            return None, True, "La respuesta no es una imagen"

        datos = response.body()
        if not datos:
            return None, True, "Archivo vacío"

        ruta = os.path.join(
            CARPETA_IMAGENES,
            hash_url(url) + extension_imagen(response, url)
        )

        with open(ruta, "wb") as f:
            f.write(datos)

        return ruta, True, None

    except Exception as e:
        return None, True, str(e)


def a_data_uri(ruta):
    if not ruta or not os.path.isfile(ruta):
        return None

    try:
        with open(ruta, "rb") as f:
            datos = f.read()

        if not datos:
            return None

        mime = mimetypes.guess_type(ruta)[0] or "image/jpeg"
        return "data:" + mime + ";base64," + base64.b64encode(datos).decode("ascii")

    except Exception:
        return None


def obtener_productos(page):
    return page.locator(
        "#productos .grid-productos .card"
    ).evaluate_all("""
        cards => cards.map(card => {
            const foto = card.querySelector("img.foto-principal");
            const nombre = card.querySelector("h3");
            const precio = card.querySelector(".precio");
            const categoria = card.closest(".categoria-bloque")
                ?.querySelector(".titulo-categoria");

            return {
                nombre: nombre ? nombre.innerText.trim() : "",
                precio: precio ? precio.innerText.trim() : "",
                categoria: categoria ? categoria.innerText.trim() : "",
                imagen: foto
                    ? (foto.currentSrc || foto.src ||
                       foto.getAttribute("data-src") || "")
                    : ""
            };
        })
    """)


def crear_html(productos):
    bloques = []
    categoria_actual = None
    tarjetas = []

    def cerrar():
        if categoria_actual is None:
            return ""
        return f"""
        <section class="categoria">
            <h2>{escape(categoria_actual)}</h2>
            <div class="grid">{''.join(tarjetas)}</div>
        </section>
        """

    for p in productos:
        categoria = p.get("categoria") or "Productos"

        if categoria != categoria_actual:
            if categoria_actual is not None:
                bloques.append(cerrar())
            categoria_actual = categoria
            tarjetas = []

        data = p.get("imagen_data_uri")

        if data:
            foto = f'<div class="foto"><img src="{data}" alt=""></div>'
        else:
            foto = '<div class="foto sin-foto">Sin foto</div>'

        tarjetas.append(f"""
        <article class="card">
            {foto}
            <h3>{escape(p.get("nombre", ""))}</h3>
            <div class="precio">{escape(p.get("precio", ""))}</div>
        </article>
        """)

    if categoria_actual is not None:
        bloques.append(cerrar())

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
@page {{ size:A4; margin:8mm; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:0; font-family:Arial,sans-serif; background:#fff; color:#222; }}
.categoria {{ break-inside:avoid; page-break-inside:avoid; margin-bottom:12px; }}
.categoria h2 {{ font-size:18px; margin:8px 0 10px; padding:5px 0; border-bottom:2px solid #eee; }}
.grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; width:100%; }}
.card {{ border:1px solid #eee; border-radius:8px; padding:8px; background:#fff; text-align:center; break-inside:avoid; page-break-inside:avoid; }}
.foto {{ width:100%; height:160px; display:flex; align-items:center; justify-content:center; margin-bottom:8px; overflow:hidden; }}
.foto img {{ display:block; width:100%; height:160px; object-fit:contain; }}
.sin-foto {{ border:1px dashed #ccc; color:#999; font-size:11px; }}
.card h3 {{ font-size:13px; line-height:1.2; margin:5px 0; }}
.precio {{ font-size:13px; margin:4px 0; font-weight:bold; }}
</style>
</head>
<body>{''.join(bloques)}</body>
</html>"""


def generar_pdf_desde_web():
    carpeta_descargas = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(carpeta_descargas, exist_ok=True)
    os.makedirs(CARPETA_IMAGENES, exist_ok=True)

    pdf_path = os.path.join(
        carpeta_descargas,
        f"catalogo_bazar_guille_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    )

    try:
        with sync_playwright() as p:
            print("======================================")
            print("      CATÁLOGO BAZAR GUILLE")
            print("======================================")
            print("")
            print("🌐 Abriendo Bazar Guille...")

            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            page = context.new_page()

            page.goto(
                URL_TIENDA,
                wait_until="domcontentloaded",
                timeout=30000
            )
            time.sleep(2)

            cantidad = page.locator(
                "#productos .grid-productos .card"
            ).count()

            print(f"🛒 Productos encontrados: {cantidad}")

            if cantidad == 0:
                print("❌ No se encontraron productos.")
                browser.close()
                return

            productos = obtener_productos(page)

            print("")
            print("📸 REVISANDO FOTOS...")
            print(f"📁 {CARPETA_IMAGENES}")
            print("")

            reutilizadas = 0
            nuevas = 0
            problemas = 0

            for i, producto in enumerate(productos, 1):
                url = producto.get("imagen", "").strip()

                if not url:
                    producto["imagen_data_uri"] = None
                    problemas += 1
                    print(f"   {i}/{cantidad} ❌ Sin URL: {producto.get('nombre','')}")
                    continue

                ruta, descargada, error = obtener_o_descargar_imagen(
                    context.request,
                    url,
                    i
                )

                data = a_data_uri(ruta)
                producto["imagen_data_uri"] = data

                if data:
                    if descargada:
                        nuevas += 1
                        print(f"   {i}/{cantidad} ⬇️ Descargada: {producto.get('nombre','')}")
                    else:
                        reutilizadas += 1
                        print(f"   {i}/{cantidad} ♻️ Ya estaba: {producto.get('nombre','')}")
                else:
                    problemas += 1
                    print(f"   {i}/{cantidad} ❌ Problema: {producto.get('nombre','')} - {error or 'archivo inválido'}")

            print("")
            print("======================================")
            print("📸 REVISIÓN TERMINADA")
            print("======================================")
            print(f"♻️ Reutilizadas: {reutilizadas}")
            print(f"⬇️ Descargadas: {nuevas}")
            print(f"❌ Con problemas: {problemas}")
            print("")

            print("🎨 Armando catálogo con las fotos LOCALES...")

            html = crear_html(productos)

            html_path = os.path.join(
                carpeta_descargas,
                "bazar_guille_catalogo_temporal.html"
            )

            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)

            # Desde acá el PDF NO depende de ImgBB.
            # Todas las fotos ya están incrustadas dentro del HTML.
            pdf_page = context.new_page()

            pdf_page.goto(
                "file:///" + html_path.replace("\\", "/"),
                wait_until="load",
                timeout=30000
            )

            pdf_page.emulate_media(media="print")

            pdf_page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
                prefer_css_page_size=False,
                display_header_footer=False,
                margin={
                    "top": "8mm",
                    "bottom": "8mm",
                    "left": "8mm",
                    "right": "8mm"
                }
            )

            browser.close()

            print("")
            print("======================================")
            print("✅ ¡CATÁLOGO GENERADO!")
            print("======================================")
            print(f"📄 {pdf_path}")
            print(f"🛍️ Productos: {cantidad}")
            print(f"♻️ Fotos reutilizadas: {reutilizadas}")
            print(f"⬇️ Fotos nuevas: {nuevas}")
            print(f"❌ Fotos con problemas: {problemas}")
            print("")
            print("💡 Las fotos quedan guardadas y se reutilizan en el próximo PDF.")

    except Exception as e:
        print("")
        print("❌ ERROR GENERANDO EL PDF")
        print("--------------------------------------")
        print(f"{type(e).__name__}: {e}")
        print("--------------------------------------")
        print("")
        print("💡 Verificá que Flask esté ejecutándose:")
        print("   python app.py")
        print("")


if __name__ == "__main__":
    generar_pdf_desde_web()
