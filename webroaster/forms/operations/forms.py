from webroaster.forms.common import BaseModelForm
from webroaster.models import Asset, Client, Deployment, Incident, PatrolLog, Shift, Site


class ClientForm(BaseModelForm):
    class Meta:
        model = Client
        fields = "__all__"


class SiteForm(BaseModelForm):
    class Meta:
        model = Site
        fields = "__all__"


class ShiftForm(BaseModelForm):
    class Meta:
        model = Shift
        fields = "__all__"


class DeploymentForm(BaseModelForm):
    class Meta:
        model = Deployment
        fields = "__all__"


class IncidentForm(BaseModelForm):
    class Meta:
        model = Incident
        fields = "__all__"


class PatrolLogForm(BaseModelForm):
    class Meta:
        model = PatrolLog
        fields = "__all__"


class AssetForm(BaseModelForm):
    class Meta:
        model = Asset
        fields = "__all__"

