import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import re
import io
import requests
import zipfile
import urllib3
import time
import xlsxwriter
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="SRI LIVE MONITOR", layout="wide", page_icon="📟")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS_WS = {"Content-Type": "text/xml;charset=UTF-8", "User-Agent": "Mozilla/5.0"}
URL_OFFLINE = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"
URL_ONLINE  = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantes?wsdl"

def extraer_datos_xml(xml_content):
    # (Tu función de extracción estándar simplificada para no llenar espacio)
    try:
        root = ET.fromstring(xml_content)
        # Desempaquetado simple para el reporte
        auth = root.find(".//autorizacion")
        if auth is None: 
            # Intentar desempaquetar SOAP si viene sucio
            text = re.sub(r'<\?xml.*?\?>', '', str(xml_content)).strip()
            if "<autorizacion>" in text: return {"ESTADO": "RECUPERADO"}
            return None
        return {"ESTADO": "OK"}
    except: return None

# --- INTERFAZ TIPO "HACKER / MONITOR" ---
st.title("📟 SRI NETWORK MONITOR")
st.markdown("""
<style>
    .terminal {
        background-color: #0e1117;
        color: #00ff00;
        font-family: 'Courier New', Courier, monospace;
        padding: 10px;
        border-radius: 5px;
        height: 400px;
        overflow-y: scroll;
        border: 1px solid #333;
        font-size: 12px;
    }
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("1. Carga de Archivo")
    archivo = st.file_uploader("Sube el TXT del SRI:", type=["txt"])
    start_btn = st.button("🔴 INICIAR RASTREO", type="primary", use_container_width=True)
    
    st.divider()
    st.metric("Estado del Sistema", "ESPERANDO", delta_color="off")
    stats_ph = st.empty()

with col2:
    st.subheader("2. Tráfico en Tiempo Real (Live Log)")
    # Este es el contenedor donde "imprimiremos" lo que pasa
    log_placeholder = st.empty()

if archivo and start_btn:
    # Preparación
    try: content = archivo.read().decode("latin-1")
    except: content = archivo.read().decode("utf-8", errors="ignore")
    
    claves = list(dict.fromkeys(re.findall(r'\d{48,49}', content)))
    
    if not claves:
        st.error("No hay claves válidas.")
        st.stop()

    # Variables de estado
    log_history = []
    session = requests.Session()
    session.verify = False
    session.headers.update(HEADERS_WS)
    
    ok_counter = 0
    fail_counter = 0
    zip_buffer = io.BytesIO()
    
    # --- FUNCIÓN DE LOGGING VISUAL ---
    def log(mensaje, tipo="INFO"):
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        icon = "info"
        if tipo == "REQ": icon = "➡️ OUT"
        elif tipo == "RES": icon = "⬅️ IN "
        elif tipo == "ERR": icon = "❌ ERR"
        elif tipo == "SUCCESS": icon = "✅ OK "
        
        line = f"[{now}] [{icon}] {mensaje}"
        log_history.insert(0, line) # Agrega al principio (más reciente arriba)
        
        # Renderizar en la 'ventana' negra
        log_content = "\n".join(log_history[:50]) # Mostrar últimas 50 líneas
        log_placeholder.code(log_content, language="bash")

    # --- INICIO DEL BUCLE ---
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for i, cl in enumerate(claves):
            stats_ph.markdown(f"**Procesando:** {i+1}/{len(claves)} | **OK:** {ok_counter} | **Fails:** {fail_counter}")
            
            exito = False
            soap = f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion"><soapenv:Body><ec:autorizacionComprobante><claveAccesoComprobante>{cl}</claveAccesoComprobante></ec:autorizacionComprobante></soapenv:Body></soapenv:Envelope>'
            
            # 1. INTENTO OFFLINE
            log(f"Consultando Clave: {cl[-8:]}...", "REQ")
            try:
                start_t = time.time()
                r = session.post(URL_OFFLINE, data=soap, timeout=5)
                latency = round((time.time() - start_t) * 1000)
                
                # Análisis de respuesta
                if r.status_code == 200:
                    if "<autorizaciones/>" in r.text or "<numeroComprobantes>0" in r.text:
                         log(f"OFFLINE ({latency}ms): SRI respondió '0 Comprobantes' (Vacío)", "ERR")
                    elif "<autorizacion>" in r.text:
                        log(f"OFFLINE ({latency}ms): AUTORIZADO. Descargando...", "SUCCESS")
                        zf.writestr(f"{cl}.xml", r.text)
                        ok_counter += 1
                        exito = True
                    else:
                        log(f"OFFLINE ({latency}ms): Respuesta desconocida.", "ERR")
                else:
                    log(f"OFFLINE Error HTTP: {r.status_code}", "ERR")
                    
            except Exception as e:
                log(f"Error Conexión Offline: {str(e)}", "ERR")

            # 2. INTENTO ONLINE (Si falló el 1)
            if not exito:
                log("⚠️ Cambiando a servidor ONLINE (Intento de rescate)...", "INFO")
                try:
                    time.sleep(0.5)
                    start_t = time.time()
                    r = session.post(URL_ONLINE, data=soap, timeout=8)
                    latency = round((time.time() - start_t) * 1000)
                    
                    if r.status_code == 200:
                        if "<autorizacion>" in r.text:
                            log(f"ONLINE ({latency}ms): ¡RESCATADA! Encontrada en base Online.", "SUCCESS")
                            zf.writestr(f"{cl}.xml", r.text)
                            ok_counter += 1
                            exito = True
                        else:
                            # AQUÍ ES DONDE VERÁS SI EL SRI TE MIENTE
                            log(f"ONLINE ({latency}ms): TAMPOCO EXISTE. Respuesta: {r.text[:60]}...", "ERR")
                    else:
                         log(f"ONLINE Error HTTP: {r.status_code}", "ERR")
                except:
                    log("Error Conexión Online.", "ERR")

            if not exito:
                fail_counter += 1
                log(f"❌ DEFINITIVO: Clave {cl[-8:]} no existe en ningún servidor.", "ERR")

    st.success("Proceso Terminado")
    if ok_counter > 0:
        st.download_button("Bajar ZIP Generado", zip_buffer.getvalue(), "Evidencia_SRI.zip", "application/zip", type="primary")

