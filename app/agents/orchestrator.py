import uuid
import json
import logging
import os
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.deal import Deal, DealRequirement, DealAnalysis
from app.models.document import Document
from app.models.alert import Alert, RecoveryAction
from app.models.proposal import Proposal
from app.models.employee import Employee
from app.models.assignment import DealAssignment
from app.websocket.manager import ws_manager
import asyncio

logger = logging.getLogger(__name__)


# In-memory task tracking (for hackathon - would use Redis in production)
task_store: Dict[str, Dict[str, Any]] = {}

# ── Load ESSHVA company profile once at startup ──
_company_profile: Dict[str, Any] = {}
_profile_path = os.path.join(os.path.dirname(__file__), "..", "data", "esshva_company_profile.json")
try:
    with open(os.path.normpath(_profile_path), "r") as f:
        _company_profile = json.load(f)
    logger.info(f"Loaded ESSHVA company profile: {_company_profile.get('company', {}).get('brand_name', 'Unknown')}")
except FileNotFoundError:
    logger.warning("ESSHVA company profile not found at app/data/esshva_company_profile.json — qualification will use employee data only")
except json.JSONDecodeError as e:
    logger.warning(f"Failed to parse company profile JSON: {e}")


async def send_update(task_id: str, step: str, step_num: int, total: int, status: str, message: str, data: dict = None):
    """Helper to update both in-memory store and WebSocket."""
    update = {
        "task_id": task_id,
        "step": step,
        "step_number": step_num,
        "total_steps": total,
        "status": status,
        "message": message,
        "data": data or {},
    }
    task_store[task_id] = update
    await ws_manager.send_task_update(task_id, update)


def _run_graph_sync(graph, initial_state, steps, step_messages, task_id, total_steps):
    """Run a LangGraph flow synchronously in a thread, updating task_store directly."""
    accumulated = {}
    for event in graph.stream(initial_state):
        for node_name, node_output in event.items():
            accumulated.update(node_output)
            step_idx = steps.index(node_name) + 1 if node_name in steps else 0
            # Update task_store directly (thread-safe in CPython due to GIL)
            task_store[task_id] = {
                "task_id": task_id,
                "step": node_name,
                "step_number": step_idx,
                "total_steps": total_steps,
                "status": "processing",
                "message": step_messages.get(node_name, f"Processing {node_name}..."),
                "data": {},
            }
    return accumulated


async def run_qualification_flow(task_id: str, deal_id: str, document_id: str = None):
    """Execute the qualification agent flow."""
    logger.info(f"run_qualification_flow: starting qualification flow for deal_id={deal_id}")
    from app.agents.qualification import qualification_graph

    db = SessionLocal()
    try:
        deal = db.query(Deal).filter(Deal.id == deal_id).first()
        if not deal:
            logger.error(f"run_qualification_flow: deal not found - deal_id={deal_id}")
            await send_update(task_id, "error", 0, 5, "failed", "Deal not found")
            return

        # Get ALL processed documents for this deal
        all_docs = (
            db.query(Document)
            .filter(Document.deal_id == deal_id, Document.is_processed == True)
            .order_by(Document.created_at.asc())
            .all()
        )

        # If a specific document_id was given, make sure it's included
        if document_id and not any(d.id == document_id for d in all_docs):
            specific_doc = db.query(Document).filter(Document.id == document_id).first()
            if specific_doc and specific_doc.extracted_text:
                all_docs.insert(0, specific_doc)

        if not all_docs:
            logger.error(f"run_qualification_flow: no processed documents found - deal_id={deal_id}")
            await send_update(task_id, "error", 0, 5, "failed", "No processed documents found for this deal")
            return

        logger.info(f"run_qualification_flow: found {len(all_docs)} documents for qualification")

        # Combine all document texts with clear separators
        doc_parts = []
        doc_metadata = {"document_count": len(all_docs), "documents": []}
        for doc in all_docs:
            if doc.extracted_text:
                category_label = (doc.doc_category or "general").upper()
                source_title = (doc.extraction_metadata or {}).get("title", doc.original_filename or doc.filename)
                doc_parts.append(f"=== [{category_label}] {source_title} ===\n{doc.extracted_text}")
                doc_metadata["documents"].append({
                    "id": doc.id,
                    "filename": doc.original_filename or doc.filename,
                    "category": doc.doc_category,
                    "size": doc.file_size,
                })

        doc_text = "\n\n".join(doc_parts)

        if not doc_text.strip():
            logger.error(f"run_qualification_flow: documents found but no text extracted - deal_id={deal_id}")
            await send_update(task_id, "error", 0, 5, "failed", "Documents found but no text could be extracted")
            return

        await send_update(task_id, "ingest", 1, 5, "processing", f"Ingesting {len(all_docs)} document(s)...")

        # ── Fetch real employee capabilities for gap analysis ──
        all_employees = db.query(Employee).filter(Employee.is_active == True).all()
        employee_capabilities = []
        all_skills_set = set()
        all_departments = set()
        for emp in all_employees:
            emp_skills = emp.skills or []
            all_skills_set.update(s.lower() for s in emp_skills)
            if emp.department:
                all_departments.add(emp.department)
            employee_capabilities.append({
                "name": emp.name,
                "role": emp.role or "",
                "department": emp.department or "",
                "skills": emp_skills,
                "availability_percent": emp.availability_percent or 100,
                "hourly_rate": emp.hourly_rate or 0,
            })
        logger.info(f"run_qualification_flow: loaded {len(employee_capabilities)} employees with {len(all_skills_set)} unique skills for capability analysis")

        # Run the LangGraph flow
        initial_state = {
            "deal_id": deal_id,
            "task_id": task_id,
            "document_text": doc_text,
            "document_metadata": doc_metadata,
            "extracted_requirements": [],
            "extracted_entities": {},
            "employee_capabilities": employee_capabilities,
            "company_profile": _company_profile,
            "skill_matches": [],
            "gap_analysis": {},
            "recommendation": "",
            "confidence_score": 0.0,
            "positive_factors": [],
            "risk_factors": [],
            "conditions": [],
            "reasoning": "",
            "current_step": "",
            "messages": [],
            "errors": [],
        }

        steps = ["ingest", "extract", "analyze", "match", "decide"]
        step_messages = {
            "ingest": "Parsing document structure...",
            "extract": "Extracting requirements and entities...",
            "analyze": "Analyzing deal viability...",
            "match": "Matching employee skills...",
            "decide": "Generating GO/NO-GO recommendation...",
        }

        # Run blocking graph in a thread so we don't block the event loop
        accumulated = await asyncio.to_thread(
            _run_graph_sync, qualification_graph, initial_state, steps, step_messages, task_id, 5
        )

        result = accumulated
        if result:
            requirements_found = len(result.get("extracted_requirements", []))
            logger.info(f"run_qualification_flow: qualification flow completed - requirements_found={requirements_found}")

            # Save requirements to DB
            for req in result.get("extracted_requirements", []):
                db_req = DealRequirement(
                    id=str(uuid.uuid4()),
                    deal_id=deal_id,
                    category=req.get("category", "technical"),
                    requirement_text=req.get("text", ""),
                    confidence=req.get("confidence", 0.5),
                )
                db.add(db_req)

            # Save analysis to DB
            analysis = DealAnalysis(
                id=str(uuid.uuid4()),
                deal_id=deal_id,
                analysis_type="qualification",
                recommendation=result.get("recommendation", "no_go"),
                confidence_score=result.get("confidence_score", 0.0),
                positive_factors=result.get("positive_factors", []),
                risk_factors=result.get("risk_factors", []),
                conditions=result.get("conditions", []),
                reasoning=result.get("reasoning", ""),
            )
            db.add(analysis)

            # Real employee matching against extracted requirements + gap analysis
            gap_analysis = result.get("gap_analysis", {})
            key_roles = gap_analysis.get("resource_estimate", {}).get("key_roles", [])
            all_employees = db.query(Employee).filter(Employee.is_active == True).all()

            matched_staff = []
            if all_employees:
                # Build skill keywords from requirements + gap analysis
                required_keywords = set()
                for req in result.get("extracted_requirements", []):
                    text = req.get("text", "").lower()
                    for word in text.split():
                        if len(word) > 3:
                            required_keywords.add(word)
                    required_keywords.add(req.get("category", "").lower())

                for area in gap_analysis.get("strong_areas", []) + gap_analysis.get("gap_areas", []):
                    for word in area.lower().split():
                        if len(word) > 3:
                            required_keywords.add(word)

                for role in key_roles:
                    for word in role.lower().split():
                        if len(word) > 3:
                            required_keywords.add(word)

                # Score each employee
                for emp in all_employees:
                    emp_skills = {s.lower() for s in (emp.skills or [])}
                    emp_role_words = {w.lower() for w in emp.role.split() if len(w) > 3}
                    all_emp_terms = emp_skills | emp_role_words
                    overlap = all_emp_terms & required_keywords
                    if overlap:
                        matched_staff.append({
                            "employee_id": emp.id,
                            "name": emp.name,
                            "role": emp.role,
                            "skills": emp.skills or [],
                            "matching_skills": list(overlap),
                            "match_score": len(overlap),
                            "availability_percent": emp.availability_percent,
                            "hourly_rate": emp.hourly_rate,
                        })

                matched_staff.sort(key=lambda x: x["match_score"], reverse=True)

            # Auto-assign top 5 matched employees to the deal
            auto_assigned = 0
            if matched_staff:
                # Clear any previous auto-assignments for this deal
                db.query(DealAssignment).filter(
                    DealAssignment.deal_id == deal_id,
                    DealAssignment.assigned_by == "auto",
                ).delete()

                for staff in matched_staff[:5]:
                    assignment = DealAssignment(
                        id=str(uuid.uuid4()),
                        deal_id=deal_id,
                        employee_id=staff["employee_id"],
                        role_on_deal=staff["role"],
                        allocation_percent=min(staff.get("availability_percent", 100), 100),
                        assigned_by="auto",
                        match_score=staff["match_score"],
                    )
                    db.add(assignment)
                    auto_assigned += 1

            # Update deal stage
            deal.stage = "qualification"
            db.commit()

            logger.info(f"run_qualification_flow: final result - recommendation={result.get('recommendation')}, employees_matched={len(matched_staff)}, auto_assigned={auto_assigned}")

            await send_update(task_id, "complete", 5, 5, "completed", "Qualification complete", {
                "recommendation": result.get("recommendation"),
                "confidence_score": result.get("confidence_score"),
                "requirements_found": len(result.get("extracted_requirements", [])),
                "matched_employees": len(matched_staff),
                "auto_assigned": auto_assigned,
                "key_roles": key_roles,
            })
    except Exception as e:
        logger.error(f"run_qualification_flow: exception occurred - {type(e).__name__}: {e}")
        db.rollback()
        await send_update(task_id, "error", 0, 5, "failed", f"Error: {str(e)}")
    finally:
        db.close()


async def run_proposal_flow(task_id: str, deal_id: str):
    """Execute the proposal generation agent flow."""
    logger.info(f"run_proposal_flow: starting proposal flow for deal_id={deal_id}")
    from app.agents.proposal import proposal_graph

    db = SessionLocal()
    try:
        deal = db.query(Deal).filter(Deal.id == deal_id).first()
        if not deal:
            logger.error(f"run_proposal_flow: deal not found - deal_id={deal_id}")
            await send_update(task_id, "error", 0, 3, "failed", "Deal not found")
            return

        requirements = db.query(DealRequirement).filter(DealRequirement.deal_id == deal_id).all()

        # ── Fetch assigned employees for this deal ──
        assignments = (
            db.query(DealAssignment, Employee)
            .join(Employee, DealAssignment.employee_id == Employee.id)
            .filter(DealAssignment.deal_id == deal_id)
            .all()
        )
        team_data = []
        for assignment, emp in assignments:
            team_data.append({
                "name": emp.name,
                "role": assignment.role_on_deal or emp.role,
                "skills": emp.skills or [],
                "department": emp.department or "",
                "hourly_rate": assignment.hourly_rate_override or emp.hourly_rate or 0,
                "allocation_percent": assignment.allocation_percent or 100,
                "assigned_by": assignment.assigned_by or "manual",
            })
        logger.info(f"run_proposal_flow: found {len(team_data)} assigned team members for deal_id={deal_id}")

        await send_update(task_id, "retrieve", 1, 3, "processing", "Quinn is retrieving relevant proposal context...")

        initial_state = {
            "deal_id": deal_id,
            "task_id": task_id,
            "deal_context": {
                "title": deal.title,
                "client_name": deal.client_name,
                "deal_value": deal.deal_value,
                "description": deal.description or "",
            },
            "requirements": [
                {"category": r.category, "text": r.requirement_text, "confidence": r.confidence}
                for r in requirements
            ],
            "team_assignments": team_data,
            "company_profile": _company_profile,
            "retrieved_sections": [],
            "proposal_draft": "",
            "proposal_sections": [],
            "compliance_score": 0.0,
            "compliance_issues": [],
            "final_proposal": "",
            "proposal_id": "",
            "current_step": "",
            "messages": [],
            "errors": [],
        }

        steps = ["retrieve", "generate", "comply"]
        step_messages = {
            "retrieve": "Searching knowledge base for relevant proposal sections...",
            "generate": "Generating proposal draft...",
            "comply": "Checking compliance against requirements...",
        }

        # Run blocking graph in a thread so we don't block the event loop
        result = await asyncio.to_thread(
            _run_graph_sync, proposal_graph, initial_state, steps, step_messages, task_id, 3
        )
        if result:
            compliance_score = result.get("compliance_score", 0.0)
            logger.info(f"run_proposal_flow: proposal flow completed - compliance_score={compliance_score}")

            proposal = Proposal(
                id=str(uuid.uuid4()),
                deal_id=deal_id,
                title=f"Proposal - {deal.client_name} - {deal.title}",
                content=result.get("final_proposal") or result.get("proposal_draft", ""),
                compliance_score=compliance_score,
                compliance_notes=result.get("compliance_issues", []),
                generated_by="esshva",
                status="draft",
            )
            db.add(proposal)
            deal.stage = "proposal"
            db.commit()

            await send_update(task_id, "complete", 3, 3, "completed", "Proposal generated", {
                "proposal_id": proposal.id,
                "compliance_score": compliance_score,
            })
    except Exception as e:
        logger.error(f"run_proposal_flow: exception occurred - {type(e).__name__}: {e}")
        db.rollback()
        await send_update(task_id, "error", 0, 3, "failed", f"Error: {str(e)}")
    finally:
        db.close()


async def run_monitoring_flow(task_id: str, deal_id: str):
    """Execute the monitoring agent flow."""
    logger.info(f"run_monitoring_flow: starting monitoring flow for deal_id={deal_id}")
    from app.agents.monitoring import monitoring_graph

    db = SessionLocal()
    try:
        deal = db.query(Deal).filter(Deal.id == deal_id).first()
        if not deal:
            logger.error(f"run_monitoring_flow: deal not found - deal_id={deal_id}")
            await send_update(task_id, "error", 0, 4, "failed", "Deal not found")
            return

        await send_update(task_id, "sentiment", 1, 4, "processing", "Fetching emails from Gmail...")

        # ── Determine time window: only fetch emails since the last monitoring run ──
        from datetime import datetime, timedelta
        last_alert = (
            db.query(Alert)
            .filter(Alert.deal_id == deal_id)
            .order_by(Alert.created_at.desc())
            .first()
        )
        if last_alert and last_alert.created_at:
            # Fetch emails newer than the last alert (with 1-hour overlap buffer)
            since_dt = last_alert.created_at - timedelta(hours=1)
            after_filter = since_dt.strftime("%Y/%m/%d")
            logger.info(f"run_monitoring_flow: last alert at {last_alert.created_at}, fetching emails after {after_filter}")
        else:
            # No previous monitoring — fetch last 7 days
            after_filter = (datetime.utcnow() - timedelta(days=7)).strftime("%Y/%m/%d")
            logger.info(f"run_monitoring_flow: no previous alerts, fetching emails after {after_filter}")

        # ── Fetch real emails from Gmail ──
        real_comms = []
        no_emails_reason = None
        try:
            from app.routers.integrations import get_gmail_client
            from app.models.integration import OAuthToken
            oauth = db.query(OAuthToken).filter(OAuthToken.provider == "google").first()
            if not oauth:
                no_emails_reason = "Gmail not connected. Connect your Google account in Settings."
                logger.warning("run_monitoring_flow: no Google OAuth token found")
            else:
                gmail = await get_gmail_client(oauth.user_id, db)
                if not gmail:
                    no_emails_reason = "Gmail token expired and could not be refreshed. Please reconnect in Settings."
                    logger.warning("run_monitoring_flow: Gmail client could not be created (token refresh failed)")
                else:
                    client_name = deal.client_name or ""
                    emails = []

                    # Step 1: Search for emails matching the client name (only since last run)
                    if client_name:
                        time_query = f"{client_name} after:{after_filter}"
                        emails = await gmail.search_emails(query=time_query, max_results=15)
                        if emails:
                            logger.info(f"run_monitoring_flow: found {len(emails)} recent emails matching client '{client_name}'")
                        else:
                            logger.info(f"run_monitoring_flow: no recent emails matching client '{client_name}', trying fallback")

                    # Step 2: If no client match (or no client name), get last 5 recent emails
                    if not client_name or not emails:
                        emails = await gmail.search_emails(query=f"newer_than:3d", max_results=5)
                        if emails:
                            logger.info(f"run_monitoring_flow: using {len(emails)} recent emails as fallback")

                    # Convert to comms format and sort newest-first
                    for e in emails:
                        real_comms.append({
                            "type": "email",
                            "date": e.get("date", "")[:10],
                            "from": e.get("from", ""),
                            "subject": e.get("subject", ""),
                            "content": e.get("preview", ""),
                            "raw_date": e.get("date", ""),
                        })
                    # Sort by date descending (newest first) — Gmail returns newest first
                    # but we make it explicit in case of mixed sources
                    real_comms.sort(key=lambda x: x.get("raw_date", ""), reverse=True)
                    # Remove raw_date helper field
                    for c in real_comms:
                        c.pop("raw_date", None)

                    if not real_comms:
                        no_emails_reason = f"No new emails found for '{client_name}' since last monitoring run."
                        logger.info(f"run_monitoring_flow: {no_emails_reason}")

        except Exception as e:
            no_emails_reason = f"Gmail fetch failed: {str(e)}"
            logger.warning(f"run_monitoring_flow: {no_emails_reason}")

        # If no emails at all, finish early with a clear message
        if not real_comms:
            logger.info(f"run_monitoring_flow: no communications to analyze - {no_emails_reason}")
            await send_update(task_id, "complete", 4, 4, "completed", "Monitoring complete — no relevant emails found", {
                "health_score": deal.health_score or 70,
                "sentiment": 0.0,
                "alerts_generated": 0,
                "no_emails_reason": no_emails_reason,
            })
            return

        initial_state = {
            "deal_id": deal_id,
            "task_id": task_id,
            "deal_data": {
                "title": deal.title,
                "client_name": deal.client_name,
                "deal_value": deal.deal_value,
                "health_score": deal.health_score or 70,
                "stage": deal.stage,
            },
            "recent_communications": real_comms,
            "sentiment_scores": [],
            "overall_sentiment": 0.0,
            "health_score": 70,
            "trend": "stable",
            "detected_alerts": [],
            "recovery_email": "",
            "recovery_actions": [],
            "current_step": "",
            "messages": [],
            "errors": [],
        }

        steps = ["sentiment", "health", "alert", "recovery"]
        step_messages = {
            "sentiment": "Analyzing communication sentiment...",
            "health": "Calculating deal health score...",
            "alert": "Detecting potential risks...",
            "recovery": "Generating recovery strategy...",
        }

        # Run blocking graph in a thread so we don't block the event loop
        result = await asyncio.to_thread(
            _run_graph_sync, monitoring_graph, initial_state, steps, step_messages, task_id, 4
        )
        if result:
            health_score = result.get("health_score", deal.health_score)
            alerts_count = len(result.get("detected_alerts", []))
            logger.info(f"run_monitoring_flow: monitoring flow completed - email_count={len(real_comms)}, health_score={health_score}, alerts_count={alerts_count}")

            # Parse recovery email into subject + body
            raw_email = result.get("recovery_email", "")
            email_subject = ""
            email_body = raw_email
            if raw_email:
                # LLM often returns "Subject: ...\n\nBody..."
                lines = raw_email.strip().split("\n", 1)
                first_line = lines[0].strip()
                if first_line.lower().startswith("subject:"):
                    email_subject = first_line[len("subject:"):].strip()
                    email_body = lines[1].strip() if len(lines) > 1 else ""
                else:
                    # No explicit subject line — use first sentence
                    email_subject = "Re: " + deal.title
                    email_body = raw_email
                logger.info(f"run_monitoring_flow: recovery email parsed - subject='{email_subject[:60]}', body_len={len(email_body)}")

            # Serialize source emails for audit trail
            source_emails_json = json.dumps(real_comms) if real_comms else None

            # Save alerts to DB
            for alert_data in result.get("detected_alerts", []):
                alert = Alert(
                    id=str(uuid.uuid4()),
                    deal_id=deal_id,
                    alert_type=alert_data.get("alert_type", "sentiment_drop"),
                    severity=alert_data.get("severity", "medium"),
                    title=alert_data.get("title", "Alert"),
                    description=alert_data.get("description", ""),
                    sentiment_score=result.get("overall_sentiment"),
                    source_context=source_emails_json,
                    email_subject=email_subject,
                    email_body=email_body,
                )
                db.add(alert)

                # Add recovery actions
                for i, action_text in enumerate(result.get("recovery_actions", [])):
                    action = RecoveryAction(
                        id=str(uuid.uuid4()),
                        alert_id=alert.id,
                        action_text=action_text,
                        priority=i + 1,
                    )
                    db.add(action)

            # Update deal health
            deal.health_score = health_score
            if result.get("detected_alerts"):
                deal.status = "at_risk"
            db.commit()

            # ── WhatsApp alert for critical/high severity risks ──
            risk_alerts = [
                a for a in result.get("detected_alerts", [])
                if a.get("severity") in ("critical", "high")
            ]
            if risk_alerts:
                try:
                    from app.mcp.tools.whatsapp_tools import send_deal_risk_alert
                    for alert_data in risk_alerts:
                        wa_result = send_deal_risk_alert(
                            deal_title=deal.title,
                            client_name=deal.client_name or "Unknown",
                            alert_type=alert_data.get("alert_type", "sentiment_drop"),
                            severity=alert_data.get("severity", "high"),
                            health_score=health_score,
                            sentiment_score=result.get("overall_sentiment", 0.0),
                            description=alert_data.get("description", ""),
                        )
                        if wa_result.get("status") == "ok":
                            logger.info(f"run_monitoring_flow: WhatsApp alert sent — SID: {wa_result.get('message_sid')}")
                        else:
                            logger.warning(f"run_monitoring_flow: WhatsApp alert failed — {wa_result.get('error')}")
                except Exception as wa_err:
                    logger.warning(f"run_monitoring_flow: WhatsApp notification skipped — {wa_err}")

            await send_update(task_id, "complete", 4, 4, "completed", "Monitoring complete", {
                "health_score": health_score,
                "sentiment": result.get("overall_sentiment"),
                "alerts_generated": alerts_count,
                "whatsapp_notified": len(risk_alerts) > 0,
            })
    except Exception as e:
        logger.error(f"run_monitoring_flow: exception occurred - {type(e).__name__}: {e}")
        db.rollback()
        await send_update(task_id, "error", 0, 4, "failed", f"Error: {str(e)}")
    finally:
        db.close()


async def run_agent_flow(task_id: str, deal_id: str, flow_type: str, **kwargs):
    """Main entry point - route to the correct agent flow."""
    logger.info(f"run_agent_flow: starting {flow_type} flow for deal_id={deal_id}")
    task_store[task_id] = {
        "task_id": task_id,
        "step": "initializing",
        "status": "processing",
        "message": f"Starting {flow_type} flow...",
    }

    if flow_type == "qualification":
        await run_qualification_flow(task_id, deal_id, **kwargs)
    elif flow_type == "proposal":
        await run_proposal_flow(task_id, deal_id)
    elif flow_type == "monitoring":
        await run_monitoring_flow(task_id, deal_id)
    else:
        logger.error(f"run_agent_flow: unknown flow type - flow_type={flow_type}")
        await send_update(task_id, "error", 0, 0, "failed", f"Unknown flow type: {flow_type}")
