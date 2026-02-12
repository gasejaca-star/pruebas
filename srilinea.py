import streamlit as st
import socket
import ssl
import gzip
import io
import re
import zipfile
import pandas as pd

st.set_page_config(page_title="SRI: SESSION HIJACK (COOKIE)", layout="wide", page_icon="🍪")

st.title("🍪 SRI: RECUPERACIÓN POR SESIÓN (COOKIE)")
st.markdown("""
**Estrategia:** Usamos la cookie `TS...` capturada de Fiddler para "engañar" al servidor y hacernos pasar por el programa autorizado.
**Nota:** Si deja de funcionar, la cookie caducó. Saca una nueva de Fiddler y pégala abajo.
""")

# --- CONFIGURACIÓN ---
# Tu cookie capturada (La pongo por defecto para que sea rápido)
COOKIE_DEFAULT = "TS010a7529=0115ac86d2ff8c6d8602bcd5b76de3c56b0d92b76d207ed83bc26ff7a2b6c9da7e1c6c59a6661e932699d7fda2eb24a82a026c7b15"

# Plantilla con la indentación EXACTA de tus fotos de Fiddler (412 bytes aprox)
XML_BODY_TEMPLATE = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion">
   <soapenv:Header/>
   <soapenv:Body>
      <ec:autorizacionComprobante>
         <claveAccesoComprobante>{}</claveAccesoComprobante>
      </ec:autorizacionComprobante>
   </soapenv:Body>
</soapenv:Envelope>"""

def descargar_con_cookie(clave, cookie_actual):
    host = "cel.sri.gob.ec"
    port = 443
    
    # 1. Preparar el XML (Ojo: convertimos a UTF-8)
    # Usamos .replace para asegurar que los saltos de línea sean Windows (\r\n) si es necesario
    body_str = XML_BODY_TEMPLATE.format(clave.strip()).replace('\n', '\r\n')
    body_bytes = body_str.encode('utf-8')
    
    # 2. Construir Headers EXACTOS (Copiados de tu Fiddler)
    headers = (
        "POST /comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl HTTP/1.1\r\n"
        "Accept: */*\r\n"
        "Accept-Encoding: gzip, deflate\r\n"  # Vital: pedimos compresión
        "Accept-Language: es-MX,es-EC;q=0.7,es;q=0.3\r\n"
        "User-Agent: Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; WOW64; Trident/7.0; .NET4.0C; .NET4.0E; Zoom 3.6.0)\r\n"
        "Host: cel.sri.gob.ec\r\n"
        "Content-Type: text/xml;charset=UTF-8\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        "Connection: Keep-Alive\r\n"
        "Cache-Control: no-cache\r\n"
        f"Cookie: {cookie_actual.strip()}\r\n" # <--- AQUÍ VA TU LLAVE
        "SOAPAction: \"\"\r\n"
        "\r\n"
    )
    
    # Paquete final
    full_payload = headers.encode('latin-1') + body_bytes

    # 3. Conexión SSL Legacy
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.set_ciphers('DEFAULT@SECLEVEL=1') 
    
    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                ssock.sendall(full_payload)
                
                # Leer respuesta
                response_data = b""
                while True:
                    chunk = ssock.recv(4096)
                    if not chunk: break
                    response_data += chunk
                
                # 4. Procesar (Separar Header/Body y Descomprimir)
                header_end = response_data.find(b"\r\n\r\n")
                if header_end != -1:
                    raw_body = response_data[header_end+4:]
                    
                    # Intentar GZIP (Si empieza con 1f 8b)
                    if raw_body.startswith(b'\x1f\x8b'):
                        try:
                            with gzip.GzipFile(fileobj=io.BytesIO(raw_body)) as f:
                                return True, f.read().decode('utf-8')
                        except:
                            return False, "Error Descompresión GZIP"
                    else:
                        return True, raw_body.decode('utf-8', errors='ignore')
                        
        return False, "Sin respuesta"
    except Exception as e:
        return False, str(e)

# --- INTERFAZ ---
col1, col2 = st.columns([1, 2])
with col1:
    archivo = st.file_uploader("1. Sube tu TXT de claves:", type=["txt"])
with col2:
    cookie_input = st.text_input("2. Cookie Activa (TS...):", value=COOKIE_DEFAULT)

if archivo and st.button("🚀 INICIAR DESCARGA CON COOKIE"):
    try: content = archivo.read().decode("latin-1")
    except: content = archivo.read().decode("utf-8", errors="ignore")
    claves = list(dict.fromkeys(re.findall(r'\d{49}', content)))
    
    if not claves: st.error("No se encontraron claves."); st.stop()
    
    bar = st.progress(0)
    log = st.empty()
    zip_buffer = io.BytesIO()
    ok_count = 0
    fail_count = 0
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for i, cl in enumerate(claves):
            exito, resp = descargar_con_cookie(cl, cookie_input)
            
            if exito:
                if "<autorizacion>" in resp:
                    # Extraer XML limpio
                    match = re.search(r'(<autorizacion>.*?</autorizacion>)', resp, re.DOTALL)
                    if match:
                        zf.writestr(f"{cl}.xml", match.group(1))
                        ok_count += 1
                        log.success(f"[{i+1}/{len(claves)}] ✅ Recuperada: {cl[-8:]}")
                    else:
                        fail_count += 1
                elif "numeroComprobantes>0" in resp:
                    log.warning(f"[{i+1}/{len(claves)}] ⚠️ Vacía (0) en SRI")
                    fail_count += 1
                else:
                    fail_count += 1
            else:
                log.error(f"Error red: {resp}")
                fail_count += 1
            
            bar.progress((i+1)/len(claves))
            
    st.divider()
    if ok_count > 0:
        st.balloons()
        st.success(f"¡LOGRADO! {ok_count} facturas recuperadas.")
        st.download_button("📦 DESCARGAR XMLs", zip_buffer.getvalue(), "Facturas_Rescatadas.zip", "application/zip", type="primary")
    else:
        st.error(f"Fallaron {fail_count} facturas. Si todas fallaron, es probable que la Cookie ya haya caducado. Saca una nueva de Fiddler.")

