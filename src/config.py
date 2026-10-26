"""Unified configuration loading credentials from .env and application settings from config.yml."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_YAML_PATH = BASE_DIR / "config.yml"


# ==========================================
# 1. Структура конфигурации из config.yml
# ==========================================

class StorageConfig(BaseModel):
    db_path: str = "data/jobs.db"


class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8086


class PollingConfig(BaseModel):
    kwork_interval: int = 180
    fl_interval: int = 180


class KworkCollectorConfig(BaseModel):
    base_url: str = "https://kwork.ru"
    category_ids: List[int] = Field(default_factory=lambda: [11, 41])
    max_pages: int = 5
    include_all_pages: int = 2


class FlRuCollectorConfig(BaseModel):
    rss_url: str = "https://www.fl.ru/rss/all.xml"


class FreelanceRuCollectorConfig(BaseModel):
    base_url: str = "https://freelance.ru"


class PchelNetCollectorConfig(BaseModel):
    base_url: str = "https://pchel.net"
    usd_rate: float = 95.0


class RemoteJobCollectorConfig(BaseModel):
    base_url: str = "https://remote-job.ru"


class CollectorsConfig(BaseModel):
    kwork: KworkCollectorConfig = Field(default_factory=KworkCollectorConfig)
    fl_ru: FlRuCollectorConfig = Field(default_factory=FlRuCollectorConfig)
    freelance_ru: FreelanceRuCollectorConfig = Field(default_factory=FreelanceRuCollectorConfig)
    pchel_net: PchelNetCollectorConfig = Field(default_factory=PchelNetCollectorConfig)
    remote_job: RemoteJobCollectorConfig = Field(default_factory=RemoteJobCollectorConfig)


class FilterConfig(BaseModel):
    min_budget: int = 10000
    hot_score_threshold: int = 7
    filter_pro_only: bool = False
    stop_words: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)


class AntigravityConfig(BaseModel):
    binary: str = "agy"
    model: str = "gemini-3.8-flash-medium"
    timeout_seconds: float = 150.0


class MistralConfig(BaseModel):
    model: str = "ministral-8b-latest"
    timeout_seconds: float = 60.0


class LLMConfig(BaseModel):
    provider: str = "antigravity"
    antigravity: AntigravityConfig = Field(default_factory=AntigravityConfig)
    mistral: MistralConfig = Field(default_factory=MistralConfig)


class ProjectDossierItem(BaseModel):
    name: str
    stack: str
    highlights: str
    use_for: str


class DeveloperProfileConfig(BaseModel):
    name: str = "Андрей Пименов"
    username: str = "@horizontal42"
    level: str = "Junior+ / Middle"
    specialization: str = "Python Backend, Telegram-боты, парсинг, CRM"
    min_budget: int = 10000
    hourly_rate_rub: int = 750


class PromptRulesConfig(BaseModel):
    strict_no_em_dash: bool = True
    preview_rule_140_chars: bool = True
    cold_start_strategy: bool = True
    no_ai_cliches: bool = True


class PromptTemplatesConfig(BaseModel):
    analysis_system_prompt: str = ""
    proposal_prompt_template: str = ""


class PromptsConfig(BaseModel):
    developer_profile: DeveloperProfileConfig = Field(default_factory=DeveloperProfileConfig)
    projects_dossier: List[ProjectDossierItem] = Field(default_factory=list)
    rules: PromptRulesConfig = Field(default_factory=PromptRulesConfig)
    templates: PromptTemplatesConfig = Field(default_factory=PromptTemplatesConfig)


class YamlAppConfig(BaseModel):
    storage: StorageConfig = Field(default_factory=StorageConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    collectors: CollectorsConfig = Field(default_factory=CollectorsConfig)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)


def load_yaml_config(yaml_path: Path) -> YamlAppConfig:
    """Загрузить и провалидировать config.yml."""
    if not yaml_path.exists():
        logger.warning("Файл %s не найден, используются дефолтные параметры", yaml_path)
        return YamlAppConfig()

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}
        return YamlAppConfig.model_validate(raw_data)
    except Exception as e:
        logger.error("Ошибка чтения %s: %s. Используются дефолтные параметры.", yaml_path, e)
        return YamlAppConfig()


# ==========================================
# 2. Секреты и учетные данные из .env
# ==========================================

class Secrets(BaseSettings):
    """Секреты и токены, читаемые строго из .env."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str = ""
    ADMIN_CHAT_ID: int = 0
    MISTRAL_API_KEY: str = ""


# ==========================================
# 3. Единый фасад настроек (Settings)
# ==========================================

class Settings:
    """Единый фасад для доступа к секретам (.env) и конфигурации (config.yml)."""

    def __init__(
        self,
        yaml_path: Optional[Path] = None,
        env_file: Optional[Path] = None,
    ) -> None:
        self.yaml_path = yaml_path or CONFIG_YAML_PATH
        self.app_config = load_yaml_config(self.yaml_path)
        self.secrets = Secrets(_env_file=env_file or (BASE_DIR / ".env"))

    # Секреты из .env
    @property
    def BOT_TOKEN(self) -> str:
        return self.secrets.BOT_TOKEN

    @property
    def ADMIN_CHAT_ID(self) -> int:
        return self.secrets.ADMIN_CHAT_ID

    @property
    def MISTRAL_API_KEY(self) -> str:
        return self.secrets.MISTRAL_API_KEY

    # База данных
    @property
    def DB_PATH(self) -> Path:
        p = Path(self.app_config.storage.db_path)
        return p if p.is_absolute() else (BASE_DIR / p)

    # Веб-дашборд
    @property
    def WEB_HOST(self) -> str:
        return self.app_config.web.host

    @property
    def WEB_PORT(self) -> int:
        return self.app_config.web.port

    # Интервалы опроса
    @property
    def KWORK_POLL_INTERVAL(self) -> int:
        return self.app_config.polling.kwork_interval

    @property
    def FL_POLL_INTERVAL(self) -> int:
        return self.app_config.polling.fl_interval

    # Источники
    @property
    def KWORK_BASE_URL(self) -> str:
        return self.app_config.collectors.kwork.base_url

    @property
    def KWORK_CATEGORY_IDS(self) -> List[int]:
        return self.app_config.collectors.kwork.category_ids

    @property
    def KWORK_MAX_PAGES(self) -> int:
        return self.app_config.collectors.kwork.max_pages

    @property
    def KWORK_INCLUDE_ALL_PAGES(self) -> int:
        return self.app_config.collectors.kwork.include_all_pages

    @property
    def FL_RSS_URL(self) -> str:
        return self.app_config.collectors.fl_ru.rss_url

    @property
    def FREELANCE_RU_BASE_URL(self) -> str:
        return self.app_config.collectors.freelance_ru.base_url

    @property
    def PCHEL_NET_BASE_URL(self) -> str:
        return self.app_config.collectors.pchel_net.base_url

    @property
    def PCHEL_NET_USD_RATE(self) -> float:
        return self.app_config.collectors.pchel_net.usd_rate

    @property
    def REMOTE_JOB_BASE_URL(self) -> str:
        return self.app_config.collectors.remote_job.base_url

    # Фильтры
    @property
    def MIN_BUDGET(self) -> int:
        return self.app_config.filter.min_budget

    @property
    def HOT_SCORE_THRESHOLD(self) -> int:
        return self.app_config.filter.hot_score_threshold

    @property
    def FILTER_PRO_ONLY(self) -> bool:
        return self.app_config.filter.filter_pro_only

    @property
    def STOP_WORDS(self) -> List[str]:
        return self.app_config.filter.stop_words

    @property
    def KEYWORDS(self) -> List[str]:
        return self.app_config.filter.keywords

    # LLM
    @property
    def LLM_PROVIDER(self) -> str:
        return self.app_config.llm.provider

    @property
    def ANTIGRAVITY_BIN(self) -> str:
        return self.app_config.llm.antigravity.binary

    @property
    def ANTIGRAVITY_MODEL(self) -> str:
        return self.app_config.llm.antigravity.model

    @property
    def ANTIGRAVITY_TIMEOUT(self) -> float:
        return self.app_config.llm.antigravity.timeout_seconds

    @property
    def MISTRAL_MODEL(self) -> str:
        return self.app_config.llm.mistral.model

    @property
    def MISTRAL_TIMEOUT(self) -> float:
        return self.app_config.llm.mistral.timeout_seconds

    # Промпты и досье проектов из config.yml
    @property
    def PROMPTS_CONFIG(self) -> PromptsConfig:
        return self.app_config.prompts

    @property
    def DOSSIER_TEXT(self) -> str:
        items = self.app_config.prompts.projects_dossier
        if not items:
            return ""
        lines = []
        for i, p in enumerate(items, 1):
            lines.append(
                f"{i}. {p.name}: {p.stack}. "
                f"Ключевые решения: {p.highlights}. "
                f"Для каких задач: {p.use_for}."
            )
        return "\n".join(lines)

    @property
    def ANALYSIS_SYSTEM_PROMPT(self) -> str:
        tmpl = self.app_config.prompts.templates.analysis_system_prompt
        if not tmpl:
            return ""
        return tmpl.format(dossier_text=self.DOSSIER_TEXT).strip()

    @property
    def PROPOSAL_PROMPT_TEMPLATE(self) -> str:
        tmpl = self.app_config.prompts.templates.proposal_prompt_template
        if not tmpl:
            return ""
        # Подставляем dossier_text, оставляя {source}, {title}, {price}, {description}, {extra_context} для format
        return tmpl.replace("{dossier_text}", self.DOSSIER_TEXT).strip()


settings = Settings()
