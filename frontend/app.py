import streamlit as st
import requests
import pandas as pd
import os
import time

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000/api")
ADMIN_TOKEN = os.environ.get("ADMIN_API_TOKEN", "")

st.set_page_config(page_title="AI Journalist — Dashboard", layout="wide")
st.title("📰 AI Journalist")

tab = st.sidebar.selectbox("View", ["Mentions", "Operations"])

# --- Shared function to fetch mentions ---
@st.cache_data(ttl=60)
def fetch_mentions():
    try:
        r = requests.get(f"{API_BASE}/mentions", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Failed to fetch mentions: {e}")
        return []

# --- Mentions tab ---
if tab == "Mentions":
    mentions = fetch_mentions()
    if not mentions:
        st.info("No mentions found.")
        st.stop()

    df = pd.DataFrame(mentions)

    # Sidebar filters
    st.sidebar.header("Filters")
    sentiment_options = sorted(df['sentiment'].dropna().unique())
    sentiment = st.sidebar.multiselect("Sentiment", options=sentiment_options, default=sentiment_options)
    source_q = st.sidebar.text_input("Source contains (substring)", "")
    query = st.sidebar.text_input("Search title/summary", "")

    filtered = df.copy()
    if sentiment:
        filtered = filtered[filtered['sentiment'].isin(sentiment)]
    if source_q:
        filtered = filtered[filtered['source'].str.contains(source_q, case=False, na=False)]
    if query:
        filtered = filtered[
            filtered['title'].str.contains(query, case=False, na=False) |
            filtered['summary'].str.contains(query, case=False, na=False)
        ]

    st.subheader(f"Mentions ({len(filtered)})")
    per_page = st.selectbox("Per page", [5, 10, 20], index=1)
    page = st.number_input("Page", min_value=1, max_value=max(1, (len(filtered)-1)//per_page + 1), value=1, step=1)
    start = (page-1)*per_page
    end = start + per_page
    page_df = filtered.iloc[start:end]

    for _, row in page_df.iterrows():
        st.markdown("---")
        st.markdown(f"### [{row['title']}]({row['url']})")
        st.write(row['summary'])
        st.write(f"**Sentiment:** {row['sentiment']}  •  **Risk:** {row['risk_score']}  •  **Source:** {row['source']}")
        cols = st.columns([1,1,6])
        with cols[0]:
            if st.button("Flag", key=f"flag-{row['id']}"):
                st.toast("Flagged (demo)")
        with cols[1]:
            if st.button("Suggest journalist", key=f"suggest-{row['id']}"):
                st.toast("Suggestion (demo)")
        with cols[2]:
            st.write(f"ID: {row['id']} • Article ID: {row['article_id']}")

    st.markdown("---")
    st.caption("Local demo — powered by AI Journalist API")

# --- Operations tab ---
elif tab == "Operations":
    st.header("⚙️ Operations")

    if not ADMIN_TOKEN:
        st.sidebar.markdown("#### Admin token (local dev)")
        ui_token = st.sidebar.text_input("Paste admin token here", type="password")
        if ui_token:
            ADMIN_TOKEN = ui_token

    if not ADMIN_TOKEN:
        st.warning("ADMIN API token not provided — operations disabled. Paste token in sidebar or set ADMIN_API_TOKEN env var.")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Fetch new articles (ingest)"):
            try:
                r = requests.post(f"{API_BASE}/ingest", headers={"X-ADMIN-TOKEN": ADMIN_TOKEN}, timeout=10)
                if r.status_code == 200:
                    st.success("Ingest started (background).")
                else:
                    st.error(f"Ingest API error: {r.status_code} {r.text}")
            except Exception as e:
                st.error(f"Ingest request failed: {e}")
    with col2:
        if st.button("📝 Process mentions (summarize)"):
            try:
                r = requests.post(f"{API_BASE}/process", headers={"X-ADMIN-TOKEN": ADMIN_TOKEN}, timeout=10)
                if r.status_code == 200:
                    st.success("Processing started (background). Refresh Mentions tab after a few seconds.")
                    time.sleep(5)
                    st.rerun()  # ✅ fixed here
                else:
                    st.error(f"Process API error: {r.status_code} {r.text}")
            except Exception as e:
                st.error(f"Process request failed: {e}")

    st.markdown("### Quick workflow")
    st.write("""
    1. Click **Fetch new articles (ingest)** to pull the latest feeds.  
    2. Click **Process mentions (summarize)** to create/refresh mentions.  
    3. Switch to **Mentions** tab and refresh to see new results.
    """)
