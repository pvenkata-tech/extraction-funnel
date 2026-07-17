from pdf_pipeline.deid import deidentify


def test_redacts_ssn_phone_mrn_dob_email():
    text = (
        "Patient SSN 123-45-6789, phone (512) 555-0199, MRN: 1002345, "
        "DOB 04/12/1980, email jane.doe@example.com. Diagnosis: lung cancer."
    )
    scrubbed, count = deidentify(text)

    assert "123-45-6789" not in scrubbed
    assert "555-0199" not in scrubbed
    assert "1002345" not in scrubbed
    assert "04/12/1980" not in scrubbed
    assert "jane.doe@example.com" not in scrubbed
    assert "lung cancer" in scrubbed  # clinical content must survive de-id
    assert count == 5


def test_no_phi_present_returns_zero_redactions():
    text = "Patient denies any history of smoking. No acute distress noted."
    scrubbed, count = deidentify(text)
    assert scrubbed == text
    assert count == 0
