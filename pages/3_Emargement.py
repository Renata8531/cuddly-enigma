import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, date, timedelta
from io import BytesIO
import uuid
import zipfile
import hashlib
import hmac

from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader, PdfWriter

# ============================================================
# HOF - Émargement par QR code
# pages/3_Emargement.py
#
# Flux :
#   1. Formateur génère une feuille QR par stagiaire (PDF)
#   2. Stagiaire scanne → page Streamlit émargement_stagiaire
#   3. Présence enregistrée dans emargements.csv
#   4. Formateur voit le récap en temps réel
# ============================================================

DATA_DIR     = Path("data")
EXPORT_DIR   = Path("exports")
TEMPLATE_DIR = Path("templates")
EXPORT_DIR.mkdir(exist_ok=True)

# ── Secret pour sécuriser les tokens ────────────────────────
# En prod : mettre dans st.secrets["emargement_secret"]
SECRET = st.secrets.get("emargement_secret", "hof-artdepatisser-2025") \
         if hasattr(st, "secrets") else "hof-artdepatisser-2025"

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

def save(path, df):
    path.parent.mkdir(exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")

sessions    = load(DATA_DIR / "sessions.csv",
                   ["session_id","programme_id","formateur_id","nom",
                    "date_debut","date_fin","prix","cout_prevu"])
stagiaires  = load(DATA_DIR / "stagiaires.csv",
                   ["stagiaire_id","session_id","nom","email","entreprise","lien_unique"])
formateurs  = load(DATA_DIR / "formateurs.csv",
                   ["formateur_id","nom","email","specialite","lien_unique"])
programmes  = load(DATA_DIR / "programmes.csv",
                   ["programme_id","referentiel_id","nom_programme","duree_heures",
                    "objectifs","prerequis","modalites"])
emargements = load(DATA_DIR / "emargements.csv",
                   ["emargement_id","stagiaire_id","session_id","date",
                    "moment","signature_stagiaire","signature_formateur","horodatage"])

# ── Helpers ──────────────────────────────────────────────────

def fmt_date(s):
    try:
        return pd.to_datetime(s).strftime("%d/%m/%Y")
    except Exception:
        return str(s)

def get(df, id_col, val, target_col, fallback=""):
    r = df[df[id_col] == val]
    return str(r.iloc[0][target_col]) if not r.empty else fallback

def make_token(stagiaire_id: str, session_id: str, jour: str, moment: str) -> str:
    """Génère un token HMAC signé pour sécuriser le lien d'émargement."""
    msg = f"{stagiaire_id}|{session_id}|{jour}|{moment}"
    return hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16]

def verify_token(token: str, stagiaire_id: str, session_id: str,
                 jour: str, moment: str) -> bool:
    return hmac.compare_digest(token, make_token(stagiaire_id, session_id, jour, moment))

def deja_emarge(stagiaire_id, session_id, jour, moment) -> bool:
    if emargements.empty:
        return False
    return not emargements[
        (emargements["stagiaire_id"] == stagiaire_id) &
        (emargements["session_id"]   == session_id)   &
        (emargements["date"]         == jour)          &
        (emargements["moment"]       == moment)
    ].empty

# ── Génération QR code ReportLab ─────────────────────────────

def make_qr_drawing(url: str, size: float = 80) -> Drawing:
    qr_widget = qr.QrCodeWidget(url)
    b = qr_widget.getBounds()
    w, h = b[2] - b[0], b[3] - b[1]
    d = Drawing(size, size, transform=[size/w, 0, 0, size/h, 0, 0])
    d.add(qr_widget)
    return d

def pdf_qr_stagiaire(stagiaire_row, session_row, prog_row,
                     base_url: str, jours_formation: list) -> bytes:
    """
    Génère une feuille PDF avec tous les QR codes du stagiaire
    (un QR matin + un QR après-midi par jour de formation).
    """
    W, H = A4
    buf  = BytesIO()
    c    = rl_canvas.Canvas(buf, pagesize=A4)

    nom_stag  = stagiaire_row["nom"]
    nom_form  = prog_row["nom_programme"]
    stag_id   = stagiaire_row["stagiaire_id"]
    sess_id   = session_row["session_id"]

    # ── En-tête ──────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(0.12, 0.23, 0.37)
    c.drawCentredString(W/2, H - 50, "FEUILLE D'ÉMARGEMENT QR CODE")

    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0.68, 0.05, 0.05)
    c.drawCentredString(W/2, H - 72, nom_stag)

    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawCentredString(W/2, H - 88,
        f"{nom_form}  |  {fmt_date(session_row['date_debut'])} → {fmt_date(session_row['date_fin'])}")

    c.setFont("Helvetica-Oblique", 8)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawCentredString(W/2, H - 102,
        "Scannez le QR code correspondant au bon moment de la journée")

    # Ligne séparatrice
    c.setStrokeColorRGB(0.12, 0.23, 0.37)
    c.setLineWidth(1.5)
    c.line(40, H - 112, W - 40, H - 112)

    # ── Grille QR codes ──────────────────────────────────────
    QR_SIZE  = 90   # px du QR
    COL_W    = (W - 80) / 2   # 2 colonnes : matin | après-midi
    ROW_H    = 130  # hauteur d'une ligne jour
    START_Y  = H - 130

    for idx, jour in enumerate(jours_formation):
        jour_str  = jour.strftime("%Y-%m-%d")
        jour_disp = jour.strftime("%A %d/%m/%Y").capitalize()

        row_y = START_Y - idx * ROW_H

        # Nouvelle page si on dépasse
        if row_y < 80:
            c.showPage()
            c.setFont("Helvetica-Bold", 10)
            c.setFillColorRGB(0.12, 0.23, 0.37)
            c.drawCentredString(W/2, H - 30, f"{nom_stag} — {nom_form} (suite)")
            row_y = H - 60

        # Fond alterné
        if idx % 2 == 0:
            c.setFillColorRGB(0.97, 0.97, 0.97)
            c.rect(40, row_y - ROW_H + 10, W - 80, ROW_H - 5, fill=1, stroke=0)

        # Jour label
        c.setFont("Helvetica-Bold", 10)
        c.setFillColorRGB(0.12, 0.23, 0.37)
        c.drawString(48, row_y - 18, f"Jour {idx+1}  —  {jour_disp}")

        for col, moment in enumerate(["matin", "apres-midi"]):
            token = make_token(stag_id, sess_id, jour_str, moment)
            url   = (f"{base_url}?stag={stag_id}&sess={sess_id}"
                     f"&jour={jour_str}&moment={moment}&token={token}")

            x_qr  = 48 + col * COL_W + (COL_W - QR_SIZE) / 2
            y_qr  = row_y - ROW_H + 28

            # QR code
            d = make_qr_drawing(url, QR_SIZE)
            renderPDF.draw(d, c, x_qr, y_qr)

            # Label sous le QR
            label = "🌅 MATIN" if moment == "matin" else "🌇 APRÈS-MIDI"
            c.setFont("Helvetica-Bold", 9)
            c.setFillColorRGB(0.2, 0.2, 0.2)
            c.drawCentredString(x_qr + QR_SIZE/2, y_qr - 14, label)

            # Statut (déjà émargé ou non)
            if deja_emarge(stag_id, sess_id, jour_str, moment):
                c.setFillColorRGB(0.06, 0.72, 0.36)
                c.setFont("Helvetica-Bold", 8)
                c.drawCentredString(x_qr + QR_SIZE/2, y_qr - 26, "✓ Émargé")

    # ── Pied de page ─────────────────────────────────────────
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.6, 0.6, 0.6)
    c.drawCentredString(W/2, 20,
        f"Art de Pâtisser — Document généré le {date.today().strftime('%d/%m/%Y')}")

    c.save()
    return buf.getvalue()


def pdf_qr_session(session_row, prog_row, stags, base_url) -> dict:
    """Génère un PDF QR par stagiaire, retourne dict {nom: bytes}."""
    try:
        d1 = pd.to_datetime(session_row["date_debut"]).date()
        d2 = pd.to_datetime(session_row["date_fin"]).date()
        jours = []
        cur = d1
        while cur <= d2:
            if cur.weekday() < 5:
                jours.append(cur)
            cur += timedelta(days=1)
    except Exception:
        jours = []

    results = {}
    for _, stag in stags.iterrows():
        pdf_bytes = pdf_qr_stagiaire(stag, session_row, prog_row, base_url, jours)
        results[stag["nom"]] = pdf_bytes
    return results


# ════════════════════════════════════════════════════════════
# INTERFACE STREAMLIT
# ════════════════════════════════════════════════════════════

st.title("✍️ Émargement QR Code")

# ── Détection mode : formateur ou stagiaire ──────────────────
params = st.query_params

MODE_STAGIAIRE = all(k in params for k in ["stag", "sess", "jour", "moment", "token"])

# ════════════════════════════════════════════════════════════
# MODE STAGIAIRE — page ouverte depuis le QR code
# ════════════════════════════════════════════════════════════

if MODE_STAGIAIRE:
    stag_id  = params["stag"]
    sess_id  = params["sess"]
    jour     = params["jour"]
    moment   = params["moment"]
    token    = params["token"]

    st.markdown("## ✍️ Émargement")

    # Vérification token
    if not verify_token(token, stag_id, sess_id, jour, moment):
        st.error("❌ Lien invalide ou expiré.")
        st.stop()

    # Récupérer le stagiaire
    stag_rows = stagiaires[stagiaires["stagiaire_id"] == stag_id]
    sess_rows = sessions[sessions["session_id"] == sess_id]

    if stag_rows.empty or sess_rows.empty:
        st.error("❌ Stagiaire ou session introuvable.")
        st.stop()

    stag_row = stag_rows.iloc[0]
    sess_row = sess_rows.iloc[0]
    moment_label = "Matin" if moment == "matin" else "Après-midi"

    try:
        jour_disp = pd.to_datetime(jour).strftime("%A %d/%m/%Y").capitalize()
    except Exception:
        jour_disp = jour

    st.success(f"Bonjour **{stag_row['nom']}** 👋")
    st.markdown(f"""
    | | |
    |---|---|
    | **Formation** | {sess_row['nom']} |
    | **Date** | {jour_disp} |
    | **Moment** | {moment_label} |
    """)

    # Déjà émargé ?
    global emargements
    emargements = load(DATA_DIR / "emargements.csv",
                       ["emargement_id","stagiaire_id","session_id","date",
                        "moment","signature_stagiaire","signature_formateur","horodatage"])

    if deja_emarge(stag_id, sess_id, jour, moment):
        st.info("✅ Vous avez déjà émargé pour ce créneau.")
        st.stop()

    # Heure actuelle
    now = datetime.now()
    heure_actuelle = now.strftime("%H:%M")

    if moment == "matin" and not (6 <= now.hour < 14):
        st.warning(f"⚠️ Ce QR code est pour le matin. Il est actuellement {heure_actuelle}.")

    if moment == "apres-midi" and not (12 <= now.hour < 21):
        st.warning(f"⚠️ Ce QR code est pour l'après-midi. Il est actuellement {heure_actuelle}.")

    st.markdown("---")
    st.markdown("### Confirmer votre présence")
    st.caption(f"Heure actuelle : {now.strftime('%d/%m/%Y à %H:%M:%S')}")

    if st.button("✅ Je confirme ma présence", type="primary", use_container_width=True):
        new_row = {
            "emargement_id":      f"EM{uuid.uuid4().hex[:8].upper()}",
            "stagiaire_id":       stag_id,
            "session_id":         sess_id,
            "date":               jour,
            "moment":             moment,
            "signature_stagiaire": f"OK_{now.strftime('%H:%M:%S')}",
            "signature_formateur": "",
            "horodatage":         now.isoformat(timespec="seconds"),
        }
        emargements = pd.concat(
            [emargements, pd.DataFrame([new_row])], ignore_index=True
        )
        save(DATA_DIR / "emargements.csv", emargements)
        st.success(f"✅ Présence enregistrée — {jour_disp} {moment_label} à {heure_actuelle}")
        st.balloons()

    st.stop()


# ════════════════════════════════════════════════════════════
# MODE FORMATEUR — interface principale
# ════════════════════════════════════════════════════════════

if sessions.empty:
    st.warning("Aucune session disponible.")
    st.stop()

tabs = st.tabs(["📄 Générer QR codes", "📊 Suivi présences"])

# ── Onglet 1 : Générer QR codes ──────────────────────────────
with tabs[0]:
    st.subheader("Générer les feuilles QR code par stagiaire")

    col1, col2 = st.columns([3, 2])
    with col1:
        session_label = st.selectbox(
            "Session",
            sessions["session_id"] + " — " + sessions["nom"],
            key="qr_session"
        )
    with col2:
        base_url = st.text_input(
            "URL de l'app Streamlit",
            value="http://localhost:8501/Emargement",
            help="L'URL où les stagiaires accèdent à l'app (ex: https://ton-app.streamlit.app/Emargement)",
        )

    session_id  = session_label.split(" — ")[0]
    session_row = sessions[sessions["session_id"] == session_id].iloc[0]
    programme_id = session_row["programme_id"]
    prog_row = programmes[programmes["programme_id"] == programme_id].iloc[0] \
               if not programmes.empty and programme_id else None
    stag_session = stagiaires[stagiaires["session_id"] == session_id] \
                   if not stagiaires.empty else pd.DataFrame()

    if prog_row is None:
        st.warning("Programme introuvable pour cette session.")
    elif stag_session.empty:
        st.warning("Aucun stagiaire dans cette session.")
    else:
        # Calcul jours de formation
        try:
            d1 = pd.to_datetime(session_row["date_debut"]).date()
            d2 = pd.to_datetime(session_row["date_fin"]).date()
            jours = []
            cur = d1
            while cur <= d2:
                if cur.weekday() < 5:
                    jours.append(cur)
                cur += timedelta(days=1)
        except Exception:
            jours = []

        st.info(
            f"**{session_row['nom']}** | "
            f"{fmt_date(session_row['date_debut'])} → {fmt_date(session_row['date_fin'])} | "
            f"**{len(stag_session)} stagiaire(s)** | **{len(jours)} jour(s)**"
        )

        # Aperçu des jours
        if jours:
            with st.expander(f"📅 {len(jours)} jours de formation détectés"):
                for i, j in enumerate(jours):
                    st.write(f"Jour {i+1} — {j.strftime('%A %d/%m/%Y').capitalize()}")

        st.divider()

        # ZIP tous les stagiaires
        if st.button("📦 Générer ZIP — tous les QR codes", type="primary"):
            with st.spinner("Génération en cours..."):
                buf = BytesIO()
                with zipfile.ZipFile(buf, "w") as zf:
                    for _, stag in stag_session.iterrows():
                        pdf_bytes = pdf_qr_stagiaire(
                            stag, session_row, prog_row, base_url, jours
                        )
                        fname = f"qr_{stag['nom'].replace(' ', '_')}.pdf"
                        zf.writestr(fname, pdf_bytes)
                        (EXPORT_DIR / fname).write_bytes(pdf_bytes)

            st.download_button(
                "⬇️ Télécharger le ZIP",
                data=buf.getvalue(),
                file_name=f"qr_emargement_{session_id}.zip",
                mime="application/zip",
            )

        st.markdown("— ou un stagiaire —")

        stag_label = st.selectbox(
            "Stagiaire",
            stag_session["stagiaire_id"] + " — " + stag_session["nom"],
            key="qr_stag_sel"
        )
        stag_id_sel  = stag_label.split(" — ")[0]
        stag_row_sel = stag_session[stag_session["stagiaire_id"] == stag_id_sel].iloc[0]

        pdf_bytes = pdf_qr_stagiaire(
            stag_row_sel, session_row, prog_row, base_url, jours
        )
        fname = f"qr_{stag_row_sel['nom'].replace(' ', '_')}.pdf"
        (EXPORT_DIR / fname).write_bytes(pdf_bytes)
        st.download_button(
            f"⬇️ QR codes — {stag_row_sel['nom']}",
            data=pdf_bytes,
            file_name=fname,
            mime="application/pdf",
        )


# ── Onglet 2 : Suivi présences ───────────────────────────────
with tabs[1]:
    st.subheader("Suivi des présences en temps réel")

    # Recharger les émargements à chaque affichage
    emargements = load(DATA_DIR / "emargements.csv",
                       ["emargement_id","stagiaire_id","session_id","date",
                        "moment","signature_stagiaire","signature_formateur","horodatage"])

    session_label2 = st.selectbox(
        "Session",
        sessions["session_id"] + " — " + sessions["nom"],
        key="suivi_session"
    )
    session_id2  = session_label2.split(" — ")[0]
    session_row2 = sessions[sessions["session_id"] == session_id2].iloc[0]
    stag_sess2   = stagiaires[stagiaires["session_id"] == session_id2] \
                   if not stagiaires.empty else pd.DataFrame()

    if st.button("🔄 Actualiser"):
        st.rerun()

    if emargements.empty or stag_sess2.empty:
        st.info("Aucun émargement enregistré pour cette session.")
    else:
        em_sess = emargements[emargements["session_id"] == session_id2].copy()

        if em_sess.empty:
            st.info("Aucun émargement pour cette session.")
        else:
            # Tableau récap par stagiaire x jour x moment
            em_sess["date_disp"] = em_sess["date"].apply(
                lambda d: pd.to_datetime(d).strftime("%d/%m") if d else "?"
            )
            em_sess["horodatage_disp"] = em_sess["horodatage"].apply(
                lambda h: h[11:16] if len(h) >= 16 else h
            )

            # Pivot : stagiaire en ligne, (date, moment) en colonne
            pivot = em_sess.pivot_table(
                index="stagiaire_id",
                columns=["date_disp", "moment"],
                values="horodatage_disp",
                aggfunc="first",
            )

            # Remplacer les IDs par les noms
            pivot.index = pivot.index.map(
                lambda sid: get(stag_sess2, "stagiaire_id", sid, "nom", sid)
            )
            pivot.columns = [f"{d} {m[:4]}" for d, m in pivot.columns]
            pivot = pivot.fillna("—")

            # Colorier : présent = vert, absent = rouge
            def color_cell(val):
                if val == "—":
                    return "background-color:#FEE2E2;color:#991B1B"
                return "background-color:#D1FAE5;color:#065F46"

            st.dataframe(
                pivot.style.applymap(color_cell),
                use_container_width=True,
            )

            # Stats globales
            st.divider()
            total_creneaux = len(em_sess)
            total_stags    = len(stag_sess2)
            st.metric("Émargements enregistrés", total_creneaux)

            # Détail par stagiaire
            with st.expander("Détail complet"):
                detail = em_sess.merge(
                    stag_sess2[["stagiaire_id", "nom"]],
                    on="stagiaire_id", how="left"
                )
                st.dataframe(
                    detail[["nom", "date", "moment", "horodatage", "signature_stagiaire"]],
                    use_container_width=True,
                )

            # Export CSV
            csv = em_sess.to_csv(index=False, encoding="utf-8-sig").encode()
            st.download_button(
                "⬇️ Exporter CSV émargements",
                data=csv,
                file_name=f"emargements_{session_id2}.csv",
                mime="text/csv",
            )
