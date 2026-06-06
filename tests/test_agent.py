"""Tests for kernel/agent.py — Multi-agent System."""
from kernel.agent import Agent, AgentOrchestrator, CODER_PROMPT, RESEARCHER_PROMPT, SYSADMIN_PROMPT


class TestAgent:
    """Agent — standalone agent with its own LLM context."""

    def test_agent_has_name_and_prompt(self):
        a = Agent("test", "You are a test agent.")
        assert a.name == "test"
        assert "test agent" in a.system_prompt

    def test_agent_starts_with_system_message(self):
        a = Agent("test", "You are a test.")
        assert len(a.messages) == 1
        assert a.messages[0]["role"] == "system"

    def test_agent_process_runs_without_error(self):
        a = Agent("test", "You are a test. Always respond with valid JSON.")
        result = a.process("Say hello")
        assert isinstance(result, dict)
        assert len(result) > 0  # LLM returned some JSON

    def test_agent_resets_context(self):
        a = Agent("test", "You are a test.")
        a.process("Hello")
        assert len(a.messages) > 1
        a.reset()
        assert len(a.messages) == 1

    def test_agent_session_log(self):
        a = Agent("test", "You are a test.")
        a.process("Hello")
        assert len(a.session_log) >= 1
        assert "input" in a.session_log[0]
        assert "output" in a.session_log[0]


class TestAgentOrchestrator:
    """AgentOrchestrator — register, list, delegate, orchestrate."""

    def test_orchestrator_empty_init(self):
        o = AgentOrchestrator()
        assert o.list_agents() == []

    def test_register_and_list(self):
        o = AgentOrchestrator()
        a = Agent("coder", CODER_PROMPT)
        o.register(a)
        assert "coder" in o.list_agents()

    def test_get_agent(self):
        o = AgentOrchestrator()
        a = Agent("research", RESEARCHER_PROMPT)
        o.register(a)
        assert o.get("research") is a
        assert o.get("ghost") is None

    def test_delegate_runs_agent(self):
        o = AgentOrchestrator()
        a = Agent("sysadmin", SYSADMIN_PROMPT)
        o.register(a)
        result = o.delegate("sysadmin", "List running processes")
        assert isinstance(result, dict)

    def test_delegate_unknown_agent(self):
        o = AgentOrchestrator()
        result = o.delegate("ghost", "Do something")
        assert "error" in result

    def test_multiple_agents_registered(self):
        o = AgentOrchestrator()
        o.register(Agent("coder", CODER_PROMPT))
        o.register(Agent("research", RESEARCHER_PROMPT))
        o.register(Agent("sysadmin", SYSADMIN_PROMPT))
        names = o.list_agents()
        assert "coder" in names
        assert "research" in names
        assert "sysadmin" in names
        assert len(names) == 3

    def test_prompts_are_different(self):
        assert CODER_PROMPT != RESEARCHER_PROMPT
        assert SYSADMIN_PROMPT != RESEARCHER_PROMPT
        assert "code" in CODER_PROMPT.lower()
        assert "research" in RESEARCHER_PROMPT.lower()
        assert "system" in SYSADMIN_PROMPT.lower()
