def test_cpu_tree_reference_uses_same_independent_validation_protocol(prepared, tmp_path):
    from idps_ai.training.tree_baseline import benchmark_tree

    report = benchmark_tree(prepared, tmp_path / "tree", max_threads=1, max_iterations=4)
    assert report["model"] == "HistGradientBoostingClassifier"
    assert report["evaluation"]["test_labels_used"] is False
    assert report["evaluation"]["selection"]["partition"] == "val_selection_groups"
    assert report["deployment_bundle_created"] is False
    assert report["iterations"] == 4
