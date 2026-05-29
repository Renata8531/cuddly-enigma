import streamlit as st
import pandas as pd
from pathlib import Path

# ============================================================
# HOF - Administration & Import données
# pages/0_Administration.py
#
# Page d'admin pour importer en masse les référentiels,
# grilles d'évaluation et autres données de base.
# Utilisée rarement — à l'ouverture d'une nouvelle formation.
# ============================================================

DATA_DIR   = Path("data")
GRILLE_DIR = DATA_DIR / "grilles"
DATA_DIR.mkdir(exist_ok=True)
GRILLE_DIR.mkdir(exist_ok=True)

st.title("⚙️ Administration — Import des données de base")
st.caption("Page à utiliser lors de la création d'une nouvelle formation. "
           "Les données importées ici alimentent toutes les autres pages de HOF.")

# ── Fonctions ─────────────────────────────────────────────────

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

REF_COLS  = ["referentiel_id","code_rncp","intitule","niveau","metier","actif","source"]
COMP_COLS = ["competence_id","referentiel_id","epreuve","bloc","section",
             "code_competence","competence","famille","niveau","actif"]
GRL_COLS  = ["grille_id","referentiel_id","epreuve","competence_code","competence",
             "famille","critique","niveau_code","niveau_libelle","note_min","note_max","indicateur"]

referentiels = load(DATA_DIR / "referentiels.csv", REF_COLS)
competences  = load(DATA_DIR / "competences.csv",  COMP_COLS)

# ════════════════════════════════════════════════════════════
# ÉTAT ACTUEL
# ════════════════════════════════════════════════════════════

st.subheader("État actuel de la base")

c1, c2, c3 = st.columns(3)
c1.metric("Référentiels", len(referentiels))
c2.metric("Compétences",  len(competences))
c3.metric("Grilles d'évaluation", len(list(GRILLE_DIR.glob("grille_*.csv"))))

if not referentiels.empty:
    with st.expander("Voir les référentiels existants"):
        st.dataframe(
            referentiels[["code_rncp","intitule","niveau","metier","actif"]],
            use_container_width=True, hide_index=True,
        )

st.divider()

# ════════════════════════════════════════════════════════════
# IMPORT EN MASSE
# ════════════════════════════════════════════════════════════

st.subheader("📥 Importer les référentiels et grilles")
st.markdown(
    "Sélectionne **tous les CSV** du dossier `data/referentiels/` d'un coup. "
    "HOF détecte automatiquement si c'est un référentiel ou une grille d'évaluation."
)

uploaded_files = st.file_uploader(
    "Charger les CSV (sélection multiple possible)",
    type="csv",
    accept_multiple_files=True,
    key="admin_upload",
)

if uploaded_files:
    st.markdown(f"**{len(uploaded_files)} fichier(s) sélectionné(s)**")

    # Classer les fichiers
    refs_to_import  = []
    comps_to_import = []
    grilles_to_import = []
    unrecognized    = []

    for f in uploaded_files:
        try:
            for enc in ["utf-8-sig", "utf-8", "latin1"]:
                try:
                    df = pd.read_csv(f, dtype=str, encoding=enc).fillna("")
                    f.seek(0)
                    break
                except Exception:
                    f.seek(0)

            # Détecter le type de fichier par ses colonnes
            cols = set(df.columns)

            if "niveau_code" in cols and "indicateur" in cols:
                # C'est une grille d'évaluation
                grilles_to_import.append((f.name, df))

            elif "competence_id" in cols or "competence" in cols:
                # C'est un référentiel/compétences
                comps_to_import.append((f.name, df))

            else:
                unrecognized.append(f.name)

        except Exception as e:
            unrecognized.append(f"{f.name} (erreur: {e})")

    # Aperçu
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Référentiels/compétences", len(comps_to_import))
    col_b.metric("Grilles d'évaluation",     len(grilles_to_import))
    col_c.metric("Non reconnus",              len(unrecognized))

    if unrecognized:
        st.warning("Fichiers non reconnus : " + ", ".join(unrecognized))

    if comps_to_import or grilles_to_import:
        if st.button("🚀 Tout importer", type="primary", use_container_width=True):

            nb_refs_added  = 0
            nb_comps_added = 0
            nb_grilles     = 0
            errors         = []

            # ── Import référentiels + compétences ─────────────
            new_comps_frames = []

            for fname, df in comps_to_import:
                try:
                    if "referentiel_id" not in df.columns:
                        errors.append(f"{fname} : colonne 'referentiel_id' manquante")
                        continue

                    rncp_id = df["referentiel_id"].iloc[0]

                    # Créer l'entrée référentiel
                    intitule = df["intitule_ref"].iloc[0] if "intitule_ref" in df.columns else rncp_id
                    niveau   = df["niveau"].iloc[0]       if "niveau" in df.columns else ""
                    type_    = df["type"].iloc[0]         if "type" in df.columns else ""

                    if referentiels.empty or rncp_id not in referentiels["referentiel_id"].values:
                        new_ref = pd.DataFrame([{
                            "referentiel_id": rncp_id,
                            "code_rncp":      rncp_id,
                            "intitule":       intitule,
                            "niveau":         niveau,
                            "metier":         type_,
                            "actif":          "1",
                            "source":         "France Compétences",
                        }])
                        referentiels = pd.concat([referentiels, new_ref], ignore_index=True)
                        nb_refs_added += 1

                    # Préparer les compétences
                    comp_df = df.copy()
                    for c in COMP_COLS:
                        if c not in comp_df.columns:
                            comp_df[c] = ""
                    new_comps_frames.append(comp_df[COMP_COLS])
                    nb_comps_added += len(comp_df)

                except Exception as e:
                    errors.append(f"{fname} : {e}")

            # Fusionner toutes les compétences (remplacer les existantes par RNCP)
            if new_comps_frames:
                # Supprimer les anciennes compétences des RNCP importés
                rncp_ids_imported = [df["referentiel_id"].iloc[0]
                                     for _, df in comps_to_import
                                     if "referentiel_id" in df.columns]
                if not competences.empty:
                    competences_clean = competences[
                        ~competences["referentiel_id"].isin(rncp_ids_imported)
                    ].copy()
                else:
                    competences_clean = pd.DataFrame(columns=COMP_COLS)

                competences = pd.concat(
                    [competences_clean] + new_comps_frames,
                    ignore_index=True,
                )

            # Sauvegarder référentiels + compétences
            save(DATA_DIR / "referentiels.csv", referentiels)
            save(DATA_DIR / "competences.csv",  competences)

            # ── Import grilles d'évaluation ───────────────────
            for fname, df in grilles_to_import:
                try:
                    if "referentiel_id" not in df.columns:
                        errors.append(f"{fname} : colonne 'referentiel_id' manquante")
                        continue
                    rncp_id = df["referentiel_id"].iloc[0]
                    dest = GRILLE_DIR / f"grille_{rncp_id}.csv"
                    df.to_csv(dest, index=False, encoding="utf-8-sig")
                    nb_grilles += 1
                except Exception as e:
                    errors.append(f"{fname} : {e}")

            # ── Résultat ──────────────────────────────────────
            st.success(
                f"✅ Import terminé — "
                f"**{nb_refs_added}** référentiel(s) ajouté(s), "
                f"**{nb_comps_added}** compétence(s) importée(s), "
                f"**{nb_grilles}** grille(s) d'évaluation sauvegardée(s)"
            )
            for err in errors:
                st.error(f"❌ {err}")

            st.rerun()

st.divider()

# ════════════════════════════════════════════════════════════
# RESET (avec confirmation)
# ════════════════════════════════════════════════════════════

with st.expander("🗑️ Zone dangereuse — Réinitialisation"):
    st.warning("Ces actions suppriment des données. À utiliser avec précaution.")

    col_r1, col_r2 = st.columns(2)

    with col_r1:
        if st.button("🗑️ Vider les référentiels et compétences", use_container_width=True):
            if st.session_state.get("confirm_reset_ref"):
                save(DATA_DIR / "referentiels.csv", pd.DataFrame(columns=REF_COLS))
                save(DATA_DIR / "competences.csv",  pd.DataFrame(columns=COMP_COLS))
                st.session_state.pop("confirm_reset_ref", None)
                st.success("Référentiels et compétences vidés.")
                st.rerun()
            else:
                st.session_state["confirm_reset_ref"] = True
                st.error("Clique à nouveau pour confirmer la suppression.")

    with col_r2:
        if st.button("🗑️ Vider les grilles d'évaluation", use_container_width=True):
            if st.session_state.get("confirm_reset_grilles"):
                for f in GRILLE_DIR.glob("grille_*.csv"):
                    f.unlink()
                st.session_state.pop("confirm_reset_grilles", None)
                st.success("Grilles vidées.")
                st.rerun()
            else:
                st.session_state["confirm_reset_grilles"] = True
                st.error("Clique à nouveau pour confirmer.")
