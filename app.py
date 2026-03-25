import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import os
from fpdf import FPDF

# --- 1. DICCIONARIO DE TRADUCCIÓN (Añadí los pagos aquí) ---
DICCIONARIO_CONCEPTOS = {
    "DERSAN": "ENVIRONMENTAL FEE",
    "ROOMSE": "ROOM SERVICE",
    "LOUNGE": "B LOUNGE BAR",
    "12TRIBE": "12 TRIBUS",
    "MAYDA": "MAYDAN",
    "OKIANU": "OKIANUS PALAPA",
    "POOL": "POOL BAR",
    "VISAD": "VISA CARD PAYMENT",
    "MASTED": "MASTER CARD PAYMENT",
    "AMEX": "AMERICAN EXPRESS PAYMENT",
    "EFE": "CASH PAYMENT",
    "PAGO": "PAYMENT RECEIVED"
}

# --- 2. CONFIGURACIÓN ---
st.set_page_config(page_title="Casa Dorada - Estado de Cuenta", layout="wide")

st.sidebar.header("⚙️ Configuración")
tipo_cambio = st.sidebar.number_input("Tipo de Cambio (1 USD = ? MXN)", min_value=1.0, value=18.50, step=0.01)

st.sidebar.markdown("---")
st.sidebar.subheader("Datos del Huésped")
nombre_h = st.sidebar.text_input("Nombre Manual", key="input_nombre")
hab_h = st.sidebar.text_input("Habitación Manual", key="input_hab")
folio_h = st.sidebar.text_input("Folio Manual", key="input_folio")

archivo_pdf = st.file_uploader("Subir Estado de Cuenta (PDF)", type=["pdf"])

# --- 3. FUNCIÓN GENERADORA DE PDF CON RESALTADO ---
def crear_pdf_recibo(df, tc, total_mxn, total_usd, guest, room, folio):
    pdf = FPDF()
    pdf.add_page()
    
    # 1. Logo Max (85mm)
    if os.path.exists("logo.png"):
        pdf.image("logo.png", 10, 10, 85)
        pdf.ln(35)
    else:
        pdf.set_font("Arial", "B", 20)
        pdf.cell(0, 10, "CASA DORADA RESORT & SPA", ln=True)
        pdf.ln(15)

    # 2. Info Hotel
    pdf.set_font("Arial", "", 9)
    pdf.set_xy(120, 12)
    pdf.multi_cell(80, 4, "Cabo San Lucas, B.C.S., Mexico\nPhone: +52 (624) 163 5700\nwww.casadorada.com", align="R")
    
    # 3. Datos Huésped
    pdf.set_xy(10, 55)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(15, 6, "Guest:", 0, 0)
    pdf.set_font("Arial", "", 10)
    pdf.cell(90, 6, guest.upper(), 0, 1)
    pdf.cell(15, 6, "Room:", 0, 0); pdf.cell(30, 6, str(room), 0, 0)
    pdf.cell(15, 6, "Folio:", 0, 0); pdf.cell(30, 6, str(folio), 0, 1)
    
    # 4. Título
    pdf.ln(8)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "GUEST STATEMENT / ESTADO DE CUENTA", ln=True, align="C")
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 5, f"Applied Rate: $1.00 USD = {tc} MXN", ln=True, align="C")
    pdf.ln(8)
    
    # 5. Encabezados
    pdf.set_fill_color(33, 47, 61) 
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(25, 9, " DATE", 1, 0, "L", True)
    pdf.cell(85, 9, " DESCRIPTION", 1, 0, "L", True)
    pdf.cell(40, 9, " AMOUNT (MXN)", 1, 0, "R", True)
    pdf.cell(40, 9, " EQUIV. (USD)", 1, 1, "R", True)
    
    # 6. Filas con COLOR PARA PAGOS
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "", 9)
    
    for _, row in df.iterrows():
        if row['Type'] == "PAYMENT":
            # Color de fondo gris claro para el renglón de pago
            pdf.set_fill_color(230, 240, 250) # Azul clarito/gris
            fill = True
            pdf.set_text_color(40, 80, 120) # Texto azul oscuro para pagos
        else:
            fill = False
            pdf.set_text_color(0, 0, 0)
            
        pdf.cell(25, 8, str(row['Fecha']), 1, 0, "C", fill)
        pdf.cell(85, 8, f" {row['Concepto']}", 1, 0, "L", fill)
        pdf.cell(40, 8, f"$ {abs(row['Monto MXN']):,.2f} ", 1, 0, "R", fill)
        pdf.cell(40, 8, f"$ {abs(row['Equivalente USD']):,.2f} ", 1, 1, "R", fill)
    
    pdf.ln(8)
    
    # 7. Totales
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(110, 10, "", 0, 0)
    pdf.cell(40, 10, "TOTAL BILL (MXN):", 0, 0, "R")
    pdf.cell(40, 10, f"$ {total_mxn:,.2f}", 1, 1, "R")
    
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(110, 12, "", 0, 0)
    pdf.cell(40, 12, "TOTAL BILL (USD):", 0, 0, "R")
    pdf.cell(40, 12, f"$ {total_usd:,.2f}", 1, 1, "R", True)
    
    return bytes(pdf.output())

# --- 4. PROCESAMIENTO ---
if archivo_pdf:
    datos_lista = []
    codigos_abonos = ["VISAD", "MASTED", "CXC", "VISA", "MASTER", "EFE", "AMEX", "COBR", "PAGO"]
    
    try:
        with pdfplumber.open(archivo_pdf) as pdf_read:
            texto_cabecera = pdf_read.pages[0].extract_text()
            match_h = re.search(r"(.*)\s+Hab:(\d+)\s+Folio:\s*(\d+)", texto_cabecera)
            
            f_name = nombre_h if nombre_h else (match_h.group(1).strip() if match_h else "N/A")
            f_hab = hab_h if hab_h else (match_h.group(2).strip() if match_h else "N/A")
            f_folio = folio_h if folio_h else (match_h.group(3).strip() if match_h else "N/A")

            for pagina in pdf_read.pages:
                palabras = pagina.extract_words()
                lineas_dict = {}
                for p in palabras:
                    top = round(p['top'], 0)
                    if top not in lineas_dict: lineas_dict[top] = []
                    lineas_dict[top].append(p)
                
                for top in sorted(lineas_dict.keys()):
                    texto_linea = " ".join([p['text'] for p in lineas_dict[top]])
                    if re.match(r'^\d{8}', texto_linea.strip()) and "SALDO" not in texto_linea.upper():
                        montos = re.findall(r'(\d[\d,]*\.\d{2})', texto_linea)
                        if montos:
                            monto_orig = float(montos[0].replace(',', ''))
                            partes = texto_linea.split()
                            codigo_raw = partes[2] if len(partes) > 2 else "SERVICE"
                            
                            concepto_final = DICCIONARIO_CONCEPTOS.get(codigo_raw, codigo_raw)
                            es_pago = any(abono in texto_linea for abono in codigos_abonos) or "-" in montos[0]
                            tipo_mov = "PAYMENT" if es_pago else "CHARGE"
                            
                            datos_lista.append({
                                "Fecha": partes[0], "Concepto": concepto_final, "Type": tipo_mov,
                                "Monto MXN": monto_orig, "Equivalente USD": round(monto_orig / tipo_cambio, 2)
                            })

        if datos_lista:
            df = pd.DataFrame(datos_lista).drop_duplicates()
            # Sumar solo cargos para el total real
            df_cargos = df[df["Type"] == "CHARGE"]
            t_mxn = df_cargos["Monto MXN"].sum()
            t_usd = df_cargos["Equivalente USD"].sum()

            pdf_bytes = crear_pdf_recibo(df, tipo_cambio, t_mxn, t_usd, f_name, f_hab, f_folio)
            
            st.success(f"Recibo listo para: {f_name}")
            st.download_button("📥 Descargar PDF Resaltado", data=pdf_bytes, file_name=f"Folio_{f_folio}.pdf", mime="application/pdf")
            st.dataframe(df, use_container_width=True)
            
    except Exception as e:
        st.error(f"Error: {e}")
        