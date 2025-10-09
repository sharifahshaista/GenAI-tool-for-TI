"""
Streamlit Research Agent Web Application

This app provides a web interface for:
1. Research Pipeline - Topic research with clarification, SERP generation, and web search
2. Learning Extraction - Extract structured learnings from search results
"""

import streamlit as st
import asyncio
import os
import json
from pathlib import Path
from datetime import datetime
import logging
import pandas as pd
from openai import AzureOpenAI
from config.azure_model import Settings

# Import existing modules
from agents.clarification import get_clarifications
from agents.serp import get_serp_queries
from agents.learn import get_learning_structured
from config.searxng_tools import searxng_web_tool
from schemas.datamodel import SearchResultsCollection

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filename='research.log'
)

# Page configuration
st.set_page_config(
    page_title="Research Agent",

    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'clarifications' not in st.session_state:
    st.session_state.clarifications = None
if 'serp_queries' not in st.session_state:
    st.session_state.serp_queries = None
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'learnings' not in st.session_state:
    st.session_state.learnings = {}
if 'current_stage' not in st.session_state:
    st.session_state.current_stage = 'input'
if 'csv_df' not in st.session_state:
    st.session_state.csv_df = None
if 'csv_name' not in st.session_state:
    st.session_state.csv_name = None
if 'csv_preview_rows' not in st.session_state:
    st.session_state.csv_preview_rows = 20
if 'csv_chat_history' not in st.session_state:
    st.session_state.csv_chat_history = []


def reset_session_state():
    """Reset all session state variables"""
    st.session_state.clarifications = None
    st.session_state.serp_queries = None
    st.session_state.search_results = None
    st.session_state.learnings = {}
    st.session_state.current_stage = 'input'


# Helper function to run async code in Streamlit
def run_async(coro):
    """Run async coroutine in Streamlit-compatible way"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(coro)
        return result
    finally:
        loop.close()


def run_clarification_stage(topic: str):
    """Stage 1: Get clarifications (Streamlit version - no input())"""
    async def _async_clarification():
        from agents.clarification import create_clarification_agent
        from schemas.datamodel import ClarificationResponse, ClarificationQuestion

        clarification_agent = create_clarification_agent()
        response = ClarificationResponse(original_query=topic)

        try:
            # Get clarification questions from agent (no user input)
            result = await clarification_agent.run(topic)
            questions = result.output

            # Parse questions and add them WITHOUT answers
            if questions:
                for i, question in enumerate(questions.split('\n'), 1):
                    if question.strip():
                        qa = ClarificationQuestion(
                            question=question.strip(),
                            answer=""  # Empty - will be filled by Streamlit form
                        )
                        response.questions_and_answers.append(qa)
        except Exception as e:
            logging.error(f"Error getting clarifications: {e}")

        logging.info(f"Clarifications received: {len(response.questions_and_answers)} questions")
        return response

    with st.spinner("Generating clarification questions..."):
        clarifications = run_async(_async_clarification())
        st.session_state.clarifications = clarifications
    return clarifications


def run_serp_generation_stage(topic: str, clarifications):
    """Stage 2: Generate SERP queries"""
    async def _async_serp():
        serp_queries = await get_serp_queries(topic, clarifications)
        logging.info(f"Generated {len(serp_queries)} SERP queries")
        return serp_queries

    with st.spinner("Generating SERP queries..."):
        serp_queries = run_async(_async_serp())
        st.session_state.serp_queries = serp_queries
    return serp_queries


def run_search_stage(serp_queries):
    """Stage 3: Execute web searches"""
    async def _async_search():
        results_collection = SearchResultsCollection()
        total_queries = len(serp_queries)

        for idx, query in enumerate(serp_queries, 1):
            status_text.text(f"Searching [{idx}/{total_queries}]: {query}")
            logging.info(f"Searching [{idx}/{total_queries}]: {query}")

            try:
                results = await searxng_web_tool(None, query)
                results_collection.add_result(query, results)
                logging.info(f"Search successful: {query}")
            except Exception as e:
                st.warning(f"Search failed for '{query}': {e}")
                logging.error(f"Search failed for '{query}': {e}")
                continue

            progress_bar.progress(idx / total_queries)

        return results_collection

    progress_bar = st.progress(0)
    status_text = st.empty()

    results_collection = run_async(_async_search())

    status_text.text(f"Search complete! {results_collection.total_queries} queries executed.")
    st.session_state.search_results = results_collection

    return results_collection


def run_learning_extraction_stage(results_collection):
    """Stage 4: Extract learnings"""
    async def _async_learning():
        learnings_dict = {}
        results_list = list(results_collection.results.items())
        total_queries = len(results_list)

        for idx, (query, search_result) in enumerate(results_list, 1):
            status_text.text(f"Extracting learnings [{idx}/{total_queries}]: {query[:50]}...")
            logging.info(f"Extracting learnings [{idx}/{total_queries}]: {query}")

            try:
                learnings = await get_learning_structured(query, search_result.results)
                learnings_dict[query] = learnings
                logging.info(f"Learning extraction successful: {query}")
            except Exception as e:
                st.warning(f"Learning extraction failed for '{query}': {e}")
                logging.error(f"Learning extraction failed for '{query}': {e}")
                continue

            progress_bar.progress(idx / total_queries)

        return learnings_dict

    progress_bar = st.progress(0)
    status_text = st.empty()

    learnings_dict = run_async(_async_learning())

    status_text.text(f"Learning extraction complete! {len(learnings_dict)} learnings extracted.")
    st.session_state.learnings = learnings_dict

    return learnings_dict


@st.cache_resource(show_spinner=False)
def get_azure_client():
    """Create and cache Azure OpenAI client from env (.env supported)."""
    settings = Settings()
    client = AzureOpenAI(
        api_key=settings.azure_api_key,
        api_version=settings.azure_api_version,
        azure_endpoint=str(settings.azure_endpoint),
    )
    return client, settings.model_name


def build_csv_context(df: pd.DataFrame, sample_rows: int) -> str:
    """Build a concise CSV context string for the LLM."""
    sample_rows = max(1, min(sample_rows, len(df)))
    preview_csv = df.head(sample_rows).to_csv(index=False)
    # Limit context size to avoid token bloat
    if len(preview_csv) > 120_000:
        preview_csv = preview_csv[:120_000] + "\n... [truncated]"
    dtypes_str = (df.dtypes.astype(str)
                  .reset_index()
                  .rename(columns={"index": "column", 0: "dtype"})
                  .to_string(index=False))
    meta = [
        f"Total rows: {len(df)}",
        f"Total columns: {len(df.columns)}",
        f"Columns: {', '.join(map(str, df.columns.tolist()))}",
        "\nColumn dtypes:\n" + dtypes_str,
        f"\nPreview (first {sample_rows} rows):\n" + preview_csv,
    ]
    return "\n".join(meta)


def generate_csv_chat_response(question: str, df: pd.DataFrame, history: list, sample_rows: int) -> str:
    """Call Azure OpenAI to answer a question about the uploaded CSV."""
    client, deployment = get_azure_client()

    system_instructions = (
        "You are a helpful data analyst. Answer questions using only the provided CSV context. "
        "If the preview may be insufficient for an exact calculation, clearly state that your answer "
        "is based on the preview and outline Pandas code the user could run locally to compute "
        "the precise value over the full dataset. Prefer concise answers, tables, and bullet points."
    )

    csv_context = build_csv_context(df, sample_rows)

    messages = [{"role": "system", "content": system_instructions},
                {"role": "user", "content": "CSV Context:\n" + csv_context}]

    # Append recent chat history (limit to last 8 turns to keep prompt short)
    for msg in history[-16:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": question})

    try:
        resp = client.chat.completions.create(
            model=deployment,
            messages=messages,
            temperature=0.2,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"Error generating response: {e}"


def save_search_results(results_collection, filename):
    """Save search results to JSON file"""
    path = Path("data")
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{filename}.json"
    results_collection.to_file(output_path)

    return output_path


def save_learnings(learnings_dict, filename):
    """Save learnings to markdown file"""
    path = Path("data")
    path.mkdir(parents=True, exist_ok=True)

    output_path = path / f"{filename}.md"

    with open(output_path, "w", encoding="utf-8") as f:
        for query, learnings in learnings_dict.items():
            f.write(f"## {query}\n\n")
            f.write(learnings)
            f.write("\n\n---\n\n")

    return output_path


def load_search_results(file_path):
    """Load search results from JSON file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    collection = SearchResultsCollection()
    for query, results in data.items():
        collection.add_result(query, results)

    return collection


# Main App
st.title("Research Agent")
st.markdown("AI-powered research with clarification, SERP generation, web search, and learning extraction")

# Sidebar
st.sidebar.header("Navigation")
page = st.sidebar.radio(
    "Select Mode",
    ["Research Pipeline", "Learning Extraction", "CSV + Chatbot", "About"],
    label_visibility="collapsed"
)

# Research Pipeline Page
if page == "Research Pipeline":
    st.header("Research Pipeline")
    st.markdown("Conduct comprehensive research with automated clarification and web search")

    # Input Section
    st.subheader("1. Research Topic")
    topic = st.text_area(
        "Enter your research topic:",
        placeholder="e.g., What is the expected growth rate for Singapore companies that sell AI solutions?",
        height=100
    )

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        start_research = st.button("Start Research", type="primary", use_container_width=True)
    with col2:
        reset_btn = st.button("Reset", use_container_width=True)

    if reset_btn:
        reset_session_state()
        st.rerun()

    if start_research and topic:
        st.session_state.current_stage = 'clarification'

    # Clarification Stage
    if st.session_state.current_stage == 'clarification' and topic:
        st.subheader("2. Clarification Questions")

        if st.session_state.clarifications is None:
            # Generate clarifications
            clarifications = run_clarification_stage(topic)

            if clarifications.questions_and_answers:
                st.success(f"Generated {len(clarifications.questions_and_answers)} clarification questions")
                st.session_state.current_stage = 'answer_clarifications'
                st.rerun()
            else:
                st.info("No clarification questions needed. Proceeding to search...")
                st.session_state.current_stage = 'search'
                st.rerun()

    # Answer Clarifications
    if st.session_state.current_stage == 'answer_clarifications':
        st.subheader("2. Answer Clarification Questions")

        clarifications = st.session_state.clarifications

        with st.form("clarification_form"):
            st.markdown("Please answer the following questions to refine the research:")

            answers = []
            for idx, qa in enumerate(clarifications.questions_and_answers):
                st.markdown(f"**Question {idx + 1}:** {qa.question}")
                answer = st.text_input(
                    f"Your answer:",
                    key=f"answer_{idx}",
                    label_visibility="collapsed"
                )
                answers.append(answer)

            submitted = st.form_submit_button("Submit Answers", type="primary")

            if submitted:
                # Update clarifications with answers
                for idx, answer in enumerate(answers):
                    clarifications.questions_and_answers[idx].answer = answer

                st.session_state.clarifications = clarifications
                st.session_state.current_stage = 'search'
                st.rerun()

    # Search Stage
    if st.session_state.current_stage == 'search' and topic:
        st.subheader("3. Web Search")

        if st.session_state.serp_queries is None:
            # Generate SERP queries
            serp_queries = run_serp_generation_stage(topic, st.session_state.clarifications)

            if serp_queries:
                st.success(f"Generated {len(serp_queries)} SERP queries")

                with st.expander("View SERP Queries"):
                    for idx, query in enumerate(serp_queries, 1):
                        st.text(f"{idx}. {query}")
            else:
                st.error("No SERP queries generated. Please try again.")
                st.stop()

        if st.session_state.search_results is None:
            if st.button("Execute Web Search", type="primary"):
                results_collection = run_search_stage(st.session_state.serp_queries)

                if results_collection.results:
                    st.success(f"Search complete! Collected {results_collection.total_queries} results.")
                    st.session_state.current_stage = 'save_results'
                    st.rerun()
                else:
                    st.error("No search results collected.")
        else:
            st.success(f"Search complete! Collected {st.session_state.search_results.total_queries} results.")
            st.session_state.current_stage = 'save_results'

    # Save Results Stage
    if st.session_state.current_stage == 'save_results':
        st.subheader("4. Save Results")

        results_collection = st.session_state.search_results

        col1, col2 = st.columns(2)

        with col1:
            st.metric("Queries Executed", results_collection.total_queries)
        with col2:
            st.metric("Timestamp", results_collection.timestamp.strftime("%Y-%m-%d %H:%M:%S"))

        # Show ALL search results
        st.subheader("Search Results")

        # Add a search/filter box
        search_filter = st.text_input("Filter queries:", placeholder="Type to filter results...")

        # Filter results if search term provided
        filtered_results = results_collection.results.items()
        if search_filter:
            filtered_results = [(q, r) for q, r in results_collection.results.items()
                               if search_filter.lower() in q.lower()]

        # Display results count
        st.info(f"Showing {len(filtered_results) if search_filter else len(results_collection.results)} results")

        # Display all results in expandable sections
        for idx, (query, result) in enumerate(filtered_results if search_filter else results_collection.results.items(), 1):
            with st.expander(f"**{idx}. {query}**", expanded=False):
                # Show snippet and full content
                col1, col2 = st.columns([1, 3])
                with col1:
                    st.caption(f"Length: {len(result.results)} chars")
                    st.caption(f"Timestamp: {result.timestamp.strftime('%H:%M:%S')}")

                # Display the full results
                st.text_area(
                    "Search Results:",
                    value=result.results,
                    height=300,
                    key=f"search_result_{idx}",
                    label_visibility="collapsed"
                )

        filename = st.text_input(
            "Enter filename to save results (without extension):",
            value=f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )

        if st.button("Save Results", type="primary"):
            try:
                output_path = save_search_results(results_collection, filename)
                st.success(f"Results saved to {output_path}")

                # Provide download button
                with open(output_path, 'r', encoding='utf-8') as f:
                    json_data = f.read()

                st.download_button(
                    label="Download JSON",
                    data=json_data,
                    file_name=f"{filename}.json",
                    mime="application/json"
                )

                st.info("You can now extract learnings from this file in the 'Learning Extraction' tab")

            except Exception as e:
                st.error(f"Error saving results: {e}")

# Learning Extraction Page
elif page == "Learning Extraction":
    st.header("Learning Extraction")
    st.markdown("Extract structured learnings from search results")

    # Option 1: Upload JSON file
    st.subheader("Option 1: Upload Search Results")
    uploaded_file = st.file_uploader(
        "Upload JSON file with search results",
        type=['json'],
        help="Upload a JSON file created from the Research Pipeline"
    )

    # Option 2: Select from existing files
    st.subheader("Option 2: Select Existing File")
    data_path = Path("data")
    if data_path.exists():
        json_files = list(data_path.glob("*.json"))
        if json_files:
            selected_file = st.selectbox(
                "Select a file:",
                options=[f.name for f in json_files],
                index=None
            )
        else:
            st.info("No JSON files found in data/ directory")
            selected_file = None
    else:
        st.info("No data/ directory found")
        selected_file = None

    # Process selected file
    results_dict = None

    if uploaded_file is not None:
        try:
            results_dict = json.load(uploaded_file)
            st.success(f"Loaded {len(results_dict)} queries from uploaded file")
        except Exception as e:
            st.error(f"Error loading file: {e}")

    elif selected_file is not None:
        try:
            file_path = data_path / selected_file
            with open(file_path, 'r', encoding='utf-8') as f:
                results_dict = json.load(f)
            st.success(f"Loaded {len(results_dict)} queries from {selected_file}")
        except Exception as e:
            st.error(f"Error loading file: {e}")

    # Extract learnings
    if results_dict is not None:
        st.subheader("Extract Learnings")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Queries", len(results_dict))

        # Preview queries
        with st.expander("Preview Queries"):
            for idx, query in enumerate(list(results_dict.keys())[:5], 1):
                st.text(f"{idx}. {query}")
            if len(results_dict) > 5:
                st.text(f"... and {len(results_dict) - 5} more")

        output_filename = st.text_input(
            "Output filename (without extension):",
            value=f"learnings_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )

        if st.button("Extract Learnings", type="primary"):
            # Create SearchResultsCollection from dict
            collection = SearchResultsCollection()
            for query, results in results_dict.items():
                collection.add_result(query, results)

            # Extract learnings
            learnings_dict = run_learning_extraction_stage(collection)

            if learnings_dict:
                st.success(f"Extracted learnings for {len(learnings_dict)} queries")

                # Display ALL learnings
                st.subheader("Extracted Learnings")

                # Add a search/filter box
                learning_filter = st.text_input(
                    "Filter learnings:",
                    placeholder="Type to filter by query...",
                    key="learning_filter"
                )

                # Filter learnings if search term provided
                filtered_learnings = learnings_dict.items()
                if learning_filter:
                    filtered_learnings = [(q, l) for q, l in learnings_dict.items()
                                          if learning_filter.lower() in q.lower()]

                # Display count
                st.info(f"Showing {len(filtered_learnings) if learning_filter else len(learnings_dict)} learnings")

                # Display all learnings in expandable sections
                for idx, (query, learnings) in enumerate(filtered_learnings if learning_filter else learnings_dict.items(), 1):
                    with st.expander(f"**{idx}. {query}**", expanded=False):
                        st.markdown(learnings)
                        st.divider()

                        # Option to copy individual learning
                        st.code(learnings, language=None)

                # Save learnings
                try:
                    output_path = save_learnings(learnings_dict, output_filename)
                    st.success(f"Learnings saved to {output_path}")

                    # Provide download button
                    with open(output_path, 'r', encoding='utf-8') as f:
                        md_data = f.read()

                    st.download_button(
                        label="Download Markdown Report",
                        data=md_data,
                        file_name=f"{output_filename}.md",
                        mime="text/markdown"
                    )

                except Exception as e:
                    st.error(f"Error saving learnings: {e}")
            else:
                st.warning("No learnings extracted")

# CSV + Chatbot Page
elif page == "CSV + Chatbot":
    st.header("CSV + Chatbot")
    st.markdown("Upload a CSV and chat with an AI about its contents. The chat uses the CSV preview as context.")

    left_col, right_col = st.columns([1, 1])

    with left_col:
        st.subheader("CSV Data")
        uploaded_csv = st.file_uploader("Upload CSV file", type=["csv"], accept_multiple_files=False)

        if uploaded_csv is not None:
            try:
                df = pd.read_csv(uploaded_csv)
                st.session_state.csv_df = df
                st.session_state.csv_name = uploaded_csv.name
                st.success(f"Loaded '{uploaded_csv.name}' with shape {df.shape}")
            except Exception as e:
                st.error(f"Failed to read CSV: {e}")

        if st.session_state.csv_df is not None:
            df = st.session_state.csv_df
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Rows", len(df))
            with col_b:
                st.metric("Columns", len(df.columns))

            st.session_state.csv_preview_rows = st.slider(
                "Preview rows",
                min_value=5,
                max_value=int(min(500, max(5, len(df)))) ,
                value=int(min(st.session_state.csv_preview_rows, max(5, len(df)))),
                step=5,
                help="Controls both the on-screen preview and the chat context sample size."
            )

            st.dataframe(
                df.head(st.session_state.csv_preview_rows),
                use_container_width=True,
            )

            with st.expander("Columns"):
                st.write(list(map(str, df.columns.tolist())))

            if st.button("Clear CSV"):
                st.session_state.csv_df = None
                st.session_state.csv_name = None
                st.session_state.csv_chat_history = []
                st.rerun()
        else:
            st.info("Upload a CSV to preview it.")

    with right_col:
        st.subheader("Chatbot")
        if st.session_state.csv_df is None:
            st.info("Upload a CSV in the left panel to start chatting.")
        else:
            # Render previous conversation
            for msg in st.session_state.csv_chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            user_input = st.chat_input("Ask a question about the CSV...")

            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("Clear chat"):
                    st.session_state.csv_chat_history = []
                    st.rerun()
            with col2:
                st.caption(f"Context rows: {st.session_state.csv_preview_rows}")

            if user_input:
                st.session_state.csv_chat_history.append({"role": "user", "content": user_input})
                with st.chat_message("user"):
                    st.markdown(user_input)

                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        reply = generate_csv_chat_response(
                            question=user_input,
                            df=st.session_state.csv_df,
                            history=st.session_state.csv_chat_history,
                            sample_rows=st.session_state.csv_preview_rows,
                        )
                        st.markdown(reply)
                st.session_state.csv_chat_history.append({"role": "assistant", "content": reply})

# About Page
elif page == "About":
    st.header("About Research Agent")

    st.markdown("""
    ### Overview

    The Research Agent is an AI-powered tool that automates comprehensive research through multiple stages:

    **Research Pipeline:**
    1. **Clarification** - Asks targeted questions to refine research scope
    2. **SERP Generation** - Creates optimized search queries
    3. **Web Search** - Executes searches via SearxNG
    4. **Results Collection** - Aggregates and saves search results

    **Learning Extraction:**
    - Analyzes search results using AI
    - Extracts key learnings with entities and metrics
    - Generates structured markdown reports

    ### Features

    - Interactive clarification questions
    - Real-time progress tracking
    - Multi-query web search
    - Structured learning extraction
    - Download results in JSON and Markdown

    ### Technology Stack

    - **Frontend:** Streamlit
    - **AI Model:** Azure OpenAI (GPT-4.1-mini)
    - **Search Engine:** SearxNG
    - **Validation:** Pydantic
    - **Agent Framework:** Pydantic AI

    ### Usage Tips

    1. Start with a clear, specific research topic
    2. Answer clarification questions thoughtfully
    3. Review SERP queries before search execution
    4. Save results with descriptive filenames
    5. Reprocess results with different learning prompts if needed

    ### File Structure

    - Search results saved to: `data/{filename}.json`
    - Learning reports saved to: `data/{filename}.md`
    - Logs saved to: `research.log`

    ### Support

    For issues or questions, check the logs at `research.log` or review the documentation.
    AL-AISG
    """)

    st.divider()

    st.markdown("""
    ### Quick Start Guide

    **Research Pipeline:**
    1. Navigate to "Research Pipeline" tab
    2. Enter your research topic
    3. Click "Start Research"
    4. Answer clarification questions
    5. Execute web search
    6. Save and download results

    **Learning Extraction:**
    1. Navigate to "Learning Extraction" tab
    2. Upload JSON file or select existing file
    3. Click "Extract Learnings"
    4. Preview and download markdown report
    """)

# Footer
st.sidebar.divider()
st.sidebar.markdown("### Settings")
st.sidebar.info(f"Session ID: {id(st.session_state)}")

if st.sidebar.button("Clear Session"):
    reset_session_state()
    st.rerun()
