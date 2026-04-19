import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import os
from fpdf import FPDF
from datetime import datetime

# --- 1. CONFIGURACIÓN Y TRADUCCIONES ---
DICCIONARIO_CONCEPTOS = {
    "DERSAN": "ENVIRONMENTAL FEE",
    "ROOMSE": "ROOM SERVICE",
    "LOUNGE": "B LOUNGE BAR",
    "12TRIB": "12 TRIBES RESTAURANT",
    "MAYDA": "MAYDAN",
    "OKIANU": "OKIANUS POOL BAR",
    "POOL": "POOL BAR",
    "PKTALL": "ALL INCLUSIVE PACKAGE",
    "MASSPA": "MASSAGE / SPA SERVICE",
    "VISAD": "VISA CARD PAYMENT",
    "MASTED": "MASTER CARD PAYMENT",
    "RESCRE": "RESORT CREDIT"  # <--- Nuevo código añadido
}

st.set_page_config(page_title="Casa Dorada - Folio USD", layout="wide")

st.sidebar.header("⚙️ Configuración")
tipo_cambio = st.sidebar.number_input("Tipo de Cambio (1 USD = ? MXN)", min_value=1.0, value=16.00, step=0.01)

def formatear_fecha_ingles(fecha_str):
    try:
        fecha_obj = datetime.strptime(fecha_str, '%Y%m%d')
        return fecha_obj.strftime('%b %d, %Y')
    except:
        return fecha_str 

# --- 2. FUNCIÓN GENERADORA DE PDF ---
def crear_pdf_recibo(df, tc, total_mxn, total_usd, guest, room, folio):
    pdf = FPDF()
    pdf.add_page()
    
    if os.path.exists("logo.png"):
        pdf.image("logo.png", 10, 10, 85)
        pdf.ln(35)
    else:
        pdf.set_font("Arial", "B", 20); pdf.cell(0, 10, "CASA DORADA RESORT & SPA", ln=True); pdf.ln(15)

    pdf.set_font("Arial", "", 9); pdf.set_xy(120, 12)
    pdf.multi_cell(80, 4, "Cabo San Lucas, B.C.S., Mexico\nPhone: +52 (624) 163 5700\nwww.casadorada.com", align="R")
    
    pdf.set_xy(10, 55); pdf.set_font("Arial", "B", 10)
    pdf.cell(15, 6, "Guest:", 0, 0); pdf.set_font("Arial", "", 10); pdf.cell(90, 6, guest.upper(), 0, 1)
    pdf.set_font("Arial", "B", 10); pdf.cell(15, 6, "Room:", 0, 0); pdf.set_font("Arial", "", 10); pdf.cell(30, 6, str(room), 0, 0)
    pdf.set_font("Arial", "B", 10); pdf.cell(15, 6, "Folio:", 0, 0); pdf.set_font("Arial", "", 10); pdf.cell(30, 6, str(folio), 0, 1)
    
    pdf.ln(8); pdf.set_font("Arial", "B", 14); pdf.cell(0, 10, "GUEST STATEMENT / ESTADO DE CUENTA", ln=True, align="C")
    pdf.set_font("Arial", "", 10); pdf.cell(0, 5, f"Applied Rate: $1.00 USD = {tc} MXN", ln=True, align="C")
    pdf.ln(8)
    
    # Encabezado Tabla
    pdf.set_fill_color(33, 47, 61); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", "B", 9)
    pdf.cell(30, 9, " DATE", 1, 0, "L", True)
    pdf.cell(80, 9, " DESCRIPTION", 1, 0, "L", True)
    pdf.cell(40, 9, " AMOUNT (MXN)", 1, 0, "R", True)
    pdf.cell(40, 9, " EQUIV. (USD)", 1, 1, "R", True)
    
    pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", "", 9)
    for _, row in df.iterrows():
        is_credit = row['Type'] == "PAYMENT"
        if is_credit:
            pdf.set_fill_color(245, 245, 245); pdf.set_text_color(180, 0, 0) # Rojo oscuro para abonos
            prefix = "-"
        else:
            pdf.set_text_color(0, 0, 0)
            prefix = ""
            
        pdf.cell(30, 8, str(row['Fecha']), 1, 0, "C", is_credit)
        pdf.cell(80, 8, f" {row['Concepto']}", 1, 0, "L", is_credit)
        pdf.cell(40, 8, f"{prefix}$ {abs(row['Monto MXN']):,.2f} ", 1, 0, "R", is_credit)
        pdf.cell(40, 8, f"{prefix}$ {abs(row['Equivalente USD']):,.2f} ", 1, 1, "R", is_credit)
    
    # Totales basados en CREDITOS
    pdf.ln(8); pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", "B", 12)
    pdf.cell(110, 10, "", 0, 0); pdf.cell(40, 10, "TOTAL CREDITS (MXN):", 0, 0, "R"); pdf.cell(40, 10, f"$ {total_mxn:,.2f}", 1, 1, "R")
    pdf.set_fill_color(230, 240, 250); pdf.cell(110, 12, "", 0, 0); pdf.cell(40, 12, "TOTAL CREDITS (USD):", 0, 0, "R"); pdf.cell(40, 12, f"$ {total_usd:,.2f}", 1, 1, "R", True)
    
    return bytes(pdf.output())

# --- 3. PROCESAMIENTO ---
st.title("🏨 Generador de Estados de Cuenta")
archivo_pdf = st.file_uploader("Subir Estado de Cuenta (PDF)", type=["pdf"])

if archivo_pdf:
    raw_data = []
    # Lista extendida de abonos
    codigos_abonos_fijos = ["VISAD", "MASTED", "CXC", "VISA", "MASTER", "EFE", "AMEX", "COBR", "PAGO", "RESCRE"]
    
    with pdfplumber.open(archivo_pdf) as pdf_read:
        texto_cabecera = pdf_read.pages[0].extract_text()
        match_h = re.search(r"(.*)\s+Hab:(\d+)\s+Folio:\s*(\d+)", texto_cabecera)
        f_name = match_h.group(1).strip() if match_h else "N/A"
        f_hab = match_h.group(2).strip() if match_h else "N/A"
        f_folio = match_h.group(3).strip() if match_h else "N/A"

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
                    montos = re.findall(r'(-?\d[\d,]*\.\d{2})', texto_linea)
                    if montos:
                        monto_val = float(montos[0].replace(',', ''))
                        partes = texto_linea.split()
                        codigo = partes[2] if len(partes) > 2 else "SERVICE"
                        fecha_bonita = formatear_fecha_ingles(partes[0])
                        raw_data.append({"Fecha": fecha_bonita, "Concepto": codigo, "Monto": monto_val})

    if raw_data:
        df_temp = pd.DataFrame(raw_data)
        
        # Agrupar y limpiar conceptos que se cancelan entre sí
        df_grouped = df_temp.groupby('Concepto')['Monto'].sum().reset_index()
        conceptos_a_borrar = df_grouped[abs(df_grouped['Monto']) < 0.01]['Concepto'].tolist()
        df_clean = df_temp[~df_temp['Concepto'].isin(conceptos_a_borrar)].copy()
        
        final_list = []
        indices_borrados = []
        for idx, row in df_clean.iterrows():
            if idx in indices_borrados: continue
            gemelo = df_clean[(abs(df_clean['Monto'] + row['Monto']) < 0.01) & 
                              (df_clean['Concepto'] == row['Concepto']) & 
                              (~df_clean.index.isin(indices_borrados)) & 
                              (df_clean.index != idx)].head(1)
            if not gemelo.empty:
                indices_borrados.extend([idx, gemelo.index[0]])
            else:
                # Lógica de identificación
                es_ajuste = row['Concepto'].startswith("AJU")
                es_pago_lista = any(abono in row['Concepto'] for abono in codigos_abonos_fijos)
                es_pago = es_ajuste or es_pago_lista or row['Monto'] < 0
                
                # Definir nombre visual
                if es_ajuste:
                    nombre_concepto = f"ADJUSTMENT ({row['Concepto']})"
                else:
                    nombre_concepto = DICCIONARIO_CONCEPTOS.get(row['Concepto'], row['Concepto'])

                final_list.append({
                    "Fecha": row['Fecha'],
                    "Concepto": nombre_concepto,
                    "Type": "PAYMENT" if es_pago else "CHARGE",
                    "Monto MXN": row['Monto'],
                    "Equivalente USD": round(row['Monto'] / tipo_cambio, 2)
                })

        df_final = pd.DataFrame(final_list)
        st.subheader(f"Resumen para: {f_name}")
        
        edited_df = st.data_editor(df_final, num_rows="dynamic", use_container_width=True)
        
        # Calcular totales sobre los CREDITS (Abonos, Ajustes y Resort Credit)
        df_creditos = edited_df[edited_df["Type"] == "PAYMENT"]
        t_mxn = abs(df_creditos["Monto MXN"].sum())
        t_usd = abs(df_creditos["Equivalente USD"].sum())

        if st.button(" Generar PDF Final"):
            pdf_bytes = crear_pdf_recibo(edited_df, tipo_cambio, t_mxn, t_usd, f_name, f_hab, f_folio)
            st.download_button("📥 Descargar PDF", data=pdf_bytes, file_name=f"Folio_{f_folio}.pdf")
