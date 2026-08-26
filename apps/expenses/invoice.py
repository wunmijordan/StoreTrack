from core.invoice import expense_invoice_pdf


def build_expense_invoice(expense, business=None):
    # Keep the expense endpoint compatible with its existing call signature while
    # using the exact same document layout as the core transaction invoices.
    return expense_invoice_pdf(expense)
