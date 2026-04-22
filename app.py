import streamlit as st
import pandas as pd
import pdfplumber
import re
import os
from fpdf import FPDF
from datetime import datetime

# --- 1. CONFIGURACIÓN ---
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
    "CXC": "CUPON VIVENZIA"
}

st.set_page_config(page_title="Casa Dorada - Folio USD", layout="wide")
tipo_cambio = st.sidebar.number_input("Tipo de Cambio (1 USD = ? MXN)", min_value=1.0, value=16.00, step=0.01)

# --- 2. CLASE PDF OPTIMIZADA ---
class FolioPDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            if os.path.exists("logo.png"):
                self.image("logo.png", 10, 10, 85)
            else:
                self.set_font("Arial", "B", 18)
                self.cell(0, 10, "CASA DORADA RESORT & SPA", ln=True)
            
            self.set_font("Arial", "", 9)
            self.set_xy(120, 12)
            self.multi_cell(80, 4, "Cabo San Lucas, B.C.S., Mexico\nPhone: +52 (624) 163 5700\nwww.casadorada.com", align="R")
            self.set_y(50)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()} - Casa Dorada Resort & Spa", 0, 0, "C")

def crear_pdf_recibo(df, tc, stats, guest, room, folio):
    pdf = FolioPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    
    # Datos Huésped (Solo en primera página)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(15, 6, "Guest:", 0, 0); pdf.set_font("Arial", "", 10); pdf.cell(90, 6, guest.upper(), 0, 1)
    pdf.set_font("Arial", "B", 10); pdf.cell(15, 6, "Room:", 0, 0); pdf.set_font("Arial", "", 10); pdf.cell(30, 6, str(room), 0, 0)
    pdf.set_font("Arial", "B", 10); pdf.cell(15, 6, "Folio:", 0, 0); pdf.set_font("Arial", "", 10); pdf.cell(30, 6, str(folio), 0, 1)
    
    pdf.ln(8)
    pdf.set_font("Arial", "B", 12); pdf.cell(0, 10, "GUEST STATEMENT / ESTADO DE CUENTA", ln=True, align="C")
    pdf.set_font("Arial", "", 9); pdf.cell(0, 5, f"Applied Rate: $1.00 USD = {tc} MXN", ln=True, align="C")
    pdf.ln(5)
    
    # Tabla
    pdf.set_fill_color(33, 47, 61); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", "B", 9)
    pdf.cell(30, 9, " DATE", 1, 0, "L", True)
    pdf.cell(80, 9, " DESCRIPTION", 1, 0, "L", True)
    pdf.cell(40, 9, " AMOUNT (MXN)", 1, 0, "R", True)
    pdf.cell(40, 9, " EQUIV. (USD)", 1, 1, "R", True)
    
    pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", "", 9)
    
    for _, row in df.iterrows():
        is_neg = row['Type'] != "CHARGE"
        prefix = "-" if is_neg else ""
        if is_neg: pdf.set_text_color(110, 110, 110)
        else: pdf.set_text_color(0, 0, 0)
            
        pdf.cell(30, 8, str(row['Fecha']), 1, 0, "C")
        pdf.cell(80, 8, f" {row['Concepto']}", 1, 0, "L")
        pdf.cell(40, 8, f"{prefix}$ {abs(row['Monto MXN']):,.2f} ", 1, 0, "R")
        pdf.cell(40, 8, f"{prefix}$ {abs(row['Equivalente USD']):,.2f} ", 1, 1, "R")

    # --- SECCIÓN DE TOTALES ---
    pdf.ln(6)
    if pdf.get_y() > 220: pdf.add_page()
    
    pdf.set_font("Arial", "", 10)
    def fila_total(label, val, neg=False, bold=False):
        p = "-" if neg and val > 0 else ""
        if bold: pdf.set_font("Arial", "B", 10)
        pdf.cell(110, 7, "", 0, 0)
        pdf.cell(45, 7, label, 0, 0, "R")
        pdf.cell(35, 7, f"{p}$ {val:,.2f}", 1, 1, "R")
        pdf.set_font("Arial", "", 10)

    fila_total("Total Charges:", stats['charges_usd'])
    fila_total("Adjustments:", stats['adjust_usd'], neg=True)
    fila_total("Resort Credits / Vivenzia:", stats['resort_usd'], neg=True)
    fila_total("Payments:", stats['payments_usd'], neg=True)
    
    pdf.ln(3)
    if abs(stats['balance_usd']) < 0.01:
        pdf.set_fill_color(230, 245, 230); pdf.set_font("Arial", "B", 11)
        pdf.cell(110, 10, "", 0, 0)
        pdf.cell(80, 12, "ACCOUNT SETTLED", 1, 1, "C", True)
    else:
        pdf.set_fill_color(255, 230, 230); pdf.set_font("Arial", "B", 11)
        pdf.cell(110, 10, "", 0, 0)
        pdf.cell(45, 10, "BALANCE DUE (USD):", 0, 0, "R")
        pdf.cell(35, 10, f"$ {stats['balance_usd']:,.2f}", 1, 1, "R", True)
    
    return bytes(pdf.output())

# --- 3. PROCESAMIENTO ---
st.title("🏨 Generador de Folios - Casa Dorada")
archivo_pdf = st.file_uploader("Subir PDF Original", type=["pdf"])

if archivo_pdf:
    raw_data = []
    codigos_pagos = ["VISAD", "MASTED", "VISA", "MASTER", "EFE", "AMEX", "COBR", "PAGO"]
    
    with pdfplumber.open(archivo_pdf) as pdf_read:
        texto_cabecera = pdf_read.pages[0].extract_text()
        match_h = re.search(r"(.*)\s+Hab:(\d+)\s+Folio:\s*(\d+)", texto_cabecera)
        
        # Extracción inicial
        f_name_extracted = match_h.group(1).strip() if match_h else "N/A"
        f_hab = match_h.group(2).strip() if match_h else "N/A"
        f_folio = match_h.group(3).strip() if match_h else "N/A"

        # --- CAMPO MANUAL PARA EL NOMBRE ---
        nombre_huesped = st.text_input("Nombre del Huésped (puedes editarlo):", value=f_name_extracted)

        for page in pdf_read.pages:
            table = page.extract_words()
            lineas = {}
            for w in table:
                y = round(w['top'], 0)
                lineas.setdefault(y, []).append(w)
            
            for y in sorted(lineas.keys()):
                txt = " ".join([w['text'] for w in lineas[y]])
                if re.match(r'^\d{8}', txt.strip()):
                    m = re.findall(r'(-?\d[\d,]*\.\d{2})', txt)
                    if m:
                        partes = txt.split()
                        raw_data.append({
                            "Fecha": datetime.strptime(partes[0], '%Y%m%d').strftime('%b %d, %Y'),
                            "Cod": partes[2],
                            "Monto": float(m[0].replace(',', '')),
                            "EsVivenzia": "VIVENZIA" in txt.upper()
                        })

    if raw_data:
        final_list = []
        for r in raw_data:
            if r['Cod'].startswith("AJU"):
                tipo, desc = "ADJUST", f"ADJUSTMENT ({r['Cod']})"
            elif r['Cod'] in ["RESCRE", "CXC"]:
                tipo, desc = "RESORT", "CUPON VIVENZIA"
            elif any(p in r['Cod'] for p in codigos_pagos) or r['Monto'] < 0:
                tipo, desc = "PAYMENT", DICCIONARIO_CONCEPTOS.get(r['Cod'], r['Cod'])
            else:
                tipo, desc = "CHARGE", DICCIONARIO_CONCEPTOS.get(r['Cod'], r['Cod'])

            final_list.append({
                "Fecha": r['Fecha'], "Concepto": desc, "Type": tipo,
                "Monto MXN": r['Monto'], "Equivalente USD": round(r['Monto'] / tipo_cambio, 2)
            })

        df_final = pd.DataFrame(final_list)
        edited_df = st.data_editor(df_final, num_rows="dynamic", use_container_width=True)
        
        def s_usd(t): return edited_df[edited_df['Type']==t]['Equivalente USD'].sum()
        
        stats = {
            'charges_usd': s_usd("CHARGE"),
            'adjust_usd': abs(s_usd("ADJUST")),
            'resort_usd': abs(s_usd("RESORT")),
            'payments_usd': abs(s_usd("PAYMENT")),
        }
        stats['balance_usd'] = stats['charges_usd'] - (stats['adjust_usd'] + stats['resort_usd'] + stats['payments_usd'])

        if st.button("Generar PDF Final"):
            # Se usa 'nombre_huesped' (el del input manual) para el PDF
            pdf_b = crear_pdf_recibo(edited_df, tipo_cambio, stats, nombre_huesped, f_hab, f_folio)
            st.download_button("📥 Descargar Folio", data=pdf_b, file_name=f"Folio_{f_folio}.pdf")
