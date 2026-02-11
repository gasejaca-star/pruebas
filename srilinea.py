import requests
import streamlit as st

# CLAVE QUE FALLA (La primera de tu lista: Satrack 01/01)
CLAVE_PRUEBA = "0101202601179233732100120010010001736100017361016" 

st.subheader("🕵️‍♂️ Diagnóstico SRI - Rayos X")

if st.button("Consultar Clave Específica"):
    url = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"
    # Headers exactos para evitar bloqueos
    headers = {"Content-Type": "text/xml;charset=UTF-8"}
    
    # El cuerpo exacto de la solicitud
    body = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion">
       <soapenv:Body>
          <ec:autorizacionComprobante>
             <claveAccesoComprobante>{CLAVE_PRUEBA}</claveAccesoComprobante>
          </ec:autorizacionComprobante>
       </soapenv:Body>
    </soapenv:Envelope>"""

    try:
        with st.spinner("Consultando al SRI..."):
            r = requests.post(url, data=body, headers=headers, verify=False, timeout=15)
        
        st.write(f"**Estado HTTP:** {r.status_code}")
        
        # Muestra la respuesta COMPLETA (Aquí veremos el error real)
        st.text_area("Respuesta Cruda del SRI:", value=r.text, height=300)
        
        if "AUTORIZADO" in r.text:
            st.success("✅ El SRI dice AUTORIZADO (El problema era tu código anterior)")
        elif "NO AUTORIZADO" in r.text:
            st.error("❌ El SRI dice NO AUTORIZADO (Lee el mensaje de error en el texto arriba)")
        else:
            st.warning("⚠️ Respuesta extraña (Posible bloqueo o mantenimiento)")
            
    except Exception as e:
        st.error(f"Error de conexión: {e}")
