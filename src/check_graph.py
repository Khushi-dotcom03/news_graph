
import networkx as nx

graph = nx.read_graphml("data/news_graph.graphml")

print("\n--- NODES ---")
for node, data in graph.nodes(data=True):
    print(node, data)

print("\n--- EDGES ---")
for source, target, data in graph.edges(data=True):
    print(source, "--", data.get("relation"), "-->", target)
