import streamlit as st
import pandas as pd
import pdfplumber
import re
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
    "RESCRE": "RESORT CREDIT",
    "CXC": "RESORT CREDIT (CXC)" # <--- Clasificado como Resort Credit
}

st.set_page_config(page_title="Casa Dorada - Folio USD", layout="wide")
tipo_cambio = st.sidebar.number_input("Tipo de Cambio (1 USD = ? MXN)", min_value=1.0, value=16.00, step=0.01)

# --- 2. FUNCIÓN GENERADORA DE PDF ---
def crear_pdf_recibo(df, tc, stats, guest, room, folio):
    pdf = FPDF()
    pdf.add_page()
    
    # Logo e Info Hotel
    if os.path.exists("logo.png"):
        pdf.image("logo.png", 10, 10, 85)
        pdf.ln(35)
    else:
        pdf.set_font("Arial", "B", 20); pdf.cell(0, 10, "CASA DORADA RESORT & SPA", ln=True); pdf.ln(15)

    pdf.set_font("Arial", "", 9); pdf.set_xy(120, 12)
    pdf.multi_cell(80, 4, "Cabo San Lucas, B.C.S., Mexico\nPhone: +52 (624) 163 5700\nwww.casadorada.com", align="R")
    
    # Datos Huésped
    pdf.set_xy(10, 55); pdf.set_font("Arial", "B", 10)
    pdf.cell(15, 6, "Guest:", 0, 0); pdf.set_font("Arial", "", 10); pdf.cell(90, 6, guest.upper(), 0, 1)
    pdf.set_font("Arial", "B", 10); pdf.cell(15, 6, "Room:", 0, 0); pdf.set_font("Arial", "", 10); pdf.cell(30, 6, str(room), 0, 0)
    pdf.set_font("Arial", "B", 10); pdf.cell(15, 6, "Folio:", 0, 0); pdf.set_font("Arial", "", 10); pdf.cell(30, 6, str(folio), 0, 1)
    
    pdf.ln(8); pdf.set_font("Arial", "B", 12); pdf.cell(0, 10, "GUEST STATEMENT / ESTADO DE CUENTA", ln=True, align="C")
    pdf.set_font("Arial", "", 9); pdf.cell(0, 5, f"Applied Rate: $1.00 USD = {tc} MXN", ln=True, align="C")
    pdf.ln(5)
    
    # Tabla de Movimientos
    pdf.set_fill_color(33, 47, 61); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", "B", 8)
    pdf.cell(25, 8, " DATE", 1, 0, "L", True)
    pdf.cell(85, 8, " DESCRIPTION", 1, 0, "L", True)
    pdf.cell(40, 8, " AMOUNT (MXN)", 1, 0, "R", True)
    pdf.cell(40, 8, " EQUIV. (USD)", 1, 1, "R", True)
    
    pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", "", 8)
    for _, row in df.iterrows():
        is_credit = row['Type'] in ["PAYMENT", "RESORT", "ADJUST"]
        prefix = "-" if is_credit else ""
        if is_credit: pdf.set_text_color(100, 100, 100)
        else: pdf.set_text_color(0, 0, 0)
            
        pdf.cell(25, 7, str(row['Fecha']), 1, 0, "C")
        pdf.cell(85, 7, f" {row['Concepto']}", 1, 0, "L")
        pdf.cell(40, 7, f"{prefix}$ {abs(row['Monto MXN']):,.2f} ", 1, 0, "R")
        pdf.cell(40, 7, f"{prefix}$ {abs(row['Equivalente USD']):,.2f} ", 1, 1, "R")
    
    # --- SECCIÓN DE TOTALES DESGLOSADOS ---
    pdf.ln(5)
    pdf.set_font("Arial", "", 9)
    
    def agregar_linea_total(etiqueta, valor_mxn, valor_usd, neg=False):
        p = "-" if neg and valor_mxn > 0 else ""
        pdf.cell(110, 6, "", 0, 0)
        pdf.cell(40, 6, etiqueta, 0, 0, "R")
        pdf.cell(40, 6, f"{p}$ {valor_usd:,.2f}", 1, 1, "R")

    agregar_linea_total("Total Charges (USD):", stats['charges_mxn'], stats['charges_usd'])
    agregar_linea_total("Payments (USD):", stats['payments_mxn'], stats['payments_usd'], neg=True)
    agregar_linea_total("Resort Credits Applied (USD):", stats['resort_mxn'], stats['resort_usd'], neg=True)
    agregar_linea_total("Adjustments (USD):", stats['adjust_mxn'], stats['adjust_usd'], neg=True)
    
    pdf.ln(2)
    pdf.set_fill_color(240, 240, 240); pdf.set_font("Arial", "B", 11)
    pdf.cell(110, 8, "", 0, 0)
    pdf.cell(40, 8, "BALANCE DUE (USD):", 0, 0, "R")
    # El balance final se muestra sin signo negativo si es 0 o cercano
    val_final = stats['balance_usd'] if abs(stats['balance_usd']) > 0.01 else 0.00
    pdf.cell(40, 8, f"$ {val_final:,.2f}", 1, 1, "R", True)
    
    return bytes(pdf.output())

# --- 3. PROCESAMIENTO ---
st.title("🏨 Generador de Folios Casa Dorada")
archivo_pdf = st.file_uploader("Subir Estado de Cuenta (PDF)", type=["pdf"])

if archivo_pdf:
    raw_data = []
    # CXC se quita de aquí porque ahora tiene su categoría especial
    codigos_pagos = ["VISAD", "MASTED", "VISA", "MASTER", "EFE", "AMEX", "COBR", "PAGO"]
    
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
                if re.match(r'^\d{8}', texto_linea.strip()):
                    montos = re.findall(r'(-?\d[\d,]*\.\d{2})', texto_linea)
                    if montos:
                        partes = texto_linea.split()
                        raw_data.append({
                            "Fecha": datetime.strptime(partes[0], '%Y%m%d').strftime('%b %d, %Y'),
                            "Cod": partes[2],
                            "Monto": float(montos[0].replace(',', ''))
                        })

    if raw_data:
        final_list = []
        for r in raw_data:
            # CLASIFICACIÓN LOGICA
            if r['Cod'] in ["RESCRE", "CXC"]: tipo = "RESORT" # <--- CXC añadido aquí
            elif r['Cod'].startswith("AJU"): tipo = "ADJUST"
            elif any(p in r['Cod'] for p in codigos_pagos) or r['Monto'] < 0: tipo = "PAYMENT"
            else: tipo = "CHARGE"
            
            # Nombre visual
            if tipo == "ADJUST": desc = f"ADJUSTMENT ({r['Cod']})"
            else: desc = DICCIONARIO_CONCEPTOS.get(r['Cod'], r['Cod'])

            final_list.append({
                "Fecha": r['Fecha'], "Concepto": desc, "Type": tipo,
                "Monto MXN": r['Monto'], "Equivalente USD": round(r['Monto'] / tipo_cambio, 2)
            })

        df_final = pd.DataFrame(final_list)
        edited_df = st.data_editor(df_final, num_rows="dynamic", use_container_width=True)
        
        # CÁLCULOS
        def get_sum(t, col): return edited_df[edited_df['Type']==t][col].sum()

        s = {
            'charges_mxn': get_sum("CHARGE", "Monto MXN"),
            'charges_usd': get_sum("CHARGE", "Equivalente USD"),
            'payments_mxn': abs(get_sum("PAYMENT", "Monto MXN")),
            'payments_usd': abs(get_sum("PAYMENT", "Equivalente USD")),
            'resort_mxn': abs(get_sum("RESORT", "Monto MXN")),
            'resort_usd': abs(get_sum("RESORT", "Equivalente USD")),
            'adjust_mxn': abs(get_sum("ADJUST", "Monto MXN")),
            'adjust_usd': abs(get_sum("ADJUST", "Equivalente USD")),
        }
        s['balance_mxn'] = s['charges_mxn'] - (s['payments_mxn'] + s['resort_mxn'] + s['adjust_mxn'])
        s['balance_usd'] = s['charges_usd'] - (s['payments_usd'] + s['resort_usd'] + s['adjust_usd'])

        if st.button("Generar PDF Final"):
            pdf_b = crear_pdf_recibo(edited_df, tipo_cambio, s, f_name, f_hab, f_folio)
            st.download_button("📥 Descargar", data=pdf_b, file_name=f"Folio_{f_folio}.pdf")
