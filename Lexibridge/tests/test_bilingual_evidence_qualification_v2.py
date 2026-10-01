from scripts.evaluations import bilingual_evidence_qualification_v2 as runner


def test_runner_keeps_all_denominators_and_does_not_hardcode_eleven():
    source = runner.__file__
    text = open(source).read()
    assert "range(11)" not in text
    assert '"evidence_qualification_eligible": 11' not in text
    result = runner.evaluate(runner.DeterministicQualificationFixture())
    assert len(result["rows"]) == 25
    assert result["metrics"]["retrieval_eligible"] == 18
    assert result["metrics"]["identification_eligible"] == 15
    assert result["metrics"]["pairing_eligible"] == 14
    assert result["metrics"]["evidence_qualification_eligible"] == sum(
        row["evidence_qualification_eligible"] for row in result["rows"]
    )


def test_upstream_failures_are_not_qualification_failures():
    result = runner.evaluate(runner.DeterministicQualificationFixture())
    upstream = [
        row for row in result["rows"]
        if row["primary_attribution"].startswith("UPSTREAM_")
    ]
    assert upstream
    assert all(not row["evidence_qualification_eligible"] for row in upstream)
    assert all(
        row["primary_attribution"].startswith("UPSTREAM_")
        for row in upstream
    )


def test_artifact_payload_is_sanitized_and_provider_free():
    result = runner.evaluate(runner.DeterministicQualificationFixture())
    serialized = runner.sanitized_results(result)
    assert "/Users/" not in serialized
    assert "DEEPSEEK_API_KEY" not in serialized
    assert "required_propositions" not in serialized
    assert result["real_provider_requests"] == 0
    assert result["external_api_requests"] == 0
