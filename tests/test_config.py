"""Tests for unified configuration (config.yml + .env)."""

from src.config import Settings, load_yaml_config


def test_yaml_config_loading(tmp_path):
    yaml_content = """
    storage:
      db_path: "custom/path.db"
    filter:
      min_budget: 20000
      hot_score_threshold: 8
      stop_words:
        - "тест_стоп"
      keywords:
        - "тест_ключ"
    llm:
      provider: "antigravity"
      antigravity:
        model: "gemini-3.8-flash-low"
        timeout_seconds: 45.0
    """
    yaml_file = tmp_path / "config.yml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    cfg = load_yaml_config(yaml_file)
    assert cfg.storage.db_path == "custom/path.db"
    assert cfg.filter.min_budget == 20000
    assert cfg.filter.hot_score_threshold == 8
    assert cfg.filter.stop_words == ["тест_стоп"]
    assert cfg.filter.keywords == ["тест_ключ"]
    assert cfg.llm.antigravity.model == "gemini-3.8-flash-low"
    assert cfg.llm.antigravity.timeout_seconds == 45.0


def test_settings_facade(tmp_path):
    yaml_file = tmp_path / "config.yml"
    yaml_file.write_text(
        "polling:\n  vacancies_interval_seconds: 3600\nfilter:\n  min_budget: 15000\n  vacancy_hot_score_threshold: 9\n  vacancy_min_salary: 100000\n  vacancy_allow_negotiable: false\n",
        encoding="utf-8",
    )

    env_file = tmp_path / ".env"
    env_file.write_text("BOT_TOKEN=test_token_123\nADMIN_CHAT_ID=99999\n", encoding="utf-8")

    settings = Settings(yaml_path=yaml_file, env_file=env_file)
    assert settings.BOT_TOKEN == "test_token_123"
    assert settings.ADMIN_CHAT_ID == 99999
    assert settings.MIN_BUDGET == 15000
    assert settings.VACANCIES_POLL_INTERVAL == 3600
    assert settings.VACANCY_HOT_SCORE_THRESHOLD == 9
    assert settings.VACANCY_MIN_SALARY == 100000
    assert settings.VACANCY_ALLOW_NEGOTIABLE is False


def test_prompts_and_dossier_from_config():
    from src.config import settings

    assert len(settings.PROMPTS_CONFIG.projects_dossier) >= 5
    assert "Speech Analytics" in settings.DOSSIER_TEXT
    assert "Avia_Pars" in settings.DOSSIER_TEXT
    assert "netsleuth" in settings.DOSSIER_TEXT
    assert "summarum" in settings.DOSSIER_TEXT
    assert "leads-monitor" in settings.DOSSIER_TEXT
    assert "—" not in settings.ANALYSIS_SYSTEM_PROMPT
    assert "PERT" in settings.ANALYSIS_SYSTEM_PROMPT
    assert "{source}" in settings.PROPOSAL_PROMPT_TEMPLATE
