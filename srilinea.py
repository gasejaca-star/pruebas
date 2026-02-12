import streamlit as st
import re
import requests
import zipfile
import io
import urllib3
import time

# --- CONFIGURACIÓN QUEMADA (HARDCODED) ---
# 1. La Cookie EXACTA que me pasaste (Limpia, sin Path ni Domain)
COOKIE_FIJA = "TS010a7529=0115ac86d2ff8c6d8602bcd5b76de3c56b0d92b76d207ed83bc26ff7a2b6c9da7e1c6c59a6661e932699d7fda2eb24a82a026c7b15"

# 2. Las Cabeceras EXACTAS de Zoom 3.6.0
HEADERS_ZOOM = {
    "Accept": "*/*",
    "Accept-Language": "es-MX,es-EC;q=0.7,es;q=0.3",
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; WOW64; Trident/7.0; .NET4.0C; .NET4.0E; Zoom 3.6.0)",
    "Content-Type": "text/xml;charset=UTF-8",
    "Connection": "Keep-Alive",
    "Host": "cel.sri.gob.ec",
    "Cache-Control": "no-cache",
    "Cookie": COOKIE_FIJA  # <--- AQUÍ ESTÁ TU LLAVE
}

# 3. El XML EXACTO con la huella "" y los espacios originales
XML_TEMPLATE = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion">
   <soapenv:Header/>
   <soapenv:Body>
      <ec:autorizacionComprobante>
         <claveAccesoComprobante>{}</claveAccesoComprobante>
      </ec:autorizacionComprobante>
   </soapenv:Body>
</soapenv:Envelope>"""

URL_OFFLINE = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"

# --- INTERFAZ SIMPLE ---
st.set_page_config(page_title="SRI ZOOM AUTO-LOGIN", layout="wide", page_icon="🔑")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.title("🔑 SRI ZOOM: Cookie Inyectada")
st.markdown(f"**Estado:** Cookie cargada automáticamente (`...{COOKIE_FIJA[-10:]}`).")

archivo = st.file_uploader("Sube tu TXT y listo:", type=["txt"])

if archivo and st.button("EJECUTAR CON COOKIE FIJA", type="primary"):
    # Leer Claves
    try: content = archivo.read().decode("latin-1")
    except: content = archivo.read().decode("utf-8", errors="ignore")
    
    claves = list(dict.fromkeys(re.findall(r'\d{48,49}', content)))
    
    if not claves:
        st.error("No se encontraron claves en el archivo.")
        st.stop()

    # Preparar Sesión
    session = requests.Session()
    session.verify = False
    
    bar = st.progress(0)
    status = st.empty()
    zip_buffer = io.BytesIO()
    ok_count = 0
    errores = []

    st.info(f"Procesando {len(claves)} facturas con la identidad de Zoom...")

    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for i, cl in enumerate(claves):
            # Inyectar clave limpia
            payload = XML_TEMPLATE.format(cl.strip())
            
            try:
                # Enviar petición con la Cookie y Headers fijos
                r = session.post(URL_OFFLINE, data=payload, headers=HEADERS_ZOOM, timeout=10)
                
                if r.status_code == 200:
                    if "<autorizacion>" in r.text:
                        zf.writestr(f"{cl}.xml", r.text)
                        ok_count += 1
                        st.toast(f"✅ Bajada: ...{cl[-8:]}")
                    elif "numeroComprobantes>0" in r.text:
                        errores.append(f"{cl} -> Vacío (0)")
                else:
                    errores.append(f"{cl} -> HTTP {r.status_code}")
                    
            except Exception as e:
                errores.append(f"{cl} -> Error {str(e)}")

            # Feedback visual
            bar.progress((i+1)/len(claves))
            status.markdown(f"**Recuperadas:** `{ok_count}` | **Fallos:** `{len(errores)}`")
            time.sleep(0.2) # Pausa técnica

    st.divider()
    if ok_count > 0:
        st.balloons()
        st.success(f"¡LOGRADO! {ok_count} facturas recuperadas usando la Cookie.")
        st.download_button("📦 DESCARGAR ZIP", zip_buffer.getvalue(), "Facturas_Recuperadas.zip", "application/zip", type="primary")
    else:
        st.error("Resultado: 0 Recuperadas.")
        st.warning("⚠️ Si sigue fallando, significa que esa Cookie ESPECÍFICA ya caducó (duran 10-15 min). Tendrías que sacar una nueva del navegador y reemplazarla en la línea 11 del código.")
        if errores:
            with st.expander("Ver Detalles de Fallo"):
                st.write(errores)
