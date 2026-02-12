import streamlit as st
import socket
import ssl
import gzip
import io
import re
import zipfile
import pandas as pd

st.set_page_config(page_title="SRI COMBO FINAL", layout="wide", page_icon="🔥")

st.title("🔥 SRI: EL COMBO SUPREMO (BOM + GZIP)")
st.markdown("""
Esta es la herramienta definitiva. Envía la petición con **todas** las trampas posibles:
1.  **BOM (\\xef\\xbb\\xbf):** Caracteres invisibles de Microsoft al inicio.
2.  **GZIP:** Pide la respuesta comprimida.
3.  **Socket Crudo:** Sin librerías modernas de Python.
""")

XML_TEMPLATE = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion">\r
   <soapenv:Header/>\r
   <soapenv:Body>\r
      <ec:autorizacionComprobante>\r
         \r
         <claveAccesoComprobante>{}</claveAccesoComprobante>\r
      </ec:autorizacionComprobante>\r
   </soapenv:Body>\r
</soapenv:Envelope>"""

def descargar_combo_supremo(clave):
    host = "cel.sri.gob.ec"
    port = 443
    
    # 1. PREPARAR EL XML CON BOM (CARACTERES ESCONDIDOS)
    # EF BB BF son los bytes mágicos que Zoom envía al principio
    BOM = b'\xef\xbb\xbf'
    xml_limpio = XML_TEMPLATE.format(clave.strip())
    body_bytes = BOM + xml_limpio.encode('utf-8') # <--- AQUÍ ESTÁ EL TRUCO
    
    # 2. HEADER EXACTO (Con largo calculado incluyendo el BOM)
    headers = (
        "POST /comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl HTTP/1.1\r\n"
        "Accept: */*\r\n"
        "Accept-Language: es-MX,es-EC;q=0.7,es;q=0.3\r\n"
        "Accept-Encoding: gzip, deflate\r\n" # <--- PEDIMOS GZIP
        "User-Agent: Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; WOW64; Trident/7.0; .NET4.0C; .NET4.0E; Zoom 3.6.0)\r\n"
        "Host: cel.sri.gob.ec\r\n"
        "Content-Type: text/xml;charset=UTF-8\r\n"
        f"Content-Length: {len(body_bytes)}\r\n" # <--- LARGO PRECISO
        "Connection: Keep-Alive\r\n"
        "SOAPAction: \"\"\r\n"
        "\r\n"
    )
    
    # Paquete final mixto (Latin-1 para headers, UTF-8 con BOM para body)
    full_payload = headers.encode('latin-1') + body_bytes

    # 3. SSL LEGACY
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.set_ciphers('DEFAULT@SECLEVEL=1') 
    
    try:
        with socket.create_connection((host, port), timeout=15) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                ssock.sendall(full_payload)
                
                # Leer respuesta
                response_data = b""
                while True:
                    chunk = ssock.recv(4096)
                    if not chunk: break
                    response_data += chunk
                
                # 4. PROCESAR RESPUESTA (EXTRAER GZIP)
                header_end = response_data.find(b"\r\n\r\n")
                if header_end != -1:
                    raw_body = response_data[header_end+4:]
                    
                    # Intentar descomprimir GZIP
                    if raw_body.startswith(b'\x1f\x8b'):
                        try:
                            with gzip.GzipFile(fileobj=io.BytesIO(raw_body)) as f:
                                return True, f.read().decode('utf-8')
                        except:
                            return False, "Error GZIP corrupto"
                    else:
                        # Si no es GZIP, devolvemos texto plano
                        return True, raw_body.decode('utf-8', errors='ignore')
                        
        return False, "Sin respuesta"
    except Exception as e:
        return False, str(e)

# --- INTERFAZ ---
archivo = st.file_uploader("Sube tu TXT:", type=["txt"])

if archivo and st.button("EJECUTAR RESCATE FINAL"):
    try: content = archivo.read().decode("latin-1")
    except: content = archivo.read().decode("utf-8", errors="ignore")
    claves = list(dict.fromkeys(re.findall(r'\d{48,49}', content)))
    
    if not claves: st.stop()
    
    bar = st.progress(0)
    status = st.empty()
    zip_buffer = io.BytesIO()
    ok_count = 0
    reporte = []

    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for i, cl in enumerate(claves):
            status.text(f"Procesando {cl}...")
            exito, resultado = descargar_combo_supremo(cl)
            
            estado = "FALLO"
            if exito:
                if "<autorizacion>" in resultado:
                    match = re.search(r'(<autorizacion>.*?</autorizacion>)', resultado, re.DOTALL)
                    if match:
                        zf.writestr(f"{cl}.xml", match.group(1))
                        ok_count += 1
                        estado = "OK"
                elif "numeroComprobantes>0" in resultado:
                    estado = "VACIO (0)"
            
            reporte.append({"CLAVE": cl, "ESTADO": estado})
            bar.progress((i+1)/len(claves))

    if ok_count > 0:
        st.balloons()
        st.success(f"¡VICTORIA! {ok_count} facturas recuperadas.")
        st.download_button("📦 DESCARGAR TODO", zip_buffer.getvalue(), "Facturas_Supremas.zip", "application/zip", type="primary")
    else:
        st.error("Si esto falló, el servidor del SRI no tiene esas facturas sincronizadas para descarga externa.")
        st.dataframe(pd.DataFrame(reporte))
