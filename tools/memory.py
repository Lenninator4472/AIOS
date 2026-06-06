"""AI-DOS Plugin: Long-term memory tools for the LLM."""

from kernel.memory_store import FactMemory

_facts = FactMemory()


def tool_remember(text: str, tags: str = ""):
    """Store a fact in long-term memory. tags: comma-separated keywords."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    fid = _facts.remember(text, tags=tag_list)
    return f"Stored as fact #{fid}: {text[:80]}"


def tool_recall(query: str):
    """Search long-term memory for facts matching keywords."""
    results = _facts.recall(query)
    if not results:
        return "No matching memories found."
    lines = [f"Fact #{r['id']}: {r['text']}" for r in results]
    return "\n".join(lines)


def tool_forget(fact_id: int):
    """Delete a fact by its ID number."""
    ok = _facts.forget(fact_id)
    return f"Fact #{fact_id} deleted." if ok else f"Fact #{fact_id} not found."


def tool_fact_count():
    """Return the total number of stored facts."""
    return f"{_facts.count()} facts stored in long-term memory."
