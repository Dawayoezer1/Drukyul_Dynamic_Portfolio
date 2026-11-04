"""Login gate for the Streamlit dashboard. Works together with Auth.py in the same folder.

app.py calls require_login() right after st.set_page_config(). The visitor must arrive
from the Drukyul website, which adds a 5-minute sign-in link to the dashboard address.
Set DRUKYUL_REQUIRE_LOGIN=0 to switch the gate off (for example during development).
"""
import os

import streamlit as st

from Auth import SITE_URL, user_from_dashboard_token


def require_login():
    if os.environ.get("DRUKYUL_REQUIRE_LOGIN", "1") == "0":
        return {"name": "Guest", "email": ""}

    token = st.query_params.get("token")
    expired = False
    if token:
        user = user_from_dashboard_token(token)
        if user:
            st.session_state["auth_user"] = user
        else:
            expired = True
        st.query_params.clear()

    user = st.session_state.get("auth_user")
    if not user:
        st.title("Please log in first")
        if expired:
            st.warning("That sign-in link has expired. Open the dashboard again from the website.")
        st.write("The dashboard opens from the Drukyul website after you log in.")
        st.link_button("Go to the login page", SITE_URL)
        st.stop()

    left, right = st.columns([5, 1])
    left.caption(f"Signed in as {user['name']} ({user['email']})")
    right.link_button("Back to website", SITE_URL)
    return user
