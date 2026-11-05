
import networkx as nx

graph = nx.read_graphml("data/news_graph_rebuilt.graphml")

for node, data in graph.nodes(data=True):
    if (
        data.get("node_type") == "article"
        and node.endswith("14ce0ff99af1e68c50a62fd06085e02a")
    ):
        print("\nARTICLE TEXT:\n")
        print(data.get("text", ""))

        print("\nEXTRACTED ENTITIES:\n")

        for _, target, edge in graph.out_edges(node, data=True):
            if edge.get("relation") == "MENTIONS":
                print(
                    graph.nodes[target].get("name"),
                    "|",
                    graph.nodes[target].get("entity_type")
                )
