import streamlit as st
import requests
import pandas as pd

import os 

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000/api")

st.set_page_config(page_title="AI Journalist — Mentions", layout="wide")
st.title("📰 AI Journalist — Mentions Dashboard")

@st.cache_data(ttl=60)
def fetch_mentions():
    try:
        r = requests.get(f"{API_BASE}/mentions", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Failed to fetch mentions: {e}")
        return []

mentions = fetch_mentions()
if not mentions:
    st.info("No mentions found.")
    st.stop()

df = pd.DataFrame(mentions)

# Sidebar
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
