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
from webroaster.views.common import build_crud_views


employee_list_create, employee_detail = build_crud_views(Employee)
guard_list_create, guard_detail = build_crud_views(Guard)
supervisor_list_create, supervisor_detail = build_crud_views(Supervisor)
training_list_create, training_detail = build_crud_views(Training)
attendance_list_create, attendance_detail = build_crud_views(Attendance)
leave_list_create, leave_detail = build_crud_views(Leave)
disciplinary_action_list_create, disciplinary_action_detail = build_crud_views(DisciplinaryAction)
performance_evaluation_list_create, performance_evaluation_detail = build_crud_views(PerformanceEvaluation)
document_list_create, document_detail = build_crud_views(Document)

