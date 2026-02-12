import streamlit as st
import xml.etree.ElementTree as ET
import re
import io
import requests
import zipfile
import urllib3
import time

# --- CONFIGURACIÓN DE DISFRAZ (ZOOM 3.6.0) ---
# Esta es la "máscara" que usaremos para engañar al SRI
HEADERS_ZOOM = {
    "Accept": "*/*",
    "Accept-Language": "es-MX,es-EC;q=0.7,es;q=0.3",
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; WOW64; Trident/7.0; .NET4.0C; .NET4.0E; Zoom 3.6.0)",
    "Connection": "Keep-Alive",
    "Cache-Control": "no-cache",
    "Content-Type": "text/xml;charset=UTF-8",
    "Host": "cel.sri.gob.ec"
}

# Cookie capturada (Se puede actualizar desde la interfaz)
DEFAULT_COOKIE = "TS010a7529=0115ac86d2ff8c6d8602bcd5b76de3c56b0d92b76d207ed83bc26ff7a2b6c9da7e1c6c59a6661e932699d7fda2eb24a82a026c7b15"

st.set_page_config(page_title="SRI ZOOM CLONE", layout="wide", page_icon="🎭")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL_OFFLINE = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"
URL_ONLINE  = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantes?wsdl"

# --- INTERFAZ ---
st.title("🎭 SRI ZOOM CLONE")
st.markdown("Este script simula ser el software **Zoom 3.6.0** usando sus cabeceras exactas para evitar bloqueos.")

col1, col2 = st.columns(2)

with col1:
    archivo = st.file_uploader("1. Sube tu TXT:", type=["txt"])

with col2:
    cookie_user = st.text_input("2. Cookie TS (Opcional, usa la default si está vacía):", value=DEFAULT_COOKIE)
    modo = st.radio("3. Modo de Ataque:", ["OFFLINE (Estándar)", "ONLINE (Rescate - Facturas Fantasma)"])

if st.button("🚀 INICIAR DESCARGA CLONADA", type="primary"):
    if not archivo:
        st.error("Sube el archivo TXT primero.")
        st.stop()

    # Preparar Cookie Final
    headers_finales = HEADERS_ZOOM.copy()
    headers_finales["Cookie"] = cookie_user.strip()
    
    # Leer claves
    try: content = archivo.read().decode("latin-1")
    except: content = archivo.read().decode("utf-8", errors="ignore")
    claves = list(dict.fromkeys(re.findall(r'\d{48,49}', content)))
    
    if not claves: st.warning("No hay claves."); st.stop()

    # Configurar Sesión
    session = requests.Session()
    session.verify = False
    
    url_destino = URL_OFFLINE if "OFFLINE" in modo else URL_ONLINE
    
    st.info(f"Iniciando descarga de {len(claves)} documentos simulando ser Zoom 3.6.0...")
    
    bar = st.progress(0)
    status = st.empty()
    zip_buffer = io.BytesIO()
    ok_count = 0
    errores = []

    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for i, cl in enumerate(claves):
            # XML SOAP estándar
            soap = f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion"><soapenv:Header/><soapenv:Body><ec:autorizacionComprobante><claveAccesoComprobante>{cl}</claveAccesoComprobante></ec:autorizacionComprobante></soapenv:Body></soapenv:Envelope>'
            
            try:
                # Disparo con headers clonados
                r = session.post(url_destino, data=soap, headers=headers_finales, timeout=12)
                
                if r.status_code == 200:
                    if "<autorizacion>" in r.text:
                        zf.writestr(f"{cl}.xml", r.text)
                        ok_count += 1
                    elif "numeroComprobantes>0" in r.text:
                        errores.append(f"{cl} -> 0 Comprobantes (SRI vacío)")
                    else:
                        errores.append(f"{cl} -> Respuesta desconocida")
                else:
                    errores.append(f"{cl} -> HTTP {r.status_code}")
                    
            except Exception as e:
                errores.append(f"{cl} -> Error Red: {str(e)}")

            bar.progress((i+1)/len(claves))
            status.text(f"Procesando {i+1}/{len(claves)} | ✅ OK: {ok_count}")
            
            # Pausa para parecer comportamiento humano/software antiguo
            time.sleep(0.3)

    st.divider()
    if ok_count > 0:
        st.success(f"¡ÉXITO! {ok_count} facturas recuperadas.")
        st.download_button("📦 BAJAR ZIP", zip_buffer.getvalue(), "Facturas_Zoom_Clone.zip", "application/zip", type="primary")
    
    if errores:
        with st.expander("Ver Errores / Faltantes"):
            st.write(errores)
