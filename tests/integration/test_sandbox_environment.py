def test_sandbox_env_structure(sandbox):
    assert "api" in sandbox
    assert "storage" in sandbox
    assert "identity" in sandbox
