from django.http import JsonResponse
from .enums import AccountType
from .models import Account
from datetime import datetime as dt


def index(request):
    return JsonResponse({"message": "Welcome to the accounts API!"})


def create_account(request):

    data = {
        "name": request.GET.get("name", "Default Account"),
        "account_type": request.GET.get("account_type", AccountType.SALES.value),
        "balance": float(request.GET.get("balance", 0.0)),
    }

    account = Account.nodes.first_or_none(
        name=data["name"],
        account_type=data["account_type"],
        balance=data["balance"],
    )

    if not account:
        account = Account(
            name=data["name"],
            account_type=data["account_type"],
            balance=data["balance"],
        )
        account.save()
    else:
        return JsonResponse({"message": "Account already exists!"}, status=400)

    return JsonResponse({"message": "Account created successfully!", "data": data})


def get_all_accounts(request):
    accounts = Account.nodes.all()
    accounts_data = [
        {
            "id": str(account.element_id),
            "name": account.name,
            "account_type": account.account_type,
            "balance": account.balance,
            "created_at": dt.fromisoformat(str(account.created_at)).strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": dt.fromisoformat(str(account.updated_at)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for account in accounts
    ]
    return JsonResponse({"accounts": accounts_data})


def get_all_account_types(request):
    account_types = [atype.value for atype in AccountType]
    return JsonResponse({"account_types": account_types})


def get_account_by_id(request):

    account_id = request.GET.get("account_id", None)
    if not account_id:
        return JsonResponse({"message": "Account ID is required!"}, status=400)

    account = Account.nodes.get_or_none(account_id=account_id)
    if account:
        account_data = {
            "id": str(account.element_id),
            "name": account.name,
            "account_type": account.account_type,
            "balance": account.balance,
            "created_at": dt.fromisoformat(str(account.created_at)).strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": dt.fromisoformat(str(account.updated_at)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        return JsonResponse({"account": account_data})

    return JsonResponse({"message": "Account not found!"}, status=404)
