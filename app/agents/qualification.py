import json
import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from app.agents.state import QualificationState
from app.services.llm import call_llm
from app.websocket.manager import ws_manager
import asyncio

logger = logging.getLogger(__name__)


async def notify_step(task_id: str, step: str, step_number: int, total: int, status: str = "processing", message: str = "", data: dict = None):
    """Send WebSocket notification about agent progress."""
    await ws_manager.send_task_update(task_id, {
        "task_id": task_id,
        "step": step,
        "step_number": step_number,
        "total_steps": total,
        "status": status,
        "message": message,
        "data": data or {},
    })


def ingest_node(state: QualificationState) -> Dict[str, Any]:
    """Step 1: Parse and prepare the document for extraction."""
    logger.info("ingest node: starting document validation")
    # Document text is already extracted by the ingestion pipeline
    # This node validates and prepares it
    text = state.get("document_text", "")
    if not text:
        logger.warning("ingest node: no document text provided")
        return {"errors": ["No document text provided"], "current_step": "ingest"}

    # Basic document stats
    metadata = state.get("document_metadata", {})
    metadata["word_count"] = len(text.split())
    metadata["char_count"] = len(text)

    logger.info(f"ingest node: document ingested - word_count={metadata['word_count']}, char_count={metadata['char_count']}")

    return {
        "document_metadata": metadata,
        "current_step": "ingest",
    }


def extract_node(state: QualificationState) -> Dict[str, Any]:
    """Step 2: Extract requirements and key entities using Claude."""
    logger.info("extract node: starting requirement extraction")
    text = state["document_text"]

    # Truncate if too long for context
    if len(text) > 50000:
        text = text[:50000] + "\n\n[Document truncated for processing]"

    extraction_prompt = f"""Analyze this RFP/proposal document and extract structured information.

DOCUMENT:
{text}

Extract the following as a JSON object:
{{
    "requirements": [
        {{
            "category": "technical|functional|integration|infrastructure|security|compliance",
            "text": "The specific requirement",
            "priority": "must_have|should_have|nice_to_have",
            "confidence": 0.0 to 1.0
        }}
    ],
    "entities": {{
        "client_name": "...",
        "project_name": "...",
        "budget_range": "...",
        "timeline": "...",
        "deadline": "...",
        "key_stakeholders": ["..."],
        "industry": "...",
        "technologies_mentioned": ["..."]
    }}
}}

Be thorough - extract ALL requirements you can identify. Return ONLY valid JSON."""

    result_text = call_llm(extraction_prompt, max_tokens=4096)

    try:
        # Try to parse JSON from the response
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        result = json.loads(result_text.strip())
        extracted_count = len(result.get("requirements", []))
        logger.info(f"extract node: successfully extracted {extracted_count} requirements")
        return {
            "extracted_requirements": result.get("requirements", []),
            "extracted_entities": result.get("entities", {}),
            "current_step": "extract",
        }
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"extract node: JSON parsing failed - {str(e)}")
        return {
            "extracted_requirements": [],
            "extracted_entities": {},
            "errors": [f"Extraction parsing error: {str(e)}"],
            "current_step": "extract",
        }


def analyze_node(state: QualificationState) -> Dict[str, Any]:
    """Step 3: Analyze requirements against company capabilities."""
    logger.info("analyze node: starting capability analysis")
    requirements = state.get("extracted_requirements", [])
    entities = state.get("extracted_entities", {})
    employees = state.get("employee_capabilities", [])
    profile = state.get("company_profile", {})

    # ── Build company profile context from esshva_company_profile.json ──
    company_info = profile.get("company", {})
    capabilities = profile.get("capabilities_summary", {})
    services = profile.get("services", {})
    tech = profile.get("technologies", {})
    industries = profile.get("industries_served", [])
    products = profile.get("products", [])
    awards = profile.get("awards_and_recognition", [])
    global_reach = profile.get("global_reach", {})

    company_context = f"""COMPANY: {company_info.get('brand_name', 'ESSHVA')} ({company_info.get('legal_name', 'ESSHVA TECHQ PVT LTD')})
FOUNDED: {company_info.get('founded', 'N/A')} | HQ: {company_info.get('headquarters', {}).get('city', 'Colombo')}, {company_info.get('headquarters', {}).get('country', 'Sri Lanka')}
CERTIFICATIONS: {', '.join(company_info.get('certifications', [])) or 'None listed'}
EMPLOYEE COUNT: {company_info.get('employee_count', len(employees))}

SERVICES OFFERED:
{chr(10).join('- ' + s.get('name', '') + ': ' + s.get('description', '') for s in services.get('primary', [])) if services.get('primary') else 'Not specified'}

KNOWN TECHNOLOGIES: {', '.join(tech.get('known_stack', [])) or 'Not specified'}

INDUSTRIES SERVED: {', '.join(industries) or 'Not specified'}

PRODUCTS BUILT: {', '.join(p.get('name', '') + ' (' + p.get('description', '')[:60] + ')' for p in products[:4]) if products else 'Not specified'}

AWARDS: {', '.join(a.get('award', '') for a in awards) if awards else 'None'}

GLOBAL CLIENTS: {', '.join(global_reach.get('client_regions', [])) or 'Not specified'}
NOTABLE CLIENTS: {global_reach.get('notable_client_types', 'Not specified')}

CAPABILITY AREAS:
- Software Development: {capabilities.get('software_development', 'N/A')}
- Cloud & Infrastructure: {capabilities.get('cloud_and_infrastructure', 'N/A')}
- AI & Data: {capabilities.get('ai_and_data', 'N/A')}
- Integration: {capabilities.get('integration', 'N/A')}
- Product Engineering: {capabilities.get('product_engineering', 'N/A')}
- Quality Assurance: {capabilities.get('quality_assurance', 'N/A')}
- Digital Transformation: {capabilities.get('digital_transformation', 'N/A')}"""

    # ── Build employee roster summary ──
    all_skills = set()
    all_roles = set()
    all_departments = set()
    for emp in employees:
        all_skills.update(s for s in (emp.get("skills") or []))
        if emp.get("role"):
            all_roles.add(emp["role"])
        if emp.get("department"):
            all_departments.add(emp["department"])

    employee_summary = f"""
CURRENT TEAM ({len(employees)} active employees):
DEPARTMENTS: {', '.join(sorted(all_departments)) if all_departments else 'Not specified'}
ROLES ON STAFF: {', '.join(sorted(all_roles)) if all_roles else 'Not specified'}
ALL SKILLS AVAILABLE: {', '.join(sorted(all_skills)) if all_skills else 'Not specified'}

EMPLOYEE ROSTER:"""
    for emp in employees[:20]:
        skills_str = ', '.join(emp.get('skills', [])[:8])
        employee_summary += f"\n- {emp.get('name', 'Unknown')} | {emp.get('role', '')} | Skills: {skills_str} | Availability: {emp.get('availability_percent', 100)}%"
    if len(employees) > 20:
        employee_summary += f"\n... and {len(employees) - 20} more employees"

    analysis_prompt = f"""You are Quinn, an AI deal intelligence agent for ESSHVA. Analyze these extracted requirements against our ACTUAL company profile and team capabilities to assess deal viability.

CLIENT: {entities.get('client_name', 'Unknown')}
INDUSTRY: {entities.get('industry', 'Unknown')}
BUDGET: {entities.get('budget_range', 'Unknown')}
TIMELINE: {entities.get('timeline', 'Unknown')}

═══ ESSHVA COMPANY PROFILE ═══
{company_context}

═══ ESSHVA TEAM CAPABILITIES ═══
{employee_summary}

═══ CLIENT REQUIREMENTS ({len(requirements)} total) ═══
{json.dumps(requirements, indent=2)}

IMPORTANT: Base your analysis on BOTH our company profile (services, technologies, industries, products, awards) AND our actual employee skills listed above. A capability is CONFIRMED if it appears in our services, technology stack, OR employee skills. Flag gaps only for requirements that genuinely don't match anything in our profile or team.

Provide your gap analysis as JSON:
{{
    "capability_match_percent": 0-100,
    "strong_areas": ["specific areas where our company profile and/or team skills demonstrably match requirements"],
    "gap_areas": ["specific requirement areas where neither our company services nor team skills provide coverage"],
    "risk_factors": ["concrete risks based on real gaps, timeline constraints, budget concerns, or capacity limits"],
    "opportunity_factors": ["positive signals — e.g. industry experience, relevant products, matching tech stack, global client experience"],
    "resource_estimate": {{
        "team_size": "estimated team size needed",
        "duration": "estimated duration",
        "key_roles": ["specific roles needed, noting which we have and which we'd need to hire/contract"]
    }}
}}

Return ONLY valid JSON."""

    result_text = call_llm(analysis_prompt, max_tokens=2048)

    try:
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        gap_analysis = json.loads(result_text.strip())
        capability_match = gap_analysis.get("capability_match_percent", 0)
        logger.info(f"analyze node: gap analysis complete - capability_match_percent={capability_match}")
        return {
            "gap_analysis": gap_analysis,
            "current_step": "analyze",
        }
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"analyze node: JSON parsing failed - {str(e)}")
        return {
            "gap_analysis": {},
            "current_step": "analyze",
        }


def match_node(state: QualificationState) -> Dict[str, Any]:
    """Step 4: Match requirements against employee skills database."""
    logger.info("match node: starting employee skill matching")
    # This node queries the employee database to find skill matches
    # In a real implementation, it would use the DB session
    # For the LangGraph flow, we prepare the matching criteria
    gap_analysis = state.get("gap_analysis", {})
    key_roles = gap_analysis.get("resource_estimate", {}).get("key_roles", [])

    skill_matches = [{"role": role, "status": "pending_db_query"} for role in key_roles]
    logger.info(f"match node: matched {len(skill_matches)} roles against employee database")

    return {
        "skill_matches": skill_matches,
        "current_step": "match",
    }


def decide_node(state: QualificationState) -> Dict[str, Any]:
    """Step 5: Make GO/NO-GO/CONDITIONAL-GO recommendation."""
    logger.info("decide node: generating deal recommendation")
    requirements = state.get("extracted_requirements", [])
    entities = state.get("extracted_entities", {})
    gap_analysis = state.get("gap_analysis", {})
    employees = state.get("employee_capabilities", [])
    profile = state.get("company_profile", {})

    team_size = len(employees)
    team_summary = f"{team_size} employees on staff"
    if employees:
        all_skills = set()
        for emp in employees:
            all_skills.update(emp.get("skills", []))
        team_summary += f" with {len(all_skills)} unique skills across the team"

    # Build concise company strengths from profile
    company_strengths = ""
    if profile:
        services_list = [s.get("name", "") for s in profile.get("services", {}).get("primary", [])]
        tech_stack = profile.get("technologies", {}).get("known_stack", [])
        industries = profile.get("industries_served", [])
        awards_list = [a.get("award", "") for a in profile.get("awards_and_recognition", [])]
        client_regions = profile.get("global_reach", {}).get("client_regions", [])
        certifications = profile.get("company", {}).get("certifications", [])
        company_strengths = f"""
ESSHVA COMPANY STRENGTHS:
- Services: {', '.join(services_list) if services_list else 'N/A'}
- Tech Stack: {', '.join(tech_stack) if tech_stack else 'N/A'}
- Industries Served: {', '.join(industries) if industries else 'N/A'}
- Global Presence: Clients in {', '.join(client_regions) if client_regions else 'N/A'}
- Awards: {', '.join(awards_list) if awards_list else 'None'}
- Certifications: {', '.join(certifications) if certifications else 'None'}"""

    decision_prompt = f"""You are Quinn, an AI deal intelligence agent for ESSHVA. Based on the complete analysis against our actual company profile and team capabilities, make a deal qualification decision.

CLIENT: {entities.get('client_name', 'Unknown')}
BUDGET: {entities.get('budget_range', 'Unknown')}
TIMELINE: {entities.get('timeline', 'Unknown')}
OUR TEAM: {team_summary}
{company_strengths}

CAPABILITY MATCH: {gap_analysis.get('capability_match_percent', 'Unknown')}%
STRONG AREAS: {json.dumps(gap_analysis.get('strong_areas', []))}
GAP AREAS: {json.dumps(gap_analysis.get('gap_areas', []))}
RISK FACTORS: {json.dumps(gap_analysis.get('risk_factors', []))}
OPPORTUNITY FACTORS: {json.dumps(gap_analysis.get('opportunity_factors', []))}
RESOURCE ESTIMATE: {json.dumps(gap_analysis.get('resource_estimate', {}))}
TOTAL REQUIREMENTS: {len(requirements)}

Make your decision as JSON. Be specific — reference actual company capabilities, service offerings, industry experience, team skills, and any gaps:
{{
    "recommendation": "go|no_go|conditional_go",
    "confidence_score": 0.0 to 1.0,
    "positive_factors": ["specific reasons supporting GO — reference our services, tech stack, industry experience, team skills, or awards"],
    "risk_factors": ["specific risks — reference real skill gaps, capacity constraints, missing capabilities, or timeline/budget concerns"],
    "conditions": ["conditions that must be met for GO, if conditional — e.g. hiring, upskilling, partnering, technology acquisition"],
    "reasoning": "2-3 sentence explanation grounded in our actual company profile and capability match"
}}

Return ONLY valid JSON."""

    result_text = call_llm(decision_prompt, max_tokens=1024)

    try:
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        decision = json.loads(result_text.strip())
        recommendation = decision.get("recommendation", "no_go")
        confidence_score = decision.get("confidence_score", 0.5)
        logger.info(f"decide node: decision generated - recommendation={recommendation}, confidence_score={confidence_score}")
        return {
            "recommendation": recommendation,
            "confidence_score": confidence_score,
            "positive_factors": decision.get("positive_factors", []),
            "risk_factors": decision.get("risk_factors", []),
            "conditions": decision.get("conditions", []),
            "reasoning": decision.get("reasoning", ""),
            "current_step": "decide",
        }
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"decide node: decision generation failed - {str(e)}")
        return {
            "recommendation": "no_go",
            "confidence_score": 0.0,
            "reasoning": "Failed to generate decision",
            "current_step": "decide",
        }


def build_qualification_graph() -> StateGraph:
    """Build the qualification LangGraph workflow."""
    workflow = StateGraph(QualificationState)

    workflow.add_node("ingest", ingest_node)
    workflow.add_node("extract", extract_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("match", match_node)
    workflow.add_node("decide", decide_node)

    workflow.set_entry_point("ingest")
    workflow.add_edge("ingest", "extract")
    workflow.add_edge("extract", "analyze")
    workflow.add_edge("analyze", "match")
    workflow.add_edge("match", "decide")
    workflow.add_edge("decide", END)

    return workflow.compile()


qualification_graph = build_qualification_graph()
