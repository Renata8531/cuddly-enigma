import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, date
import uuid

# ============================================================
# HOF - Gestion formation
# Version complète propre
# Compatible avec :
# - referentiels.csv
# - competences_referentiel.csv
# - programmes.csv
# - programme_competences.csv
# ============================================================

st.set_page_config(page_title="HOF - Gestion formation", layout="wide")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

FILES = {
    "sessions": DATA_DIR / "sessions.csv",
    "stagiaires": DATA_DIR / "stagiaires.csv",
    "formateurs": DATA_DIR / "formateurs.csv",
    "referentiels": DATA_DIR / "referentiels.csv",
    "competences": DATA_DIR / "competences.csv",
    "programmes": DATA_DIR / "programmes.csv",
    "programme_competences": DATA_DIR / "programme_competences.csv",
    "session_competences": DATA_DIR / "session_competences.csv",
    "emargements": DATA_DIR / "emargements.csv",
    "evaluations": DATA_DIR / "evaluations.csv",
    "satisfaction": DATA_DIR / "satisfaction_stagiaire.csv",
    "auto_evaluation": DATA_DIR / "auto_evaluation.csv",
    "bilan_formateur": DATA_DIR / "bilan_formateur.csv",
    "qualiopi": DATA_DIR / "qualiopi_checks.csv",
}

COLUMNS = {
    "sessions": [
        "session_id", "programme_id", "formateur_id",
        "nom", "date_debut", "date_fin", "prix", "cout_prevu"
    ],
    "stagiaires": [
        "stagiaire_id", "session_id", "nom", "email", "entreprise", "lien_unique"
    ],
    "formateurs": [
        "formateur_id", "nom", "email", "specialite", "lien_unique"
    ],
    "referentiels": [
        "referentiel_id", "code_rncp", "intitule", "niveau", "metier", "actif", "source"
    ],
    "competences": [
        "competence_id", "referentiel_id", "epreuve", "bloc", "section",
        "code_competence", "competence", "famille", "niveau", "actif"
    ],
    "programmes": [
        "programme_id", "referentiel_id", "nom_programme", "duree_heures",
        "objectifs", "prerequis", "modalites"
    ],
    "programme_competences": [
        "programme_id", "competence_id", "prevue"
    ],
    "session_competences": [
        "session_id", "competence_id", "prevue", "realisee", "a_evaluer"
    ],
    "emargements": [
        "emargement_id", "stagiaire_id", "session_id", "date",
        "moment", "signature_stagiaire", "signature_formateur", "horodatage"
    ],
    "evaluations": [
        "evaluation_id", "stagiaire_id", "session_id", "competence_id",
        "epreuve", "niveau", "commentaire", "horodatage"
    ],
    "satisfaction": [
        "satisfaction_id", "stagiaire_id", "session_id", "date",
        "rubrique", "note", "commentaire"
    ],
    "auto_evaluation": [
        "auto_eval_id", "stagiaire_id", "session_id", "competence_id",
        "moment", "note", "commentaire"
    ],
    "bilan_formateur": [
        "bilan_id", "formateur_id", "session_id", "rubrique",
        "note", "reponse", "commentaire", "date"
    ],
    "qualiopi": [
        "check_id", "session_id", "element", "fait"
    ],
}


# ============================================================
# Fonctions utilitaires
# ============================================================

def load_csv(name: str) -> pd.DataFrame:
    file = FILES[name]
    cols = COLUMNS[name]

    if not file.exists():
        return pd.DataFrame(columns=cols)

    attempts = [
        {"encoding": "utf-8-sig", "sep": ","},
        {"encoding": "utf-8", "sep": ","},
        {"encoding": "latin1", "sep": ","},
        {"encoding": "utf-8-sig", "sep": ";"},
        {"encoding": "utf-8", "sep": ";"},
        {"encoding": "latin1", "sep": ";"},
    ]

    last_error = None

    for params in attempts:
        try:
            df = pd.read_csv(file, dtype=str, **params).fillna("")

            # Si tout est lu dans une seule colonne, c'est souvent le mauvais séparateur
            if len(df.columns) == 1 and len(cols) > 1:
                continue

            for col in cols:
                if col not in df.columns:
                    df[col] = ""

            return df[cols]

        except Exception as exc:
            last_error = exc

    st.error(f"Impossible de lire {file}. Erreur : {last_error}")
    return pd.DataFrame(columns=cols)


def save_csv(name: str, df: pd.DataFrame):
    FILES[name].parent.mkdir(exist_ok=True)
    df.to_csv(FILES[name], index=False, encoding="utf-8-sig")


def generate_id(df: pd.DataFrame, id_col: str, prefix: str) -> str:
    if df.empty or id_col not in df.columns:
        return f"{prefix}0001"

    numbers = []

    for value in df[id_col].dropna().astype(str):
        if value.startswith(prefix):
            raw = value.replace(prefix, "")
            if raw.isdigit():
                numbers.append(int(raw))

    next_number = max(numbers) + 1 if numbers else 1
    return f"{prefix}{next_number:04d}"


def safe_float(value) -> float:
    try:
        if value == "":
            return 0.0
        return float(str(value).replace(",", "."))
    except Exception:
        return 0.0


def get_name(df: pd.DataFrame, id_col: str, name_col: str, item_id: str) -> str:
    if df.empty or not item_id:
        return ""
    result = df[df[id_col] == item_id]
    if result.empty:
        return item_id
    return str(result.iloc[0][name_col])


def bool_value(value) -> bool:
    return str(value).lower() in ["true", "1", "oui", "yes"]


# ============================================================
# Chargement des données
# ============================================================

sessions = load_csv("sessions")
stagiaires = load_csv("stagiaires")
formateurs = load_csv("formateurs")
referentiels = load_csv("referentiels")
competences = load_csv("competences")
programmes = load_csv("programmes")
programme_competences = load_csv("programme_competences")
session_competences = load_csv("session_competences")
emargements = load_csv("emargements")
evaluations = load_csv("evaluations")
satisfaction = load_csv("satisfaction")
auto_evaluation = load_csv("auto_evaluation")
bilan_formateur = load_csv("bilan_formateur")
qualiopi = load_csv("qualiopi")


# ============================================================
# Interface
# ============================================================

st.title("HOF - Gestion formation V1.0")

# ── Raccourcis vers les pages multipage ──────────────────────
with st.sidebar:
    st.markdown("### 🗂️ Menu principal")
    menu = st.radio(
        "Menu",
        [
            "Tableau de bord",
            "Référentiels",
            "Programmes",
            "Formateurs",
            "Sessions",
            "Stagiaires",
            "Fiche stagiaire",
            "Compétences réalisées",
            "Évaluations ciblées",
            "Émargement",
            "Satisfaction stagiaire",
            "Auto-évaluation stagiaire",
            "Bilan formateur",
            "Qualiopi",
            "BPF",
        ],
    )
    st.divider()
    st.markdown("### 🚀 Outils")
    st.markdown("📅 [Calendrier formations](1_Calendrier)")
    st.markdown("📄 [Génération PDF](2_Documents)")
    st.markdown("✍️ [QR Émargement](3_Emargement)")
    st.markdown("📧 [Envoi liens stagiaires](4_Envoi_liens)")
    st.markdown("🔏 [Signature électronique](5_Signature)")
    st.markdown("📝 [Documents Word](6_Documents_Word)")
    st.markdown("📊 [Évaluations](7_Evaluations)")
    st.divider()
    st.markdown("### ⚙️ Admin")
    st.markdown("🗄️ [Import référentiels & grilles](0_Administration)")


# ============================================================
# Tableau de bord
# ============================================================

if menu == "Tableau de bord":
    st.header("Tableau de bord")

    today         = pd.Timestamp.today().date()
    current_month = today.month
    current_year  = today.year

    # ── Métriques globales ────────────────────────────────────
    signatures_db = Path("data/signatures.csv")
    otp_db        = Path("data/otp_pending.csv")

    def load_simple(path, cols):
        if not path.exists():
            return pd.DataFrame(columns=cols)
        try:
            return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
        except Exception:
            return pd.DataFrame(columns=cols)

    signatures_df  = load_simple(signatures_db, ["signature_id","statut","session_id"])
    otp_df         = load_simple(otp_db, ["otp_id","stagiaire_id","expire_at"])

    col1, col2, col3, col4 = st.columns(4)

    nb_sessions   = len(sessions)
    nb_stagiaires = len(stagiaires)
    nb_signes     = len(signatures_df[signatures_df.get("statut","") == "signe"]) \
                    if not signatures_df.empty and "statut" in signatures_df.columns else 0
    nb_otp        = len(otp_df) if not otp_df.empty else 0

    col1.metric("Sessions totales",     nb_sessions)
    col2.metric("Stagiaires inscrits",  nb_stagiaires)
    col3.metric("Documents signés",     nb_signes)
    col4.metric("Signatures en attente", nb_otp,
                delta=f"⚠️ {nb_otp} en cours" if nb_otp > 0 else None,
                delta_color="inverse")

    st.divider()

    # ── Sessions du mois ─────────────────────────────────────
    st.subheader("Formations prévues ce mois-ci")

    if sessions.empty:
        st.info("Aucune session prévue.")
    else:
        sessions_display = sessions.copy()
        sessions_display["date_debut_dt"] = pd.to_datetime(
            sessions_display["date_debut"], errors="coerce"
        )

        sessions_mois = sessions_display[
            (sessions_display["date_debut_dt"].dt.month == current_month)
            & (sessions_display["date_debut_dt"].dt.year == current_year)
        ]

        if sessions_mois.empty:
            st.info("Aucune formation prévue ce mois-ci.")
        else:
            st.dataframe(
                sessions_mois[
                    ["session_id", "nom", "date_debut", "date_fin", "programme_id", "formateur_id"]
                ],
                use_container_width=True
            )

    st.divider()

    st.subheader("Formations en cours")

    if sessions.empty:
        st.info("Aucune formation en cours.")
    else:
        sessions_display["date_fin_dt"] = pd.to_datetime(
            sessions_display["date_fin"], errors="coerce"
        )

        en_cours = sessions_display[
            (sessions_display["date_debut_dt"].dt.date <= today)
            & (sessions_display["date_fin_dt"].dt.date >= today)
        ]

        if en_cours.empty:
            st.info("Aucune formation en cours aujourd'hui.")
        else:
            st.dataframe(
                en_cours[
                    ["session_id", "nom", "date_debut", "date_fin"]
                ],
                use_container_width=True
            )

    st.divider()

    st.subheader("Tâches à réaliser")

    taches = []

    for _, session in sessions.iterrows():
        session_id = session["session_id"]
        nom_session = session["nom"]

        stagiaires_session = stagiaires[stagiaires["session_id"] == session_id]
        emargements_session = emargements[emargements["session_id"] == session_id]
        evaluations_session = evaluations[evaluations["session_id"] == session_id]
        satisfaction_session = satisfaction[satisfaction["session_id"] == session_id]
        bilan_session = bilan_formateur[bilan_formateur["session_id"] == session_id]

        if stagiaires_session.empty:
            taches.append([session_id, nom_session, "Ajouter les stagiaires"])

        if emargements_session.empty:
            taches.append([session_id, nom_session, "Prévoir / vérifier l’émargement"])

        if evaluations_session.empty:
            taches.append([session_id, nom_session, "Préparer les évaluations"])

        if satisfaction_session.empty:
            taches.append([session_id, nom_session, "Envoyer satisfaction stagiaire"])

        if bilan_session.empty:
            taches.append([session_id, nom_session, "Faire remplir le bilan formateur"])

    if taches:
        df_taches = pd.DataFrame(
            taches,
            columns=["Session", "Formation", "Tâche à réaliser"]
        )
        st.dataframe(df_taches, use_container_width=True)
    else:
        st.success("Aucune tâche urgente détectée.")

    st.divider()

    # ── Signatures en attente ─────────────────────────────────
    st.subheader("🔏 Signatures en attente")
    if not otp_df.empty and "expire_at" in otp_df.columns:
        otp_valides = []
        for _, row in otp_df.iterrows():
            try:
                exp = datetime.fromisoformat(row["expire_at"])
                if datetime.now() < exp:
                    nom_stag = get_name(stagiaires, "stagiaire_id", "nom",
                                       row.get("stagiaire_id","")) if not stagiaires.empty else row.get("stagiaire_id","")
                    otp_valides.append({
                        "Stagiaire": nom_stag,
                        "Expire":    exp.strftime("%d/%m/%Y %H:%M"),
                    })
            except Exception:
                pass
        if otp_valides:
            st.dataframe(pd.DataFrame(otp_valides), use_container_width=True, hide_index=True)
        else:
            st.info("Aucune signature en attente.")
    else:
        st.info("Aucune signature en attente.")

    st.divider()

    # ── Accès rapide ──────────────────────────────────────────
    st.subheader("🚀 Accès rapide")
    st.markdown("""
- 📅 [Calendrier formations](1_Calendrier)
- 📄 [Générer des PDF](2_Documents)
- ✍️ [QR codes émargement](3_Emargement)
- 📧 [Envoyer aux stagiaires](4_Envoi_liens)
- 🔏 [Signature électronique](5_Signature)
""")

    st.divider()

    # ── Candidatures ─────────────────────────────────────────
    st.subheader("Candidatures / stagiaires postulants")
    with st.form("form_candidature"):
        nom_c         = st.text_input("Nom du stagiaire")
        email_c       = st.text_input("Email")
        telephone_c   = st.text_input("Téléphone")
        financement_c = st.selectbox(
            "Financement",
            ["OPCO", "CPF", "Transition PRO", "Fonds perso"]
        )
        formation_c   = st.selectbox(
            "Formation souhaitée",
            programmes["nom_programme"].tolist() if not programmes.empty else ["—"]
        )
        entreprise_c  = st.text_input("Entreprise (si disponible)")
        submitted_c   = st.form_submit_button("Enregistrer la candidature")

        if submitted_c and nom_c.strip():
            cand_path = Path("data/candidatures.csv")
            cand_cols = ["candidature_id","nom","email","telephone",
                         "financement","formation","entreprise","date","statut"]
            if cand_path.exists():
                cand_df = pd.read_csv(cand_path, dtype=str).fillna("")
                for c in cand_cols:
                    if c not in cand_df.columns:
                        cand_df[c] = ""
            else:
                cand_df = pd.DataFrame(columns=cand_cols)
            new_cand = {
                "candidature_id": f"CA{len(cand_df)+1:04d}",
                "nom":        nom_c,
                "email":      email_c,
                "telephone":  telephone_c,
                "financement":financement_c,
                "formation":  formation_c,
                "entreprise": entreprise_c,
                "date":       date.today().isoformat(),
                "statut":     "postulé",
            }
            cand_df = pd.concat([cand_df, pd.DataFrame([new_cand])], ignore_index=True)
            cand_df.to_csv(cand_path, index=False, encoding="utf-8-sig")
            st.success(f"Candidature de {nom_c} enregistrée !")
            st.rerun()
# ============================================================
# Référentiels
# ============================================================

elif menu == "Référentiels":
    st.header("Référentiels RNCP")

    tabs_ref = st.tabs(["📋 Référentiels", "🎯 Compétences", "📥 Importer CSV", "➕ Saisie manuelle"])

    # ── Onglet 1 : Liste des référentiels ─────────────────
    with tabs_ref[0]:
        st.subheader("Référentiels enregistrés")
        if referentiels.empty:
            st.info("Aucun référentiel. Importe les CSV depuis l'onglet **Importer CSV**.")
        else:
            # Affichage enrichi
            for _, ref in referentiels.iterrows():
                actif_badge = "🟢" if ref.get("actif","1") == "1" else "⚫"
                with st.expander(f"{actif_badge} **{ref['intitule']}** — {ref['code_rncp']}"):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Code RNCP", ref["code_rncp"])
                    c2.metric("Niveau", ref.get("niveau","—"))
                    c3.metric("Type", ref.get("type", ref.get("metier","—")))

                    # Compétences liées
                    comps_ref = competences[competences["referentiel_id"] == ref["referentiel_id"]] \
                                if not competences.empty else pd.DataFrame()
                    st.caption(f"{len(comps_ref)} compétence(s) EP1/EP2 associée(s)")

                    if not comps_ref.empty:
                        ep_counts = comps_ref.groupby("epreuve").size()
                        cols = st.columns(len(ep_counts))
                        for i, (ep, n) in enumerate(ep_counts.items()):
                            cols[i].metric(ep, n)

    # ── Onglet 2 : Compétences ────────────────────────────
    with tabs_ref[1]:
        st.subheader("Compétences EP1 / EP2")

        if competences.empty:
            st.info("Aucune compétence. Importe les CSV depuis l'onglet **Importer CSV**.")
        else:
            col_f1, col_f2 = st.columns(2)

            with col_f1:
                # Filtre par référentiel
                ref_opts = ["Tous"] + competences["referentiel_id"].unique().tolist()
                sel_ref = st.selectbox("Référentiel", ref_opts, key="comp_ref_filter")

            with col_f2:
                ep_opts = ["Toutes"] + sorted(
                    [x for x in competences["epreuve"].unique() if x]
                )
                sel_ep = st.selectbox("Épreuve", ep_opts, key="comp_ep_filter")

            filtered = competences.copy()
            if sel_ref != "Tous":
                filtered = filtered[filtered["referentiel_id"] == sel_ref]
            if sel_ep != "Toutes":
                filtered = filtered[filtered["epreuve"] == sel_ep]

            st.caption(f"{len(filtered)} compétence(s) affichée(s)")
            st.dataframe(
                filtered[["referentiel_id","epreuve","famille","competence","code_competence"]],
                use_container_width=True,
                hide_index=True,
            )

    # ── Onglet 3 : Import CSV ─────────────────────────────
    with tabs_ref[2]:
        st.subheader("Importer un référentiel RNCP depuis CSV")
        st.caption(
            "Les CSV sont dans le dossier `data/referentiels/` du ZIP téléchargé. "
            "Chaque fichier contient un diplôme complet (EP1 + EP2)."
        )

        RNCP_DISPONIBLES = {
            "RNCP38765": "CAP Pâtissier",
            "RNCP38632": "CAP Chocolaterie-Confiserie",
            "RNCP37534": "CAP Glacier Fabricant",
            "RNCP38597": "CAP Boulanger",
            "RNCP38761": "CS Pâtisserie de boutique",
            "RNCP38762": "CS Chocolaterie",
            "RNCP38763": "CS Glacerie-Confiserie",
            "RNCP41998": "BTM Pâtissier-glacier-chocolatier",
        }

        # Statut de chaque référentiel
        for rncp_id, label in RNCP_DISPONIBLES.items():
            deja = not referentiels.empty and rncp_id in referentiels["referentiel_id"].values
            comps_count = len(competences[competences["referentiel_id"] == rncp_id]) \
                          if not competences.empty else 0
            if deja:
                st.success(f"✅ **{label}** ({rncp_id}) — {comps_count} compétences")
            else:
                st.warning(f"⬜ **{label}** ({rncp_id}) — non importé")

        st.divider()

        uploaded_csv = st.file_uploader(
            "Charger un CSV référentiel (ex: RNCP38765_CAP_Patissier.csv)",
            type="csv",
            key="import_ref_csv",
        )

        if uploaded_csv:
            try:
                df_import = pd.read_csv(uploaded_csv, dtype=str, encoding="utf-8-sig").fillna("")
                if "," not in uploaded_csv.name and len(df_import.columns) == 1:
                    uploaded_csv.seek(0)
                    df_import = pd.read_csv(uploaded_csv, dtype=str, encoding="utf-8-sig", sep=";").fillna("")

                st.success(f"✅ {len(df_import)} lignes lues")
                st.dataframe(df_import.head(5), use_container_width=True)

                if st.button("💾 Importer dans HOF", type="primary"):
                    # Détecter le referentiel_id du CSV
                    if "referentiel_id" not in df_import.columns:
                        st.error("Colonne 'referentiel_id' manquante dans le CSV.")
                    else:
                        rncp_id = df_import["referentiel_id"].iloc[0]
                        intitule = df_import["intitule_ref"].iloc[0] \
                                   if "intitule_ref" in df_import.columns else rncp_id
                        niveau   = df_import["niveau"].iloc[0] \
                                   if "niveau" in df_import.columns else ""
                        type_ref = df_import["type"].iloc[0] \
                                   if "type" in df_import.columns else ""

                        # 1. Ajouter le référentiel s'il n'existe pas
                        if referentiels.empty or rncp_id not in referentiels["referentiel_id"].values:
                            new_ref = {
                                "referentiel_id": rncp_id,
                                "code_rncp":      rncp_id,
                                "intitule":       intitule,
                                "niveau":         niveau,
                                "metier":         type_ref,
                                "actif":          "1",
                                "source":         "France Compétences",
                            }
                            referentiels = pd.concat(
                                [referentiels, pd.DataFrame([new_ref])],
                                ignore_index=True,
                            )
                            save_csv("referentiels", referentiels)

                        # 2. Ajouter les compétences (supprimer les anciennes du même RNCP)
                        comp_cols = COLUMNS["competences"]
                        if not competences.empty:
                            competences_clean = competences[
                                competences["referentiel_id"] != rncp_id
                            ].copy()
                        else:
                            competences_clean = pd.DataFrame(columns=comp_cols)

                        # Adapter les colonnes du CSV importé
                        new_comps = df_import.copy()
                        for c in comp_cols:
                            if c not in new_comps.columns:
                                new_comps[c] = ""
                        new_comps = new_comps[comp_cols]

                        competences = pd.concat(
                            [competences_clean, new_comps],
                            ignore_index=True,
                        )
                        save_csv("competences", competences)

                        st.success(
                            f"✅ **{intitule}** importé — "
                            f"{len(new_comps)} compétences enregistrées"
                        )
                        st.rerun()

            except Exception as e:
                st.error(f"Erreur lors de la lecture du CSV : {e}")

    # ── Onglet 4 : Saisie manuelle ────────────────────────
    with tabs_ref[3]:
        col_manual1, col_manual2 = st.columns(2)

        with col_manual1:
            st.subheader("Ajouter un référentiel manuellement")
            with st.form("form_referentiel"):
                code_rncp  = st.text_input("Code RNCP (ex: RNCP38765)")
                intitule   = st.text_input("Intitulé (ex: CAP Pâtissier)")
                niveau     = st.text_input("Niveau (ex: 3)")
                metier     = st.selectbox(
                    "Domaine",
                    ["Pâtisserie","Boulangerie","Chocolaterie","Glacerie",
                     "Confiserie","Cuisine","Traiteur","Autre"]
                )
                actif      = st.checkbox("Actif", value=True)
                submitted  = st.form_submit_button("Ajouter")

                if submitted and code_rncp.strip():
                    new = {
                        "referentiel_id": code_rncp.strip(),
                        "code_rncp":      code_rncp.strip(),
                        "intitule":       intitule,
                        "niveau":         niveau,
                        "metier":         metier,
                        "actif":          str(actif),
                        "source":         "Saisie manuelle",
                    }
                    referentiels = pd.concat(
                        [referentiels, pd.DataFrame([new])], ignore_index=True
                    )
                    save_csv("referentiels", referentiels)
                    st.success("Référentiel ajouté")
                    st.rerun()

        with col_manual2:
            st.subheader("Ajouter une compétence manuellement")
            if referentiels.empty:
                st.warning("Crée d'abord un référentiel.")
            else:
                ref_label = st.selectbox(
                    "Référentiel",
                    referentiels["referentiel_id"] + " — " + referentiels["intitule"],
                    key="ref_comp_manual",
                )
                referentiel_id = ref_label.split(" — ")[0]

                with st.form("form_competence"):
                    epreuve        = st.selectbox("Épreuve", ["EP1","EP2","BC01","BC02","BC03","BC04","BC05","Autre"])
                    famille        = st.text_input("Famille (ex: Technique)")
                    competence_txt = st.text_area("Compétence")
                    code_comp      = st.text_input("Code (ex: C5.3)")
                    submitted      = st.form_submit_button("Ajouter")

                    if submitted and competence_txt.strip():
                        new = {
                            "competence_id":   generate_id(competences, "competence_id", "C"),
                            "referentiel_id":  referentiel_id,
                            "epreuve":         epreuve,
                            "bloc":            "",
                            "section":         "",
                            "code_competence": code_comp,
                            "competence":      competence_txt,
                            "famille":         famille,
                            "niveau":          "",
                            "actif":           "1",
                        }
                        competences = pd.concat(
                            [competences, pd.DataFrame([new])], ignore_index=True
                        )
                        save_csv("competences", competences)
                        st.success("Compétence ajoutée")
                        st.rerun()


# ============================================================
# Programmes
# ============================================================


elif menu == "Programmes":
    st.header("Programmes")

    with st.expander("Créer un programme", expanded=True):
        if referentiels.empty:
            st.warning("Crée d'abord un référentiel.")
        else:
            with st.form("form_programme"):
                ref_label = st.selectbox(
                    "Référentiel associé",
                    referentiels["referentiel_id"] + " - " + referentiels["intitule"]
                )
                referentiel_id = ref_label.split(" - ")[0]

                nom_programme = st.text_input("Nom du programme")
                duree_heures = st.number_input("Durée en heures", min_value=0.0, step=1.0)
                objectifs = st.text_area("Objectifs pédagogiques")
                prerequis = st.text_area("Prérequis")
                modalites = st.text_area("Modalités pédagogiques / évaluation")

                submitted = st.form_submit_button("Créer le programme")

                if submitted:
                    if not nom_programme.strip():
                        st.error("Le nom du programme est obligatoire.")
                        st.stop()

                    new_id = generate_id(programmes, "programme_id", "P")

                    new = {
                        "programme_id": new_id,
                        "referentiel_id": referentiel_id,
                        "nom_programme": nom_programme,
                        "duree_heures": str(duree_heures),
                        "objectifs": objectifs,
                        "prerequis": prerequis,
                        "modalites": modalites,
                    }

                    programmes = pd.concat([programmes, pd.DataFrame([new])], ignore_index=True)
                    save_csv("programmes", programmes)

                    st.success(f"Programme ajouté : {new_id} - {nom_programme}")
                    st.rerun()

    st.subheader("Programmes existants")
    st.dataframe(programmes, use_container_width=True)

    st.divider()
    st.subheader("Compétences prévues dans le programme")

    if programmes.empty:
        st.warning("Crée d'abord un programme.")
    else:
        prog_label = st.selectbox(
            "Programme",
            programmes["programme_id"] + " - " + programmes["nom_programme"]
        )
        programme_id = prog_label.split(" - ")[0]

        prog = programmes[programmes["programme_id"] == programme_id].iloc[0]
        ref_id = prog["referentiel_id"]

        comps_ref = competences[competences["referentiel_id"] == ref_id].copy()

        if comps_ref.empty:
            st.warning(
                "Aucune compétence dans le référentiel associé à ce programme. "
                "Vérifie que programmes.csv et competences_referentiel.csv utilisent le même referentiel_id."
            )
            st.write("Référentiel du programme :", ref_id)
            st.write("Référentiels présents dans les compétences :", sorted(competences["referentiel_id"].unique()))

        else:
            epreuves = ["Toutes"] + sorted([x for x in comps_ref["epreuve"].unique() if x])
            selected_epreuve = st.selectbox(
                "Filtrer par épreuve",
                epreuves,
                key="prog_epreuve_filter"
            )

            visible_comps = comps_ref.copy()

            if selected_epreuve != "Toutes":
                visible_comps = visible_comps[
                    visible_comps["epreuve"] == selected_epreuve
                ]

            search = st.text_input("Rechercher une compétence", "")

            if search:
                visible_comps = visible_comps[
                    visible_comps["competence"].str.contains(search, case=False, na=False)
                    | visible_comps["code_competence"].str.contains(search, case=False, na=False)
                    | visible_comps["epreuve"].str.contains(search, case=False, na=False)
                    | visible_comps["bloc"].str.contains(search, case=False, na=False)
                    | visible_comps["famille"].str.contains(search, case=False, na=False)
                ]

            col1, col2 = st.columns(2)
            tout_cocher = col1.button("Tout cocher les compétences affichées")
            tout_decocher = col2.button("Tout décocher les compétences affichées")

            existing = programme_competences[
                (programme_competences["programme_id"] == programme_id)
                & (programme_competences["prevue"].astype(str) == "True")
            ]["competence_id"].tolist()

            table = visible_comps[
                [
                    "competence_id",
                    "epreuve",
                    "bloc",
                    "code_competence",
                    "competence",
                    "famille",
                    "niveau",
                ]
            ].copy()

            table["prévue"] = table["competence_id"].isin(existing)

            if tout_cocher:
                table["prévue"] = True

            if tout_decocher:
                table["prévue"] = False

            edited = st.data_editor(
                table,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "prévue": st.column_config.CheckboxColumn(
                        "Prévue",
                        help="Coche les compétences prévues dans ce programme",
                        default=False,
                    )
                },
                disabled=[
                    "competence_id",
                    "epreuve",
                    "bloc",
                    "code_competence",
                    "competence",
                    "famille",
                    "niveau",
                ],
            )

            if st.button("Sauvegarder les compétences du programme"):
                rows = []

                for _, row in edited.iterrows():
                    rows.append({
                        "programme_id": programme_id,
                        "competence_id": row["competence_id"],
                        "prevue": str(row["prévue"]),
                    })

                visible_ids = edited["competence_id"].tolist()

                programme_competences = programme_competences[
                    ~(
                        (programme_competences["programme_id"] == programme_id)
                        & (programme_competences["competence_id"].isin(visible_ids))
                    )
                ]

                programme_competences = pd.concat(
                    [programme_competences, pd.DataFrame(rows)],
                    ignore_index=True,
                )

                save_csv("programme_competences", programme_competences)
                st.success("Compétences du programme sauvegardées")
    
# ============================================================
# Formateurs
# ============================================================

elif menu == "Formateurs":
    st.header("Formateurs")

    with st.form("form_formateur"):
        nom = st.text_input("Nom du formateur")
        email = st.text_input("Email")
        specialite = st.text_input("Spécialité")
        submitted = st.form_submit_button("Ajouter le formateur")

        if submitted:
            new = {
                "formateur_id": generate_id(formateurs, "formateur_id", "F"),
                "nom": nom,
                "email": email,
                "specialite": specialite,
                "lien_unique": str(uuid.uuid4()),
            }

            formateurs = pd.concat([formateurs, pd.DataFrame([new])], ignore_index=True)
            save_csv("formateurs", formateurs)
            st.success("Formateur ajouté")
            st.rerun()

    st.dataframe(formateurs, use_container_width=True)


# ============================================================
# Sessions
# ============================================================

elif menu == "Sessions":
    st.header("Sessions")

    if programmes.empty:
        st.warning("Crée d'abord un programme.")
    else:
        with st.form("form_session"):
            programme_label = st.selectbox(
                "Programme",
                programmes["programme_id"] + " - " + programmes["nom_programme"]
            )
            programme_id = programme_label.split(" - ")[0]

            formateur_id = ""

            if not formateurs.empty:
                formateur_label = st.selectbox(
                    "Formateur",
                    formateurs["formateur_id"] + " - " + formateurs["nom"]
                )
                formateur_id = formateur_label.split(" - ")[0]
            else:
                st.info("Aucun formateur créé pour le moment.")

            nom = st.text_input("Nom de la session")
            date_debut = st.date_input("Date de début")
            date_fin = st.date_input("Date de fin")
            prix = st.number_input("Prix vendu (€)", min_value=0.0)
            cout_prevu = st.number_input("Coût prévu (€)", min_value=0.0)

            submitted = st.form_submit_button("Créer la session")

            if submitted:
                if not nom.strip():
                    st.error("Le nom de la session est obligatoire.")
                    st.stop()

                new_session_id = generate_id(sessions, "session_id", "S")

                new = {
                    "session_id": new_session_id,
                    "programme_id": programme_id,
                    "formateur_id": formateur_id,
                    "nom": nom,
                    "date_debut": date_debut,
                    "date_fin": date_fin,
                    "prix": str(prix),
                    "cout_prevu": str(cout_prevu),
                }

                sessions = pd.concat([sessions, pd.DataFrame([new])], ignore_index=True)
                save_csv("sessions", sessions)

                selected = programme_competences[
                    (programme_competences["programme_id"] == programme_id) &
                    (programme_competences["prevue"].astype(str) == "True")
                ]

                rows = []

                for _, row in selected.iterrows():
                    rows.append({
                        "session_id": new_session_id,
                        "competence_id": row["competence_id"],
                        "prevue": "True",
                        "realisee": "False",
                        "a_evaluer": "False",
                    })

                if rows:
                    session_competences = pd.concat(
                        [session_competences, pd.DataFrame(rows)],
                        ignore_index=True
                    )
                    save_csv("session_competences", session_competences)

                st.success("Session créée avec ses compétences prévues")
                st.rerun()

    display = sessions.copy()

    if not display.empty:
        display["programme"] = display["programme_id"].apply(
            lambda x: get_name(programmes, "programme_id", "nom_programme", x)
        )
        display["formateur"] = display["formateur_id"].apply(
            lambda x: get_name(formateurs, "formateur_id", "nom", x)
        )

    st.subheader("Sessions existantes")
    st.dataframe(display, use_container_width=True)


# ============================================================
# Stagiaires
# ============================================================

elif menu == "Stagiaires":
    st.header("Stagiaires")

    if sessions.empty:
        st.warning("Crée d'abord une session.")
    else:
        session_label = st.selectbox(
            "Session",
            sessions["session_id"] + " - " + sessions["nom"]
        )
        session_id = session_label.split(" - ")[0]

        with st.form("form_stagiaire"):
            nom = st.text_input("Nom du stagiaire")
            email = st.text_input("Email")
            entreprise = st.text_input("Entreprise")
            submitted = st.form_submit_button("Ajouter le stagiaire")

            if submitted:
                if not nom.strip():
                    st.error("Le nom du stagiaire est obligatoire.")
                    st.stop()

                new = {
                    "stagiaire_id": generate_id(stagiaires, "stagiaire_id", "ST"),
                    "session_id": session_id,
                    "nom": nom,
                    "email": email,
                    "entreprise": entreprise,
                    "lien_unique": str(uuid.uuid4()),
                }

                stagiaires = pd.concat([stagiaires, pd.DataFrame([new])], ignore_index=True)
                save_csv("stagiaires", stagiaires)
                st.success("Stagiaire ajouté")
                st.rerun()

    st.dataframe(stagiaires, use_container_width=True)
elif menu == "Fiche stagiaire":
    st.header("Fiche stagiaire")

    if stagiaires.empty:
        st.warning("Aucun stagiaire.")
    else:
        stagiaire_label = st.selectbox(
            "Choisir un stagiaire",
            stagiaires["stagiaire_id"] + " - " + stagiaires["nom"]
        )

        stagiaire_id = stagiaire_label.split(" - ")[0]
        stagiaire = stagiaires[stagiaires["stagiaire_id"] == stagiaire_id].iloc[0]

        st.subheader(stagiaire["nom"])

        st.write("Email :", stagiaire["email"])
        st.write("Entreprise :", stagiaire["entreprise"])
        st.write("Session :", stagiaire["session_id"])

        st.divider()

        st.subheader("Émargements")
        st.dataframe(emargements[emargements["stagiaire_id"] == stagiaire_id])

        st.subheader("Évaluations")
        st.dataframe(evaluations[evaluations["stagiaire_id"] == stagiaire_id])

        st.subheader("Satisfaction")
        st.dataframe(satisfaction[satisfaction["stagiaire_id"] == stagiaire_id])

# ============================================================
# Compétences réalisées
# ============================================================

elif menu == "Compétences réalisées":
    st.header("Compétences réalisées / à évaluer")

    if sessions.empty:
        st.warning("Crée d'abord une session.")
    else:
        session_label = st.selectbox(
            "Session",
            sessions["session_id"] + " - " + sessions["nom"]
        )
        session_id = session_label.split(" - ")[0]

        current = session_competences[
            session_competences["session_id"] == session_id
        ].merge(competences, on="competence_id", how="left")

        if current.empty:
            st.warning("Aucune compétence prévue sur cette session.")
        else:
            st.caption(
                "Le formateur coche ce qui a réellement été traité. "
                "L’évaluation affichera seulement les compétences marquées à évaluer."
            )

            rows = []

            for _, row in current.iterrows():
                st.markdown(f"**{row['epreuve']} | {row['code_competence']} — {row['competence']}**")

                col1, col2 = st.columns(2)

                realisee = col1.checkbox(
                    "Réalisée",
                    value=bool_value(row.get("realisee", "")),
                    key=f"realisee_{session_id}_{row['competence_id']}"
                )

                a_evaluer = col2.checkbox(
                    "À évaluer",
                    value=bool_value(row.get("a_evaluer", "")),
                    key=f"eval_{session_id}_{row['competence_id']}"
                )

                rows.append({
                    "session_id": session_id,
                    "competence_id": row["competence_id"],
                    "prevue": "True",
                    "realisee": str(realisee),
                    "a_evaluer": str(a_evaluer),
                })

            if st.button("Sauvegarder les compétences réalisées"):
                session_competences = session_competences[
                    session_competences["session_id"] != session_id
                ]
                session_competences = pd.concat(
                    [session_competences, pd.DataFrame(rows)],
                    ignore_index=True
                )
                save_csv("session_competences", session_competences)
                st.success("Compétences de session sauvegardées")


# ============================================================
# Évaluations ciblées
# ============================================================

elif menu == "Évaluations ciblées":
    st.header("Évaluations ciblées formateur")

    if sessions.empty or stagiaires.empty:
        st.warning("Il faut au moins une session et un stagiaire.")
    else:
        session_label = st.selectbox(
            "Session",
            sessions["session_id"] + " - " + sessions["nom"],
            key="eval_session"
        )
        session_id = session_label.split(" - ")[0]

        stagiaires_session = stagiaires[stagiaires["session_id"] == session_id]

        if stagiaires_session.empty:
            st.warning("Aucun stagiaire dans cette session.")
        else:
            stagiaire_label = st.selectbox(
                "Stagiaire",
                stagiaires_session["stagiaire_id"] + " - " + stagiaires_session["nom"]
            )
            stagiaire_id = stagiaire_label.split(" - ")[0]

            comps_eval = session_competences[
                (session_competences["session_id"] == session_id) &
                (session_competences["a_evaluer"].astype(str) == "True")
            ].merge(competences, on="competence_id", how="left")

            if comps_eval.empty:
                st.warning(
                    "Aucune compétence marquée 'à évaluer'. "
                    "Va dans l’onglet 'Compétences réalisées' pour les sélectionner."
                )
            else:
                rows = []

                for _, comp in comps_eval.iterrows():
                    st.markdown(f"### {comp['epreuve']} | {comp['code_competence']} — {comp['competence']}")

                    niveau = st.radio(
                        "Niveau",
                        ["DEB", "EXE", "OPE", "EXC"],
                        horizontal=True,
                        key=f"niveau_{session_id}_{stagiaire_id}_{comp['competence_id']}"
                    )

                    commentaire = st.text_area(
                        "Commentaire",
                        key=f"commentaire_{session_id}_{stagiaire_id}_{comp['competence_id']}"
                    )

                    rows.append({
                        "evaluation_id": generate_id(evaluations, "evaluation_id", "E"),
                        "stagiaire_id": stagiaire_id,
                        "session_id": session_id,
                        "competence_id": comp["competence_id"],
                        "epreuve": comp["epreuve"],
                        "niveau": niveau,
                        "commentaire": commentaire,
                        "horodatage": datetime.now().isoformat(timespec="seconds"),
                    })

                if st.button("Sauvegarder l'évaluation"):
                    evaluations = evaluations[
                        ~(
                            (evaluations["stagiaire_id"] == stagiaire_id) &
                            (evaluations["session_id"] == session_id)
                        )
                    ]
                    evaluations = pd.concat([evaluations, pd.DataFrame(rows)], ignore_index=True)
                    save_csv("evaluations", evaluations)
                    st.success("Évaluation sauvegardée")

    st.subheader("Historique évaluations")
    st.dataframe(evaluations, use_container_width=True)


# ============================================================
# Émargement
# ============================================================

elif menu == "Émargement":
    st.header("Émargement demi-journée")

    if sessions.empty or stagiaires.empty:
        st.warning("Il faut au moins une session et un stagiaire.")
    else:
        session_label = st.selectbox(
            "Session",
            sessions["session_id"] + " - " + sessions["nom"]
        )
        session_id = session_label.split(" - ")[0]
        stagiaires_session = stagiaires[stagiaires["session_id"] == session_id]

        if stagiaires_session.empty:
            st.warning("Aucun stagiaire dans cette session.")
        else:
            stagiaire_label = st.selectbox(
                "Stagiaire",
                stagiaires_session["stagiaire_id"] + " - " + stagiaires_session["nom"]
            )
            stagiaire_id = stagiaire_label.split(" - ")[0]

            jour = st.date_input("Date", value=date.today())
            moment = st.selectbox("Moment", ["Matin", "Après-midi"])
            signature_stagiaire = st.text_input("Signature stagiaire")
            signature_formateur = st.text_input("Signature formateur")

            if st.button("Enregistrer émargement"):
                new = {
                    "emargement_id": generate_id(emargements, "emargement_id", "EM"),
                    "stagiaire_id": stagiaire_id,
                    "session_id": session_id,
                    "date": jour,
                    "moment": moment,
                    "signature_stagiaire": signature_stagiaire,
                    "signature_formateur": signature_formateur,
                    "horodatage": datetime.now().isoformat(timespec="seconds"),
                }

                emargements = pd.concat([emargements, pd.DataFrame([new])], ignore_index=True)
                save_csv("emargements", emargements)
                st.success("Émargement enregistré")

    st.dataframe(emargements, use_container_width=True)


# ============================================================
# Satisfaction stagiaire
# ============================================================

elif menu == "Satisfaction stagiaire":
    st.header("Évaluation satisfaction stagiaire")

    rubriques = [
        "Accueil : qualité de l’accueil à la formation",
        "Objectifs : la formation a répondu à mes attentes",
        "Rythme de la formation / progression",
        "Animation : l’animateur est clair",
        "Animation : l’animateur est à l’écoute",
        "Réponses du formateur aux questions",
        "Thèmes abordés et compréhension",
        "Équipements et propreté du laboratoire",
        "Matériels et ingrédients mis à disposition",
        "Recettes remises utiles et faciles à utiliser",
        "Évaluation de mes productions",
        "Utilisation future des techniques / recettes",
    ]

    if stagiaires.empty:
        st.warning("Ajoute d'abord un stagiaire.")
    else:
        stagiaire_label = st.selectbox(
            "Stagiaire",
            stagiaires["stagiaire_id"] + " - " + stagiaires["nom"]
        )
        stagiaire_id = stagiaire_label.split(" - ")[0]
        stagiaire = stagiaires[stagiaires["stagiaire_id"] == stagiaire_id].iloc[0]
        session_id = stagiaire["session_id"]

        rows = []

        for rubrique in rubriques:
            note = st.radio(
                rubrique,
                ["Très bien", "Bien", "Moyen", "Faible"],
                horizontal=True,
                key=f"sat_{stagiaire_id}_{rubrique}"
            )

            rows.append({
                "satisfaction_id": generate_id(satisfaction, "satisfaction_id", "SA"),
                "stagiaire_id": stagiaire_id,
                "session_id": session_id,
                "date": date.today(),
                "rubrique": rubrique,
                "note": note,
                "commentaire": "",
            })

        remarques = st.text_area("Remarques générales")
        difficultes = st.text_area("3 techniques ou recettes ayant posé le plus de difficultés")

        if st.button("Sauvegarder satisfaction"):
            rows.append({
                "satisfaction_id": generate_id(satisfaction, "satisfaction_id", "SA"),
                "stagiaire_id": stagiaire_id,
                "session_id": session_id,
                "date": date.today(),
                "rubrique": "Remarques générales",
                "note": "",
                "commentaire": remarques,
            })
            rows.append({
                "satisfaction_id": generate_id(satisfaction, "satisfaction_id", "SA"),
                "stagiaire_id": stagiaire_id,
                "session_id": session_id,
                "date": date.today(),
                "rubrique": "Difficultés rencontrées",
                "note": "",
                "commentaire": difficultes,
            })

            satisfaction = satisfaction[
                ~(
                    (satisfaction["stagiaire_id"] == stagiaire_id) &
                    (satisfaction["session_id"] == session_id)
                )
            ]
            satisfaction = pd.concat([satisfaction, pd.DataFrame(rows)], ignore_index=True)
            save_csv("satisfaction", satisfaction)
            st.success("Satisfaction sauvegardée")

    st.dataframe(satisfaction, use_container_width=True)


# ============================================================
# Auto-évaluation
# ============================================================

elif menu == "Auto-évaluation stagiaire":
    st.header("Auto-évaluation stagiaire début / fin")

    if sessions.empty or stagiaires.empty:
        st.warning("Il faut au moins une session et un stagiaire.")
    else:
        session_label = st.selectbox(
            "Session",
            sessions["session_id"] + " - " + sessions["nom"],
            key="auto_session"
        )
        session_id = session_label.split(" - ")[0]

        stagiaires_session = stagiaires[stagiaires["session_id"] == session_id]

        if stagiaires_session.empty:
            st.warning("Aucun stagiaire dans cette session.")
        else:
            stagiaire_label = st.selectbox(
                "Stagiaire",
                stagiaires_session["stagiaire_id"] + " - " + stagiaires_session["nom"]
            )
            stagiaire_id = stagiaire_label.split(" - ")[0]

            moment = st.selectbox("Moment", ["Début de formation", "Fin de formation"])

            comps_eval = session_competences[
                (session_competences["session_id"] == session_id) &
                (session_competences["a_evaluer"].astype(str) == "True")
            ].merge(competences, on="competence_id", how="left")

            if comps_eval.empty:
                st.warning("Aucune compétence à auto-évaluer.")
            else:
                rows = []

                for _, comp in comps_eval.iterrows():
                    note = st.slider(
                        f"{comp['code_competence']} - {comp['competence']}",
                        1, 10, 5,
                        key=f"auto_{session_id}_{stagiaire_id}_{moment}_{comp['competence_id']}"
                    )

                    rows.append({
                        "auto_eval_id": generate_id(auto_evaluation, "auto_eval_id", "AE"),
                        "stagiaire_id": stagiaire_id,
                        "session_id": session_id,
                        "competence_id": comp["competence_id"],
                        "moment": moment,
                        "note": note,
                        "commentaire": "",
                    })

                commentaire = st.text_area("Remarques / commentaires")

                if st.button("Sauvegarder auto-évaluation"):
                    auto_evaluation = auto_evaluation[
                        ~(
                            (auto_evaluation["stagiaire_id"] == stagiaire_id) &
                            (auto_evaluation["session_id"] == session_id) &
                            (auto_evaluation["moment"] == moment)
                        )
                    ]

                    if rows:
                        rows[-1]["commentaire"] = commentaire

                    auto_evaluation = pd.concat(
                        [auto_evaluation, pd.DataFrame(rows)],
                        ignore_index=True
                    )
                    save_csv("auto_evaluation", auto_evaluation)
                    st.success("Auto-évaluation sauvegardée")

    st.dataframe(auto_evaluation, use_container_width=True)


# ============================================================
# Bilan formateur
# ============================================================

elif menu == "Bilan formateur":
    st.header("Bilan formateur")

    questions = [
        "Les objectifs de la formation pour les stagiaires ont-ils été atteints ?",
        "Le temps alloué à la formation est suffisant ?",
        "Ustensiles et matériels mis à disposition satisfaisants ?",
        "Ingrédients mis à disposition satisfaisants ?",
        "Ambiance",
    ]

    if sessions.empty:
        st.warning("Crée d'abord une session.")
    else:
        session_label = st.selectbox(
            "Session",
            sessions["session_id"] + " - " + sessions["nom"]
        )
        session_id = session_label.split(" - ")[0]
        session = sessions[sessions["session_id"] == session_id].iloc[0]
        formateur_id = session["formateur_id"]

        rows = []

        for question in questions:
            note = st.slider(question, 1, 10, 7, key=f"bf_{session_id}_{question}")
            rows.append({
                "bilan_id": generate_id(bilan_formateur, "bilan_id", "BF"),
                "formateur_id": formateur_id,
                "session_id": session_id,
                "rubrique": question,
                "note": note,
                "reponse": "",
                "commentaire": "",
                "date": date.today(),
            })

        remarques = st.text_area("Remarques / Commentaires")
        ameliorations = st.text_area("Ce qui aurait pu être amélioré / actions à inclure au plan d'action")
        autres = st.text_area("Autres remarques")

        if st.button("Sauvegarder bilan formateur"):
            extra_rows = [
                ("Remarques / Commentaires", remarques),
                ("Améliorations / plan d'action", ameliorations),
                ("Autres remarques", autres),
            ]

            for rubrique, commentaire in extra_rows:
                rows.append({
                    "bilan_id": generate_id(bilan_formateur, "bilan_id", "BF"),
                    "formateur_id": formateur_id,
                    "session_id": session_id,
                    "rubrique": rubrique,
                    "note": "",
                    "reponse": "",
                    "commentaire": commentaire,
                    "date": date.today(),
                })

            bilan_formateur = bilan_formateur[bilan_formateur["session_id"] != session_id]
            bilan_formateur = pd.concat([bilan_formateur, pd.DataFrame(rows)], ignore_index=True)
            save_csv("bilan_formateur", bilan_formateur)
            st.success("Bilan formateur sauvegardé")

    st.dataframe(bilan_formateur, use_container_width=True)


# Documents → redirigé vers pages/2_Documents.py


# ============================================================
# Qualiopi
# ============================================================

elif menu == "Qualiopi":
    st.header("Checklist Qualiopi par session")

    checks_base = [
        "Programme complet",
        "Objectifs pédagogiques renseignés",
        "Prérequis indiqués",
        "Modalités d'évaluation prévues",
        "Accessibilité handicap renseignée",
        "Émargement prévu",
        "Évaluation satisfaction prévue",
        "Auto-évaluation prévue",
        "Bilan formateur prévu",
        "Certificat de réalisation prévu",
        "Réclamations suivies",
        "Amélioration continue documentée",
    ]

    if sessions.empty:
        st.warning("Crée d'abord une session.")
    else:
        session_label = st.selectbox(
            "Session",
            sessions["session_id"] + " - " + sessions["nom"]
        )
        session_id = session_label.split(" - ")[0]
        current = qualiopi[qualiopi["session_id"] == session_id]

        updated_rows = []

        for element in checks_base:
            existing = current[current["element"] == element]
            default = False if existing.empty else bool_value(existing["fait"].iloc[0])

            fait = st.checkbox(
                element,
                value=default,
                key=f"qual_{session_id}_{element}"
            )

            updated_rows.append({
                "check_id": generate_id(qualiopi, "check_id", "Q"),
                "session_id": session_id,
                "element": element,
                "fait": str(fait),
            })

        if st.button("Sauvegarder checklist Qualiopi"):
            qualiopi = qualiopi[qualiopi["session_id"] != session_id]
            qualiopi = pd.concat([qualiopi, pd.DataFrame(updated_rows)], ignore_index=True)
            save_csv("qualiopi", qualiopi)
            st.success("Checklist sauvegardée")

        done = sum(1 for row in updated_rows if row["fait"] == "True")
        score = int(done / len(updated_rows) * 100)
        st.metric("Score Qualiopi session", f"{score} %")


# ============================================================
# BPF
# ============================================================

elif menu == "BPF":
    st.header("BPF - Bilan pédagogique et financier")

    if sessions.empty:
        st.warning("Aucune session.")
    else:
        recap = sessions.copy()

        if not stagiaires.empty:
            counts = stagiaires.groupby("session_id").size().reset_index(name="nb_stagiaires")
            recap = recap.merge(counts, on="session_id", how="left")
            recap["nb_stagiaires"] = recap["nb_stagiaires"].fillna(0).astype(int)
        else:
            recap["nb_stagiaires"] = 0

        recap["prix_num"] = recap["prix"].apply(safe_float)
        recap["cout_num"] = recap["cout_prevu"].apply(safe_float)
        recap["marge_prevue"] = recap["prix_num"] - recap["cout_num"]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Sessions", len(recap))
        col2.metric("Stagiaires", int(recap["nb_stagiaires"].sum()))
        col3.metric("CA formation", f"{recap['prix_num'].sum():.0f} €")
        col4.metric("Marge prévue", f"{recap['marge_prevue'].sum():.0f} €")

        st.subheader("Détail par session")
        st.dataframe(recap, use_container_width=True)

        st.download_button(
            "Télécharger l'export BPF CSV",
            recap.to_csv(index=False, encoding="utf-8-sig"),
            "export_bpf.csv",
            "text/csv"
        )
