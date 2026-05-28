import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, date
from io import BytesIO
import zipfile

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable, PageBreak
)
from reportlab.graphics.barcode import qr as qr_mod
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

# ============================================================
# HOF - Génération PDF Qualiopi — Art de Pâtisser
# pages/2_Documents.py  v2
# ============================================================

DATA_DIR     = Path("data")
EXPORT_DIR   = Path("exports")
TEMPLATE_DIR = Path("templates")
EXPORT_DIR.mkdir(exist_ok=True)
TEMPLATE_DIR.mkdir(exist_ok=True)

FONT_NORMAL = "Helvetica"
FONT_BOLD   = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"
RED         = (0.68, 0.05, 0.05)
NAVY        = (0.12, 0.23, 0.37)
DARK        = (0.20, 0.20, 0.20)
GREY        = (0.50, 0.50, 0.50)

# ── Chargement données ────────────────────────────────────────

def load(path, cols):
    if not path.exists():
        return pd.DataFrame(columns=cols)
    for enc in ["utf-8-sig", "utf-8", "latin1"]:
        for sep in [",", ";"]:
            try:
                df = pd.read_csv(path, dtype=str, encoding=enc, sep=sep).fillna("")
                if len(df.columns) == 1 and len(cols) > 1:
                    continue
                for c in cols:
                    if c not in df.columns:
                        df[c] = ""
                return df[cols]
            except Exception:
                pass
    return pd.DataFrame(columns=cols)

sessions        = load(DATA_DIR / "sessions.csv",
                       ["session_id","programme_id","formateur_id","nom",
                        "date_debut","date_fin","prix","cout_prevu"])
stagiaires      = load(DATA_DIR / "stagiaires.csv",
                       ["stagiaire_id","session_id","nom","email","entreprise","lien_unique"])
formateurs      = load(DATA_DIR / "formateurs.csv",
                       ["formateur_id","nom","email","specialite","lien_unique"])
programmes      = load(DATA_DIR / "programmes.csv",
                       ["programme_id","referentiel_id","nom_programme","duree_heures",
                        "objectifs","prerequis","modalites"])
competences     = load(DATA_DIR / "competences.csv",
                       ["competence_id","referentiel_id","epreuve","bloc","section",
                        "code_competence","competence","famille","niveau","actif"])
evaluations     = load(DATA_DIR / "evaluations.csv",
                       ["evaluation_id","stagiaire_id","session_id","competence_id",
                        "epreuve","niveau","commentaire","horodatage"])
auto_evaluation = load(DATA_DIR / "auto_evaluation.csv",
                       ["auto_eval_id","stagiaire_id","session_id","competence_id",
                        "moment","note","commentaire"])
satisfaction    = load(DATA_DIR / "satisfaction_stagiaire.csv",
                       ["satisfaction_id","stagiaire_id","session_id","date",
                        "rubrique","note","commentaire"])

# ── Helpers ──────────────────────────────────────────────────

def get(df, id_col, val, target_col, fallback=""):
    r = df[df[id_col] == val]
    return str(r.iloc[0][target_col]) if not r.empty else fallback

def fmt_date(s):
    try:
        return pd.to_datetime(s).strftime("%d/%m/%Y")
    except Exception:
        return str(s)

def sc(c, rgb):
    c.setFillColorRGB(*rgb)

def get_tpl(key):
    files = list((TEMPLATE_DIR / key).glob("*.pdf"))
    return files[0] if files else None

def make_overlay(draw_fn, pagesize=(595.3, 841.9)) -> bytes:
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=pagesize)
    draw_fn(c)
    c.save()
    return buf.getvalue()

def overlay_on_template(tpl_path: Path, overlay_bytes: bytes) -> bytes:
    tpl     = PdfReader(str(tpl_path))
    overlay = PdfReader(BytesIO(overlay_bytes))
    writer  = PdfWriter()
    for i, page in enumerate(tpl.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()

def merge_pdfs(pdf_bytes_list: list) -> bytes:
    """Assemble plusieurs PDF bytes en un seul."""
    writer = PdfWriter()
    for pdf_bytes in pdf_bytes_list:
        reader = PdfReader(BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()

# ════════════════════════════════════════════════════════════
# GÉNÉRATEURS — chaque fonction retourne bytes PDF
# ════════════════════════════════════════════════════════════

# ── Certificat ───────────────────────────────────────────────

def pdf_certificat(tpl, session_row, stag_row, prog_row, formateur_nom):
    W, H = 595.3, 841.9
    def draw(c):
        c.setFont(FONT_BOLD, 13); sc(c, RED)
        c.drawString(93.5, H-212.0, stag_row["nom"])
        c.setFont(FONT_NORMAL, 10); sc(c, DARK)
        c.drawString(93.5, H-232.0, stag_row.get("entreprise",""))
        c.setFont(FONT_BOLD, 11)
        c.drawString(136.1, H-263.0, prog_row["nom_programme"])
        c.setFont(FONT_NORMAL, 10)
        c.drawString(277.8, H-356.5, fmt_date(session_row["date_debut"]))
        c.drawString(348.7, H-356.5, fmt_date(session_row["date_fin"]))
        c.drawString(271.2, H-382.0, str(prog_row["duree_heures"]))
        # Objectifs — effacer + réécrire
        c.setFillColorRGB(1,1,1)
        c.rect(38, H-502, 522, 52, fill=1, stroke=0)
        sc(c, DARK); c.setFont(FONT_NORMAL, 8.5)
        to = c.beginText(45.4, H-467.0)
        to.setFont(FONT_NORMAL, 8.5); to.setLeading(12)
        for s in prog_row["objectifs"].split(". "):
            s = s.strip()
            if s:
                to.textLine(s + ("." if not s.endswith(".") else ""))
        c.drawText(to)
        c.setFont(FONT_NORMAL, 10)
        c.drawString(119.1, H-612.5, date.today().strftime("%d/%m/%Y"))
    return overlay_on_template(tpl, make_overlay(draw, (W, H)))


# ── Convocation (page 1 du contrat) ──────────────────────────

def pdf_convocation(tpl, session_row, stag_row, prog_row):
    W, H = 595.3, 841.9
    def draw(c):
        c.setFont(FONT_BOLD, 12); sc(c, DARK)
        c.drawString(93.5, H-212.0, stag_row["nom"])
        c.setFont(FONT_BOLD, 11)
        c.drawString(93.5, H-269.0, fmt_date(session_row["date_debut"]))
        sc(c, RED)
        c.drawString(93.5, H-375.0, prog_row["nom_programme"])
        c.setFont(FONT_NORMAL, 10); sc(c, DARK)
        c.drawString(119.1, H-612.0, date.today().strftime("%d/%m/%Y"))
    return overlay_on_template(tpl, make_overlay(draw, (W, H)))


# ── Droit à l'image (page 4 du contrat) ──────────────────────

def pdf_droit_image(tpl, session_row, stag_row, prog_row):
    W, H = 595.3, 841.9
    def draw(c):
        # Effacer zones variables
        c.setFillColorRGB(1,1,1)
        c.rect(140, H-182, 340, 14, fill=1, stroke=0)  # nom
        c.rect(178, H-208, 300, 14, fill=1, stroke=0)  # formation
        c.rect(133, H-232, 250, 14, fill=1, stroke=0)  # dates
        sc(c, DARK)
        # Nom stagiaire
        c.setFont(FONT_BOLD, 11)
        c.drawString(144.6, H-176.5, stag_row["nom"])
        # Formation
        c.setFont(FONT_NORMAL, 10)
        c.drawString(181.4, H-202.0, prog_row["nom_programme"])
        # Date début → date fin
        c.drawString(137.5, H-226.0, fmt_date(session_row["date_debut"]))
        c.drawString(209.8, H-226.0, fmt_date(session_row["date_fin"]))
    return overlay_on_template(tpl, make_overlay(draw, (W, H)))


# ── Programme de formation (pages 5-7 du contrat) ────────────
# Pages fixes sauf titre + dates prochaine session (page 5)

def pdf_programme(tpl_pages567, session_row, prog_row):
    """
    tpl_pages567 : PDF avec les 3 pages du programme (extrait du contrat)
    """
    W, H = 595.3, 841.9
    # Overlay seulement sur page 1 (titre + dates session)
    def draw(c):
        # Effacer titre formation (top≈62)
        c.setFillColorRGB(1,1,1)
        c.rect(180, H-72, 340, 16, fill=1, stroke=0)
        # Effacer dates "Prochaine session" (top≈342)
        c.rect(400, H-352, 160, 14, fill=1, stroke=0)
        sc(c, DARK)
        # Titre
        c.setFont(FONT_BOLD, 13); sc(c, RED)
        c.drawCentredString(W/2, H-66.0, prog_row["nom_programme"])
        # Dates session
        c.setFont(FONT_NORMAL, 9); sc(c, DARK)
        dates_str = (f"{fmt_date(session_row['date_debut'])} "
                     f"au {fmt_date(session_row['date_fin'])}")
        c.drawString(405.0, H-345.0, dates_str)
    overlay_bytes = make_overlay(draw, (W, H))
    # Appliquer overlay sur page 1, pages 2-3 inchangées
    tpl_reader   = PdfReader(str(tpl_pages567))
    over_reader  = PdfReader(BytesIO(overlay_bytes))
    writer       = PdfWriter()
    for i, page in enumerate(tpl_reader.pages):
        if i == 0:
            page.merge_page(over_reader.pages[0])
        writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


# ── Satisfaction (page Streamlit → PDF récap) ─────────────────

def pdf_satisfaction(tpl, session_row, stag_row):
    W, H = 595.0, 842.0
    def draw(c):
        c.setFillColorRGB(1,1,1)
        c.rect(60, H-175, 470, 16, fill=1, stroke=0)
        sc(c, DARK)
        c.setFont(FONT_NORMAL, 10)
        c.drawString(66.7, H-168.0, date.today().strftime("%d/%m/%Y"))
        c.setFont(FONT_BOLD, 10)
        c.drawString(186.0, H-168.0, stag_row["nom"])
    return overlay_on_template(tpl, make_overlay(draw, (W, H)))


# ── Auto-évaluation ───────────────────────────────────────────

def pdf_auto_evaluation(tpl, session_row, stag_row, auto_evals_stag, comps):
    W, H = 595.0, 842.0
    def draw(c):
        c.setFillColorRGB(1,1,1)
        c.rect(350, H-100, 200, 14, fill=1, stroke=0)
        c.rect(283, H-144, 160, 12, fill=1, stroke=0)
        sc(c, DARK)
        c.setFont(FONT_BOLD, 10)
        c.drawString(356.2, H-95.0, stag_row["nom"])
        c.setFont(FONT_NORMAL, 9)
        c.drawString(290.9, H-139.0, fmt_date(session_row["date_debut"]))
        c.drawString(366.2, H-139.0, fmt_date(session_row["date_fin"]))
        if not auto_evals_stag.empty:
            avant = auto_evals_stag[auto_evals_stag["moment"] == "avant"]
            apres = auto_evals_stag[auto_evals_stag["moment"] == "apres"]
            for idx, (_, cr) in enumerate(comps.iterrows()):
                cid = cr["competence_id"]
                nav = avant[avant["competence_id"]==cid]["note"].values
                nap = apres[apres["competence_id"]==cid]["note"].values
                y   = H - (163.0 + idx * 11.2)
                c.setFont(FONT_BOLD, 9)
                if nav.size > 0: c.drawString(305, y, str(nav[0]))
                if nap.size > 0: c.drawString(382, y, str(nap[0]))
    return overlay_on_template(tpl, make_overlay(draw, (W, H)))


# ── Bilan formateur ───────────────────────────────────────────

def pdf_bilan_formateur(tpl, session_row, formateur_nom, evals_session, comps):
    W, H = 595.0, 842.0
    def draw(c):
        c.setFillColorRGB(1,1,1)
        c.rect(230, H-106, 120, 13, fill=1, stroke=0)
        sc(c, DARK)
        c.setFont(FONT_NORMAL, 10)
        c.drawString(238.1, H-100.5, date.today().strftime("%d/%m/%Y"))
        if not evals_session.empty and not comps.empty:
            for idx, (_, cr) in enumerate(comps.iterrows()):
                nr = evals_session[evals_session["competence_id"]==cr["competence_id"]]["niveau"].values
                if nr.size > 0:
                    c.setFont(FONT_BOLD, 9)
                    c.drawString(468, H-(163.0+idx*11.2), str(nr[0]))
    return overlay_on_template(tpl, make_overlay(draw, (W, H)))


# ── Émargement ────────────────────────────────────────────────

def pdf_emargement(tpl, session_row, stag_row, prog_row):
    W, H = 607.0, 999.0
    def draw(c):
        c.setFillColorRGB(1,1,1)
        c.rect(100, H-65, 400, 18, fill=1, stroke=0)
        c.rect(0,   H-83, 380, 13, fill=1, stroke=0)
        sc(c, DARK)
        c.setFont(FONT_BOLD, 13)
        nw = c.stringWidth(stag_row["nom"], FONT_BOLD, 13)
        c.drawString((W-nw)/2, H-58, stag_row["nom"])
        c.setFont(FONT_NORMAL, 10)
        c.drawString(50, H-77, prog_row["nom_programme"])
        try:
            nb_j = int(float(prog_row["duree_heures"])/8)
        except Exception:
            nb_j = 0
        c.drawString(515, H-77, f"{nb_j} jours")
        try:
            d1 = pd.to_datetime(session_row["date_debut"]).date()
            d2 = pd.to_datetime(session_row["date_fin"]).date()
            from datetime import timedelta
            jours, cur = [], d1
            while cur <= d2 and len(jours) < 14:
                if cur.weekday() < 5: jours.append(cur)
                cur += timedelta(days=1)
            c.setFont(FONT_NORMAL, 9)
            for i, j in enumerate(jours):
                y = H - (162 + i*90 + 32)
                c.setFillColorRGB(1,1,1)
                c.rect(20, y-4, 110, 13, fill=1, stroke=0)
                sc(c, DARK)
                c.drawString(25, y, str(i+1))
                c.drawString(48, y, j.strftime("%d/%m/%y"))
        except Exception:
            pass
    return overlay_on_template(tpl, make_overlay(draw, (W, H)))


# ════════════════════════════════════════════════════════════
# CONTRAT COMPLET — assemblage de toutes les pages
# ════════════════════════════════════════════════════════════

def pdf_contrat_complet(session_row, stag_row, prog_row, formateur_nom):
    """
    Assemble dans l'ordre :
      1. Convocation (page 1)
      2. Règlement intérieur (pages 2-3) — fixe
      3. Droit à l'image (page 4)
      4. Programme de formation (pages 5-7)
    """
    parts = []
    errors = []

    # Page 1 — Convocation
    tpl_conv = get_tpl("convocation")
    if tpl_conv:
        try:
            # Extraire seulement la page 1 du contrat (qui contient aussi les pages suivantes)
            reader = PdfReader(str(tpl_conv))
            writer = PdfWriter()
            writer.add_page(reader.pages[0])
            p1_buf = BytesIO(); writer.write(p1_buf)
            p1_tpl = Path("/tmp/conv_p1.pdf"); p1_tpl.write_bytes(p1_buf.getvalue())
            parts.append(pdf_convocation(p1_tpl, session_row, stag_row, prog_row))
        except Exception as e:
            errors.append(f"Convocation : {e}")

    # Pages 2-3 — Règlement intérieur (fixe)
    tpl_ri = get_tpl("reglement")
    if tpl_ri:
        try:
            parts.append(tpl_ri.read_bytes())
        except Exception as e:
            errors.append(f"Règlement : {e}")

    # Page 4 — Droit à l'image
    tpl_di = get_tpl("droit_image")
    if tpl_di:
        try:
            parts.append(pdf_droit_image(tpl_di, session_row, stag_row, prog_row))
        except Exception as e:
            errors.append(f"Droit image : {e}")

    # Pages 5-7 — Programme
    tpl_prog = get_tpl("programme")
    if tpl_prog:
        try:
            parts.append(pdf_programme(tpl_prog, session_row, prog_row))
        except Exception as e:
            errors.append(f"Programme : {e}")

    if not parts:
        return None, ["Aucun template chargé pour le contrat."]

    return merge_pdfs(parts), errors


# ════════════════════════════════════════════════════════════
# BPF — Bilan Pédagogique et Financier (généré from scratch)
# ════════════════════════════════════════════════════════════

def pdf_bpf(annee: int, organisme: str = "Art de Pâtisser") -> bytes:
    buf  = BytesIO()
    doc  = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm,  bottomMargin=2*cm,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Titre",    fontSize=18, fontName=FONT_BOLD,
                               textColor=colors.HexColor("#1E3A5F"),
                               alignment=TA_CENTER, spaceAfter=4))
    styles.add(ParagraphStyle("SousTitre",fontSize=11, fontName=FONT_NORMAL,
                               textColor=colors.HexColor("#6B7280"),
                               alignment=TA_CENTER, spaceAfter=16))
    styles.add(ParagraphStyle("Section",  fontSize=12, fontName=FONT_BOLD,
                               textColor=colors.HexColor("#1E3A5F"),
                               spaceBefore=14, spaceAfter=6))
    styles.add(ParagraphStyle("Corps",    fontSize=10, fontName=FONT_NORMAL,
                               textColor=colors.HexColor("#374151"),
                               spaceAfter=4, leading=14))
    styles.add(ParagraphStyle("Small",    fontSize=8,  fontName=FONT_NORMAL,
                               textColor=colors.HexColor("#9CA3AF"),
                               alignment=TA_CENTER))

    TH = colors.HexColor("#1E3A5F")
    ALT = colors.HexColor("#F0F4F8")

    def tbl_style():
        return TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  TH),
            ("TEXTCOLOR",     (0,0), (-1,0),  colors.white),
            ("FONTNAME",      (0,0), (-1,0),  FONT_BOLD),
            ("FONTSIZE",      (0,0), (-1,0),  9),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, ALT]),
            ("FONTNAME",      (0,1), (-1,-1), FONT_NORMAL),
            ("FONTSIZE",      (0,1), (-1,-1), 9),
            ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#D1D5DB")),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ])

    story = []

    # En-tête
    story.append(Paragraph(organisme, styles["Titre"]))
    story.append(HRFlowable(width="100%", thickness=2,
                             color=colors.HexColor("#1E3A5F"), spaceAfter=8))
    story.append(Paragraph("BILAN PÉDAGOGIQUE ET FINANCIER", styles["Titre"]))
    story.append(Paragraph(f"Exercice {annee}", styles["SousTitre"]))
    story.append(Spacer(1, 0.3*cm))

    # Infos organisme
    infos = [
        ["Organisme",            organisme],
        ["N° déclaration activité", "76311092431"],
        ["Période de référence",  f"1er janvier {annee} — 31 décembre {annee}"],
        ["Date d'établissement",  date.today().strftime("%d/%m/%Y")],
    ]
    t_info = Table(infos, colWidths=[6*cm, 11*cm])
    t_info.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(0,-1), ALT),
        ("FONTNAME",     (0,0),(0,-1), FONT_BOLD),
        ("FONTNAME",     (1,0),(1,-1), FONT_NORMAL),
        ("FONTSIZE",     (0,0),(-1,-1),10),
        ("GRID",         (0,0),(-1,-1),0.5, colors.HexColor("#D1D5DB")),
        ("TOPPADDING",   (0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("LEFTPADDING",  (0,0),(-1,-1),8),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 0.4*cm))

    # ── Section 1 : Sessions ─────────────────────────────────
    story.append(Paragraph("1. Formations dispensées", styles["Section"]))

    sess_annee = sessions.copy()
    if not sess_annee.empty:
        sess_annee["_annee"] = pd.to_datetime(
            sess_annee["date_debut"], errors="coerce").dt.year
        sess_annee = sess_annee[sess_annee["_annee"] == int(annee)]

    if sess_annee.empty:
        story.append(Paragraph(f"Aucune formation enregistrée pour {annee}.", styles["Corps"]))
    else:
        rows = [["Session", "Programme", "Début", "Fin", "Stagiaires", "Heures", "CA (€)"]]
        total_stag = 0; total_h = 0; total_ca = 0.0

        for _, s in sess_annee.iterrows():
            nb = len(stagiaires[stagiaires["session_id"]==s["session_id"]]) \
                 if not stagiaires.empty else 0
            prog = programmes[programmes["programme_id"]==s["programme_id"]]
            heures = float(prog.iloc[0]["duree_heures"]) if not prog.empty else 0
            try:
                ca = float(str(s["prix"]).replace(",",".") or 0) * nb
            except Exception:
                ca = 0.0
            total_stag += nb; total_h += heures; total_ca += ca
            nom_prog = prog.iloc[0]["nom_programme"] if not prog.empty else "—"
            rows.append([
                s["nom"],
                Paragraph(nom_prog, styles["Corps"]),
                fmt_date(s["date_debut"]),
                fmt_date(s["date_fin"]),
                str(nb),
                f"{heures:.0f}h",
                f"{ca:,.0f} €",
            ])

        # Ligne total
        rows.append(["TOTAL", "", "", "", str(total_stag),
                      f"{total_h:.0f}h", f"{total_ca:,.0f} €"])

        ts = tbl_style()
        ts.add("FONTNAME",   (0,len(rows)-1),(-1,len(rows)-1), FONT_BOLD)
        ts.add("BACKGROUND", (0,len(rows)-1),(-1,len(rows)-1), TH)
        ts.add("TEXTCOLOR",  (0,len(rows)-1),(-1,len(rows)-1), colors.white)

        t = Table(rows, colWidths=[3.5*cm, 4*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.5*cm, 2.1*cm])
        t.setStyle(ts)
        story.append(t)

    story.append(Spacer(1, 0.4*cm))

    # ── Section 2 : Stagiaires ───────────────────────────────
    story.append(Paragraph("2. Stagiaires formés", styles["Section"]))

    if not stagiaires.empty and not sess_annee.empty:
        stag_annee = stagiaires[stagiaires["session_id"].isin(sess_annee["session_id"])]
        nb_total    = len(stag_annee)
        nb_uniques  = stag_annee["nom"].nunique()
        entreprises = stag_annee["entreprise"].replace("", "Particulier")

        recap_stag = [
            ["Indicateur",                 "Valeur"],
            ["Nombre de stagiaires (entrées)", str(nb_total)],
            ["Nombre de stagiaires uniques",   str(nb_uniques)],
            ["Nombre d'entreprises bénéficiaires",
             str(entreprises.nunique())],
        ]
        t2 = Table(recap_stag, colWidths=[10*cm, 7*cm])
        t2.setStyle(tbl_style())
        story.append(t2)
    else:
        story.append(Paragraph("Aucun stagiaire enregistré.", styles["Corps"]))

    story.append(Spacer(1, 0.4*cm))

    # ── Section 3 : Financier ────────────────────────────────
    story.append(Paragraph("3. Données financières", styles["Section"]))

    if not sess_annee.empty:
        total_ca_val  = 0.0
        total_cout    = 0.0
        for _, s in sess_annee.iterrows():
            nb = len(stagiaires[stagiaires["session_id"]==s["session_id"]]) \
                 if not stagiaires.empty else 0
            try:
                total_ca_val  += float(str(s["prix"]).replace(",",".") or 0) * nb
                total_cout    += float(str(s["cout_prevu"]).replace(",",".") or 0)
            except Exception:
                pass

        fin_data = [
            ["Poste",                   "Montant"],
            ["Chiffre d'affaires formation", f"{total_ca_val:,.0f} €"],
            ["Coût prévisionnel total",       f"{total_cout:,.0f} €"],
            ["Marge brute estimée",
             f"{(total_ca_val - total_cout):,.0f} €"],
        ]
        t3 = Table(fin_data, colWidths=[10*cm, 7*cm])
        t3.setStyle(tbl_style())
        story.append(t3)
    else:
        story.append(Paragraph("Aucune donnée financière disponible.", styles["Corps"]))

    story.append(Spacer(1, 0.4*cm))

    # ── Section 4 : Satisfaction ─────────────────────────────
    story.append(Paragraph("4. Résultats satisfaction stagiaires", styles["Section"]))

    sat_annee = pd.DataFrame()
    if not satisfaction.empty and not sess_annee.empty:
        sat_annee = satisfaction[
            satisfaction["session_id"].isin(sess_annee["session_id"]) &
            (satisfaction["note"] != "")
        ].copy()

    if sat_annee.empty:
        story.append(Paragraph("Aucune évaluation de satisfaction enregistrée.", styles["Corps"]))
    else:
        sat_annee["note_num"] = pd.to_numeric(sat_annee["note"], errors="coerce")
        moy_glob = sat_annee["note_num"].mean()
        moy_rub  = sat_annee.groupby("rubrique")["note_num"].mean().reset_index()
        moy_rub.columns = ["Rubrique", "Moyenne (/4)"]
        moy_rub["Moyenne (/4)"] = moy_rub["Moyenne (/4)"].apply(lambda x: f"{x:.2f}")

        story.append(Paragraph(
            f"Moyenne générale de satisfaction : <b>{moy_glob:.2f} / 4</b> "
            f"({'Très bien' if moy_glob>=3.5 else 'Bien' if moy_glob>=2.5 else 'Moyen'})",
            styles["Corps"]
        ))
        story.append(Spacer(1, 0.2*cm))

        rows_sat = [["Rubrique", "Moyenne /4"]] + moy_rub.values.tolist()
        t4 = Table(rows_sat, colWidths=[13*cm, 4*cm])
        t4.setStyle(tbl_style())
        story.append(t4)

    story.append(Spacer(1, 0.6*cm))

    # Signature
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=colors.HexColor("#D1D5DB"), spaceAfter=8))
    sig = Table(
        [[f"Fait à Toulouse le {date.today().strftime('%d/%m/%Y')}",
          "Signature du responsable"],
         ["", ""]],
        colWidths=[9*cm, 8*cm],
        rowHeights=[0.6*cm, 2.5*cm],
    )
    sig.setStyle(TableStyle([
        ("FONTNAME",  (0,0),(-1,-1), FONT_NORMAL),
        ("FONTSIZE",  (0,0),(-1,-1), 9),
        ("BOX",       (1,0),(1,1),  0.5, colors.grey),
        ("ALIGN",     (1,0),(1,1),  "CENTER"),
    ]))
    story.append(sig)
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        f"Art de Pâtisser — SIRET 889519633 00016 — "
        f"OF n° 76311092431 — Document conforme Qualiopi",
        styles["Small"]
    ))

    doc.build(story)
    return buf.getvalue()


# ════════════════════════════════════════════════════════════
# INTERFACE STREAMLIT
# ════════════════════════════════════════════════════════════

st.title("📄 Documents Qualiopi — Art de Pâtisser")

# ── Sidebar templates ─────────────────────────────────────────
TEMPLATES = {
    "certificat":   "Certificat de réalisation",
    "convocation":  "Convocation (page 1 du contrat)",
    "reglement":    "Règlement intérieur (pages 2-3)",
    "droit_image":  "Droit à l'image (page 4)",
    "programme":    "Programme de formation (pages 5-7)",
    "satisfaction": "Satisfaction stagiaire",
    "auto_eval":    "Auto-évaluation stagiaire",
    "bilan_form":   "Bilan formateur",
    "emargement":   "Feuille d'émargement",
}

with st.sidebar:
    st.header("📁 Templates PDF")
    st.caption("Dépose chaque page une seule fois")
    for key, label in TEMPLATES.items():
        folder = TEMPLATE_DIR / key
        folder.mkdir(exist_ok=True)
        if list(folder.glob("*.pdf")):
            st.success(f"✅ {label}")
        else:
            up = st.file_uploader(f"📎 {label}", type="pdf", key=f"up_{key}")
            if up:
                (folder / up.name).write_bytes(up.read())
                st.success(f"✅ {label} sauvegardé")
                st.rerun()
    st.divider()
    st.caption("PDFs générés dans /exports")

# ── Sélection session ─────────────────────────────────────────
if sessions.empty:
    st.warning("Aucune session disponible.")
    st.stop()

session_label = st.selectbox("Session", sessions["session_id"] + " — " + sessions["nom"])
session_id    = session_label.split(" — ")[0]
session_row   = sessions[sessions["session_id"] == session_id].iloc[0]
programme_id  = session_row["programme_id"]
formateur_id  = session_row["formateur_id"]
prog_row      = programmes[programmes["programme_id"] == programme_id].iloc[0] \
                if not programmes.empty and programme_id else None
formateur_nom = get(formateurs, "formateur_id", formateur_id, "nom", "—")
stag_session  = stagiaires[stagiaires["session_id"] == session_id] \
                if not stagiaires.empty else pd.DataFrame()
comps_session = competences[
    competences["referentiel_id"] == (prog_row["referentiel_id"] if prog_row else "")
] if not competences.empty and prog_row is not None else pd.DataFrame()

st.info(
    f"**{session_row['nom']}** | "
    f"{fmt_date(session_row['date_debut'])} → {fmt_date(session_row['date_fin'])} | "
    f"**{len(stag_session)} stagiaire(s)**"
)
st.divider()

# ── Helper UI ─────────────────────────────────────────────────

def doc_ui(key, gen_fn_stag=None, gen_fn_session=None, label="document"):
    tpl = get_tpl(key)
    if not tpl and gen_fn_stag:
        st.warning(f"Template manquant — charge-le dans la sidebar.")
        return

    if gen_fn_session:
        try:
            pdf_bytes = gen_fn_session(tpl)
            fname = f"{key}_{session_id}.pdf"
            (EXPORT_DIR / fname).write_bytes(pdf_bytes)
            st.download_button("⬇️ Télécharger", data=pdf_bytes,
                               file_name=fname, mime="application/pdf",
                               key=f"dl_{key}")
        except Exception as e:
            st.error(f"Erreur : {e}")
        return

    if stag_session.empty:
        st.warning("Aucun stagiaire dans cette session.")
        return

    if st.button(f"📦 ZIP — tous les stagiaires", key=f"zip_{key}"):
        buf = BytesIO()
        errs = []
        with zipfile.ZipFile(buf, "w") as zf:
            for _, stag in stag_session.iterrows():
                try:
                    pb = gen_fn_stag(tpl, stag)
                    fn = f"{key}_{stag['nom'].replace(' ','_')}.pdf"
                    zf.writestr(fn, pb)
                    (EXPORT_DIR / fn).write_bytes(pb)
                except Exception as e:
                    errs.append(f"{stag['nom']}: {e}")
        for err in errs:
            st.error(err)
        if not errs:
            st.download_button("⬇️ Télécharger ZIP", data=buf.getvalue(),
                               file_name=f"{key}_{session_id}.zip",
                               mime="application/zip", key=f"dlzip_{key}")

    st.markdown("— ou —")
    sl = st.selectbox("Stagiaire",
                      stag_session["stagiaire_id"] + " — " + stag_session["nom"],
                      key=f"sel_{key}")
    sid = sl.split(" — ")[0]
    sr  = stag_session[stag_session["stagiaire_id"] == sid].iloc[0]
    try:
        pb  = gen_fn_stag(tpl, sr)
        fn  = f"{key}_{sr['nom'].replace(' ','_')}.pdf"
        (EXPORT_DIR / fn).write_bytes(pb)
        st.download_button(f"⬇️ {sr['nom']}", data=pb,
                           file_name=fn, mime="application/pdf",
                           key=f"dlsingle_{key}")
    except Exception as e:
        st.error(f"Erreur : {e}")


# ── Onglets ───────────────────────────────────────────────────

tabs = st.tabs([
    "📦 Contrat complet",
    "🎓 Certificat",
    "📨 Convocation",
    "🖼️ Droit à l'image",
    "📋 Programme",
    "✅ Satisfaction",
    "🔍 Auto-évaluation",
    "📊 Bilan formateur",
    "✍️ Émargement",
    "📈 BPF",
])

# ── Contrat complet ───────────────────────────────────────────
with tabs[0]:
    st.subheader("Contrat de formation complet (toutes pages assemblées)")
    st.caption("Convocation + Règlement intérieur + Droit à l'image + Programme")

    if prog_row is None:
        st.warning("Programme introuvable.")
    elif stag_session.empty:
        st.warning("Aucun stagiaire.")
    else:
        if st.button("📦 ZIP contrats complets — tous les stagiaires", key="zip_contrat"):
            buf = BytesIO()
            errs = []
            with zipfile.ZipFile(buf, "w") as zf:
                for _, stag in stag_session.iterrows():
                    pdf_bytes, errors = pdf_contrat_complet(
                        session_row, stag, prog_row, formateur_nom)
                    if pdf_bytes:
                        fn = f"contrat_{stag['nom'].replace(' ','_')}.pdf"
                        zf.writestr(fn, pdf_bytes)
                        (EXPORT_DIR / fn).write_bytes(pdf_bytes)
                    for e in errors:
                        errs.append(f"{stag['nom']}: {e}")
            for err in errs:
                st.warning(err)
            st.download_button("⬇️ Télécharger ZIP", data=buf.getvalue(),
                               file_name=f"contrats_{session_id}.zip",
                               mime="application/zip", key="dlzip_contrat")

        st.markdown("— ou —")
        sl = st.selectbox("Stagiaire", stag_session["stagiaire_id"] + " — " + stag_session["nom"],
                          key="sel_contrat")
        sid = sl.split(" — ")[0]
        sr  = stag_session[stag_session["stagiaire_id"] == sid].iloc[0]
        pdf_bytes, errors = pdf_contrat_complet(session_row, sr, prog_row, formateur_nom)
        for e in errors:
            st.warning(e)
        if pdf_bytes:
            fn = f"contrat_{sr['nom'].replace(' ','_')}.pdf"
            (EXPORT_DIR / fn).write_bytes(pdf_bytes)
            st.download_button(f"⬇️ Contrat — {sr['nom']}", data=pdf_bytes,
                               file_name=fn, mime="application/pdf",
                               key="dlsingle_contrat")

# ── Certificat ───────────────────────────────────────────────
with tabs[1]:
    st.subheader("Certificat de réalisation")
    if prog_row is not None:
        doc_ui("certificat",
               gen_fn_stag=lambda tpl, stag: pdf_certificat(
                   tpl, session_row, stag, prog_row, formateur_nom))
    else:
        st.warning("Programme introuvable.")

# ── Convocation ───────────────────────────────────────────────
with tabs[2]:
    st.subheader("Convocation")
    if prog_row is not None:
        doc_ui("convocation",
               gen_fn_stag=lambda tpl, stag: pdf_convocation(
                   tpl, session_row, stag, prog_row))
    else:
        st.warning("Programme introuvable.")

# ── Droit à l'image ───────────────────────────────────────────
with tabs[3]:
    st.subheader("Droit à l'image")
    if prog_row is not None:
        doc_ui("droit_image",
               gen_fn_stag=lambda tpl, stag: pdf_droit_image(
                   tpl, session_row, stag, prog_row))
    else:
        st.warning("Programme introuvable.")

# ── Programme ─────────────────────────────────────────────────
with tabs[4]:
    st.subheader("Programme de formation")
    tpl_prog = get_tpl("programme")
    if tpl_prog is None:
        st.warning("Template programme manquant.")
    elif prog_row is None:
        st.warning("Programme introuvable.")
    else:
        pdf_bytes = pdf_programme(tpl_prog, session_row, prog_row)
        fn = f"programme_{session_id}.pdf"
        (EXPORT_DIR / fn).write_bytes(pdf_bytes)
        st.download_button("⬇️ Télécharger", data=pdf_bytes,
                           file_name=fn, mime="application/pdf")

# ── Satisfaction ──────────────────────────────────────────────
with tabs[5]:
    st.subheader("Évaluation satisfaction stagiaire")
    doc_ui("satisfaction",
           gen_fn_stag=lambda tpl, stag: pdf_satisfaction(tpl, session_row, stag))

# ── Auto-évaluation ───────────────────────────────────────────
with tabs[6]:
    st.subheader("Auto-évaluation stagiaire")
    def _gen_ae(tpl, stag):
        ae = auto_evaluation[
            (auto_evaluation["stagiaire_id"] == stag["stagiaire_id"]) &
            (auto_evaluation["session_id"]   == session_id)
        ] if not auto_evaluation.empty else pd.DataFrame()
        return pdf_auto_evaluation(tpl, session_row, stag, ae, comps_session)
    doc_ui("auto_eval", gen_fn_stag=_gen_ae)

# ── Bilan formateur ───────────────────────────────────────────
with tabs[7]:
    st.subheader("Bilan formateur")
    evals_s = evaluations[evaluations["session_id"] == session_id] \
              if not evaluations.empty else pd.DataFrame()
    doc_ui("bilan_form",
           gen_fn_session=lambda tpl: pdf_bilan_formateur(
               tpl, session_row, formateur_nom, evals_s, comps_session))

# ── Émargement ────────────────────────────────────────────────
with tabs[8]:
    st.subheader("Feuille d'émargement")
    if prog_row is not None:
        doc_ui("emargement",
               gen_fn_stag=lambda tpl, stag: pdf_emargement(
                   tpl, session_row, stag, prog_row))
    else:
        st.warning("Programme introuvable.")

# ── BPF ──────────────────────────────────────────────────────
with tabs[9]:
    st.subheader("Bilan Pédagogique et Financier (BPF)")
    st.caption("Document annuel obligatoire Qualiopi — généré automatiquement depuis les données HOF")

    col1, col2 = st.columns([2, 3])
    with col1:
        annee_bpf = st.selectbox(
            "Année",
            list(range(date.today().year, date.today().year - 5, -1)),
        )
    with col2:
        organisme_bpf = st.text_input("Nom de l'organisme", value="Art de Pâtisser")

    if st.button("📊 Générer le BPF", type="primary"):
        with st.spinner("Génération du BPF..."):
            pdf_bytes = pdf_bpf(annee_bpf, organisme_bpf)
        fn = f"BPF_{annee_bpf}.pdf"
        (EXPORT_DIR / fn).write_bytes(pdf_bytes)
        st.success(f"BPF {annee_bpf} généré")
        st.download_button("⬇️ Télécharger le BPF", data=pdf_bytes,
                           file_name=fn, mime="application/pdf")

# ── Liste exports ─────────────────────────────────────────────
with st.expander("📁 Fichiers dans /exports"):
    files = sorted(EXPORT_DIR.glob("*.pdf"))
    if files:
        for f in files:
            c1, c2 = st.columns([4, 1])
            c1.text(f.name)
            c2.write(f"{f.stat().st_size // 1024} Ko")
    else:
        st.info("Aucun fichier pour l'instant.")
