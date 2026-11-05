import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if importlib.util.find_spec("plotly"):
    import networkx as nx
    import plotly.express as px
    from dashboard.graph_explorer import _make_figure, _make_static_figure
else:
    nx = None
    px = None


@unittest.skipUnless(px is not None, "Plotly is installed through requirements.txt")
class DashboardChartTests(unittest.TestCase):
    def test_empty_entity_distribution_can_render_a_donut_figure(self):
        data = [
            {"Type": "Organizations", "Entities": 0},
            {"Type": "People", "Entities": 0},
            {"Type": "Locations", "Entities": 0},
        ]
        figure = px.pie(data, names="Type", values="Entities", hole=0.68)
        self.assertEqual(len(figure.data), 1)

    def test_focused_graph_figure_carries_node_ids_for_selection(self):
        graph = nx.MultiDiGraph()
        graph.add_node("entity:org:acme", node_type="entity", entity_type="ORG", name="Acme")
        graph.add_node("entity:org:beta", node_type="entity", entity_type="ORG", name="Beta")
        graph.add_edge("entity:org:acme", "entity:org:beta", relation="PARTNERED_WITH")
        figure = _make_figure(graph, "entity:org:acme")
        self.assertEqual(len(figure.data), 3)
        self.assertEqual(list(figure.data[-1].customdata), [["entity:org:acme"], ["entity:org:beta"]])

    def test_static_graph_fallback_renders_labeled_nodes_and_edges(self):
        graph = nx.MultiDiGraph()
        graph.add_node("entity:org:acme", node_type="entity", entity_type="ORG", name="Acme")
        graph.add_node("entity:org:beta", node_type="entity", entity_type="ORG", name="Beta")
        graph.add_edge("entity:org:acme", "entity:org:beta", relation="PARTNERED_WITH")
        figure = _make_static_figure(graph, "entity:org:acme")
        self.assertEqual(len(figure.axes), 1)
        self.assertTrue(figure.axes[0].get_legend())


if __name__ == "__main__":
    unittest.main()
