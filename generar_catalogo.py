import os
import time
from datetime import datetime
from playwright.sync_api import sync_playwright


URL_TIENDA = "http://127.0.0.1:5000"


def generar_pdf_desde_web():

    carpeta_descargas = os.path.join(
        os.path.expanduser("~"),
        "Downloads"
    )

    os.makedirs(carpeta_descargas, exist_ok=True)

    nombre_pdf = (
        f"catalogo_bazar_guille_"
        f"{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    )

    pdf_path = os.path.join(
        carpeta_descargas,
        nombre_pdf
    )

    try:

        # ==================================================
        # PLAYWRIGHT
        # ==================================================

        with sync_playwright() as p:

            print("🌐 Abriendo navegador...")

            browser = p.chromium.launch(
                headless=True
            )

            context = browser.new_context(
                viewport={
                    "width": 1280,
                    "height": 900
                }
            )

            page = context.new_page()

            # ==================================================
            # ABRIR TIENDA
            # ==================================================

            print("🛍️ Cargando Bazar Guille...")

            page.goto(
                URL_TIENDA,
                wait_until="domcontentloaded",
                timeout=30000
            )

            print("✅ Página HTML cargada")

            print("⏳ Esperando que cargue la página...")

            time.sleep(3)

            # ==================================================
            # BUSCAR PRODUCTOS
            # ==================================================

            cantidad_productos = page.locator(
                "#productos .grid-productos .card"
            ).count()

            print(
                f"🛒 Productos encontrados: "
                f"{cantidad_productos}"
            )

            if cantidad_productos == 0:

                print("")
                print("❌ No se encontraron productos.")
                print("")
                print(
                    "El generador buscó:"
                )
                print(
                    "   #productos .grid-productos .card"
                )
                print("")

                browser.close()
                return

            # ==================================================
            # PREPARAR IMÁGENES
            # ==================================================

            print("📸 Preparando imágenes...")

            page.evaluate("""
                () => {

                    document
                        .querySelectorAll('#productos img')
                        .forEach(img => {

                            img.loading = 'eager';

                        });

                }
            """)

            # ==================================================
            # RECORRER TODA LA PÁGINA
            # ==================================================

            print("📜 Recorriendo productos...")

            page.evaluate("""
                async () => {

                    await new Promise(resolve => {

                        let posicion = 0;

                        const distancia = 400;

                        const intervalo =
                            setInterval(() => {

                                window.scrollBy(
                                    0,
                                    distancia
                                );

                                posicion += distancia;

                                if (
                                    posicion >=
                                    document.body.scrollHeight
                                ) {

                                    clearInterval(
                                        intervalo
                                    );

                                    window.scrollTo(
                                        0,
                                        0
                                    );

                                    resolve();

                                }

                            }, 150);

                    });

                }
            """)

            time.sleep(2)

            # ==================================================
            # ESPERAR IMÁGENES
            # ==================================================

            print("📸 Verificando imágenes...")

            tiempo_limite = time.time() + 20

            while time.time() < tiempo_limite:

                imagenes = page.evaluate("""
                    () => {

                        return Array.from(
                            document.querySelectorAll(
                                '#productos img.foto-principal'
                            )
                        ).map(img => ({

                            src: img.src,

                            complete: img.complete,

                            width: img.naturalWidth,

                            height: img.naturalHeight

                        }));

                    }
                """)

                pendientes = [
                    imagen
                    for imagen in imagenes
                    if not imagen["complete"]
                ]

                if not pendientes:
                    break

                time.sleep(0.5)

            # ==================================================
            # DETECTAR IMÁGENES FALLIDAS
            # ==================================================

            imagenes = page.evaluate("""
                () => {

                    return Array.from(
                        document.querySelectorAll(
                            '#productos img.foto-principal'
                        )
                    ).map(img => ({

                        src: img.src,

                        complete: img.complete,

                        width: img.naturalWidth,

                        height: img.naturalHeight

                    }));

                }
            """)

            imagenes_fallidas = [
                imagen
                for imagen in imagenes
                if imagen["complete"]
                and imagen["width"] == 0
            ]

            if imagenes_fallidas:

                print("")
                print(
                    f"⚠️ Imágenes que no pudieron cargar: "
                    f"{len(imagenes_fallidas)}"
                )

                for imagen in imagenes_fallidas:

                    print(
                        "   ❌",
                        imagen["src"]
                    )

            else:

                print(
                    "✅ Todas las imágenes "
                    "cargaron correctamente"
                )

            # ==================================================
            # PREPARAR CATÁLOGO
            # ==================================================

            print("🎨 Preparando catálogo...")

            page.evaluate("""
                () => {

                    // ==========================================
                    // OCULTAR ELEMENTOS
                    // ==========================================

                    const elementosOcultar = [

                        '.header',

                        '.buscador',

                        '.categorias-nav',

                        '.slider-container',

                        '.footer',

                        '.whatsapp-float',

                        '.carrito-float',

                        '.btn-top-bar',

                        '.dropdown-cat',

                        '.galeria-miniaturas',

                        '.btn-comprar',

                        '.instagram-btn',

                        'form'

                    ];

                    elementosOcultar.forEach(selector => {

                        document
                            .querySelectorAll(selector)
                            .forEach(elemento => {

                                elemento.style.display =
                                    'none';

                            });

                    });


                    // ==========================================
                    // BODY
                    // ==========================================

                    document.body.style.background =
                        '#ffffff';

                    document.body.style.margin =
                        '0';

                    document.body.style.padding =
                        '0';

                    document.body.style.fontFamily =
                        'Arial, sans-serif';


                    // ==========================================
                    // CONTENEDOR PRINCIPAL
                    // ==========================================

                    const contenedor =
                        document.querySelector(
                            '#productos'
                        );

                    if (contenedor) {

                        contenedor.style.width =
                            '100%';

                        contenedor.style.margin =
                            '0';

                        contenedor.style.padding =
                            '0';

                    }


                    // ==========================================
                    // CATEGORÍAS
                    // ==========================================

                    document
                        .querySelectorAll(
                            '#productos .categoria-bloque'
                        )
                        .forEach(categoria => {

                            categoria.style.breakInside =
                                'avoid';

                            categoria.style.pageBreakInside =
                                'avoid';

                            categoria.style.marginBottom =
                                '12px';

                        });


                    // ==========================================
                    // TÍTULOS DE CATEGORÍA
                    // ==========================================

                    document
                        .querySelectorAll(
                            '#productos .titulo-categoria'
                        )
                        .forEach(titulo => {

                            titulo.style.fontSize =
                                '18px';

                            titulo.style.margin =
                                '10px 0';

                            titulo.style.padding =
                                '6px 0';

                            titulo.style.borderBottom =
                                '2px solid #eeeeee';

                            titulo.style.color =
                                '#222';

                        });


                    // ==========================================
                    // GRILLA
                    // ==========================================

                    document
                        .querySelectorAll(
                            '#productos .grid-productos'
                        )
                        .forEach(grid => {

                            grid.style.display =
                                'grid';

                            grid.style.gridTemplateColumns =
                                'repeat(3, 1fr)';

                            grid.style.gap =
                                '10px';

                            grid.style.width =
                                '100%';

                            grid.style.margin =
                                '0';

                            grid.style.padding =
                                '0';

                        });


                    // ==========================================
                    // TARJETAS
                    // ==========================================

                    document
                        .querySelectorAll(
                            '#productos .card'
                        )
                        .forEach(card => {

                            card.style.display =
                                'block';

                            card.style.breakInside =
                                'avoid';

                            card.style.pageBreakInside =
                                'avoid';

                            card.style.border =
                                '1px solid #eeeeee';

                            card.style.borderRadius =
                                '8px';

                            card.style.padding =
                                '8px';

                            card.style.background =
                                '#ffffff';

                            card.style.boxSizing =
                                'border-box';

                            card.style.textAlign =
                                'center';

                            card.style.margin =
                                '0';


                            // ==================================
                            // FOTO PRINCIPAL
                            // ==================================

                            const foto =
                                card.querySelector(
                                    '.foto-principal'
                                );

                            if (foto) {

                                foto.loading =
                                    'eager';

                                foto.style.display =
                                    'block';

                                foto.style.width =
                                    '100%';

                                foto.style.height =
                                    '160px';

                                foto.style.objectFit =
                                    'contain';

                                foto.style.margin =
                                    '0 auto 8px';

                            }


                            // ==================================
                            // NOMBRE
                            // ==================================

                            const nombre =
                                card.querySelector(
                                    'h3'
                                );

                            if (nombre) {

                                nombre.style.fontSize =
                                    '13px';

                                nombre.style.lineHeight =
                                    '1.2';

                                nombre.style.margin =
                                    '5px 0';

                                nombre.style.color =
                                    '#222';

                            }


                            // ==================================
                            // PRECIO
                            // ==================================

                            const precio =
                                card.querySelector(
                                    '.precio'
                                );

                            if (precio) {

                                precio.style.fontSize =
                                    '13px';

                                precio.style.margin =
                                    '4px 0';

                                precio.style.color =
                                    '#222';

                            }


                            // ==================================
                            // OCULTAR REGISTRO MAYORISTA
                            // ==================================

                            card.querySelectorAll(
                                'small'
                            ).forEach(elemento => {

                                elemento.style.display =
                                    'none';

                            });

                        });

                }
            """)

            # ==================================================
            # MODO IMPRESIÓN
            # ==================================================

            page.emulate_media(
                media="print"
            )

            # ==================================================
            # GENERAR PDF
            # ==================================================

            print("📄 Generando PDF...")

            page.pdf(

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

            # ==================================================
            # RESULTADO
            # ==================================================

            print("")
            print("======================================")
            print("✅ ¡CATÁLOGO GENERADO CORRECTAMENTE!")
            print("======================================")
            print("")
            print("📄 Archivo:")
            print(pdf_path)
            print("")
            print(
                f"🛍️ Productos incluidos: "
                f"{cantidad_productos}"
            )

            if imagenes_fallidas:

                print(
                    f"⚠️ Imágenes con problemas: "
                    f"{len(imagenes_fallidas)}"
                )

            else:

                print("📸 Imágenes: OK")

            print("")

            # ==================================================
            # CERRAR NAVEGADOR UNA SOLA VEZ
            # ==================================================

            browser.close()


    except Exception as e:

        print("")
        print("❌ ERROR GENERANDO EL PDF")
        print("--------------------------------------")
        print(
            f"{type(e).__name__}: {e}"
        )
        print("--------------------------------------")
        print("")
        print(
            "💡 Verificá que Flask esté ejecutándose:"
        )
        print("   python app.py")
        print("")


if __name__ == "__main__":

    generar_pdf_desde_web()