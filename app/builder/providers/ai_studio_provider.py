"""
Google AI Studio Provider — AI Prototyping & Conversational Feature Engine.
Configures prompt templates, model configurations, safety settings, and interactive
AI conversational hooks for demo prototypes.
"""

from typing import Dict, Any, List, Optional
from app.database.models import ProjectSpecification, CustomerProject
from app.builder.models import AIPrototypeResult
from app.builder.providers.base import BaseAIProvider
from app.core.logging import logger


class GoogleAIStudioProvider(BaseAIProvider):
    """
    Provider integrating Google AI Studio & Gemini API for autonomous
    conversational inquiry intake, triage, and interactive prototyping.
    """

    DEFAULT_MODEL = "gemini-2.5-flash"

    async def generate_prototype(
        self,
        spec: ProjectSpecification,
        customer_project: CustomerProject
    ) -> AIPrototypeResult:
        industry = customer_project.industry or "General"
        biz_name = customer_project.title or "Client Partner"

        ai_features = spec.ai_features or []
        primary_feature = ai_features[0] if ai_features else {}

        system_instruction = primary_feature.get(
            "system_instructions",
            f"You are the dedicated AI assistant for {biz_name} in the {industry} sector. Warmly answer customer questions, explain service packages, and guide users to book appointments."
        )

        safety_settings = {
            "HARM_CATEGORY_HARASSMENT": "BLOCK_MEDIUM_AND_ABOVE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_MEDIUM_AND_ABOVE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_MEDIUM_AND_ABOVE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_MEDIUM_AND_ABOVE"
        }

        prompt_templates = {
            "greeting": f"Hello! Welcome to {biz_name}. How can we assist with your {industry} requirements today?",
            "booking_prompt": "I can schedule your consultation right now. What day and time work best for you?",
            "pricing_prompt": "We offer transparent, itemized packages designed specifically for your needs.",
            "emergency_prompt": "For urgent matters, our team is dispatched immediately upon inquiry confirmation."
        }

        # Deterministic simulation dialogue for client-safe interactive demonstration
        interactive_hooks = {
            "sample_dialogue": [
                {
                    "user": f"Hi, I was looking for services with {biz_name} and wanted to know about availability this week?",
                    "assistant": f"Welcome to {biz_name}! We have consultation openings available this Thursday at 10:30 AM or 2:00 PM. Would you like me to reserve one of those for you?"
                },
                {
                    "user": "Thursday at 10:30 AM works great.",
                    "assistant": f"Excellent! I've reserved Thursday at 10:30 AM for your consultation with {biz_name}. An automated confirmation has been logged to your calendar."
                }
            ],
            "quick_replies": [
                "Book Appointment",
                "Request Estimate",
                "Speak with Advisor"
            ]
        }

        fallback_behavior = {
            "on_model_timeout": "Display instant booking calendar and dispatch priority notification to service staff.",
            "on_invalid_input": "Politely ask customer for service type and contact phone number.",
            "escalate_to_human": "Alert senior management queue immediately."
        }

        logger.info(
            f"[GoogleAIStudioProvider] Configured AI prototype using {self.DEFAULT_MODEL} "
            f"for project {customer_project.project_id}."
        )

        return AIPrototypeResult(
            provider="google_ai_studio",
            status="AI_PROTOTYPE_READY",
            version=spec.version,
            prototype_type="conversational_assistant",
            prompt_templates=prompt_templates,
            system_instructions=system_instruction,
            safety_settings=safety_settings,
            model_name=self.DEFAULT_MODEL,
            fallback_behavior=fallback_behavior,
            interactive_hooks=interactive_hooks
        )
