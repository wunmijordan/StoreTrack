from decimal import Decimal
from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.db.models import Q
from .models import Order, OrderItem, ProductionBatch, ProductionQualityCheck
from inventory.models import FinishedGood
from sales.models import Customer
from core.models import CashAccount

INPUT_CLS = "w-full rounded-md border border-[#D9CFB4] bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#8f172d]/30 focus:border-[#8f172d]"


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = INPUT_CLS


class OrderForm(StyledModelForm):
    class Meta:
        model = Order
        fields = ["date", "order_type", "production_destination", "non_stock_purpose", "customer", "customer_name", "customer_region", "customer_group", "customer_payment_status", "customer_payment_method", "customer_payment_account",
                  "transaction_type", "unpaid_description", "payment_method", "account", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "production_destination": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(active=True).order_by("name")
        self.fields["production_destination"].required = False
        self.fields["non_stock_purpose"].required = False
        self.fields["customer"].required = False
        self.fields["customer"].label = "Customer (from Customer list)"
        self.fields["customer"].help_text = "Required for Distribution. Optional for Online orders."
        self.fields["customer_name"].required = False
        self.fields["customer_name"].label = "Customer name (optional)"
        self.fields["customer_region"].required = False
        self.fields["customer_region"].label = "Region (optional)"
        self.fields["customer_group"].required = False
        self.fields["customer_group"].label = "Group (optional)"
        self.fields["payment_method"].required = False
        accounts = CashAccount.objects.filter(active=True).order_by("name")
        self.fields["account"].queryset = accounts
        self.fields["customer_payment_account"].queryset = accounts
        self.fields["customer_payment_account"].required = False
        self.fields["account"].required = False
        selected_type = (self.data.get("order_type") if self.data else None) or self.initial.get("order_type") or getattr(self.instance, "order_type", None)
        if selected_type in ("distribution", "online"):
            self.fields["transaction_type"].required = False
            self.fields["unpaid_description"].required = False
            self.fields["account"].required = False
            self.fields["customer_payment_status"].required = True
            # Method/account are only meaningful once payment status is
            # Received. Receivable orders deliberately leave both blank.
            self.fields["customer_payment_method"].required = False
        else:
            self.fields["customer_payment_status"].required = False
            self.fields["production_destination"].required = True
            self.fields["customer_payment_method"].required = False
            self.fields["customer_payment_account"].required = False

    def clean(self):
        cleaned = super().clean()
        order_type = cleaned.get("order_type")
        customer = cleaned.get("customer")
        # Distribution retains the existing customer-master requirement.
        # Online orders may come from an ad-hoc web buyer, so customer master,
        # name, region and group are all optional while the rest of the order
        # workflow (pricing, payment status, approval and fulfilment) is unchanged.
        if order_type == "distribution" and not customer:
            self.add_error("customer", "Select a customer from the customer master for a Distribution order.")
        if order_type == "physical_store":
            cleaned["customer"] = None
            cleaned["customer_name"] = ""
            cleaned["customer_region"] = ""
            cleaned["customer_group"] = ""
        if order_type == "physical_store":
            # Physical Store Orders are never payment records. Direct sale
            # payment is captured only when the product is sold from Sales.
            cleaned["transaction_type"] = "paid"
            cleaned["unpaid_description"] = ""
            cleaned["customer_payment_status"] = "paid"
            cleaned["customer_payment_method"] = ""
            cleaned["customer_payment_account"] = None
            cleaned["payment_method"] = ""
            cleaned["account"] = None
            if not cleaned.get("production_destination"):
                cleaned["production_destination"] = "store"
            if cleaned.get("production_destination") == "non_stock" and not (cleaned.get("non_stock_purpose") or "").strip():
                self.add_error("non_stock_purpose", "Enter the specific purpose for this non-stock production.")
            elif cleaned.get("production_destination") == "store":
                cleaned["non_stock_purpose"] = ""
        else:
            if cleaned.get("customer_payment_status") == "paid" and not cleaned.get("customer_payment_account"):
                self.add_error("customer_payment_account", "Select the account where the customer's payment was received.")
            if cleaned.get("customer_payment_status") == "paid":
                cleaned["transaction_type"] = "paid"
                cleaned["unpaid_description"] = ""
                cleaned["account"] = cleaned.get("customer_payment_account")
                cleaned["payment_method"] = cleaned.get("customer_payment_method") or "Transfer"
            else:
                cleaned["transaction_type"] = "unpaid"
                cleaned["unpaid_description"] = "Customer receivable — payment to be recorded through Finance."
                cleaned["customer_payment_method"] = ""
                cleaned["customer_payment_account"] = None
                cleaned["payment_method"] = ""
                cleaned["account"] = None
        return cleaned


class OrderItemForm(StyledModelForm):
    class Meta:
        model = OrderItem
        fields = ["finished_good", "batch_qty", "piece_qty", "production_batch_qty", "production_piece_qty", "discount"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("batch_qty", "piece_qty", "production_batch_qty", "production_piece_qty", "discount"):
            self.fields[name].required = False
            self.fields[name].widget.attrs.update({"min": "0", "step": "0.01"})
        self.fields["production_batch_qty"].label = "Produce batches"
        self.fields["production_piece_qty"].label = "Produce pieces"

    def clean(self):
        cleaned = super().clean()
        for name in ("batch_qty", "piece_qty", "production_batch_qty", "production_piece_qty", "discount"):
            if cleaned.get(name) is None:
                cleaned[name] = Decimal("0")
        if cleaned.get("finished_good") and cleaned["batch_qty"] <= 0 and cleaned["piece_qty"] <= 0:
            self.add_error("piece_qty", "Enter at least one ordered batch or piece.")
        return cleaned


class OrderItemFormSetBase(BaseInlineFormSet):
    """Apply the Physical Store product restriction only to store replenishment.

    Non-stock Physical Store production is intentionally allowed to use any
    finished good, including products with reorder_level=0. Distribution and
    Online orders also retain the full finished-good catalogue.
    """
    def __init__(self, *args, store_replenishment=False, order_type=None, **kwargs):
        self.order_type = order_type or getattr(kwargs.get("instance"), "order_type", None)
        super().__init__(*args, **kwargs)
        if store_replenishment:
            allowed = FinishedGood.objects.filter(
                stock__isnull=False,
                reorder_level__gt=0,
            ).order_by("name")
            for form in self.forms:
                form.fields["finished_good"].queryset = allowed

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        for form in self.forms:
            data = getattr(form, "cleaned_data", None) or {}
            if data.get("DELETE") or not data.get("finished_good"):
                continue
            good = data["finished_good"]
            upb = good.units_per_batch or Decimal("1")
            ordered = (data.get("batch_qty") or Decimal("0")) * upb + (data.get("piece_qty") or Decimal("0"))
            plan_batches = data.get("production_batch_qty") or Decimal("0")
            plan_pieces = data.get("production_piece_qty") or Decimal("0")
            production_plan = plan_batches * upb + plan_pieces
            if self.order_type == "physical_store":
                # A physical-store order already is a production request; the
                # separate plan is only meaningful for customer-order offcuts.
                data["production_batch_qty"] = Decimal("0")
                data["production_piece_qty"] = Decimal("0")
            elif production_plan > 0 and production_plan < ordered:
                form.add_error(
                    "production_batch_qty",
                    f"Production plan ({production_plan:.2f}) cannot be below the customer order ({ordered:.2f}). Leave both production-plan fields at 0 to produce exactly the order quantity.",
                )


OrderItemFormSet = inlineformset_factory(
    Order, OrderItem, form=OrderItemForm, formset=OrderItemFormSetBase,
    extra=1, can_delete=True,
)


class ProductionCompletionForm(forms.Form):
    produced_units = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, label="Gross units produced", widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}))
    wastage_units = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, label="Wastage / rejected units", initial=0, widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}))
    batch_number = forms.CharField(max_length=60, label="Batch number")
    expiry_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Expiry date")
    wastage_reason = forms.CharField(max_length=255, required=False, label="Wastage reason")
    qc_status = forms.ChoiceField(choices=ProductionQualityCheck.STATUS_CHOICES, initial="pending", label="Quality status")
    qc_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="QC notes")
    flag_shortage = forms.BooleanField(required=False, label="Flag production shortage for reconciliation")
    shortage_reason = forms.CharField(max_length=255, required=False, label="Shortage / reconciliation reason")
    excess_to_stock = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, initial=0, label="Excess to Physical Store stock")
    excess_to_non_stock = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, initial=0, label="Excess to non-stock purpose")
    excess_non_stock_purpose = forms.CharField(max_length=255, required=False, label="Non-stock excess purpose")
    planned_offcut_to_stock = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False, initial=0, label="Planned offcut to Physical Store")
    planned_offcut_to_customer = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False, initial=0, label="Planned offcut to customer")
    planned_offcut_customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False, label="Interested customer")
    planned_offcut_channel = forms.ChoiceField(choices=[("", "Select channel"), ("distribution", "Distribution"), ("online", "Online")], required=False, label="Customer channel")

    def __init__(self, *args, planned_units=None, required_units=None, customer_order=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.planned_units = Decimal(planned_units or 0).quantize(Decimal("0.01"))
        self.required_units = Decimal(required_units if required_units is not None else planned_units or 0).quantize(Decimal("0.01"))
        self.customer_order = bool(customer_order)
        self.fields["planned_offcut_customer"].queryset = Customer.objects.filter(active=True).order_by("name")
        for f in self.fields.values():
            f.widget.attrs["class"] = INPUT_CLS
        self.fields["produced_units"].help_text = (
            f"Production target: {self.planned_units:.2f} units"
            + (f"; customer requires {self.required_units:.2f}." if self.customer_order else ".")
            + " Enter gross output before wastage/rejection."
        )

    def clean(self):
        cleaned = super().clean()
        produced = cleaned.get("produced_units") or Decimal("0")
        wastage = cleaned.get("wastage_units") or Decimal("0")
        if wastage > produced:
            self.add_error("wastage_units", "Wastage cannot exceed gross units produced.")
        if wastage > 0 and not (cleaned.get("wastage_reason") or "").strip():
            self.add_error("wastage_reason", "Give a reason when wastage/rejected units are recorded.")
        cleaned["saleable_units"] = max(Decimal("0"), produced - wastage)
        shortage = max(Decimal("0"), self.required_units - cleaned["saleable_units"]) if self.customer_order else Decimal("0")
        planned_surplus = (
            max(Decimal("0"), min(cleaned["saleable_units"], self.planned_units) - self.required_units)
            if self.customer_order else Decimal("0")
        )
        to_planned_stock = cleaned.get("planned_offcut_to_stock") or Decimal("0")
        to_planned_customer = cleaned.get("planned_offcut_to_customer") or Decimal("0")
        cleaned["planned_surplus_stock_units"] = to_planned_stock
        cleaned["planned_surplus_customer_units"] = to_planned_customer
        if planned_surplus > 0:
            if (to_planned_stock + to_planned_customer) != planned_surplus:
                self.add_error("planned_offcut_to_stock", f"Allocate the full planned offcut of {planned_surplus:.2f} units between Physical Store and an interested customer.")
                self.add_error("planned_offcut_to_customer", f"Planned offcut allocation must total exactly {planned_surplus:.2f} units.")
            if to_planned_customer > 0:
                if not cleaned.get("planned_offcut_customer"):
                    self.add_error("planned_offcut_customer", "Select the customer receiving this planned offcut.")
                if cleaned.get("planned_offcut_channel") not in ("distribution", "online"):
                    self.add_error("planned_offcut_channel", "Select Distribution or Online for the interested customer.")
        else:
            if to_planned_stock or to_planned_customer:
                self.add_error("planned_offcut_to_stock", "There is no saleable planned offcut to allocate.")
            cleaned["planned_offcut_customer"] = None
            cleaned["planned_offcut_channel"] = ""
        if self.customer_order and shortage > 0 and not cleaned.get("flag_shortage"):
            self.add_error("flag_shortage", "Flag this shortage so it can be reconciled from available surplus production of the same product, regardless of channel.")
        if self.customer_order and shortage > 0 and not (cleaned.get("shortage_reason") or "").strip():
            self.add_error("shortage_reason", "Explain the shortage and how it is expected to be reconciled.")
        if not self.customer_order:
            cleaned["flag_shortage"] = False
            cleaned["shortage_reason"] = ""
        if shortage == 0 and cleaned.get("flag_shortage"):
            self.add_error("flag_shortage", "There is no production shortage to reconcile.")
        if shortage == 0:
            cleaned["shortage_reason"] = ""

        excess = max(Decimal("0"), cleaned["saleable_units"] - self.planned_units)
        to_stock = cleaned.get("excess_to_stock") or Decimal("0")
        to_non_stock = cleaned.get("excess_to_non_stock") or Decimal("0")
        cleaned["excess_units"] = excess
        if excess > 0:
            if (to_stock + to_non_stock) != excess:
                self.add_error("excess_to_stock", f"Allocate the full excess of {excess:.2f} units between Physical Store stock and non-stock purpose.")
                self.add_error("excess_to_non_stock", f"Allocated excess must total exactly {excess:.2f} units.")
            if to_non_stock > 0 and not (cleaned.get("excess_non_stock_purpose") or "").strip():
                self.add_error("excess_non_stock_purpose", "Give the purpose for excess units assigned outside Physical Store stock (for example Staff Welfare or Charity).")
        else:
            if to_stock or to_non_stock:
                self.add_error("excess_to_stock", "There is no excess saleable output to allocate.")
            cleaned["excess_non_stock_purpose"] = ""
        return cleaned


class ProductionReconciliationForm(forms.Form):
    source_batch = forms.ModelChoiceField(
        queryset=ProductionBatch.objects.none(),
        label="Source production batch",
    )
    quantity = forms.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01"),
        label="Quantity to reconcile",
    )
    reason = forms.CharField(max_length=255, label="Justification")

    def __init__(self, *args, target_batch=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_batch = target_batch
        if target_batch is not None:
            candidates = ProductionBatch.objects.filter(
                Q(planned_surplus_stock_units__gt=0) | Q(excess_stock_units__gt=0),
                business=target_batch.business,
                finished_good=target_batch.finished_good,
                is_reversed=False,
            ).exclude(pk=target_batch.pk).select_related("order", "finished_good")
            self.fields["source_batch"].queryset = candidates
            self.fields["source_batch"].label_from_instance = lambda obj: (
                f"{obj.batch_number} — {obj.order.get_order_type_display()} — "
                f"{obj.available_surplus_units:.2f} available"
            )

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("source_batch")
        qty = cleaned.get("quantity") or Decimal("0")
        target = self.target_batch
        if not target or not source:
            return cleaned
        if target.order.order_type not in ("distribution", "online"):
            self.add_error("source_batch", "Only Distribution/Online customer-order shortages can be reconciled.")
            return cleaned
        if not target.shortage_flag:
            self.add_error("source_batch", "This batch is not flagged for reconciliation.")
        if source.finished_good_id != target.finished_good_id:
            self.add_error("source_batch", "Source and target batches must be for the same finished good.")
        if qty > source.available_surplus_units:
            self.add_error("quantity", f"Only {source.available_surplus_units:.2f} units are currently available from that source batch/stock pool.")
        if qty > target.outstanding_shortage_units:
            self.add_error("quantity", f"Only {target.outstanding_shortage_units:.2f} units remain to be reconciled.")
        if not (cleaned.get("reason") or "").strip():
            self.add_error("reason", "Give a justification for this reconciliation.")
        return cleaned


class ProductionQualityCheckForm(StyledModelForm):
    class Meta:
        model = ProductionQualityCheck
        fields = ["status", "notes", "defects"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2}), "defects": forms.Textarea(attrs={"rows": 2})}
