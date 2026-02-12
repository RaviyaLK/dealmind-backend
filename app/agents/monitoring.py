import json
import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from app.agents.state import MonitoringState
from app.services.llm import call_llm

logger = logging.getLogger(__name__)


def sentiment_node(state: MonitoringState) -> Dict[str, Any]:
    """Step 1: Analyze sentiment from recent communications."""
    logger.info("sentiment node: starting communication sentiment analysis")
    communications = state.get("recent_communications", [])
    deal_data = state.get("deal_data", {})

    if not communications:
        logger.warning("sentiment node: no communications found to analyze")
        return {
            "sentiment_scores": [],
            "overall_sentiment": 0.0,
            "current_step": "sentiment",
        }

    # Build communications text — emails are sorted newest-first
    comms_lines = []
    for i, c in enumerate(communications[:10]):
        label = "★ MOST RECENT EMAIL" if i == 0 else f"Email #{i + 1}"
        from_field = c.get('from', 'unknown')
        subject = c.get('subject', '(no subject)')
        date = c.get('date', 'unknown')
        content = c.get('content', '')
        comms_lines.append(f"--- {label} (Date: {date}) ---\nFrom: {from_field}\nSubject: {subject}\n{content}")
    comms_text = "\n\n".join(comms_lines)

    prompt = f"""You are Quinn, an AI deal intelligence agent. Analyze the sentiment of these recent communications for the deal: {deal_data.get('title', 'Unknown Deal')}.

IMPORTANT: The emails below are sorted NEWEST FIRST. The ★ MOST RECENT EMAIL carries the HIGHEST weight — it reflects the client's CURRENT state of mind. Older emails provide context but should NOT override the latest sentiment. If the latest email is positive, the overall sentiment should lean positive even if older emails were negative (the situation has improved).

COMMUNICATIONS:
{comms_text}

Analyze each communication and provide overall sentiment. The overall_sentiment MUST primarily reflect the most recent email's tone. Return JSON:
{{
    "scores": [
        {{
            "index": 0,
            "sentiment": -1.0 to 1.0,
            "signals": ["positive or negative signals detected"],
            "summary": "brief summary"
        }}
    ],
    "overall_sentiment": -1.0 to 1.0 (MUST primarily reflect the LATEST email),
    "key_concerns": ["any concerning patterns"],
    "positive_signals": ["any positive patterns"]
}}

Return ONLY valid JSON."""

    result_text = call_llm(prompt, max_tokens=2048)

    try:
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        result = json.loads(result_text.strip())
        sentiment_scores = result.get("scores", [])
        overall_sentiment = result.get("overall_sentiment", 0.0)
        logger.info(f"sentiment node: sentiment analysis complete - communications_analyzed={len(sentiment_scores)}, overall_sentiment={overall_sentiment}")
        return {
            "sentiment_scores": sentiment_scores,
            "overall_sentiment": overall_sentiment,
            "current_step": "sentiment",
        }
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"sentiment node: JSON parsing failed - {str(e)}")
        return {
            "sentiment_scores": [],
            "overall_sentiment": 0.0,
            "current_step": "sentiment",
        }


def health_node(state: MonitoringState) -> Dict[str, Any]:
    """Step 2: Calculate deal health score."""
    logger.info("health node: calculating deal health score")
    deal_data = state.get("deal_data", {})
    sentiment = state.get("overall_sentiment", 0.0)

    # Health score calculation: base score adjusted by sentiment and other factors
    base_score = deal_data.get("health_score", 70)

    # Sentiment adjustment (-20 to +10 points)
    sentiment_adjustment = int(sentiment * 15)

    health_score = max(0, min(100, base_score + sentiment_adjustment))

    # Determine trend
    previous_score = deal_data.get("previous_health_score", base_score)
    if health_score > previous_score + 5:
        trend = "up"
    elif health_score < previous_score - 5:
        trend = "down"
    else:
        trend = "stable"

    logger.info(f"health node: health score calculated - score={health_score}, trend={trend}")

    return {
        "health_score": health_score,
        "trend": trend,
        "current_step": "health",
    }


def alert_node(state: MonitoringState) -> Dict[str, Any]:
    """Step 3: Detect and generate alerts based on analysis."""
    logger.info("alert node: detecting alerts based on analysis")
    sentiment = state.get("overall_sentiment", 0.0)
    health_score = state.get("health_score", 70)
    sentiment_scores = state.get("sentiment_scores", [])
    deal_data = state.get("deal_data", {})

    alerts = []

    # Sentiment drop alert
    if sentiment < -0.3:
        alerts.append({
            "alert_type": "sentiment_drop",
            "severity": "critical" if sentiment < -0.6 else "high",
            "title": f"Negative sentiment detected for {deal_data.get('client_name', 'client')}",
            "description": f"Overall sentiment score: {sentiment:.2f}. Immediate attention required.",
        })

    # Health score alert
    if health_score < 50:
        alerts.append({
            "alert_type": "deadline_risk",
            "severity": "high",
            "title": f"Deal health critical: {health_score}%",
            "description": f"Deal health has dropped to {health_score}%. Review and take action.",
        })

    # Check for competitor mentions in sentiment analysis
    for score in sentiment_scores:
        signals = score.get("signals", [])
        for signal in signals:
            if "competitor" in signal.lower():
                alerts.append({
                    "alert_type": "competitor_mention",
                    "severity": "medium",
                    "title": "Competitor mentioned in communications",
                    "description": signal,
                })
                break

    # Positive sentiment — create an info-level notification so we still generate a reply
    if not alerts and sentiment > 0.2:
        positive_signals = []
        for score in sentiment_scores:
            positive_signals.extend(score.get("signals", []))
        alerts.append({
            "alert_type": "positive_update",
            "severity": "info",
            "title": f"Positive sentiment from {deal_data.get('client_name', 'client')}",
            "description": f"Client communication is positive (sentiment: {sentiment:.2f}). " + ("; ".join(positive_signals[:3]) if positive_signals else "Good relationship signals detected."),
        })

    logger.info(f"alert node: alerts generated - alert_count={len(alerts)}")

    return {
        "detected_alerts": alerts,
        "current_step": "alert",
    }


def recovery_node(state: MonitoringState) -> Dict[str, Any]:
    """Step 4: Generate reply email — recovery for risks, positive follow-up for good news."""
    logger.info("recovery node: generating email response")
    alerts = state.get("detected_alerts", [])
    deal_data = state.get("deal_data", {})
    sentiment = state.get("overall_sentiment", 0.0)

    if not alerts:
        logger.info("recovery node: no alerts detected, skipping")
        return {
            "recovery_email": "",
            "recovery_actions": [],
            "current_step": "recovery",
        }

    # Determine if this is a positive or negative situation
    is_positive = all(a.get("alert_type") == "positive_update" for a in alerts)

    alert_summary = "\n".join(f"- [{a['severity']}] {a['title']}: {a['description']}" for a in alerts)

    # Include the actual source emails so the LLM addresses the right person
    comms = state.get("recent_communications", [])
    comms_summary = ""
    sender_name = ""
    sender_email = ""
    if comms:
        comms_lines = []
        for c in comms:
            from_field = c.get("from", "")
            subj = c.get("subject", "(no subject)")
            content = c.get("content", "")[:500]
            comms_lines.append(f"From: {from_field}\nSubject: {subj}\nDate: {c.get('date', '')}\n{content}")
            if not sender_email and from_field:
                sender_email = from_field
                if "<" in from_field:
                    sender_name = from_field.split("<")[0].strip().strip('"')
                else:
                    sender_name = from_field.split("@")[0]
        comms_summary = "\n---\n".join(comms_lines)

    recipient = sender_name or deal_data.get('client_name', 'the client')

    if is_positive:
        prompt = f"""You are Quinn, an AI deal intelligence agent. The client has sent a POSITIVE email about the deal. Generate a warm, professional reply to strengthen the relationship.

DEAL: {deal_data.get('title', 'Unknown')}
CLIENT: {deal_data.get('client_name', 'Unknown')}
SENTIMENT: {sentiment:.2f} (POSITIVE)
DEAL VALUE: {deal_data.get('deal_value', 'Unknown')}

SOURCE EMAILS:
{comms_summary if comms_summary else "(No source emails available)"}

RECIPIENT: {recipient} at {sender_email or 'their email'}

Generate:
1. A warm, professional reply email to {recipient} that:
   - Thanks them for the positive feedback
   - References specific points they mentioned in their email
   - Reaffirms your commitment to the project
   - Proposes next steps or expresses excitement about future collaboration
   - Is well-formatted with separate paragraphs (use \\n\\n between paragraphs)
   - Starts with a greeting and ends with a professional sign-off
2. A list of internal action items to capitalize on the positive momentum

Return JSON:
{{
    "recovery_email": "Subject: Re: ...\n\nDear {recipient},\n\nThank you paragraph...\n\nSpecific feedback reference...\n\nNext steps...\n\nBest regards,\\n[Name]\\n[Title]",
    "recovery_actions": [
        "Action item 1",
        "Action item 2"
    ]
}}

Return ONLY valid JSON."""
    else:
        prompt = f"""You are Quinn, an AI deal intelligence agent. Based on these alerts for {deal_data.get('client_name', 'the client')}, generate a recovery strategy.

DEAL: {deal_data.get('title', 'Unknown')}
CLIENT: {deal_data.get('client_name', 'Unknown')}
SENTIMENT: {sentiment:.2f}
DEAL VALUE: {deal_data.get('deal_value', 'Unknown')}

ALERTS:
{alert_summary}

SOURCE EMAILS THAT TRIGGERED THESE ALERTS:
{comms_summary if comms_summary else "(No source emails available)"}

RECIPIENT FOR RECOVERY EMAIL: {sender_email or deal_data.get('client_name', 'the client')}

Provide:
1. A professional recovery email addressed to {recipient} at {sender_email or 'their email'}. The email should directly address their specific concerns from the source emails above, reaffirm value, and offer concrete next steps.
   - The email MUST be well-formatted with separate paragraphs (use \\n\\n between paragraphs).
   - Start with a greeting line (e.g. "Dear [Name],")
   - Each key point should be its own paragraph
   - End with a professional sign-off (e.g. "Best regards,\\n[Your Name]\\n[Your Title]")
2. A list of internal action items for the team

Return JSON:
{{
    "recovery_email": "Subject: Re: Concern about ...\n\nDear [Name],\n\nFirst paragraph addressing concern...\n\nSecond paragraph with value proposition...\n\nThird paragraph with next steps...\n\nBest regards,\n[Name]\n[Title]",
    "recovery_actions": [
        "Action item 1",
        "Action item 2"
    ]
}}

Return ONLY valid JSON."""

    result_text = call_llm(prompt, max_tokens=2048)

    try:
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        result = json.loads(result_text.strip())
        recovery_actions_count = len(result.get("recovery_actions", []))
        logger.info(f"recovery node: recovery strategy generated - actions_count={recovery_actions_count}")
        return {
            "recovery_email": result.get("recovery_email", ""),
            "recovery_actions": result.get("recovery_actions", []),
            "current_step": "recovery",
        }
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"recovery node: JSON parsing failed - {str(e)}")
        return {
            "recovery_email": "",
            "recovery_actions": [],
            "current_step": "recovery",
        }


def build_monitoring_graph() -> StateGraph:
    """Build the monitoring LangGraph workflow."""
    workflow = StateGraph(MonitoringState)

    workflow.add_node("sentiment", sentiment_node)
    workflow.add_node("health", health_node)
    workflow.add_node("alert", alert_node)
    workflow.add_node("recovery", recovery_node)

    workflow.set_entry_point("sentiment")
    workflow.add_edge("sentiment", "health")
    workflow.add_edge("health", "alert")
    workflow.add_edge("alert", "recovery")
    workflow.add_edge("recovery", END)

    return workflow.compile()


monitoring_graph = build_monitoring_graph()
