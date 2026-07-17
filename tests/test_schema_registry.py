from csv_pipeline.schema_registry import SchemaRegistry


def test_first_sighting_registers_without_drift(tmp_path):
    registry = SchemaRegistry(path=tmp_path / "registry.json")
    version, renamed, added = registry.check("procurement_export", ["entity_key", "employee_count", "region_code"])
    assert version == 1
    assert renamed == {}
    assert added == []


def test_fuzzy_rename_detected(tmp_path):
    registry = SchemaRegistry(path=tmp_path / "registry.json")
    registry.check("procurement_export", ["entity_key", "registration_number"])
    version, renamed, added = registry.check("procurement_export", ["entity_key", "registration_no"])
    assert renamed == {"registration_no": "registration_number"}
    assert version == 2


def test_new_column_bumps_version_without_dropping(tmp_path):
    registry = SchemaRegistry(path=tmp_path / "registry.json")
    registry.check("procurement_export", ["entity_key", "employee_count"])
    version, renamed, added = registry.check("procurement_export", ["entity_key", "employee_count", "contract_tier"])
    assert added == ["contract_tier"]
    assert version == 2


def test_registry_persists_across_instances(tmp_path):
    path = tmp_path / "registry.json"
    SchemaRegistry(path=path).check("procurement_export", ["entity_key", "employee_count"])
    reloaded = SchemaRegistry(path=path)
    version, _, added = reloaded.check("procurement_export", ["entity_key", "employee_count"])
    assert version == 1
    assert added == []
