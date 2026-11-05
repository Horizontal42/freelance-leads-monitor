"""HeadHunter applicant service for managing OAuth authorization and 1-click applies."""

import logging
from typing import Any, Dict, Optional
import httpx

from src.config import settings
from src.models.analysis import sanitize_proposal_text
from src.storage.repository import OrderRepository

logger = logging.getLogger(__name__)


class HhApplicantService:
    """Сервис взаимодействия с API HeadHunter от лица соискателя (OAuth + отклики)."""

    def __init__(self, repo: OrderRepository) -> None:
        self.repo = repo

    def get_auth_url(self) -> str:
        """Получить URL для авторизации соискателя на hh.ru."""
        client_id = settings.HH_CLIENT_ID or ""
        redirect_uri = settings.HH_REDIRECT_URI or "https://jobs.3dvex.ru/callback"
        return f"https://hh.ru/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}"

    async def get_applicant_status(self) -> Dict[str, Any]:
        """Получить текущий статус подключения аккаунта HeadHunter."""
        user_token = await self.repo.get_setting("hh_user_token", None)
        resume_id = await self.repo.get_setting("hh_resume_id", None)
        resume_title = await self.repo.get_setting("hh_resume_title", None)

        is_connected = bool(user_token and resume_id)
        return {
            "connected": is_connected,
            "resume_id": resume_id,
            "resume_title": resume_title,
            "auth_url": self.get_auth_url(),
        }

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        """Обменять авторизационный код на access_token соискателя и получить резюме."""
        client_id = settings.HH_CLIENT_ID
        client_secret = settings.HH_CLIENT_SECRET
        redirect_uri = settings.HH_REDIRECT_URI

        if not client_id or not client_secret:
            return {
                "ok": False,
                "error": "HH_CLIENT_ID или HH_CLIENT_SECRET не заданы в конфигурации .env",
            }

        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Запрос access_token
            token_resp = await client.post(
                "https://api.hh.ru/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={
                    "User-Agent": settings.HH_USER_AGENT,
                    "HH-User-Agent": settings.HH_USER_AGENT,
                },
            )

            if token_resp.status_code != 200:
                logger.error("Ошибка обмена кода HH на токен: %s", token_resp.text)
                return {
                    "ok": False,
                    "error": f"Ошибка авторизации HeadHunter ({token_resp.status_code}): {token_resp.text}",
                }

            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")

            await self.repo.set_setting("hh_user_token", access_token)
            if refresh_token:
                await self.repo.set_setting("hh_refresh_token", refresh_token)
            if expires_in:
                await self.repo.set_setting("hh_token_expires_in", expires_in)

            # 2. Получение списка резюме соискателя
            resume_resp = await client.get(
                "https://api.hh.ru/resumes/mine",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": settings.HH_USER_AGENT,
                    "HH-User-Agent": settings.HH_USER_AGENT,
                },
            )

            resume_id = None
            resume_title = None
            if resume_resp.status_code == 200:
                resumes_data = resume_resp.json()
                items = resumes_data.get("items", [])
                if items:
                    # Выбираем первое активное резюме
                    active_res = next((r for r in items if r.get("status", {}).get("id") == "published"), items[0])
                    resume_id = active_res.get("id")
                    resume_title = active_res.get("title") or "Основное резюме"
                    await self.repo.set_setting("hh_resume_id", resume_id)
                    await self.repo.set_setting("hh_resume_title", resume_title)
            else:
                logger.warning("Не удалось получить список резюме: %s", resume_resp.text)

            return {
                "ok": True,
                "resume_id": resume_id,
                "resume_title": resume_title,
            }

    async def refresh_user_token(self) -> Optional[str]:
        """Обновить access_token через refresh_token."""
        refresh_token = await self.repo.get_setting("hh_refresh_token", None)
        client_id = settings.HH_CLIENT_ID
        client_secret = settings.HH_CLIENT_SECRET

        if not refresh_token or not client_id or not client_secret:
            return None

        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(
                "https://api.hh.ru/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={
                    "User-Agent": settings.HH_USER_AGENT,
                    "HH-User-Agent": settings.HH_USER_AGENT,
                },
            )
            if token_resp.status_code == 200:
                data = token_resp.json()
                new_token = data.get("access_token")
                new_refresh = data.get("refresh_token")
                await self.repo.set_setting("hh_user_token", new_token)
                if new_refresh:
                    await self.repo.set_setting("hh_refresh_token", new_refresh)
                return new_token
            return None

    async def apply_to_vacancy(self, vacancy_id: str, cover_letter: str) -> Dict[str, Any]:
        """Отправить отклик на вакансию через HeadHunter API."""
        user_token = await self.repo.get_setting("hh_user_token", None)
        resume_id = await self.repo.get_setting("hh_resume_id", None)

        if not user_token or not resume_id:
            return {
                "ok": False,
                "need_auth": True,
                "message": "Аккаунт HeadHunter не подключен. Авторизуйтесь через настройки для включения откликов в 1 клик.",
                "auth_url": self.get_auth_url(),
            }

        # Очистка сопроводительного письма (удаление дежурных фраз и контактов)
        clean_letter = sanitize_proposal_text(cover_letter)

        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {
                "Authorization": f"Bearer {user_token}",
                "User-Agent": settings.HH_USER_AGENT,
                "HH-User-Agent": settings.HH_USER_AGENT,
            }
            payload = {
                "vacancy_id": str(vacancy_id),
                "resume_id": str(resume_id),
                "message": clean_letter,
            }

            resp = await client.post(
                "https://api.hh.ru/negotiations",
                data=payload,
                headers=headers,
            )

            # Если токен истек, пробуем обновить один раз
            if resp.status_code in (401, 403):
                new_token = await self.refresh_user_token()
                if new_token:
                    headers["Authorization"] = f"Bearer {new_token}"
                    resp = await client.post(
                        "https://api.hh.ru/negotiations",
                        data=payload,
                        headers=headers,
                    )

            if resp.status_code in (200, 201):
                logger.info("Успешный отклик на вакансию HH #%s", vacancy_id)
                return {
                    "ok": True,
                    "status": "applied",
                    "message": "Отклик успешно отправлен на HeadHunter!",
                }

            # Обработка ошибки с обязательным опросником
            err_text = resp.text
            if "test" in err_text.lower() or "question" in err_text.lower():
                return {
                    "ok": False,
                    "requires_test": True,
                    "message": "Работодатель требует прохождения опросника/теста перед откликом.",
                    "url": f"https://hh.ru/vacancy/{vacancy_id}",
                }

            # Уже откликались
            if "already_applied" in err_text.lower() or "нельзя откликнуться повторно" in err_text.lower():
                return {
                    "ok": True,
                    "status": "already_applied",
                    "message": "Вы уже откликались на эту вакансию ранее.",
                }

            logger.warning("Ошибка отклика на HH #%s: (%d) %s", vacancy_id, resp.status_code, err_text)
            return {
                "ok": False,
                "error": f"Ошибка отклика ({resp.status_code}): {err_text}",
                "url": f"https://hh.ru/vacancy/{vacancy_id}",
            }
