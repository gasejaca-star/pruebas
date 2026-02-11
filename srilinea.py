import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import re
import io
import requests
import zipfile
import urllib3
import time

st.set_page_config(page_title="SRI MIMIC TOOL", layout="wide", page_icon="🎭")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURACIÓN DE HUELLA DIGITAL (MIMIC) ---
# Copiamos exactamente los headers que nos pasaste
HEADERS_MIMIC = {
    "Accept": "*/*",
    "Accept-Language": "es-MX,es-EC;q=0.7,es;q=0.3",
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; WOW64; Trident/7.0; .NET4.0C; .NET4.0E; Zoom 3.6.0)",
    "Connection": "Keep-Alive",
    "Cache-Control": "no-cache",
    "Content-Type": "text/xml;charset=UTF-8" # Necesario para SOAP
}

URL_OFFLINE = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"
URL_ONLINE  = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantes?wsdl"

def extraer_info_xml(content):
    try:
        root = ET.fromstring(content)
        # Buscar autorización dentro del CDATA o estructura
        raw = str(content)
        if "AUTORIZADO" in raw:
            return "AUTORIZADO"
        elif "NO AUTORIZADO" in raw:
            return "RECHAZADO"
        else:
            return "DESCONOCIDO"
    except: return "ERROR_XML"

# --- INTERFAZ ---
st.title("🎭 SRI MIMIC (Clonador de Petición)")
st.markdown("""
Este script envía las peticiones usando **exactamente** la cabecera del software 'Zoom 3.6.0' 
y la Cookie de sesión que ingreses, para saltar bloqueos del SRI.
""")

col1, col2 = st.columns(2)

with col1:
    archivo = st.file_uploader("1. Sube tu TXT:", type=["txt"])

with col2:
    cookie_input = st.text_input("2. Pega la Cookie (TS...):", 
                                 placeholder="Ej: TS010a7529=0115ac86d28...",
                                 help="Copia todo el valor que está después de 'Cookie:' en tu ejemplo")
    
    ambiente = st.radio("3. ¿A qué servidor disparamos?", ["OFFLINE (Estándar)", "ONLINE (Rescate)"])

if st.button("🔫 DISPARAR PETICIONES MIMIC", type="primary"):
    if not archivo or not cookie_input:
        st.error("Falta el archivo o la Cookie.")
        st.stop()

    # Preparar Datos
    try: content = archivo.read().decode("latin-1")
    except: content = archivo.read().decode("utf-8", errors="ignore")
    claves = list(dict.fromkeys(re.findall(r'\d{48,49}', content)))
    
    if not claves: st.warning("No hay claves."); st.stop()

    # Preparar Headers con la Cookie del Usuario
    mis_headers = HEADERS_MIMIC.copy()
    mis_headers["Cookie"] = cookie_input.strip() # Inyectamos la cookie manual
    
    url_destino = URL_OFFLINE if "OFFLINE" in ambiente else URL_ONLINE
    
    # UI
    bar = st.progress(0)
    status_box = st.empty()
    logs = st.expander("Ver Tráfico Raw", expanded=True)
    
    zip_buffer = io.BytesIO()
    ok_count = 0
    fail_count = 0
    
    session = requests.Session()
    session.verify = False
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for i, cl in enumerate(claves):
            # Construir XML SOAP exacto
            soap_body = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion">
   <soapenv:Header/>
   <soapenv:Body>
      <ec:autorizacionComprobante>
         <claveAccesoComprobante>{cl}</claveAccesoComprobante>
      </ec:autorizacionComprobante>
   </soapenv:Body>
</soapenv:Envelope>"""

            try:
                # Disparar con los headers clonados
                # Nota: requests calcula Content-Length automático
                r = session.post(url_destino, data=soap_body, headers=mis_headers, timeout=10)
                
                estado = "FALLO"
                if r.status_code == 200:
                    if "<autorizacion>" in r.text:
                        zf.writestr(f"{cl}.xml", r.text)
                        ok_count += 1
                        estado = "✅ EXITO"
                        logs.success(f"[{i+1}] {cl[-10:]}... -> RECUPERADA (MIMIC)")
                    elif "numeroComprobantes>0" in r.text:
                        estado = "⚠️ VACÍO (0)"
                        logs.warning(f"[{i+1}] {cl[-10:]}... -> SRI dice 0 comprobantes")
                    else:
                        logs.info(f"[{i+1}] {cl[-10:]}... -> {r.text[:100]}")
                else:
                    estado = f"❌ HTTP {r.status_code}"
                    logs.error(f"[{i+1}] Error HTTP: {r.status_code}")

            except Exception as e:
                estado = "❌ ERROR RED"
                logs.error(f"[{i+1}] Error: {e}")
                fail_count += 1

            bar.progress((i+1)/len(claves))
            status_box.markdown(f"**Procesando:** {i+1}/{len(claves)} | **Recuperadas:** {ok_count}")
            
            # Pausa humana pequeña para que no detecten el patrón del script
            time.sleep(0.5)

    st.divider()
    if ok_count > 0:
        st.success(f"¡Misión Cumplida! {ok_count} facturas recuperadas.")
        st.download_button("📦 BAJAR ZIP MIMIC", zip_buffer.getvalue(), "Facturas_Mimic.zip", "application/zip", type="primary")
    else:
        st.error("No se recuperó nada. Prueba cambiando el servidor a ONLINE o actualiza la Cookie.")

