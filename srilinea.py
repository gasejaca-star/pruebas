import streamlit as st
import requests
import time
import re
import io
import zipfile
import urllib3

# Desactivar advertencias de SSL (necesario para el SRI)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- MÓDULO DE DESCARGA HÍBRIDA (OFFLINE + ONLINE) ---
def bloque_sri(titulo, tipo_filtro, key):
    # 1. Configuración de URLs y Headers dentro del módulo para asegurar visibilidad
    URL_OFFLINE = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"
    URL_ONLINE  = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantes?wsdl"
    HEADERS_WS = {
        "Content-Type": "text/xml;charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }

    st.subheader(f"{titulo} (Modo Híbrido)")
    up = st.file_uploader(f"Cargar TXT para {titulo}", type=["txt"], key=key)
    
    if up and st.button(f"Iniciar Descarga", key=f"b_{key}"):
        # 2. Lectura y Limpieza del TXT
        try:
            content = up.read().decode("latin-1", errors="ignore")
        except:
            content = up.read().decode("utf-8", errors="ignore")
            
        # Regex 48,49 para capturar claves incluso si Excel borró el '0' inicial
        claves = list(dict.fromkeys(re.findall(r'\d{48,49}', content)))
        
        if claves:
            registrar_actividad(st.session_state.usuario_actual, f"INICIÓ DESCARGA {titulo}", len(claves))
            
            # Inicializar UI
            bar = st.progress(0)
            status = st.empty()
            log_box = st.expander("📝 Bitácora de Recuperación (Ver detalles)", expanded=True)
            
            lst = []
            errores = 0 
            recuperadas_online = 0
            zip_buffer = io.BytesIO()
            
            # 3. Sesión Persistente (Vital para evitar bloqueos del SRI)
            session = requests.Session()
            session.verify = False
            session.headers.update(HEADERS_WS)

            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
                for i, cl in enumerate(claves):
                    exito = False
                    origen = ""
                    
                    # Cuerpo del mensaje SOAP
                    body = f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion"><soapenv:Body><ec:autorizacionComprobante><claveAccesoComprobante>{cl}</claveAccesoComprobante></ec:autorizacionComprobante></soapenv:Body></soapenv:Envelope>'

                    # --- INTENTO 1: AMBIENTE OFFLINE (Base de datos estándar) ---
                    try:
                        time.sleep(0.2) # Pausa técnica
                        r = session.post(URL_OFFLINE, data=body, timeout=8)
                        
                        # Validamos que la respuesta tenga contenido real
                        if r.status_code == 200 and "<autorizaciones>" in r.text and "<autorizacion>" in r.text:
                            zf.writestr(f"{cl}.xml", r.text)
                            d = extraer_datos_robusto(io.BytesIO(r.content)) # Llama a tu función externa
                            
                            # Filtro de tipo de documento
                            if d and ((tipo_filtro == "RET" and d["TIPO"] == "RET") or (tipo_filtro == "NC" and d["TIPO"] == "NC") or (tipo_filtro == "FC" and d["TIPO"] in ["FC","LC"])): 
                                lst.append(d)
                                exito = True
                                origen = "OFFLINE"
                    except Exception: pass

                    # --- INTENTO 2: AMBIENTE ONLINE (Base de datos de respaldo) ---
                    # Si falló el Offline (0 comprobantes), buscamos en el Online
                    if not exito:
                        try:
                            time.sleep(1.5) # Pausa mayor para cambio de servidor
                            r = session.post(URL_ONLINE, data=body, timeout=12)
                            
                            if r.status_code == 200 and "<autorizaciones>" in r.text and "<autorizacion>" in r.text:
                                zf.writestr(f"{cl}.xml", r.text)
                                d = extraer_datos_robusto(io.BytesIO(r.content))
                                
                                if d and ((tipo_filtro == "RET" and d["TIPO"] == "RET") or (tipo_filtro == "NC" and d["TIPO"] == "NC") or (tipo_filtro == "FC" and d["TIPO"] in ["FC","LC"])): 
                                    lst.append(d)
                                    exito = True
                                    origen = "ONLINE"
                                    recuperadas_online += 1
                        except Exception: pass

                    # --- BITÁCORA VISUAL ---
                    if exito:
                        if origen == "ONLINE":
                            log_box.success(f"✅ {i+1}. {cl[-10:]}... RECUPERADA (ONLINE)")
                    else:
                        errores += 1
                        # Opcional: log_box.warning(f"❌ {i+1}. {cl[-10:]}... No encontrada")

                    # Actualizar barra
                    bar.progress((i + 1) / len(claves))
                    status.text(f"Procesando {i+1}/{len(claves)} | Rescatadas Online: {recuperadas_online} | Total OK: {len(lst)}")

            # 4. Resultados Finales
            if lst: 
                st.success(f"🎉 Proceso Finalizado. {len(lst)} documentos procesados correctamente.")
                if recuperadas_online > 0:
                    st.info(f"✨ ÉXITO: El sistema rescató {recuperadas_online} facturas del servidor ONLINE que antes fallaban.")
                
                registrar_actividad(st.session_state.usuario_actual, f"GENERÓ EXCEL SRI {titulo}", len(lst))
                
                c1, c2 = st.columns(2)
                with c1: st.download_button(f"📦 ZIP XMLs {titulo}", zip_buffer.getvalue(), f"{titulo}.zip")
                with c2: st.download_button(f"📊 Excel {titulo}", generar_excel_multiexcel(data_sri_lista=lst, sri_mode=tipo_filtro), f"{titulo}.xlsx")
            else:
                st.error("No se pudo descargar ningún documento. Verifique si el SRI está en mantenimiento.")
        else:
             st.warning("No se encontraron claves válidas (48 o 49 dígitos) en el archivo.")
