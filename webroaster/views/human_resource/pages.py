from webroaster.forms import (
    AttendanceForm,
    DisciplinaryActionForm,
    DocumentForm,
    EmployeeForm,
    GuardForm,
    LeaveForm,
    PerformanceEvaluationForm,
    SupervisorForm,
    TrainingForm,
)
from webroaster.models import (
    Attendance,
    DisciplinaryAction,
    Document,
    Employee,
    Guard,
    Leave,
    PerformanceEvaluation,
    Supervisor,
    Training,
)
from webroaster.views.pages import build_page_views


employee_page_list, employee_page_create, employee_page_detail, employee_page_update, employee_page_delete = build_page_views(
    Employee,
    EmployeeForm,
    department_name="Human Resource",
    template_dir="human_resource",
    route_base="hr-employee",
    list_fields=("first_name", "last_name", "role", "department", "current_deployment_area", "status"),
)
guard_page_list, guard_page_create, guard_page_detail, guard_page_update, guard_page_delete = build_page_views(
    Guard, GuardForm, department_name="Human Resource", template_dir="human_resource", route_base="hr-guard", list_fields=("employee", "badge_number", "armed_status", "training_level")
)
supervisor_page_list, supervisor_page_create, supervisor_page_detail, supervisor_page_update, supervisor_page_delete = build_page_views(
    Supervisor, SupervisorForm, department_name="Human Resource", template_dir="human_resource", route_base="hr-supervisor", list_fields=("employee", "assigned_zone", "experience_years", "authority_level")
)
training_page_list, training_page_create, training_page_detail, training_page_update, training_page_delete = build_page_views(
    Training, TrainingForm, department_name="Human Resource", template_dir="human_resource", route_base="hr-training", list_fields=("employee", "training_name", "provider", "status")
)
attendance_page_list, attendance_page_create, attendance_page_detail, attendance_page_update, attendance_page_delete = build_page_views(
    Attendance, AttendanceForm, department_name="Human Resource", template_dir="human_resource", route_base="hr-attendance", list_fields=("employee", "date", "time_in", "status")
)
leave_page_list, leave_page_create, leave_page_detail, leave_page_update, leave_page_delete = build_page_views(
    Leave, LeaveForm, department_name="Human Resource", template_dir="human_resource", route_base="hr-leave", list_fields=("employee", "leave_type", "start_date", "approval_status")
)
disciplinary_action_page_list, disciplinary_action_page_create, disciplinary_action_page_detail, disciplinary_action_page_update, disciplinary_action_page_delete = build_page_views(
    DisciplinaryAction, DisciplinaryActionForm, department_name="Human Resource", template_dir="human_resource", route_base="hr-disciplinary-action", list_fields=("employee", "action_type", "action_date", "status")
)
performance_evaluation_page_list, performance_evaluation_page_create, performance_evaluation_page_detail, performance_evaluation_page_update, performance_evaluation_page_delete = build_page_views(
    PerformanceEvaluation, PerformanceEvaluationForm, department_name="Human Resource", template_dir="human_resource", route_base="hr-performance-evaluation", list_fields=("employee", "eval_date", "rating", "evaluated_by")
)
document_page_list, document_page_create, document_page_detail, document_page_update, document_page_delete = build_page_views(
    Document, DocumentForm, department_name="Human Resource", template_dir="human_resource", route_base="hr-document", list_fields=("employee", "doc_type", "issue_date", "expiry_date")
)

