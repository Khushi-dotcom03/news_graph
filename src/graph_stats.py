
import networkx as nx
from collections import Counter

graph = nx.read_graphml("data/news_graph_rebuilt.graphml")

print("NODE COUNTS")
print(Counter(
    data.get("node_type", "unknown")
    for _, data in graph.nodes(data=True)
))

print("\nRELATION COUNTS")
print(Counter(
    data.get("relation", "unknown")
    for _, _, data in graph.edges(data=True)
))

print("\nTOP 10 ARTICLES BY ENTITY COUNT")

for node, data in graph.nodes(data=True):
    if data.get("node_type") == "article":
        count = sum(
            1 for _, target, edge in graph.out_edges(
                node, data=True
            )
            if edge.get("relation") == "MENTIONS"
        )
        print(node, ":", count)
