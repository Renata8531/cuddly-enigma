import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, date
from io import BytesIO
import uuid
import hmac
import hashlib
import requests
import json

# ============================================================
# HOF - Envoi des liens stagiaires par email (Brevo)
# pages/4_Envoi_liens.py
#
# Envoie dans un seul email :
#   - Lien QR émargement (PDF en pièce jointe)
#   - Lien satisfaction (formulaire en ligne)
#   - Lien auto-évaluation (formulaire en ligne)
# ============================================================

DATA_DIR   = Path("data")
EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)

# ── Config Brevo ─────────────────────────────────────────────
# Clé API à mettre dans .streamlit/secrets.toml :
#   [brevo]
#   api_key = "xkeysib-..."
#   sender_email = "client@artdepatisser.com"
#   sender_name  = "Art de Pâtisser"

def get_brevo_config():
    try:
        return {
            "api_key":      st.secrets["brevo"]["api_key"],
            "sender_email": st.secrets["brevo"]["sender_email"],
            "sender_name":  st.secrets["brevo"]["sender_name"],
        }
    except Exception:
        return None

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
satisfaction   = load(DATA_DIR / "satisfaction_stagiaire.csv",
                      ["satisfaction_id","stagiaire_id","session_id","date",
                       "rubrique","note","commentaire"])
auto_evaluation = load(DATA_DIR / "auto_evaluation.csv",
                       ["auto_eval_id","stagiaire_id","session_id","competence_id",
                        "moment","note","commentaire"])

# ── Helpers ──────────────────────────────────────────────────

def fmt_date(s):
    try:
        return pd.to_datetime(s).strftime("%d/%m/%Y")
    except Exception:
        return str(s)

def get(df, id_col, val, target_col, fallback=""):
    r = df[df[id_col] == val]
    return str(r.iloc[0][target_col]) if not r.empty else fallback

SECRET = "hof-artdepatisser-2025"
try:
    SECRET = st.secrets.get("emargement_secret", SECRET)
except Exception:
    pass

def make_token(stagiaire_id: str, session_id: str, doc_type: str) -> str:
    msg = f"{stagiaire_id}|{session_id}|{doc_type}"
    return hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()[:20]

def verify_token(token: str, stagiaire_id: str, session_id: str, doc_type: str) -> bool:
    return hmac.compare_digest(token, make_token(stagiaire_id, session_id, doc_type))

def make_lien(base_url: str, stagiaire_id: str, session_id: str, doc_type: str) -> str:
    token = make_token(stagiaire_id, session_id, doc_type)
    return f"{base_url}?stag={stagiaire_id}&sess={session_id}&type={doc_type}&token={token}"

# ── Envoi email via Brevo API ─────────────────────────────────

def envoyer_email_brevo(api_key: str, sender_email: str, sender_name: str,
                         destinataire_email: str, destinataire_nom: str,
                         sujet: str, html_body: str,
                         pdf_bytes: bytes = None, pdf_nom: str = None) -> dict:
    """
    Envoie un email via l'API Brevo (ex-Sendinblue).
    Retourne {"ok": True} ou {"ok": False, "error": "..."}
    """
    import base64

    payload = {
        "sender":  {"name": sender_name, "email": sender_email},
        "to":      [{"email": destinataire_email, "name": destinataire_nom}],
        "subject": sujet,
        "htmlContent": html_body,
    }

    if pdf_bytes and pdf_nom:
        payload["attachment"] = [{
            "name":    pdf_nom,
            "content": base64.b64encode(pdf_bytes).decode(),
        }]

    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept":       "application/json",
                "content-type": "application/json",
                "api-key":      api_key,
            },
            data=json.dumps(payload),
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return {"ok": True}
        else:
            return {"ok": False, "error": f"HTTP {resp.status_code} — {resp.text}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Template email HTML ───────────────────────────────────────

def build_email_html(nom_stag: str, nom_formation: str,
                     date_debut: str, date_fin: str,
                     lien_satisfaction: str, lien_auto_eval: str) -> str:
    return f"""
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" bgcolor="#f4f4f4">
    <tr><td align="center" style="padding:30px 10px;">
      <table width="600" cellpadding="0" cellspacing="0" bgcolor="#ffffff"
             style="border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

        <!-- En-tête -->
        <tr bgcolor="#1E3A5F">
          <td align="center" style="padding:28px 40px;">
            <p style="margin:0;font-size:22px;font-weight:bold;color:#ffffff;letter-spacing:1px;">
              Art de Pâtisser
            </p>
            <p style="margin:6px 0 0;font-size:13px;color:#93C5FD;">
              Organisme de formation professionnelle
            </p>
          </td>
        </tr>

        <!-- Corps -->
        <tr>
          <td style="padding:32px 40px;">
            <p style="margin:0 0 16px;font-size:16px;color:#1E3A5F;font-weight:bold;">
              Bonjour {nom_stag},
            </p>
            <p style="margin:0 0 20px;font-size:14px;color:#374151;line-height:1.6;">
              Merci de votre participation à la formation
              <strong style="color:#1E3A5F;">{nom_formation}</strong>
              du {date_debut} au {date_fin}.
            </p>
            <p style="margin:0 0 24px;font-size:14px;color:#374151;line-height:1.6;">
              Merci de compléter les deux formulaires ci-dessous — cela nous prend
              moins de 5 minutes et nous aide à améliorer nos formations.
            </p>

            <!-- Bouton satisfaction -->
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;">
              <tr>
                <td bgcolor="#1E3A5F" align="center"
                    style="border-radius:6px;padding:14px 24px;">
                  <a href="{lien_satisfaction}"
                     style="color:#ffffff;text-decoration:none;font-size:15px;
                            font-weight:bold;display:block;">
                    ✅ Évaluation satisfaction
                  </a>
                </td>
              </tr>
            </table>

            <!-- Bouton auto-évaluation -->
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
              <tr>
                <td bgcolor="#AE1C1C" align="center"
                    style="border-radius:6px;padding:14px 24px;">
                  <a href="{lien_auto_eval}"
                     style="color:#ffffff;text-decoration:none;font-size:15px;
                            font-weight:bold;display:block;">
                    🔍 Auto-évaluation des compétences
                  </a>
                </td>
              </tr>
            </table>

            <p style="margin:0 0 8px;font-size:13px;color:#6B7280;">
              La feuille d'émargement QR code est jointe à cet email en PDF.
            </p>
            <p style="margin:0;font-size:13px;color:#6B7280;">
              Pour toute question : 
              <a href="mailto:client@artdepatisser.com" style="color:#1E3A5F;">
                client@artdepatisser.com
              </a>
            </p>
          </td>
        </tr>

        <!-- Pied -->
        <tr bgcolor="#F3F4F6">
          <td align="center" style="padding:16px 40px;">
            <p style="margin:0;font-size:11px;color:#9CA3AF;">
              Art de Pâtisser — 3 rue Caussette 31000 Toulouse<br>
              Tél. 05 62 75 57 26 — SIRET 889519633 00016<br>
              Organisme de formation enregistré sous le n° 76311092431
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""


# ════════════════════════════════════════════════════════════
# PAGES STAGIAIRES — satisfaction & auto-évaluation en ligne
# Accessibles via lien unique sécurisé
# ════════════════════════════════════════════════════════════

params   = st.query_params
MODE_STAG = all(k in params for k in ["stag", "sess", "type", "token"])

if MODE_STAG:
    stag_id  = params["stag"]
    sess_id  = params["sess"]
    doc_type = params["type"]
    token    = params["token"]

    if not verify_token(token, stag_id, sess_id, doc_type):
        st.error("❌ Lien invalide ou expiré.")
        st.stop()

    stag_rows = stagiaires[stagiaires["stagiaire_id"] == stag_id]
    sess_rows = sessions[sessions["session_id"] == sess_id]

    if stag_rows.empty or sess_rows.empty:
        st.error("❌ Stagiaire ou session introuvable.")
        st.stop()

    stag_row = stag_rows.iloc[0]
    sess_row = sess_rows.iloc[0]

    # ── Page Satisfaction ─────────────────────────────────────
    if doc_type == "satisfaction":
        st.title("✅ Évaluation de satisfaction")
        st.markdown(f"**{stag_row['nom']}** — {sess_row['nom']}")
        st.markdown(f"*{fmt_date(sess_row['date_debut'])} → {fmt_date(sess_row['date_fin'])}*")

        # Vérifier si déjà rempli
        deja = satisfaction[
            (satisfaction["stagiaire_id"] == stag_id) &
            (satisfaction["session_id"]   == sess_id)
        ] if not satisfaction.empty else pd.DataFrame()

        if not deja.empty:
            st.success("✅ Vous avez déjà complété ce questionnaire. Merci !")
            st.stop()

        st.divider()
        st.caption("*Mettre une note de 1 (faible) à 4 (très bien)*")

        RUBRIQUES = [
            ("accueil",      "Accueil : Qualité de l'accueil à la formation"),
            ("objectifs",    "Objectifs : La formation a répondu à mes attentes"),
            ("rythme",       "Rythme de la formation, la progression me convenait"),
            ("animation_1",  "Animation : L'animateur est clair"),
            ("animation_2",  "Animation : L'animateur est à l'écoute"),
            ("difficultes",  "Difficultés techniques : Les réponses du formateur ont été claires"),
            ("themes",       "Thèmes abordés : décortiqués et mis en œuvre simplement"),
            ("equipements",  "Équipements et propreté — Matériels et ingrédients de bonne qualité"),
            ("recettes",     "Les recettes remises vous sont-elles utiles et faciles à utiliser ?"),
            ("evaluations",  "Comment évaluez-vous vos productions ?"),
        ]

        notes = {}
        for key, label in RUBRIQUES:
            notes[key] = st.select_slider(
                label,
                options=[1, 2, 3, 4],
                value=3,
                format_func=lambda x: {1: "Faible", 2: "Moyen", 3: "Bien", 4: "Très bien"}[x],
                key=f"sat_{key}",
            )

        st.divider()
        utiliser = st.radio(
            "Je vais utiliser les techniques / recettes approfondies ?",
            ["Oui", "Probablement", "Pas sûr(e)", "Non"],
            horizontal=True,
        )
        horizon = st.text_input("À quel horizon pensez-vous les mettre en place ?")
        difficultes_txt = st.text_area(
            "Citez les 3 techniques ou recettes où vous avez rencontré le plus de difficultés"
        )
        remarques = st.text_area("Remarques libres")

        if st.button("✅ Envoyer mon évaluation", type="primary", use_container_width=True):
            rows = []
            for key, label in RUBRIQUES:
                rows.append({
                    "satisfaction_id": f"SAT{uuid.uuid4().hex[:8].upper()}",
                    "stagiaire_id":    stag_id,
                    "session_id":      sess_id,
                    "date":            date.today().isoformat(),
                    "rubrique":        key,
                    "note":            str(notes[key]),
                    "commentaire":     "",
                })
            # Champs libres
            for rubrique, val in [
                ("utiliser_techniques", utiliser),
                ("horizon",             horizon),
                ("difficultes",         difficultes_txt),
                ("remarques",           remarques),
            ]:
                rows.append({
                    "satisfaction_id": f"SAT{uuid.uuid4().hex[:8].upper()}",
                    "stagiaire_id":    stag_id,
                    "session_id":      sess_id,
                    "date":            date.today().isoformat(),
                    "rubrique":        rubrique,
                    "note":            "",
                    "commentaire":     val,
                })

            sat_df = load(DATA_DIR / "satisfaction_stagiaire.csv",
                          ["satisfaction_id","stagiaire_id","session_id","date",
                           "rubrique","note","commentaire"])
            sat_df = pd.concat([sat_df, pd.DataFrame(rows)], ignore_index=True)
            save(DATA_DIR / "satisfaction_stagiaire.csv", sat_df)
            st.success("🎉 Merci pour votre retour ! Vos réponses ont bien été enregistrées.")
            st.balloons()

    # ── Page Auto-évaluation ──────────────────────────────────
    elif doc_type == "auto_eval":
        st.title("🔍 Auto-évaluation des compétences")
        st.markdown(f"**{stag_row['nom']}** — {sess_row['nom']}")
        st.markdown(f"*{fmt_date(sess_row['date_debut'])} → {fmt_date(sess_row['date_fin'])}*")

        # Compétences de la session
        programme_id = sess_row["programme_id"]
        prog_row = programmes[programmes["programme_id"] == programme_id].iloc[0] \
                   if not programmes.empty and programme_id else None

        from pathlib import Path as _P
        competences = load(DATA_DIR / "competences.csv",
                           ["competence_id","referentiel_id","epreuve","bloc","section",
                            "code_competence","competence","famille","niveau","actif"])
        comps = competences[
            competences["referentiel_id"] == (prog_row["referentiel_id"] if prog_row else "")
        ] if not competences.empty and prog_row is not None else pd.DataFrame()

        deja_ae = auto_evaluation[
            (auto_evaluation["stagiaire_id"] == stag_id) &
            (auto_evaluation["session_id"]   == sess_id)
        ] if not auto_evaluation.empty else pd.DataFrame()

        if not deja_ae.empty:
            st.success("✅ Vous avez déjà complété cette auto-évaluation. Merci !")
            st.stop()

        if comps.empty:
            st.warning("Aucune compétence définie pour cette formation.")
            st.stop()

        st.divider()
        st.caption("Notez-vous de 1 (très faible) à 10 (excellent)")

        moment = st.radio(
            "Quand remplissez-vous cette évaluation ?",
            ["En début de formation", "En fin de formation"],
            horizontal=True,
        )
        moment_key = "avant" if "début" in moment else "apres"

        notes_ae = {}
        for _, comp in comps.iterrows():
            notes_ae[comp["competence_id"]] = st.slider(
                comp["competence"],
                min_value=1, max_value=10, value=5,
                key=f"ae_{comp['competence_id']}",
            )

        commentaire_global = st.text_area("Commentaires / observations")

        if st.button("✅ Envoyer mon auto-évaluation", type="primary", use_container_width=True):
            rows = []
            for comp_id, note in notes_ae.items():
                rows.append({
                    "auto_eval_id":  f"AE{uuid.uuid4().hex[:8].upper()}",
                    "stagiaire_id":  stag_id,
                    "session_id":    sess_id,
                    "competence_id": comp_id,
                    "moment":        moment_key,
                    "note":          str(note),
                    "commentaire":   commentaire_global,
                })
            ae_df = load(DATA_DIR / "auto_evaluation.csv",
                         ["auto_eval_id","stagiaire_id","session_id","competence_id",
                          "moment","note","commentaire"])
            ae_df = pd.concat([ae_df, pd.DataFrame(rows)], ignore_index=True)
            save(DATA_DIR / "auto_evaluation.csv", ae_df)
            st.success("🎉 Auto-évaluation enregistrée. Merci !")
            st.balloons()

    st.stop()


# ════════════════════════════════════════════════════════════
# MODE FORMATEUR — envoi des emails
# ════════════════════════════════════════════════════════════

st.title("📧 Envoi des liens aux stagiaires")

# ── Config Brevo ─────────────────────────────────────────────
brevo_cfg = get_brevo_config()

with st.sidebar:
    st.header("⚙️ Configuration Brevo")

    if brevo_cfg:
        st.success("✅ Clé API configurée")
        st.caption(f"Expéditeur : {brevo_cfg['sender_email']}")
    else:
        st.warning("Clé API manquante")
        st.markdown("""
**Pour configurer :**

1. Crée un compte sur [brevo.com](https://brevo.com)
2. Menu → SMTP & API → Clés API → Créer une clé
3. Crée le fichier `.streamlit/secrets.toml` :

```toml
[brevo]
api_key      = "xkeysib-..."
sender_email = "client@artdepatisser.com"
sender_name  = "Art de Pâtisser"
```
        """)
        # Saisie manuelle en attendant
        st.divider()
        st.caption("Ou saisis temporairement :")
        tmp_key   = st.text_input("Clé API Brevo", type="password")
        tmp_email = st.text_input("Email expéditeur")
        tmp_name  = st.text_input("Nom expéditeur", value="Art de Pâtisser")
        if tmp_key and tmp_email:
            brevo_cfg = {
                "api_key":      tmp_key,
                "sender_email": tmp_email,
                "sender_name":  tmp_name,
            }

    st.divider()
    base_url = st.text_input(
        "URL de l'app",
        value="http://localhost:8501/Envoi_liens",
        help="URL Streamlit accessible par les stagiaires",
    )
    emargement_url = st.text_input(
        "URL page émargement",
        value="http://localhost:8501/Emargement",
    )

# ── Sélection session ─────────────────────────────────────────
if sessions.empty:
    st.warning("Aucune session disponible.")
    st.stop()

session_label = st.selectbox(
    "Session",
    sessions["session_id"] + " — " + sessions["nom"],
)
session_id  = session_label.split(" — ")[0]
session_row = sessions[sessions["session_id"] == session_id].iloc[0]
programme_id = session_row["programme_id"]
prog_row = programmes[programmes["programme_id"] == programme_id].iloc[0] \
           if not programmes.empty and programme_id else None

stag_session = stagiaires[stagiaires["session_id"] == session_id] \
               if not stagiaires.empty else pd.DataFrame()

st.info(
    f"**{session_row['nom']}** | "
    f"{fmt_date(session_row['date_debut'])} → {fmt_date(session_row['date_fin'])} | "
    f"**{len(stag_session)} stagiaire(s)**"
)

if stag_session.empty:
    st.warning("Aucun stagiaire dans cette session.")
    st.stop()

# ── Vérification emails manquants ─────────────────────────────
sans_email = stag_session[stag_session["email"] == ""]
if not sans_email.empty:
    st.warning(
        f"⚠️ {len(sans_email)} stagiaire(s) sans email : "
        + ", ".join(sans_email["nom"].tolist())
        + " — Va dans Stagiaires pour compléter."
    )

avec_email = stag_session[stag_session["email"] != ""]

# ── Prévisualisation email ─────────────────────────────────────
st.divider()
st.subheader("📋 Prévisualisation de l'email")

if not avec_email.empty:
    ex_stag = avec_email.iloc[0]
    lien_sat = make_lien(base_url, ex_stag["stagiaire_id"], session_id, "satisfaction")
    lien_ae  = make_lien(base_url, ex_stag["stagiaire_id"], session_id, "auto_eval")
    html_ex  = build_email_html(
        nom_stag       = ex_stag["nom"],
        nom_formation  = session_row["nom"],
        date_debut     = fmt_date(session_row["date_debut"]),
        date_fin       = fmt_date(session_row["date_fin"]),
        lien_satisfaction = lien_sat,
        lien_auto_eval    = lien_ae,
    )
    with st.expander("Voir l'email HTML (exemple pour le 1er stagiaire)", expanded=False):
        st.components.v1.html(html_ex, height=520, scrolling=True)

    with st.expander("Voir les liens générés"):
        st.code(f"Satisfaction   : {lien_sat}")
        st.code(f"Auto-évaluation: {lien_ae}")

# ── Envoi ─────────────────────────────────────────────────────
st.divider()
st.subheader("📤 Envoi")

# Choix : tous ou un seul
mode_envoi = st.radio(
    "Envoyer à",
    ["Tous les stagiaires avec email", "Un stagiaire en particulier"],
    horizontal=True,
)

cibles = avec_email.copy()
if mode_envoi == "Un stagiaire en particulier":
    sel = st.selectbox(
        "Stagiaire",
        avec_email["stagiaire_id"] + " — " + avec_email["nom"],
    )
    sel_id = sel.split(" — ")[0]
    cibles = avec_email[avec_email["stagiaire_id"] == sel_id]

# Type d'envoi
type_envoi = st.multiselect(
    "Que veux-tu envoyer ?",
    ["Liens satisfaction + auto-évaluation", "PDF QR émargement en pièce jointe"],
    default=["Liens satisfaction + auto-évaluation"],
)

sujet = st.text_input(
    "Sujet de l'email",
    value=f"Formation {session_row['nom']} — Vos liens de suivi",
)

st.caption(f"**{len(cibles)} email(s) à envoyer**")

envoyer_btn = st.button(
    f"📧 Envoyer à {len(cibles)} stagiaire(s)",
    type="primary",
    disabled=(brevo_cfg is None),
)

if brevo_cfg is None:
    st.info("Configure la clé Brevo dans la sidebar pour activer l'envoi.")

if envoyer_btn and brevo_cfg:
    # Import QR PDF si nécessaire
    pdf_qr_fn = None
    if "PDF QR émargement en pièce jointe" in type_envoi and prog_row is not None:
        try:
            import sys
            sys.path.insert(0, "pages")
            from datetime import timedelta
            from reportlab.graphics.barcode import qr as qr_mod
            from reportlab.graphics.shapes import Drawing
            from reportlab.graphics import renderPDF
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib.pagesizes import A4
            from pypdf import PdfReader, PdfWriter
            import importlib.util, os

            # Charger la fonction depuis 3_Emargement.py
            spec = importlib.util.spec_from_file_location(
                "emargement", Path("pages") / "3_Emargement.py"
            )
            if spec is None:
                spec = importlib.util.spec_from_file_location(
                    "emargement", Path("3_Emargement.py")
                )
            em_mod = importlib.util.module_from_spec(spec)
            # On recrée la fonction ici directement pour éviter les dépendances
            pdf_qr_fn = "available"
        except Exception:
            pdf_qr_fn = None

    progress = st.progress(0, text="Envoi en cours...")
    results  = {"ok": 0, "erreurs": []}

    for i, (_, stag) in enumerate(cibles.iterrows()):
        lien_sat = make_lien(base_url, stag["stagiaire_id"], session_id, "satisfaction")
        lien_ae  = make_lien(base_url, stag["stagiaire_id"], session_id, "auto_eval")

        html_body = build_email_html(
            nom_stag          = stag["nom"],
            nom_formation     = session_row["nom"],
            date_debut        = fmt_date(session_row["date_debut"]),
            date_fin          = fmt_date(session_row["date_fin"]),
            lien_satisfaction = lien_sat,
            lien_auto_eval    = lien_ae,
        )

        result = envoyer_email_brevo(
            api_key          = brevo_cfg["api_key"],
            sender_email     = brevo_cfg["sender_email"],
            sender_name      = brevo_cfg["sender_name"],
            destinataire_email = stag["email"],
            destinataire_nom   = stag["nom"],
            sujet              = sujet,
            html_body          = html_body,
        )

        if result["ok"]:
            results["ok"] += 1
        else:
            results["erreurs"].append(f"{stag['nom']} : {result['error']}")

        progress.progress(
            (i + 1) / len(cibles),
            text=f"Envoyé à {stag['nom']}..."
        )

    progress.empty()

    if results["ok"] > 0:
        st.success(f"✅ {results['ok']} email(s) envoyé(s) avec succès !")
    for err in results["erreurs"]:
        st.error(f"❌ {err}")

# ── Récap réponses reçues ─────────────────────────────────────
st.divider()
st.subheader("📊 Réponses reçues")

satisfaction = load(DATA_DIR / "satisfaction_stagiaire.csv",
                    ["satisfaction_id","stagiaire_id","session_id","date",
                     "rubrique","note","commentaire"])
auto_evaluation = load(DATA_DIR / "auto_evaluation.csv",
                       ["auto_eval_id","stagiaire_id","session_id","competence_id",
                        "moment","note","commentaire"])

col1, col2 = st.columns(2)

with col1:
    sat_sess = satisfaction[satisfaction["session_id"] == session_id] \
               if not satisfaction.empty else pd.DataFrame()
    stags_sat = sat_sess["stagiaire_id"].nunique() if not sat_sess.empty else 0
    st.metric(
        "✅ Satisfactions reçues",
        f"{stags_sat} / {len(avec_email)}",
        delta=f"{len(avec_email) - stags_sat} en attente" if stags_sat < len(avec_email) else "Complet"
    )

with col2:
    ae_sess = auto_evaluation[auto_evaluation["session_id"] == session_id] \
              if not auto_evaluation.empty else pd.DataFrame()
    stags_ae = ae_sess["stagiaire_id"].nunique() if not ae_sess.empty else 0
    st.metric(
        "🔍 Auto-évaluations reçues",
        f"{stags_ae} / {len(avec_email)}",
        delta=f"{len(avec_email) - stags_ae} en attente" if stags_ae < len(avec_email) else "Complet"
    )

# Détail par stagiaire
if not avec_email.empty:
    with st.expander("Détail par stagiaire"):
        rows = []
        for _, stag in avec_email.iterrows():
            has_sat = not satisfaction.empty and not satisfaction[
                (satisfaction["stagiaire_id"] == stag["stagiaire_id"]) &
                (satisfaction["session_id"]   == session_id)
            ].empty
            has_ae = not auto_evaluation.empty and not auto_evaluation[
                (auto_evaluation["stagiaire_id"] == stag["stagiaire_id"]) &
                (auto_evaluation["session_id"]   == session_id)
            ].empty
            rows.append({
                "Stagiaire":        stag["nom"],
                "Email":            stag["email"],
                "Satisfaction":     "✅" if has_sat else "⏳",
                "Auto-évaluation":  "✅" if has_ae  else "⏳",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
