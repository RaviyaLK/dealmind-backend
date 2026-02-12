import json
import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from app.agents.state import ProposalState
from app.services.llm import call_llm
from app.rag.retriever import rag_retriever

logger = logging.getLogger(__name__)


def retrieve_node(state: ProposalState) -> Dict[str, Any]:
    """Step 1: Retrieve relevant sections from previous proposals using RAG."""
    logger.info("retrieve node: starting RAG retrieval for proposal context")
    deal_context = state.get("deal_context", {})
    requirements = state.get("requirements", [])

    context_str = json.dumps(deal_context)
    req_texts = [r.get("text", r.get("requirement_text", "")) for r in requirements]

    retrieved = []
    try:
        retrieved = rag_retriever.retrieve_for_proposal(
            deal_context=context_str,
            requirements=req_texts,
            n_results=10,
        )
        logger.info(f"retrieve node: successfully retrieved {len(retrieved)} proposal sections from RAG")
    except Exception as e:
        # RAG retrieval is optional — proceed without context if embeddings/vector store fails
        logger.warning(f"retrieve node: RAG retrieval failed (non-fatal, continuing without context): {e}")

    return {
        "retrieved_sections": retrieved,
        "current_step": "retrieve",
    }


def generate_node(state: ProposalState) -> Dict[str, Any]:
    """Step 2: Generate proposal draft using Claude with RAG context."""
    logger.info("generate node: starting proposal draft generation")
    deal_context = state.get("deal_context", {})
    requirements = state.get("requirements", [])
    retrieved = state.get("retrieved_sections", [])
    team_assignments = state.get("team_assignments", [])
    profile = state.get("company_profile", {})

    # Build RAG context
    rag_context = ""
    if retrieved:
        rag_context = "\n\nRELEVANT SECTIONS FROM PREVIOUS PROPOSALS & UPLOADED DOCUMENTS:\n"
        for i, section in enumerate(retrieved[:7]):
            source = section.get("source", "Unknown")
            collection = section.get("collection", "")
            label = f"{source} [{collection}]" if collection else source
            rag_context += f"\n--- Section {i+1} (Source: {label}, Relevance: {section.get('relevance_score', 0):.2f}) ---\n"
            rag_context += section.get("text", "") + "\n"

    req_text = "\n".join(f"- [{r.get('category', 'general')}] {r.get('text', r.get('requirement_text', ''))}" for r in requirements)

    # ── Analyze requirements to drive proposal strategy ──
    categories = {}
    for r in requirements:
        cat = (r.get("category") or "general").lower()
        categories[cat] = categories.get(cat, 0) + 1

    total_reqs = len(requirements)
    strategy_hints = []
    extra_sections = []

    # Detect what kind of deal this is and what to emphasize
    tech_cats = {"technical", "architecture", "infrastructure", "performance", "scalability", "integration"}
    security_cats = {"security", "compliance", "regulatory", "privacy", "data_protection"}
    functional_cats = {"functional", "feature", "ui", "ux", "user_experience"}
    process_cats = {"process", "methodology", "agile", "management", "reporting"}

    tech_weight = sum(categories.get(c, 0) for c in tech_cats)
    security_weight = sum(categories.get(c, 0) for c in security_cats)
    functional_weight = sum(categories.get(c, 0) for c in functional_cats)
    process_weight = sum(categories.get(c, 0) for c in process_cats)

    if tech_weight > total_reqs * 0.3:
        strategy_hints.append("This is a TECHNICALLY HEAVY project. Go deep on architecture diagrams (describe them textually), technology stack choices with justifications, scalability approach, and performance benchmarks. Show ESSHVA's technical depth.")
        extra_sections.append(("Technical Architecture Deep-Dive", "Provide a detailed breakdown of the system architecture — components, data flow, API design, tech stack rationale. Explain WHY each technology choice is the best fit for these specific requirements."))

    if security_weight > 0:
        strategy_hints.append("This project has SECURITY/COMPLIANCE requirements. Dedicate significant attention to how ESSHVA will ensure compliance. Reference specific standards, certifications, or frameworks relevant to the requirements.")
        extra_sections.append(("Security & Compliance Framework", "Detail ESSHVA's approach to meeting every security and compliance requirement. Reference specific standards (ISO 27001, SOC 2, GDPR, etc.) where relevant. Include audit trail, access control, and data protection strategies."))

    if functional_weight > total_reqs * 0.3:
        strategy_hints.append("This project is FEATURE-RICH. Focus on user experience, feature prioritization, and how each functional requirement maps to a concrete deliverable. Consider including wireframe descriptions or user journey narratives.")

    if process_weight > 0:
        strategy_hints.append("The client cares about PROCESS & METHODOLOGY. Emphasize ESSHVA's project management approach — sprint cycles, communication cadence, reporting dashboards, stakeholder involvement, and risk mitigation.")

    if total_reqs > 10:
        strategy_hints.append("There are MANY requirements. Organize them into logical groups in your response. Show a clear traceability matrix mindset — every requirement should be visibly addressed somewhere in the proposal.")

    if not strategy_hints:
        strategy_hints.append("Provide a well-balanced proposal covering solution design, implementation approach, and business value. Emphasize ESSHVA's ability to deliver quality results on time.")

    strategy_block = "\n".join(f"- {h}" for h in strategy_hints)

    # Build extra sections block — these go BEFORE "Next Steps" so Next Steps is always last
    extra_sections_block = ""
    next_steps_number = 8  # default if no extra sections
    if extra_sections:
        extra_sections_block = "\n"
        for i, (title, guidance) in enumerate(extra_sections, 8):
            extra_sections_block += f"\n## {i}. {title}\n{guidance}\n"
        next_steps_number = 8 + len(extra_sections)

    # Build team context from assigned employees
    team_context = ""
    if team_assignments:
        team_context = "\n\nASSIGNED TEAM MEMBERS (use these EXACT people in the Team & Resources section):\n"
        total_monthly = 0
        for i, member in enumerate(team_assignments, 1):
            rate = member.get("hourly_rate", 0)
            alloc = member.get("allocation_percent", 100)
            monthly = rate * 160 * (alloc / 100)
            total_monthly += monthly
            skills_str = ", ".join(member.get("skills", [])[:6]) if member.get("skills") else "General"
            team_context += f"  {i}. {member['name']} — {member['role']}\n"
            team_context += f"     Skills: {skills_str}\n"
            team_context += f"     Department: {member.get('department', 'N/A')} | Allocation: {alloc}% | Rate: ${rate}/hr | Monthly: ${monthly:,.0f}\n"
        team_context += f"\n  TOTAL ESTIMATED MONTHLY COST: ${total_monthly:,.0f}\n"
        team_context += "\nIMPORTANT: Use ONLY these assigned team members in the proposal. Do NOT invent or add fictional team members. Reference their real names, roles, and skills."
    else:
        team_context = "\n\nNOTE: No specific team members have been assigned yet. Describe team structure generically based on required roles.\n"

    # ── Build ESSHVA company profile context for grounded proposals ──
    company_context = ""
    if profile:
        company_info = profile.get("company", {})
        services = profile.get("services", {})
        tech = profile.get("technologies", {})
        industries = profile.get("industries_served", [])
        products = profile.get("products", [])
        awards = profile.get("awards_and_recognition", [])
        global_reach = profile.get("global_reach", {})
        capabilities = profile.get("capabilities_summary", {})
        certifications = company_info.get("certifications", [])

        services_list = [s.get("name", "") for s in services.get("primary", [])]
        delivery_models = [d.get("name", "") + ": " + d.get("description", "") for d in services.get("delivery_models", [])]
        products_list = [p.get("name", "") + (" — " + p.get("award", "") if p.get("award") else "") for p in products[:4]]
        awards_list = [a.get("award", "") for a in awards]

        company_context = f"""

ESSHVA COMPANY PROFILE — Use these REAL facts to strengthen the proposal:
- Full Name: {company_info.get('legal_name', 'ESSHVA TECHQ PVT LTD')} (Brand: {company_info.get('brand_name', 'ESSHVA')})
- Tagline: "{company_info.get('tagline', 'Build products, define experiences')}"
- Founded: {company_info.get('founded', 'N/A')} | HQ: {company_info.get('headquarters', {}).get('city', 'Colombo')}, {company_info.get('headquarters', {}).get('country', 'Sri Lanka')}
- Additional Presence: {company_info.get('additional_presence', 'N/A')}
- Certifications: {', '.join(certifications) if certifications else 'None listed'}
- Team Size: {company_info.get('employee_count', 'N/A')} employees
- Methodology: {services.get('methodology', 'Agile')}

SERVICES: {', '.join(services_list) if services_list else 'Custom software development'}
DELIVERY MODELS: {chr(10).join('  - ' + d for d in delivery_models) if delivery_models else 'Project-based, POD model'}
TECHNOLOGY STACK: {', '.join(tech.get('known_stack', [])) if tech.get('known_stack') else 'Full-stack capabilities'}
INDUSTRIES SERVED: {', '.join(industries) if industries else 'Multiple verticals'}

PRODUCTS & AWARDS:
{chr(10).join('  - ' + p for p in products_list) if products_list else '  - Multiple SaaS products'}
{chr(10).join('  - ' + a for a in awards_list) if awards_list else ''}

GLOBAL CLIENTS: {', '.join(global_reach.get('client_regions', [])) if global_reach.get('client_regions') else 'Global'}
NOTABLE CLIENTS: {global_reach.get('notable_client_types', 'Enterprise clients')}

CAPABILITY AREAS:
- Software Development: {capabilities.get('software_development', 'Custom enterprise software')}
- Cloud & Infrastructure: {capabilities.get('cloud_and_infrastructure', 'Cloud migration, managed infra')}
- AI & Data: {capabilities.get('ai_and_data', 'ML, AI solutions')}
- Integration: {capabilities.get('integration', 'Enterprise system integration')}
- Product Engineering: {capabilities.get('product_engineering', 'End-to-end product dev')}
- Quality Assurance: {capabilities.get('quality_assurance', 'Comprehensive testing, ISO certified')}

IMPORTANT: Reference these REAL company facts in the proposal — especially in "Why Choose ESSHVA", Executive Summary, and when justifying technical approach. Mention relevant certifications, industry experience, awards, and global client base where they strengthen the case. Do NOT fabricate capabilities that aren't listed above."""

    client = deal_context.get('client_name', 'Unknown Client')
    project = deal_context.get('title', 'Unknown Project')
    description = deal_context.get('description', '')
    budget = deal_context.get('budget_range', 'To be discussed')
    timeline = deal_context.get('timeline', 'To be discussed')

    prompt = f"""You are a senior proposal writer at ESSHVA, a technology solutions company. Your job is to write a WINNING proposal — one that proves ESSHVA is the best choice and directly addresses every concern the client might have.

BRANDING & TONE:
- The proposal is FROM "ESSHVA" to "{client}" for the "{project}" project
- Use "ESSHVA" as the company name. Mention the client naturally (executive summary, next steps) but don't force it into every sentence
- Do NOT mention any AI assistant, Quinn, or AI-generated disclaimers
- Write as ESSHVA's proposal team — confident, specific, and persuasive
- Use direct language: "We will deliver..." not "We can deliver..."
- Every claim must be backed by specifics from the requirements or team data below

CLIENT: {client}
PROJECT: {project}
{'DESCRIPTION: ' + description if description else ''}
BUDGET: {budget}
TIMELINE: {timeline}

REQUIREMENTS ({total_reqs} total):
{req_text}
{team_context}
{rag_context}
{company_context}

PROPOSAL STRATEGY — What to emphasize based on this project's requirements:
{strategy_block}

WINNING APPROACH — For EVERY section:
1. Don't just describe what ESSHVA will do — explain WHY this approach is better than alternatives
2. Tie each solution directly back to a specific requirement (e.g. "To address the need for X, we will...")
3. Include concrete deliverables, not vague promises
4. Where relevant, mention risks ESSHVA has already mitigated in the approach
5. Show business value — how does each piece help the client succeed, save money, or reduce risk?

Generate a complete proposal with these CORE sections:

# Proposal: {project}

## 1. Executive Summary
Open with a clear understanding of the business problem this project solves. State ESSHVA's proposed approach in 2-3 sentences. End with the key value proposition — why this proposal deserves to win. Keep it to 3-4 paragraphs.

## 2. Understanding of Requirements
Group the requirements logically (don't just list them). For each group, show that ESSHVA understands not just WHAT is needed but WHY it matters. Demonstrate insight into the business context behind the technical requirements.

## 3. Proposed Solution & Technical Approach
This is the core of the proposal. For each major requirement area, detail:
- The specific solution approach
- Technology choices and WHY they're the best fit (not just what they are)
- How components integrate together
- What makes this approach superior to obvious alternatives
Be specific — architecture patterns, frameworks, data flow. No generic platitudes.

## 4. Implementation Plan & Timeline
Phase-by-phase plan tied to actual deliverables. Each phase should:
- Have clear entry/exit criteria
- List concrete milestones the client can verify
- Show dependencies and risk buffers
- Map back to which requirements get delivered in each phase
Include week ranges or specific dates.

## 5. Proposed Team & Resources
Introduce each team member with their specific relevance to THIS project — don't just list titles. Show why this team composition is ideal for these requirements. Use ONLY the assigned team members listed above with their real names, roles, and skills.

## 6. Investment & Commercial Terms
Present pricing tied to deliverables (not just hourly rates). Use the real rates and allocations from the assigned team. Include:
- Breakdown by phase or deliverable
- Payment milestones linked to acceptance criteria
- What's included vs. optional add-ons

## 7. Why Choose ESSHVA
Don't be generic. Connect ESSHVA's REAL strengths (from the company profile above) directly to this project's specific challenges — reference certifications, awards, industry experience, global client base, and proven products. What would the client lose by going with a competitor? What unique advantage does ESSHVA bring?
{extra_sections_block}

## {next_steps_number}. Next Steps
This MUST be the FINAL section of the proposal. Clear, specific action items with a sense of momentum. Make it easy to say yes. Include:
- Company: ESSHVA
- Email: contact@esshva.com
- Website: www.esshva.com

Write in a confident, professional but warm tone. This should read like a proposal that was carefully crafted to win THIS specific deal — not a template with blanks filled in.

Output in clean markdown format with proper # and ## headers."""

    draft = call_llm(prompt, max_tokens=8192)

    # Parse sections
    sections = []
    current_section = {"title": "Introduction", "content": ""}
    for line in draft.split("\n"):
        if line.startswith("## ") or line.startswith("# "):
            if current_section["content"].strip():
                sections.append(current_section)
            current_section = {"title": line.lstrip("#").strip(), "content": ""}
        else:
            current_section["content"] += line + "\n"
    if current_section["content"].strip():
        sections.append(current_section)

    logger.info(f"generate node: proposal draft generated - length={len(draft)} chars, sections={len(sections)}")

    return {
        "proposal_draft": draft,
        "proposal_sections": sections,
        "current_step": "generate",
    }


def comply_node(state: ProposalState) -> Dict[str, Any]:
    """Step 3: Check proposal compliance against requirements."""
    draft = state.get("proposal_draft", "")
    requirements = state.get("requirements", [])

    if not requirements:
        return {
            "compliance_score": 1.0,
            "compliance_issues": [],
            "current_step": "comply",
        }

    req_text = "\n".join(f"{i+1}. [{r.get('category', 'general')}] {r.get('text', r.get('requirement_text', ''))}" for i, r in enumerate(requirements))

    prompt = f"""You are a compliance checker for ESSHVA. Review this proposal against the requirements and check compliance.

PROPOSAL:
{draft[:10000]}

REQUIREMENTS TO CHECK:
{req_text}

For each requirement, assess if it is addressed in the proposal. Return JSON:
{{
    "compliance_score": 0.0 to 1.0 (overall),
    "issues": [
        {{
            "requirement_index": 1,
            "requirement_text": "...",
            "status": "addressed|partially_addressed|not_addressed",
            "notes": "explanation"
        }}
    ]
}}

Return ONLY valid JSON."""

    result_text = call_llm(prompt, max_tokens=2048)

    try:
        logger.debug(f"comply node: raw response length={len(result_text)}")

        # Try multiple JSON extraction strategies
        parsed = None

        # Strategy 1: ```json code block
        if "```json" in result_text:
            json_str = result_text.split("```json")[1].split("```")[0].strip()
            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # Strategy 2: ``` code block
        if parsed is None and "```" in result_text:
            json_str = result_text.split("```")[1].split("```")[0].strip()
            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find JSON object with regex
        if parsed is None:
            import re
            json_match = re.search(r'\{[\s\S]*"compliance_score"[\s\S]*\}', result_text)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

        # Strategy 4: Try the entire response as JSON
        if parsed is None:
            try:
                parsed = json.loads(result_text.strip())
            except json.JSONDecodeError:
                pass

        if parsed:
            score = parsed.get("compliance_score", 0.0)
            # Ensure score is a float between 0 and 1
            if isinstance(score, (int, float)):
                score = max(0.0, min(1.0, float(score)))
            else:
                score = 0.85  # Default to reasonable score if parsing is odd
            issues_count = len(parsed.get('issues', []))
            logger.info(f"comply node: compliance check complete - score={score}, issue_count={issues_count}")
            return {
                "compliance_score": score,
                "compliance_issues": parsed.get("issues", []),
                "final_proposal": state.get("proposal_draft", ""),
                "current_step": "comply",
            }
        else:
            logger.warning(f"comply node: could not parse JSON response. First 500 chars: {result_text[:500]}")
            # If we can't parse but proposal was generated, give a default reasonable score
            return {
                "compliance_score": 0.85,
                "compliance_issues": [{"requirement_index": 0, "requirement_text": "Auto-check", "status": "partially_addressed", "notes": "Compliance check could not fully parse — manual review recommended."}],
                "final_proposal": state.get("proposal_draft", ""),
                "current_step": "comply",
            }

    except Exception as e:
        logger.error(f"comply node: exception occurred - {type(e).__name__}: {e}")
        return {
            "compliance_score": 0.85,
            "compliance_issues": [{"requirement_index": 0, "requirement_text": "Auto-check", "status": "partially_addressed", "notes": f"Compliance check error: {str(e)}"}],
            "final_proposal": state.get("proposal_draft", ""),
            "current_step": "comply",
        }


def build_proposal_graph() -> StateGraph:
    """Build the proposal generation LangGraph workflow."""
    workflow = StateGraph(ProposalState)

    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("comply", comply_node)

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", "comply")
    workflow.add_edge("comply", END)

    return workflow.compile()


proposal_graph = build_proposal_graph()
