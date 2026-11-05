"""NEWSGRAPH AI dashboard: overview and interactive graph explorer."""

from datetime import datetime, timezone

import plotly.express as px
import streamlit as st
import networkx as nx

from dashboard.data import graph_summary, load_dashboard_graph
from dashboard.graph_explorer import (
    _edge_records,
    _make_static_figure,
    build_network_overview,
    list_entities,
    most_connected_entity,
    render_graph_explorer,
)
from dashboard.insights import entity_insights, trending_entities


st.set_page_config(
    page_title="NEWSGRAPH AI",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
:root { --ink: #e8eef8; --muted: #93a4bd; --panel: #111c2e; --line: #24344b; }
.stApp { background: radial-gradient(ellipse at 70% -20%, #193252 0%, #0b1220 52%); color: var(--ink); font-family: 'Segoe UI', sans-serif; }
h1, h2, h3 { font-family: 'Segoe UI', sans-serif !important; letter-spacing: -0.025em; }
section[data-testid="stSidebar"] { background: #0d1727; border-right: 1px solid var(--line); }
div[data-testid="stMetric"] { background: linear-gradient(145deg, #142239, #101a2a); border: 1px solid var(--line); border-radius: 15px; padding: 15px 18px; }
div[data-testid="stMetricLabel"] { color: var(--muted); }
div[data-testid="stMetricValue"] { color: var(--ink); font-family: 'Segoe UI', sans-serif; }
.hero { padding: 1.25rem 1.5rem; border: 1px solid #29415f; border-radius: 18px; background: linear-gradient(110deg, rgba(25,49,78,.95), rgba(17,28,46,.84)); margin-bottom: 1.1rem; }
.eyebrow { color: #78c8ff; font-size: .78rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
.hero p { color: #a9bad0; margin: .3rem 0 0; }
.panel-title { color: #dce8f7; font-weight: 700; margin: .25rem 0 .7rem; }
div[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)


def _format_update_time(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc).strftime("%b %d, %Y · %H:%M UTC")
    except (TypeError, ValueError):
        return "Time unavailable"


def _overview(graph, summary):
    st.markdown("""
    <div class="hero">
      <div class="eyebrow">Multilingual news intelligence</div>
      <h1>Discover the connections behind the news.</h1>
      <p>Explore English and Hindi reporting through an evidence-linked knowledge graph.</p>
    </div>
    """, unsafe_allow_html=True)

    metrics = st.columns(4)
    for column, label, value in zip(
        metrics,
        ["Articles", "Entities", "Relationships", "Events"],
        [summary["articles"], summary["entities"], summary["relationships"], summary["events"]],
    ):
        column.metric(label, f"{value:,}")

    focus_id = most_connected_entity(graph)
    if focus_id:
        relation_types = {
            data.get("relation", "RELATED_TO")
            for _, _, _, data in _edge_records(graph)
            if data.get("relation") != "REPORTS_ON"
        }
        preview = build_network_overview(
            graph,
            max_nodes=50,
            entity_types={"PER", "ORG", "LOC"},
            relation_types=relation_types,
        )
        if preview.number_of_nodes() > 1:
            st.markdown("### Knowledge graph overview")
            st.caption(
                f"Showing {preview.number_of_nodes()} connected articles, entities, and events · "
                "Open Graph Explorer for larger samples and click-to-focus navigation."
            )
            st.pyplot(
                _make_static_figure(preview, focus_id if focus_id in preview else None),
                use_container_width=True,
                clear_figure=True,
            )
        else:
            st.info("No evidence-backed relationships are available for the graph preview yet.")
    else:
        st.info("The graph preview will appear when entity and relation nodes are available.")

    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown('<div class="panel-title">Article language</div>', unsafe_allow_html=True)
        lang_values = [
            {"Language": "English", "Articles": summary["languages"].get("en", 0)},
            {"Language": "Hindi", "Articles": summary["languages"].get("hi", 0)},
        ]
        chart = px.bar(
            lang_values,
            x="Language",
            y="Articles",
            color="Language",
            color_discrete_map={"English": "#38bdf8", "Hindi": "#a78bfa"},
            text="Articles",
        )
        chart.update_layout(
            height=300,
            margin={"l": 10, "r": 10, "t": 10, "b": 10},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#cbd5e1",
            showlegend=False,
            yaxis={"gridcolor": "#24344b", "title": ""},
            xaxis={"title": ""},
        )
        if sum(item["Articles"] for item in lang_values):
            st.plotly_chart(chart, width="stretch", config={"displayModeBar": False}, key="language_chart")
        else:
            st.info("No articles have language metadata yet.")

    with right:
        st.markdown('<div class="panel-title">Entity types</div>', unsafe_allow_html=True)
        type_values = [
            {"Type": label, "Entities": summary["entity_types"].get(key, 0)}
            for key, label in [("ORG", "Organizations"), ("PER", "People"), ("LOC", "Locations")]
        ]
        chart = px.pie(
            type_values,
            names="Type",
            values="Entities",
            hole=0.68,
            color="Type",
            color_discrete_map={"Organizations": "#38bdf8", "People": "#f59e0b", "Locations": "#34d399"},
        )
        chart.update_layout(
            height=300,
            margin={"l": 10, "r": 10, "t": 10, "b": 10},
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#cbd5e1",
            legend={"orientation": "h", "y": -0.05},
        )
        if sum(item["Entities"] for item in type_values):
            st.plotly_chart(chart, width="stretch", config={"displayModeBar": False}, key="entity_type_chart")
        else:
            st.info("No typed entities are available to chart yet.")

    st.markdown("### Entity activity")
    search_col, type_col, lang_col = st.columns([2, 1, 1])
    with search_col:
        query = st.text_input("Find an entity", placeholder="Search names and aliases")
    with type_col:
        selected_type = st.selectbox("Type", ["All", "ORG", "PER", "LOC"], key="overview_entity_type")
    with lang_col:
        selected_language = st.selectbox("Mentioned in", ["All", "en", "hi"], key="overview_entity_language")

    rows = summary["top_entities"]
    if selected_type != "All":
        rows = [row for row in rows if row["type"] == selected_type]
    if selected_language != "All":
        rows = [row for row in rows if selected_language in row["languages"]]
    if query:
        query_folded = query.casefold()
        rows = [
            row for row in rows
            if query_folded in str(row["name"]).casefold()
            or query_folded in str(graph.nodes[row["id"]].get("aliases", "")).casefold()
        ]
    st.dataframe(
        [{"Entity": row["name"], "Type": row["type"], "Articles": row["mentions"]} for row in rows[:10]],
        hide_index=True,
        use_container_width=True,
        height=360,
    )

    article_col, update_col = st.columns([1.25, 1], gap="large")
    with article_col:
        st.markdown("### Recent articles")
        article_rows = summary["recent_articles"][:8]
        st.dataframe(
            [{
                "Title": row["title"],
                "Language": row["language"],
                "Source": row["source"],
                "Published": row["publication_date"],
                "URL": row["url"],
            } for row in article_rows],
            hide_index=True,
            use_container_width=True,
            height=340,
            column_config={"URL": st.column_config.LinkColumn("URL", display_text="Open article")},
        )
        if not article_rows:
            st.info("No articles have been saved yet.")

    with update_col:
        st.markdown("### Recent graph updates")
        updates = summary["graph_updates"]
        if updates:
            st.dataframe(
                [{
                    "Updated": _format_update_time(item.get("timestamp")),
                    "New articles": item.get("added_articles", 0),
                    "Fetched": item.get("fetched_articles", 0),
                    "Skipped": item.get("skipped_articles", 0),
                } for item in updates],
                hide_index=True,
                use_container_width=True,
                height=340,
            )
        else:
            st.info("No saved ingestion history yet. Update history will appear after the next pipeline run.")


def _entity_insights_page(graph):
    st.markdown("### Entity insights")
    st.caption("Inspect the articles, relationships, and dated activity associated with one entity.")
    left, middle, right = st.columns([2, 1, 1])
    with left:
        query = st.text_input("Search entity", placeholder="Search a name or alias", key="insight_search")
    with middle:
        entity_type = st.selectbox("Entity type", ["All", "ORG", "PER", "LOC"], key="insight_type")
    with right:
        window_days = st.selectbox("Trend window", [7, 30, 90], index=1, format_func=lambda days: f"Last {days} days")

    types = {"PER", "ORG", "LOC"} if entity_type == "All" else {entity_type}
    matches = list_entities(graph, query, types)
    if not matches:
        st.info("No entities match this search and type filter.")
        return
    labels = {f"{name} · {kind}": node_id for node_id, name, kind in matches}
    selected_label = st.selectbox("Select entity", list(labels), key="insight_entity")
    insights = entity_insights(graph, labels[selected_label], window_days=window_days)
    if not insights:
        st.info("Insights are unavailable for this entity.")
        return

    st.markdown(f"# {insights['name']}")
    aliases = insights["aliases"]
    st.caption(f"{insights['type']} · {insights['id']}" + (f" · Aliases: {' · '.join(aliases)}" if aliases else " · No aliases stored"))
    metrics = st.columns(4)
    values = [
        ("Articles mentioning", insights["article_count"]),
        ("Connected entities", len(insights["connected_entities"])),
        ("Relationships", len(insights["relationships"])),
        (f"Mentions · {window_days} days", insights["recent_mentions"]),
    ]
    for column, (label, value) in zip(metrics, values):
        column.metric(label, f"{value:,}")

    trend_col, trending_col = st.columns([1.35, 1], gap="large")
    with trend_col:
        st.markdown("### Mention activity")
        if insights["dated_mentions"]:
            trend = px.line(
                insights["timeseries"],
                x="date",
                y="mentions",
                markers=True,
                labels={"date": "Publication date", "mentions": "Articles"},
            )
            trend.update_layout(
                height=300,
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#cbd5e1",
                xaxis={"gridcolor": "#24344b"},
                yaxis={"gridcolor": "#24344b", "rangemode": "tozero"},
            )
            st.plotly_chart(trend, width="stretch", config={"displayModeBar": False}, key="entity_trend")
        else:
            st.info("No publication dates fall inside this trend window, so no trend is shown.")
    with trending_col:
        st.markdown(f"### Trending entities · {window_days} days")
        trends = trending_entities(graph, window_days=window_days, limit=8)
        st.dataframe(
            [{"Entity": row["name"], "Type": row["type"], "Articles": row["articles"]} for row in trends],
            hide_index=True,
            use_container_width=True,
            height=300,
        )
        if not trends:
            st.caption("No entities have dated mentions in this window.")

    connected_col, articles_col = st.columns([1, 1.2], gap="large")
    with connected_col:
        st.markdown("### Connected entities")
        st.dataframe(
            [{"Entity": row["name"], "Type": row["type"], "Relationship": row["relation"]} for row in insights["connected_entities"]],
            hide_index=True,
            use_container_width=True,
            height=320,
        )
        if not insights["connected_entities"]:
            st.caption("No direct entity-to-entity connections are stored for this entity.")
    with articles_col:
        st.markdown("### Articles mentioning this entity")
        st.dataframe(
            [{"Title": row["title"], "Language": row["language"], "Source": row["source"], "Published": row["publication_date"], "URL": row["url"]} for row in insights["articles"]],
            hide_index=True,
            use_container_width=True,
            height=320,
            column_config={"URL": st.column_config.LinkColumn("URL", display_text="Open article")},
        )
        if not insights["articles"]:
            st.caption("No article mention edges are stored for this entity.")

    st.markdown("### Relationship evidence")
    if not insights["relationships"]:
        st.info("No extracted relationships are stored for this entity yet.")
    for row in insights["relationships"]:
        with st.expander(f"{row['subject']} — {row['predicate']} → {row['object']}"):
            st.write(row["evidence"] or "No evidence sentence is stored for this relationship.")
            article = row["article"]
            if article:
                st.caption(f"{article['source']} · {article['publication_date']} · {article['title']}")
                if article["url"]:
                    st.markdown(f"[Open source article]({article['url']})")
            else:
                st.caption("Source article metadata is unavailable for this relationship.")
            if row["confidence"] not in (None, ""):
                try:
                    st.caption(f"Rule confidence: {float(row['confidence']):.2f}")
                except (TypeError, ValueError):
                    pass


try:
    graph = load_dashboard_graph()
    summary = graph_summary(graph)
except (OSError, ValueError, RuntimeError, nx.NetworkXException) as error:
    st.error(f"Could not load the knowledge graph: {error}")
    st.stop()

with st.sidebar:
    st.markdown("## ◉ NEWSGRAPH AI")
    st.caption("Discover the connections behind the news.")
    page = st.radio("Workspace", ["Overview", "Graph Explorer", "Entity Insights"], label_visibility="collapsed")
    st.divider()
    st.caption(f"Graph · {graph.number_of_nodes():,} nodes · {graph.number_of_edges():,} edges")

if page == "Overview":
    _overview(graph, summary)
elif page == "Graph Explorer":
    st.title("Knowledge graph explorer")
    render_graph_explorer(st, graph)
else:
    _entity_insights_page(graph)
