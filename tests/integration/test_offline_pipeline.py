def test_offline_export_preserves_multiple_modalities(
    tmp_path,
    multimodal_sample_config,
):
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.config import load_pipeline_config
    from experiment_to_cpfe.datasets.hdf5 import read_hdf5, write_hdf5

    config = load_pipeline_config(multimodal_sample_config)
    sample = assemble_sample(config)
    output = tmp_path / "multimodal.h5"

    write_hdf5(sample, output)
    restored = read_hdf5(output)

    modalities = {asset.modality.value for asset in restored.assets}
    assert {"orientation_map", "point_field", "voxel_grid", "mesh", "time_series"} <= modalities
    assert any(asset.axis_order == ("z", "y", "x") for asset in restored.assets)
    assert any(asset.parent_asset_id for asset in restored.assets)
    assert restored.arrays["ct-voxels"].shape == (2, 2, 2)
    assert restored.arrays["dic-points"].shape == (4, 4)
