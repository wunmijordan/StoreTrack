from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models import Sum
from .models import CashAccount, FinancialTransaction, AuditLog
from .finance_forms import CashAccountForm, SupplierPaymentForm, CustomerPaymentForm, StockAdjustmentForm
from .services import record_cash, audit
from procurement.models import SupplierPayment, PurchaseOrder
from sales.models import CustomerPayment, Sale
from inventory.models import StockAdjustment, StockMovement
from expenses.models import Expense, ExpensePayment
from inventory.services import record_raw_material_movement, record_finished_good_movement

def today(): return timezone.localdate()
@login_required
def finance_dashboard(request):
    accounts=CashAccount.objects.filter(active=True)
    tx=FinancialTransaction.objects.select_related("account","created_by")[:100]
    receivables = Decimal("0")
    for s in Sale.objects.filter(source__in=("distribution_order","online_order"), transaction_type__in=("unpaid","partial")).prefetch_related("items","payments"):
        receivables += max(Decimal("0"), s.total - sum((p.amount for p in s.payments.all()), Decimal("0")))
    payables = Decimal("0")
    for p in PurchaseOrder.objects.filter(payment_status__in=("unpaid","partial"), status="received").prefetch_related("items","payments"):
        payables += max(Decimal("0"), p.total - sum((x.amount for x in p.payments.all()), Decimal("0")))
    payables += Expense.objects.filter(payment_status="unpaid").aggregate(v=Sum("amount"))["v"] or Decimal("0")
    outstanding_sales = []
    for sale in Sale.objects.filter(source__in=("distribution_order","online_order"), transaction_type__in=("unpaid","partial")).prefetch_related("items","payments"):
        paid = sum((p.amount for p in sale.payments.all()), Decimal("0"))
        balance = max(Decimal("0"), sale.total - paid)
        if balance: outstanding_sales.append({"sale": sale, "balance": balance})
    outstanding_pos = []
    for po in PurchaseOrder.objects.filter(status="received", payment_status__in=("unpaid","partial")).prefetch_related("items","payments"):
        paid = sum((p.amount for p in po.payments.all()), Decimal("0"))
        balance = max(Decimal("0"), po.total - paid)
        if balance: outstanding_pos.append({"po": po, "balance": balance})
    outstanding_expenses = [
        {"expense": e, "balance": e.amount}
        for e in Expense.objects.filter(payment_status="unpaid").order_by("-date","-id")[:30]
    ]
    return render(request,"core/finance.html",{"accounts":accounts,"transactions":tx,"audit_logs":AuditLog.objects.select_related("created_by")[:80],
        "receivables":receivables,"payables":payables,"outstanding_sales":outstanding_sales[:30],
        "outstanding_pos":outstanding_pos[:30],"outstanding_expenses":outstanding_expenses})
@login_required
def cash_account_form(request,pk=None):
    obj=get_object_or_404(CashAccount,pk=pk) if pk else None
    form=CashAccountForm(request.POST or None,instance=obj)
    if request.method=="POST" and form.is_valid():
        x=form.save(commit=False); x.business=request.business
        if not obj: x.created_by=request.user
        x.save(); audit(request.business,request.user,"create" if not obj else "update",x,"Cash account saved"); messages.success(request,"Cash account saved."); return redirect("finance_dashboard")
    return render(request,"core/cash_account_form.html",{"form":form,"obj":obj})
@login_required
def supplier_payment_form(request):
    form=SupplierPaymentForm(request.POST or None,initial={"date":today()})
    if request.method=="POST" and form.is_valid():
        with transaction.atomic():
            x=form.save(commit=False); x.business=request.business; x.created_by=request.user; x.save()
            if x.purchase_order:
                po=x.purchase_order
                paid_before=sum((p.amount for p in po.payments.exclude(pk=x.pk)), Decimal("0"))
                outstanding=max(Decimal("0"), po.total-paid_before)
                new_paid=paid_before+x.amount
                po.payment_status="paid" if new_paid >= po.total else "partial"
                if new_paid >= po.total: po.payment_status="paid"
                po.save(update_fields=["payment_status","updated_at"])
                supplier=po.supplier or x.supplier
            else:
                supplier=x.supplier
            record_cash(request.business,request.user,date=x.date,amount=x.amount,transaction_type=FinancialTransaction.OUTFLOW,category="Supplier payment",description=f"Payment to {supplier}",payment_method=x.payment_method,reference=x.reference or f"SUPPAY-{x.pk}",account=x.account)
            audit(request.business,request.user,"create",x,"Supplier payment recorded",{"amount":str(x.amount),"purchase_order":getattr(x.purchase_order,"pk",None)})
        messages.success(request,"Supplier payment recorded and payable updated."); return redirect("finance_dashboard")
    return render(request,"core/payment_form.html",{"form":form,"supplier_payload":form.supplier_payload,"title":"Supplier Payment","help_text":"Pay an outstanding received purchase order. Stock was already received when the PO was received; this payment only settles the payable."})
@login_required
def customer_payment_form(request):
    form=CustomerPaymentForm(request.POST or None,initial={"date":today()})
    if request.method=="POST" and form.is_valid():
        with transaction.atomic():
            x=form.save(commit=False); x.business=request.business; x.created_by=request.user; x.save()
            sale=x.sale
            paid_before=sum((p.amount for p in sale.payments.exclude(pk=x.pk)), Decimal("0"))
            new_paid=paid_before+x.amount
            sale.transaction_type="paid" if new_paid >= sale.total else "partial"
            sale.save(update_fields=["transaction_type","updated_at"])
            if sale.linked_order and sale.source in ("distribution_order", "online_order"):
                # Customer orders have their own payment-status field. Keep the
                # physical-store transaction_type untouched; only a fully settled
                # receivable becomes Received on the originating order.
                linked_order = sale.linked_order
                if new_paid >= sale.total:
                    linked_order.customer_payment_status = "paid"
                    linked_order.save(update_fields=["customer_payment_status","updated_at"])
            record_cash(request.business,request.user,date=x.date,amount=x.amount,transaction_type=FinancialTransaction.INCOME,category="Customer payment",description=f"Payment from {sale.customer} — Sale #{sale.pk}",payment_method=x.payment_method,reference=x.reference or f"CUSTPAY-{x.pk}",account=x.account)
            audit(request.business,request.user,"create",x,"Customer payment recorded",{"amount":str(x.amount),"sale":sale.pk,"customer":sale.customer})
        messages.success(request,"Customer payment recorded and receivable updated."); return redirect("finance_dashboard")
    return render(request,"core/payment_form.html",{"form":form,"sales_payload":form.sales_payload,"title":"Customer Payment","help_text":"Only Distribution and Online customer sales appear here. Select the customer and then the specific sale being settled."})
@login_required
def stock_adjustment_form(request):
    form=StockAdjustmentForm(request.POST or None,initial={"date":today()})
    if request.method=="POST" and form.is_valid():
        with transaction.atomic():
            x=form.save(commit=False); x.business=request.business; x.created_by=request.user
            if x.raw_material:
                x.unit_value=x.raw_material.cost_per_unit
                if x.quantity + x.raw_material.stock < 0:
                    form.add_error("quantity","Adjustment would make stock negative."); return render(request,"core/adjustment_form.html",{"form":form})
            else:
                if x.finished_good.stock is None:
                    form.add_error("finished_good","This product is not configured for physical-store stock."); return render(request,"core/adjustment_form.html",{"form":form})
                if x.quantity + x.finished_good.stock < 0:
                    form.add_error("quantity","Adjustment would make stock negative."); return render(request,"core/adjustment_form.html",{"form":form})
                latest=x.finished_good.adjustments.order_by("-date","-id").first()
                x.unit_value=latest.unit_value if latest else x.finished_good.est_cost
            x.save()
            ref=f"ADJ-{x.pk}"
            if x.raw_material:
                record_raw_material_movement(x.raw_material,x.quantity,StockMovement.ADJUSTMENT,note=x.description,reference=ref,unit_value=x.unit_value,location=x.location)
            else:
                record_finished_good_movement(x.finished_good,x.quantity,StockMovement.ADJUSTMENT,note=x.description,reference=ref,unit_value=x.unit_value,location=x.location)
            audit(request.business,request.user,"create",x,"Stock adjustment recorded",{"quantity":str(x.quantity),"reason":x.reason})
        messages.success(request,"Stock adjustment recorded."); return redirect("finance_dashboard")
    return render(request,"core/adjustment_form.html",{"form":form})


