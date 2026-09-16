import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import ProtectedError
from django.http import HttpResponseNotAllowed, JsonResponse
from django.views.decorators.csrf import csrf_exempt


def serialize_instance(instance):
    data = {}

    for field in instance._meta.concrete_fields:
        value = getattr(instance, field.name)

        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            data[field.name] = getattr(instance, field.attname)
        elif isinstance(field, models.FileField):
            data[field.name] = value.url if value else None
        elif isinstance(value, Decimal):
            data[field.name] = str(value)
        elif hasattr(value, "isoformat"):
            data[field.name] = value.isoformat()
        else:
            data[field.name] = value

    return data


def parse_json_body(request):
    if not request.body:
        return {}

    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        raise ValidationError("Request body must be valid JSON.")

    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")

    return data


def apply_payload(instance, payload, *, creating=False):
    editable_fields = {
        field.name: field
        for field in instance._meta.concrete_fields
        if not (field.primary_key and isinstance(field, models.AutoField))
    }

    for name, value in payload.items():
        field = editable_fields.get(name)
        if field is None:
            continue

        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            setattr(instance, field.attname, value)
        else:
            setattr(instance, name, value)

    instance.full_clean()
    instance.save()
    return instance


def validation_error_response(error):
    if hasattr(error, "message_dict"):
        return JsonResponse({"errors": error.message_dict}, status=400)
    return JsonResponse({"errors": error.messages}, status=400)


def build_crud_views(model):
    @csrf_exempt
    def collection_view(request):
        if request.method == "GET":
            objects = model.objects.all()
            return JsonResponse({"results": [serialize_instance(obj) for obj in objects]})

        if request.method == "POST":
            try:
                payload = parse_json_body(request)
                instance = apply_payload(model(), payload, creating=True)
            except ValidationError as error:
                return validation_error_response(error)

            return JsonResponse(serialize_instance(instance), status=201)

        return HttpResponseNotAllowed(["GET", "POST"])

    @csrf_exempt
    def detail_view(request, pk):
        try:
            instance = model.objects.get(pk=pk)
        except model.DoesNotExist:
            return JsonResponse({"detail": f"{model.__name__} not found."}, status=404)

        if request.method == "GET":
            return JsonResponse(serialize_instance(instance))

        if request.method in {"PUT", "PATCH"}:
            try:
                payload = parse_json_body(request)
                instance = apply_payload(instance, payload)
            except ValidationError as error:
                return validation_error_response(error)

            return JsonResponse(serialize_instance(instance))

        if request.method == "DELETE":
            try:
                instance.delete()
            except ProtectedError:
                return JsonResponse({"detail": f"{model.__name__} is referenced by other records."}, status=409)

            return JsonResponse({}, status=204)

        return HttpResponseNotAllowed(["GET", "PUT", "PATCH", "DELETE"])

    collection_view.__name__ = f"{model.__name__.lower()}_list_create"
    detail_view.__name__ = f"{model.__name__.lower()}_detail"

    return collection_view, detail_view

