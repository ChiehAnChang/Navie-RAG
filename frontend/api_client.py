"""Shared HTTP calls and API error messages."""

import requests
import streamlit as st

from config import SETTINGS


def api_request(method, path, **kwargs):
    """Call FastAPI and show failures without a Python traceback."""
    api_url = str(SETTINGS.rag_api_url).rstrip("/")
    try:
        response = requests.request(
            method, f"{api_url}{path}", timeout=(5, 180), **kwargs
        )
    except requests.Timeout:
        st.error("The API request timed out. Importing may still be in progress. Check your knowledge base before retrying.")
        st.stop()
    except requests.RequestException:
        st.error(f"Cannot connect to {api_url}. Make sure FastAPI is running.")
        st.stop()

    if not response.ok:
        try:
            detail = response.json().get("detail", response.reason)
        except ValueError:
            detail = response.reason
        st.error(f"API error ({response.status_code}): {detail}")
        st.stop()
    return response.json()


def get_knowledge_bases() -> list[str]:
    """Fetch existing knowledge base IDs from FastAPI."""
    return api_request("GET", "/knowledge-bases")
