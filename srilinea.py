import streamlit as st
import socket
import ssl
import gzip
import io
import re
import zipfile

st.set_page_config(page_title="SRI RESCATE TOTAL", layout="wide", page_icon="🚑")

st.title("🚑 SRI: RESCATISTA GZIP (Enero 1-8)")
st.markdown("""
Este script utiliza la técnica **"Zoom Simulation + GZIP"**.
Se conecta al servidor Legacy, pide los datos comprimidos (como lo hace el programa antiguo) y los descomprime para recuperar las facturas "invisibles".
""")

# --- CONFIGURACIÓN DEL DISFRAZ ---
XML_BODY_TEMPLATE = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion">\r
   <soapenv:Header/>\r
   <soapenv:Body>\r
      <ec:autorizacionComprobante>\r
         \r
         <claveAccesoComprobante>{}</claveAccesoComprobante>\r
      </ec:autorizacionComprobante>\r
   </soapenv:Body>\r
</soapenv:Envelope>"""

def rescatar_factura(clave):
    host = "cel.sri.gob.ec"
    port = 443
    
    # 1. Preparar el cuerpo exacto
    body = XML_BODY_TEMPLATE.format(clave.strip())
    
    # 2. Preparar Headers (La clave es Accept-Encoding: gzip)
    headers = (
        "POST /comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl HTTP/1.1\r\n"
        "Accept: */*\r\n"
        "Accept-Language: es-MX,es-EC;q=0.7,es;q=0.3\r\n"
        "Accept-Encoding: gzip, deflate\r\n"  # <--- EL SECRETO
        "User-Agent: Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; WOW64; Trident/7.0; .NET4.0C; .NET4.0E; Zoom 3.6.0)\r\n"
        "Host: cel.sri.gob.ec\r\n"
        "Content-Type: text/xml;charset=UTF-8\r\n"
        f"Content-Length: {len(body.encode('utf-8'))}\r\n"
        "Connection: Keep-Alive\r\n"
        "SOAPAction: \"\"\r\n"
        "\r\n"
    )
    
    full_payload = headers + body

    # 3. Contexto SSL Legacy
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.set_ciphers('DEFAULT@SECLEVEL=1') 
    
    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                ssock.sendall(full_payload.encode('utf-8'))
                
                # Leer respuesta
                response_data = b""
                while True:
                    chunk = ssock.recv(4096)
                    if not chunk: break
                    response_data += chunk
                
                # 4. Separar y Descomprimir
                header_end = response_data.find(b"\r\n\r\n")
                if header_end != -1:
                    raw_body = response_data[header_end+4:]
                    
                    # Intentar GZIP
                    if raw_body.startswith(b'\x1f\x8b'):
                        with gzip.GzipFile(fileobj=io.BytesIO(raw_body)) as f:
                            xml_str = f.read().decode('utf-8')
                            return True, xml_str
                    else:
                        # Si no vino comprimido, intentar leer directo
                        return True, raw_body.decode('utf-8', errors='ignore')
                        
        return False, "Conexión vacía"
    except Exception as e:
        return False, str(e)

# --- INTERFAZ ---
archivo = st.file_uploader("Sube tu TXT con las claves faltantes:", type=["txt"])

if archivo and st.button("INICIAR RESCATE"):
    try: content = archivo.read().decode("latin-1")
    except: content = archivo.read().decode("utf-8", errors="ignore")
    claves = list(dict.fromkeys(re.findall(r'\d{48,49}', content)))
    
    if not claves: st.stop()

    bar = st.progress(0)
    status = st.empty()
    zip_buffer = io.BytesIO()
    ok_count = 0
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for i, cl in enumerate(claves):
            status.text(f"Rescatando {i+1}/{len(claves)}: {cl}...")
            
            exito, resultado = rescatar_factura(cl)
            
            if exito and "<autorizacion>" in resultado:
                # Extraer solo el bloque de autorización limpio
                match = re.search(r'(<autorizacion>.*?</autorizacion>)', resultado, re.DOTALL)
                if match:
                    xml_limpio = match.group(1)
                    zf.writestr(f"{cl}.xml", xml_limpio)
                    ok_count += 1
            
            bar.progress((i+1)/len(claves))

    st.success(f"✅ Misión Cumplida: {ok_count} facturas recuperadas.")
    if ok_count > 0:
        st.download_button("📦 DESCARGAR XMLs RESCATADOS", zip_buffer.getvalue(), "Enero_Rescatado.zip", "application/zip", type="primary")
