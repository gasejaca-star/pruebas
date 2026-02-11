import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import re
import io
import requests
import zipfile
import urllib3
import time
import xlsxwriter

# --- CONFIGURACIÓN DE LA APP ---
st.set_page_config(page_title="SRI Recovery Tool", layout="wide", page_icon="🚑")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONSTANTES ---
URL_OFFLINE = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"
URL_ONLINE  = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantes?wsdl"
HEADERS_WS = {"Content-Type": "text/xml;charset=UTF-8", "User-Agent": "Mozilla/5.0"}

# --- FUNCIONES DE EXTRACCIÓN (CORE) ---
def extraer_datos_xml(xml_content):
    try:
        tree = ET.parse(io.BytesIO(xml_content))
        root = tree.getroot()
        xml_data = None
        
        # 1. Desempaquetar SOAP
        for elem in root.iter():
            if 'comprobante' in elem.tag.lower() and elem.text and "<" in elem.text:
                try:
                    clean_text = re.sub(r'<\?xml.*?\?>', '', elem.text).strip()
                    xml_data = ET.fromstring(clean_text)
                    break
                except: continue
        
        if xml_data is None: xml_data = root # Si no es SOAP, usar raíz directa

        # 2. Datos Clave
        def buscar(tags):
            for t in tags:
                f = xml_data.find(f".//{t}")
                if f is not None and f.text: return f.text.strip()
            return ""
            
        def buscar_float(tags):
            val = buscar(tags)
            return float(val) if val else 0.0

        tipo_doc = "FC"
        tag = xml_data.tag.lower()
        if 'notacredito' in tag: tipo_doc = "NC"
        elif 'comprobanteretencion' in tag: tipo_doc = "RET"
        elif 'liquidacion' in tag: tipo_doc = "LC"

        # 3. Construir Diccionario
        data = {
            "TIPO": tipo_doc,
            "FECHA": buscar(["fechaEmision"]),
            "RUC": buscar(["ruc"]),
            "RAZON_SOCIAL": buscar(["razonSocial"]).upper(),
            "N_FACTURA": f"{buscar(['estab'])}-{buscar(['ptoEmi'])}-{buscar(['secuencial'])}",
            "AUTORIZACION": buscar(["numeroAutorizacion", "claveAcceso"]),
            "CLIENTE": buscar(["razonSocialComprador", "razonSocialSujetoRetenido"]).upper(),
            "RUC_CLIENTE": buscar(["identificacionComprador", "identificacionSujetoRetenido"]),
            "TOTAL": 0.0, "IVA": 0.0, "BASE_0": 0.0, "BASE_12": 0.0
        }

        # 4. Extraer Valores (Solo Facturas/NC)
        if tipo_doc in ["FC", "NC", "LC"]:
            m = -1 if tipo_doc == "NC" else 1
            data["TOTAL"] = buscar_float(["importeTotal", "valorModificado"]) * m
            
            for imp in xml_data.findall(".//totalImpuesto"):
                try:
                    cod = imp.find("codigo").text
                    cod_por = imp.find("codigoPorcentaje").text
                    base = float(imp.find("baseImponible").text or 0) * m
                    val = float(imp.find("valor").text or 0) * m
                    
                    if cod == "2": # IVA
                        data["IVA"] += val
                        if cod_por == "0": data["BASE_0"] += base
                        elif cod_por in ["2", "3", "4", "8", "10"]: data["BASE_12"] += base
                except: continue
        
        # 5. Extraer Retenciones (Solo RET)
        elif tipo_doc == "RET":
            for imp in xml_data.findall(".//impuesto"):
                cod = imp.find("codigo").text
                val = float(imp.find("valorRetenido").text or 0)
                if cod == "1": data["TOTAL"] += val # Renta
                if cod == "2": data["TOTAL"] += val # IVA

        return data
    except: return None

def generar_excel_simple(lista_datos):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df = pd.DataFrame(lista_datos)
        
        # Ordenar columnas
        cols = ["FECHA", "TIPO", "N_FACTURA", "RUC", "RAZON_SOCIAL", "RUC_CLIENTE", "CLIENTE", "BASE_0", "BASE_12", "IVA", "TOTAL", "AUTORIZACION"]
        for c in cols: 
            if c not in df.columns: df[c] = ""
        df = df[cols]

        # Formato
        wb = writer.book
        ws = wb.add_worksheet("REPORTE_SRI")
        ws.write_row(0, 0, df.columns, wb.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1}))
        
        # Escribir datos
        fmt_num = wb.add_format({'num_format': '0.00'})
        for row_num, row_data in enumerate(df.values, 1):
            for col_num, cell_data in enumerate(row_data):
                if isinstance(cell_data, float):
                    ws.write(row_num, col_num, cell_data, fmt_num)
                else:
                    ws.write(row_num, col_num, cell_data)
        
        ws.set_column(0, 12, 20) # Ajustar ancho
        writer.close() 
    return output.getvalue()

# --- INTERFAZ PRINCIPAL ---
st.title("🚑 SRI RECOVERY TOOL")
st.markdown("### Recuperador de Facturas (Offline + Online)")
st.info("Esta herramienta usa una estrategia híbrida para recuperar facturas que fallan por bloqueos o retrasos del SRI.")

# 1. Carga
archivo = st.file_uploader("Sube tu archivo TXT del SRI aquí:", type=["txt"])

if archivo:
    if st.button("🚀 INICIAR RECUPERACIÓN", type="primary"):
        
        # 2. Lectura Segura
        try: content = archivo.read().decode("latin-1")
        except: content = archivo.read().decode("utf-8", errors="ignore")
        
        claves = list(dict.fromkeys(re.findall(r'\d{48,49}', content)))
        
        if not claves:
            st.error("No se encontraron claves de 49 dígitos en el archivo.")
            st.stop()
            
        st.write(f"**Total Claves Encontradas:** {len(claves)}")
        
        # 3. Proceso de Descarga
        bar = st.progress(0)
        status_text = st.empty()
        log_container = st.container() # Para logs en vivo
        
        session = requests.Session()
        session.verify = False
        session.headers.update(HEADERS_WS)
        
        zip_buffer = io.BytesIO()
        datos_reporte = []
        conteo = {"OK_OFFLINE": 0, "OK_ONLINE": 0, "FALLOS": 0}
        
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
            for i, cl in enumerate(claves):
                # Mensaje SOAP
                soap = f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion"><soapenv:Body><ec:autorizacionComprobante><claveAccesoComprobante>{cl}</claveAccesoComprobante></ec:autorizacionComprobante></soapenv:Body></soapenv:Envelope>'
                
                exito = False
                
                # --- INTENTO 1: OFFLINE ---
                try:
                    time.sleep(0.1) # Micro pausa
                    r = session.post(URL_OFFLINE, data=soap, timeout=6)
                    if "AUTORIZADO" in r.text and "<autorizacion>" in r.text:
                        zf.writestr(f"{cl}.xml", r.text)
                        datos = extraer_datos_xml(r.content)
                        if datos: datos_reporte.append(datos)
                        conteo["OK_OFFLINE"] += 1
                        exito = True
                except: pass
                
                # --- INTENTO 2: ONLINE (RESCATE) ---
                if not exito:
                    try:
                        time.sleep(1.2) # Pausa de cambio de carril
                        r = session.post(URL_ONLINE, data=soap, timeout=10)
                        if "AUTORIZADO" in r.text and "<autorizacion>" in r.text:
                            zf.writestr(f"{cl}.xml", r.text)
                            datos = extraer_datos_xml(r.content)
                            if datos: datos_reporte.append(datos)
                            conteo["OK_ONLINE"] += 1
                            exito = True
                            # Notificar rescate visualmente
                            with log_container:
                                st.success(f"✅ Rescatada del ONLINE: {cl}")
                    except: pass
                
                if not exito:
                    conteo["FALLOS"] += 1
                
                # Actualizar barra
                bar.progress((i+1)/len(claves))
                status_text.write(f"⏳ Procesando: {i+1}/{len(claves)} | 🏠 Offline: {conteo['OK_OFFLINE']} | 🌐 Online: {conteo['OK_ONLINE']} | ❌ Fallos: {conteo['FALLOS']}")

        # 4. Resultados Finales
        st.divider()
        if datos_reporte:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Procesado", len(datos_reporte))
            col2.metric("Vía Offline (Normal)", conteo["OK_OFFLINE"])
            col3.metric("Vía Online (Rescatadas)", conteo["OK_ONLINE"])
            
            st.success("¡Descarga completada!")
            
            # Botones de Descarga Gigantes
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    label="📂 DESCARGAR TODOS LOS XML (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="Facturas_SRI_Recuperadas.zip",
                    mime="application/zip",
                    use_container_width=True,
                    type="primary"
                )
            with c2:
                excel_data = generar_excel_simple(datos_reporte)
                st.download_button(
                    label="📊 DESCARGAR REPORTE EXCEL",
                    data=excel_data,
                    file_name="Reporte_SRI.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary"
                )
        else:
            st.error("No se pudo recuperar ninguna factura. Verifica que el TXT contenga claves válidas.")

