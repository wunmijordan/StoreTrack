def business(request):
    return {"biz": getattr(request, "business", None)}
