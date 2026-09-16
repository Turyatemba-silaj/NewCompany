from webroaster.forms import AssetForm, ClientForm, DeploymentForm, IncidentForm, PatrolLogForm, ShiftForm, SiteForm
from webroaster.models import Asset, Client, Deployment, Incident, PatrolLog, Shift, Site
from webroaster.views.pages import build_page_views


client_page_list, client_page_create, client_page_detail, client_page_update, client_page_delete = build_page_views(
    Client,
    ClientForm,
    department_name="Operations",
    template_dir="operations",
    route_base="operations-client",
    list_fields=("client_name", "contact_person", "phone_number", "contract_status"),
)
site_page_list, site_page_create, site_page_detail, site_page_update, site_page_delete = build_page_views(
    Site,
    SiteForm,
    department_name="Operations",
    template_dir="operations",
    route_base="operations-site",
    list_fields=("site_name", "client", "city", "security_level"),
)
shift_page_list, shift_page_create, shift_page_detail, shift_page_update, shift_page_delete = build_page_views(
    Shift,
    ShiftForm,
    department_name="Operations",
    template_dir="operations",
    route_base="operations-shift",
    list_fields=("shift_name", "start_time", "end_time", "shift_type"),
)
deployment_page_list, deployment_page_create, deployment_page_detail, deployment_page_update, deployment_page_delete = build_page_views(
    Deployment,
    DeploymentForm,
    department_name="Operations",
    template_dir="operations",
    route_base="operations-deployment",
    list_fields=("guard", "client", "site", "shift", "status"),
)
incident_page_list, incident_page_create, incident_page_detail, incident_page_update, incident_page_delete = build_page_views(
    Incident,
    IncidentForm,
    department_name="Operations",
    template_dir="operations",
    route_base="operations-incident",
    list_fields=("incident_type", "guard", "incident_date", "severity_level"),
)
patrol_log_page_list, patrol_log_page_create, patrol_log_page_detail, patrol_log_page_update, patrol_log_page_delete = build_page_views(
    PatrolLog,
    PatrolLogForm,
    department_name="Operations",
    template_dir="operations",
    route_base="operations-patrol-log",
    list_fields=("guard", "site", "patrol_time", "patrol_route"),
)
asset_page_list, asset_page_create, asset_page_detail, asset_page_update, asset_page_delete = build_page_views(
    Asset,
    AssetForm,
    department_name="Operations",
    template_dir="operations",
    route_base="operations-asset",
    list_fields=("asset_name", "asset_type", "serial_number", "condition"),
)

