from decimal import Decimal
from .models import AuditLog, FinancialTransaction, CashAccount


def audit(business, user, action, obj, description, metadata=None):
    return AuditLog.objects.create(
        business=business, created_by=user, action=action,
        model_name=obj.__class__.__name__ if obj else "system",
        object_id=str(getattr(obj, "pk", "")), description=description,
        metadata=metadata or {},
    )


def record_cash(business, user, *, date, amount, transaction_type, category, description,
                payment_method="", reference="", account=None):
    amount = Decimal(amount or 0)
    if amount <= 0:
        return None
    if account is None:
        account = CashAccount.objects.filter(business=business, active=True).order_by("id").first()
        if account is None:
            account = CashAccount.objects.create(business=business, name="Main Cash", account_type="cash", created_by=user)
    elif account.business_id != business.id:
        raise ValueError("Cash account belongs to a different business.")
    return FinancialTransaction.objects.create(
        business=business, created_by=user, date=date, amount=amount,
        transaction_type=transaction_type, category=category,
        description=description, payment_method=payment_method or "",
        reference=reference or "", account=account,
    )
