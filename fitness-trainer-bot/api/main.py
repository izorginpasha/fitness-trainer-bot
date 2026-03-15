"""
Backend API: платежи Robokassa, ResultURL/SuccessURL/FailURL.
"""

import hashlib
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException
from pydantic import BaseModel

from db.session import init_db, create_payment, update_payment_status, get_payment_by_inv_id

# Загружаем .env: сначала api/.env, иначе корень проекта
_env_path = Path(__file__).resolve().parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


app = FastAPI(title="Fitness Trainer Bot API")


class CreatePaymentRequest(BaseModel):
    telegram_id: int
    tariff_code: str
    out_sum: float
    description: str


class CreatePaymentResponse(BaseModel):
    inv_id: int
    payment_url: str


def _build_robokassa_payment_url(
    *,
    inv_id: int,
    out_sum: float,
    description: str,
) -> str:
    merchant_login = os.getenv("ROBOKASSA_MERCHANT_LOGIN") or "demo"
    password1 = os.getenv("ROBOKASSA_PASSWORD1") or "password_1"
    is_test = os.getenv("ROBOKASSA_IS_TEST", "1")

    out_sum_str = f"{out_sum:.2f}".replace(",", ".")
    signature_str = f"{merchant_login}:{out_sum_str}:{inv_id}:{password1}"
    signature = hashlib.md5(signature_str.encode("utf-8")).hexdigest()

    base_url = "https://auth.robokassa.ru/Merchant/Index.aspx"
    params = (
        f"MerchantLogin={merchant_login}"
        f"&OutSum={out_sum_str}"
        f"&InvId={inv_id}"
        f"&Description={description}"
        f"&SignatureValue={signature}"
        f"&IsTest={is_test}"
    )
    return f"{base_url}?{params}"


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.post("/payment/create", response_model=CreatePaymentResponse)
def create_payment_endpoint(payload: CreatePaymentRequest):
    """
    Создать платёж и вернуть ссылку Robokassa.
    """
    # В реальном проекте inv_id лучше генерировать последовательностью из БД.
    from datetime import datetime

    inv_id = int(datetime.utcnow().timestamp())

    create_payment(
        telegram_id=payload.telegram_id,
        tariff_code=payload.tariff_code,
        out_sum=payload.out_sum,
        inv_id=inv_id,
        description=payload.description,
        status="pending",
    )

    payment_url = _build_robokassa_payment_url(
        inv_id=inv_id,
        out_sum=payload.out_sum,
        description=payload.description,
    )

    return CreatePaymentResponse(inv_id=inv_id, payment_url=payment_url)


def _verify_result_signature(out_sum: str, inv_id: str, signature_value: str) -> bool:
    password2 = os.getenv("ROBOKASSA_PASSWORD2")
    merchant_login = os.getenv("ROBOKASSA_MERCHANT_LOGIN")
    if not merchant_login or not password2:
        return False

    base_string = f"{out_sum}:{inv_id}:{password2}"
    control_signature = hashlib.md5(base_string.encode("utf-8")).hexdigest()

    return control_signature.lower() == signature_value.lower()


@app.post("/payment/result")
def payment_result(
    OutSum: str = Form(...),
    InvId: str = Form(...),
    SignatureValue: str = Form(...),
) -> str:
    """
    ResultURL от Robokassa. Проверяем подпись с Паролем №2 и отмечаем платёж успешным.
    Robokassa ожидает ответ вида "OK<InvId>" при успешной обработке.
    """
    if not _verify_result_signature(OutSum, InvId, SignatureValue):
        raise HTTPException(status_code=400, detail="invalid signature")

    inv_id_int = int(InvId)
    payment = get_payment_by_inv_id(inv_id_int)
    if not payment:
        raise HTTPException(status_code=404, detail="payment not found")

    update_payment_status(inv_id_int, "success")
    return f"OK{InvId}"


@app.get("/payment/success")
def payment_success(InvId: Optional[int] = None):
    """
    SuccessURL для Robokassa. Можно возвращать простую HTML-страницу или текст.
    """
    if InvId is None:
        return "Оплата успешно выполнена."

    payment = get_payment_by_inv_id(InvId)
    if not payment:
        return "Оплата успешно выполнена, но платёж не найден в системе."

    return f"Оплата по счёту #{InvId} успешно выполнена. Спасибо!"


@app.get("/payment/fail")
def payment_fail(InvId: Optional[int] = None):
    """
    FailURL для Robokassa.
    """
    if InvId is None:
        return "Оплата не была выполнена или была отменена."

    update_payment_status(InvId, "fail")
    return f"Оплата по счёту #{InvId} не была выполнена или была отменена."
