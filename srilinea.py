import streamlit as st
import socket
import ssl
import gzip
import io
import re
import zipfile

st.set_page_config(page_title="SRI: MODO NUCLEAR", layout="wide", page_icon="☢️")

st.title("☢️ SRI: MODO NUCLEAR (SOCKET CRUDO + SSL INSEGURO)")
st.markdown("""
**Diagnóstico:** El servidor SRI detecta que eres Python por tu "forma de saludar" (SSL Handshake) o por headers extra.
**Solución:** Este script fuerza encriptación antigua (SECLEVEL=0) y envía los headers **exactos** de tu captura, sin agregar nada más.
""")

# COOKIE (Pégala aquí si quieres dejarla fija, o úsala en el input de abajo)
COOKIE_DEFAULT = "TS010a7529=PON_AQUI_TU_COOKIE_FRESCA"

# XML EXACTO (Con tus espacios y saltos de línea)
XML_BODY = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion">
   <soapenv:Header/>
   <soapenv:Body>
      <ec:autorizacionComprobante>
         <claveAccesoComprobante>{}</claveAccesoComprobante>
      </ec:autorizacionComprobante>
   </soapenv:Body>
</soapenv:Envelope>"""

def descargar_modo_nuclear(clave, cookie_valor):
    host = "cel.sri.gob.ec"
    port = 443
    
    # 1. Preparar el Cuerpo (Aseguramos saltos de línea Windows \r\n)
    # Tu captura tiene espacios, así que los respetamos.
    cuerpo = XML_BODY.format(clave.strip()).replace('\n', '\r\n')
    cuerpo_bytes = cuerpo.encode('utf-8')
    largo = len(cuerpo_bytes)

    # 2. CONSTRUCCIÓN MANUAL DEL PAQUETE HTTP (TEXTO PLANO)
    # Copiado EXACTO de tu captura de texto.
    # NOTA: No ponemos Content-Type porque en tu captura NO estaba.
    request_raw = (
        f"POST /comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl HTTP/1.1\r\n"
        f"Accept: */*\r\n" # Corregido de tu texto 'Accept: /' que parece error de OCR, usualmente es */*
        f"Accept-Language: es-MX,es-EC;q=0.7,es;q=0.3\r\n"
        f"Accept-Encoding: gzip, deflate\r\n"
        f"User-Agent: Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; WOW64; Trident/7.0; .NET4.0C; .NET4.0E; Zoom 3.6.0)\r\n"
        f"Host: cel.sri.gob.ec\r\n"
        f"Content-Length: {largo}\r\n"
        f"Connection: Keep-Alive\r\n"
        f"Cache-Control: no-cache\r\n"
        f"Cookie: {cookie_valor.strip()}\r\n"
        f"\r\n" # Doble salto de línea para indicar fin de headers
    )
    
    # Unir Headers y Cuerpo
    paquete_completo = request_raw.encode('latin-1') + cuerpo_bytes

    # 3. SSL "SUCIO" (Downgrade de seguridad para imitar software viejo)
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    # ESTA ES LA CLAVE: Habilitar cifrados viejos e inseguros que usa el SRI Legacy
    try:
        context.set_ciphers('DEFAULT@SECLEVEL=0')
    except:
        # Si falla (Linux a veces no deja), intentamos ciphers genéricos
        context.set_ciphers('ALL')

    try:
        # Abrir Socket TCP Puro
        with socket.create_connection((host, port), timeout=15) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                # Enviar los bytes crudos
                ssock.sendall(paquete_completo)
                
                # Leer respuesta
                response_data = b""
                while True:
                    chunk = ssock.recv(4096)
                    if not chunk: break
                    response_data += chunk
                
                # 4. Procesar
                header_end = response_data.find(b"\r\n\r\n")
                if header_end != -1:
                    raw_body = response_data[header_end+4:]
                    
                    # Intentar GZIP
                    if raw_body.startswith(b'\x1f\x8b'):
                        try:
                            with gzip.GzipFile(fileobj=io.BytesIO(raw_body)) as f:
                                return True, f.read().decode('utf-8')
                        except:
                            return False, "Error Descompresión GZIP"
                    else:
                        return True, raw_body.decode('utf-8', errors='ignore')
        return False, "Sin conexión / Timeout"
    except Exception as e:
        return False, f"Error SSL/Socket: {str(e)}"

# --- INTERFAZ ---
st.warning("⚠️ IMPORTANTE: Usa la cookie más reciente posible. Si Zoom funciona, copia la cookie AHORA y pégala aquí.")
col1, col2 = st.columns([1, 2])
with col1:
    archivo = st.file_uploader("Archivo de Claves (TXT):", type=["txt"])
with col2:
    cookie_input = st.text_input("Pegar Cookie TS...:", value="")

if archivo and cookie_input and st.button("🔥 LANZAR MODO NUCLEAR"):
    try: content = archivo.read().decode("latin-1")
    except: content = archivo.read().decode("utf-8", errors="ignore")
    claves = list(dict.fromkeys(re.findall(r'\d{49}', content)))
    
    if not claves: st.error("No hay claves."); st.stop()
    
    bar = st.progress(0)
    log = st.empty()
    zip_buffer = io.BytesIO()
    ok = 0
    fail = 0
    
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
        for i, cl in enumerate(claves):
            exito, resp = descargar_modo_nuclear(cl, cookie_input)
            
            if exito:
                if "<autorizacion>" in resp:
                    match = re.search(r'(<autorizacion>.*?</autorizacion>)', resp, re.DOTALL)
                    if match:
                        zf.writestr(f"{cl}.xml", match.group(1))
                        ok += 1
                        log.success(f"[{i+1}] ✅ RECUPERADA: {cl[-8:]}")
                    else:
                        fail += 1
                elif "numeroComprobantes>0" in resp:
                    # Si sale esto, el SSL funcionó pero el servidor dice que no existe.
                    # Significa que la cookie NO nos llevó al servidor correcto o la clave está mal.
                    fail += 1
                    # log.warning(f"[{i+1}] Servidor respondió 0 comprobantes.") 
                else:
                    fail += 1
            else:
                log.error(f"Error técnico: {resp}")
                fail += 1
            
            bar.progress((i+1)/len(claves))
            
    if ok > 0:
        st.balloons()
        st.success(f"¡FUNCIONÓ! {ok} facturas rescatadas.")
        st.download_button("📦 DESCARGAR ZIP", zip_buffer.getvalue(), "Nuclear_Rescate.zip", "application/zip", type="primary")
    else:
        st.error("Resultado: 0 Recuperadas. Si sigue saliendo '0 comprobantes', el balanceador de carga del SRI ha vinculado tu Cookie a la IP/Sesión exacta de Zoom y la rechaza desde Python, o el servidor backend cambió en ese milisegundo.")
