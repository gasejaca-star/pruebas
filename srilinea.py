import streamlit as st
import socket
import ssl
import gzip
import io
import re
import zipfile
import pandas as pd

st.set_page_config(page_title="SRI CLON EXACTO (FOTO FIDDLER)", layout="wide", page_icon="📸")

st.title("📸 SRI: CLON EXACTO (Cookie + Formato 412)")
st.markdown("""
**Diagnóstico Final:** El servidor requiere la **Cookie de Sesión (TS...)** para dirigirte al servidor correcto, y espera un XML con formato (no minificado).
**Instrucción:** Copia el valor de la Cookie `TSxxxx=` desde Fiddler y pégalo abajo.
""")

# --- LA PLANTILLA "FORMATEADA" (Basada en tu Foto 5) ---
# Fíjate que ahora tiene saltos de línea (\r\n) y espacios (indentación)
# Esto simula el peso de ~412 bytes que vemos en tu captura.
XML_FORMATO_ZOOM = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion">\r
   <soapenv:Header/>\r
   <soapenv:Body>\r
      <ec:autorizacionComprobante>\r
         \r
         <claveAccesoComprobante>{}</claveAccesoComprobante>\r
      </ec:autorizacionComprobante>\r
   </soapenv:Body>\r
</soapenv:Envelope>"""

def descargar_con_cookie_robada(clave, cookie_valor):
    host = "cel.sri.gob.ec"
    port = 443
    
    # 1. Preparar el XML con espacios (Como en la foto)
    body = XML_FORMATO_ZOOM.format(clave.strip())
    body_bytes = body.encode('utf-8')
    
    # 2. HEADERS EXACTOS DE TU CAPTURA (FOTO 2 y 5)
    # Incluimos la COOKIE que es la llave de acceso al servidor bueno.
    headers = (
        "POST /comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl HTTP/1.1\r\n"
        "Accept: */*\r\n"
        "Accept-Encoding: gzip, deflate\r\n"  # <--- Como en Foto 2
        "Accept-Language: es-MX,es-EC;q=0.7,es;q=0.3\r\n"
        "User-Agent: Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; WOW64; Trident/7.0; .NET4.0C; .NET4.0E; Zoom 3.6.0)\r\n"
        "Host: cel.sri.gob.ec\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        "Connection: Keep-Alive\r\n"
        "Cache-Control: no-cache\r\n"
        f"Cookie: {cookie_valor.strip()}\r\n" # <--- LA CLAVE MAESTRA
        "SOAPAction: \"\"\r\n" # A veces necesario aunque no salga
        "\r\n"
    )
    
    full_payload = headers.encode('latin-1') + body_bytes

    # 3. CONTEXTO SSL (Igual que antes, seguridad baja para servidor viejo)
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
                
                # 4. PROCESAR
                header_end = response_data.find(b"\r\n\r\n")
                if header_end != -1:
                    raw_body = response_data[header_end+4:]
                    
                    # GZIP?
                    if raw_body.startswith(b'\x1f\x8b'):
                        try:
                            with gzip.GzipFile(fileobj=io.BytesIO(raw_body)) as f:
                                return True, f.read().decode('utf-8')
                        except:
                            return False, "Error Descompresión"
                    else:
                        return True, raw_body.decode('utf-8', errors='ignore')
                        
        return False, "Sin conexión"
    except Exception as e:
        return False, str(e)

# --- INTERFAZ ---
col1, col2 = st.columns([1, 2])
with col1:
    archivo = st.file_uploader("1. Sube tu TXT:", type=["txt"])
with col2:
    cookie_input = st.text_input("2. Pega la COOKIE de Fiddler (TSxxxx=...):", help="Copia todo el texto de la Cookie de la Foto 4")

if archivo and cookie_input and st.button("EJECUTAR CLON CON COOKIE"):
    try: content = archivo.read().decode("latin-1")
    except: content = archivo.read().decode("utf-8", errors="ignore")
    claves = list(dict.fromkeys(re.findall(r'\d{49}', content)))
    
    if not claves: st.stop()
    
    bar = st.progress(0)
    zip_buffer = io.BytesIO()
    ok_count = 0
    fail_count = 0
    errores = []

    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for i, cl in enumerate(claves):
            exito, resultado = descargar_con_cookie_robada(cl, cookie_input)
            
            if exito and "<autorizacion>" in resultado:
                match = re.search(r'(<autorizacion>.*?</autorizacion>)', resultado, re.DOTALL)
                if match:
                    zf.writestr(f"{cl}.xml", match.group(1))
                    ok_count += 1
            else:
                fail_count += 1
                if "numeroComprobantes>0" in str(resultado):
                    errores.append({"CLAVE": cl, "ERROR": "0 Comprobantes (¿Cookie caducada?)"})
                else:
                    errores.append({"CLAVE": cl, "ERROR": str(resultado)[:100]})
            
            bar.progress((i+1)/len(claves))

    if ok_count > 0:
        st.balloons()
        st.success(f"¡SÍ! {ok_count} facturas recuperadas usando la sesión de Zoom.")
        st.download_button("📦 DESCARGAR ZIP", zip_buffer.getvalue(), "Facturas_Cookie_Zoom.zip", "application/zip", type="primary")
    
    if fail_count > 0:
        st.warning(f"Fallaron {fail_count}. Asegúrate de copiar la cookie fresca de una petición que ACABE de funcionar en Zoom.")
        with st.expander("Ver errores"):
            st.dataframe(pd.DataFrame(errores))

