import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import re
import io
import requests
import zipfile
import urllib3
import time
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="SRI LIVE MONITOR (STEALTH)", layout="wide", page_icon="🥷")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURACIÓN ANTI-BLOQUEO (NUEVO) ---
# Estas cabeceras hacen creer al SRI que somos un navegador Chrome real, no un script.
HEADERS_WS = {
    "Content-Type": "text/xml;charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

URL_OFFLINE = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"
URL_ONLINE  = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantes?wsdl"

# --- INTERFAZ ---
st.title("🥷 SRI MONITOR - MODO SIGILO")
st.markdown("""
<style>
    .terminal {
        background-color: #000000;
        color: #00ff00;
        font-family: 'Consolas', 'Courier New', monospace;
        padding: 10px;
        border-radius: 5px;
        height: 450px;
        overflow-y: scroll;
        border: 1px solid #333;
        font-size: 13px;
    }
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("1. Carga de Archivo")
    archivo = st.file_uploader("Sube el TXT del SRI:", type=["txt"])
    start_btn = st.button("🚀 INICIAR RESCATE", type="primary", use_container_width=True)
    
    st.divider()
    stats_ph = st.empty()

with col2:
    st.subheader("2. Tráfico en Tiempo Real")
    log_placeholder = st.empty()

if archivo and start_btn:
    try: content = archivo.read().decode("latin-1")
    except: content = archivo.read().decode("utf-8", errors="ignore")
    
    claves = list(dict.fromkeys(re.findall(r'\d{48,49}', content)))
    
    if not claves:
        st.error("No hay claves válidas.")
        st.stop()

    log_history = []
    
    # Usamos una sesión con adaptadores para reintentos de bajo nivel
    session = requests.Session()
    session.verify = False
    session.headers.update(HEADERS_WS)
    
    # Adaptador para manejar cortes de conexión
    adapter = requests.adapters.HTTPAdapter(max_retries=1)
    session.mount("https://", adapter)
    
    ok_counter = 0
    fail_counter = 0
    rescue_counter = 0
    zip_buffer = io.BytesIO()
    
    def log(mensaje, tipo="INFO"):
        now = datetime.now().strftime("%H:%M:%S")
        color = "white"
        icon = "ℹ️"
        
        if tipo == "OFF_OK": icon = "✅ OFF"; color = "#4CAF50" # Verde
        elif tipo == "ON_OK": icon = "🔥 ON "; color = "#00FFFF" # Cyan (Rescate)
        elif tipo == "EMPTY": icon = "⚠️ VAC"; color = "#FFC107" # Amarillo
        elif tipo == "ERR": icon = "❌ ERR"; color = "#FF5252" # Rojo
        
        # Formato HTML para la terminal simulada
        line = f"<div style='color:{color};'>[{now}] <b>[{icon}]</b> {mensaje}</div>"
        log_history.insert(0, line)
        log_placeholder.markdown(f"<div class='terminal'>{''.join(log_history)}</div>", unsafe_allow_html=True)

    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for i, cl in enumerate(claves):
            stats_ph.info(f"⏳ Procesando: {i+1}/{len(claves)}\n\n✅ Éxitos: {ok_counter}\n🔥 Rescatadas: {rescue_counter}\n❌ Fallos: {fail_counter}")
            
            exito = False
            soap = f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion"><soapenv:Body><ec:autorizacionComprobante><claveAccesoComprobante>{cl}</claveAccesoComprobante></ec:autorizacionComprobante></soapenv:Body></soapenv:Envelope>'
            
            # --- INTENTO 1: OFFLINE ---
            try:
                # Timeout corto (5s) para el Offline
                r = session.post(URL_OFFLINE, data=soap, timeout=5)
                
                if r.status_code == 200:
                    if "<autorizacion>" in r.text:
                        zf.writestr(f"{cl}.xml", r.text)
                        log(f"Clave ...{cl[-8:]} descargada (Offline)", "OFF_OK")
                        ok_counter += 1
                        exito = True
                    else:
                        log(f"Clave ...{cl[-8:]} no está en Offline (Vacío)", "EMPTY")
            except Exception as e:
                pass # Si falla Offline, vamos directo al Online

            # --- INTENTO 2: ONLINE (MODO SIGILO) ---
            if not exito:
                try:
                    time.sleep(1.0) # Pausa obligatoria para engañar al firewall
                    
                    # Timeout largo (15s) porque el Online es lento y pesado
                    r = session.post(URL_ONLINE, data=soap, timeout=15)
                    
                    if r.status_code == 200:
                        if "<autorizacion>" in r.text:
                            zf.writestr(f"{cl}.xml", r.text)
                             
                            log(f"¡RESCATADA! Clave ...{cl[-8:]} bajada del Online", "ON_OK")
                            ok_counter += 1
                            rescue_counter += 1
                            exito = True
                        else:
                            log(f"Fallo definitivo: Clave ...{cl[-8:]} no existe ni en Online.", "ERR")
                    else:
                        log(f"Bloqueo Online HTTP {r.status_code}", "ERR")
                        
                except Exception as e:
                    log(f"Error Conexión Online: {str(e)}", "ERR")

            if not exito:
                fail_counter += 1

    st.success("Finalizado")
    if ok_counter > 0:
        st.download_button("📦 DESCARGAR ZIP FINAL", zip_buffer.getvalue(), "Facturas_Rescatadas.zip", "application/zip", type="primary")
    if ok_counter > 0:
        st.download_button("Bajar ZIP Generado", zip_buffer.getvalue(), "Evidencia_SRI.zip", "application/zip", type="primary")


