import streamlit as st

from api_client import api_request


def render(knowledge_bases: list[str]) -> None:
    st.header("Ask questions")
    if not knowledge_bases:
        st.info("No knowledge bases yet. Go to Add data to import text or a file first.")
        st.stop()

    with st.form("ask"):
        knowledge_base_id = st.selectbox("Knowledge base", knowledge_bases)
        question = st.text_area("Your question")
        submitted = st.form_submit_button("Submit question")

    if submitted:
        if not question.strip():
            st.warning("Please enter a question first.")
        else:
            with st.spinner("Searching…"):
                result = api_request(
                    "POST", "/ask",
                    json={
                        "knowledge_base_id": knowledge_base_id,
                        "question": question.strip(),
                    },
                )
            st.markdown(result["answer"])
            for index, source in enumerate(result["sources"], start=1):
                page_number = source.get("page")
                page_label = f" · Page {page_number + 1}" if page_number is not None else ""
                with st.expander(f"Source {index}: {source['source']}{page_label}"):
                    st.text(source["content"])
