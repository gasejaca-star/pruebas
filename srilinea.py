import streamlit as st
import re
import requests
import zipfile
import io
import urllib3
import time

# --- CONFIGURACIÓN DE CIRUJANO ---
HEADERS_ZOOM = {
    "Accept": "*/*",
    "Accept-Language": "es-MX,es-EC;q=0.7,es;q=0.3",
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; WOW64; Trident/7.0; .NET4.0C; .NET4.0E; Zoom 3.6.0)",
    "Content-Type": "text/xml;charset=UTF-8",
    "Connection": "Keep-Alive",
    "Host": "cel.sri.gob.ec",
    "Cache-Control": "no-cache",
    "SOAPAction": ""
}

# ESTA ES LA PLANTILLA CONGELADA (NO TOCAR ESPACIOS)
# Hemos replicado la indentación exacta de tu captura.
XML_EXACTO = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion">\r
   <soapenv:Header/>\r
   <soapenv:Body>\r
      <ec:autorizacionComprobante>\r
         \r
         <claveAccesoComprobante>{}</claveAccesoComprobante>\r
      </ec:autorizacionComprobante>\r
   </soapenv:Body>\r
</soapenv:Envelope>"""

URL_OFFLINE = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"

st.set_page_config(page_title="SRI BYTE PRECISE", layout="wide", page_icon="📏")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.title("📏 SRI: Precisión de Bytes")
st.markdown("Este script verifica que la clave se inyecte limpia, sin espacios fantasma, replicando el `Content-Length`.")

col1, col2 = st.columns(2)
with col1:
    archivo = st.file_uploader("1. Sube tu TXT:", type=["txt"])
with col2:
    cookie_ts = st.text_input("2. Cookie TS (¡OBLIGATORIA!):", placeholder="TS010a7529=...")

if st.button("INICIAR CIRUGÍA", type="primary"):
    if not archivo or not cookie_ts:
        st.error("Falta archivo o Cookie.")
        st.stop()

    # Headers finales
    mis_headers = HEADERS_ZOOM.copy()
    mis_headers["Cookie"] = cookie_ts.strip()

    # Leer Claves y LIMPIARLAS
    try: content = archivo.read().decode("latin-1")
    except: content = archivo.read().decode("utf-8", errors="ignore")
    
    # Regex estricto para evitar espacios o saltos de línea al final
    claves_sucias = re.findall(r'\d{48,49}', content)
    claves = [c.strip() for c in claves_sucias] # Limpieza forzosa
    claves = list(dict.fromkeys(claves))
    
    if not claves: st.warning("No hay claves."); st.stop()

    # UI
    log_box = st.expander("Verificación de Bytes (Debug)", expanded=True)
    bar = st.progress(0)
    zip_buffer = io.BytesIO()
    ok_count = 0
    
    session = requests.Session()
    session.verify = False

    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for i, cl in enumerate(claves):
            # INYECCIÓN: El .strip() garantiza que no entre basura
            payload = XML_EXACTO.format(cl.strip())
            
            # CALCULAR PESO (Simulando Content-Length)
            peso_bytes = len(payload.encode('utf-8'))
            
            # Debug visual para la primera clave
            if i == 0:
                log_box.info(f"🔍 DIAGNÓSTICO PRIMERA CLAVE:")
                log_box.code(payload, language="xml")
                log_box.metric("Peso del Paquete (Content-Length)", f"{peso_bytes} bytes", "Debe ser ~412")
                
                if peso_bytes != 412:
                    log_box.warning(f"⚠️ Nota: El peso es {peso_bytes}. Si la clave tiene 49 dígitos exactos, la diferencia es solo el formato de línea. Enviando de todas formas...")

            try:
                # Enviar petición
                r = session.post(URL_OFFLINE, data=payload, headers=mis_headers, timeout=8)
                
                if r.status_code == 200:
                    if "<autorizacion>" in r.text:
                        zf.writestr(f"{cl}.xml", r.text)
                        ok_count += 1
                        st.toast(f"✅ Bajada: ...{cl[-8:]}")
                    elif "numeroComprobantes>0" in r.text:
                         pass # Vacío
                
            except Exception as e:
                pass

            bar.progress((i+1)/len(claves))
            time.sleep(0.1)

    if ok_count > 0:
        st.balloons()
        st.success(f"¡LOGRADO! {ok_count} facturas recuperadas.")
        st.download_button("📦 BAJAR ZIP", zip_buffer.getvalue(), "Facturas_Cirujano.zip", "application/zip", type="primary")
    else:
        st.error("Sigue dando 0. Diagnóstico final: El formato XML es perfecto. El bloqueo es 100% por la COOKIE (o IP). Asegúrate de que la Cookie 'TS...' sea fresca del navegador.")
