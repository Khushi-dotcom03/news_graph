"""Focused, interactive explorer for the saved NetworkX news graph."""

from pathlib import Path

import networkx as nx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAPH_PATH = PROJECT_ROOT / "data" / "news_graph_rebuilt.graphml"
ARTICLE_RELATIONS = {"MENTIONS", "REPORTS_ON"}


def load_graph(path=DEFAULT_GRAPH_PATH):
    """Load the existing GraphML graph, returning an empty graph if absent."""
    path = Path(path)
    if not path.exists():
        return nx.MultiDiGraph()
    return nx.read_graphml(path)


def list_entities(graph, query="", entity_types=None):
    """Return matching entity nodes, sorted by display name."""
    query = (query or "").strip().casefold()
    accepted_types = {"PER", "ORG", "LOC"} if entity_types is None else set(entity_types)
    matches = []
    for node_id, data in graph.nodes(data=True):
        if data.get("node_type") != "entity":
            continue
        entity_type = data.get("entity_type", "")
        if entity_type not in accepted_types:
            continue
        name = data.get("name", str(node_id))
        searchable = f"{name} {data.get('aliases', '')}".casefold()
        if query and query not in searchable:
            continue
        matches.append((node_id, name, entity_type))
    return sorted(matches, key=lambda item: str(item[1]).casefold())


def list_articles(graph, language=None):
    """Return article IDs and labels, optionally restricted by language."""
    articles = []
    for node_id, data in graph.nodes(data=True):
        if data.get("node_type") != "article":
            continue
        if language and data.get("language") != language:
            continue
        title = data.get("title") or node_id
        date = data.get("publication_date", "")
        label = f"{title} · {date}" if date and date != "unknown" else str(title)
        articles.append((node_id, label))
    return sorted(articles, key=lambda item: item[1].casefold())


def _edge_records(graph):
    if graph.is_multigraph():
        for source, target, key, data in graph.edges(keys=True, data=True):
            yield source, target, key, data
    else:
        for source, target, data in graph.edges(data=True):
            yield source, target, 0, data


def _confidence_value(data):
    try:
        return float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def most_connected_entity(graph, entity_types=None):
    """Pick a deterministic entity with relation edges for the initial view."""
    candidates = list_entities(graph, entity_types=entity_types)
    if not candidates:
        return None
    degrees = {node_id: 0 for node_id, _, _ in candidates}
    for source, target, _, data in _edge_records(graph):
        if data.get("relation") in ARTICLE_RELATIONS:
            continue
        if source in degrees:
            degrees[source] += 1
        if target in degrees:
            degrees[target] += 1
    return max(candidates, key=lambda row: degrees[row[0]])[0]


def build_network_overview(
    graph,
    max_nodes=60,
    entity_types=None,
    language=None,
    source_article=None,
    relation_types=None,
    query="",
):
    """Build a larger article/entity network using mentions and relation edges."""
    max_nodes = max(2, int(max_nodes))
    candidates = list_entities(graph, query=query, entity_types=entity_types)
    if not candidates:
        return nx.MultiDiGraph()
    candidate_ids = {node_id for node_id, _, _ in candidates}
    relation_filter = None if relation_types is None else set(relation_types)
    if relation_filter is not None and not relation_filter:
        return nx.MultiDiGraph()
    show_mentions = relation_filter is None or "MENTIONS" in relation_filter
    article_mentions = {}
    relation_degree = {node_id: 0 for node_id in candidate_ids}

    for source, target, _, data in _edge_records(graph):
        relation = data.get("relation", "")
        if relation == "MENTIONS" and graph.nodes.get(source, {}).get("node_type") == "article":
            article = graph.nodes[source]
            if language and article.get("language") != language:
                continue
            if source_article and source != source_article:
                continue
            if target in candidate_ids:
                article_mentions.setdefault(source, set()).add(target)
        elif relation and relation not in ARTICLE_RELATIONS:
            if relation_filter is not None and relation not in relation_filter:
                continue
            provenance_id = data.get("source_article")
            if source_article and provenance_id != source_article:
                continue
            provenance = graph.nodes.get(provenance_id, {}) if provenance_id else {}
            if language and provenance.get("language") != language:
                continue
            if source in relation_degree:
                relation_degree[source] += 1
            if target in relation_degree:
                relation_degree[target] += 1

    mention_count = {node_id: 0 for node_id in candidate_ids}
    for mentioned in article_mentions.values():
        for node_id in mentioned:
            mention_count[node_id] += 1
    ranked_entities = sorted(
        candidates,
        key=lambda row: (-mention_count[row[0]], -relation_degree[row[0]], str(row[1]).casefold()),
    )

    if source_article:
        entity_budget = max_nodes - 1
        preferred_entities = [node_id for node_id in article_mentions.get(source_article, set())]
        chosen_entities = preferred_entities[:entity_budget]
    else:
        entity_budget = max(1, min(len(ranked_entities), max_nodes // 2))
        chosen_entities = [row[0] for row in ranked_entities[:entity_budget]]

    result = nx.MultiDiGraph()
    for node_id in chosen_entities:
        result.add_node(node_id, **graph.nodes[node_id])

    if source_article:
        article_ids = [source_article] if show_mentions and source_article in article_mentions else []
    else:
        article_ids = sorted(
            article_mentions,
            key=lambda article_id: (
                -len(article_mentions[article_id] & set(chosen_entities)),
                str(graph.nodes[article_id].get("publication_date", "")),
                article_id,
            ),
            reverse=True,
        ) if show_mentions else []
    article_slots = max_nodes - result.number_of_nodes()
    selected_articles = article_ids[:article_slots]
    for article_id in selected_articles:
        result.add_node(article_id, **graph.nodes[article_id])
    if show_mentions:
        chosen_entity_ids = set(chosen_entities)
        selected_article_ids = set(selected_articles)
        for source, target, key, data in _edge_records(graph):
            if (
                data.get("relation") == "MENTIONS"
                and source in selected_article_ids
                and target in chosen_entity_ids
            ):
                result.add_edge(source, target, key=key, **data)

    # Retain explicit relationship edges among selected entities and their
    # event nodes when they fit inside the view's node limit.
    for source, target, key, data in _edge_records(graph):
        relation = data.get("relation", "")
        if not relation or relation in ARTICLE_RELATIONS:
            continue
        if relation_filter is not None and relation not in relation_filter:
            continue
        provenance_id = data.get("source_article")
        if source_article and provenance_id != source_article:
            continue
        provenance = graph.nodes.get(provenance_id, {}) if provenance_id else {}
        if language and provenance.get("language") != language:
            continue
        if source not in chosen_entities and target not in chosen_entities:
            continue
        new_nodes = {source, target} - set(result.nodes)
        if len(result.nodes) + len(new_nodes) > max_nodes:
            continue
        for node_id in new_nodes:
            result.add_node(node_id, **graph.nodes[node_id])
        result.add_edge(source, target, key=key, **data)

    return result


def build_focused_graph(
    graph,
    center_id,
    relation_types=None,
    language=None,
    source_article=None,
    max_nodes=30,
):
    """Return a bounded, filtered ego graph around one entity.

    Relation edges connect entities/events. Selecting a source article switches
    the view to the entities explicitly mentioned in that article, retaining
    article nodes so MENTIONS edges are not misrepresented as entity relations.
    """
    if center_id not in graph or graph.nodes[center_id].get("node_type") != "entity":
        return nx.MultiDiGraph()

    accepted_relations = set(relation_types or ())
    candidate_edges = []
    if source_article:
        article_data = graph.nodes.get(source_article, {})
        if language and article_data.get("language") != language:
            return nx.MultiDiGraph()
        for source, target, key, data in _edge_records(graph):
            relation = data.get("relation", "RELATED_TO")
            if relation == "MENTIONS":
                if source != source_article or "MENTIONS" not in accepted_relations:
                    continue
                if target != center_id and graph.nodes[target].get("node_type") != "entity":
                    continue
                candidate_edges.append((source, target, key, data))
                continue
            if relation in ARTICLE_RELATIONS or relation not in accepted_relations:
                continue
            if data.get("source_article") != source_article:
                continue
            if center_id in {source, target}:
                candidate_edges.append((source, target, key, data))
    else:
        for source, target, key, data in _edge_records(graph):
            relation = data.get("relation", "RELATED_TO")
            if relation in ARTICLE_RELATIONS:
                continue
            if relation_types is not None and relation not in accepted_relations:
                continue
            if source_article and data.get("source_article") != source_article:
                continue
            provenance_id = data.get("source_article")
            provenance = graph.nodes.get(provenance_id, {}) if provenance_id else {}
            edge_language = provenance.get("language")
            if language and edge_language != language:
                continue
            if center_id not in {source, target}:
                continue
            candidate_edges.append((source, target, key, data))

    # Keep the strongest/most recent evidence first while respecting the cap.
    candidate_edges.sort(key=lambda item: _confidence_value(item[3]), reverse=True)
    result = nx.MultiDiGraph()
    result.add_node(center_id, **graph.nodes[center_id])
    for source, target, key, data in candidate_edges:
        new_nodes = {source, target} - set(result.nodes)
        if len(result.nodes) + len(new_nodes) > max_nodes:
            continue
        result.add_node(source, **graph.nodes[source])
        result.add_node(target, **graph.nodes[target])
        result.add_edge(source, target, key=key, **data)
    return result


def _make_figure(graph, center_id=None):
    import plotly.graph_objects as go

    positions = nx.spring_layout(graph, seed=42, iterations=80)
    edge_x, edge_y, labels = [], [], []
    for source, target, _, data in _edge_records(graph):
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        labels.append((
            (x0 + x1) / 2,
            (y0 + y1) / 2,
            data.get("relation", "RELATED_TO"),
        ))

    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line={"width": 1.5, "color": "#64748b"},
        hoverinfo="skip",
        showlegend=False,
    ))
    if labels:
        figure.add_trace(go.Scatter(
            x=[item[0] for item in labels],
            y=[item[1] for item in labels],
            text=[item[2] for item in labels],
            mode="text",
            textfont={"size": 9, "color": "#cbd5e1"},
            hoverinfo="skip",
            showlegend=False,
        ))

    colors = {"PER": "#f59e0b", "ORG": "#38bdf8", "LOC": "#34d399", "event": "#c084fc", "article": "#94a3b8"}
    nodes = list(graph.nodes)
    node_types = [graph.nodes[node].get("entity_type") or graph.nodes[node].get("node_type", "other") for node in nodes]
    names = [graph.nodes[node].get("name", str(node)) for node in nodes]
    figure.add_trace(go.Scatter(
        x=[positions[node][0] for node in nodes],
        y=[positions[node][1] for node in nodes],
        mode="markers+text",
        text=names,
        textposition="top center",
        textfont={"size": 11, "color": "#e2e8f0"},
        customdata=[[node] for node in nodes],
        marker={
            "size": [26 if node == center_id else 19 for node in nodes],
            "color": [colors.get(node_type, "#cbd5e1") for node_type in node_types],
            "line": {"width": 1, "color": "#0f172a"},
        },
        hovertemplate="%{text}<br>%{customdata[0]}<extra></extra>",
        showlegend=False,
    ))
    figure.update_layout(
        height=620,
        margin={"l": 10, "r": 10, "t": 20, "b": 10},
        paper_bgcolor="#0b1220",
        plot_bgcolor="#0b1220",
        xaxis={"visible": False},
        yaxis={"visible": False},
        dragmode="pan",
        clickmode="event+select",
    )
    return figure


def _make_static_figure(graph, center_id=None):
    """Create a self-contained Matplotlib rendering as a reliable fallback."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    positions = nx.spring_layout(graph, seed=42, iterations=120)
    figure_width = min(16, max(10, 8 + graph.number_of_nodes() / 12))
    figure_height = min(11, max(7, 5 + graph.number_of_nodes() / 18))
    figure, axis = plt.subplots(figsize=(figure_width, figure_height), facecolor="#0b1220")
    axis.set_facecolor("#0b1220")
    node_types = {
        node: graph.nodes[node].get("entity_type") or graph.nodes[node].get("node_type", "other")
        for node in graph
    }
    palette = {"PER": "#f59e0b", "ORG": "#38bdf8", "LOC": "#34d399", "event": "#c084fc", "article": "#94a3b8"}
    node_colors = [palette.get(node_types[node], "#cbd5e1") for node in graph]
    node_sizes = [
        1000 if node == center_id else
        620 if node_types[node] == "entity" else
        250 if node_types[node] == "article" else 420
        for node in graph
    ]
    mention_edges = [
        (source, target)
        for source, target, _, data in _edge_records(graph)
        if data.get("relation") == "MENTIONS"
    ]
    relation_edges = [
        (source, target)
        for source, target, _, data in _edge_records(graph)
        if data.get("relation") != "MENTIONS"
    ]
    if mention_edges:
        nx.draw_networkx_edges(
            graph,
            positions,
            ax=axis,
            edgelist=mention_edges,
            edge_color="#64748b",
            alpha=0.28,
            arrows=False,
            width=0.8,
        )
    if relation_edges:
        nx.draw_networkx_edges(
            graph,
            positions,
            ax=axis,
            edgelist=relation_edges,
            edge_color="#64748b",
            alpha=0.85,
            arrows=True,
            arrowsize=18,
            width=1.5,
            connectionstyle="arc3,rad=0.06",
        )
    nx.draw_networkx_nodes(
        graph,
        positions,
        ax=axis,
        node_color=node_colors,
        node_size=node_sizes,
        edgecolors="#e2e8f0",
        linewidths=1.2,
    )
    labels = {}
    for node in graph:
        data = graph.nodes[node]
        name = data.get("name", str(node))
        if data.get("node_type") == "article":
            name = str(name).strip()
            labels[node] = name[:22].rstrip() + ("…" if len(name) > 22 else "")
        else:
            labels[node] = name
    nx.draw_networkx_labels(
        graph,
        positions,
        labels=labels,
        ax=axis,
        font_size=9 if graph.number_of_nodes() <= 24 else 7,
        font_color="#f8fafc",
        font_weight="bold",
    )
    edge_labels = {}
    for source, target, _, data in _edge_records(graph):
        relation = data.get("relation", "RELATED_TO")
        if relation != "MENTIONS":
            edge_labels.setdefault((source, target), relation)
    if edge_labels and len(edge_labels) <= 30:
        nx.draw_networkx_edge_labels(
            nx.DiGraph(graph),
            positions,
            edge_labels=edge_labels,
            ax=axis,
            font_size=8,
            font_color="#dbeafe",
            rotate=False,
            label_pos=0.5,
            bbox={"alpha": 0.75, "color": "#0b1220", "pad": 1},
        )
    legend = [
        Line2D([0], [0], marker="o", color="none", label=label, markerfacecolor=color, markersize=9)
        for label, color in [("Organization", palette["ORG"]), ("Person", palette["PER"]), ("Location", palette["LOC"]), ("Article", palette["article"]), ("Event", palette["event"])]
    ]
    axis.legend(handles=legend, loc="upper left", frameon=False, labelcolor="#cbd5e1", ncol=2)
    axis.axis("off")
    figure.tight_layout(pad=1.3)
    return figure


def render_graph_explorer(st, graph):
    """Render the interactive graph view inside an existing Streamlit page."""
    st.caption("Network Overview shows article–entity mentions and relationships. Focused Entity zooms in on one entity.")
    if not graph.number_of_nodes():
        st.info(f"No graph data found at {DEFAULT_GRAPH_PATH}. Run the news update first.")
        return

    pending_focus = st.session_state.pop("pending_focused_entity", None)
    if pending_focus in graph:
        st.session_state["focused_entity"] = pending_focus
        st.session_state["graph_scope"] = "Focused Entity"

    with st.sidebar:
        st.header("Explore")
        graph_scope = st.radio(
            "Graph view",
            ["Network Overview", "Focused Entity"],
            key="graph_scope",
        )
        query = st.text_input("Search entities", placeholder="e.g. Tata Motors")
        entity_types = st.multiselect("Entity types", ["ORG", "PER", "LOC"], default=["ORG", "PER", "LOC"])
        matches = list_entities(graph, query, entity_types)
        if not matches:
            st.info("No entities match this search and filter.")
            return
        labels = {}
        for node_id, name, entity_type in matches:
            label = f"{name} · {entity_type}"
            if label in labels:
                label = f"{label} · {node_id}"
            labels[label] = node_id
        label_options = list(labels)
        center_id = None
        if graph_scope == "Focused Entity":
            stored = st.session_state.get("focused_entity")
            preferred = most_connected_entity(graph, entity_types)
            has_any_relation = any(
                data.get("relation") not in ARTICLE_RELATIONS
                for _, _, _, data in _edge_records(graph)
            )
            if stored in graph and stored in labels.values() and (
                not has_any_relation or any(
                    stored in {source, target} and data.get("relation") not in ARTICLE_RELATIONS
                    for source, target, _, data in _edge_records(graph)
                )
            ):
                current_label = next(label for label, node_id in labels.items() if node_id == stored)
            else:
                current_label = next(label for label, node_id in labels.items() if node_id == preferred)
            selected_label = st.selectbox("Focus entity", label_options, index=label_options.index(current_label))
            center_id = labels[selected_label]
            st.session_state["focused_entity"] = center_id

        languages = ["All", "en", "hi"]
        language_label = st.selectbox("Article language", languages)
        language = None if language_label == "All" else language_label
        articles = list_articles(graph, language)
        article_labels = dict(articles)
        article_ids = [None] + [node_id for node_id, _ in articles]
        source_article = st.selectbox(
            "Source article",
            article_ids,
            format_func=lambda node_id: "All source articles" if node_id is None else article_labels[node_id],
        )

        available_relations = sorted({
            data.get("relation", "RELATED_TO")
            for _, _, _, data in _edge_records(graph)
            if data.get("relation") != "REPORTS_ON"
        })
        relation_types = st.multiselect("Relationship types", available_relations, default=available_relations)
        max_nodes = st.slider("Maximum nodes", min_value=5, max_value=150, value=60)

    if graph_scope == "Network Overview":
        focused = build_network_overview(
            graph,
            max_nodes=max_nodes,
            entity_types=entity_types,
            language=language,
            source_article=source_article,
            relation_types=relation_types,
            query=query,
        )
        st.markdown("### Network Overview")
        st.caption(f"Showing a connected sample of {focused.number_of_nodes()} nodes and {focused.number_of_edges()} edges. Click a node in the interactive view to focus it.")
    else:
        focused = build_focused_graph(
            graph,
            center_id,
            relation_types=relation_types,
            language=language,
            source_article=source_article,
            max_nodes=max_nodes,
        )
        st.markdown(f"### {graph.nodes[center_id].get('name', center_id)}")
        st.caption("Focused on one entity. Click a connected node in the interactive view to change focus.")

    if focused.number_of_nodes() <= 1:
        st.info("No matching connections for these filters. Try another relationship type or source article.")
    else:
        st.pyplot(_make_static_figure(focused, center_id), use_container_width=True, clear_figure=True)
        with st.expander("Interactive graph · click a node to refocus"):
            try:
                event = st.plotly_chart(
                    _make_figure(focused, center_id),
                    key="knowledge_graph",
                    on_select="rerun",
                    selection_mode="points",
                    config={"displayModeBar": True, "scrollZoom": True},
                    width="stretch",
                    alt="Interactive focused knowledge graph showing connected entities",
                )
                points = event.selection.get("points", []) if event else []
                if points:
                    selected_node = points[-1].get("customdata", [None])[0]
                    if selected_node in graph and graph.nodes[selected_node].get("node_type") == "entity" and selected_node != center_id:
                        st.session_state["pending_focused_entity"] = selected_node
                        st.rerun()
            except (ImportError, TypeError, ValueError) as error:
                st.info(f"Interactive chart unavailable in this Streamlit environment: {error}")

    st.subheader("Relationship evidence")
    edge_records = [
        item for item in _edge_records(focused)
        if item[3].get("relation") != "MENTIONS"
    ][:30]
    if not edge_records:
        st.caption("Evidence will appear here when a relationship matches the selected filters.")
    for index, (source, target, _, data) in enumerate(edge_records, start=1):
        source_name = graph.nodes[source].get("name", source)
        target_name = graph.nodes[target].get("name", target)
        relation = data.get("relation", "RELATED_TO")
        with st.expander(f"{source_name} — {relation} → {target_name}"):
            st.write(data.get("evidence") or "No evidence sentence is stored for this edge.")
            article_id = data.get("source_article") or (source if graph.nodes[source].get("node_type") == "article" else None)
            if article_id in graph:
                article = graph.nodes[article_id]
                st.caption(f"Source: {article.get('source', 'unknown')} · {article.get('publication_date', 'unknown')} · {article.get('title', article_id)}")
            if data.get("confidence") not in (None, ""):
                st.caption(f"Rule confidence: {float(data['confidence']):.2f}")


def main():
    import streamlit as st

    st.set_page_config(page_title="NEWSGRAPH AI · Graph Explorer", page_icon="◉", layout="wide")
    try:
        graph = load_graph()
    except (OSError, ValueError, nx.NetworkXException) as error:
        st.error(f"Could not read the knowledge graph: {error}")
        return
    st.title("NEWSGRAPH AI")
    render_graph_explorer(st, graph)


if __name__ == "__main__":
    main()
