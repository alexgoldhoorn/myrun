"""myrun entrypoint: a router with a top navigation bar. The pages live in app/views/."""

from pathlib import Path

import streamlit as st

STATIC = Path(__file__).resolve().parent / "static"

st.set_page_config(page_title="myrun", layout="wide", initial_sidebar_state="collapsed")
st.logo(str(STATIC / "logo.svg"), size="medium", icon_image=str(STATIC / "icon.svg"))
st.session_state["_mr_nav"] = True
pages = [st.Page("views/dashboard.py", title="Dashboard", default=True),
         st.Page("views/trends.py", title="Trends"),
         st.Page("views/activity.py", title="Activity"),
         st.Page("views/explore.py", title="Explore")]
st.navigation(pages, position="top").run()
