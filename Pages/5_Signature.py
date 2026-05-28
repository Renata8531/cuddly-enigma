import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, date, timedelta
from io import BytesIO
import uuid, hashlib, hmac, secrets, json, base64, requests

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable
)

# ============================================================
# HOF - Signature électronique OTP
# pages/5_Signature.py
#
# Flux :
#   1. Formateur sélectionne document + stagiaire → envoie OTP
#   2. Stagiaire reçoit email avec code 6 chiffres + lien
#   3. Stagiaire ouvre le lien, lit le document, saisit le code
#   4. HOF vérifie OTP, capture IP/user-agent/timestamp
#   5. HOF génère certificat de preuve + fusionne avec document
#   6. PDF signé stocké dans /exports/signes/
# ============================================================

DATA_DIR    = Path("data")
EXPORT_DIR  = Path("exports")
SIGNED_DIR  = Path("exports") / "signes"
SIGN_DB     = DATA_DIR / "signatures.csv"
OTP_DB      = DATA_DIR / "otp_pending.csv"

EXPORT_DIR.mkdir(exist_ok=True)
SIGNED_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

FONT_NORMAL = "Helvetica"
FONT_BOLD   = "Helvetica-Bold"
NAVY        = (0.12, 0.23, 0.37)
GREEN       = (0.06, 0.53, 0.29)
RED_C       = (0.68, 0.05, 0.05)
DARK        = (0.20, 0.20, 0.20)
GREY        = (0.55, 0.55, 0.55)

# ── Config ───────────────────────────────────────────────────
SECRET = "hof-signature-secret-2025"
try:
    SECRET = st.secrets.get("signature_secret", SECRET)
except Exception:
    pass

OTP_VALIDITY_MINUTES = 30

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

def save_df(path, df):
    path.parent.mkdir(exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")

sessions   = load(DATA_DIR / "sessions.csv",
                  ["session_id","programme_id","formateur_id","nom",
                   "date_debut","date_fin","prix","cout_prevu"])
stagiaires = load(DATA_DIR / "stagiaires.csv",
                  ["stagiaire_id","session_id","nom","email","entreprise","lien_unique"])
programmes = load(DATA_DIR / "programmes.csv",
                  ["programme_id","referentiel_id","nom_programme","duree_heures",
                   "objectifs","prerequis","modalites"])
formateurs = load(DATA_DIR / "formateurs.csv",
                  ["formateur_id","nom","email","specialite","lien_unique"])

signatures = load(SIGN_DB, [
    "signature_id","stagiaire_id","session_id","document_type",
    "document_hash","otp_code","timestamp_envoi","timestamp_signature",
    "ip_signataire","user_agent","statut","pdf_signe_path"
])
otp_pending = load(OTP_DB, [
    "otp_id","stagiaire_id","session_id","document_type",
    "document_hash","otp_code","timestamp_envoi","expire_at","pdf_path"
])

# ── Helpers ──────────────────────────────────────────────────

def get(df, id_col, val, target_col, fallback=""):
    r = df[df[id_col] == val]
    return str(r.iloc[0][target_col]) if not r.empty else fallback

def fmt_date(s):
    try:
        return pd.to_datetime(s).strftime("%d/%m/%Y")
    except Exception:
        return str(s)

def hash_pdf(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()

def sign_token(signature_id: str) -> str:
    return hmac.new(
        SECRET.encode(), signature_id.encode(), hashlib.sha256
    ).hexdigest()[:24]

def verify_sign_token(token: str, signature_id: str) -> bool:
    return hmac.compare_digest(token, sign_token(signature_id))

def generate_otp() -> str:
    return str(secrets.randbelow(900000) + 100000)

# ── Brevo email ───────────────────────────────────────────────

def get_brevo():
    try:
        return {
            "api_key":      st.secrets["brevo"]["api_key"],
            "sender_email": st.secrets["brevo"]["sender_email"],
            "sender_name":  st.secrets["brevo"]["sender_name"],
        }
    except Exception:
        return None

def envoyer_otp_email(destinataire_email, destinataire_nom,
                       otp_code, lien_signature,
                       nom_document, nom_formation) -> dict:
    brevo = get_brevo()
    if not brevo:
        return {"ok": False, "error": "Brevo non configuré"}

    html = f"""
<!DOCTYPE html><html lang="fr">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:30px 10px;">
<table width="580" cellpadding="0" cellspacing="0" bgcolor="#ffffff"
       style="border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">

  <tr bgcolor="#1E3A5F">
    <td align="center" style="padding:24px 40px;">
      <p style="margin:0;font-size:20px;font-weight:bold;color:#fff;">Art de Pâtisser</p>
      <p style="margin:4px 0 0;font-size:12px;color:#93C5FD;">Document à signer</p>
    </td>
  </tr>

  <tr><td style="padding:28px 40px;">
    <p style="font-size:16px;color:#1E3A5F;font-weight:bold;margin:0 0 12px;">
      Bonjour {destinataire_nom},
    </p>
    <p style="font-size:14px;color:#374151;line-height:1.6;margin:0 0 20px;">
      Vous êtes invité(e) à signer le document
      <strong>{nom_document}</strong>
      pour la formation <strong>{nom_formation}</strong>.
    </p>

    <!-- Code OTP -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr>
        <td align="center" bgcolor="#F0F4F8"
            style="border-radius:8px;padding:20px;border:2px dashed #1E3A5F;">
          <p style="margin:0 0 8px;font-size:13px;color:#6B7280;">
            Votre code de signature (valable {OTP_VALIDITY_MINUTES} minutes)
          </p>
          <p style="margin:0;font-size:36px;font-weight:bold;
                    color:#1E3A5F;letter-spacing:8px;">
            {otp_code}
          </p>
        </td>
      </tr>
    </table>

    <!-- Bouton -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
      <tr>
        <td bgcolor="#1E3A5F" align="center"
            style="border-radius:6px;padding:14px 24px;">
          <a href="{lien_signature}"
             style="color:#fff;text-decoration:none;font-size:15px;font-weight:bold;">
            ✍️ Accéder au document et signer
          </a>
        </td>
      </tr>
    </table>

    <p style="font-size:12px;color:#9CA3AF;margin:0;">
      Ce lien est personnel et sécurisé. N'envoyez pas ce code à quelqu'un d'autre.<br>
      Si vous n'êtes pas concerné(e), ignorez cet email.
    </p>
  </td></tr>

  <tr bgcolor="#F3F4F6">
    <td align="center" style="padding:14px 40px;">
      <p style="margin:0;font-size:11px;color:#9CA3AF;">
        Art de Pâtisser — 3 rue Caussette 31000 Toulouse<br>
        OF n° 76311092431
      </p>
    </td>
  </tr>

</table></td></tr></table>
</body></html>
"""

    payload = {
        "sender":      {"name": brevo["sender_name"], "email": brevo["sender_email"]},
        "to":          [{"email": destinataire_email, "name": destinataire_nom}],
        "subject":     f"Code de signature — {nom_document}",
        "htmlContent": html,
    }
    try:
        r = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"accept":"application/json",
                     "content-type":"application/json",
                     "api-key": brevo["api_key"]},
            data=json.dumps(payload), timeout=15,
        )
        return {"ok": r.status_code in (200,201)} if r.status_code in (200,201) \
               else {"ok": False, "error": f"HTTP {r.status_code} — {r.text}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── Certificat de preuve ──────────────────────────────────────

def pdf_certificat_preuve(signature_row: dict, nom_stag: str,
                           nom_doc: str, nom_formation: str,
                           doc_hash: str) -> bytes:
    """
    Génère une page de certificat de signature électronique.
    Fusionnée à la fin du document original.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm,  bottomMargin=2*cm,
    )
    styles = getSampleStyleSheet()
    TH  = colors.HexColor("#1E3A5F")
    ALT = colors.HexColor("#F0F4F8")
    GRN = colors.HexColor("#065F46")

    styles.add(ParagraphStyle("Titre", fontSize=16, fontName=FONT_BOLD,
               textColor=TH, alignment=TA_CENTER, spaceAfter=4))
    styles.add(ParagraphStyle("Sous", fontSize=10, fontName=FONT_NORMAL,
               textColor=colors.HexColor("#6B7280"), alignment=TA_CENTER, spaceAfter=16))
    styles.add(ParagraphStyle("Corps", fontSize=9, fontName=FONT_NORMAL,
               textColor=colors.HexColor("#374151"), spaceAfter=4, leading=13))
    styles.add(ParagraphStyle("Hash", fontSize=7, fontName="Courier",
               textColor=colors.HexColor("#6B7280"), spaceAfter=4, leading=10))
    styles.add(ParagraphStyle("Small", fontSize=8, fontName=FONT_NORMAL,
               textColor=colors.HexColor("#9CA3AF"), alignment=TA_CENTER))

    story = []

    # En-tête
    story.append(Paragraph("Art de Pâtisser", styles["Titre"]))
    story.append(HRFlowable(width="100%", thickness=2, color=TH, spaceAfter=6))
    story.append(Paragraph("CERTIFICAT DE SIGNATURE ÉLECTRONIQUE", styles["Titre"]))
    story.append(Paragraph(
        "Ce certificat atteste de la signature électronique du document ci-joint "
        "conformément au règlement eIDAS (UE) n°910/2014 — Niveau Simple.",
        styles["Sous"]
    ))

    # Bandeau vert "SIGNÉ"
    t_signed = Table([["✅  DOCUMENT SIGNÉ ÉLECTRONIQUEMENT"]],
                     colWidths=[17*cm])
    t_signed.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#D1FAE5")),
        ("TEXTCOLOR",     (0,0),(-1,-1), GRN),
        ("FONTNAME",      (0,0),(-1,-1), FONT_BOLD),
        ("FONTSIZE",      (0,0),(-1,-1), 12),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("BOX",           (0,0),(-1,-1), 1.5, colors.HexColor("#6EE7B7")),
    ]))
    story.append(t_signed)
    story.append(Spacer(1, 0.4*cm))

    # Infos document
    story.append(Paragraph("Informations du document", styles.get("Heading2", styles["Titulo" if "Titulo" in styles.byName else "Normal"])))

    infos = [
        ["Document",         nom_doc],
        ["Formation",        nom_formation],
        ["Signataire",       nom_stag],
        ["Email signataire", signature_row.get("email","—")],
    ]
    t_info = Table(infos, colWidths=[5*cm, 12*cm])
    t_info.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(0,-1), ALT),
        ("FONTNAME",      (0,0),(0,-1), FONT_BOLD),
        ("FONTNAME",      (1,0),(1,-1), FONT_NORMAL),
        ("FONTSIZE",      (0,0),(-1,-1),9),
        ("GRID",          (0,0),(-1,-1),0.4, colors.HexColor("#D1D5DB")),
        ("TOPPADDING",    (0,0),(-1,-1),5),
        ("BOTTOMPADDING", (0,0),(-1,-1),5),
        ("LEFTPADDING",   (0,0),(-1,-1),6),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 0.3*cm))

    # Preuves techniques
    story.append(Paragraph("Preuves techniques", styles.get("Heading2", styles["Normal"])))

    preuves = [
        ["Élément de preuve",        "Valeur"],
        ["Horodatage envoi OTP",     signature_row.get("timestamp_envoi","—")],
        ["Horodatage signature",     signature_row.get("timestamp_signature","—")],
        ["Adresse IP signataire",    signature_row.get("ip_signataire","—")],
        ["Navigateur / Appareil",    signature_row.get("user_agent","—")[:80]],
        ["Code OTP vérifié",         "✅ " + signature_row.get("otp_code","—")],
        ["ID de signature",          signature_row.get("signature_id","—")],
    ]
    t_preuves = Table(preuves, colWidths=[5*cm, 12*cm])
    t_preuves.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  TH),
        ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
        ("FONTNAME",      (0,0),(-1,0),  FONT_BOLD),
        ("FONTSIZE",      (0,0),(-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, ALT]),
        ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#D1D5DB")),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("FONTNAME",      (0,1),(0,-1),  FONT_BOLD),
        ("WORDWRAP",      (1,1),(-1,-1), True),
    ]))
    story.append(t_preuves)
    story.append(Spacer(1, 0.3*cm))

    # Hash document
    story.append(Paragraph("Intégrité du document (empreinte SHA-256)", styles["Corps"]))
    story.append(Paragraph(doc_hash, styles["Hash"]))
    story.append(Spacer(1, 0.3*cm))

    # Mention légale
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=colors.HexColor("#D1D5DB"), spaceAfter=6))
    story.append(Paragraph(
        "Ce certificat constitue une preuve de signature électronique simple au sens du règlement "
        "eIDAS (UE) n°910/2014. L'identité du signataire est attestée par la vérification de son "
        "adresse email et d'un code à usage unique (OTP) envoyé sur cette adresse. "
        "Art de Pâtisser conserve l'ensemble des éléments de preuve pendant 3 ans.",
        styles["Small"]
    ))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')} UTC — "
        f"Art de Pâtisser — SIRET 889519633 00016 — OF n° 76311092431",
        styles["Small"]
    ))

    doc.build(story)
    return buf.getvalue()


def fusionner_avec_certificat(doc_pdf_bytes: bytes, certificat_bytes: bytes) -> bytes:
    """Ajoute le certificat de preuve à la fin du document."""
    writer = PdfWriter()
    for pdf_bytes in [doc_pdf_bytes, certificat_bytes]:
        reader = PdfReader(BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


# ════════════════════════════════════════════════════════════
# INTERFACE STREAMLIT
# ════════════════════════════════════════════════════════════

params    = st.query_params
MODE_SIGN = all(k in params for k in ["sig_id", "token"])

# ════════════════════════════════════════════════════════════
# MODE SIGNATURE — page ouverte par le stagiaire
# ════════════════════════════════════════════════════════════

if MODE_SIGN:
    sig_id = params["sig_id"]
    token  = params["token"]

    if not verify_sign_token(token, sig_id):
        st.error("❌ Lien invalide ou expiré.")
        st.stop()

    # Charger la demande OTP
    otp_pending = load(OTP_DB, [
        "otp_id","stagiaire_id","session_id","document_type",
        "document_hash","otp_code","timestamp_envoi","expire_at","pdf_path"
    ])

    otp_rows = otp_pending[otp_pending["otp_id"] == sig_id]
    if otp_rows.empty:
        st.error("❌ Demande de signature introuvable.")
        st.stop()

    otp_row = otp_rows.iloc[0]

    # Vérifier expiration
    try:
        expire = datetime.fromisoformat(otp_row["expire_at"])
        if datetime.now() > expire:
            st.error("❌ Ce lien a expiré. Demandez un nouvel envoi.")
            st.stop()
    except Exception:
        pass

    # Vérifier si déjà signé
    signatures = load(SIGN_DB, [
        "signature_id","stagiaire_id","session_id","document_type",
        "document_hash","otp_code","timestamp_envoi","timestamp_signature",
        "ip_signataire","user_agent","statut","pdf_signe_path"
    ])
    deja = signatures[
        (signatures["stagiaire_id"]   == otp_row["stagiaire_id"]) &
        (signatures["session_id"]     == otp_row["session_id"])   &
        (signatures["document_type"]  == otp_row["document_type"]) &
        (signatures["statut"]         == "signe")
    ]
    if not deja.empty:
        st.success("✅ Ce document a déjà été signé. Merci !")
        st.stop()

    # Récupérer infos
    stag_row = stagiaires[stagiaires["stagiaire_id"] == otp_row["stagiaire_id"]]
    sess_row = sessions[sessions["session_id"]       == otp_row["session_id"]]
    if stag_row.empty or sess_row.empty:
        st.error("❌ Données introuvables.")
        st.stop()

    stag = stag_row.iloc[0]
    sess = sess_row.iloc[0]

    DOC_LABELS = {
        "contrat":     "Contrat de formation",
        "certificat":  "Certificat de réalisation",
        "attestation": "Attestation de fin de formation",
        "emargement":  "Feuille d'émargement",
    }
    nom_doc = DOC_LABELS.get(otp_row["document_type"], otp_row["document_type"])

    # ── UI signature ─────────────────────────────────────────
    st.title("✍️ Signature électronique")
    st.markdown(f"**{stag['nom']}** — {sess['nom']}")

    col1, col2 = st.columns(2)
    col1.markdown(f"📄 **Document :** {nom_doc}")
    col2.markdown(f"📅 **Formation :** {fmt_date(sess['date_debut'])} → {fmt_date(sess['date_fin'])}")

    # Temps restant
    try:
        expire  = datetime.fromisoformat(otp_row["expire_at"])
        restant = int((expire - datetime.now()).total_seconds() / 60)
        if restant > 0:
            st.info(f"⏱️ Ce lien expire dans **{restant} minute(s)**.")
    except Exception:
        pass

    st.divider()

    # Afficher le document PDF si disponible
    pdf_path = Path(otp_row["pdf_path"]) if otp_row["pdf_path"] else None
    if pdf_path and pdf_path.exists():
        with st.expander("📄 Lire le document avant de signer", expanded=True):
            with open(pdf_path, "rb") as f:
                st.download_button(
                    "⬇️ Télécharger le document",
                    data=f.read(),
                    file_name=pdf_path.name,
                    mime="application/pdf",
                )
            st.caption("Lisez attentivement le document avant de signer.")

    st.divider()
    st.markdown("### Saisir votre code de signature")
    st.caption("Le code a 6 chiffres vous a été envoyé par email.")

    lu = st.checkbox("✅ J'ai lu et j'accepte le contenu du document", key="lu_doc")
    otp_input = st.text_input(
        "Code reçu par email",
        max_chars=6,
        placeholder="123456",
    )

    if st.button("✍️ Signer le document", type="primary",
                 use_container_width=True, disabled=not lu):

        if not otp_input.strip():
            st.error("Veuillez saisir le code reçu par email.")
        elif otp_input.strip() != otp_row["otp_code"]:
            st.error("❌ Code incorrect. Vérifiez l'email reçu.")
        else:
            # ── Signature validée ─────────────────────────────
            now      = datetime.now()
            sig_uuid = f"SIG{uuid.uuid4().hex[:12].upper()}"

            # Récupérer IP et user-agent via headers Streamlit
            # (approximation — Streamlit ne donne pas directement l'IP)
            try:
                from streamlit.web.server.websocket_headers import _get_websocket_headers
                headers    = _get_websocket_headers()
                ip_addr    = headers.get("X-Forwarded-For", headers.get("X-Real-IP", "Inconnue"))
                user_agent = headers.get("User-Agent", "Inconnu")
            except Exception:
                ip_addr    = "Capturée côté serveur"
                user_agent = st.context.headers.get("User-Agent","Inconnu") \
                             if hasattr(st, "context") else "Inconnu"

            # Charger le PDF original
            pdf_bytes = pdf_path.read_bytes() if pdf_path and pdf_path.exists() else b""
            doc_hash  = hash_pdf(pdf_bytes) if pdf_bytes else otp_row["document_hash"]

            # Générer certificat de preuve
            sig_data = {
                "signature_id":       sig_uuid,
                "email":              stag["email"],
                "timestamp_envoi":    otp_row["timestamp_envoi"],
                "timestamp_signature":now.isoformat(timespec="seconds"),
                "ip_signataire":      ip_addr,
                "user_agent":         user_agent,
                "otp_code":           otp_row["otp_code"],
            }

            prog_rows = programmes[programmes["programme_id"] == sess["programme_id"]]
            nom_prog  = prog_rows.iloc[0]["nom_programme"] \
                        if not prog_rows.empty else sess["nom"]

            cert_bytes  = pdf_certificat_preuve(sig_data, stag["nom"],
                                                nom_doc, nom_prog, doc_hash)
            signed_pdf  = fusionner_avec_certificat(pdf_bytes, cert_bytes) \
                          if pdf_bytes else cert_bytes

            # Sauvegarder PDF signé
            signed_name = f"{otp_row['document_type']}_{stag['nom'].replace(' ','_')}_SIGNE.pdf"
            signed_path = SIGNED_DIR / signed_name
            signed_path.write_bytes(signed_pdf)

            # Enregistrer la signature
            new_sig = {
                "signature_id":        sig_uuid,
                "stagiaire_id":        stag["stagiaire_id"],
                "session_id":          sess["session_id"],
                "document_type":       otp_row["document_type"],
                "document_hash":       doc_hash,
                "otp_code":            otp_row["otp_code"],
                "timestamp_envoi":     otp_row["timestamp_envoi"],
                "timestamp_signature": now.isoformat(timespec="seconds"),
                "ip_signataire":       ip_addr,
                "user_agent":          user_agent,
                "statut":              "signe",
                "pdf_signe_path":      str(signed_path),
            }
            signatures = load(SIGN_DB, list(new_sig.keys()))
            signatures = pd.concat(
                [signatures, pd.DataFrame([new_sig])], ignore_index=True
            )
            save_df(SIGN_DB, signatures)

            # Supprimer OTP utilisé
            otp_pending = otp_pending[otp_pending["otp_id"] != sig_id]
            save_df(OTP_DB, otp_pending)

            st.success("✅ Document signé avec succès !")
            st.markdown(f"**ID de signature :** `{sig_uuid}`")
            st.markdown(f"**Horodatage :** {now.strftime('%d/%m/%Y à %H:%M:%S')}")
            st.download_button(
                "⬇️ Télécharger le document signé",
                data=signed_pdf,
                file_name=signed_name,
                mime="application/pdf",
            )
            st.balloons()

    st.stop()


# ════════════════════════════════════════════════════════════
# MODE FORMATEUR — envoi des OTP
# ════════════════════════════════════════════════════════════

st.title("✍️ Signature électronique")

brevo = get_brevo()

with st.sidebar:
    st.header("⚙️ Configuration")
    if brevo:
        st.success("✅ Brevo configuré")
    else:
        st.warning("Brevo non configuré")
        tmp_key   = st.text_input("Clé API Brevo", type="password")
        tmp_email = st.text_input("Email expéditeur")
        if tmp_key and tmp_email:
            import os
            os.environ["BREVO_TMP_KEY"]   = tmp_key
            os.environ["BREVO_TMP_EMAIL"] = tmp_email

    base_url = st.text_input(
        "URL de l'app",
        value="http://localhost:8501/Signature",
        help="URL accessible par les stagiaires",
    )

tabs = st.tabs(["📤 Envoyer pour signature", "📊 Suivi signatures", "📁 Documents signés"])

# ── Onglet 1 : Envoyer ────────────────────────────────────────
with tabs[0]:
    st.subheader("Envoyer un document à signer")

    if sessions.empty:
        st.warning("Aucune session disponible.")
        st.stop()

    session_label = st.selectbox(
        "Session",
        sessions["session_id"] + " — " + sessions["nom"],
        key="sig_session",
    )
    session_id  = session_label.split(" — ")[0]
    session_row = sessions[sessions["session_id"] == session_id].iloc[0]
    stag_sess   = stagiaires[stagiaires["session_id"] == session_id] \
                  if not stagiaires.empty else pd.DataFrame()

    if stag_sess.empty:
        st.warning("Aucun stagiaire dans cette session.")
        st.stop()

    col1, col2 = st.columns(2)

    with col1:
        doc_type = st.selectbox(
            "Document à faire signer",
            options=["contrat","certificat","attestation","emargement"],
            format_func=lambda x: {
                "contrat":     "📋 Contrat de formation",
                "certificat":  "🎓 Certificat de réalisation",
                "attestation": "📄 Attestation de fin de formation",
                "emargement":  "✍️ Feuille d'émargement",
            }[x],
        )

    with col2:
        mode = st.radio(
            "Envoyer à",
            ["Tous les stagiaires", "Un stagiaire"],
            horizontal=True,
        )

    cibles = stag_sess.copy()
    if mode == "Un stagiaire":
        sel = st.selectbox(
            "Stagiaire",
            stag_sess["stagiaire_id"] + " — " + stag_sess["nom"],
            key="sig_stag_sel",
        )
        sel_id = sel.split(" — ")[0]
        cibles = stag_sess[stag_sess["stagiaire_id"] == sel_id]

    # Vérifier emails manquants
    sans_email = cibles[cibles["email"] == ""]
    if not sans_email.empty:
        st.warning(f"⚠️ Sans email : {', '.join(sans_email['nom'].tolist())}")
    cibles = cibles[cibles["email"] != ""]

    # Charger le PDF à signer depuis /exports
    pdf_disponibles = list(EXPORT_DIR.glob(f"{doc_type}_*.pdf")) + \
                      list(EXPORT_DIR.glob(f"*{doc_type}*.pdf"))
    pdf_disponibles = [f for f in pdf_disponibles if "SIGNE" not in f.name]

    pdf_source = None
    if pdf_disponibles:
        st.caption(f"📂 {len(pdf_disponibles)} PDF trouvé(s) dans /exports")
        pdf_choix = st.selectbox(
            "PDF à utiliser (ou uploader ci-dessous)",
            ["— Uploader un nouveau —"] + [f.name for f in pdf_disponibles],
        )
        if pdf_choix != "— Uploader un nouveau —":
            pdf_source = EXPORT_DIR / pdf_choix

    uploaded = st.file_uploader("Uploader le PDF à signer", type="pdf",
                                 key=f"pdf_up_{doc_type}")
    if uploaded:
        tmp_path = EXPORT_DIR / uploaded.name
        tmp_path.write_bytes(uploaded.read())
        pdf_source = tmp_path

    st.divider()
    st.caption(f"**{len(cibles)} envoi(s) prévu(s)**")

    if st.button("📧 Envoyer les codes de signature", type="primary",
                 disabled=(brevo is None and not st.sidebar)):

        if not brevo:
            st.error("Configure Brevo dans la sidebar.")
            st.stop()

        otp_pending = load(OTP_DB, [
            "otp_id","stagiaire_id","session_id","document_type",
            "document_hash","otp_code","timestamp_envoi","expire_at","pdf_path"
        ])

        prog_rows = programmes[programmes["programme_id"] == session_row["programme_id"]]
        nom_prog  = prog_rows.iloc[0]["nom_programme"] \
                    if not prog_rows.empty else session_row["nom"]

        now      = datetime.now()
        expire   = (now + timedelta(minutes=OTP_VALIDITY_MINUTES)).isoformat(timespec="seconds")
        doc_hash = hash_pdf(pdf_source.read_bytes()) if pdf_source else ""

        progress = st.progress(0, "Envoi en cours...")
        results  = {"ok": 0, "erreurs": []}

        for i, (_, stag) in enumerate(cibles.iterrows()):
            otp_code = generate_otp()
            otp_id   = f"OTP{uuid.uuid4().hex[:12].upper()}"
            token    = sign_token(otp_id)
            lien     = f"{base_url}?sig_id={otp_id}&token={token}"

            # Enregistrer OTP
            new_otp = {
                "otp_id":          otp_id,
                "stagiaire_id":    stag["stagiaire_id"],
                "session_id":      session_id,
                "document_type":   doc_type,
                "document_hash":   doc_hash,
                "otp_code":        otp_code,
                "timestamp_envoi": now.isoformat(timespec="seconds"),
                "expire_at":       expire,
                "pdf_path":        str(pdf_source) if pdf_source else "",
            }
            otp_pending = pd.concat(
                [otp_pending, pd.DataFrame([new_otp])], ignore_index=True
            )

            # Envoyer email
            result = envoyer_otp_email(
                destinataire_email = stag["email"],
                destinataire_nom   = stag["nom"],
                otp_code           = otp_code,
                lien_signature     = lien,
                nom_document       = {
                    "contrat":     "Contrat de formation",
                    "certificat":  "Certificat de réalisation",
                    "attestation": "Attestation de fin de formation",
                    "emargement":  "Feuille d'émargement",
                }[doc_type],
                nom_formation = nom_prog,
            )

            if result["ok"]:
                results["ok"] += 1
            else:
                results["erreurs"].append(f"{stag['nom']}: {result['error']}")

            progress.progress((i+1)/len(cibles), f"Envoyé à {stag['nom']}...")

        save_df(OTP_DB, otp_pending)
        progress.empty()

        if results["ok"] > 0:
            st.success(f"✅ {results['ok']} code(s) envoyé(s)")
        for err in results["erreurs"]:
            st.error(f"❌ {err}")


# ── Onglet 2 : Suivi ──────────────────────────────────────────
with tabs[1]:
    st.subheader("Suivi des signatures")

    if st.button("🔄 Actualiser", key="refresh_sig"):
        st.rerun()

    signatures = load(SIGN_DB, [
        "signature_id","stagiaire_id","session_id","document_type",
        "document_hash","otp_code","timestamp_envoi","timestamp_signature",
        "ip_signataire","user_agent","statut","pdf_signe_path"
    ])

    session_label2 = st.selectbox(
        "Session",
        sessions["session_id"] + " — " + sessions["nom"],
        key="suivi_sig_sess",
    )
    session_id2 = session_label2.split(" — ")[0]
    stag_sess2  = stagiaires[stagiaires["session_id"] == session_id2] \
                  if not stagiaires.empty else pd.DataFrame()

    sig_sess = signatures[signatures["session_id"] == session_id2] \
               if not signatures.empty else pd.DataFrame()

    if sig_sess.empty:
        st.info("Aucune signature enregistrée pour cette session.")
    else:
        # Tableau récap
        rows = []
        for _, stag in stag_sess2.iterrows():
            for doc_type, label in [
                ("contrat",     "Contrat"),
                ("certificat",  "Certificat"),
                ("attestation", "Attestation"),
                ("emargement",  "Émargement"),
            ]:
                sig = sig_sess[
                    (sig_sess["stagiaire_id"]  == stag["stagiaire_id"]) &
                    (sig_sess["document_type"] == doc_type) &
                    (sig_sess["statut"]        == "signe")
                ]
                if not sig.empty:
                    ts = sig.iloc[0]["timestamp_signature"][:16].replace("T"," ")
                    rows.append({
                        "Stagiaire":  stag["nom"],
                        "Document":   label,
                        "Statut":     "✅ Signé",
                        "Horodatage": ts,
                        "IP":         sig.iloc[0]["ip_signataire"],
                    })
                else:
                    rows.append({
                        "Stagiaire":  stag["nom"],
                        "Document":   label,
                        "Statut":     "⏳ En attente",
                        "Horodatage": "—",
                        "IP":         "—",
                    })

        df_suivi = pd.DataFrame(rows)

        def color_statut(val):
            if "Signé" in str(val):
                return "background-color:#D1FAE5;color:#065F46"
            return "background-color:#FEE2E2;color:#991B1B"

        st.dataframe(
            df_suivi.style.applymap(color_statut, subset=["Statut"]),
            use_container_width=True, hide_index=True,
        )

        total   = len(df_suivi)
        signes  = len(df_suivi[df_suivi["Statut"].str.contains("Signé")])
        st.metric("Taux de signature", f"{signes}/{total}",
                  delta=f"{(signes/total*100):.0f}%" if total > 0 else "0%")


# ── Onglet 3 : Documents signés ───────────────────────────────
with tabs[2]:
    st.subheader("Documents signés")

    signed_files = sorted(SIGNED_DIR.glob("*.pdf"))
    if not signed_files:
        st.info("Aucun document signé pour l'instant.")
    else:
        for f in signed_files:
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.text(f.name)
            c2.write(f"{f.stat().st_size // 1024} Ko")
            with open(f, "rb") as fh:
                c3.download_button(
                    "⬇️", data=fh.read(),
                    file_name=f.name,
                    mime="application/pdf",
                    key=f"dl_signed_{f.name}",
                )
