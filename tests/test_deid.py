from pdf_pipeline.deid import deidentify


def test_redacts_ssn_phone_ein_email():
    text = (
        "Signer SSN 123-45-6789, phone (512) 555-0199, EIN: 12-3456789, "
        "email jane.doe@example.com. Vendor's liability shall not be limited."
    )
    scrubbed, count = deidentify(text)

    assert "123-45-6789" not in scrubbed
    assert "555-0199" not in scrubbed
    assert "12-3456789" not in scrubbed
    assert "jane.doe@example.com" not in scrubbed
    assert "liability shall not be limited" in scrubbed  # contract content must survive de-id
    assert count == 4


def test_no_sensitive_data_present_returns_zero_redactions():
    text = "Vendor's liability under this Agreement shall not be limited."
    scrubbed, count = deidentify(text)
    assert scrubbed == text
    assert count == 0
