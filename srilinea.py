import streamlit as st
import re
import io
import requests
import zipfile
import urllib3
import time

# --- CONFIGURACIÓN DE CLONACIÓN ---
# 1. Cabeceras EXACTAS del programa "Zoom"
HEADERS_TWIN = {
    "Accept": "*/*",
    "Accept-Language": "es-MX,es-EC;q=0.7,es;q=0.3",
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; WOW64; Trident/7.0; .NET4.0C; .NET4.0E; Zoom 3.6.0)",
    "Content-Type": "text/xml;charset=UTF-8",
    "Connection": "Keep-Alive",
    "Host": "cel.sri.gob.ec",
    "Cache-Control": "no-cache"
}

# 2. El cuerpo XML EXACTO con la huella ""
# Nota los saltos de línea (\n) y espacios, son importantes para la huella.
XML_TEMPLATE = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion">
   <soapenv:Header/>
   <soapenv:Body>
      <ec:autorizacionComprobante>
         <claveAccesoComprobante>{}</claveAccesoComprobante>
      </ec:autorizacionComprobante>
   </soapenv:Body>
</soapenv:Envelope>"""

URL_OFFLINE = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"

st.set_page_config(page_title="SRI GEMELO EXACTO", layout="wide", page_icon="👯")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.title("👯 SRI: EL GEMELO (The Twin)")
st.markdown("Este script envía el XML **byte por byte** idéntico al que capturaste en Fiddler, incluyendo la marca ``.")

col1, col2 = st.columns(2)
with col1:
    archivo = st.file_uploader("1. Sube tu TXT:", type=["txt"])
with col2:
    cookie_input = st.text_input("2. Pega la Cookie TS (Vital):", placeholder="TS010a7529=...")

if st.button("ACTIVAR GEMELO", type="primary"):
    if not archivo or not cookie_input:
        st.error("Falta archivo o Cookie.")
        st.stop()

    # Preparamos Headers con la Cookie
    headers_finales = HEADERS_TWIN.copy()
    headers_finales["Cookie"] = cookie_input.strip()

    # Leer Claves
    try: content = archivo.read().decode("latin-1")
    except: content = archivo.read().decode("utf-8", errors="ignore")
    claves = list(dict.fromkeys(re.findall(r'\d{48,49}', content)))
    
    if not claves: st.warning("No hay claves."); st.stop()

    st.success(f"Clonando peticiones para {len(claves)} facturas...")
    
    # UI
    bar = st.progress(0)
    status = st.empty()
    zip_buffer = io.BytesIO()
    ok_count = 0
    
    session = requests.Session()
    session.verify = False # Ignorar SSL como lo hace Fiddler a veces
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for i, cl in enumerate(claves):
            # Inyectar clave en el template exacto
            soap_body = XML_TEMPLATE.format(cl)
            
            try:
                # Enviar al mismo endpoint que Fiddler (Offline)
                r = session.post(URL_OFFLINE, data=soap_body, headers=headers_finales, timeout=10)
                
                # Análisis de respuesta
                if r.status_code == 200:
                    if "<autorizacion>" in r.text:
                        zf.writestr(f"{cl}.xml", r.text)
                        ok_count += 1
                        # Pequeño log visual si es una de las difíciles
                        if cl.endswith("322130112"): 
                            st.toast(f"🎯 ¡DIANA! Recuperada la .112", icon="🔥")
                
            except: pass

            bar.progress((i+1)/len(claves))
            status.text(f"Gemelo procesando: {i+1}/{len(claves)} | Recuperadas: {ok_count}")
            time.sleep(0.2) # Pausa técnica

    st.divider()
    if ok_count > 0:
        st.balloons()
        st.success(f"¡FUNCIONÓ! {ok_count} facturas recuperadas con la técnica del Gemelo.")
        st.download_button("📦 DESCARGAR ZIP", zip_buffer.getvalue(), "Facturas_Gemelo.zip", "application/zip", type="primary")
    else:
        st.error("Sigue dando 0. Si el XML y los Headers son idénticos, entonces la Cookie caducó o tu IP está en lista gris temporal.")
