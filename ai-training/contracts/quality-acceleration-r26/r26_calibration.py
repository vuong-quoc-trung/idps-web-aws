"""Namespace parent tensors before reusing the frozen calibration exporter."""

# isort: skip_file

import onnx

from r26_common import check
from r20_calibration import calibrated_graph


def append_sigmoid(calibration, graph):
    parent = onnx.ModelProto.FromString(graph.SerializeToString())
    check(
        not any(
            a.type in (onnx.AttributeProto.GRAPH, onnx.AttributeProto.GRAPHS)
            for n in parent.graph.node
            for a in n.attribute
        ),
        "Subgraph calibration unsupported",
    )
    names = {name for node in parent.graph.node for name in (*node.input, *node.output) if name}
    names.update(t.name for t in parent.graph.initializer)
    prefix = "r26_parent_"
    while any(name.startswith(prefix) for name in names):
        prefix += "x_"
    public = {item.name for item in (*parent.graph.input, *parent.graph.output)}
    mapping = {name: prefix + name for name in names if name not in public}
    for node in parent.graph.node:
        for fields in (node.input, node.output):
            for i, name in enumerate(fields):
                fields[i] = mapping.get(name, name)
    for fields in (parent.graph.initializer, parent.graph.value_info):
        for item in fields:
            item.name = mapping.get(item.name, item.name)
    return calibrated_graph(calibration, parent)
