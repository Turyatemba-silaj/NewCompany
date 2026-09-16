from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render


def build_page_views(model, form_class, *, department_name, template_dir, route_base, list_fields):
    model_name = model._meta.verbose_name.title()
    model_name_plural = model._meta.verbose_name_plural.title()

    route_names = {
        "list": f"{route_base}-page-list",
        "create": f"{route_base}-page-create",
        "detail": f"{route_base}-page-detail",
        "update": f"{route_base}-page-update",
        "delete": f"{route_base}-page-delete",
    }

    def base_context():
        return {
            "department_name": department_name,
            "model_name": model_name,
            "model_name_plural": model_name_plural,
            "route_names": route_names,
            "list_fields": list_fields,
        }

    def list_view(request):
        context = base_context()
        context["objects"] = model.objects.all()
        context["form"] = form_class()
        context["form_title"] = f"Create {model_name}"
        context["submit_label"] = "Create"
        return render(request, f"webroaster/{template_dir}/list.html", context)

    def create_view(request):
        form = form_class(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            instance = form.save()
            messages.success(request, f"{model_name} created successfully.")
            return redirect(route_names["detail"], pk=instance.pk)

        context = base_context()
        context.update({"form": form, "form_title": f"Create {model_name}", "submit_label": "Create"})
        return render(request, f"webroaster/{template_dir}/form.html", context)

    def detail_view(request, pk):
        instance = get_object_or_404(model, pk=pk)
        context = base_context()
        context["object"] = instance
        context["fields"] = [field.name for field in model._meta.fields]
        return render(request, f"webroaster/{template_dir}/detail.html", context)

    def update_view(request, pk):
        instance = get_object_or_404(model, pk=pk)
        form = form_class(request.POST or None, request.FILES or None, instance=instance)
        if request.method == "POST" and form.is_valid():
            instance = form.save()
            messages.success(request, f"{model_name} updated successfully.")
            return redirect(route_names["detail"], pk=instance.pk)

        context = base_context()
        context.update({"form": form, "object": instance, "form_title": f"Edit {model_name}", "submit_label": "Save"})
        return render(request, f"webroaster/{template_dir}/form.html", context)

    def delete_view(request, pk):
        instance = get_object_or_404(model, pk=pk)
        if request.method == "POST":
            instance.delete()
            messages.success(request, f"{model_name} deleted successfully.")
            return redirect(route_names["list"])

        context = base_context()
        context["object"] = instance
        return render(request, f"webroaster/{template_dir}/confirm_delete.html", context)

    return list_view, create_view, detail_view, update_view, delete_view

