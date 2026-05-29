import streamlit as st
import pandas as pd
from pathlib import Path
import calendar
from datetime import date, timedelta

# ============================================================
# HOF - Calendrier des formations
# Page séparée — vue mensuelle
# ============================================================


DATA_DIR = Path("data")

# ── Chargement ───────────────────────────────────────────────

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

sessions   = load(DATA_DIR / "sessions.csv",
                  ["session_id","programme_id","formateur_id","nom",
                   "date_debut","date_fin","prix","cout_prevu"])
stagiaires = load(DATA_DIR / "stagiaires.csv",
                  ["stagiaire_id","session_id","nom","email","entreprise","lien_unique"])
formateurs = load(DATA_DIR / "formateurs.csv",
                  ["formateur_id","nom","email","specialite","lien_unique"])

# ── Helpers ──────────────────────────────────────────────────

def statut(row, today):
    try:
        d = pd.to_datetime(row["date_debut"]).date()
        f = pd.to_datetime(row["date_fin"]).date()
    except Exception:
        return "Inconnue"
    if today < d:
        return "Prévue"
    elif d <= today <= f:
        return "En cours"
    else:
        return "Terminée"

STATUT_COLOR = {
    "Prévue":    "#3B82F6",   # bleu
    "En cours":  "#10B981",   # vert
    "Terminée":  "#9CA3AF",   # gris
}

# ── Enrichissement sessions ───────────────────────────────────

today = date.today()

if not sessions.empty:
    sessions["date_debut_dt"] = pd.to_datetime(sessions["date_debut"], errors="coerce")
    sessions["date_fin_dt"]   = pd.to_datetime(sessions["date_fin"],   errors="coerce")
    sessions["statut"]        = sessions.apply(lambda r: statut(r, today), axis=1)
    sessions["nb_stagiaires"] = sessions["session_id"].apply(
        lambda sid: len(stagiaires[stagiaires["session_id"] == sid])
        if not stagiaires.empty else 0
    )

# ── Interface ─────────────────────────────────────────────────

st.title("📅 Calendrier des formations")

if sessions.empty:
    st.warning("Aucune session trouvée. Vérifie que le dossier `data/` est accessible.")
    st.stop()

# Navigation mois
col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
if "cal_year"  not in st.session_state: st.session_state.cal_year  = today.year
if "cal_month" not in st.session_state: st.session_state.cal_month = today.month

with col_nav1:
    if st.button("◀ Mois précédent"):
        if st.session_state.cal_month == 1:
            st.session_state.cal_month = 12
            st.session_state.cal_year -= 1
        else:
            st.session_state.cal_month -= 1

with col_nav3:
    if st.button("Mois suivant ▶"):
        if st.session_state.cal_month == 12:
            st.session_state.cal_month = 1
            st.session_state.cal_year += 1
        else:
            st.session_state.cal_month += 1

with col_nav2:
    st.markdown(
        f"<h2 style='text-align:center;margin:0'>"
        f"{calendar.month_name[st.session_state.cal_month].capitalize()} "
        f"{st.session_state.cal_year}</h2>",
        unsafe_allow_html=True,
    )

year  = st.session_state.cal_year
month = st.session_state.cal_month

# Sessions qui touchent ce mois
month_start = date(year, month, 1)
month_end   = date(year, month, calendar.monthrange(year, month)[1])

visible = sessions[
    (sessions["date_debut_dt"].dt.date <= month_end) &
    (sessions["date_fin_dt"].dt.date   >= month_start)
].copy()

# ── Légende ──────────────────────────────────────────────────

st.markdown("&nbsp;", unsafe_allow_html=True)
leg_cols = st.columns(3)
for i, (s, c) in enumerate(STATUT_COLOR.items()):
    leg_cols[i].markdown(
        f"<span style='background:{c};border-radius:4px;"
        f"padding:2px 10px;color:white;font-size:0.85rem'>{s}</span>",
        unsafe_allow_html=True,
    )
st.markdown("---")

# ── Grille calendrier ─────────────────────────────────────────

JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

# En-têtes colonnes
header_cols = st.columns(7)
for i, j in enumerate(JOURS):
    header_cols[i].markdown(
        f"<div style='text-align:center;font-weight:700;"
        f"font-size:0.9rem;color:#6B7280;padding-bottom:4px'>{j}</div>",
        unsafe_allow_html=True,
    )

# Calcul des semaines
cal = calendar.monthcalendar(year, month)   # liste de semaines [lun..dim]

for week in cal:
    week_cols = st.columns(7)
    for col_idx, day_num in enumerate(week):
        cell = week_cols[col_idx]
        if day_num == 0:
            cell.markdown(
                "<div style='min-height:90px'></div>",
                unsafe_allow_html=True,
            )
            continue

        current_date = date(year, month, day_num)
        is_today = (current_date == today)
        is_weekend = col_idx >= 5

        # Trouver les sessions actives ce jour
        day_sessions = visible[
            (visible["date_debut_dt"].dt.date <= current_date) &
            (visible["date_fin_dt"].dt.date   >= current_date)
        ]

        # Style de la cellule
        bg = "#FEF3C7" if is_today else ("#F9FAFB" if not is_weekend else "#F3F4F6")
        border = "2px solid #F59E0B" if is_today else "1px solid #E5E7EB"

        html = (
            f"<div style='background:{bg};border:{border};border-radius:8px;"
            f"padding:6px;min-height:90px;'>"
            f"<div style='font-weight:{'700' if is_today else '500'};"
            f"font-size:0.9rem;color:{'#D97706' if is_today else '#374151'}"
            f";margin-bottom:4px'>{day_num}</div>"
        )

        for _, s in day_sessions.iterrows():
            color = STATUT_COLOR.get(s["statut"], "#9CA3AF")
            nb    = s["nb_stagiaires"]
            nom   = s["nom"][:22] + "…" if len(s["nom"]) > 22 else s["nom"]
            html += (
                f"<div style='background:{color};color:white;border-radius:4px;"
                f"padding:2px 5px;margin-bottom:3px;font-size:0.72rem;"
                f"line-height:1.3;word-break:break-word'>"
                f"<b>{nom}</b><br>"
                f"👤 {nb} stagiaire{'s' if nb > 1 else ''} · {s['statut']}"
                f"</div>"
            )

        html += "</div>"
        cell.markdown(html, unsafe_allow_html=True)

# ── Détail du mois ────────────────────────────────────────────

st.markdown("---")
st.subheader(f"Sessions de {calendar.month_name[month]} {year}")

if visible.empty:
    st.info("Aucune formation ce mois-ci.")
else:
    for _, s in visible.sort_values("date_debut_dt").iterrows():
        color = STATUT_COLOR.get(s["statut"], "#9CA3AF")
        nb    = s["nb_stagiaires"]
        debut = s["date_debut_dt"].strftime("%d/%m/%Y") if pd.notna(s["date_debut_dt"]) else "?"
        fin   = s["date_fin_dt"].strftime("%d/%m/%Y")   if pd.notna(s["date_fin_dt"])   else "?"

        with st.expander(f"**{s['nom']}** — {debut} → {fin}"):
            c1, c2, c3 = st.columns(3)
            c1.markdown(
                f"<span style='background:{color};color:white;border-radius:4px;"
                f"padding:3px 10px'>{s['statut']}</span>",
                unsafe_allow_html=True,
            )
            c2.metric("Stagiaires inscrits", nb)
            c3.metric("Session ID", s["session_id"])

# ── Résumé stats ─────────────────────────────────────────────

st.markdown("---")
st.subheader("Vue d'ensemble")

total   = len(sessions)
prevues  = len(sessions[sessions["statut"] == "Prévue"])
en_cours = len(sessions[sessions["statut"] == "En cours"])
terminees= len(sessions[sessions["statut"] == "Terminée"])

s1, s2, s3, s4 = st.columns(4)
s1.metric("Total sessions", total)
s2.metric("🔵 Prévues",    prevues)
s3.metric("🟢 En cours",   en_cours)
s4.metric("⚫ Terminées",  terminees)
