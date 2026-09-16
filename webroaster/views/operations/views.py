from webroaster.models import Asset, Client, Deployment, Incident, PatrolLog, Shift, Site
from webroaster.views.common import build_crud_views


client_list_create, client_detail = build_crud_views(Client)
site_list_create, site_detail = build_crud_views(Site)
shift_list_create, shift_detail = build_crud_views(Shift)
deployment_list_create, deployment_detail = build_crud_views(Deployment)
incident_list_create, incident_detail = build_crud_views(Incident)
patrol_log_list_create, patrol_log_detail = build_crud_views(PatrolLog)
asset_list_create, asset_detail = build_crud_views(Asset)

