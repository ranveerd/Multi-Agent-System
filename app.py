import time
from datetime import datetime

import streamlit as st
from dotenv import find_dotenv, load_dotenv

# Load API keys from the .env file
load_dotenv(find_dotenv())

from agents import build_search_agent, build_reader_agent, writer_chain, critic_chain  # noqa: E402

# page setup
st.set_page_config(
    page_title="Research Desk",
    page_icon="🔎",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container { max-width: 1100px; padding-top: 2.5rem; }
        h1 { letter-spacing: -0.02em; margin-bottom: 0.2rem; }
        .subtitle { color: #6b7280; font-size: 1.05rem; margin-bottom: 1.5rem; }
        div[data-testid="stStatusWidget"] { border-radius: 10px; }
        .step-meta { color: #6b7280; font-size: 0.85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

EXAMPLE_TOPICS = [
    "Impact of generative AI on software jobs",
    "Latest breakthroughs in solid-state batteries",
    "How does India's UPI compare to other payment systems?",
]

# helpers
def to_text(content) -> str:
    """LangChain message content can be a str or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p)
    return str(content)


def run_pipeline(topic: str) -> dict:
    """Runs the 4 steps one by one and shows live progress in the UI."""
    state = {"topic": topic, "timings": {}}
    progress = st.progress(0.0, text="Starting…")

    # Step 1 - Search agent
    with st.status("Searching the web…", expanded=True) as status:
        t0 = time.time()
        st.write("The search agent is looking for recent, reliable sources.")
        search_agent = build_search_agent()
        result = search_agent.invoke(
            {
                "messages": [
                    (
                        "user",
                        f"Find recent, reliable and detailed information about: {topic}",
                    )
                ]
            }
        )
        state["search_results"] = to_text(result["messages"][-1].content)
        state["timings"]["Search"] = time.time() - t0
        status.update(label="Search complete", state="complete", expanded=False)
    progress.progress(0.25, text="Search complete")

    # Step 2 - Reader agent
    with st.status("Reading the best source…", expanded=True) as status:
        t0 = time.time()
        st.write("The reader agent is picking the most relevant URL and scraping it.")
        reader_agent = build_reader_agent()
        result = reader_agent.invoke(
            {
                "messages": [
                    (
                        "user",
                        f"Based on the following search results about '{topic}', "
                        f"pick the most relevant URL and scrape it for deeper content.\n\n"
                        f"Search Results:\n{state['search_results'][:800]}",
                    )
                ]
            }
        )
        state["scraped_content"] = to_text(result["messages"][-1].content)
        state["timings"]["Read"] = time.time() - t0
        status.update(label="Source read", state="complete", expanded=False)
    progress.progress(0.5, text="Source read")

    # Step 3 - Writer chain
    with st.status("Writing the report…", expanded=True) as status:
        t0 = time.time()
        st.write("The writer is drafting a report from the research.")
        research_combined = (
            f"SEARCH RESULT : \n {state['search_results']} \n\n"
            f"DETAILED SCRAPED CONTENT : \n {state['scraped_content']}"
        )
        state["report"] = to_text(
            writer_chain.invoke({"topic": topic, "research": research_combined})
        )
        state["timings"]["Write"] = time.time() - t0
        status.update(label="Report written", state="complete", expanded=False)
    progress.progress(0.75, text="Report written")

    # Step 4 - Critic chain 
    with st.status("Reviewing the report…", expanded=True) as status:
        t0 = time.time()
        st.write("The critic is checking the report and preparing feedback.")
        state["feedback"] = to_text(critic_chain.invoke({"report": state["report"]}))
        state["timings"]["Review"] = time.time() - t0
        status.update(label="Review complete", state="complete", expanded=False)
    progress.progress(1.0, text="Done")

    state["finished_at"] = datetime.now().strftime("%d %b %Y, %H:%M")
    return state


def slugify(text: str) -> str:
    keep = "".join(c if c.isalnum() else "-" for c in text.lower())
    return "-".join(filter(None, keep.split("-")))[:50] or "report"


# sidebar
with st.sidebar:
    st.header("How it works")
    st.markdown(
        """
        1. **Search agent** finds recent sources
        2. **Reader agent** scrapes the best one
        3. **Writer** drafts the report
        4. **Critic** reviews it and gives feedback
        """
    )
    st.divider()
    st.caption("Try an example")
    for i, example in enumerate(EXAMPLE_TOPICS):
        if st.button(example, key=f"example_{i}", use_container_width=True):
            st.session_state["topic_input"] = example
    st.divider()
    if st.button("Clear results", use_container_width=True):
        st.session_state.pop("result", None)
        st.rerun()

# main
st.title("Research Desk")
st.markdown(
    '<div class="subtitle">Enter a topic. Four AI agents search, read, write and review a report for you.</div>',
    unsafe_allow_html=True,
)

topic = st.text_input(
    "Research topic",
    key="topic_input",
    placeholder="e.g. Impact of generative AI on software jobs",
)

run_clicked = st.button("Run research", type="primary", disabled=not topic.strip())

if run_clicked:
    st.session_state.pop("result", None)
    try:
        st.session_state["result"] = run_pipeline(topic.strip())
    except Exception as e:
        st.error(
            f"The pipeline stopped with an error: {e}\n\n"
            "Check that your API keys are set in the .env file and that you have internet access."
        )
        with st.expander("Error details"):
            st.exception(e)

result = st.session_state.get("result")

if result:
    st.divider()
    total = sum(result["timings"].values())
    st.markdown(
        f"**{result['topic']}**  \n"
        f"<span class='step-meta'>Finished {result['finished_at']} · took {total:.0f}s "
        f"({', '.join(f'{k} {v:.0f}s' for k, v in result['timings'].items())})</span>",
        unsafe_allow_html=True,
    )

    tab_report, tab_feedback, tab_sources = st.tabs(
        ["Report", "Critic feedback", "Sources & raw research"]
    )

    with tab_report:
        st.markdown(result["report"])
        st.download_button(
            "Download report (.md)",
            data=result["report"],
            file_name=f"{slugify(result['topic'])}.md",
            mime="text/markdown",
        )

    with tab_feedback:
        st.markdown(result["feedback"])

    with tab_sources:
        with st.expander("Search results", expanded=False):
            st.markdown(result["search_results"])
        with st.expander("Scraped content", expanded=False):
            st.markdown(result["scraped_content"])
else:
    st.info("Your report will appear here once the agents finish.")