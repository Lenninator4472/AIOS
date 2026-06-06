"""
AI-DOS Kernel: Multi-agent System
Specialized agents with independent LLM contexts and an orchestrator.
"""

import json
import uuid
from typing import Dict, List, Optional

from kernel.llm import get_provider, extract_json


# System prompts for specialized agents
CODER_PROMPT = """You are Coder Agent, an AI-DOS subsystem specialized in writing, analyzing, and debugging code.
You respond with the SAME JSON format as the AI-DOS kernel:
{
  "thought_process": "Your reasoning about the code task.",
  "commands": ["any shell commands needed"],
  "user_response": "The code/output/explanation."
}
Focus on Python, Kotlin, and bash. Output clean, working code."""

RESEARCHER_PROMPT = """You are Research Agent, an AI-DOS subsystem specialized in information analysis.
You respond with the SAME JSON format as the AI-DOS kernel:
{
  "thought_process": "Your reasoning about the research task.",
  "commands": [],
  "user_response": "The researched information."
}
You explain concepts and analyze data. You do NOT have internet access — work with what the user provides."""

SYSADMIN_PROMPT = """You are Sysadmin Agent, an AI-DOS subsystem specialized in system operations.
You respond with the SAME JSON format as the AI-DOS kernel:
{
  "thought_process": "Your reasoning about the system task.",
  "commands": ["safe shell commands"],
  "user_response": "Results of the system operation."
}
Focus on file management, process monitoring, and system configuration. Follow all safety rules."""

PLANNER_PROMPT = """You are Planner Agent, an AI-DOS subsystem specialized in task decomposition.
You respond with the SAME JSON format as the AI-DOS kernel:
{
  "thought_process": "How to break this task down.",
  "commands": [],
  "user_response": "A step-by-step plan with which agent should handle each step."
}
Given a complex request, break it into steps and recommend which agent(s) should handle each."""


class Agent:
    """
    An AI agent with its own LLM provider, system prompt, conversation context,
    and optional EventBus integration for inter-agent communication.
    """

    def __init__(self, name: str, system_prompt: str, model: str = None, bus=None):
        self.name = name
        self.system_prompt = system_prompt
        self.llm = get_provider(model=model or "llama3.2:1b")
        self.messages: List[Dict] = [{"role": "system", "content": system_prompt}]
        self.session_log: List[Dict] = []
        self.bus = bus

    def process(self, user_input: str) -> dict:
        """Process an input through this agent's LLM. Returns parsed JSON decision.

        If connected to an EventBus, emits ``agent.<name>.started`` before
        processing and ``agent.<name>.output`` with the result afterwards.
        """
        self.messages.append({"role": "user", "content": user_input})

        if self.bus:
            self.bus.emit(f"agent.{self.name}.started", {"task": user_input})

        raw = self.llm.query(self.system_prompt, user_input, self.messages[1:])
        decision = extract_json(raw)
        if decision is None:
            decision = {
                "thought_process": f"Agent {self.name}: failed to parse LLM response",
                "commands": [],
                "user_response": raw[:200],
            }
        self.messages.append({"role": "assistant", "content": json.dumps(decision)})
        self.session_log.append({"input": user_input, "output": decision})

        if self.bus:
            self.bus.emit(f"agent.{self.name}.output", {
                "task": user_input,
                "response": decision.get("user_response", ""),
                "has_commands": bool(decision.get("commands")),
            })

        return decision

    def reset(self):
        """Clear conversation context (keep system prompt)."""
        self.messages = [{"role": "system", "content": self.system_prompt}]


class AgentOrchestrator:
    """
    Orchestrates multiple agents — delegates tasks, collects results, merges responses.
    """

    def __init__(self, bus=None):
        self.agents: Dict[str, Agent] = {}
        self.bus = bus

    def register(self, agent: Agent):
        """Register an agent by name and connect it to the bus."""
        agent.bus = self.bus
        self.agents[agent.name] = agent

    def get(self, name: str) -> Optional[Agent]:
        """Get an agent by name."""
        return self.agents.get(name)

    def list_agents(self) -> List[str]:
        """List all registered agent names."""
        return sorted(self.agents.keys())

    def delegate(self, agent_name: str, task: str) -> dict:
        """Send a task to a specific agent."""
        agent = self.agents.get(agent_name)
        if not agent:
            return {"error": f"Unknown agent: {agent_name}"}
        return agent.process(task)

    def orchestrate(self, task: str) -> dict:
        """
        Route a task to the most appropriate agent.
        Uses the planner agent to decide routing.
        """
        # Check if we have a planner
        planner = self.agents.get("planner")
        if planner:
            plan = planner.process(f"Route this task to the right agent(s): {task}")
            return plan

        # Fallback: try each agent and return the first good result
        for name, agent in self.agents.items():
            if name == "planner":
                continue
            result = agent.process(task)
            if "error" not in result.get("user_response", "").lower():
                return result
        return {"error": "No agent could handle this task.", "commands": [], "user_response": "All agents failed."}
