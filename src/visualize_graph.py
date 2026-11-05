
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from pathlib import Path
import os
import re

GRAPH_PATH = Path("data/news_graph_rebuilt.graphml")
OUTPUT_DIR = Path("data")

# --------------------------------
# 1. Hindi font configuration
# --------------------------------

font_paths = [
    r"C:\Windows\Fonts\mangal.ttf",
    r"C:\Windows\Fonts\Nirmala.ttf",
    r"C:\Windows\Fonts\NirmalaUI.ttf",
]

hindi_font = None

for path in font_paths:
    if os.path.exists(path):
        font_manager.fontManager.addfont(path)
        hindi_font = font_manager.FontProperties(fname=path).get_name()
        break

if hindi_font:
    plt.rcParams["font.family"] = hindi_font
    print("Hindi font:", hindi_font)
else:
    plt.rcParams["font.family"] = "DejaVu Sans"
    print("Hindi font not found. Hindi labels may show boxes.")

# --------------------------------
# 2. Load graph
# --------------------------------

graph = nx.read_graphml(GRAPH_PATH)
G = nx.DiGraph()

for node, data in graph.nodes(data=True):
    G.add_node(node, **data)

for source, target, data in graph.edges(data=True):
    relation = data.get("relation", "RELATED_TO")

    if G.has_edge(source, target):
        old = G[source][target]["relation"]
        G[source][target]["relation"] = old + ", " + relation
    else:
        G.add_edge(source, target, relation=relation)

node_types = nx.get_node_attributes(G, "node_type")

# --------------------------------
# 3. Common drawing function
# --------------------------------

def draw_graph(H, output_name, title, label_limit=15):

    if H.number_of_nodes() == 0:
        print("No nodes to draw:", output_name)
        return

    types = nx.get_node_attributes(H, "node_type")

    articles = [n for n in H if types.get(n) == "article"]
    entities = [n for n in H if types.get(n) == "entity"]
    events = [n for n in H if types.get(n) == "event"]

    # Label only important entities
    entities.sort(
        key=lambda n: H.degree(n),
        reverse=True
    )

    labels = {}

    for node in entities[:label_limit]:
        labels[node] = H.nodes[node].get("name", node)

    for node in events:
        labels[node] = H.nodes[node].get("name", "Event")

    # Node colors and sizes
    colors = []
    sizes = []

    for node in H:
        node_type = types.get(node)

        if node_type == "article":
            colors.append("skyblue")
            sizes.append(350)

        elif node_type == "entity":
            colors.append("lightgreen")
            sizes.append(250 + 70 * min(H.degree(node), 5))

        elif node_type == "event":
            colors.append("orange")
            sizes.append(800)

        else:
            colors.append("lightgray")
            sizes.append(250)

    fig, ax = plt.subplots(figsize=(18, 13))

    # Spring layout
    pos = nx.spring_layout(
        H,
        k=1.8 / (H.number_of_nodes() ** 0.5),
        iterations=250,
        seed=42
    )

    nx.draw_networkx_edges(
        H,
        pos,
        ax=ax,
        edge_color="gray",
        alpha=0.22,
        arrows=True,
        arrowsize=10,
        width=0.8
    )

    nx.draw_networkx_nodes(
        H,
        pos,
        ax=ax,
        node_color=colors,
        node_size=sizes,
        alpha=0.85
    )

    nx.draw_networkx_labels(
        H,
        pos,
        labels=labels,
        ax=ax,
        font_size=9,
        font_weight="bold"
    )

    legend = [
        Line2D([0], [0], marker="o", color="w",
               label="Articles", markerfacecolor="skyblue",
               markersize=11),
        Line2D([0], [0], marker="o", color="w",
               label="Entities", markerfacecolor="lightgreen",
               markersize=11),
        Line2D([0], [0], marker="o", color="w",
               label="Events", markerfacecolor="orange",
               markersize=11)
    ]

    ax.legend(handles=legend, loc="upper right")
    ax.set_title(title, fontsize=17, fontweight="bold")
    ax.axis("off")

    plt.tight_layout()

    output_path = OUTPUT_DIR / output_name

    plt.savefig(
        output_path,
        dpi=250,
        bbox_inches="tight"
    )

    plt.close(fig)

    print("Saved:", output_path)
    print(
        "Nodes:", H.number_of_nodes(),
        "| Edges:", H.number_of_edges()
    )


# --------------------------------
# 4. Full knowledge graph
# --------------------------------

draw_graph(
    G,
    "full_graph.png",
    "Self-Updating Multilingual News Knowledge Graph",
    label_limit=12
)

# --------------------------------
# 5. Focused graph: Tata Motors
# --------------------------------

target = None

for node, data in G.nodes(data=True):
    if (
        data.get("node_type") == "entity"
        and re.sub(r"\s+", " ", data.get("name", "")).strip().lower()
        == "tata motors"
    ):
        target = node
        break

if target:

    # Get connected nodes within two hops
    focused = nx.ego_graph(
        G,
        target,
        radius=2,
        undirected=True
    )

    draw_graph(
        focused,
        "focused_graph.png",
        "Focused Knowledge Graph: Tata Motors",
        label_limit=30
    )

else:
    print("Tata Motors entity not found in graph.")

print("\nBoth visualizations completed!")
