import streamlit as st

from api_client import api_request


def render(knowledge_bases: list[str]) -> None:
    st.header("Add data")
    source_mode = st.radio("Data source", ["Paste text", "Upload file"], horizontal=True)

    with st.form("ingest"):
        knowledge_base_id = st.selectbox(
            "Knowledge base",
            [None, *knowledge_bases],
            format_func=lambda value: "None (create a new knowledge base)" if value is None else value,
        )
        if source_mode == "Paste text":
            source_name = st.text_input("Source name", value="pasted-text")
            text = st.text_area("Paste text", height=240)
            st.caption("source_type: txt")
        else:
            uploaded_file = st.file_uploader("Choose a file", type=["txt", "md", "pdf", "docx"])
            st.caption("source_type is set automatically from the file extension: txt / md / pdf / docx")
        submitted = st.form_submit_button("Add to knowledge base")

    if submitted:
        if source_mode == "Paste text" and not text.strip():
            st.warning("Please paste some text first.")
        elif source_mode == "Upload file" and uploaded_file is None:
            st.warning("Please choose a file first.")
        else:
            with st.spinner("Importing data…"):
                if source_mode == "Paste text":
                    result = api_request(
                        "POST", "/ingest/text",
                        json={
                            "text": text,
                            "source_name": source_name.strip() or "pasted-text",
                            "knowledge_base_id": knowledge_base_id,
                        },
                    )
                else:
                    result = api_request(
                        "POST", "/ingest/file",
                        files={"file": (
                            uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type,
                        )},
                        data={"knowledge_base_id": knowledge_base_id} if knowledge_base_id else {},
                    )
            st.session_state["ingest_success"] = (
                f"Imported {result['source']}. Knowledge base: {result['knowledge_base_id']}"
            )
            st.rerun()
