# --- BLOQUE DE PRUEBA HÍBRIDO (OFFLINE + ONLINE) ---

def bloque_sri(titulo, tipo_filtro, key):
    st.subheader(f"🧪 Test Híbrido: {titulo}")
    up = st.file_uploader(f"Cargar TXT para {titulo}", type=["txt"], key=key)
    
    if up and st.button(f"Iniciar Descarga Híbrida", key=f"b_{key}"):
        # 1. Extracción de Claves
        content = up.read().decode("latin-1", errors="ignore")
        # Regex 48,49 para capturar incluso si Excel se comió el 0 inicial
        claves = list(dict.fromkeys(re.findall(r'\d{48,49}', content)))
        
        if claves:
            registrar_actividad(st.session_state.usuario_actual, f"TEST SRI {titulo}", len(claves))
            
            # Barras y contenedores
            bar = st.progress(0)
            status = st.empty()
            log_box = st.expander("📝 Bitácora de Conexión (Ver detalles)", expanded=True)
            
            lst = []
            errores = 0 
            recuperadas_online = 0
            zip_buffer = io.BytesIO()
            
            # 2. Configuración de Sesión (Vital para estabilidad)
            session = requests.Session()
            session.verify = False
            session.headers.update(HEADERS_WS)

            # 3. URLs de los dos ambientes del SRI
            URL_OFFLINE = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"
            URL_ONLINE  = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantes?wsdl"

            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
                for i, cl in enumerate(claves):
                    exito = False
                    origen = ""
                    
                    # Cuerpo del mensaje SOAP (Es igual para ambos)
                    body = f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion"><soapenv:Body><ec:autorizacionComprobante><claveAccesoComprobante>{cl}</claveAccesoComprobante></ec:autorizacionComprobante></soapenv:Body></soapenv:Envelope>'

                    # --- INTENTO 1: AMBIENTE OFFLINE (Rápido) ---
                    try:
                        time.sleep(0.2) # Breve pausa
                        r = session.post(URL_OFFLINE, data=body, timeout=8)
                        
                        # Validamos si TRAE autorización real (no solo respuesta vacía)
                        if r.status_code == 200 and "<autorizaciones>" in r.text and "<autorizacion>" in r.text:
                            zf.writestr(f"{cl}.xml", r.text)
                            d = extraer_datos_robusto(io.BytesIO(r.content))
                            if d: lst.append(d)
                            exito = True
                            origen = "OFFLINE"
                    except: pass

                    # --- INTENTO 2: AMBIENTE ONLINE (Rescate) ---
                    # Si falló el Offline, probamos el Online (donde suelen quedarse las trabadas)
                    if not exito:
                        try:
                            time.sleep(1.5) # Pausa más larga para cambiar de servidor
                            r = session.post(URL_ONLINE, data=body, timeout=12)
                            
                            if r.status_code == 200 and "<autorizaciones>" in r.text and "<autorizacion>" in r.text:
                                zf.writestr(f"{cl}.xml", r.text)
                                d = extraer_datos_robusto(io.BytesIO(r.content))
                                if d: lst.append(d)
                                exito = True
                                origen = "ONLINE (RESCATADA)"
                                recuperadas_online += 1
                        except Exception as e:
                            pass # Si falla aquí, ya no hay más opciones

                    # --- RESULTADO FINAL ---
                    if exito:
                        log_box.write(f"✅ {i+1}. {cl[-10:]}... -> DESCARGADO vía {origen}")
                    else:
                        errores += 1
                        log_box.error(f"❌ {i+1}. {cl[-10:]}... -> NO ENCONTRADO en ningún ambiente.")

                    # Actualizar barra
                    bar.progress((i + 1) / len(claves))
                    status.text(f"Procesando {i+1}/{len(claves)} | Online: {recuperadas_online} | Offline: {len(lst)-recuperadas_online}")

            # 4. Resultados
            if lst: 
                st.success(f"🎉 Proceso Finalizado. Total XMLs: {len(lst)}")
                if recuperadas_online > 0:
                    st.info(f"✨ NOTA: Se rescataron {recuperadas_online} facturas usando el servidor ONLINE (las que antes fallaban).")
                
                c1, c2 = st.columns(2)
                with c1: st.download_button(f"📦 Descargar ZIP", zip_buffer.getvalue(), f"{titulo}.zip")
                with c2: st.download_button(f"📊 Descargar Excel", generar_excel_multiexcel(data_sri_lista=lst, sri_mode=tipo_filtro), f"{titulo}.xlsx")
            else:
                st.error("No se pudo descargar ningún documento válido.")
        else:
             st.warning("No se encontraron claves válidas en el archivo.")
