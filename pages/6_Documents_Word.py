import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date
from io import BytesIO
import zipfile as zipmod
import re

# ============================================================
# HOF - Génération documents Word depuis templates publipostage
# pages/6_Documents_Word.py
# ============================================================

DATA_DIR     = Path("data")
EXPORT_DIR   = Path("exports")
TEMPLATE_DIR = Path("templates_word")
EXPORT_DIR.mkdir(exist_ok=True)
TEMPLATE_DIR.mkdir(exist_ok=True)

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
competences = load(DATA_DIR / "competences.csv",
                   ["competence_id","referentiel_id","epreuve","bloc","section",
                    "code_competence","competence","famille","niveau","actif"])

# ── Helpers ──────────────────────────────────────────────────

def fmt_date(s):
    try:
        return pd.to_datetime(s).strftime("%d/%m/%Y")
    except Exception:
        return str(s)

def get_val(df, id_col, val, target_col, fallback=""):
    r = df[df[id_col] == val]
    return str(r.iloc[0][target_col]) if not r.empty else fallback

def jours_formation(date_debut, date_fin):
    """Retourne la liste des jours ouvrés entre deux dates."""
    from datetime import timedelta
    try:
        d1 = pd.to_datetime(date_debut).date()
        d2 = pd.to_datetime(date_fin).date()
        jours, cur = [], d1
        while cur <= d2:
            if cur.weekday() < 5:
                jours.append(cur)
            cur += timedelta(days=1)
        return jours
    except Exception:
        return []

# ── Moteur de remplacement MERGEFIELD ────────────────────────

def replace_mergefield(xml: str, field_name: str, new_value: str) -> tuple:
    """
    Remplace un champ MERGEFIELD dans le XML Word.
    Gère 3 patterns : fldChar+separate, fldSimple, fldChar sans separate.
    Retourne (xml_modifié, nb_remplacements).
    """
    safe = (new_value
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))
    fn = re.escape(field_name)

    # Pattern 1 : fldChar begin → instrText → separate → valeur → end
    p1 = (
        r'(MERGEFIELD\s+["\']?' + fn + r'["\']?\s*</w:instrText>)'
        r'(.*?<w:fldChar w:fldCharType="separate"/>)'
        r'(.*?)'
        r'(<w:fldChar w:fldCharType="end"/>)'
    )
    def repl1(m):
        mid = m.group(3)
        if re.search(r'<w:t', mid):
            mid = re.sub(r'<w:t[^>]*>[^<]*</w:t>', f'<w:t>{safe}</w:t>', mid)
        else:
            mid += f'<w:r><w:t>{safe}</w:t></w:r>'
        return m.group(1) + m.group(2) + mid + m.group(4)
    xml, n1 = re.subn(p1, repl1, xml, flags=re.DOTALL)

    # Pattern 2 : fldSimple inline
    p2 = (
        r'(<w:fldSimple\s+w:instr="[^"]*MERGEFIELD\s+["\']?' + fn + r'["\']?[^"]*">)'
        r'(.*?)(</w:fldSimple>)'
    )
    def repl2(m):
        mid = re.sub(r'<w:t[^>]*>[^<]*</w:t>', f'<w:t>{safe}</w:t>', m.group(2))
        return m.group(1) + mid + m.group(3)
    xml, n2 = re.subn(p2, repl2, xml, flags=re.DOTALL)

    # Pattern 3 : fldChar begin → instrText → end (sans separate ni valeur)
    p3 = (
        r'(<w:fldChar w:fldCharType="begin"/>)</w:r>'
        r'(<w:r><w:instrText[^>]*>\s*MERGEFIELD\s+["\']?' + fn + r'["\']?\s*</w:instrText></w:r>)'
        r'(<w:r><w:fldChar w:fldCharType="end"/>)</w:r>'
    )
    repl3 = (
        r'\1</w:r>\2'
        r'<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        f'<w:r><w:t>{safe}</w:t></w:r>'
        r'\3</w:r>'
    )
    xml, n3 = re.subn(p3, repl3, xml, flags=re.DOTALL)

    return xml, n1 + n2 + n3


def fill_template(template_path: Path, fields: dict) -> bytes:
    """
    Remplace tous les champs MERGEFIELD d'un .docx template.
    fields = {"NomChamp": "valeur", ...}
    Retourne les bytes du .docx généré.
    """
    with zipmod.ZipFile(str(template_path), 'r') as zin:
        xml = zin.read('word/document.xml').decode('utf-8')

    replacements = {}
    for field, value in fields.items():
        xml, n = replace_mergefield(xml, field, str(value))
        replacements[field] = n

    buf = BytesIO()
    with zipmod.ZipFile(str(template_path), 'r') as zin:
        with zipmod.ZipFile(buf, 'w', zipmod.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == 'word/document.xml':
                    zout.writestr(item, xml.encode('utf-8'))
                else:
                    zout.writestr(item, zin.read(item.filename))

    return buf.getvalue(), replacements


# ── Builders par type de document ────────────────────────────

def build_programme(session_row, prog_row, formateur_nom, tpl_path) -> bytes:
    """Génère le programme de formation."""
    jours = jours_formation(session_row["date_debut"], session_row["date_fin"])
    nb_jours = int(float(prog_row["duree_heures"]) / 8) if prog_row["duree_heures"] else len(jours)

    # Dates par jour
    dates_str = " · ".join(j.strftime("%d/%m/%Y") for j in jours) if jours else \
                f"{fmt_date(session_row['date_debut'])} au {fmt_date(session_row['date_fin'])}"

    fields = {
        "Formation":        prog_row["nom_programme"],
        "Objectifs":        prog_row["objectifs"],
        "Programme":        prog_row.get("programme_detail", prog_row["objectifs"]),
        "Orga":             prog_row.get("modalites", "Formation 100% en présentiel"),
        "jours":            f"{nb_jours} jours — {prog_row['duree_heures']} heures",
        "prochaines_dates": f"{fmt_date(session_row['date_debut'])} au {fmt_date(session_row['date_fin'])}",
        "jour1_":           jours[0].strftime("%d/%m/%Y") if jours else "",
    }
    # Jours supplémentaires si le template en a
    for i, jour in enumerate(jours[1:], 2):
        fields[f"jour{i}_"] = jour.strftime("%d/%m/%Y")

    doc_bytes, stats = fill_template(tpl_path, fields)
    return doc_bytes, stats


def build_convocation(session_row, stag_row, prog_row, formateur_nom, tpl_path) -> bytes:
    """Génère la convocation pour un stagiaire."""
    fields = {
        "Formation":        prog_row["nom_programme"],
        "Stagiaire":        stag_row["nom"],
        "Formateur":        formateur_nom,
        "Entreprise":       stag_row.get("entreprise", ""),
        "E-mail":           stag_row.get("email", ""),
        "Date":             date.today().strftime("%d/%m/%Y"),
        "Date_formation":   fmt_date(session_row["date_debut"]),
        "date_debut":       fmt_date(session_row["date_debut"]),
        "date_fin":         fmt_date(session_row["date_fin"]),
        "durée":            f"{prog_row['duree_heures']} heures",
        "Horaires":         "8h30 — 17h30 (pause 1 heure)",
        "lieu":             "3 rue Caussette 31000 TOULOUSE",
        "n_stagiaires":     "",
    }
    doc_bytes, stats = fill_template(tpl_path, fields)
    return doc_bytes, stats


# ════════════════════════════════════════════════════════════
# INTERFACE STREAMLIT
# ════════════════════════════════════════════════════════════

st.title("📝 Documents Word — Publipostage HOF")
st.caption("Génère les documents Word depuis tes templates .docx existants")

# ── Sidebar : upload templates ────────────────────────────────
WORD_TEMPLATES = {
    "programme":   "Programme de formation",
    "convocation": "Convocation / Contrat",
}

with st.sidebar:
    st.header("📁 Templates Word")
    st.caption("Uploade tes .docx une seule fois")
    for key, label in WORD_TEMPLATES.items():
        folder = TEMPLATE_DIR / key
        folder.mkdir(exist_ok=True)
        existing = list(folder.glob("*.docx"))
        if existing:
            st.success(f"✅ {label} — `{existing[0].name}`")
            if st.button(f"🔄 Remplacer", key=f"replace_{key}"):
                for f in existing:
                    f.unlink()
                st.rerun()
        else:
            up = st.file_uploader(f"📎 {label}", type="docx", key=f"up_{key}")
            if up:
                dest = folder / up.name
                dest.write_bytes(up.read())
                st.success(f"✅ Sauvegardé")
                st.rerun()
    st.divider()
    st.caption("Docs générés dans /exports")

def get_tpl(key):
    files = list((TEMPLATE_DIR / key).glob("*.docx"))
    return files[0] if files else None

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
formateur_nom = get_val(formateurs, "formateur_id", formateur_id, "nom", "—")
stag_session  = stagiaires[stagiaires["session_id"] == session_id] \
                if not stagiaires.empty else pd.DataFrame()

st.info(
    f"**{session_row['nom']}** | "
    f"{fmt_date(session_row['date_debut'])} → {fmt_date(session_row['date_fin'])} | "
    f"**{len(stag_session)} stagiaire(s)** | Formateur : {formateur_nom}"
)
st.divider()

# ── Onglets ───────────────────────────────────────────────────
tabs = st.tabs(["📋 Programme", "📨 Convocations", "🔍 Vérifier les champs"])

# ── Programme ─────────────────────────────────────────────────
with tabs[0]:
    st.subheader("Programme de formation")
    tpl = get_tpl("programme")

    if not tpl:
        st.warning("Template programme manquant — uploade `Programme_formation_vierge.docx` dans la sidebar.")
    elif prog_row is None:
        st.warning("Programme introuvable pour cette session.")
    else:
        # Aperçu des champs
        with st.expander("📋 Valeurs qui seront injectées"):
            jours = jours_formation(session_row["date_debut"], session_row["date_fin"])
            st.json({
                "Formation":        prog_row["nom_programme"],
                "Objectifs":        prog_row["objectifs"][:80] + "...",
                "Programme":        prog_row.get("programme_detail", prog_row["objectifs"])[:80] + "...",
                "Orga":             prog_row.get("modalites","")[:60],
                "jours":            f"{len(jours)} jours — {prog_row['duree_heures']}h",
                "prochaines_dates": f"{fmt_date(session_row['date_debut'])} au {fmt_date(session_row['date_fin'])}",
                "jour1_":           jours[0].strftime("%d/%m/%Y") if jours else "",
            })

        if st.button("📄 Générer le programme Word", type="primary"):
            try:
                doc_bytes, stats = build_programme(session_row, prog_row, formateur_nom, tpl)
                fname = f"programme_{session_id}.docx"
                (EXPORT_DIR / fname).write_bytes(doc_bytes)

                nb_ok = sum(v > 0 for v in stats.values())
                nb_ko = sum(v == 0 for v in stats.values())
                if nb_ko > 0:
                    st.warning(f"⚠️ {nb_ko} champ(s) non trouvé(s) dans le template : "
                               + ", ".join(k for k,v in stats.items() if v == 0))
                else:
                    st.success(f"✅ {nb_ok} champ(s) remplacé(s)")

                st.download_button(
                    "⬇️ Télécharger le programme",
                    data=doc_bytes,
                    file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            except Exception as e:
                st.error(f"Erreur : {e}")

# ── Convocations ──────────────────────────────────────────────
with tabs[1]:
    st.subheader("Convocations stagiaires")
    tpl = get_tpl("convocation")

    if not tpl:
        st.warning("Template convocation manquant — uploade ton .docx dans la sidebar.")
    elif prog_row is None:
        st.warning("Programme introuvable.")
    elif stag_session.empty:
        st.warning("Aucun stagiaire dans cette session.")
    else:
        # ZIP tous
        if st.button("📦 Générer ZIP — toutes les convocations", type="primary"):
            buf = BytesIO()
            errs = []
            with zipmod.ZipFile(buf, "w") as zf:
                for _, stag in stag_session.iterrows():
                    try:
                        doc_bytes, _ = build_convocation(
                            session_row, stag, prog_row, formateur_nom, tpl)
                        fname = f"convocation_{stag['nom'].replace(' ','_')}.docx"
                        zf.writestr(fname, doc_bytes)
                        (EXPORT_DIR / fname).write_bytes(doc_bytes)
                    except Exception as e:
                        errs.append(f"{stag['nom']}: {e}")
            for err in errs:
                st.error(err)
            st.download_button(
                "⬇️ Télécharger ZIP",
                data=buf.getvalue(),
                file_name=f"convocations_{session_id}.zip",
                mime="application/zip",
            )

        st.markdown("— ou —")

        # Individuel
        sel = st.selectbox(
            "Stagiaire",
            stag_session["stagiaire_id"] + " — " + stag_session["nom"],
            key="conv_stag_word",
        )
        stag_id  = sel.split(" — ")[0]
        stag_row = stag_session[stag_session["stagiaire_id"] == stag_id].iloc[0]

        # Aperçu champs
        with st.expander("📋 Valeurs qui seront injectées"):
            st.json({
                "Stagiaire":      stag_row["nom"],
                "Formation":      prog_row["nom_programme"],
                "Formateur":      formateur_nom,
                "Entreprise":     stag_row.get("entreprise",""),
                "Date_formation": fmt_date(session_row["date_debut"]),
                "date_fin":       fmt_date(session_row["date_fin"]),
                "durée":          f"{prog_row['duree_heures']} heures",
            })

        if st.button(f"📄 Générer la convocation — {stag_row['nom']}"):
            try:
                doc_bytes, stats = build_convocation(
                    session_row, stag_row, prog_row, formateur_nom, tpl)
                fname = f"convocation_{stag_row['nom'].replace(' ','_')}.docx"
                (EXPORT_DIR / fname).write_bytes(doc_bytes)

                nb_ko = sum(v == 0 for v in stats.values())
                if nb_ko > 0:
                    st.warning(f"⚠️ Champs non trouvés : "
                               + ", ".join(k for k,v in stats.items() if v == 0))
                st.download_button(
                    f"⬇️ {stag_row['nom']}",
                    data=doc_bytes,
                    file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            except Exception as e:
                st.error(f"Erreur : {e}")

# ── Vérificateur de champs ────────────────────────────────────
with tabs[2]:
    st.subheader("Vérifier les champs MERGEFIELD d'un template")
    st.caption("Uploade n'importe quel .docx pour voir tous ses champs de publipostage")

    check_file = st.file_uploader("Charger un .docx à analyser", type="docx")
    if check_file:
        xml_check = zipmod.ZipFile(check_file).read('word/document.xml').decode('utf-8')
        fields_found = re.findall(r'MERGEFIELD\s+["\']?([\w_]+)["\']?', xml_check)
        fields_found = list(dict.fromkeys(fields_found))  # dédoublonner

        st.success(f"**{len(fields_found)} champ(s) trouvé(s) :**")
        for f in fields_found:
            st.code(f"{{ {f} }}")

        # Correspondance avec les données HOF
        st.divider()
        st.markdown("**Correspondance avec les données HOF :**")
        HOF_FIELDS = {
            "Formation":        "nom_programme (programmes)",
            "Objectifs":        "objectifs (programmes)",
            "Programme":        "programme_detail (programmes)",
            "Orga":             "modalites (programmes)",
            "jours":            "duree_heures (programmes)",
            "prochaines_dates": "date_debut → date_fin (sessions)",
            "jour1_":           "dates jours ouvrés (sessions)",
            "Stagiaire":        "nom (stagiaires)",
            "Formateur":        "nom (formateurs)",
            "Entreprise":       "entreprise (stagiaires)",
            "E-mail":           "email (stagiaires)",
            "Date":             "date aujourd'hui",
            "Date_formation":   "date_debut (sessions)",
            "date_debut":       "date_debut (sessions)",
            "date_fin":         "date_fin (sessions)",
            "durée":            "duree_heures (programmes)",
            "Horaires":         "fixe : 8h30-17h30",
            "lieu":             "fixe : 3 rue Caussette",
        }
        rows = []
        for f in fields_found:
            rows.append({
                "Champ MERGEFIELD": f,
                "Source HOF":       HOF_FIELDS.get(f, "⚠️ Non mappé — à configurer"),
                "Statut":           "✅" if f in HOF_FIELDS else "❓",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if any(r["Statut"] == "❓" for r in rows):
            st.info("Les champs ❓ sont dans ton template mais pas encore mappés dans HOF. "
                    "Dis-moi ce qu'ils représentent et je les ajoute.")
