from django.http import JsonResponse
from .models import BankAccount
from datetime import datetime as dt


def index(request):
    return JsonResponse({"message": "Welcome to the banks API!"})


def create_bank_account(request):
    # Placeholder logic for creating a bank account

    data = {
        "name": request.GET.get("name", "Default Bank Account"),
        "account_number": request.GET.get("account_number", "0000000000"),
        "bank_name": request.GET.get("bank_name", "Default Bank"),
        "opening_balance": float(request.GET.get("opening_balance", 0.0)),
        "opening_balance_date": request.GET.get("opening_balance_date", None),
    }

    bank_account = BankAccount.nodes.first_or_none(
        name=data["name"],
        account_number=data["account_number"],
        bank_name=data["bank_name"],
        opening_balance=data["opening_balance"],
    )

    if not bank_account:
        bank_account = BankAccount(
            name=data["name"],
            account_number=data["account_number"],
            bank_name=data["bank_name"],
            opening_balance=data["opening_balance"],
            opening_balance_date=data["opening_balance_date"] if data["opening_balance_date"] else dt.now(
            ),
        )
        bank_account.save()
    else:
        return JsonResponse({"message": "Bank account already exists!"}, status=400)

    return JsonResponse({"message": "Bank account created successfully!", "data": data})
