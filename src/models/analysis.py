"""Domain models for LLM evaluation and proposals."""

import ast
import re
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from src.models.order import OrderPriority


def extract_clean_text_items(v: Any) -> list[str]:
    """Рекурсивно извлекает плоский список строк из любых вложенных списков, словарей или строк."""
    if v is None:
        return []
    items: list[str] = []
    if isinstance(v, (list, tuple, set)):
        for x in v:
            items.extend(extract_clean_text_items(x))
    elif isinstance(v, dict):
        parts = []
        for k, val in v.items():
            if val is not None and str(val).strip():
                label = ""
                k_lower = str(k).lower()
                if k_lower in ("years", "experience"):
                    label = "Опыт: "
                elif k_lower in ("role", "position"):
                    label = "Позиция: "
                elif k_lower not in ("note", "text", "description"):
                    label = f"{k}: "
                parts.append(f"{label}{str(val).strip()}")
        if parts:
            items.append("; ".join(parts))
    elif isinstance(v, str):
        text = v.strip()
        if not text:
            return []
        if ("['" in text or '["' in text or "{'" in text or '{"' in text) and (text.startswith("[") or text.startswith("{") or "]" in text):
            parsed_any = False
            matches = re.findall(r"(\[.*?\]|\{.*?\})", text, flags=re.DOTALL)
            for m in matches:
                try:
                    res = ast.literal_eval(m)
                    sub = extract_clean_text_items(res)
                    if sub:
                        items.extend(sub)
                        parsed_any = True
                except Exception:
                    pass
            if not parsed_any:
                items.append(text)
        else:
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            for l in lines:
                cleaned_line = re.sub(r"^([\*\-\•]|\d+[\.\)])\s*", "", l).strip()
                if cleaned_line:
                    items.append(cleaned_line)
    else:
        s = str(v).strip()
        if s:
            items.append(s)
    return items


def clean_analysis_field(v: Any) -> str:
    """Форматирует значение поля анализа в аккуратный читаемый текст без сырых структур Python/JSON."""
    if v is None:
        return ""
    items = extract_clean_text_items(v)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return "\n".join(f"• {it}" if not it.startswith("• ") else it for it in items)


class PertEstimate(BaseModel):
    """PERT-анализ сроков разработки."""

    optimistic_days: float = Field(..., description="Оптимистичный сценарий (O)")
    most_likely_days: float = Field(..., description="Наиболее вероятный сценарий (M)")
    pessimistic_days: float = Field(..., description="Пессимистичный сценарий (P)")
    expected_days: float = Field(default=0.0, description="Ожидаемый срок E = (O + 4M + P) / 6")
    sigma: float = Field(default=0.0, description="Стандартное отклонение (P - O) / 6")

    @model_validator(mode="before")
    @classmethod
    def calculate_pert_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            try:
                o = float(data.get("optimistic_days", 1.0))
                m = float(data.get("most_likely_days", 2.0))
                p = float(data.get("pessimistic_days", 4.0))
                # Автоматический точный расчет математики PERT на стороне Python
                data["expected_days"] = round((o + 4.0 * m + p) / 6.0, 1)
                data["sigma"] = round(abs(p - o) / 6.0, 1)
            except Exception:
                pass
        return data


class AnalysisResult(BaseModel):
    """Структурированный результат разбора заказа нейросетью.

    Строго соблюдает регламент FREELANCE_PROFILE.md:
    - Оценка брать/не брать, сложность, чистое время
    - Подводные камни и технические риски
    - Зацепка за реальные проекты из PROJECTS_DOSSIER.md
    - Готовый живой отклик: без маркеров ИИ, строго с дефисами "-" (без "—")
    - PERT-анализ и обоснование цены (холодный старт vs торг)
    """

    take_order: bool = Field(..., description="Брать ли заказ (Да/Нет)")
    score: int = Field(..., ge=1, le=10, description="Общая привлекательность лида от 1 до 10")
    priority: OrderPriority = Field(..., description="Уровень приоритета (hot / normal)")
    executive_summary: str = Field(..., description="Краткое резюме: почему брать/не брать")

    # Специфика вакансий (HH.ru) под резюме Андрея Пименова
    company_overview: Optional[str] = Field(
        default="",
        description="Что за компания, ее сфера бизнеса, масштаб и продукт",
    )
    candidate_requirements: Optional[str] = Field(
        default="",
        description="Требования к кандидату, стек технологий, адекватность грейда",
    )
    job_responsibilities: Optional[str] = Field(
        default="",
        description="Чем предстоит заниматься на практике, реальные задачи",
    )
    match_reason: Optional[str] = Field(
        default="",
        description="Почему вакансия подходит Андрею Пименову с учетом его резюме",
    )
    skills_gap: Optional[str] = Field(
        default="",
        description="Чего не хватает в резюме Андрея из требований вакансии (пробелы в стеке)",
    )
    skills_gap_counter: Optional[str] = Field(
        default="",
        description="Как парировать пробел в требованиях вакансии в Cover Letter",
    )

    market_price: Optional[float] = Field(
        default=None,
        description="Объективная рыночная стоимость разработки (чистые часы * ставка 750-1000 ₽/ч + сложность) БЕЗ привязки к бюджету заказчика",
    )
    recommended_price: float = Field(default=0.0, description="Тактическая рекомендуемая цена для предложения клиенту в рублях")
    price_justification: str = Field(default="", description="Обоснование цен: сравнение рыночной стоимости с бюджетом клиента и стратегия торга")
    realistic_days: float = Field(default=0.0, description="Реалистичный срок для клиента в днях")

    matched_project: str = Field(
        default="Общий бэкграунд (Python Backend)",
        description="На какой проект из досье больше всего похоже (Speech Analytics, Avia_Pars, leads-monitor и др.)",
    )
    complexity: int = Field(default=1, ge=1, le=10, description="Реальная техническая сложность 1-10")
    pure_dev_hours: float = Field(default=0.0, description="Чистое расчетное время работы в часах")
    risks_and_pitfalls: List[str] = Field(
        default_factory=list,
        description="Скрытые риски, лимиты API, WAF, блокировки",
    )

    proposal_text: str = Field(
        default="",
        description="Готовый отклик живым языком: без штампов, строго с дефисами '-', первые 140 симв с зацепкой",
    )
    pert: Optional[PertEstimate] = Field(default=None, description="PERT расчет сроков")

    @field_validator("matched_project", mode="before")
    @classmethod
    def sanitize_matched_project(cls, v: Any) -> str:
        if v is None:
            return "Общий бэкграунд (Python Backend)"
        return str(v)

    @field_validator("price_justification", mode="before")
    @classmethod
    def sanitize_price_justification(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, dict):
            return " ".join(f"{k}: {val}" for k, val in v.items() if val)
        return str(v)

    @field_validator("executive_summary", mode="before")
    @classmethod
    def sanitize_executive_summary(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return " ".join(str(x) for x in v)
        if isinstance(v, dict):
            return " ".join(str(val) for val in v.values() if val)
        return str(v)

    @field_validator("company_overview", mode="before")
    @classmethod
    def sanitize_company_overview(cls, v: Any) -> str:
        return clean_analysis_field(v)

    @field_validator("candidate_requirements", mode="before")
    @classmethod
    def sanitize_candidate_requirements(cls, v: Any) -> str:
        return clean_analysis_field(v)

    @field_validator("job_responsibilities", mode="before")
    @classmethod
    def sanitize_job_responsibilities(cls, v: Any) -> str:
        return clean_analysis_field(v)

    @field_validator("match_reason", mode="before")
    @classmethod
    def sanitize_match_reason(cls, v: Any) -> str:
        return clean_analysis_field(v)

    @field_validator("skills_gap", mode="before")
    @classmethod
    def sanitize_skills_gap(cls, v: Any) -> str:
        return clean_analysis_field(v)

    @field_validator("skills_gap_counter", mode="before")
    @classmethod
    def sanitize_skills_gap_counter(cls, v: Any) -> str:
        return clean_analysis_field(v)


class ProposalResult(str):
    """Результат генерации отклика Antigravity (agy) с финансовой оценкой на основе поиска в интернете.

    Наследуется от str для 100% обратной совместимости со всеми существующими хэндлерами и тестами,
    но несет в себе дополнительные поля recommended_price, price_justification, market_price, estimated_days.
    """

    def __new__(
        cls,
        text: str,
        recommended_price: Optional[float] = None,
        price_justification: Optional[str] = None,
        market_price: Optional[float] = None,
        estimated_days: Optional[str] = None,
    ) -> "ProposalResult":
        obj = super().__new__(cls, text)
        obj.proposal_text = text
        obj.recommended_price = recommended_price
        obj.price_justification = price_justification
        obj.market_price = market_price
        obj.estimated_days = estimated_days
        return obj


def trim_text_to_char_limit(text: str, max_chars: int = 2000) -> str:
    """Обрезает текст отклика до лимита символов по границе предложения или абзаца без обрыва на полуслове."""
    if not text or len(text) <= max_chars:
        return text

    import re
    # 0. Сначала пробуем мягко оптимизировать форматирование (убрать хвостовые пробелы и избыточные пустые строки)
    cleaned = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(cleaned) <= max_chars:
        return cleaned

    # Если превышение небольшое (до 15%), пробуем компактно оформить списки (одинарный перенос перед буллетами)
    if len(cleaned) <= max_chars * 1.15:
        compacted = re.sub(r"\n\n([ \t]*(?:[-*•]|\d+[\.\)]))", r"\n\1", cleaned)
        if len(compacted) <= max_chars:
            return compacted

    truncated = cleaned[:max_chars]
    # 1. Попытка обрезать по границе абзаца (если занимает хотя бы 75% лимита)
    last_para = truncated.rfind("\n\n")
    if last_para >= int(max_chars * 0.75):
        return truncated[:last_para].strip()

    # 2. Попытка обрезать по границе предложения (. ! ?)
    best_sent_end = -1
    for sep in [".\n", "!\n", "?\n", ". ", "! ", "? "]:
        idx = truncated.rfind(sep)
        if idx > best_sent_end:
            best_sent_end = idx + (1 if sep.endswith(" ") else 0)

    if best_sent_end >= int(max_chars * 0.75):
        return truncated[:best_sent_end + 1].strip()

    # 3. Попытка обрезать по последнему переносу строки или пробелу
    last_space = max(truncated.rfind("\n"), truncated.rfind(" "))
    if last_space >= int(max_chars * 0.8):
        return truncated[:last_space].strip()

    return truncated.strip()


def normalize_extracted_price(val: Optional[Any]) -> Optional[float]:
    """Нормализует распарсенную цену: очищает от пробелов, восстанавливает масштаб (млн/тыс руб)."""
    if val is None:
        return None
    import re
    try:
        if isinstance(val, str):
            clean_str = re.sub(r"[^\d.]", "", val.replace(" ", "").replace("\xa0", ""))
            val = float(clean_str) if clean_str else None
        if val is None:
            return None
        val = float(val)
        if val <= 0:
            return None
        # Если модель вернула число в миллионах (например, 1.0 или 1.5)
        if 0 < val <= 20:
            val = round(val * 1_000_000)
        # Если модель вернула число в тысячах (например, 280 или 950 вместо 280000 или 950000)
        elif 20 < val < 1000:
            val = round(val * 1_000)
        return float(val)
    except (ValueError, TypeError):
        return None


def format_matched_project(raw_val: Any) -> Optional[str]:
    """Форматирует название кейса в человекочитаемый вид, убирая сырые Python-списки и внутренние кодовые имена."""
    if not raw_val:
        return None
    val_str = str(raw_val).strip()
    if not val_str:
        return None
    import ast
    parts = []
    if val_str.startswith("[") and val_str.endswith("]"):
        try:
            evaluated = ast.literal_eval(val_str)
            if isinstance(evaluated, list):
                parts = [str(x) for x in evaluated if x]
        except Exception:
            parts = [p.strip(" '\"[]") for p in val_str.strip("[]").split(",") if p.strip(" '\"[]")]
    else:
        parts = [val_str]

    clean_parts = []
    mapping = {
        "Avia_Pars": "Мониторинг цен (боты)",
        "Speech Analytics": "Речевая аналитика",
        "SpeechAnalytics": "Речевая аналитика",
        "Intervesp": "Речевая аналитика",
        "RAG-ассистент": "Корпоративный RAG",
        "RAG": "Корпоративный RAG",
        "leads-monitor": "Сбор данных и парсинг",
        "Sort_YM": "Автоматизация каталога",
        "LaptopTester": "Тестирование оборудования",
        "netsleuth": "Сетевая диагностика",
        "netcheck": "Сетевая диагностика",
        "summarum": "Калькулятор-парсер",
        "Numi": "Калькулятор-парсер",
        "Warehouse Master": "Складской учет",
        "WarehouseMaster": "Складской учет",
        "AgroTech CV": "Компьютерное зрение",
        "AgroTech_CV": "Компьютерное зрение",
        "AgroTech": "Компьютерное зрение",
    }
    for p in parts:
        p_clean = p.strip(" '\"")
        if not p_clean:
            continue
        cleaned = mapping.get(p_clean)
        if not cleaned:
            cleaned = p_clean
            for k in sorted(mapping.keys(), key=len, reverse=True):
                cleaned = re.sub(rf"\b{re.escape(k)}\b", mapping[k], cleaned)
        if cleaned and cleaned not in clean_parts:
            clean_parts.append(cleaned)
    return ", ".join(clean_parts) if clean_parts else None


def sanitize_internal_project_codenames(t: str) -> str:
    """Удаляет и заменяет ВСЕ внутренние кодовые имена репозиториев на человеческие описания функционала."""
    if not t:
        return ""
    import re
    # 1. Обобщенные конструкции сравнения '(как в X)', '(аналогично X)'
    t = re.sub(r"(?i)\((?:как\s+в|аналогичн[оа-я]*\s+с?)\s+Avia_Pars\)", "(в аналогичном проекте)", t)
    t = re.sub(r"(?i)\((?:как\s+в|аналогичн[оа-я]*\s+с?)\s+netsleuth\)", "(в аналогичной сетевой утилите)", t)
    t = re.sub(r"(?i)\((?:как\s+в|аналогичн[оа-я]*\s+с?)\s+leads-monitor\)", "(в аналогичном парсере)", t)
    t = re.sub(r"(?i)\((?:как\s+в|аналогичн[оа-я]*\s+с?)\s+Speech\s+Analytics\)", "(в аналогичной системе)", t)
    t = re.sub(r"(?i)\((?:как\s+в|аналогичн[оа-я]*\s+с?)\s+Sort_YM\)", "(в аналогичном скрипте)", t)
    t = re.sub(r"(?i)\((?:как\s+в|аналогичн[оа-я]*\s+с?)\s+LaptopTester\)", "(в аналогичном приложении)", t)
    t = re.sub(r"(?i)\((?:как\s+в|аналогичн[оа-я]*\s+с?)\s+RAG(?:-ассистент|-assistant)?\)", "(в аналогичной RAG-системе)", t)
    t = re.sub(r"(?i)\((?:как\s+в|аналогичн[оа-я]*\s+с?)\s+AgroTech(?:[-_ ]CV)?\)", "(в аналогичном проекте CV)", t)
    t = re.sub(r"(?i)\((?:как\s+в|аналогичн[оа-я]*\s+с?)\s+[A-Za-z0-9_ -]+\)", "(в аналогичном проекте)", t)

    # 2. Обороты с 'в рамках кейса', 'проекте', 'базе', 'стека'
    t = re.sub(r"(?i)\bв\s+рамках\s+кейса\s+[A-Za-z0-9_ -]+", "в аналогичном проекте", t)
    t = re.sub(r"(?i)аналогичн[а-я]+\s+Avia_Pars", "аналогичную ранее реализованному решению", t)
    t = re.sub(r"(?i)стека\s+Avia_Pars", "стека ранее реализованного парсера", t)
    t = re.sub(r"(?i)базе\s+(?:проверенного\s+)?стека\s+(?:Avia_Pars|Sort_YM|leads-monitor)", "базе проверенного стека для парсинга и ботов", t)
    t = re.sub(r"(?i)базе\s+(?:Avia_Pars|Sort_YM|leads-monitor)", "базе проверенного решения", t)
    t = re.sub(r"(?i)например,\s*Avia_Pars\s+для", "например, Telegram-бота для", t)
    t = re.sub(r"(?i)проекте\s+Speech\s+Analytics", "проекте речевой аналитики", t)
    t = re.sub(r"(?i)проекта\s+Speech\s+Analytics", "проекта речевой аналитики", t)
    t = re.sub(r"(?i)системе\s+Speech\s+Analytics", "системе речевой аналитики", t)
    t = re.sub(r"(?i)в\s+проекте\s+RAG(?:-ассистент|-assistant)?", "в корпоративной RAG-системе", t)

    # 3. Маркеры списков и заголовки с кодовыми именами проектов ('- RAG-ассистент:', '1. Speech Analytics:')
    t = re.sub(r"(?im)^([ \t]*(?:[-*•]|\d+[\.\)]))\s*RAG(?:-ассистент|-assistant)?\s*:", r"\1 Корпоративная RAG-система:", t)
    t = re.sub(r"(?im)^([ \t]*(?:[-*•]|\d+[\.\)]))\s*Speech\s*Analytics\s*:", r"\1 B2B-система речевой аналитики:", t)
    t = re.sub(r"(?im)^([ \t]*(?:[-*•]|\d+[\.\)]))\s*Avia_Pars\s*:", r"\1 Отказоустойчивый Telegram-бот:", t)
    t = re.sub(r"(?im)^([ \t]*(?:[-*•]|\d+[\.\)]))\s*leads-monitor\s*:", r"\1 Сервис B2B-мониторинга:", t)
    t = re.sub(r"(?im)^([ \t]*(?:[-*•]|\d+[\.\)]))\s*netsleuth\s*:", r"\1 Сетевая CLI-утилита:", t)
    t = re.sub(r"(?im)^([ \t]*(?:[-*•]|\d+[\.\)]))\s*AgroTech(?:[-_ ]CV)?\s*:", r"\1 Система компьютерного зрения:", t)
    t = re.sub(r"(?im)^([ \t]*(?:[-*•]|\d+[\.\)]))\s*Sort_YM\s*:", r"\1 Скрипт автоматизации:", t)
    t = re.sub(r"(?im)^([ \t]*(?:[-*•]|\d+[\.\)]))\s*LaptopTester\s*:", r"\1 Диагностическая утилита:", t)
    t = re.sub(r"(?im)^([ \t]*(?:[-*•]|\d+[\.\)]))\s*Warehouse\s*Master\s*:", r"\1 Складская система:", t)

    # 4. Точечные замены технических названий проектов
    replacements = {
        r"\bAvia_Pars\b": "Telegram-бота мониторинга",
        r"\bnetsleuth\b": "сетевой утилиты",
        r"\bnetcheck\b": "сетевой утилиты",
        r"\bleads-monitor\b": "пайплайна мониторинга",
        r"\bSort_YM\b": "скрипта автоматизации",
        r"\bLaptopTester\b": "диагностической утилиты",
        r"\bWarehouse Master\b": "складской системы",
        r"\bWarehouseMaster\b": "складской системы",
        r"\bSpeech Analytics\b": "системы речевой аналитики",
        r"\bSpeechAnalytics\b": "системы речевой аналитики",
        r"\bIntervesp\b": "B2B-клиента",
        r"(?i)\bRAG(?:-ассистент|-assistant)\b": "корпоративной RAG-системы",
        r"\bsummarum\b": "десктопного калькулятора",
        r"\bNumi\b": "калькулятора с парсером",
        r"\bAgroTech[-_ ]CV\b": "системы компьютерного зрения",
        r"\bAgroTech\b": "системы компьютерного зрения",
    }
    for pattern, repl in replacements.items():
        t = re.sub(pattern, repl, t)
    return t


def sanitize_proposal_text(text: str, max_len: Optional[int] = None) -> str:
    """Гарантированная очистка отклика: замена длинных тире на дефисы, удаление звездочек (**) и markdown-разметки."""
    if not text:
        return ""
    import re
    t = str(text)
    # 0. Преобразование литеральных экранированных переносов строк (\n -> перенос строки)
    if "\\n" in t:
        t = t.replace("\\r\\n", "\n").replace("\\n", "\n")
    if "\\t" in t:
        t = t.replace("\\t", " ")
    if '\\"' in t:
        t = t.replace('\\"', '"')
    # 1. Замена длинных и средних тире на обычный дефис
    t = t.replace("—", "-").replace("–", "-")
    # 2. Удаление жирного шрифта markdown (**текст** -> текст)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    # 3. Удаление курсива (*текст* -> текст)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    # 4. Удаление оставшихся звездочек
    t = t.replace("*", "")
    # 5. Удаление заголовков markdown (например ### Опыт)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.MULTILINE)
    # 6. Удаление горизонтальных разделителей markdown (---, ___, ***)
    t = re.sub(r"^\s*[-*_]{3,}\s*$", "", t, flags=re.MULTILINE)
    # 7. Преобразование markdown-ссылок [текст](url) и [Ссылка: url] в чистые URL
    t = re.sub(r"\[(?:[^\]]*)\]\((https?://[^\)]+)\)", r"\1", t)
    t = re.sub(r"\[(?:[^:\]]+:\s*)?(https?://[^\]]+)\]", r"\1", t)
    # 8. Гарантия пометки об NDA для ссылок на GitHub (коммерческие проекты закрыты NDA)
    lines = t.split("\n")
    processed_lines = []
    for line in lines:
        if "github.com" in line.lower() and not any(w in line.lower() for w in ["nda", "коммерческ", "закрыт", "скрыт"]):
            line = line.rstrip(".") + " (коммерческие проекты закрыты NDA)"
        processed_lines.append(line)
    t = "\n".join(processed_lines)
    # 9. Удаление блоков ожиданий по зарплате и срокам выхода (работодатель сам должен предложить условия)
    t = re.sub(r"^[ \t]*Ожидания:[\s\S]*?(?=\n\n|\n[А-ЯA-Z]|\Z)", "", t, flags=re.MULTILINE)
    # 10. Удаление шаблонных фраз вежливости ("Буду рад обсудить...", "Готов обсудить...", "Спасибо за внимание...")
    boilerplate_rx = re.compile(
        r"(?i)^[ \t]*(?:спасибо[^\n]*?[.,!?:;]?\s*)?(?:буду\s+рад[а-я]*|готов[а-я]*)\s+(?:обсудить|ответить|пообщаться|рассказать)[\s\S]*?(?:звонк[а-я]*|встреч[а-я]*|интервью|созвон[а-я]*)[^\n]*\n*",
        re.MULTILINE,
    )
    t = boilerplate_rx.sub("", t)
    t = re.sub(r"(?i)^[ \t]*спасибо\s+за\s+внимание[.,!]?[ \t]*\n*", "", t, flags=re.MULTILINE)

    # Удаление роботизированных фраз-клише, лести и пустых связок
    t = re.sub(
        r"(?im)^[ \t]*(?:ваша\s+вакансия\s+[^\n]*соответствует|расскажу\s+о\s+проекте[^\n]*близок|моя\s+работа\s+[^\n]*|мой\s+опыт\s+[^\n]*|мой\s+стек\s+[^\n]*|мои\s+навыки\s+[^\n]*|с\s+большим\s+интересом\s+[^\n]*ваканси|меня\s+заинтересовала\s+[^\n]*ваканси|считаю,?\s+что\s+мой\s+опыт\s+[^\n]*)[^\n]*:?[ \t]*\n*",
        "",
        t,
    )

    # Удаление шаблонных блоков самосоответствия и лести компании вместе со списками буллетов (включая нумерованные вроде '3. Почему подхожу для вашей команды')
    t = re.sub(
        r"(?im)^[ \t]*(?:\d+[\.\)]\s*)?(?:почему\s+[^\n]*|мое\s+соответствие[^\n]*|чем\s+(?:я\s+)?могу\s+быть\s+полезен[^\n]*)[ \t]*:?[ \t]*\n(?:[ \t]*(?:[-*•]|\d+[\.\)])[^\n]*\n*)+",
        "",
        t,
    )
    # Удаление оставшихся одиночных заголовков такого типа
    t = re.sub(
        r"(?im)^[ \t]*(?:\d+[\.\)]\s*)?(?:почему\s+[^\n]*|мое\s+соответствие[^\n]*|чем\s+(?:я\s+)?могу\s+быть\s+полезен[^\n]*)[ \t]*:?[ \t]*\n*",
        "",
        t,
    )

    # Удаление оправдательных буллетов про 'готовность быстро освоить' / 'быстро изучу'
    t = re.sub(
        r"(?im)^[ \t]*[-*•]?\s*(?:готовность\s+быстро\s+освоить|готов(?:ен|а)?\s+быстро\s+(?:освоить|изучить|разобраться)|быстро\s+освою|готов(?:ен|а)?\s+изучить|в\s+процессе\s+работы\s+освою)[^\n]*\n*",
        "",
        t,
    )
    # 11. Форматирование приветствия "Здравствуйте":
    # После "Здравствуйте" ОБЯЗАТЕЛЬНО идет запятая и сплошной текст на ТОЙ ЖЕ строке со строчной буквы (без переноса строки или абзаца)
    def _repl_greeting(m: re.Match) -> str:
        greeting = m.group(1)
        next_word = m.group(2)
        # Если слово - аббревиатура (AI, B2B, LLM), сохраняем регистр
        if re.match(r"^[A-ZА-ЯЁ]{2,}", next_word):
            return f"{greeting}, {next_word}"
        return f"{greeting}, {next_word[0].lower()}{next_word[1:]}"

    # а) С последующим переносом строки или абзацем: "Здравствуйте,\n\nЗанимаюсь" -> "Здравствуйте, занимаюсь"
    t = re.sub(
        r"(?i)\b(здравствуйте)[.,]?[ \t]*\n+[ \t]*(\S+)",
        _repl_greeting,
        t,
    )
    # б) На одной строке с точкой: "Здравствуйте. Занимаюсь" -> "Здравствуйте, занимаюсь"
    t = re.sub(
        r"(?i)\b(здравствуйте)\.[ \t]*(\S+)",
        _repl_greeting,
        t,
    )
    # в) Оставшиеся точки непосредственно после "Здравствуйте" -> запятая
    t = re.sub(r"(?i)\b(здравствуйте)\.", r"\1,", t)
    # 12. Удаление и замена внутренних кодовых имен проектов (клиент не знает и не должен знать кодовые имена)
    t = sanitize_internal_project_codenames(t)
    # 13. Схлопывание избыточных пустых строк
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = t.strip()

    # 14. Гарантия наличия прямых контактов Андрея в сопроводительных письмах с GitHub
    if "github.com/Horizontal42" in t and "@Horizontal84" not in t:
        t = t + "\n\nTelegram: @Horizontal84\nEmail: pimenoffandrew@gmail.com"

    if max_len is not None and max_len > 0:
        t = trim_text_to_char_limit(t, max_chars=max_len)
    return t


def extract_clean_proposal_payload(raw_text: str) -> dict:
    """Извлечь чистый текст отклика и метаданные даже из сырого, неэкранированного JSON-ответа модели."""
    import json
    import re

    if not raw_text or not str(raw_text).strip():
        return {
            "proposal_text": "",
            "recommended_price": None,
            "market_price": None,
            "price_justification": None,
            "estimated_days": None,
        }

    text = str(raw_text).strip()
    result = {
        "proposal_text": "",
        "recommended_price": None,
        "market_price": None,
        "price_justification": None,
        "estimated_days": None,
    }

    # Если текст содержит структуру JSON (ключ proposal_text и фигурные скобки/блок кода)
    if "proposal_text" in text and ("{" in text or "```" in text):
        cleaned = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            candidate = cleaned[start_idx : end_idx + 1]
            try:
                parsed = json.loads(candidate, strict=False)
                if isinstance(parsed, dict) and "proposal_text" in parsed:
                    rec_p = normalize_extracted_price(parsed.get("recommended_price"))
                    mkt_p = normalize_extracted_price(parsed.get("market_price"))
                    days = parsed.get("estimated_days") or parsed.get("realistic_days")
                    raw_just = str(parsed["price_justification"]).strip() if parsed.get("price_justification") else None
                    return {
                        "proposal_text": sanitize_proposal_text(str(parsed.get("proposal_text") or "")),
                        "recommended_price": rec_p,
                        "market_price": mkt_p,
                        "price_justification": sanitize_proposal_text(raw_just) if raw_just else None,
                        "estimated_days": sanitize_proposal_text(str(days)) if days else None,
                    }
            except Exception:
                pass

        # Регэксп-фоллбэк, если json.loads не справился (например, неэкранированные кавычки внутри текста)
        # Используем lookahead до закрывающей кавычки перед известными ключами корневой схемы или концом JSON
        prop_m = re.search(
            r'"proposal_text"\s*:\s*"((?:\\.|[\s\S])*?)(?="[ \t]*(?:,[ \t\r\n]*"(?:market_price|recommended_price|estimated_days|realistic_days|price_justification|pert|score|take_order|priority)"|\s*\}))',
            text,
        )
        if not prop_m:
            # Резервный поиск, если структура JSON нестандартная
            prop_m = re.search(r'"proposal_text"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)

        if prop_m:
            raw_val = prop_m.group(1)
            try:
                clean_prop = json.loads(f'"{raw_val}"')
            except Exception:
                clean_prop = raw_val.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
            result["proposal_text"] = sanitize_proposal_text(clean_prop)

            rec_m = re.search(r'"recommended_price"\s*:\s*"?([0-9][0-9\s.,]*)', text)
            if rec_m:
                result["recommended_price"] = normalize_extracted_price(rec_m.group(1))

            mkt_m = re.search(r'"market_price"\s*:\s*"?([0-9][0-9\s.,]*)', text)
            if mkt_m:
                result["market_price"] = normalize_extracted_price(mkt_m.group(1))

            just_m = re.search(
                r'"price_justification"\s*:\s*"((?:\\.|[\s\S])*?)(?="[ \t]*(?:,[ \t\r\n]*"(?:market_price|recommended_price|estimated_days|realistic_days|proposal_text|pert|score|take_order|priority)"|\s*\}))',
                text,
            )
            if not just_m:
                just_m = re.search(r'"price_justification"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)

            if just_m:
                raw_just = just_m.group(1)
                try:
                    clean_just = json.loads(f'"{raw_just}"')
                except Exception:
                    clean_just = raw_just.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                result["price_justification"] = sanitize_proposal_text(clean_just)

            days_m = re.search(r'"(?:estimated_days|realistic_days)"\s*:\s*"([^"]+)"', text)
            if days_m:
                result["estimated_days"] = sanitize_proposal_text(days_m.group(1))
            elif re.search(r'"(?:estimated_days|realistic_days)"\s*:\s*([0-9.]+)', text):
                dm = re.search(r'"(?:estimated_days|realistic_days)"\s*:\s*([0-9.]+)', text)
                result["estimated_days"] = f"{dm.group(1)} дн."

            return result

    # Если это чистый текст (не JSON)
    cleaned_text = re.sub(r"^```[a-zA-Z]*\n", "", text)
    cleaned_text = re.sub(r"\n```$", "", cleaned_text).strip()
    result["proposal_text"] = sanitize_proposal_text(cleaned_text)
    return result
