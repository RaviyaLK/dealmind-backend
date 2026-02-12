from typing import TypedDict, List, Dict, Any, Optional, Annotated
from langgraph.graph import add_messages


class QualificationState(TypedDict):
    """State for the deal qualification flow."""
    deal_id: str
    task_id: str
    # Document data
    document_text: str
    document_metadata: Dict[str, Any]
    # Extraction results
    extracted_requirements: List[Dict[str, Any]]
    extracted_entities: Dict[str, Any]  # client name, dates, budget, etc.
    # Company capabilities (real employee data + company profile)
    employee_capabilities: List[Dict[str, Any]]
    company_profile: Dict[str, Any]
    # Analysis results
    skill_matches: List[Dict[str, Any]]
    gap_analysis: Dict[str, Any]
    # Decision
    recommendation: str  # go / no_go / conditional_go
    confidence_score: float
    positive_factors: List[str]
    risk_factors: List[str]
    conditions: List[str]
    reasoning: str
    # Flow control
    current_step: str
    messages: Annotated[list, add_messages]
    errors: List[str]


class ProposalState(TypedDict):
    """State for the proposal generation flow."""
    deal_id: str
    task_id: str
    # Input context
    deal_context: Dict[str, Any]
    requirements: List[Dict[str, Any]]
    team_assignments: List[Dict[str, Any]]  # assigned employees with skills/rates
    # Company profile (ESSHVA capabilities, services, tech stack, awards)
    company_profile: Dict[str, Any]
    # RAG context
    retrieved_sections: List[Dict[str, Any]]
    # Generation
    proposal_draft: str
    proposal_sections: List[Dict[str, Any]]
    # Compliance
    compliance_score: float
    compliance_issues: List[Dict[str, Any]]
    # Output
    final_proposal: str
    proposal_id: str
    # Flow control
    current_step: str
    messages: Annotated[list, add_messages]
    errors: List[str]


class MonitoringState(TypedDict):
    """State for the deal monitoring flow."""
    deal_id: str
    task_id: str
    # Input
    deal_data: Dict[str, Any]
    recent_communications: List[Dict[str, Any]]
    # Analysis
    sentiment_scores: List[Dict[str, Any]]
    overall_sentiment: float
    health_score: int
    trend: str  # up / down / stable
    # Alerts
    detected_alerts: List[Dict[str, Any]]
    # Recovery
    recovery_email: str
    recovery_actions: List[str]
    # Flow control
    current_step: str
    messages: Annotated[list, add_messages]
    errors: List[str]
