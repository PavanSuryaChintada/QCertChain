from services.config import load_settings


def test_defaults_when_env_empty(tmp_path, monkeypatch):
    for k in ["TRIAGE_THRESHOLD", "INTERDICT_BACKEND", "CLUSTER_EDGE_THRESHOLD", "MAX_QUBO_VARIABLES"]:
        monkeypatch.delenv(k, raising=False)
    s = load_settings(env_file=tmp_path / "missing.env")
    assert s.triage_threshold == 0.35  # owner decision 1
    assert s.interdict_backend == "cpsat"
    assert s.cluster_edge_threshold == 0.6
    assert s.max_qubo_variables == 24


def test_env_file_parsed_and_process_env_wins(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# comment\nTRIAGE_THRESHOLD=0.5\nINTERDICT_BUDGET_K=7  # trailing\n")
    monkeypatch.setenv("INTERDICT_BUDGET_K", "3")
    monkeypatch.delenv("TRIAGE_THRESHOLD", raising=False)
    s = load_settings(env_file=f)
    assert s.triage_threshold == 0.5
    assert s.interdict_budget_k == 3
