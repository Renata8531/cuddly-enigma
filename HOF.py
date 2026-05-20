# HOF.py

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
import uuid

st.set_page_config(page_title="HOF - Gestion formation", layout="wide")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

FILES = {
    "sessions": DATA_DIR / "sessions.csv",
    "stagiaires": DATA_DIR / "stagiaires.csv",
    "emargements": DATA_DIR / "emargements.csv",
    "evaluations": DATA_DIR / "evaluations.csv",
    "qualiopi": DATA_DIR / "qualiopi_checks.csv",
    "bpf": DATA_DIR / "bpf.csv",
    "referenciels":DATA_DIR / "referenciels.csv"
    "formateur":DATA_DIR / "formateurs.csv"
}


def load_csv(name, columns):
    file = FILES[name]
    if file.exists():
        return pd.read_csv(file)
    return pd.DataFrame(columns=columns)


def save_csv(name, df):
    df.to_csv(FILES[name], index=False)


sessions = load_csv("sessions", [
    "session_id", "nom", "date_debut", "date_fin", "prix", "cout_prevu"
])

stagiaires = load_csv("stagiaires", [
    "stagiaire_id", "session_id", "nom", "email", "lien_unique"
])

emargements = load_csv("emargements", [
    "emargement_id", "stagiaire_id", "session_id", "date", "moment", "signature", "horodatage"
])

evaluations = load_csv("evaluations", [
    "evaluation_id", "stagiaire_id", "session_id", "type", "note", "commentaire", "horodatage"
])

qualiopi = load_csv("qualiopi", [
    "check_id", "session_id", "element", "fait"
])

bpf = load_csv("bpf", [
    "ligne_id", "session_id", "type", "libelle", "montant", "statut"
])

formateurs = load_csv("formateurs", [
    "formateur_id", "nom", "email", "specialite", "lien_unique"

])
referenciels=load_csv("referentiel_id", "code_rncp", "intitule", "niveau", "metier", "actif"
                      
])
st.title("HOF - Outil de gestion formation")

menu = st.sidebar.radio(
    "Menu",
    [
        "Sessions",
        "Stagiaires",
        "Émargement",
        "Évaluations",
        "Qualiopi",
        "Formateur"
        "Referenciels"
        "BFR",
        
    ]
)


if menu == "Sessions":
    st.header("Créer une session")

    with st.form("form_session"):
        nom = st.text_input("Nom de la formation")
        date_debut = st.date_input("Date de début")
        date_fin = st.date_input("Date de fin")
        prix = st.number_input("Prix vendu (€)", min_value=0.0)
        cout_prevu = st.number_input("Coût prévu (€)", min_value=0.0)

        submit = st.form_submit_button("Créer la session")

        if submit:
            new = {
                "session_id": generate_id(sessions, "S"),
                "nom": nom,
                "date_debut": date_debut,
                "date_fin": date_fin,
                "prix": prix,
                "cout_prevu": cout_prevu,
            }
            sessions = pd.concat([sessions, pd.DataFrame([new])], ignore_index=True)
            save_csv("sessions", sessions)
            st.success("Session créée")

    st.subheader("Sessions existantes")
    st.dataframe(sessions, use_container_width=True)


elif menu == "Stagiaires":
    st.header("Ajouter un stagiaire")

    if sessions.empty:
        st.warning("Crée d'abord une session.")
    else:
        session_label = st.selectbox("Session", sessions["nom"])
        session_id = sessions.loc[sessions["nom"] == session_label, "session_id"].iloc[0]

        with st.form("form_stagiaire"):
            nom = st.text_input("Nom du stagiaire")
            email = st.text_input("Email")
            submit = st.form_submit_button("Ajouter")

            if submit:
                lien_unique = str(uuid.uuid4())

                new = {
                    "stagiaire_id": generate_id(stagiaires, "ST"),
                    "session_id": session_id,
                    "nom": nom,
                    "email": email,
                    "lien_unique": lien_unique,
                }

                stagiaires = pd.concat([stagiaires, pd.DataFrame([new])], ignore_index=True)
                save_csv("stagiaires", stagiaires)
                st.success("Stagiaire ajouté")
                st.info(f"Lien unique futur : /?token={lien_unique}")

    st.subheader("Stagiaires")
    st.dataframe(stagiaires, use_container_width=True)


elif menu == "Émargement":
    st.header("Émargement numérique simple")

    if stagiaires.empty:
        st.warning("Ajoute d'abord des stagiaires.")
    else:
        stagiaire_label = st.selectbox("Stagiaire", stagiaires["nom"])
        stagiaire = stagiaires[stagiaires["nom"] == stagiaire_label].iloc[0]

        moment = st.selectbox("Moment", ["Matin", "Après-midi"])
        signature = st.text_input("Signature : taper nom/prénom")

        if st.button("Signer"):
            new = {
                "emargement_id": str(uuid.uuid4()),
                "stagiaire_id": stagiaire["stagiaire_id"],
                "session_id": stagiaire["session_id"],
                "date": datetime.now().date(),
                "moment": moment,
                "signature": signature,
                "horodatage": datetime.now().isoformat(timespec="seconds"),
            }

            emargements = pd.concat([emargements, pd.DataFrame([new])], ignore_index=True)
            save_csv("emargements", emargements)
            st.success("Émargement enregistré")

    st.subheader("Historique émargements")
    st.dataframe(emargements, use_container_width=True)


elif menu == "Évaluations":
    st.header("Évaluation en ligne")

    if stagiaires.empty:
        st.warning("Ajoute d'abord des stagiaires.")
    else:
        stagiaire_label = st.selectbox("Stagiaire", stagiaires["nom"])
        stagiaire = stagiaires[stagiaires["nom"] == stagiaire_label].iloc[0]

        type_eval = st.selectbox("Type d'évaluation", ["Début formation", "Fin formation", "À froid"])
        note = st.slider("Note / satisfaction", 0, 10, 5)
        commentaire = st.text_area("Commentaire")

        if st.button("Enregistrer l'évaluation"):
            new = {
                "evaluation_id": str(uuid.uuid4()),
                "stagiaire_id": stagiaire["stagiaire_id"],
                "session_id": stagiaire["session_id"],
                "type": type_eval,
                "note": note,
                "commentaire": commentaire,
                "horodatage": datetime.now().isoformat(timespec="seconds"),
            }

            evaluations = pd.concat([evaluations, pd.DataFrame([new])], ignore_index=True)
            save_csv("evaluations", evaluations)
            st.success("Évaluation enregistrée")

    st.subheader("Évaluations")
    st.dataframe(evaluations, use_container_width=True)


elif menu == "Qualiopi":
    st.header("Checklist Qualiopi par session")

    checks_base = [
        "Programme complet",
        "Objectifs pédagogiques renseignés",
        "Prérequis indiqués",
        "Modalités d'évaluation prévues",
        "Accessibilité handicap renseignée",
        "Émargement prévu",
        "Évaluation à chaud prévue",
        "Attestation prévue",
        "Réclamations suivies",
        "Amélioration continue documentée",
    ]

    if sessions.empty:
        st.warning("Crée d'abord une session.")
    else:
        session_label = st.selectbox("Session", sessions["nom"])
        session_id = sessions.loc[sessions["nom"] == session_label, "session_id"].iloc[0]

        current = qualiopi[qualiopi["session_id"] == session_id]

        updated_rows = []

        for element in checks_base:
            existing = current[current["element"] == element]
            default = False if existing.empty else bool(existing["fait"].iloc[0])

            fait = st.checkbox(element, value=default)

            updated_rows.append({
                "check_id": str(uuid.uuid4()),
                "session_id": session_id,
                "element": element,
                "fait": fait,
            })

        if st.button("Sauvegarder checklist Qualiopi"):
            qualiopi = qualiopi[qualiopi["session_id"] != session_id]
            qualiopi = pd.concat([qualiopi, pd.DataFrame(updated_rows)], ignore_index=True)
            save_csv("qualiopi", qualiopi)
            st.success("Checklist sauvegardée")

        done = sum(row["fait"] for row in updated_rows)
        score = int(done / len(updated_rows) * 100)
        st.metric("Score Qualiopi session", f"{score} %")


elif menu == "BFR":
    st.header("BFR / Trésorerie simplifiée")

    if sessions.empty:
        st.warning("Crée d'abord une session.")
    else:
        session_label = st.selectbox("Session", sessions["nom"])
        session_id = sessions.loc[sessions["nom"] == session_label, "session_id"].iloc[0]

        with st.form("form_bfr"):
            type_ligne = st.selectbox("Type", ["Encaissement", "Décaissement"])
            libelle = st.text_input("Libellé")
            montant = st.number_input("Montant (€)", min_value=0.0)
            statut = st.selectbox("Statut", ["Prévu", "Réalisé", "En retard"])

            submit = st.form_submit_button("Ajouter ligne BFR")

            if submit:
                new = {
                    "ligne_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "type": type_ligne,
                    "libelle": libelle,
                    "montant": montant,
                    "statut": statut,
                }

                bfr = pd.concat([bfr, pd.DataFrame([new])], ignore_index=True)
                save_csv("bfr", bfr)
                st.success("Ligne ajoutée")

        current_bfr = bfr[bfr["session_id"] == session_id]

        encaissements = current_bfr[current_bfr["type"] == "Encaissement"]["montant"].sum()
        decaissements = current_bfr[current_bfr["type"] == "Décaissement"]["montant"].sum()
        solde = encaissements - decaissements

        col1, col2, col3 = st.columns(3)
        col1.metric("Encaissements", f"{encaissements:.0f} €")
        col2.metric("Décaissements", f"{decaissements:.0f} €")
        col3.metric("Solde prévisionnel", f"{solde:.0f} €")

        st.subheader("Détail BFR")
        st.dataframe(current_bfr, use_container_width=True)
