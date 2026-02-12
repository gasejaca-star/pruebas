import streamlit as st
import socket
import ssl
import gzip
import io

st.set_page_config(page_title="SRI GZIP DECODER", layout="wide", page_icon="🔓")

st.title("🔓 DECODIFICADOR GZIP SRI")
st.markdown("""
Esta herramienta simula ser Zoom, recibe la respuesta "basura" (GZIP) y la descomprime para revelar la verdad.
Veremos si esos 236 bytes son una factura o un mensaje de error.
""")

# XML de prueba (El que sabemos que Zoom usa)
# NOTA: Reemplaza la CLAVE dentro de las llaves {} si quieres probar otra
XML_TEMPLATE = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion">\r
   <soapenv:Header/>\r
   <soapenv:Body>\r
      <ec:autorizacionComprobante>\r
         \r
         <claveAccesoComprobante>{}</claveAccesoComprobante>\r
      </ec:autorizacionComprobante>\r
   </soapenv:Body>\r
</soapenv:Envelope>"""

clave_input = st.text_input("Ingresa una CLAVE del 1-8 Enero que falle:", value="0101202601179206778200120010030226137300322130112")

if st.button("OBTENER Y DESCOMPRIMIR"):
    # Construimos el cuerpo
    body = XML_TEMPLATE.format(clave_input.strip())
    
    # Construimos los Headers IDÉNTICOS A ZOOM
    # Nota: Agregamos 'Accept-Encoding: gzip' para que el servidor nos mande el ZIP
    request = (
        "POST /comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl HTTP/1.1\r\n"
        "Accept: */*\r\n"
        "Accept-Language: es-MX,es-EC;q=0.7,es;q=0.3\r\n"
        "Accept-Encoding: gzip, deflate\r\n"
        "User-Agent: Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; WOW64; Trident/7.0; .NET4.0C; .NET4.0E; Zoom 3.6.0)\r\n"
        "Host: cel.sri.gob.ec\r\n"
        "Content-Type: text/xml;charset=UTF-8\r\n"
        f"Content-Length: {len(body.encode('utf-8'))}\r\n"
        "Connection: Keep-Alive\r\n"
        "SOAPAction: \"\"\r\n"
        "\r\n"  # Fin de headers
        f"{body}"
    )

    host = "cel.sri.gob.ec"
    port = 443
    
    # Contexto SSL Inseguro (Como Zoom)
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.set_ciphers('DEFAULT@SECLEVEL=1') 
    
    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                # Enviar petición
                ssock.sendall(request.encode('utf-8'))
                
                # Leer respuesta bruta
                response_data = b""
                while True:
                    chunk = ssock.recv(4096)
                    if not chunk: break
                    response_data += chunk
                
                # Separar Headers del Cuerpo (Body)
                header_end = response_data.find(b"\r\n\r\n")
                if header_end != -1:
                    raw_headers = response_data[:header_end].decode('latin-1')
                    raw_body = response_data[header_end+4:] # El contenido comprimido
                    
                    st.text("--- HEADERS RECIBIDOS ---")
                    st.code(raw_headers)
                    
                    st.text(f"--- CUERPO COMPRIMIDO ({len(raw_body)} bytes) ---")
                    st.caption("Esto es lo que antes veías como basura:")
                    st.code(str(raw_body[:50]) + "...", language="python")

                    # INTENTO DE DESCOMPRESIÓN (LA MAGIA)
                    st.subheader("🕵️ RESULTADO DESCOMPRIMIDO (LA VERDAD):")
                    try:
                        # Si es GZIP, empieza con bytes 1f 8b
                        if raw_body.startswith(b'\x1f\x8b'):
                            with gzip.GzipFile(fileobj=io.BytesIO(raw_body)) as f:
                                xml_real = f.read().decode('utf-8')
                                st.success("✅ ¡Descompresión Exitosa!")
                                st.code(xml_real, language="xml")
                                
                                if "numeroComprobantes>0" in xml_real:
                                    st.error("CONCLUSIÓN: El servidor respondió '0 Comprobantes'. Zoom tampoco la tiene en esta petición.")
                                else:
                                    st.balloons()
                                    st.success("CONCLUSIÓN: ¡SÍ HAY FACTURA! Hemos logrado replicar a Zoom.")
                        else:
                            st.warning("El cuerpo no parece ser GZIP válido. Intentando leer como texto plano...")
                            st.code(raw_body.decode('utf-8', errors='ignore'))
                            
                    except Exception as e:
                        st.error(f"Error al descomprimir: {e}")

    except Exception as e:
        st.error(f"Error de conexión: {e}")
