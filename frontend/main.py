"""Run with: uv run streamlit run frontend/main.py."""

import streamlit as st

from api_client import get_knowledge_bases
from views import add_data, ask_questions


def main() -> None:
    st.set_page_config(page_title="Naive RAG", page_icon="📚")
    st.title("📚 Naive RAG")

    page = st.sidebar.radio("Page", ["Add data", "Ask questions"])
    st.sidebar.caption(
        "Knowledge bases are stored in API memory and cleared when the API restarts."
    )
    st.sidebar.button("Refresh knowledge bases")
    # Each rerun, including the refresh button, fetches the current API list.
    knowledge_bases = get_knowledge_bases()

    if message := st.session_state.pop("ingest_success", None):
        st.success(message)

    if page == "Add data":
        add_data.render(knowledge_bases)
    else:
        ask_questions.render(knowledge_bases)


if __name__ == "__main__":
    main()
