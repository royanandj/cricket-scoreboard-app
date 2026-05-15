import sqlite3
from datetime import date
from pathlib import Path
import io
import zipfile

import pandas as pd
import streamlit as st

DB_PATH = Path("scoreboard.db")

st.set_page_config(page_title="Quick Cricket Scorebook", page_icon="🏏", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1rem; padding-bottom: 2rem; max-width: 1050px;}
    div[data-testid="stMetric"] {background: #f8f8f8; border-radius: 14px; padding: 12px;}
    .stButton>button {width: 100%; border-radius: 10px; height: 3rem; font-weight: 700;}
    .stDownloadButton>button {width: 100%; border-radius: 10px;}
    input, textarea, select {font-size: 16px !important;}
    @media (max-width: 768px) {
        .block-container {padding-left: .7rem; padding-right: .7rem;}
        div[data-testid="column"] {width: 100% !important; flex: unset;}
        .stDataFrame {font-size: 12px;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Database ----------
def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

conn = connect()
conn.execute("PRAGMA foreign_keys = ON")

conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        captain TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_date TEXT NOT NULL,
        competition TEXT DEFAULT '',
        venue TEXT DEFAULT '',
        overs_per_innings REAL NOT NULL,
        team1_id INTEGER NOT NULL,
        team2_id INTEGER NOT NULL,
        toss_winner_id INTEGER,
        elected TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Completed',
        winner_id INTEGER,
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(team1_id) REFERENCES teams(id),
        FOREIGN KEY(team2_id) REFERENCES teams(id),
        FOREIGN KEY(toss_winner_id) REFERENCES teams(id),
        FOREIGN KEY(winner_id) REFERENCES teams(id)
    );

    CREATE TABLE IF NOT EXISTS innings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL,
        innings_no INTEGER NOT NULL,
        batting_team_id INTEGER NOT NULL,
        bowling_team_id INTEGER NOT NULL,
        runs INTEGER NOT NULL,
        wickets INTEGER NOT NULL,
        overs REAL NOT NULL,
        extras INTEGER DEFAULT 0,
        fours INTEGER DEFAULT 0,
        sixes INTEGER DEFAULT 0,
        top_scorer TEXT DEFAULT '',
        best_bowler TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        FOREIGN KEY(match_id) REFERENCES matches(id) ON DELETE CASCADE,
        FOREIGN KEY(batting_team_id) REFERENCES teams(id),
        FOREIGN KEY(bowling_team_id) REFERENCES teams(id)
    );
    """
)
conn.commit()

# ---------- Helpers ----------
def q(sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)

def execute(sql, params=()):
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid

def team_df():
    return q("SELECT id, name, captain FROM teams ORDER BY name")

def team_options():
    df = team_df()
    return {r["name"]: int(r["id"]) for _, r in df.iterrows()}

def overs_to_balls(overs_value: float) -> int:
    """Converts cricket overs notation: 4.5 = 4 overs 5 balls = 29 balls."""
    whole = int(overs_value)
    balls = int(round((float(overs_value) - whole) * 10))
    if balls > 5:
        raise ValueError("Balls after decimal must be 0 to 5. Example: 4.5 means 4 overs and 5 balls.")
    return whole * 6 + balls

def balls_to_overs(balls: int) -> float:
    return round((balls // 6) + (balls % 6) / 10, 1)

def nrr_overs_for_innings(overs_value, wickets, max_overs):
    # If a team is all out, NRR uses full allotted overs, not actual balls faced.
    if int(wickets) >= 10:
        return float(max_overs)
    return float(overs_value)

def validate_innings(runs, wickets, overs, max_overs, label):
    if runs < 0:
        raise ValueError(f"{label}: runs cannot be negative.")
    if wickets < 0 or wickets > 10:
        raise ValueError(f"{label}: wickets must be between 0 and 10.")
    balls = overs_to_balls(overs)
    max_balls = overs_to_balls(max_overs)
    if balls < 0 or balls > max_balls:
        raise ValueError(f"{label}: overs cannot exceed match overs.")
    if wickets == 10 and balls == 0:
        raise ValueError(f"{label}: all out cannot have 0 overs.")
    return True

def get_standings():
    teams = q("SELECT id, name FROM teams ORDER BY name")
    innings_df = q("SELECT * FROM innings")
    matches = q("SELECT * FROM matches")

    rows = []
    for _, t in teams.iterrows():
        tid = int(t.id)
        team_matches = matches[((matches.team1_id == tid) | (matches.team2_id == tid)) & (matches.status == "Completed")]
        played = len(team_matches)
        won = len(team_matches[team_matches.winner_id == tid])
        tied = len(team_matches[team_matches.winner_id.isna()])
        lost = played - won - tied
        points = won * 2 + tied

        bat = innings_df[innings_df.batting_team_id == tid]
        bowl = innings_df[innings_df.bowling_team_id == tid]
        runs_for = int(bat.runs.sum()) if not bat.empty else 0
        runs_against = int(bowl.runs.sum()) if not bowl.empty else 0

        overs_for = 0.0
        overs_against = 0.0
        for _, inn in bat.iterrows():
            max_overs = float(matches.loc[matches.id == inn.match_id, "overs_per_innings"].iloc[0])
            overs_for += nrr_overs_for_innings(inn.overs, inn.wickets, max_overs)
        for _, inn in bowl.iterrows():
            max_overs = float(matches.loc[matches.id == inn.match_id, "overs_per_innings"].iloc[0])
            overs_against += nrr_overs_for_innings(inn.overs, inn.wickets, max_overs)

        rr_for = runs_for / overs_for if overs_for else 0
        rr_against = runs_against / overs_against if overs_against else 0
        nrr = rr_for - rr_against

        rows.append({
            "Team": t.name, "P": played, "W": won, "L": lost, "T/NR": tied, "Pts": points,
            "Runs For": runs_for, "Overs For": round(overs_for, 1),
            "Runs Against": runs_against, "Overs Against": round(overs_against, 1),
            "NRR": round(nrr, 3)
        })
    return pd.DataFrame(rows).sort_values(["Pts", "NRR", "W"], ascending=[False, False, False]).reset_index(drop=True)

def score_line(match_id):
    inn = q(
        """
        SELECT i.*, bt.name batting, bw.name bowling
        FROM innings i
        JOIN teams bt ON bt.id=i.batting_team_id
        JOIN teams bw ON bw.id=i.bowling_team_id
        WHERE match_id=? ORDER BY innings_no
        """, (match_id,)
    )
    parts = []
    for _, r in inn.iterrows():
        parts.append(f"{r.batting} {int(r.runs)}/{int(r.wickets)} ({r.overs} ov)")
    return "  |  ".join(parts)

# ---------- UI ----------
st.title("🏏 Quick Cricket Scorebook")
st.caption("Fast mobile-friendly scoring, match records, and automatic points table with NRR.")

with st.expander("➕ Add teams", expanded=False):
    c1, c2 = st.columns([2, 1])
    with c1:
        new_teams = st.text_area("Team names", placeholder="One team per line\nWarriors\nTitans\nStrikers")
    with c2:
        captain = st.text_input("Captain, optional")
        if st.button("Save teams"):
            names = [x.strip() for x in new_teams.splitlines() if x.strip()]
            saved = 0
            for name in names:
                try:
                    execute("INSERT OR IGNORE INTO teams(name, captain) VALUES (?, ?)", (name, captain))
                    saved += 1
                except Exception as e:
                    st.error(str(e))
            st.success(f"Saved {saved} team(s).")
            st.rerun()

teams_map = team_options()
if len(teams_map) < 2:
    st.info("Add at least two teams to start scoring matches.")
    st.stop()

page = st.radio("Menu", ["Score match", "Points table", "Match records", "Teams", "Backup"], horizontal=True)

# ---------- Score Match ----------
if page == "Score match":
    st.subheader("Score a match")
    st.write("Use cricket overs format: **4.5 = 4 overs and 5 balls**, not 4.5 decimal overs.")

    with st.form("match_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            competition = st.text_input("Competition", value="Office Cricket Tournament")
            mdate = st.date_input("Date", value=date.today())
            venue = st.text_input("Venue", placeholder="Ground / location")
            max_overs = st.number_input("Overs per innings", min_value=1.0, max_value=50.0, value=5.0, step=1.0)
        with c2:
            team1 = st.selectbox("Team 1", list(teams_map.keys()), key="t1")
            team2 = st.selectbox("Team 2", [x for x in teams_map.keys() if x != team1], key="t2")
            toss = st.selectbox("Toss won by", ["Not recorded", team1, team2])
            elected = st.selectbox("Elected to", ["", "Bat", "Bowl"])

        st.markdown("### Innings")
        i1, i2 = st.columns(2)
        with i1:
            st.markdown(f"**1st innings: {team1} batting**")
            t1_runs = st.number_input("Runs", 0, 999, 0, key="t1_runs")
            t1_wkts = st.number_input("Wickets", 0, 10, 0, key="t1_wkts")
            t1_overs = st.number_input("Overs", 0.0, float(max_overs), 0.0, step=0.1, key="t1_overs")
            t1_extras = st.number_input("Extras", 0, 200, 0, key="t1_extras")
            t1_top = st.text_input("Top scorer, optional", key="t1_top")
        with i2:
            st.markdown(f"**2nd innings: {team2} batting**")
            t2_runs = st.number_input("Runs", 0, 999, 0, key="t2_runs")
            t2_wkts = st.number_input("Wickets", 0, 10, 0, key="t2_wkts")
            t2_overs = st.number_input("Overs", 0.0, float(max_overs), 0.0, step=0.1, key="t2_overs")
            t2_extras = st.number_input("Extras", 0, 200, 0, key="t2_extras")
            t2_top = st.text_input("Top scorer, optional", key="t2_top")

        notes = st.text_area("Notes, optional", placeholder="Player of the match, key moment, dispute, substitute, etc.")
        submitted = st.form_submit_button("Save match")

    if submitted:
        try:
            if team1 == team2:
                raise ValueError("Choose two different teams.")
            validate_innings(t1_runs, t1_wkts, t1_overs, max_overs, team1)
            validate_innings(t2_runs, t2_wkts, t2_overs, max_overs, team2)
            winner = None
            if t1_runs > t2_runs:
                winner = teams_map[team1]
            elif t2_runs > t1_runs:
                winner = teams_map[team2]

            mid = execute(
                """
                INSERT INTO matches(match_date, competition, venue, overs_per_innings, team1_id, team2_id,
                toss_winner_id, elected, status, winner_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Completed', ?, ?)
                """,
                (str(mdate), competition, venue, float(max_overs), teams_map[team1], teams_map[team2],
                 None if toss == "Not recorded" else teams_map[toss], elected, winner, notes)
            )
            execute(
                """
                INSERT INTO innings(match_id, innings_no, batting_team_id, bowling_team_id, runs, wickets, overs, extras, top_scorer)
                VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)
                """,
                (mid, teams_map[team1], teams_map[team2], int(t1_runs), int(t1_wkts), float(t1_overs), int(t1_extras), t1_top)
            )
            execute(
                """
                INSERT INTO innings(match_id, innings_no, batting_team_id, bowling_team_id, runs, wickets, overs, extras, top_scorer)
                VALUES (?, 2, ?, ?, ?, ?, ?, ?, ?)
                """,
                (mid, teams_map[team2], teams_map[team1], int(t2_runs), int(t2_wkts), float(t2_overs), int(t2_extras), t2_top)
            )
            st.success("Match saved. Points table updated automatically.")
        except Exception as e:
            st.error(f"Could not save: {e}")

# ---------- Points Table ----------
elif page == "Points table":
    st.subheader("Points table")
    standings = get_standings()
    st.dataframe(standings, use_container_width=True, hide_index=True)
    st.download_button("Download points table CSV", standings.to_csv(index=False), "points_table.csv", "text/csv")

    if not standings.empty:
        top = standings.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Leader", top["Team"])
        c2.metric("Points", int(top["Pts"]))
        c3.metric("NRR", top["NRR"])

# ---------- Match Records ----------
elif page == "Match records":
    st.subheader("Match records")
    matches = q(
        """
        SELECT m.id, m.match_date Date, m.competition Competition, m.venue Venue,
               t1.name Team_1, t2.name Team_2, COALESCE(w.name, 'Tie/No result') Winner, m.notes Notes
        FROM matches m
        JOIN teams t1 ON t1.id=m.team1_id
        JOIN teams t2 ON t2.id=m.team2_id
        LEFT JOIN teams w ON w.id=m.winner_id
        ORDER BY m.match_date DESC, m.id DESC
        """
    )
    if matches.empty:
        st.info("No matches saved yet.")
    else:
        display = matches.copy()
        display["Score"] = display["id"].apply(score_line)
        st.dataframe(display.drop(columns=["id"]), use_container_width=True, hide_index=True)
        st.download_button("Download match records CSV", display.drop(columns=["id"]).to_csv(index=False), "match_records.csv", "text/csv")

        st.markdown("### Delete a wrongly entered match")
        delete_id = st.selectbox("Select match", display["id"].tolist(), format_func=lambda x: f"#{x} | {score_line(x)}")
        if st.button("Delete selected match"):
            execute("DELETE FROM matches WHERE id=?", (int(delete_id),))
            st.success("Deleted.")
            st.rerun()

# ---------- Teams ----------
elif page == "Teams":
    st.subheader("Teams")
    df = team_df()
    st.dataframe(df.drop(columns=["id"]), use_container_width=True, hide_index=True)
    st.download_button("Download teams CSV", df.drop(columns=["id"]).to_csv(index=False), "teams.csv", "text/csv")

    st.markdown("### Remove team")
    st.caption("Only possible if the team has no saved matches.")
    choice = st.selectbox("Team", df["name"].tolist())
    if st.button("Remove team"):
        try:
            execute("DELETE FROM teams WHERE id=?", (teams_map[choice],))
            st.success("Team removed.")
            st.rerun()
        except Exception:
            st.error("This team has match records, so it cannot be removed.")

# ---------- Backup ----------
else:
    st.subheader("Backup / Restore")
    st.write("Use this before and after tournament days, especially if you deploy on Streamlit Community Cloud.")

    db_file = Path(DB_PATH)
    if db_file.exists():
        st.download_button(
            "Download full database backup",
            db_file.read_bytes(),
            "scoreboard_backup.db",
            "application/octet-stream",
        )

    st.markdown("### Restore from backup")
    st.caption("Upload a previously downloaded scoreboard_backup.db file. This replaces the current database.")
    uploaded = st.file_uploader("Upload backup file", type=["db", "sqlite", "sqlite3"])
    if uploaded is not None:
        if st.button("Restore backup"):
            try:
                conn.close()
                db_file.write_bytes(uploaded.getvalue())
                st.success("Backup restored. Refresh the app once.")
            except Exception as e:
                st.error(f"Could not restore backup: {e}")

    st.markdown("### Quick safety tips")
    st.info("Download the backup after every few matches. If the app is redeployed or restarted, you can restore the latest backup in seconds.")
