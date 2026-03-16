"""
Запрос к AI-модели в роли фитнес-тренера.
Поддерживаются: Groq, OpenRouter (free), Google Gemini — по очереди по наличию ключей.
"""
import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Подгружаем .env из папки bot или корня проекта
_bot_env = Path(__file__).resolve().parent.parent / ".env"
if _bot_env.exists():
    load_dotenv(_bot_env)
else:
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

SYSTEM_PROMPT = """Ты — дружелюбный фитнес-тренер. Отвечай кратко и по делу на русском языке.
Давай практичные советы по тренировкам, питанию, восстановлению и мотивации.
Не ставь диагнозы и при серьёзных проблемах со здоровьем советуй обратиться к врачу.
Отвечай в одном сообщении, без длинных списков, если пользователь не просит подробный план."""


async def _ask_groq(user_message: str) -> Optional[str]:
    """Groq API (OpenAI-совместимый), бесплатный tier."""
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        return None
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message.strip()},
        ],
        "max_tokens": 1024,
        "temperature": 0.7,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.warning("Groq API error: status=%s body=%s", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message", {}).get("content") or "").strip()
        return text or None
    except Exception as e:
        logger.exception("Groq request failed: %s", e)
        return None


async def _ask_openrouter(user_message: str) -> Optional[str]:
    """OpenRouter API — бесплатные модели (openrouter/free)."""
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return None
    model = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/fitness-trainer-bot",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message.strip()},
        ],
        "max_tokens": 1024,
        "temperature": 0.7,
    }
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.warning("OpenRouter API error: status=%s body=%s", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message", {}).get("content") or "").strip()
        return text or None
    except Exception as e:
        logger.exception("OpenRouter request failed: %s", e)
        return None


async def ask_fitness_trainer(user_message: str) -> Optional[str]:
    """
    Отправляет вопрос AI в роли фитнес-тренера.
    Порядок: Groq → OpenRouter → Gemini (по наличию ключей и успешному ответу).
    """
    if not user_message or not user_message.strip():
        return None

    # 1) Groq
    answer = await _ask_groq(user_message)
    if answer:
        return answer

    # 2) OpenRouter
    answer = await _ask_openrouter(user_message)
    if answer:
        return answer

    # 3) Gemini
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return None

    env_model = (os.getenv("GEMINI_MODEL") or "").strip()
    models_to_try = [env_model] if env_model else [
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash",
        "gemini-1.5-pro-latest",
        "gemini-pro",
        "gemini-2.0-flash",
    ]
    payload = {
        "contents": [{"parts": [{"text": user_message.strip()}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.7},
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for model in models_to_try:
                if not model:
                    continue
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates") or []
                    if candidates:
                        parts = (candidates[0].get("content") or {}).get("parts") or []
                        if parts:
                            text = (parts[0].get("text") or "").strip()
                            if text:
                                return text
                if resp.status_code == 429:
                    logger.warning("Gemini API rate limit (429) for model=%s", model)
                    return None
                if resp.status_code == 404:
                    continue
        return None
    except Exception as e:
        logger.exception("Gemini request failed: %s", e)
        return None
