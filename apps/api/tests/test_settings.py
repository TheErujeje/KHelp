import pytest

from khelp_api.agent.runner import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ("KHELP_USE_LOCAL_MODEL", "KHELP_HOSTED_PROVIDER", "OLLAMA_MODEL", "GROQ_MODEL",
                "BEDROCK_MODEL_ID", "BEDROCK_REGION"):
        monkeypatch.delenv(key, raising=False)


def test_local_model_is_the_default():
    s = Settings()
    assert (s.provider, s.model) == ("ollama", "qwen2.5:7b-instruct")


def test_local_switch_uses_ollama_model(monkeypatch):
    monkeypatch.setenv("KHELP_USE_LOCAL_MODEL", "true")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:14b-instruct")
    monkeypatch.setenv("GROQ_MODEL", "ignored")
    assert Settings().model_label == "ollama:qwen2.5:14b-instruct"


def test_hosted_groq(monkeypatch):
    monkeypatch.setenv("KHELP_USE_LOCAL_MODEL", "false")
    assert Settings().model_label == "groq:openai/gpt-oss-120b"


def test_hosted_bedrock(monkeypatch):
    monkeypatch.setenv("KHELP_USE_LOCAL_MODEL", "False")
    monkeypatch.setenv("KHELP_HOSTED_PROVIDER", "bedrock")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "openai.gpt-oss-120b-1:0")
    s = Settings()
    assert (s.provider, s.model, s.bedrock_region) == ("bedrock", "openai.gpt-oss-120b-1:0", "eu-west-1")


@pytest.mark.parametrize("key,value", [("KHELP_USE_LOCAL_MODEL", "maybe"), ("KHELP_HOSTED_PROVIDER", "openai")])
def test_bad_values_fail_loudly(monkeypatch, key, value):
    monkeypatch.setenv("KHELP_USE_LOCAL_MODEL", "false")
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        Settings()
