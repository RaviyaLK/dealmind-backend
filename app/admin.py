"""
SQLAdmin Configuration
======================
Web UI for browsing and managing database tables.
Access at: http://localhost:8000/admin
"""

from sqladmin import Admin, ModelView
from app.models.user import User
from app.models.deal import Deal, DealRequirement, DealAnalysis
from app.models.employee import Employee
from app.models.document import Document, DocumentChunk
from app.models.alert import Alert, RecoveryAction
from app.models.proposal import Proposal


# ── Model Views ──────────────────────────────────────────

class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.email, User.full_name, User.role, User.created_at]
    column_searchable_list = [User.email, User.full_name]
    column_sortable_list = [User.id, User.email, User.created_at]
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"


class DealAdmin(ModelView, model=Deal):
    column_list = [Deal.id, Deal.title, Deal.client_name, Deal.deal_value, Deal.stage, Deal.health_score, Deal.status, Deal.created_at]
    column_searchable_list = [Deal.title, Deal.client_name]
    column_sortable_list = [Deal.id, Deal.title, Deal.deal_value, Deal.health_score, Deal.created_at]
    name = "Deal"
    name_plural = "Deals"
    icon = "fa-solid fa-handshake"


class DealRequirementAdmin(ModelView, model=DealRequirement):
    column_list = [DealRequirement.id, DealRequirement.deal_id, DealRequirement.category, DealRequirement.confidence, DealRequirement.is_met]
    column_sortable_list = [DealRequirement.id, DealRequirement.confidence]
    name = "Deal Requirement"
    name_plural = "Deal Requirements"
    icon = "fa-solid fa-list-check"


class DealAnalysisAdmin(ModelView, model=DealAnalysis):
    column_list = [DealAnalysis.id, DealAnalysis.deal_id, DealAnalysis.analysis_type, DealAnalysis.confidence_score, DealAnalysis.created_at]
    column_sortable_list = [DealAnalysis.id, DealAnalysis.confidence_score, DealAnalysis.created_at]
    name = "Deal Analysis"
    name_plural = "Deal Analyses"
    icon = "fa-solid fa-chart-line"


class EmployeeAdmin(ModelView, model=Employee):
    column_list = [Employee.id, Employee.name, Employee.role, Employee.department, Employee.availability_percent]
    column_searchable_list = [Employee.name, Employee.role, Employee.department]
    column_sortable_list = [Employee.id, Employee.name, Employee.department]
    name = "Employee"
    name_plural = "Employees"
    icon = "fa-solid fa-users"


class DocumentAdmin(ModelView, model=Document):
    column_list = [Document.id, Document.filename, Document.file_type, Document.deal_id, Document.is_processed, Document.created_at]
    column_searchable_list = [Document.filename]
    column_sortable_list = [Document.id, Document.filename, Document.created_at]
    name = "Document"
    name_plural = "Documents"
    icon = "fa-solid fa-file"


class DocumentChunkAdmin(ModelView, model=DocumentChunk):
    column_list = [DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.chunk_index, DocumentChunk.embedding_id]
    column_sortable_list = [DocumentChunk.id, DocumentChunk.chunk_index]
    name = "Document Chunk"
    name_plural = "Document Chunks"
    icon = "fa-solid fa-puzzle-piece"


class AlertAdmin(ModelView, model=Alert):
    column_list = [Alert.id, Alert.deal_id, Alert.alert_type, Alert.severity, Alert.title, Alert.is_resolved, Alert.created_at]
    column_searchable_list = [Alert.title]
    column_sortable_list = [Alert.id, Alert.severity, Alert.created_at]
    name = "Alert"
    name_plural = "Alerts"
    icon = "fa-solid fa-bell"


class RecoveryActionAdmin(ModelView, model=RecoveryAction):
    column_list = [RecoveryAction.id, RecoveryAction.alert_id, RecoveryAction.action_text, RecoveryAction.priority, RecoveryAction.is_completed]
    column_sortable_list = [RecoveryAction.id, RecoveryAction.priority]
    name = "Recovery Action"
    name_plural = "Recovery Actions"
    icon = "fa-solid fa-wrench"


class ProposalAdmin(ModelView, model=Proposal):
    column_list = [Proposal.id, Proposal.deal_id, Proposal.title, Proposal.status, Proposal.version, Proposal.created_at]
    column_searchable_list = [Proposal.title]
    column_sortable_list = [Proposal.id, Proposal.title, Proposal.created_at]
    name = "Proposal"
    name_plural = "Proposals"
    icon = "fa-solid fa-file-contract"


def setup_admin(app, engine):
    """Mount SQLAdmin on the FastAPI app."""
    admin = Admin(app, engine, title="DealMind Admin", base_url="/admin")

    admin.add_view(UserAdmin)
    admin.add_view(DealAdmin)
    admin.add_view(DealRequirementAdmin)
    admin.add_view(DealAnalysisAdmin)
    admin.add_view(EmployeeAdmin)
    admin.add_view(DocumentAdmin)
    admin.add_view(DocumentChunkAdmin)
    admin.add_view(AlertAdmin)
    admin.add_view(RecoveryActionAdmin)
    admin.add_view(ProposalAdmin)

    return admin
