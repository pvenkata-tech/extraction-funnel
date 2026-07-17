from csv_pipeline.schema_registry import SchemaRegistry


def test_first_sighting_registers_without_drift(tmp_path):
    registry = SchemaRegistry(path=tmp_path / "registry.json")
    version, renamed, added = registry.check("ehr_export", ["entity_key", "age", "zip_code"])
    assert version == 1
    assert renamed == {}
    assert added == []


def test_fuzzy_rename_detected(tmp_path):
    registry = SchemaRegistry(path=tmp_path / "registry.json")
    registry.check("ehr_export", ["entity_key", "diagnosis_code"])
    version, renamed, added = registry.check("ehr_export", ["entity_key", "diagnosis_cd"])
    assert renamed == {"diagnosis_cd": "diagnosis_code"}
    assert version == 2


def test_new_column_bumps_version_without_dropping(tmp_path):
    registry = SchemaRegistry(path=tmp_path / "registry.json")
    registry.check("ehr_export", ["entity_key", "age"])
    version, renamed, added = registry.check("ehr_export", ["entity_key", "age", "insurance_type"])
    assert added == ["insurance_type"]
    assert version == 2


def test_registry_persists_across_instances(tmp_path):
    path = tmp_path / "registry.json"
    SchemaRegistry(path=path).check("ehr_export", ["entity_key", "age"])
    reloaded = SchemaRegistry(path=path)
    version, _, added = reloaded.check("ehr_export", ["entity_key", "age"])
    assert version == 1
    assert added == []
