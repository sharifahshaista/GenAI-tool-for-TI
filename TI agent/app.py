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

# Import existing modules
from agents.clarification import get_clarifications
from agents.serp import get_serp_queries
from agents.learn import get_learning_structured
from agents.summarise_csv import summarize_csv_file, save_summarized_csv
from config.searxng_tools import searxng_web_tool
from config.model_config import get_model
from schemas.datamodel import (
    SearchResultsCollection, 
    CSVSummarizationMetadata,
    CSVSummarizationHistory
)
import pandas as pd
import tempfile

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
if 'csv_processed_df' not in st.session_state:
    st.session_state.csv_processed_df = None
if 'csv_metadata' not in st.session_state:
    st.session_state.csv_metadata = None
if 'csv_processing' not in st.session_state:
    st.session_state.csv_processing = False
if 'csv_progress' not in st.session_state:
    st.session_state.csv_progress = {'current': 0, 'total': 0, 'elapsed': 0, 'remaining': 0}


def reset_session_state():
    """Reset all session state variables"""
    st.session_state.clarifications = None
    st.session_state.serp_queries = None
    st.session_state.search_results = None
    st.session_state.learnings = {}
    st.session_state.current_stage = 'input'
    st.session_state.csv_processed_df = None
    st.session_state.csv_metadata = None
    st.session_state.csv_processing = False
    st.session_state.csv_progress = {'current': 0, 'total': 0, 'elapsed': 0, 'remaining': 0}


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
    ["Web Search", "First-pass Summarization", "Database", "About"],
    label_visibility="collapsed"
)

# Web Search Page
if page == "Web Search":
    st.header("Web Search")
    st.markdown("AI-powered research with clarification, SERP generation, web search, and learning extraction")
    
    # Create tabs for Research Pipeline and Learning Extraction
    tab1, tab2 = st.tabs(["Research Pipeline", "Learning Extraction"])
    
    with tab1:
        st.subheader("Research Pipeline")
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

                    st.info("You can now extract learnings from this file in the 'Learning Extraction' tab (above)")

                except Exception as e:
                    st.error(f"Error saving results: {e}")

    with tab2:
        st.subheader("Learning Extraction")
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

# First-pass Summarization Page
elif page == "First-pass Summarization":
    st.header("First-pass Summarization")
    st.markdown("Upload CSV files with a 'content' column to generate tech-intelligence summaries and automatic categorization")

    # Check if processing flag is stuck (interrupted by navigation)
    if st.session_state.csv_processing and st.session_state.csv_processed_df is None:
        st.warning("⚠️ **Previous processing was interrupted.** The task did not complete because you navigated away from this page.")
        if st.button("Clear Interrupted Task", type="secondary"):
            st.session_state.csv_processing = False
            st.session_state.csv_progress = {'current': 0, 'total': 0, 'elapsed': 0, 'remaining': 0}
            st.rerun()
        st.divider()

    # Create tabs for upload and history
    tab1, tab2 = st.tabs(["Upload & Process", "History"])

    with tab1:
        st.subheader("Upload CSV File")
        st.markdown("""
        **Requirements:**
        - CSV file must contain a column named `content`
        - The content column should contain text to be summarized
        - Each row will be processed independently
        """)
        
        st.divider()
        
        # Model Selection
        st.subheader("🤖 Model Selection")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            model_provider = st.selectbox(
                "Provider",
                ["Azure OpenAI", "LM Studio (Local)"],
                help="Select the AI model provider"
            )
        
        with col2:
            if model_provider == "Azure OpenAI":
                azure_model_name = st.selectbox(
                    "Model",
                    ["pmo-gpt-4.1-nano", "gpt-4o", "gpt-4o-mini", "gpt-4"],
                    help="Select Azure OpenAI model"
                )
                st.session_state.selected_model_config = {
                    'provider': 'azure',
                    'model_name': azure_model_name
                }
            else:  # LM Studio
                lm_studio_url = st.text_input(
                    "LM Studio URL",
                    value="http://127.0.0.1:1234/v1",
                    help="LM Studio API endpoint"
                )
                st.session_state.selected_model_config = {
                    'provider': 'lm_studio',
                    'base_url': lm_studio_url,
                    'model_name': 'local-model'
                }
                st.info("💡 Make sure LM Studio is running and a model is loaded at the specified URL")
        
        st.divider()

        # File uploader
        uploaded_csv = st.file_uploader(
            "Choose a CSV file",
            type=['csv'],
            help="Upload a CSV file with a 'content' column"
        )

        if uploaded_csv is not None:
            try:
                # Read the CSV to preview
                df_preview = pd.read_csv(uploaded_csv)
                
                st.success(f"File loaded: {uploaded_csv.name}")
                
                # Show file info
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Rows", len(df_preview))
                with col2:
                    st.metric("Total Columns", len(df_preview.columns))
                with col3:
                    has_content = 'content' in df_preview.columns
                    st.metric("Has 'content' column", "✓" if has_content else "✗")

                # Show column names
                with st.expander("View Columns"):
                    st.write(df_preview.columns.tolist())

                # Check if content column exists
                if 'content' not in df_preview.columns:
                    st.error("❌ CSV must contain a 'content' column")
                    st.info(f"Available columns: {', '.join(df_preview.columns)}")
                    st.stop()

                # Preview data
                st.subheader("Data Preview")
                st.dataframe(df_preview.head(10), use_container_width=True)

                # Process button
                if st.button("Start Summarization", type="primary", use_container_width=True):
                    # Save uploaded file temporarily
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='wb') as tmp_file:
                        tmp_file.write(uploaded_csv.getvalue())
                        tmp_path = Path(tmp_file.name)

                    try:
                        # Set processing flag
                        st.session_state.csv_processing = True
                        st.session_state.csv_progress = {
                            'current': 0,
                            'total': len(df_preview),
                            'elapsed': 0,
                            'remaining': 0
                        }
                        
                        # Show warning about navigation
                        st.warning("⚠️ **Important:** Processing will continue only while you stay on this page. Navigating to another section will interrupt the task. Please wait for completion.")
                        
                        # Process the CSV
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        time_text = st.empty()
                        
                        # Create a container for progress updates
                        progress_info = {
                            'current': 0,
                            'total': len(df_preview),
                            'elapsed': 0,
                            'remaining': 0
                        }
                        
                        def format_time(seconds):
                            """Format seconds into human-readable time"""
                            if seconds < 60:
                                return f"{seconds:.0f}s"
                            elif seconds < 3600:
                                mins = int(seconds // 60)
                                secs = int(seconds % 60)
                                return f"{mins}m {secs}s"
                            else:
                                hours = int(seconds // 3600)
                                mins = int((seconds % 3600) // 60)
                                return f"{hours}h {mins}m"
                        
                        def update_progress(current, total, elapsed, est_remaining):
                            """Update progress display with time estimates"""
                            progress_info['current'] = current
                            progress_info['elapsed'] = elapsed
                            progress_info['remaining'] = est_remaining
                            
                            # Update session state for sidebar display
                            st.session_state.csv_progress = {
                                'current': current,
                                'total': total,
                                'elapsed': elapsed,
                                'remaining': est_remaining
                            }
                            
                            # Update progress bar
                            progress = current / total if total > 0 else 0
                            progress_bar.progress(progress)
                            
                            # Update status text
                            status_text.text(f"Processing row {current}/{total} (summarizing & classifying)...")
                            
                            # Update time information with dynamic estimates
                            elapsed_str = format_time(elapsed)
                            remaining_str = format_time(est_remaining)
                            
                            if current < total:
                                time_text.markdown(
                                    f"**Time Elapsed:** {elapsed_str} | "
                                    f"**Estimated Remaining:** {remaining_str} | "
                                    f"**Progress:** {current}/{total} rows ({progress*100:.1f}%)"
                                )
                            else:
                                time_text.markdown(
                                    f"**Total Duration:** {elapsed_str} | "
                                    f"**Completed:** {total} rows (100%)"
                                )

                        async def process_with_progress():
                            # Get selected model
                            model_config = st.session_state.get('selected_model_config', {'provider': 'azure', 'model_name': 'pmo-gpt-4.1-nano'})
                            selected_model = get_model(**model_config)
                            
                            df_result, duration, metadata = await summarize_csv_file(
                                tmp_path, 
                                "content",
                                progress_callback=update_progress,
                                custom_model=selected_model
                            )
                            return df_result, duration, metadata

                        df_result, duration, metadata = run_async(process_with_progress())

                        progress_bar.progress(1.0)
                        status_text.text("✓ Processing complete!")
                        time_text.markdown(
                            f"✅ **Total Duration:** {format_time(duration)} | "
                            f"📊 **Completed:** {len(df_result)} rows (100%)"
                        )

                        # Store in session state
                        st.session_state.csv_processed_df = df_result
                        metadata['source_file'] = uploaded_csv.name
                        st.session_state.csv_metadata = CSVSummarizationMetadata(**metadata)
                        
                        # Clear processing flag
                        st.session_state.csv_processing = False

                        st.success(f"✓ Summarization complete in {duration:.2f} seconds ({format_time(duration)})!")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error processing CSV: {e}")
                        logging.error(f"CSV processing error: {e}")
                        # Clear processing flag on error
                        st.session_state.csv_processing = False
                    finally:
                        # Clean up temp file
                        if tmp_path.exists():
                            tmp_path.unlink()

            except Exception as e:
                st.error(f"Error reading CSV file: {e}")

        # Show processed results
        if st.session_state.csv_processed_df is not None and st.session_state.csv_metadata is not None:
            st.divider()
            st.subheader("✓ Processing Complete")

            metadata = st.session_state.csv_metadata
            df_result = st.session_state.csv_processed_df

            # Show statistics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Rows", metadata.total_rows)
            with col2:
                st.metric("Successful", metadata.successful)
            with col3:
                st.metric("Failed", metadata.failed)
            with col4:
                st.metric("Success Rate", f"{metadata.success_rate:.1f}%")

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Duration", f"{metadata.duration_seconds:.2f}s")
            with col2:
                st.metric("Avg per Row", f"{metadata.avg_time_per_row:.2f}s")

            # Preview results
            st.subheader("Preview Summarized Content")
            
            # Add filter
            preview_count = st.slider("Number of rows to preview", 5, min(50, len(df_result)), 10)
            
            # Show results in expandable sections
            for idx in range(min(preview_count, len(df_result))):
                row = df_result.iloc[idx]
                with st.expander(f"Row {idx + 1}", expanded=(idx == 0)):
                    # Show classification at the top
                    if 'classification' in row:
                        st.markdown(f"**Categories:** :green[{row['classification']}]")
                        st.divider()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Original Content:**")
                        st.text_area(
                            "Original",
                            value=str(row['content'])[:500] + "..." if len(str(row['content'])) > 500 else str(row['content']),
                            height=150,
                            key=f"orig_{idx}",
                            label_visibility="collapsed"
                        )
                    with col2:
                        st.markdown("**Summary:**")
                        st.text_area(
                            "Summary",
                            value=str(row['summary']),
                            height=150,
                            key=f"summ_{idx}",
                            label_visibility="collapsed"
                        )

            # Full data preview
            st.subheader("Full Dataset Preview")
            st.dataframe(df_result, use_container_width=True, height=400)

            # Save and download options
            st.subheader("Save & Download")
            
            if st.button("Save to 'summarised_content' folder", type="primary"):
                try:
                    # Save the processed CSV and log
                    csv_path, log_path = save_summarized_csv(
                        df_result,
                        metadata.model_dump()
                    )

                    # Update metadata with paths
                    metadata.output_csv_path = str(csv_path)
                    metadata.output_log_path = str(log_path)

                    # Save to history
                    history_path = Path("summarised_content") / "history.json"
                    history = CSVSummarizationHistory.from_file(history_path)
                    history.add_file(metadata)
                    history.to_file(history_path)

                    st.success(f"✓ Files saved successfully!")
                    st.info(f"📁 CSV: `{csv_path.name}`\n\n📄 Log: `{log_path.name}`")

                except Exception as e:
                    st.error(f"Error saving files: {e}")
                    logging.error(f"Error saving CSV results: {e}")

            # Download buttons
            col1, col2 = st.columns(2)
            
            with col1:
                csv_data = df_result.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download CSV",
                    data=csv_data,
                    file_name=f"{Path(metadata.source_file).stem}_summarized.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            with col2:
                # Create log content for download
                log_content = f"""{'='*60}
FIRST-PASS SUMMARIZATION LOG
{'='*60}

Source File: {metadata.source_file}
Date: {metadata.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
Content Column: {metadata.content_column}

{'-'*60}
PROCESSING STATISTICS
{'-'*60}
Total Rows: {metadata.total_rows}
Successfully Processed: {metadata.successful}
Failed: {metadata.failed}
Success Rate: {metadata.success_rate:.2f}%

{'-'*60}
DURATION
{'-'*60}
Total Duration: {metadata.duration_seconds:.2f} seconds
Average per Row: {metadata.avg_time_per_row:.2f} seconds

{'='*60}
"""
                st.download_button(
                    label="📥 Download Log",
                    data=log_content,
                    file_name=f"{Path(metadata.source_file).stem}_log.txt",
                    mime="text/plain",
                    use_container_width=True
                )

            # Reset button
            if st.button("Process Another File", use_container_width=True):
                st.session_state.csv_processed_df = None
                st.session_state.csv_metadata = None
                st.rerun()

    with tab2:
        st.subheader("Processing History")
        
        history_path = Path("summarised_content") / "history.json"
        
        if history_path.exists():
            try:
                history = CSVSummarizationHistory.from_file(history_path)
                
                if history.files:
                    st.info(f"Found {len(history.files)} processed file(s)")
                    
                    # Display each file in history
                    for idx, file_meta in enumerate(reversed(history.files), 1):
                        with st.expander(
                            f"**{idx}. {file_meta.source_file}** - {file_meta.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                            expanded=(idx == 1)
                        ):
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Total Rows", file_meta.total_rows)
                                st.metric("Duration", f"{file_meta.duration_seconds:.2f}s")
                            with col2:
                                st.metric("Successful", file_meta.successful)
                                st.metric("Failed", file_meta.failed)
                            with col3:
                                st.metric("Success Rate", f"{file_meta.success_rate:.1f}%")
                                st.metric("Avg per Row", f"{file_meta.avg_time_per_row:.2f}s")
                            
                            # Show file paths if available
                            if file_meta.output_csv_path:
                                st.text(f"📁 CSV: {Path(file_meta.output_csv_path).name}")
                            if file_meta.output_log_path:
                                st.text(f"📄 Log: {Path(file_meta.output_log_path).name}")
                            
                            # Load and preview if files exist
                            if file_meta.output_csv_path and Path(file_meta.output_csv_path).exists():
                                if st.button(f"Preview File", key=f"preview_{idx}"):
                                    try:
                                        preview_df = pd.read_csv(file_meta.output_csv_path)
                                        st.dataframe(preview_df.head(5), use_container_width=True)
                                        
                                        # Download button for historical file
                                        csv_data = preview_df.to_csv(index=False).encode('utf-8')
                                        st.download_button(
                                            label="📥 Download This File",
                                            data=csv_data,
                                            file_name=Path(file_meta.output_csv_path).name,
                                            mime="text/csv",
                                            key=f"download_{idx}"
                                        )
                                    except Exception as e:
                                        st.error(f"Error loading file: {e}")
                else:
                    st.info("No processing history yet. Process a CSV file to see it here.")
            
            except Exception as e:
                st.error(f"Error loading history: {e}")
                logging.error(f"Error loading CSV history: {e}")
        else:
            st.info("No processing history yet. Process a CSV file to see it here.")
            
        # Option to clear history
        if history_path.exists():
            st.divider()
            if st.button("🗑️ Clear History", type="secondary"):
                try:
                    history_path.unlink()
                    st.success("History cleared!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error clearing history: {e}")

# Database View Page
elif page == "Database":
    st.header("📊 Summarization Database")
    st.markdown("Consolidated view of all summarized CSV files")
    
    # Load all CSV files
    summarised_dir = Path("summarised_content")
    
    if not summarised_dir.exists():
        st.warning("No summarised_content folder found. Process some CSV files first!")
        st.stop()
    
    # Find all summarized CSV files
    csv_files = list(summarised_dir.glob("*_summarized_*.csv"))
    
    if not csv_files:
        st.info("No summarized CSV files found. Process some files in First-pass Summarization first!")
        st.stop()
    
    # Statistics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Files", len(csv_files))
    
    # Load and combine all CSVs
    @st.cache_data
    def load_all_csvs(file_list):
        """Load and combine all CSV files"""
        all_data = []
        total_rows = 0
        
        for csv_file in file_list:
            try:
                df = pd.read_csv(csv_file)
                df['source_file'] = csv_file.stem  # Add source file name
                # Extract date from filename (format: name_summarized_YYYYMMDD_HHMMSS)
                parts = csv_file.stem.split('_')
                if len(parts) >= 3:
                    df['processed_date'] = parts[-2] + '_' + parts[-1]
                else:
                    df['processed_date'] = 'unknown'
                all_data.append(df)
                total_rows += len(df)
            except Exception as e:
                st.warning(f"Could not load {csv_file.name}: {e}")
        
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            
            # Merge date and pubDate columns into a single 'date' column
            if 'pubDate' in combined_df.columns and 'date' in combined_df.columns:
                # Prefer pubDate, fallback to date
                combined_df['date'] = combined_df['pubDate'].fillna(combined_df['date'])
                combined_df = combined_df.drop(columns=['pubDate'])
            elif 'pubDate' in combined_df.columns:
                # Rename pubDate to date
                combined_df = combined_df.rename(columns={'pubDate': 'date'})
            
            # Standardize date format to DD MMM YYYY
            if 'date' in combined_df.columns:
                def format_date(date_val):
                    if pd.isna(date_val):
                        return ''
                    try:
                        # Try to parse the date
                        parsed_date = pd.to_datetime(date_val, errors='coerce')
                        if pd.notna(parsed_date):
                            # Format as DD MMM YYYY (e.g., 13 Oct 2025)
                            return parsed_date.strftime('%d %b %Y')
                        return str(date_val)  # Return original if parsing fails
                    except:
                        return str(date_val)
                
                combined_df['date'] = combined_df['date'].apply(format_date)
            
            # Merge tags and classification columns into a single 'categories' column
            if 'tags' in combined_df.columns and 'classification' in combined_df.columns:
                # Combine tags and classification, removing duplicates
                def merge_categories(row):
                    tags = str(row.get('tags', '')).strip() if pd.notna(row.get('tags')) else ''
                    classification = str(row.get('classification', '')).strip() if pd.notna(row.get('classification')) else ''
                    
                    # Split by semicolon and clean
                    all_cats = []
                    if tags:
                        all_cats.extend([t.strip() for t in tags.split(';') if t.strip()])
                    if classification:
                        all_cats.extend([c.strip() for c in classification.split(';') if c.strip()])
                    
                    # Remove duplicates while preserving order
                    seen = set()
                    unique_cats = []
                    for cat in all_cats:
                        if cat.lower() not in seen:
                            seen.add(cat.lower())
                            unique_cats.append(cat)
                    
                    return '; '.join(unique_cats) if unique_cats else ''
                
                combined_df['categories'] = combined_df.apply(merge_categories, axis=1)
                # Drop original columns
                combined_df = combined_df.drop(columns=['tags', 'classification'])
            elif 'tags' in combined_df.columns:
                # Rename tags to categories if only tags exist
                combined_df = combined_df.rename(columns={'tags': 'categories'})
            elif 'classification' in combined_df.columns:
                # Rename classification to categories if only classification exists
                combined_df = combined_df.rename(columns={'classification': 'categories'})
            
            # Sort categories alphabetically within each cell
            if 'categories' in combined_df.columns:
                def sort_categories(cat_string):
                    if pd.isna(cat_string) or not str(cat_string).strip():
                        return ''
                    # Split by semicolon, strip whitespace, sort alphabetically, rejoin
                    cats = [c.strip() for c in str(cat_string).split(';') if c.strip()]
                    sorted_cats = sorted(cats, key=lambda x: x.lower())
                    return '; '.join(sorted_cats)
                
                combined_df['categories'] = combined_df['categories'].apply(sort_categories)
            
            # Merge url and link columns into a single 'url' column
            if 'url' in combined_df.columns and 'link' in combined_df.columns:
                # Prefer url, fallback to link
                combined_df['url'] = combined_df['url'].fillna(combined_df['link'])
                combined_df = combined_df.drop(columns=['link'])
            elif 'link' in combined_df.columns:
                # Rename link to url if only link exists
                combined_df = combined_df.rename(columns={'link': 'url'})
            
            # Fill empty 'source' column with filename-based source
            if 'source' in combined_df.columns and 'source_file' in combined_df.columns:
                def extract_source_from_filename(row):
                    # If source already has a value, keep it
                    if pd.notna(row.get('source')) and str(row.get('source')).strip():
                        return row.get('source')
                    
                    # Extract source from filename
                    source_file = str(row.get('source_file', ''))
                    if source_file:
                        # Remove '_summarized_YYYYMMDD_HHMMSS' part
                        parts = source_file.split('_summarized_')
                        if len(parts) > 0:
                            source_name = parts[0]
                            # Convert underscores to spaces and title case
                            # e.g., "canary_media" -> "Canary Media"
                            formatted_source = source_name.replace('_', ' ').title()
                            return formatted_source
                    
                    return ''
                
                combined_df['source'] = combined_df.apply(extract_source_from_filename, axis=1)
            elif 'source_file' in combined_df.columns:
                # Create source column from filename if it doesn't exist
                def create_source_from_filename(source_file):
                    if pd.isna(source_file):
                        return ''
                    source_file = str(source_file)
                    # Remove '_summarized_YYYYMMDD_HHMMSS' part
                    parts = source_file.split('_summarized_')
                    if len(parts) > 0:
                        source_name = parts[0]
                        # Convert underscores to spaces and title case
                        formatted_source = source_name.replace('_', ' ').title()
                        return formatted_source
                    return ''
                
                combined_df['source'] = combined_df['source_file'].apply(create_source_from_filename)
            
            return combined_df, total_rows
        return None, 0
    
    with st.spinner("Loading all CSV files..."):
        combined_df, total_rows = load_all_csvs(csv_files)
    
    if combined_df is None:
        st.error("Could not load any CSV files!")
        st.stop()
    
    # Deduplicate based on URL
    rows_before_dedup = len(combined_df)
    if 'url' in combined_df.columns:
        # Keep first occurrence, drop duplicates based on URL
        combined_df = combined_df.drop_duplicates(subset=['url'], keep='first')
        rows_after_dedup = len(combined_df)
        duplicates_removed = rows_before_dedup - rows_after_dedup
        
        if duplicates_removed > 0:
            st.info(f"ℹ️ Removed {duplicates_removed} duplicate entries based on URL")
    
    # Reindex starting from 1
    combined_df.index = range(1, len(combined_df) + 1)
    
    # Update metrics
    with col2:
        st.metric("Total Entries", len(combined_df))
    with col3:
        if 'categories' in combined_df.columns:
            unique_categories = combined_df['categories'].str.split(';').explode().str.strip().nunique()
            st.metric("Unique Categories", unique_categories)
    
    st.divider()
    
    # Filters and Search
    st.subheader("🔍 Filters & Search")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Source file filter
        source_files = ["All"] + sorted(combined_df['source_file'].unique().tolist())
        selected_source = st.selectbox("Source File", source_files)
    
    with col2:
        # Category filter - multiselect for individual terms
        if 'categories' in combined_df.columns:
            all_categories = combined_df['categories'].str.split(';').explode().str.strip().unique()
            all_categories = sorted([cat for cat in all_categories if pd.notna(cat) and cat])
            selected_categories = st.multiselect(
                "Filter by Categories",
                options=all_categories,
                help="Select one or more categories to filter"
            )
        else:
            selected_categories = []
    
    with col3:
        # Date range
        if 'processed_date' in combined_df.columns:
            unique_dates = sorted(combined_df['processed_date'].unique())
            if len(unique_dates) > 1:
                selected_date = st.selectbox("Processed Date", ["All"] + unique_dates)
            else:
                selected_date = "All"
        else:
            selected_date = "All"
    
    # Text search
    search_query = st.text_input("🔎 Search in summaries, titles, or content", placeholder="Enter keywords...")
    
    # Apply filters
    filtered_df = combined_df.copy()
    
    if selected_source != "All":
        filtered_df = filtered_df[filtered_df['source_file'] == selected_source]
    
    # Filter by selected categories (multiselect)
    if selected_categories and 'categories' in filtered_df.columns:
        # Check if any of the selected categories are in the row's categories
        def has_selected_category(cat_string):
            if pd.isna(cat_string):
                return False
            row_cats = [c.strip() for c in str(cat_string).split(';')]
            return any(selected_cat in row_cats for selected_cat in selected_categories)
        
        filtered_df = filtered_df[filtered_df['categories'].apply(has_selected_category)]
    
    if selected_date != "All":
        filtered_df = filtered_df[filtered_df['processed_date'] == selected_date]
    
    if search_query:
        # Search across multiple columns
        search_cols = [col for col in ['summary', 'title', 'content', 'content snippet'] if col in filtered_df.columns]
        mask = pd.Series([False] * len(filtered_df))
        for col in search_cols:
            mask |= filtered_df[col].astype(str).str.contains(search_query, case=False, na=False)
        filtered_df = filtered_df[mask]
    
    st.info(f"Showing {len(filtered_df)} of {len(combined_df)} entries")
    
    st.divider()
    
    # Display results
    st.subheader("📋 Results")
    
    # Add custom CSS for text wrapping in dataframe
    st.markdown("""
        <style>
        [data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] div[data-testid="stDataFrameCell"] {
            white-space: normal !important;
            word-wrap: break-word !important;
            overflow-wrap: break-word !important;
            min-height: 40px !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    if len(filtered_df) == 0:
        st.warning("No entries match your filters.")
    else:
        # Display dataframe - exclude specified columns
        exclude_cols = ['source_file', 'processed_date', 'content', 'file', 'file_location', 'filename', 'file_name', 'folder']
        display_df = filtered_df.drop(columns=[col for col in exclude_cols if col in filtered_df.columns])
        
        # Convert categories from semicolon-separated string to list
        if 'categories' in display_df.columns:
            display_df['categories'] = display_df['categories'].apply(
                lambda x: [cat.strip() for cat in str(x).split(';') if cat.strip()] if pd.notna(x) else []
            )
        
        # Configure columns for text wrapping
        column_config = {}
        for col in display_df.columns:
            if col == 'summary':
                column_config[col] = st.column_config.TextColumn(
                    col,
                    width="large",
                    help=f"{col}"
                )
            elif col == 'categories':
                column_config[col] = st.column_config.ListColumn(
                    col,
                    width="medium",
                    help="Category tags"
                )
            elif col == 'url':
                column_config[col] = st.column_config.LinkColumn(
                    col,
                    width="large",
                    help="Click to open article"
                )
            elif col == 'date':
                column_config[col] = st.column_config.TextColumn(
                    col,
                    width="small",
                    help="Publication date"
                )
            elif col == 'source':
                column_config[col] = st.column_config.TextColumn(
                    col,
                    width="small",
                    help="Content source"
                )
            elif col in ['title', 'content snippet']:
                column_config[col] = st.column_config.TextColumn(
                    col,
                    width="medium",
                    help=f"{col}"
                )
            else:
                column_config[col] = st.column_config.TextColumn(
                    col,
                    width="small",
                    help=f"{col}"
                )
        
        st.dataframe(
            display_df, 
            use_container_width=True, 
            height=600,
            column_config=column_config,
            hide_index=False
        )
    
    st.divider()
    
    # Export options
    st.subheader("📥 Export Database")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Export filtered results
        if len(filtered_df) > 0:
            # Convert categories back to semicolon-separated string for export
            export_df = filtered_df.copy()
            if 'categories' in export_df.columns:
                export_df['categories'] = export_df['categories'].apply(
                    lambda x: '; '.join(x) if isinstance(x, list) else x
                )
            
            csv_export = export_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download Filtered Results",
                data=csv_export,
                file_name=f"filtered_database_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    with col2:
        # Export all data
        export_all_df = combined_df.copy()
        if 'categories' in export_all_df.columns:
            export_all_df['categories'] = export_all_df['categories'].apply(
                lambda x: '; '.join(x) if isinstance(x, list) else x
            )
        
        all_csv = export_all_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Complete Database",
            data=all_csv,
            file_name=f"complete_database_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col3:
        # Export to Excel (if openpyxl is installed)
        try:
            from io import BytesIO
            output = BytesIO()
            
            # Prepare dataframes for export
            export_all_df = combined_df.copy()
            if 'categories' in export_all_df.columns:
                export_all_df['categories'] = export_all_df['categories'].apply(
                    lambda x: '; '.join(x) if isinstance(x, list) else x
                )
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                export_all_df.to_excel(writer, index=False, sheet_name='All Data')
                if len(filtered_df) > 0 and len(filtered_df) < len(combined_df):
                    export_filtered_df = filtered_df.copy()
                    if 'categories' in export_filtered_df.columns:
                        export_filtered_df['categories'] = export_filtered_df['categories'].apply(
                            lambda x: '; '.join(x) if isinstance(x, list) else x
                        )
                    export_filtered_df.to_excel(writer, index=False, sheet_name='Filtered')
            
            st.download_button(
                label="Download as Excel",
                data=output.getvalue(),
                file_name=f"database_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except ImportError:
            st.caption("Install openpyxl for Excel export")

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

    **First-pass Summarization:**
    - Upload CSV files with a 'content' column
    - Automatically summarize content using tech-intelligence analysis
    - Track processing statistics and duration
    - Access history of all processed files
    - Download summarized CSV and processing logs

    **Database:**
    - Consolidated view of all summarized CSV files
    - Advanced filtering by category, source, and date
    - Full-text search across summaries and content
    - Multiple view modes (Cards, Table, Detailed)
    - Export filtered or complete database

    ### Features

    - Interactive clarification questions
    - Real-time progress tracking
    - Multi-query web search
    - Structured learning extraction
    - First-pass content summarization with tech-intel focus
    - Download results in JSON, Markdown, and CSV
    - Processing history

    ### Technology Stack

    - **Frontend:** Streamlit
    - **AI Model:** Azure OpenAI (GPT-4.1-mini)
    - **Search Engine:** SearxNG
    - **Validation:** Pydantic
    - **Agent Framework:** Pydantic AI
    - **Data Processing:** Pandas

    ### Usage Tips

    1. Start with a clear, specific research topic
    2. Answer clarification questions thoughtfully
    3. Review SERP queries before search execution
    4. Save results with descriptive filenames
    5. Reprocess results with different learning prompts if needed
    6. For first-pass summarization, ensure your file has a 'content' column
    7. Use the History tab to access previously processed CSV files

    ### File Structure

    - Search results saved to: `data/{filename}.json`
    - Learning reports saved to: `data/{filename}.md`
    - Summarized CSVs saved to: `summarised_content/{filename}.csv`
    - Summarization logs saved to: `summarised_content/{filename}_log.txt`
    - Main logs saved to: `research.log`

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

    **First-pass Summarization:**
    1. Navigate to "First-pass Summarization" tab
    2. Upload CSV file with 'content' column
    3. Preview the data
    4. Click "Start Summarization"
    5. Review results and statistics
    6. Save to folder or download directly
    7. Access processed files in the History tab

    **Database:**
    1. Navigate to "Database" tab
    2. View all summarized entries from all files
    3. Use filters to narrow down results
    4. Search for specific keywords
    5. Switch between view modes
    6. Export filtered or complete data
    7. View analytics and trends
    """)

# Footer
st.sidebar.divider()

# Show processing status in sidebar
if st.session_state.csv_processing:
    st.sidebar.markdown("### 🔄 Processing Status")
    progress = st.session_state.csv_progress
    if progress['total'] > 0:
        progress_pct = progress['current'] / progress['total']
        st.sidebar.progress(progress_pct)
        st.sidebar.caption(f"Summarizing: {progress['current']}/{progress['total']} rows")
        if progress['remaining'] > 0:
            mins = int(progress['remaining'] // 60)
            secs = int(progress['remaining'] % 60)
            st.sidebar.caption(f"⏳ Est. remaining: {mins}m {secs}s" if mins > 0 else f"⏳ Est. remaining: {secs}s")
        st.sidebar.error("⚠️ Stay on First-pass Summarization page!")
    st.sidebar.divider()
    
    # If not on the summarization page, show warning and option to stop
    if page != "First-pass Summarization":
        st.sidebar.warning("Processing was interrupted by navigation.")
        if st.sidebar.button("Clear Interrupted Task"):
            st.session_state.csv_processing = False
            st.session_state.csv_progress = {'current': 0, 'total': 0, 'elapsed': 0, 'remaining': 0}
            st.rerun()

st.sidebar.markdown("### Settings")
st.sidebar.info(f"Session ID: {id(st.session_state)}")

if st.sidebar.button("Clear Session"):
    reset_session_state()
    st.rerun()
