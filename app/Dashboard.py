"""myrun entrypoint: a router with a top navigation bar. The pages live in app/views/."""

from pathlib import Path

import streamlit as st

STATIC = Path(__file__).resolve().parent / "static"

st.session_state["_mr_nav"] = True
pages = [st.Page("views/dashboard.py", title="Dashboard", default=True),
         st.Page("views/trends.py", title="Trends", url_path="Trends"),
         st.Page("views/activity.py", title="Activity", url_path="Activity"),
         st.Page("views/explore.py", title="Explore", url_path="Explore")]
page = st.navigation(pages, position="top")
st.set_page_config(page_title=f"myrun · {page.title}", layout="wide",
                   initial_sidebar_state="collapsed")
st.logo(str(STATIC / "logo.svg"), size="medium")
# Streamlit moves the top nav into the sidebar on phones; this row (shown by CSS only there) replaces it.
with st.container(key="mr-phone-nav", horizontal=True):
    for p in pages:
        st.page_link(p)
page.run()
