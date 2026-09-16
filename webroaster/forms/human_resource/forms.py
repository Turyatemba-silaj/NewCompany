from webroaster.forms.common import BaseModelForm
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


class EmployeeForm(BaseModelForm):
    class Meta:
        model = Employee
        fields = "__all__"


class GuardForm(BaseModelForm):
    class Meta:
        model = Guard
        fields = "__all__"


class SupervisorForm(BaseModelForm):
    class Meta:
        model = Supervisor
        fields = "__all__"


class TrainingForm(BaseModelForm):
    class Meta:
        model = Training
        fields = "__all__"


class AttendanceForm(BaseModelForm):
    class Meta:
        model = Attendance
        fields = "__all__"


class LeaveForm(BaseModelForm):
    class Meta:
        model = Leave
        fields = "__all__"


class DisciplinaryActionForm(BaseModelForm):
    class Meta:
        model = DisciplinaryAction
        fields = "__all__"


class PerformanceEvaluationForm(BaseModelForm):
    class Meta:
        model = PerformanceEvaluation
        fields = "__all__"


class DocumentForm(BaseModelForm):
    class Meta:
        model = Document
        fields = "__all__"

