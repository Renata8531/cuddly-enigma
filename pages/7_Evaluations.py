import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date
import uuid

# ============================================================
# HOF - Évaluations des compétences par grille officielle
# pages/7_Evaluations.py
#
# Lien entre :
#   data/competences.csv      (référentiel : quoi évaluer)
#   data/grilles/             (critères DEB/EXE/OPE/EXC)
#   data/evaluations.csv      (résultats par stagiaire)
# ============================================================

DATA_DIR   = Path("data")
GRILLE_DIR = Path("data") / "grilles"
GRILLE_DIR.mkdir(exist_ok=True)

NIVEAUX = {
    "DEB": {"libelle": "Débutant",     "note_min": 0,  "note_max": 4.5,  "color": "#EF4444"},
    "EXE": {"libelle": "Exécution",    "note_min": 5,  "note_max": 9.5,  "color": "#F97316"},
    "OPE": {"libelle": "Opérationnel", "note_min": 10, "note_max": 14.5, "color": "#22C55E"},
    "EXC": {"libelle": "Excellent",    "note_min": 15, "note_max": 20,   "color": "#3B82F6"},
}

# ── Chargement ────────────────────────────────────────────────

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

def load_grille(referentiel_id: str) -> pd.DataFrame:
    path = GRILLE_DIR / f"grille_{referentiel_id}.csv"
    if not path.exists():
        return pd.DataFrame()
    return load(path, ["grille_id","referentiel_id","epreuve","competence_code",
                        "competence","famille","critique","niveau_code",
                        "niveau_libelle","note_min","note_max","indicateur"])

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
evaluations = load(DATA_DIR / "evaluations.csv",
                   ["evaluation_id","stagiaire_id","session_id","competence_code",
                    "epreuve","niveau_code","note","commentaire","horodatage"])

# ── Helpers ───────────────────────────────────────────────────

def fmt_date(s):
    try:
        return pd.to_datetime(s).strftime("%d/%m/%Y")
    except Exception:
        return str(s)

def get(df, id_col, val, target_col, fallback=""):
    r = df[df[id_col] == val]
    return str(r.iloc[0][target_col]) if not r.empty else fallback

def note_from_niveau(niveau_code: str) -> float:
    n = NIVEAUX.get(niveau_code, {})
    return (n.get("note_min", 0) + n.get("note_max", 0)) / 2

def niveau_badge(code: str) -> str:
    n = NIVEAUX.get(code, {})
    color = n.get("color", "#9CA3AF")
    label = n.get("libelle", code)
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.8rem;font-weight:bold">{code} — {label}</span>'

# ════════════════════════════════════════════════════════════
# INTERFACE
# ════════════════════════════════════════════════════════════

st.title("📊 Évaluations des compétences")

if sessions.empty:
    st.warning("Aucune session disponible.")
    st.stop()

# ── Sidebar : importer grilles ────────────────────────────────
with st.sidebar:
    st.header("📁 Grilles d'évaluation")
    st.caption("Importe les grilles depuis /evaluations/")
    grilles_dispo = list(GRILLE_DIR.glob("grille_*.csv"))
    if grilles_dispo:
        for g in sorted(grilles_dispo):
            rncp = g.stem.replace("grille_", "")
            st.success(f"✅ {rncp}")
    else:
        st.warning("Aucune grille chargée")

    up = st.file_uploader("Importer une grille CSV", type="csv", key="grille_up")
    if up:
        dest = GRILLE_DIR / up.name
        dest.write_bytes(up.read())
        st.success(f"✅ {up.name} importée")
        st.rerun()

    st.divider()
    st.caption("Niveaux officiels")
    for code, n in NIVEAUX.items():
        st.markdown(
            f'<span style="background:{n["color"]};color:white;padding:2px 6px;'
            f'border-radius:3px;font-size:0.75rem">{code}</span> '
            f'{n["libelle"]} ({n["note_min"]}–{n["note_max"]}/20)',
            unsafe_allow_html=True,
        )

# ── Sélection session + stagiaire ─────────────────────────────
col1, col2 = st.columns(2)

with col1:
    sess_label = st.selectbox("Session", sessions["session_id"] + " — " + sessions["nom"])
    session_id = sess_label.split(" — ")[0]
    session_row = sessions[sessions["session_id"] == session_id].iloc[0]
    programme_id = session_row["programme_id"]

with col2:
    stag_sess = stagiaires[stagiaires["session_id"] == session_id] \
                if not stagiaires.empty else pd.DataFrame()
    if stag_sess.empty:
        st.warning("Aucun stagiaire dans cette session.")
        st.stop()
    stag_label = st.selectbox("Stagiaire", stag_sess["stagiaire_id"] + " — " + stag_sess["nom"])
    stag_id = stag_label.split(" — ")[0]
    stag_row = stag_sess[stag_sess["stagiaire_id"] == stag_id].iloc[0]

# Référentiel de la session
referentiel_id = get(programmes, "programme_id", programme_id, "referentiel_id", "")
grille = load_grille(referentiel_id)

st.info(
    f"**{stag_row['nom']}** | {session_row['nom']} | "
    f"{fmt_date(session_row['date_debut'])} → {fmt_date(session_row['date_fin'])} | "
    f"Référentiel : **{referentiel_id or '—'}**"
)

if grille.empty:
    st.warning(
        f"Aucune grille d'évaluation pour le référentiel **{referentiel_id}**. "
        f"Importe le fichier `grille_{referentiel_id}.csv` dans la sidebar."
    )
    st.stop()

st.divider()

# ── Onglets ───────────────────────────────────────────────────
tabs = st.tabs(["✏️ Évaluer", "📊 Résultats", "📋 Historique session"])

# ════════════════════════════════════════════════════════════
# ONGLET 1 : ÉVALUER
# ════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader(f"Évaluation — {stag_row['nom']}")

    epreuves = grille["epreuve"].unique().tolist()
    ep_tabs = st.tabs(epreuves)

    nouvelles_evals = []

    for ep_idx, epreuve in enumerate(epreuves):
        with ep_tabs[ep_idx]:
            criteres_ep = grille[grille["epreuve"] == epreuve]
            codes = criteres_ep["competence_code"].unique().tolist()

            # Évals existantes pour ce stagiaire/session/épreuve
            evals_exist = evaluations[
                (evaluations["stagiaire_id"] == stag_id) &
                (evaluations["session_id"]   == session_id) &
                (evaluations["epreuve"]      == epreuve)
            ] if not evaluations.empty else pd.DataFrame()

            st.markdown(f"**{len(codes)} critères à évaluer**")

            for code in codes:
                critere_rows = criteres_ep[criteres_ep["competence_code"] == code]
                if critere_rows.empty:
                    continue
                competence_label = critere_rows.iloc[0]["competence"]
                famille          = critere_rows.iloc[0]["famille"]
                critique         = critere_rows.iloc[0]["critique"] == "1"

                # Valeur actuelle
                eval_exist = evals_exist[evals_exist["competence_code"] == code]
                current_niv = eval_exist.iloc[0]["niveau_code"] if not eval_exist.empty else "OPE"

                st.markdown("---")
                badge_critique = " 🔴 **CRITIQUE**" if critique else ""
                st.markdown(f"**{code}** — {competence_label}{badge_critique}  "
                            f"`{famille}`")

                # Afficher les indicateurs de chaque niveau
                with st.expander("📋 Descripteurs de niveau"):
                    cols = st.columns(4)
                    for i, (niv_code, niv_data) in enumerate(NIVEAUX.items()):
                        ind_row = critere_rows[critere_rows["niveau_code"] == niv_code]
                        ind_txt = ind_row.iloc[0]["indicateur"] if not ind_row.empty else "—"
                        cols[i].markdown(
                            f'<div style="background:{niv_data["color"]}20;border-left:3px solid '
                            f'{niv_data["color"]};padding:6px;border-radius:4px;font-size:0.8rem">'
                            f'<b style="color:{niv_data["color"]}">{niv_code}</b><br>{ind_txt}</div>',
                            unsafe_allow_html=True,
                        )

                # Sélection du niveau
                sel_niv = st.radio(
                    f"Niveau — {code}",
                    options=["DEB", "EXE", "OPE", "EXC"],
                    index=["DEB","EXE","OPE","EXC"].index(current_niv),
                    horizontal=True,
                    key=f"eval_{session_id}_{stag_id}_{epreuve}_{code}",
                    format_func=lambda x: f"{x} — {NIVEAUX[x]['libelle']}",
                )
                commentaire = st.text_input(
                    f"Commentaire (optionnel)",
                    value=eval_exist.iloc[0]["commentaire"] if not eval_exist.empty else "",
                    key=f"com_{session_id}_{stag_id}_{epreuve}_{code}",
                    placeholder="Observation sur la prestation...",
                )

                nouvelles_evals.append({
                    "evaluation_id":   f"EV{uuid.uuid4().hex[:8].upper()}",
                    "stagiaire_id":    stag_id,
                    "session_id":      session_id,
                    "competence_code": code,
                    "epreuve":         epreuve,
                    "niveau_code":     sel_niv,
                    "note":            str(note_from_niveau(sel_niv)),
                    "commentaire":     commentaire,
                    "horodatage":      "",
                })

    # Bouton enregistrer
    st.divider()
    if st.button("💾 Enregistrer toutes les évaluations", type="primary", use_container_width=True):
        now = pd.Timestamp.now().isoformat(timespec="seconds")
        for e in nouvelles_evals:
            e["horodatage"] = now

        # Supprimer les anciennes évals pour ce stagiaire/session
        if not evaluations.empty:
            existing_mask = (
                (evaluations["stagiaire_id"] == stag_id) &
                (evaluations["session_id"]   == session_id)
            )
            evaluations_clean = evaluations[~existing_mask].copy()
        else:
            evaluations_clean = pd.DataFrame(columns=list(nouvelles_evals[0].keys()))

        all_evals = pd.concat(
            [evaluations_clean, pd.DataFrame(nouvelles_evals)],
            ignore_index=True,
        )
        save(DATA_DIR / "evaluations.csv", all_evals)
        evaluations = all_evals
        st.success(f"✅ {len(nouvelles_evals)} évaluations enregistrées")
        st.rerun()


# ════════════════════════════════════════════════════════════
# ONGLET 2 : RÉSULTATS
# ════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader(f"Résultats — {stag_row['nom']}")

    evals_stag = evaluations[
        (evaluations["stagiaire_id"] == stag_id) &
        (evaluations["session_id"]   == session_id)
    ] if not evaluations.empty else pd.DataFrame()

    if evals_stag.empty:
        st.info("Aucune évaluation enregistrée pour ce stagiaire.")
    else:
        # Profil de compétences par épreuve
        for epreuve in evals_stag["epreuve"].unique():
            st.markdown(f"#### {epreuve}")
            ep_evals = evals_stag[evals_stag["epreuve"] == epreuve]

            rows = []
            has_bloquant = False
            for _, ev in ep_evals.iterrows():
                n = NIVEAUX.get(ev["niveau_code"], {})
                comp_label = get(grille[grille["competence_code"] == ev["competence_code"]],
                                  "competence_code", ev["competence_code"], "competence",
                                  ev["competence_code"])
                crit_row = grille[grille["competence_code"] == ev["competence_code"]]
                is_critique = not crit_row.empty and crit_row.iloc[0]["critique"] == "1"
                if ev["niveau_code"] == "DEB" and is_critique:
                    has_bloquant = True
                rows.append({
                    "Critère":    ev["competence_code"],
                    "Compétence": comp_label[:60] + "…" if len(comp_label) > 60 else comp_label,
                    "Niveau":     ev["niveau_code"],
                    "Note /20":   float(ev["note"]) if ev["note"] else note_from_niveau(ev["niveau_code"]),
                    "Commentaire":ev["commentaire"],
                })

            df_res = pd.DataFrame(rows)

            # Colorier les niveaux
            def color_niveau(val):
                n = NIVEAUX.get(str(val), {})
                c = n.get("color", "#9CA3AF")
                return f"background-color:{c}30;color:{c};font-weight:bold"

            st.dataframe(
                df_res.style.applymap(color_niveau, subset=["Niveau"]),
                use_container_width=True,
                hide_index=True,
            )

            # Moyenne épreuve
            moy = df_res["Note /20"].mean()
            col1, col2, col3 = st.columns(3)
            col1.metric("Moyenne épreuve", f"{moy:.1f}/20")
            col2.metric("Niveau global", "OPE" if moy >= 10 else "EXE" if moy >= 5 else "DEB")
            if has_bloquant:
                col3.markdown(
                    '<div style="background:#FEE2E2;border:1px solid #EF4444;border-radius:6px;'
                    'padding:8px;color:#991B1B;font-size:0.85rem">⛔ Critère CRITIQUE à DEB<br>'
                    '<b>Moyenne EP < 10 automatique</b></div>',
                    unsafe_allow_html=True,
                )
            else:
                col3.metric("Statut", "✅ Validé" if moy >= 10 else "⚠️ En dessous de la moyenne")

            st.markdown("")

        # Bilan global
        st.divider()
        st.subheader("Bilan global")
        moy_globale = evals_stag["note"].astype(float).mean()
        nb_exc = len(evals_stag[evals_stag["niveau_code"] == "EXC"])
        nb_ope = len(evals_stag[evals_stag["niveau_code"] == "OPE"])
        nb_exe = len(evals_stag[evals_stag["niveau_code"] == "EXE"])
        nb_deb = len(evals_stag[evals_stag["niveau_code"] == "DEB"])

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Moyenne générale", f"{moy_globale:.1f}/20")
        c2.metric("🔵 EXC", nb_exc)
        c3.metric("🟢 OPE", nb_ope)
        c4.metric("🟠 EXE", nb_exe)
        c5.metric("🔴 DEB", nb_deb)


# ════════════════════════════════════════════════════════════
# ONGLET 3 : HISTORIQUE SESSION
# ════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader(f"Résultats de toute la session — {session_row['nom']}")

    if evaluations.empty:
        st.info("Aucune évaluation enregistrée pour cette session.")
    else:
        evals_sess = evaluations[evaluations["session_id"] == session_id].copy()
        if evals_sess.empty:
            st.info("Aucune évaluation pour cette session.")
        else:
            # Tableau récap : stagiaire x épreuve → moyenne + niveau global
            recap_rows = []
            for _, stag in stag_sess.iterrows():
                ev_stag = evals_sess[evals_sess["stagiaire_id"] == stag["stagiaire_id"]]
                if ev_stag.empty:
                    recap_rows.append({
                        "Stagiaire": stag["nom"],
                        "Nb critères": 0,
                        "Moyenne /20": "—",
                        "Niveau global": "—",
                        "EXC": 0, "OPE": 0, "EXE": 0, "DEB": 0,
                    })
                else:
                    moy = ev_stag["note"].astype(float).mean()
                    recap_rows.append({
                        "Stagiaire":    stag["nom"],
                        "Nb critères":  len(ev_stag),
                        "Moyenne /20":  f"{moy:.1f}",
                        "Niveau global":"OPE" if moy >= 10 else "EXE" if moy >= 5 else "DEB",
                        "EXC": len(ev_stag[ev_stag["niveau_code"] == "EXC"]),
                        "OPE": len(ev_stag[ev_stag["niveau_code"] == "OPE"]),
                        "EXE": len(ev_stag[ev_stag["niveau_code"] == "EXE"]),
                        "DEB": len(ev_stag[ev_stag["niveau_code"] == "DEB"]),
                    })

            df_recap = pd.DataFrame(recap_rows)

            def color_global(val):
                colors = {"OPE":"#22C55E30", "EXE":"#F9731630", "DEB":"#EF444430", "EXC":"#3B82F630"}
                return f"background-color:{colors.get(str(val), '#F3F4F6')};font-weight:bold"

            st.dataframe(
                df_recap.style.applymap(color_global, subset=["Niveau global"]),
                use_container_width=True,
                hide_index=True,
            )

            # Export CSV
            csv = df_recap.to_csv(index=False, encoding="utf-8-sig").encode()
            st.download_button(
                "⬇️ Exporter les résultats",
                data=csv,
                file_name=f"resultats_{session_id}.csv",
                mime="text/csv",
            )
