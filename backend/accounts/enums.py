from enum import Enum


class AccountType(Enum):
    SALES = "Sales"
    COST_OF_SALES = "Cost of Sales"
    EXPENSES = "Expenses"
    INCOME_TAX = "Income Tax"
    NON_CURRENT_ASSETS = "Non-Current Assets"
    CURRENT_ASSETS = "Current Assets"
    CURRENT_LIABILITIES = "Current Liabilities"
    NON_CURRENT_LIABILITIES = "Non-Current Liabilities"
    OWNERS_EQUITY = "Owner's Equity"
    OTHERS = "Other Incomes"

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]
