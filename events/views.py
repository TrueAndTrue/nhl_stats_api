from django.http import HttpResponse


def index(request):
    return HttpResponse("events index — endpoints pending rewrite against new schema")
