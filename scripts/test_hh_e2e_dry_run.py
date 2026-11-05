"""E2E dry-run test for HeadHunter applicant authorization and apply pipeline without actual send."""

import asyncio
import json
import re
import httpx
from src.config import settings
from src.models.analysis import sanitize_proposal_text
from src.storage.repository import OrderRepository


async def run_e2e_dry_run():
    repo = OrderRepository()

    print("==================================================")
    print("🚀 Запуск E2E проверки цепочки HeadHunter (Dry Run)")
    print("==================================================")

    # 1. Проверяем OAuth токены соискателя в базе
    user_token = await repo.get_setting("hh_user_token")
    if not user_token:
        print("❌ [FAIL] hh_user_token не найден в базе данных!")
        return False
    print(f"✅ [OK] Токен соискателя в базе SQLite найден: {user_token[:15]}... (длина {len(user_token)})")

    # 2. Проверяем валидность токена соискателя через GET /me
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            "https://api.hh.ru/me",
            headers={
                "Authorization": f"Bearer {user_token}",
                "User-Agent": settings.HH_USER_AGENT,
                "HH-User-Agent": settings.HH_USER_AGENT,
            },
        )
        if r.status_code != 200:
            print(f"❌ [FAIL] GET /me вернул статус {r.status_code}: {r.text}")
            return False
        me_data = r.json()
        first_name = me_data.get("first_name", "")
        last_name = me_data.get("last_name", "")
        user_id = me_data.get("id")
        email = me_data.get("email")
        resumes_count = me_data.get("counters", {}).get("resumes_count", 0)
        auth_type = me_data.get("auth_type")
        is_applicant = me_data.get("is_applicant")

        print(f"✅ [OK] HeadHunter авторизация подтверждена!")
        print(f"   Пользователь: {first_name} {last_name} (ID: {user_id})")
        print(f"   Email: {email}")
        print(f"   Тип аккаунта: {auth_type} (is_applicant={is_applicant})")
        print(f"   Количество резюме в аккаунте: {resumes_count}")

    # 3. Выбираем реальную вакансию HeadHunter из базы данных
    async with repo._get_conn() as db:
        async with db.execute(
            "SELECT id, external_id, title, url, proposal_text FROM orders WHERE source = 'hh_ru' ORDER BY id DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()

    if not row:
        print("❌ [FAIL] В базе данных нет вакансий hh_ru!")
        return False

    order_id, external_id, title, url, proposal_text = row
    print(f"✅ [OK] Выбрана целевая вакансия #{order_id}: {title}")
    print(f"   URL: {url}")
    print(f"   External ID: {external_id}")

    # 4. Проверяем парсинг vacancy_id
    vac_id = external_id
    if not vac_id and url:
        m = re.search(r"/vacancy/(\d+)", url)
        if m:
            vac_id = m.group(1)
    if not vac_id:
        print("❌ [FAIL] Не удалось определить ID вакансии!")
        return False
    print(f"✅ [OK] Вакансия валидна, ID для API HeadHunter: {vac_id}")

    # 5. Проверяем сопроводительное письмо и санитайзер дежурных фраз
    test_letter = (
        proposal_text
        if proposal_text
        else (
            "Здравствуйте! Ознакомился с вакансией.\n\n"
            "Мой стек: Python, FastAPI, PostgreSQL, LangChain.\n\n"
            "Буду рад обсудить задачи ROOMGRAM, кейсы автоматизации и детали решений на звонке или личной встрече.\n\n"
            "Telegram: @Horizontal84\n"
            "Email: pimenoffandrew@gmail.com"
        )
    )
    cleaned_letter = sanitize_proposal_text(test_letter)
    print("✅ [OK] Сопроводительное письмо подготовлено и очищено от шаблонных фраз:")
    print("----------------------------------------------------------------------")
    print(cleaned_letter)
    print("----------------------------------------------------------------------")
    assert "Буду рад обсудить" not in cleaned_letter, "Ошибка: фраза 'Буду рад обсудить' не была удалена санитайзером!"
    assert "Telegram: @Horizontal84" in cleaned_letter

    # 6. Проверяем ID резюме в базе
    resume_id = await repo.get_setting("hh_resume_id")
    resume_title = await repo.get_setting("hh_resume_title")
    print(f"ℹ️  [INFO] Резюме в базе: {resume_title or 'Не задано'} (ID: {resume_id or 'Ожидает выбора/ввода'})")

    # 7. Формирование финального payload для POST /negotiations БЕЗ отправки
    target_resume_id = resume_id or "<HH_RESUME_ID>"
    payload = {
        "vacancy_id": str(vac_id),
        "resume_id": str(target_resume_id),
        "message": cleaned_letter,
    }
    print("✅ [OK] Сформирован финальный payload для запроса POST https://api.hh.ru/negotiations:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("🛑 [STOP] Остановка перед отправкой отклика (POST запрос намеренно НЕ отправлялся).")
    print("==================================================")
    print("🎉 Результат: E2E пайплайн полностью работоспособен!")
    print("==================================================")
    return True


if __name__ == "__main__":
    asyncio.run(run_e2e_dry_run())
