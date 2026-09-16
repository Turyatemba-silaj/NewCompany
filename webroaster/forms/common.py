from django import forms


class BaseModelForm(forms.ModelForm):
    date_fields = {"DateField", "DateTimeField", "TimeField"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css_class = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                css_class = "form-select"
            if isinstance(field.widget, forms.ClearableFileInput):
                css_class = "form-control"

            existing_classes = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing_classes} {css_class}".strip()

            model_field = self._meta.model._meta.get_field(name)
            if model_field.get_internal_type() == "DateField":
                field.widget.input_type = "date"
            elif model_field.get_internal_type() == "DateTimeField":
                field.widget.input_type = "datetime-local"
            elif model_field.get_internal_type() == "TimeField":
                field.widget.input_type = "time"

